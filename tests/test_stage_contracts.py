import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from studio.contracts import STAGES, issues, template
from studio.route import normalize, statuses
from studio.samples import SAMPLES, SELECTED_CONCEPT
from studio.workspace import WorkspaceStore, ModelGateway, make_router
from studio.writing import build_pack


class StageContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.tmp.name)/'test.db')
        self.p = self.store.create({'title': 'Contract test', 'brief': SAMPLES['brief']})
        self.bid = self.p['branches'][0]['id']
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            self.gateway = ModelGateway()
        self.endpoint = next(r.endpoint for r in make_router(self.store, self.gateway).routes if r.path.endswith('/versions'))

    def tearDown(self):
        self.tmp.cleanup()

    def head(self):
        return next(b['head'] for b in self.p['branches'] if b['id'] == self.bid)

    def current(self):
        return next(v for v in self.p['versions'] if v['id'] == self.head())

    def act(self, stage, action, **fields):
        self.p = self.endpoint(self.p['id'], dict(stage=stage, action=action, branch_id=self.bid, parent_id=self.head(), **fields))
        return self.current()

    def complete(self):
        for s in STAGES:
            if s != 'brief':
                self.act(s, 'edit', document=SAMPLES[s])
            if s == 'concept':
                self.act(s, 'select_concept', selection=SELECTED_CONCEPT)
            self.act(s, 'confirm')

    def test_draft_is_saveable_but_empty_sections_cannot_be_confirmed(self):
        self.act('brief', 'edit', document=template('brief'))
        before = self.head()
        with self.assertRaises(HTTPException) as e:
            self.act('brief', 'confirm')
        self.assertEqual(400, e.exception.status_code)
        self.assertEqual(before, self.store.project(self.p['id'])['branches'][0]['head'])
        self.assertTrue(self.current()['stage_checks']['brief'])

    def test_selected_direction_required_and_candidates_never_sent_downstream(self):
        self.act('brief', 'confirm')
        self.act('concept', 'edit', document=SAMPLES['concept'])
        with self.assertRaises(HTTPException):
            self.act('concept', 'confirm')
        for selection in ('方向一', ''):
            with self.assertRaises(HTTPException):
                self.act('concept', 'select_concept', selection=selection)
        self.act('concept', 'select_concept', selection=SELECTED_CONCEPT)
        self.act('concept', 'confirm')
        def generate(project, history, instruction, prompt):
            self.assertEqual(SELECTED_CONCEPT, project['upstream']['concept'])
            self.assertNotIn('方向二', json.dumps(project['upstream'], ensure_ascii=False))
            return 'Done', SAMPLES['character'], 'deepseek', 'mock'
        with patch.object(self.gateway, 'generate', side_effect=generate):
            self.act('character', 'chat', instruction='Write characters')

    def test_selection_change_and_candidate_rewrite_invalidate_downstream(self):
        self.complete()
        old = deepcopy(self.current()['route'])
        self.act('concept', 'select_concept', selection=SELECTED_CONCEPT+' 修改：最终决定拒绝控制条件。')
        for s in STAGES[2:]:
            self.assertEqual('stale', self.current()['stage_status'][s])
        self.assertEqual(old['documents']['script']['text'], self.current()['route']['documents']['script']['text'])
        self.act('concept', 'edit', document=SAMPLES['concept']+'\n增加候选说明')
        self.assertEqual('', self.current()['route']['selected_concept'])

    def test_scene_stage_required_before_script_generation(self):
        self.complete()
        self.act('scenes', 'edit', document=SAMPLES['scenes']+'\n修改预计时长。')
        with patch.object(self.gateway, 'generate') as generate:
            with self.assertRaises(HTTPException):
                self.act('script', 'chat', instruction='Write')
            generate.assert_not_called()

    def test_old_routes_are_projected_without_rewriting_original_rows(self):
        old = deepcopy(self.current()['route'])
        old.pop('schema_version'); old.pop('selected_concept')
        old['documents'].pop('scenes')
        old['documents']['script'].update(text='Old English screenplay', confirmed=True, revision='old-script')
        old['documents']['review'] = dict(text='Old review report', confirmed=True, revision='old-review', dependencies={})
        raw = json.dumps(old, ensure_ascii=False)
        with self.store.connect() as c:
            c.execute("UPDATE w_versions SET route_json=?,stage='review' WHERE id=?", (raw, self.head()))
        self.p = self.store.project(self.p['id'])
        projected = self.current()['route']
        self.assertEqual('Old review report', projected['archived_review']['text'])
        self.assertEqual('', projected['documents']['scenes']['text'])
        self.assertEqual('Old English screenplay', projected['documents']['script']['text'])
        self.assertNotEqual('confirmed', statuses(projected)['script'])
        self.assertEqual(projected, normalize(projected))
        self.act('brief', 'confirm')
        self.assertEqual('Old review report', self.current()['route']['archived_review']['text'])
        with self.store.connect() as c:
            self.assertEqual(raw, c.execute('SELECT route_json FROM w_versions WHERE parent_id IS NULL').fetchone()[0])

    def test_reviews_are_read_only_in_every_stage(self):
        self.complete()
        for s in STAGES:
            before = deepcopy(self.current()['route'])
            with patch.object(self.gateway, 'generate', return_value=('Review evidence', 'Unexpected rewrite', 'deepseek', 'mock')):
                self.act(s, 'chat', writing_mode='critique', instruction='Review this stage')
            self.assertEqual(before, self.current()['route'])
            self.assertEqual('critique', json.loads(self.current()['prompt_json'])['writing']['mode'])

    def test_prompt_scopes_and_stage_specific_rules(self):
        custom = self.store.save_prompt(dict(title='Scene test', category='Team', body='No dialogue', stage='scenes'))
        library = self.store.prompts()
        self.assertEqual(['scenes'], next(p for p in library if p['id'] == custom['id'])['stages'])
        self.assertEqual(['script'], next(p for p in library if p['id'] == 'seed-localize')['stages'])
        self.assertEqual(['micro_scene'], [s['id'] for s in build_pack('scenes')['skills']])
        self.assertNotIn('英文剧本采用', build_pack('brief')['instructions'])
        self.assertNotIn('前三集可见变化', build_pack('character')['instructions'])
        with self.assertRaises(HTTPException):
            build_pack('review')

    def test_contract_rejects_additional_episode_and_missing_scene_or_script_headers(self):
        self.assertFalse(issues('outline', SAMPLES['outline']))
        self.assertTrue(issues('outline', SAMPLES['outline']+'\n## 第4集\nExtra'))
        self.assertTrue(issues('scenes', SAMPLES['scenes'].replace('### 场景1', 'Scene one')))
        self.assertTrue(issues('script', SAMPLES['script'].replace('INT.', 'Inside')))

    def test_concurrent_selection_cannot_overwrite_another_editor(self):
        self.complete(); old_head = self.head()
        self.act('concept', 'select_concept', selection=SELECTED_CONCEPT+' 新决定。')
        with self.assertRaises(HTTPException) as e:
            self.endpoint(self.p['id'], dict(stage='concept', action='select_concept', branch_id=self.bid, parent_id=old_head, selection=SELECTED_CONCEPT+' 过时决定。'))
        self.assertEqual(409, e.exception.status_code)
        self.assertTrue(self.current()['route']['selected_concept'].endswith('新决定。'))

    def test_evaluation_baseline_keeps_the_same_contract(self):
        from studio.contracts import CONTRACTS
        baseline = build_pack('script', include_skills=False)
        enhanced = build_pack('script')
        self.assertEqual([], baseline['skills'])
        for field in ('role', 'boundary', 'check'):
            self.assertIn(CONTRACTS['script'][field], baseline['instructions'])
            self.assertIn(CONTRACTS['script'][field], enhanced['instructions'])
        self.assertNotEqual(baseline['sha256'], enhanced['sha256'])

    def test_out_of_scope_request_can_preserve_an_empty_draft(self):
        import io
        self.gateway.configure({'mode': 'deepseek', 'api_key': 'mock-only', 'model': 'mock'})
        raw = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'reply': '请切换到首集剧本阶段。', 'document': ''})}}]}
        with patch('studio.workspace.urlopen', return_value=io.BytesIO(json.dumps(raw).encode())):
            result = self.gateway.generate({'brief': 'Test', 'active_stage': 'concept'}, [{'document': '', 'instruction': '', 'reply': ''}], 'Write a script', {'writing': build_pack('concept')})
        self.assertEqual('', result[1])
