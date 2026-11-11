import os
from pathlib import Path
import tempfile
import unittest

from studio.auth import AuthStore
from studio.backup import backup
from studio.workspace import WorkspaceStore


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'workspace.db'
        self.store = WorkspaceStore(self.path)
        self.auth = AuthStore(self.path)
        self.uid = self.auth.add_user('test','Test','test-password-123')

    def tearDown(self):
        self.tmp.cleanup()

    def test_successful_logins_do_not_exhaust_shared_ip(self):
        for _ in range(22):
            token,error = self.auth.login('test','test-password-123','campus')
            self.assertIsNone(error)
            self.auth.logout(token)
        with self.auth.connect() as c:
            self.assertEqual(0,c.execute("SELECT count FROM login_attempts WHERE bucket='ip:campus'").fetchone()[0])

    def test_success_does_not_clear_other_failed_attempts_on_ip(self):
        self.auth.login('other','wrong','campus')
        self.auth.login('test','test-password-123','campus')
        with self.auth.connect() as c:
            self.assertEqual(1,c.execute("SELECT count FROM login_attempts WHERE bucket='ip:campus'").fetchone()[0])

    def test_backup_restores_project_branch_version_and_membership(self):
        project=self.store.create({'title':'Backup test','brief':'Original'}, {'id':self.uid,'name':'Test'})
        fork=self.store.fork(project['id'],{'version_id':project['branches'][0]['head'],'name':'Alternative'})
        dest=backup(self.path,Path(self.tmp.name)/'backup.db')
        restored=WorkspaceStore(dest)
        self.assertEqual(fork['project'],restored.project(project['id']))
        self.assertTrue(AuthStore(dest).member(project['id'],self.uid))
        with self.assertRaises(ValueError):backup(self.path,dest)
        with self.assertRaises(ValueError):backup(self.path,self.path)

    def test_missing_source_creates_no_empty_database(self):
        missing=Path(self.tmp.name)/'missing.db'
        with self.assertRaises(ValueError):backup(missing,Path(self.tmp.name)/'out.db')
        self.assertFalse(missing.exists())
