import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from studio.workspace import WorkspaceStore, ModelGateway, make_router
from studio.writing import build_pack, PACK_VERSION


class WritingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name)/"test.db")
        self.project = self.store.create({"title":"Test", "brief":"English drama; two locations"})
        self.branch = self.project["branches"][0]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY":""}):
            self.gateway = ModelGateway()
        self.endpoint = next(r.endpoint for r in make_router(self.store,self.gateway).routes if r.path.endswith('/versions'))

    def tearDown(self):
        self.temp.cleanup()

    def request(self, **fields):
        return dict(action="chat",stage="brief",writing_mode="discuss",branch_id=self.branch["id"],parent_id=self.branch["head"],instruction="Discuss",**fields)

    def test_task_modes_validate_before_call(self):
        for stage,mode in [("brief","polish"),("script","unknown"),("script",[]),("script",None)]:
            with self.subTest(stage=stage,mode=mode),patch.object(self.gateway,'generate') as generate:
                data=self.request();data.update(stage=stage,writing_mode=mode)
                with self.assertRaises(HTTPException) as error:self.endpoint(self.project['id'],data)
                self.assertEqual(400,error.exception.status_code);generate.assert_not_called()

    def test_readonly_enforced_even_when_gateway_returns_rewrite(self):
        old_route=self.project['versions'][0]['route']
        with patch.object(self.gateway,'generate',return_value=('Notes','Unwanted rewrite','deepseek','test')):
            result=self.endpoint(self.project['id'],self.request())
        self.assertEqual(old_route,result['versions'][-1]['route'])
        saved=json.loads(result['versions'][-1]['prompt_json'])['writing']
        self.assertEqual(PACK_VERSION,saved['version'])
        self.assertEqual('discuss',saved['mode'])
        self.assertEqual(64,len(saved['sha256']))

    def test_empty_stage_can_be_discussed_before_upstream_confirmation(self):
        data=self.request();data.update(stage='script',writing_mode='critique')
        def generate(project,history,instruction,prompt):
            self.assertEqual({},project['upstream'])
            self.assertEqual('draft',project['unconfirmed_reference']['brief']['status'])
            self.assertEqual('',history[-1]['document'])
            self.assertIn('notes',[s['id'] for s in prompt['writing']['skills']])
            return 'No script yet','Invented script','deepseek','test'
        with patch.object(self.gateway,'generate',side_effect=generate):result=self.endpoint(self.project['id'],data)
        self.assertEqual('',result['versions'][-1]['route']['documents']['script']['text'])
        self.assertEqual('empty',result['versions'][-1]['stage_status']['script'])

    def test_request_contains_stage_skills_and_one_model_call(self):
        self.gateway.configure({'mode':'deepseek','api_key':'test-only','model':'test-model'})
        pack=build_pack('script','polish',{'character':'character-v1'})
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reply':'Done','document':'Complete revised script'})}}]}
        with patch('studio.workspace.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as call:
            self.gateway.generate({'brief':'Two actors','active_stage':'script','upstream':{'character':'Distinct voices'}},[{'document':'Original','instruction':'Draft','reply':'Done'}],'Polish',{'body':'Keep ending','writing':pack})
        self.assertEqual(1,call.call_count)
        payload=json.loads(call.call_args.args[0].data)
        self.assertIn(pack['instructions'],payload['messages'][0]['content'])
        self.assertEqual('polish',json.loads(payload['messages'][1]['content'])['task_mode'])
        self.assertEqual(['scene','dialogue','localize'],[s['id'] for s in pack['skills']])

    def test_gateway_readonly_accepts_empty_document_and_rejects_bad_structure(self):
        self.gateway.configure({'mode':'deepseek','api_key':'test-only','model':'test-model'})
        history=[{'document':'','instruction':'Discuss','reply':'None'}]
        for doc in ('','Unwanted rewrite'):
            raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reply':'Need more context','document':doc})}}]}
            with patch('studio.workspace.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
                result=self.gateway.generate({'brief':'B','active_stage':'script'},history,'Discuss',{'writing':build_pack('script','discuss')})
            self.assertEqual('',result[1])

    def test_builtin_upgrade_preserves_custom_and_past_snapshot(self):
        self.store.save_prompt({'title':'Custom','category':'User','body':'Keep my guide'})
        self.store.append(self.project['id'],self.branch['id'],self.branch['head'],'Old','Reply','Draft','manual','',{'body':'Old prompt'})
        with self.store.connect() as c:c.execute("UPDATE w_prompts SET body='Old builtin' WHERE id='seed-script'")
        reloaded=WorkspaceStore(self.store.path)
        self.assertNotEqual('Old builtin',next(p['body'] for p in reloaded.prompts() if p['id']=='seed-script'))
        self.assertEqual('Keep my guide',next(p['body'] for p in reloaded.prompts() if not p['builtin']))
        self.assertEqual('Old prompt',json.loads(reloaded.project(self.project['id'])['versions'][-1]['prompt_json'])['body'])

    def test_source_records_and_pack_fingerprint(self):
        sources=json.loads((Path(__file__).resolve().parents[1]/'third_party/autopunk-media-skills/sources.json').read_text())
        shas={s['git_blob_sha'] for s in sources['files']}
        extra=json.loads((Path(__file__).resolve().parents[1]/'third_party/short-drama/sources.json').read_text(encoding='utf-8'))
        shas.update(s['git_blob_sha'] for s in extra['files'])
        for stage in ['brief','concept','character','outline','scenes','script']:
            pack=build_pack(stage)
            self.assertTrue(all(s['git_blob_sha'] in shas for s in pack['skills']))
        self.assertNotEqual(build_pack('script','write')['sha256'],build_pack('script','discuss')['sha256'])
