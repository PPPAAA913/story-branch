import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from studio.workspace import WorkspaceStore, ModelGateway, make_router


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.tmp.name) / 'test.db')
        self.p = self.store.create({'title': 'Test', 'brief': 'Original brief'})
        self.pid = self.p['id']
        self.main = self.p['branches'][0]
        self.head = self.main['head']
        self.gateway = ModelGateway()

    def tearDown(self):
        self.tmp.cleanup()

    def test_delete_protects_main_and_updated_branch(self):
        with self.assertRaises(HTTPException) as e:
            self.store.delete_branch(self.pid, self.main['id'], {'head': self.head})
        self.assertEqual(400, e.exception.status_code)
        fork = self.store.fork(self.pid, {'version_id': self.head, 'name': 'Alternative'})
        bid = fork['branch_id']
        self.store.append(self.pid, bid, self.head, 'Edit', 'Saved', 'New draft', 'manual', '', {})
        with self.assertRaises(HTTPException) as e:
            self.store.delete_branch(self.pid, bid, {'head': self.head})
        self.assertEqual(409, e.exception.status_code)
        self.assertEqual(2, len(self.store.project(self.pid)['branches']))

    def test_delete_keeps_descendant_ancestry_and_project_scope(self):
        fork = self.store.fork(self.pid, {'version_id': self.head, 'name': 'Parent'})
        bid = fork['branch_id']
        p = self.store.append(self.pid, bid, self.head, 'Edit', 'Saved', 'Shared', 'manual', '', {})
        head = next(b['head'] for b in p['branches'] if b['id'] == bid)
        child = self.store.fork(self.pid, {'version_id': head, 'name': 'Child'})['branch_id']
        other = self.store.create({'title': 'Other', 'brief': 'Other'})
        with self.assertRaises(HTTPException):
            self.store.delete_branch(other['id'], bid, {'head': head})
        p = self.store.delete_branch(self.pid, bid, {'head': head})
        self.assertNotIn(bid, [b['id'] for b in p['branches']])
        _, history = self.store.context(self.pid, child, head)
        self.assertEqual('Shared', history[-1]['document'])
        self.store.append(self.pid, child, head, 'Continue', 'Saved', 'Continued', 'manual', '', {})

    def response(self, content, reason='stop'):
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':reason,'message':{'content':content}}]}).encode())

    def test_long_output_and_context_and_fenced_json(self):
        self.gateway.configure({'mode':'deepseek', 'api_key':'test'})
        _, history = self.store.context(self.pid, self.main['id'], self.head)
        history[-1]['document'] = 'x' * 70000
        draft = '新剧本' * 20000
        content = '```json\n' + json.dumps({'reply':'完成','document':draft}) + '\n```'
        with patch('studio.workspace.urlopen', return_value=self.response(content)) as call:
            result = self.gateway.generate(self.p, history, 'Continue', {})
        self.assertEqual(draft, result[1])
        self.assertEqual(81920, json.loads(call.call_args.args[0].data)['max_tokens'])
        self.assertEqual(600, call.call_args.kwargs['timeout'])
        endpoint = next(r.endpoint for r in make_router(self.store,self.gateway).routes if r.path.endswith('/versions'))
        p = endpoint(self.pid, {'action':'edit','branch_id':self.main['id'],'parent_id':self.head,'document':draft})
        self.assertEqual(draft, p['versions'][-1]['document'])

    def test_truncation_recovery_keeps_original_version(self):
        self.gateway.configure({'mode':'deepseek','api_key':'test'})
        endpoint = next(r.endpoint for r in make_router(self.store,self.gateway).routes if r.path.endswith('/versions'))
        with patch('studio.workspace.urlopen',return_value=self.response('Partial draft', 'length')):
            with self.assertRaises(HTTPException) as e:
                endpoint(self.pid,{'action':'chat','branch_id':self.main['id'],'parent_id':self.head,'instruction':'Write'})
        self.assertEqual('Partial draft', e.exception.detail['response_text'])
        self.assertIn('截断', e.exception.detail['message'])
        self.assertEqual(1, len(self.store.project(self.pid)['versions']))

    def test_invalid_limit_does_not_change_key_or_configuration(self):
        before = self.gateway.status()
        for invalid in [True, 0, 393217, '81920']:
            with self.assertRaises(HTTPException):
                self.gateway.configure({'mode':'deepseek','api_key':'new-key','max_tokens':invalid})
        self.assertEqual(before, self.gateway.status())
        self.gateway.configure({'mode':'demo','max_tokens':100000})
        self.assertEqual(100000, self.gateway.status()['max_tokens'])
