import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from studio.route import STAGES
from studio.samples import SAMPLES, SELECTED_CONCEPT
from studio.workspace import WorkspaceStore, ModelGateway, make_router


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name)/"test.db")
        self.p = self.store.create({"title":"Route", "brief":SAMPLES["brief"]})
        self.bid = self.p["branches"][0]["id"]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY":""}):
            self.gateway = ModelGateway()
        self.endpoint = next(r.endpoint for r in make_router(self.store,self.gateway).routes if r.path.endswith('/versions'))

    def tearDown(self):
        self.temp.cleanup()

    def head(self):
        return next(b["head"] for b in self.p["branches"] if b["id"]==self.bid)

    def version(self):
        return next(v for v in self.p["versions"] if v["id"]==self.head())

    def action(self,stage,action,**fields):
        self.p=self.endpoint(self.p["id"],dict(stage=stage,action=action,branch_id=self.bid,parent_id=self.head(),**fields))
        return self.version()

    def complete(self):
        for stage in STAGES:
            if stage!='brief':
                self.action(stage,'edit',document=SAMPLES[stage])
            if stage=='concept':
                self.action(stage,'select_concept',selection=SELECTED_CONCEPT)
            self.action(stage,'confirm')

    def test_upstream_changes_mark_all_descendants_and_confirmation_is_explicit(self):
        self.complete()
        original=self.version()
        result=self.action('character','edit',document=SAMPLES['character']+'\nCharacter becomes a reporter')
        self.assertEqual('draft',result['stage_status']['character'])
        for s in ('outline','scenes','script'):
            self.assertEqual('stale',result['stage_status'][s])
        with self.assertRaises(HTTPException):
            self.action('script','confirm')
        self.action('character','confirm')
        self.action('outline','confirm')
        self.action('scenes','confirm')
        self.assertEqual('stale',self.version()['stage_status']['script'])
        self.action('script','confirm')
        self.assertEqual('confirmed',self.version()['stage_status']['script'])
        self.assertEqual(SAMPLES['script'],self.version()['route']['documents']['script']['text'])
        self.assertEqual(SAMPLES['character'],original['route']['documents']['character']['text'])

    def test_fork_keeps_entire_route_and_survives_restart(self):
        self.complete()
        fork_head=self.head()
        fork=self.store.fork(self.p['id'],{'version_id':fork_head,'name':'Alternative'})
        self.action('brief','edit',document='Changed main brief')
        self.p=self.store.project(self.p['id']);self.bid=fork['branch_id']
        self.assertEqual(SAMPLES['brief'],self.version()['route']['documents']['brief']['text'])
        self.assertTrue(all(x=='confirmed' for x in self.version()['stage_status'].values()))
        self.action('script','edit',document='Different ending')
        reloaded=WorkspaceStore(self.store.path).project(self.p['id'])
        self.assertEqual(self.p,reloaded)

    def test_generation_checks_upstream_before_call_and_keeps_other_stages(self):
        with patch.object(self.gateway,'generate') as gen:
            with self.assertRaises(HTTPException):
                self.action('script','chat',instruction='Write')
            gen.assert_not_called()
        self.action('brief','confirm')
        def generate(project,history,instruction,prompt):
            self.assertEqual('concept',project['active_stage'])
            self.assertEqual({'brief':SAMPLES['brief']},project['upstream'])
            self.assertEqual('',history[-1]['document'])
            return 'Done','Selected direction','deepseek','test'
        with patch.object(self.gateway,'generate',side_effect=generate):
            result=self.action('concept','chat',instruction='Write')
        self.assertEqual(SAMPLES['brief'],result['route']['documents']['brief']['text'])
        self.assertEqual('Selected direction',result['route']['documents']['concept']['text'])
        self.assertEqual('draft',result['stage_status']['concept'])

    def test_discussion_unchanged_document_does_not_invalidate_confirmed_stage(self):
        self.complete()
        old=self.version()['route']
        with patch.object(self.gateway,'generate',return_value=('Discussion only',SAMPLES['character'],'deepseek','test')):
            self.action('character','chat',instruction='Discuss motivation')
        self.assertEqual(old,self.version()['route'])

    def test_manual_edit_cannot_silently_clear_stale_status(self):
        self.complete()
        self.action('brief','edit',document='New brief')
        self.action('outline','edit',document='Manually adjusted outline')
        self.assertEqual('stale',self.version()['stage_status']['outline'])

    def test_demo_full_workflow_produces_script_and_synopsis(self):
        self.action('brief','confirm')
        for stage in STAGES[1:]:
            self.action(stage,'chat',instruction='Generate '+stage)
            if stage=='concept':
                self.action(stage,'select_concept',selection=SELECTED_CONCEPT)
            self.action(stage,'confirm')
        script=self.version()['route']['documents']['script']['text']
        self.assertIn('INT. PRODUCTION OFFICE',script)
        self.assertIn('中文梗概',script)
        self.assertTrue(all(x=='confirmed' for x in self.version()['stage_status'].values()))

    def test_ai_conflict_preserves_original_upstream_snapshot(self):
        self.complete()
        old_head=self.head()
        main_bid=self.bid
        def concurrent(*args):
            self.store.append(self.p['id'],main_bid,old_head,'Change brief','Saved','New main brief','manual','',{},stage='brief')
            return 'Done','Alternate generated script','deepseek','test'
        with patch.object(self.gateway,'generate',side_effect=concurrent):
            result=self.endpoint(self.p['id'],dict(action='chat',stage='script',branch_id=main_bid,parent_id=old_head,instruction='Revise'))
        self.p=result;self.bid=result['recovered_branch_id']
        self.assertEqual(SAMPLES['brief'],self.version()['route']['documents']['brief']['text'])
        self.assertEqual('Alternate generated script',self.version()['route']['documents']['script']['text'])
        self.bid=main_bid
        self.assertEqual('New main brief',self.version()['route']['documents']['brief']['text'])
        self.assertEqual(SAMPLES['script'],self.version()['route']['documents']['script']['text'])

    def test_v03_migration_preserves_legacy_documents_without_guessing_stage(self):
        self.store.append(self.p['id'],self.bid,self.head(),'Legacy edit','Saved','Unstructured older draft','manual','',{})
        with self.store.connect() as c:
            c.execute('ALTER TABLE w_versions DROP COLUMN route_json')
            c.execute('ALTER TABLE w_versions DROP COLUMN stage')
        self.store=WorkspaceStore(self.store.path)
        self.p=self.store.project(self.p['id'])
        route=self.version()['route']
        self.assertEqual('Unstructured older draft',route['legacy'])
        self.assertEqual('',route['documents']['script']['text'])
        self.assertEqual(SAMPLES['brief'],route['documents']['brief']['text'])
        self.assertEqual(1,len(list(Path(self.temp.name).glob('*.pre-v04-*.db'))))

    def test_stale_confirmation_does_not_change_newer_route(self):
        old_head=self.head()
        self.action('brief','edit',document='New brief')
        with self.assertRaises(HTTPException) as error:
            self.endpoint(self.p['id'],dict(action='confirm',stage='brief',branch_id=self.bid,parent_id=old_head))
        self.assertEqual(409,error.exception.status_code)
        self.assertEqual('draft',self.version()['stage_status']['brief'])
