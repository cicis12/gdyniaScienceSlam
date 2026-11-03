from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import test_site_content as content_tests
from interaction_analytics import ENABLED_KEY, prune
from models import InteractionLink, InteractionVisit, InteractionSection, SystemSetting
from site_pages import PUBLIC_PAGES


class InteractionAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()
        self.link_id, self.visit_id = str(uuid4()), str(uuid4())
        with self.sessions() as db:
            db.add(InteractionLink(id=self.link_id, label='Campaign A', path='/become-a-partner'))
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def enable(self):
        self.assertEqual(self.client.post('/admin/analytics/settings', data={'enabled': 'true'}).status_code, 200)
        self.consent()

    def consent(self):
        from referral_access import get_popup
        with self.sessions() as db:
            revision = get_popup(db).revision
        self.assertEqual(self.client.post('/api/referrals/decision', json={'accepted': True, 'link_id': self.link_id, 'revision': revision}).status_code, 200)

    def batch(self, milliseconds=5000, **overrides):
        return {'link_id': self.link_id, 'visit_id': self.visit_id, 'path': '/become-a-partner',
                'samples': [{'section_id': 'page', 'visible_ms': milliseconds, 'clicks': 1, 'faq_opens': 0},
                            {'section_id': 'section-faq', 'visible_ms': milliseconds, 'clicks': 2, 'faq_opens': 1}], **overrides}

    def post(self, batch=None, **kwargs):
        return self.client.post('/api/interactions', json=batch or self.batch(), **kwargs)

    def test_disabled_by_default_and_public_layout_coverage(self):
        self.assertEqual(self.post().status_code, 404)
        self.assertNotIn('js/interaction-analytics.js', self.client.get('/become-a-partner').text)
        self.enable()
        # Admin sessions and all previews are deliberately excluded.
        self.assertNotIn('js/interaction-analytics.js', self.client.get('/become-a-partner').text)
        self.assertNotIn('js/interaction-analytics.js', self.client.get('/admin/content/preview').text)
        self.client.cookies.clear()
        self.consent()
        for _, path, _ in PUBLIC_PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('js/interaction-analytics.js', response.text)
                soup = BeautifulSoup(response.text, 'html.parser')
                self.assertEqual(soup.select_one('meta[name="referrer"]')['content'], 'same-origin')
        self.assertEqual(self.post().status_code, 204)
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionVisit).count(), 1)
        self.fixture.login()
        self.client.post('/admin/analytics/settings')
        self.assertEqual(self.post().status_code, 404)

    def test_cumulative_totals_duplicate_out_of_order_and_report(self):
        self.enable()
        for total in (5000, 5000, 2000, 8000):
            self.assertEqual(self.post(self.batch(total)).status_code, 204)
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionVisit).count(), 1)
            record = db.get(InteractionSection, (self.visit_id, 'section-faq'))
            self.assertEqual((record.visible_ms, record.clicks, record.faq_opens), (8000, 2, 1))
        response = self.client.get('/admin/analytics/' + self.link_id)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertIn('?ref=' + self.link_id, soup.select_one('input[readonly]')['value'])
        self.assertEqual(len(soup.select('tbody tr')), 2)
        self.assertIn('8.0', soup.text)
        self.assertIn('Campaign A', soup.text)
        other_visit = str(uuid4())
        self.assertEqual(self.post(self.batch(3000, visit_id=other_visit, path='/about')).status_code, 204)
        self.assertIn('/about', self.client.get('/admin/analytics/' + self.link_id).text)

    def test_invalid_fields_unknown_uuid_and_page_visibility(self):
        self.enable()
        for invalid in ({'link_id': 'not-a-uuid'}, {'path': '/admin/dashboard'}, {'path': '/about?email=private@example.com'},
                        {'samples': [{'section_id': '../secrets', 'visible_ms': 10}]},
                        {'samples': [{'section_id': 'page', 'visible_ms': -1}]},
                        {'samples': [{'section_id': 'page', 'visible_ms': True}]},
                        {'samples': [{'section_id': 'page', 'visible_ms': 10, 'input_value': 'private'}]},
                        {'email': 'private@example.com'}):
            self.assertEqual(self.post(self.batch(**invalid)).status_code, 422)
        duplicate = self.batch()
        duplicate['samples'].append(duplicate['samples'][0])
        self.assertEqual(self.post(duplicate).status_code, 422)
        self.assertEqual(self.post(self.batch(link_id=str(uuid4()))).status_code, 403)
        self.assertEqual(self.post(self.batch(path='/forms/missing')).status_code, 404)
        self.assertEqual(self.post(headers={'Origin': 'https://other-site.example'}).status_code, 403)
        self.client.post('/admin/content/pages', data={'visible': [key for key, _, _ in PUBLIC_PAGES if key != 'become_partner']})
        self.assertEqual(self.post().status_code, 404)

    def test_caps_privacy_signals_body_limit_and_counters(self):
        self.enable()
        for headers in ({'DNT': '1'}, {'Sec-GPC': '1'}):
            self.assertEqual(self.post(headers=headers).status_code, 204)
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionVisit).count(), 0)
        self.assertEqual(self.post(self.batch(86400000)).status_code, 204)
        with self.sessions() as db:
            self.assertLessEqual(db.get(InteractionSection, (self.visit_id, 'page')).visible_ms, 15001)
        self.assertEqual(self.client.post('/api/interactions', content=b'x' * 32769).status_code, 413)
        with patch('request_limits.form_rate_limiter.hit', return_value=False):
            self.assertEqual(self.post().status_code, 429)
        initial = self.batch(samples=[{'section_id': 'block-' + str(i), 'visible_ms': 10} for i in range(98)])
        self.assertEqual(self.post(initial).status_code, 204)
        self.assertEqual(self.post(self.batch(samples=[{'section_id': 'overflow', 'visible_ms': 10}])).status_code, 422)
        with self.sessions() as db:
            columns = set(InteractionVisit.__table__.columns.keys()) | set(InteractionSection.__table__.columns.keys())
            self.assertFalse(columns & {'ip', 'email', 'user_agent', 'referrer', 'content', 'url'})

    def test_create_disable_clear_delete_and_permissions(self):
        self.enable()
        response = self.client.post('/admin/analytics/links', data={'path': '/about', 'label': 'New campaign'})
        self.assertEqual(response.status_code, 200)
        url = BeautifulSoup(response.text, 'html.parser').select_one('input[readonly]')['value']
        new_id = url.split('?ref=')[1]
        self.assertEqual(len(new_id), 36)
        self.assertEqual(self.client.post('/admin/analytics/links', data={'path': '//evil.example', 'label': 'Bad'}).status_code, 422)
        self.assertEqual(self.post().status_code, 204)
        self.client.post('/admin/analytics/' + self.link_id + '/toggle')
        self.assertEqual(self.post().status_code, 404)
        self.client.post('/admin/analytics/' + self.link_id + '/toggle')
        self.assertEqual(self.post(self.batch(path='/about')).status_code, 409)
        self.client.post('/admin/analytics/' + self.link_id + '/clear')
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionVisit).count(), 0)
            self.assertEqual(db.query(InteractionSection).count(), 0)
            self.assertIsNotNone(db.get(InteractionLink, self.link_id))
        self.client.post('/admin/analytics/' + self.link_id + '/delete')
        with self.sessions() as db:
            self.assertIsNone(db.get(InteractionLink, self.link_id))
        for username, expected in ((None, 303), ('regular', 403)):
            self.client.cookies.clear()
            if username:
                self.fixture.login(username)
            for path in ('/settings', '/links', '/' + new_id + '/clear', '/' + new_id + '/toggle', '/' + new_id + '/delete'):
                self.assertEqual(self.client.post('/admin/analytics' + path, follow_redirects=False).status_code, expected)
            self.assertEqual(self.client.get('/admin/analytics', follow_redirects=False).status_code, 303)

    def test_retention_prunes_sections_and_visits(self):
        self.enable()
        self.assertEqual(self.post().status_code, 204)
        with self.sessions() as db:
            db.get(InteractionVisit, self.visit_id).created_at = datetime.utcnow() - timedelta(days=91)
            db.commit()
        self.assertEqual(self.client.get('/admin/analytics').status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionSection).count(), 0)
            self.assertEqual(db.query(InteractionVisit).count(), 0)
            self.assertIsNotNone(db.get(InteractionLink, self.link_id))
        self.assertEqual(self.post().status_code, 204)

    def test_migration_upgrade_and_downgrade(self):
        spec = importlib.util.spec_from_file_location('analytics_migration', 'alembic/versions/e62f9d128a43_add_interaction_analytics.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                self.assertEqual(set(inspect(connection).get_table_names()), {'interaction_links', 'interaction_visits', 'interaction_sections'})
                migration.downgrade()
                self.assertEqual(inspect(connection).get_table_names(), [])
        engine.dispose()


class AnalyticsTransferExclusionTests(unittest.TestCase):
    def test_configuration_transfer_preserves_private_analytics(self):
        import test_gallery_transfer as transfer_tests
        from site_transfer import export_bundle, inspect_bundle, apply_bundle
        fixture = transfer_tests.GalleryTransferTests()
        fixture.setUp()
        try:
            link_id, visit_id = str(uuid4()), str(uuid4())
            with fixture.sessions() as db:
                db.add(InteractionLink(id=link_id, label='Private label', path='/'))
                db.flush()
                db.add(InteractionVisit(id=visit_id, link_id=link_id, path='/'))
                db.flush()
                db.add(InteractionSection(visit_id=visit_id, section_id='page', visible_ms=3000, clicks=0, faq_opens=0))
                db.merge(SystemSetting(key=ENABLED_KEY, value='true'))
                db.commit()
                bundle, media = inspect_bundle(export_bundle(db))
                self.assertNotIn(link_id, bundle.model_dump_json())
                self.assertNotIn(ENABLED_KEY, bundle.settings)
                apply_bundle(db, bundle, media, 'all')
                self.assertIsNotNone(db.get(InteractionLink, link_id))
                self.assertEqual(db.get(InteractionSection, (visit_id, 'page')).visible_ms, 3000)
                self.assertEqual(db.get(SystemSetting, ENABLED_KEY).value, 'true')
        finally:
            fixture.tearDown()
