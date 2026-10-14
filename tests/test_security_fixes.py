import importlib.util
import json
from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from bs4 import BeautifulSoup
from jose import jwt
from sqlalchemy import create_engine, text

import test_site_content as content_tests
import main
from admin_sessions import create_admin_session, fingerprint
from html_content import clean_html
from models import AdminUser, AdminSession, FormInfo, FormVersion, FormSubmission, SystemSetting
from request_limits import form_rate_storage
from security import hash_password


class SecurityFixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client, self.sessions = self.fixture.client, self.fixture.sessions
        self.upload_dir = Path(self.fixture.temp.name) / 'forms'
        self.upload_patch = patch('form_uploads.UPLOAD_DIR', self.upload_dir)
        self.upload_patch.start()
        with self.sessions() as db:
            db.add(AdminUser(username='system', password_hash='unused', is_active=True, is_sysadmin=True))
            db.commit()

    def tearDown(self):
        self.upload_patch.stop()
        self.fixture.tearDown()

    def login(self, username='system'):
        self.client.cookies.clear()
        self.fixture.login(username)

    def csrf(self):
        soup = BeautifulSoup(self.client.get('/admin/form-submissions').text, 'html.parser')
        return soup.select_one('input[name=csrf]')['value']

    def form(self, required_file=True):
        self.login('super')
        response = self.client.post('/admin/forms/create', json={
            'name': 'Upload', 'slug': 'upload', 'display_name': 'Upload', 'fields': [
                {'name': 'name', 'type': 'text', 'question': 'Imię', 'required': True},
                {'name': 'video', 'type': 'file', 'question': 'Film', 'required': required_file},
            ],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.client.cookies.clear()
        return {'form_id': response.json()['form_id'], 'form_version_id': response.json()['version_id'], 'answers': {'name': 'Tester'}}

    def upload(self, payload, data=b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 20, name='demo.mp4'):
        return self.client.post('/api/forms/submit', data={'payload': json.dumps(payload)},
                                files={'file:video': (name, data, 'video/mp4')})

    def test_sysadmin_only_account_management_and_csrf(self):
        for username in ('regular', 'super'):
            self.login(username)
            self.assertEqual(self.client.get('/admin/admins').status_code, 403)
            self.assertEqual(self.client.post('/admin/admins/create', data={'username': 'x', 'password': 'abc'}).status_code, 403)
        self.login()
        self.assertEqual(self.client.get('/admin/admins').status_code, 200)
        self.assertEqual(self.client.get('/admin/content').status_code, 200)
        self.assertEqual(self.client.post('/admin/admins/create', data={
            'username': 'x', 'password': 'abcdefgh123456', 'csrf': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/admin/admins/create', data={
            'username': 'x', 'password': 'short', 'csrf': self.csrf()}).status_code, 422)
        self.assertEqual(self.client.post('/admin/admins/create', data={
            'username': 'new', 'password': 'abcdefgh123456', 'csrf': self.csrf(),
            'is_superadmin': 'true', 'is_sysadmin': 'true'}).status_code, 200)
        with self.sessions() as db:
            account = db.query(AdminUser).filter_by(username='new').one()
            self.assertTrue(account.is_superadmin)
            self.assertFalse(account.is_sysadmin)
            self.assertNotEqual(account.password_hash, 'abcdefgh123456')
            account_id = account.id
        self.assertEqual(self.client.post('/admin/admins/create', data={
            'username': 'new', 'password': 'abcdefgh123456', 'csrf': self.csrf()}).status_code, 409)
        self.assertEqual(self.client.post(f'/admin/admins/{account_id}/delete', data={'csrf': self.csrf()}).status_code, 200)
        with self.sessions() as db:
            self.assertIsNone(db.get(AdminUser, account_id))

    def test_disable_demote_reset_password_and_self_protection(self):
        self.login('super')
        old_token = self.client.cookies.get('admin_session')
        self.login()
        with self.sessions() as db:
            account_id = db.query(AdminUser).filter_by(username='super').one().id
            self_id = db.query(AdminUser).filter_by(username='system').one().id
        response = self.client.post(f'/admin/admins/{account_id}/update', data={'csrf': self.csrf(), 'password': 'new-password-123'})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            account = db.get(AdminUser, account_id)
            self.assertFalse(account.is_active)
            self.assertFalse(account.is_superadmin)
            self.assertIsNone(db.get(AdminSession, fingerprint(old_token)))
        for action in ('delete', 'update'):
            self.assertEqual(self.client.post(f'/admin/admins/{self_id}/{action}', data={'csrf': self.csrf()}).status_code, 422)
        self.assertEqual(self.client.post(f'/admin/admins/{account_id}/update', data={'csrf': self.csrf(), 'is_active': 'true'}).status_code, 200)
        self.client.cookies.clear()
        self.client.cookies.set('admin_session', old_token)
        self.assertIn(self.client.get('/admin/content', follow_redirects=False).status_code, (303, 307))

    def test_login_disabled_expired_and_legacy_sessions(self):
        with self.sessions() as db:
            account = db.query(AdminUser).filter_by(username='super').one()
            account.password_hash = hash_password('real-password-123')
            account.is_active = False
            db.commit()
        response = self.client.post('/adminLogin', data={'username': 'super', 'password': 'real-password-123'})
        self.assertNotIn('admin_session', response.cookies)
        with self.sessions() as db:
            account = db.query(AdminUser).filter_by(username='super').one()
            account.is_active = True
            db.commit()
        response = self.client.post('/adminLogin', data={'username': 'super', 'password': 'real-password-123'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        token = response.cookies['admin_session']
        self.assertNotIn('real-password', token)
        self.assertNotIn('.', token)
        self.assertEqual(self.client.get('/admin/content').status_code, 200)
        with self.sessions() as db:
            db.get(AdminSession, fingerprint(token)).expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get('/admin/content', follow_redirects=False).status_code, 303)
        self.client.cookies.clear()
        self.client.cookies.set('admin_session', jwt.encode({'sub': 'super'}, main.SECRET_KEY, algorithm='HS256'))
        self.assertEqual(self.client.get('/admin/content', follow_redirects=False).status_code, 303)

    def test_password_change_and_logout_revoke_tokens(self):
        self.login('super')
        with self.sessions() as db:
            db.query(AdminUser).filter_by(username='super').one().password_hash = 'different-server-hash'
            db.commit()
        self.assertEqual(self.client.get('/admin/content', follow_redirects=False).status_code, 303)
        self.login('regular')
        token = self.client.cookies.get('admin_session')
        self.assertEqual(self.client.post('/admin/logout', data={'csrf': 'wrong'}).status_code, 403)
        response = self.client.post('/admin/logout', data={'csrf': self.csrf()}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('Max-Age=0', response.headers['set-cookie'])
        self.client.cookies.clear()
        self.client.cookies.set('admin_session', token)
        self.assertIn(self.client.get('/admin/form-submissions', follow_redirects=False).status_code, (303, 307))

    def test_host_header_does_not_bypass_auth_or_page_visibility(self):
        with patch('main.send_email') as email:
            for host in ('testserver', 'testserver/ignored?path='):
                response = self.client.post('/admin/send-email', headers={'Host': host}, data={
                    'mode': 'test', 'table': 'viewers', 'test_email': 'test@example.invalid', 'subject': 'test', 'body': 'test'}, follow_redirects=False)
                self.assertEqual(response.status_code, 303)
            email.assert_not_called()
        # Set the actual visibility setting through the existing interface.
        self.login('super')
        self.client.post('/admin/content/pages')
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/registration', headers={'Host': 'testserver/ignored?path='}).status_code, 404)

    def test_upload_download_ranges_and_regular_admin_playback(self):
        payload = self.form()
        response = self.upload(payload)
        self.assertEqual(response.status_code, 200, response.text)
        submission_id = response.json()['submission_id']
        url = f'/admin/uploads/{submission_id}/video'
        self.assertEqual(self.client.get(url, follow_redirects=False).status_code, 303)
        self.login('regular')
        html = self.client.get(f"/admin/form-submissions?form_id={payload['form_id']}").text
        self.assertIn(f'src="{url}"', html)
        self.assertIn('Pobierz demo.mp4', html)
        response = self.client.get(url, headers={'Range': 'bytes=0-11'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 12)
        self.assertEqual(response.headers['content-type'], 'video/mp4')
        self.assertIn('inline', response.headers['content-disposition'])
        self.assertIn('attachment', self.client.get(url + '?download=true').headers['content-disposition'])
        self.client.cookies.clear()
        self.assertEqual(self.client.get(url, follow_redirects=False).status_code, 303)

    def test_invalid_missing_forged_files_and_cleanup(self):
        payload = self.form()
        self.assertEqual(self.client.post('/api/forms/submit', json=payload).status_code, 422)
        self.assertEqual(self.upload(payload, b'<script>alert(1)</script>', 'evil.mp4').status_code, 422)
        self.assertEqual(self.upload(payload, b'%PDF-1.7', 'evil.html').status_code, 422)
        self.assertEqual(self.client.post('/api/forms/submit', json={**payload, 'answers': {'name': 'x', 'video': '/etc/passwd'}}).status_code, 422)
        with patch('form_uploads.MAX_FILE_SIZE', 12):
            self.assertEqual(self.upload(payload).status_code, 413)
        with patch('form_uploads.MAX_STORAGE_SIZE', 1):
            self.assertEqual(self.upload(payload).status_code, 503)
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('database unavailable')):
            self.assertEqual(self.upload(payload).status_code, 500)
        self.assertFalse(list(self.upload_dir.glob('*.mp4')))
        with self.sessions() as db:
            self.assertEqual(db.query(FormSubmission).count(), 0)

    def test_rate_limit_is_before_body_parsing_and_limits_text(self):
        payload = self.form(False)
        response = self.client.post('/api/forms/submit', json={**payload, 'answers': {'name': 'x' * 10001}})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post('/api/forms/submit', content=b'x' * (256 * 1024 + 1), headers={'Content-Type': 'application/json'}).status_code, 413)
        form_rate_storage.reset()
        for _ in range(10):
            self.assertEqual(self.client.post('/api/forms/submit', json=payload).status_code, 200)
        with patch('starlette.requests.Request.json', side_effect=AssertionError('Must not parse rejected requests')):
            response = self.client.post('/api/forms/submit', json=payload)
        self.assertEqual(response.status_code, 429)
        self.assertIn('retry-after', response.headers)
        with self.sessions() as db:
            self.assertEqual(db.query(FormSubmission).count(), 10)

    def test_streamed_body_limits_and_form_parser_limits(self):
        payload = self.form(False)
        def chunks():
            yield b'x' * (128 * 1024)
            yield b'x' * (128 * 1024 + 1)
        response = self.client.post('/api/forms/submit', content=chunks(), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        many_fields = '&'.join(['username=invalid', 'password=invalid'] + [f'f{i}=1' for i in range(1001)])
        self.assertEqual(self.client.post('/adminLogin', content=many_fields,
                         headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 400)
        self.assertEqual(self.client.post('/adminLogin', content=b'x' * (16 * 1024 + 1),
                         headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 413)

    def test_stale_versions_cannot_bypass_new_requirements(self):
        payload = self.form(False)
        with self.sessions() as db:
            version = FormVersion(form_id=payload['form_id'], version_num=2, display_name='New', definition={'fields': [
                {'name': 'consent', 'type': 'checkbox', 'question': 'Consent', 'required': True}]})
            db.add(version)
            db.flush()
            db.get(FormInfo, payload['form_id']).cur_version_id = version.id
            db.commit()
        self.assertEqual(self.client.post('/api/forms/submit', json=payload).status_code, 409)
        self.assertEqual(self.upload(payload).status_code, 409)
        self.assertFalse(self.upload_dir.exists())

    def test_safe_markup_survives_and_scripts_do_not(self):
        value = '''<h2 class="text-xl text-[#123456]">Title</h2><p>Text <a href="/documents" target="_blank">link</a></p>
        <svg viewBox="0 0 24 24" class="w-6" onload="alert(1)"><path d="M0 0h10" stroke="currentColor"/><script>alert(1)</script><foreignObject><img onerror="alert(1)"></foreignObject></svg>
        <img src="/static/photo.png" onerror="alert(1)"><a href="jav&#x61;script:alert(1)">bad</a>
        <iframe srcdoc="bad"></iframe><style>body{display:none}</style>'''
        cleaned = clean_html(value)
        self.assertNotIn('alert(1)', cleaned)
        soup = BeautifulSoup(cleaned, 'html.parser')
        self.assertEqual(soup.h2['class'], ['text-xl', 'text-[#123456]'])
        self.assertIsNotNone(soup.select_one('svg path'))
        self.assertEqual(soup.select_one('a[href="/documents"]')['rel'], ['noopener', 'noreferrer'])
        self.assertIsNotNone(soup.select_one('img[src="/static/photo.png"]'))
        self.login('super')
        self.client.post('/admin/content/footer', data={'additional': value})
        for url in ('/', '/admin/content'):
            soup = BeautifulSoup(self.client.get(url).text, 'html.parser')
            footer = soup.select_one('.site-footer')
            self.assertFalse(footer.select('script, iframe, style, [onload], [onerror]'))

    def test_sysadmin_script_toggle_and_cancel(self):
        import make_sysadmin
        with patch('make_sysadmin.SessionLocal', self.sessions), patch('builtins.input', side_effect=['super', 'y']):
            make_sysadmin.main()
        with self.sessions() as db:
            self.assertTrue(db.query(AdminUser).filter_by(username='super').one().is_sysadmin)
        with patch('make_sysadmin.SessionLocal', self.sessions), patch('builtins.input', side_effect=['super', 'n']):
            make_sysadmin.main()
        with self.sessions() as db:
            self.assertTrue(db.query(AdminUser).filter_by(username='super').one().is_sysadmin)
        with patch('make_sysadmin.SessionLocal', self.sessions), patch('builtins.input', side_effect=['super', '']):
            make_sysadmin.main()
        with self.sessions() as db:
            self.assertFalse(db.query(AdminUser).filter_by(username='super').one().is_sysadmin)

    def test_migration_preserves_existing_accounts(self):
        spec = importlib.util.spec_from_file_location('security_migration', 'alembic/versions/d45f7b893201_admin_sessions_sysadmins.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE admin_users (id INTEGER PRIMARY KEY, username TEXT)'))
                connection.execute(text("INSERT INTO admin_users VALUES (1, 'existing')"))
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                row = connection.execute(text('SELECT username, is_sysadmin FROM admin_users')).one()
                self.assertEqual(tuple(row), ('existing', 0))
                with Operations.context(MigrationContext.configure(connection)):
                    migration.downgrade()
                self.assertEqual(connection.execute(text('SELECT username FROM admin_users')).scalar(), 'existing')
        finally:
            engine.dispose()
