import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location('deploy_support', Path(__file__).resolve().parents[1] / 'scripts/deploy_support.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name) / 'config'

    def tearDown(self):
        self.temp.cleanup()

    def configure(self):
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=['localhost', 'test@example.com', '2', 'testadmin', 'no']), patch('getpass.getpass', side_effect=['a-long-test-password', 'a-long-test-password']):
            deployment.configure(self.directory)

    def test_configuration_preserves_secrets_on_rerun_and_protects_directories(self):
        self.configure()
        files = {path.name: path.read_bytes() for path in (self.directory / 'secrets').iterdir()}
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.directory / 'secrets').stat().st_mode & 0o777, 0o700)
        with patch('builtins.input', side_effect=AssertionError('No prompts on reuse')):
            deployment.configure(self.directory)
        self.assertEqual(files, {path.name: path.read_bytes() for path in (self.directory / 'secrets').iterdir()})
        self.assertEqual(deployment.check(self.directory)['domain'], 'localhost')

    def test_incomplete_configuration_is_preserved(self):
        self.directory.mkdir()
        file = self.directory / 'old-data'
        file.write_text('preserve')
        with self.assertRaises(RuntimeError):
            deployment.configure(self.directory)
        self.assertEqual(file.read_text(), 'preserve')

    def test_invalid_domain_and_missing_secrets(self):
        for value in ('https://example.com', '127.0.0.1', 'example.com;rm', 'bad_domain.com', '-bad.com', 'example.local'):
            self.assertFalse(deployment.valid_domain(value))
        for value in ('example.com', 'WWW.Example.COM', 'localhost'):
            self.assertTrue(deployment.valid_domain(value))
        self.configure()
        (self.directory / 'secrets/postgres_password').unlink()
        with self.assertRaises(RuntimeError):
            deployment.check(self.directory)

    def test_symlinked_secret_and_insecure_directory_are_rejected(self):
        self.configure()
        path = self.directory / 'secrets/postgres_password'
        original = path.read_text()
        target = Path(self.temp.name) / 'outside'
        target.write_text(original)
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(RuntimeError):
            deployment.check(self.directory)
        path.unlink()
        path.write_text(original)
        path.chmod(0o444)
        self.directory.chmod(0o755)
        with self.assertRaises(RuntimeError):
            deployment.check(self.directory)

    def test_saved_settings_must_agree(self):
        self.configure()
        path = self.directory / 'config.json'
        config = json.loads(path.read_text())
        config['domain'] = 'example.com'
        path.chmod(0o600)
        path.write_text(json.dumps(config))
        with self.assertRaises(RuntimeError):
            deployment.check(self.directory)

    def test_default_compose_env_link_is_created_and_existing_env_is_preserved(self):
        project = Path(self.temp.name) / 'project'
        deployment_directory = project / '.deploy'
        deployment_directory.mkdir(parents=True)
        (deployment_directory / 'site.env').write_text('SITE_DOMAIN="example.com"\n')
        deployment.ensure_compose_env(deployment_directory, project)
        link = project / '.env'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(), 'SITE_DOMAIN="example.com"\n')
        deployment.ensure_compose_env(deployment_directory, project)
        link.unlink()
        link.write_text('EXISTING=value\n')
        deployment.ensure_compose_env(deployment_directory, project)
        self.assertFalse(link.is_symlink())
        self.assertEqual(link.read_text(), 'EXISTING=value\n')
        link.unlink()
        deployment.ensure_compose_env(self.directory, project)
        self.assertFalse(link.exists())

    def test_noninteractive_first_run_stops_for_human_input(self):
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(RuntimeError):
            deployment.configure(self.directory)
        self.assertFalse(self.directory.exists())
