"""Safety checks for status inspection, without cloud mutation or credentials."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec = importlib.util.spec_from_file_location('cloud_status', Path(__file__).with_name('cloud_status.py'))
status = importlib.util.module_from_spec(spec); spec.loader.exec_module(status)


class InspectionTests(unittest.TestCase):
    def workspace(self, root):
        app = root / 'guitarscribe'
        path = app / 'infra/on_demand'; path.mkdir(parents=True)
        config = dict(project_id='hanana-491223', project_number='324350766154', region='asia-east1',
                      zone='asia-east1-b', service='guitarscribe', instance='guitarscribe-personal',
                      url='https://guitarscribe-324350766154.asia-east1.run.app', bucket='private', monthly_target_twd=300)
        (path / 'deployment.json').write_text(json.dumps(config))
        credentials = app / 'output/cloud-control'; credentials.mkdir(parents=True)
        (credentials / 'access.json').write_text(json.dumps(dict(username='owner', password='SECRET_NOT_IN_REPORT')))
        return path / 'deployment.json'

    def test_stopped_inspection_never_starts_or_leaks_credentials_and_bounds_backup_output(self):
        calls = []
        def runner(args):
            calls.append(args)
            self.assertNotIn('start', args); self.assertNotIn('stop', args); self.assertNotIn('deploy', args)
            self.assertIn('--project=hanana-491223', args)
            if 'ls' in args:
                self.assertNotIn('--long', args)
                return {'ok':True,'data':[{'type':'cloud_object','metadata':dict(name=f'backup{i}',timeCreated=f'{i:03}',generation=str(i),size='5',unknown='do not print')} for i in range(8)]}
            return {'ok': True, 'data': {'status': 'TERMINATED'}}
        def fetch(url, access=None):
            if access: self.assertEqual(access['password'], 'SECRET_NOT_IN_REPORT')
            return {'http_status': 200, 'state': 'stopped', 'can_wake': True} if access else {'http_status':401}
        with TemporaryDirectory() as tmp:
            root=Path(tmp); self.workspace(root); report=status.inspect(root,runner,fetch)
        self.assertEqual(len(calls),3)
        self.assertEqual(report['backup_manifests']['count'],8)
        self.assertEqual(len(report['backup_manifests']['latest']),5)
        self.assertFalse(report['automatic_wake'])
        self.assertNotIn('SECRET_NOT_IN_REPORT',json.dumps(report))
        self.assertNotIn('do not print',json.dumps(report))

    def test_changed_origin_is_rejected_before_reading_or_sending_credentials(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); path=self.workspace(root); config=json.loads(path.read_text())
            config['url']='https://another.example';path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                status.inspect(root,lambda _:self.fail('must not query'),lambda *_:self.fail('must not fetch'))

    def test_missing_access_or_failed_cloud_check_is_explicit_not_claimed_healthy(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);self.workspace(root)
            (root/'guitarscribe/output/cloud-control/access.json').unlink()
            report=status.inspect(root,lambda _:dict(ok=False,error='denied'),lambda *_:dict(http_status=401))
            self.assertFalse(report['vm']['ok'])
            self.assertFalse(report['backup_manifests']['ok'])
            self.assertIn('unavailable',report['authenticated']['error'])
            self.assertEqual(report['billing']['actual_cost'],'not_checked')


if __name__ == '__main__': unittest.main()
