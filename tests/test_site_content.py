import importlib.util
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from jose import jwt
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations

import main
from database import Base, get_db
from models import AdminUser, FormInfo, FormVersion, SystemSetting, TeamMember
from site_pages import PUBLIC_PAGES
from team_theme import DEFAULT_PALETTE, PALETTE_KEY, get_team_palette


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(type_, compiler, **kw):
    return 'JSON'


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.temp = TemporaryDirectory()
        self.patches = [patch('main.SessionLocal', self.sessions),
                        patch('routers.site_content.PHOTO_DIR', Path(self.temp.name))]
        for item in self.patches:
            item.start()
        def db_override():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = db_override
        self.client = TestClient(main.app, base_url='https://testserver')
        with self.sessions() as db:
            db.add_all([AdminUser(username='super', password_hash='unused', is_superadmin=True),
                        AdminUser(username='regular', password_hash='unused', is_superadmin=False),
                        TeamMember(name='Original Person', position='Leader', description='Original bio', photo='/static/original.webp')])
            db.commit()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()
        self.engine.dispose()

    def login(self, username='super'):
        self.client.cookies.set('admin_session', jwt.encode({'sub': username}, main.SECRET_KEY, algorithm=main.ALGORITHM))

    def photo(self):
        output = BytesIO()
        Image.new('RGB', (10, 10), 'red').save(output, 'PNG')
        return ('photo.png', output.getvalue(), 'image/png')

    def test_crud_upload_grid_and_homepage(self):
        self.login()
        response = self.client.post('/admin/content/team', data={
            'name': 'New Person', 'position': 'Designer', 'description': '<script>alert(1)</script>\nHello'
        }, files={'photo': self.photo()})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            member = db.query(TeamMember).filter_by(name='New Person').one()
            member_id, original_photo = member.id, member.photo
        self.assertEqual(len(list(Path(self.temp.name).glob('*.webp'))), 1)
        response = self.client.get('/team')
        self.assertEqual(response.text.count('<details class="team-card">'), 2)
        self.assertIn('&lt;script&gt;', response.text)
        self.assertIn('New Person', self.client.get('/').text)
        response = self.client.post(f'/admin/content/team/{member_id}', data={
            'name': 'Updated Person', 'position': 'Editor', 'description': 'Updated biography'
        })
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(TeamMember, member_id).photo, original_photo)
        self.assertIn('Updated biography', self.client.get('/team').text)
        self.assertEqual(self.client.post(f'/admin/content/team/{member_id}/delete').status_code, 200)
        self.assertNotIn('Updated Person', self.client.get('/team').text)

    def test_visibility_blocks_every_page_and_keeps_admin_access(self):
        self.login()
        self.assertEqual(self.client.post('/admin/content/pages').status_code, 200)
        for _, path, _ in PUBLIC_PAGES:
            for suffix in ['', '/'] if path != '/' else ['']:
                with self.subTest(path=path + suffix):
                    response = self.client.get(path + suffix)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn('href="/team"', response.text)
        for path in ['/vote/login', '/vote/submit', '/api/forms/submit']:
            self.assertEqual(self.client.post(path).status_code, 404)
        self.assertEqual(self.client.get('/forms/anything').status_code, 404)
        self.assertEqual(self.client.get('/admin/content').status_code, 200)
        self.client.post('/admin/content/pages', data={'visible': [key for key, _, _ in PUBLIC_PAGES]})
        self.assertEqual(self.client.get('/team').status_code, 200)
        self.assertIn('href="/team"', self.client.get('/').text)

    def test_navigation_and_home_team_preview_hide(self):
        self.login()
        self.client.post('/admin/content/pages', data={'visible': [key for key, _, _ in PUBLIC_PAGES if key != 'team']})
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('href="/team"', response.text)
        self.assertNotIn('Original Person', response.text)

    def test_permissions(self):
        for username, expected in [(None, 303), ('regular', 403)]:
            if username:
                self.login(username)
            for path in ['/admin/content/team', '/admin/content/team/1', '/admin/content/team/1/delete', '/admin/content/pages', '/admin/content/forms/1', '/admin/content/palette', '/admin/content/palette/reset', '/admin/content/team-settings']:
                self.assertEqual(self.client.post(path, follow_redirects=False).status_code, expected)
        with self.sessions() as db:
            self.assertEqual(db.query(TeamMember).count(), 1)
            self.assertEqual(db.query(SystemSetting).count(), 0)

    def test_team_details_can_be_disabled_without_losing_profiles(self):
        self.assertIn('id="team-profile"', self.client.get('/team').text)
        self.login()
        self.assertEqual(self.client.post('/admin/content/team-settings').status_code, 200)
        response = self.client.get('/team')
        self.assertIn('Original Person', response.text)
        self.assertIn('<article class="team-card">', response.text)
        self.assertNotIn('Original bio', response.text)
        self.assertNotIn('Poznaj mnie', response.text)
        self.assertNotIn('id="team-profile"', response.text)
        self.assertNotIn('team-profiles.js', response.text)
        with self.sessions() as db:
            self.assertEqual(db.query(TeamMember).one().description, 'Original bio')
        self.assertEqual(self.client.post('/admin/content/team-settings', data={'details_enabled': 'true'}).status_code, 200)
        response = self.client.get('/team')
        self.assertIn('Original bio', response.text)
        self.assertIn('id="team-profile"', response.text)

    def test_palette_persists_renders_and_resets(self):
        self.login()
        palette = {**DEFAULT_PALETTE, 'background': '#112233', 'card_1': '#ABCDEF'}
        response = self.client.post('/admin/content/palette', data=palette)
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="#abcdef"', response.text)
        with self.sessions() as db:
            self.assertEqual(get_team_palette(db)['background'], '#112233')
        self.client.cookies.clear()
        response = self.client.get('/team')
        self.assertIn('--team-background: #112233;', response.text)
        self.assertIn('--team-card-1: #abcdef;', response.text)
        self.login()
        self.assertEqual(self.client.post('/admin/content/palette/reset').status_code, 200)
        with self.sessions() as db:
            self.assertEqual(get_team_palette(db), DEFAULT_PALETTE)

    def test_palette_validation_is_atomic_and_bad_saved_values_fall_back(self):
        self.login()
        for value in ['red', '#123', '#123456; background:url(https://example.com)', '</style><script>alert(1)</script>']:
            response = self.client.post('/admin/content/palette', data={**DEFAULT_PALETTE, 'background': value})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post('/admin/content/palette', data={'background': '#112233'}).status_code, 422)
        with self.sessions() as db:
            self.assertIsNone(db.get(SystemSetting, PALETTE_KEY))
            db.add(SystemSetting(key=PALETTE_KEY, value='{"background": "not-a-color", "card_1": "#aabbcc"}'))
            db.commit()
            self.assertEqual(get_team_palette(db), {**DEFAULT_PALETTE, 'card_1': '#aabbcc'})

    def test_invalid_photos_and_blank_fields(self):
        self.login()
        data = {'name': 'Test', 'position': 'Test', 'description': 'Bio'}
        for photo in [('fake.png', b'\x89PNG\r\n\x1a\ninvalid', 'image/png'),
                      ('huge.jpg', b'x' * (5 * 1024 * 1024 + 1), 'image/jpeg')]:
            self.assertEqual(self.client.post('/admin/content/team', data=data, files={'photo': photo}).status_code, 422)
        self.assertEqual(self.client.post('/admin/content/team', data=data).status_code, 422)
        self.assertEqual(self.client.post('/admin/content/team', data={**data, 'name': '   '}, files={'photo': self.photo()}).status_code, 422)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(self.client.post('/admin/content/team/999/delete').status_code, 404)
        self.assertEqual(self.client.post('/admin/content/pages', data={'visible': ['unknown']}).status_code, 422)

    def test_form_visibility(self):
        self.login()
        with self.sessions() as db:
            form = FormInfo(slug='example', name='Example', enabled=True, cur_version_id=1)
            db.add(form)
            db.flush()
            form_id = form.id
            db.add(FormVersion(id=1, form_id=form_id, version_num=1, display_name='Example', definition={'fields': []}))
            db.commit()
        self.assertEqual(self.client.get('/forms/example').status_code, 200)
        self.assertEqual(self.client.post(f'/admin/content/forms/{form_id}').status_code, 200)
        self.assertEqual(self.client.get('/forms/example').status_code, 404)
        self.assertEqual(self.client.post('/api/forms/submit', json={'form_id': form_id, 'form_version_id': 1, 'answers': {}}).status_code, 404)
        self.client.post(f'/admin/content/forms/{form_id}', data={'enabled': 'true'})
        self.assertEqual(self.client.get('/forms/example').status_code, 200)

    def test_seed_migration(self):
        spec = importlib.util.spec_from_file_location('team_migration', 'alembic/versions/b81c92d43e10_add_team_members.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                with sessionmaker(bind=connection)() as db:
                    self.assertEqual(db.query(TeamMember).count(), 17)
                    for member in db.query(TeamMember):
                        self.assertTrue(Path(member.photo.lstrip('/')).is_file())
                migration.downgrade()
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
