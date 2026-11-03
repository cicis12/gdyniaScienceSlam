from uuid import uuid4
import unittest

from bs4 import BeautifulSoup

import test_site_content as content_tests
from models import InteractionLink, InteractionVisit, InteractionSection, SystemSetting
from interaction_analytics import ENABLED_KEY
from partnership_content import PartnershipConfig, ContactSection, get_partnership, save_partnership
from referral_access import ACCESS_COOKIE, CONSENT_COOKIE, SETTINGS_KEY, decode_cookie, get_popup


class ReferralAccessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client, self.sessions = self.fixture.client, self.fixture.sessions
        self.link_id = str(uuid4())
        with self.sessions() as db:
            db.add(InteractionLink(id=self.link_id, label='Invitation', path='/'))
            db.merge(SystemSetting(key=ENABLED_KEY, value='true'))
            save_partnership(db, PartnershipConfig(uuid_only=True, featured=True, sections=[ContactSection(id='contact', enabled=True)]))
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def choice(self, accepted, **kwargs):
        with self.sessions() as db:
            revision = get_popup(db).revision
        return self.client.post('/api/referrals/decision', json={'accepted': accepted, 'link_id': self.link_id, 'revision': revision}, **kwargs)

    def batch(self):
        return {'link_id': self.link_id, 'visit_id': str(uuid4()), 'path': '/become-a-partner',
                'samples': [{'section_id': 'page', 'visible_ms': 1000}]}

    def assert_no_analytics(self):
        with self.sessions() as db:
            self.assertEqual(db.query(InteractionVisit).count(), 0)
            self.assertEqual(db.query(InteractionSection).count(), 0)

    def test_valid_uuid_shows_popup_but_sends_no_analytics_before_consent(self):
        response = self.client.get('/become-a-partner?ref=' + self.link_id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('private, no-store', response.headers['cache-control'])
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertIsNotNone(soup.select_one('#referral-consent'))
        self.assertEqual(len(soup.select('[data-referral-choice]')), 2)
        self.assertIsNone(soup.select_one('script[src*="js/interaction-analytics.js"]'))
        self.assertNotIn(ACCESS_COOKIE, self.client.cookies)
        self.assertNotIn(CONSENT_COOKIE, self.client.cookies)
        self.assertEqual(self.client.post('/api/interactions', json=self.batch()).status_code, 403)
        self.assert_no_analytics()

    def test_no_keeps_only_signed_access_flag_and_clean_page_access(self):
        response = self.choice(False)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['tracking'])
        self.assertNotIn(CONSENT_COOKIE, self.client.cookies)
        access = decode_cookie(self.client.cookies.get(ACCESS_COOKIE), 'partner-access')
        self.assertEqual(set(access), {'access', 'purpose', 'exp'})
        self.assertTrue(access['access'])
        self.assertNotIn(self.link_id, str(access))
        self.assertIn('httponly', response.headers.get('set-cookie', '').lower())
        self.assertIn('secure', response.headers.get('set-cookie', '').lower())
        response = self.client.get('/become-a-partner')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('referral-session-config', response.text)
        self.assertNotIn('interaction-analytics-config', response.text)
        self.assertIn('partnership-home-feature', self.client.get('/').text)
        self.assertEqual(self.client.post('/api/interactions', json=self.batch()).status_code, 403)
        self.assert_no_analytics()

    def test_yes_remembers_consent_and_withdrawal_keeps_access(self):
        self.assertTrue(self.choice(True).json()['tracking'])
        consent = decode_cookie(self.client.cookies.get(CONSENT_COOKIE), 'tracking-consent')
        self.assertEqual(consent['link_id'], self.link_id)
        response = self.client.get('/become-a-partner')
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertIsNone(soup.select_one('#referral-consent'))
        self.assertIsNotNone(soup.select_one('script[src*="js/interaction-analytics.js"]'))
        self.assertEqual(self.client.post('/api/interactions', json=self.batch()).status_code, 204)
        # Footer withdrawal has no UUID in its request body.
        response = self.client.post('/api/referrals/decision', json={'accepted': False})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(CONSENT_COOKIE, self.client.cookies)
        self.assertIn(ACCESS_COOKIE, self.client.cookies)
        self.assertEqual(self.client.get('/become-a-partner').status_code, 200)
        self.assertEqual(self.client.post('/api/interactions', json=self.batch()).status_code, 403)

    def test_gate_hides_links_feature_and_contact_endpoint(self):
        self.assertEqual(self.client.get('/become-a-partner').status_code, 404)
        home = self.client.get('/').text
        self.assertNotIn('href="/become-a-partner"', home)
        self.assertNotIn('partnership-home-feature', home)
        self.assertEqual(self.client.post('/become-a-partner/contact/contact', json={}).status_code, 404)
        self.assertEqual(self.client.get('/become-a-partner?ref=' + str(uuid4())).status_code, 404)
        self.client.cookies.set(ACCESS_COOKIE, 'true')
        self.assertEqual(self.client.get('/become-a-partner').status_code, 404)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/referrals/decision', json={'accepted': False}).status_code, 403)
        self.assertNotIn(ACCESS_COOKIE, self.client.cookies)

    def test_restricted_mode_is_optional_and_global_visibility_wins(self):
        with self.sessions() as db:
            config = get_partnership(db)
            config.uuid_only = False
            save_partnership(db, config)
            db.commit()
        self.assertEqual(self.client.get('/become-a-partner').status_code, 200)
        self.choice(False)
        with self.sessions() as db:
            db.merge(SystemSetting(key='page_visible:become_partner', value='false'))
            db.commit()
        self.assertEqual(self.client.get('/become-a-partner').status_code, 404)
        self.assertEqual(self.client.get('/become-a-partner?ref=' + self.link_id).status_code, 404)

    def test_popup_configuration_sanitization_and_revision_invalidation(self):
        self.choice(True)
        self.fixture.login()
        response = self.client.post('/admin/analytics/referral-settings', data={
            'title': 'Invitation consent', 'content': '<strong>Choose freely</strong><script>alert(1)</script>',
            'accept_label': 'Allow statistics', 'reject_label': 'Continue without statistics'})
        self.assertEqual(response.status_code, 200)
        self.client.cookies.delete('admin_session')
        self.assertEqual(self.client.post('/api/interactions', json=self.batch()).status_code, 403)
        response = self.client.get('/about')
        self.assertIn('Invitation consent', response.text)
        self.assertIn('<strong>Choose freely</strong>', response.text)
        self.assertNotIn('alert(1)', response.text)
        self.assertIn('Continue without statistics', response.text)
        self.assert_no_analytics()

    def test_stale_popup_cannot_grant_consent_for_unseen_copy(self):
        response = self.client.post('/api/referrals/decision', json={'accepted': True, 'link_id': self.link_id, 'revision': '0' * 64})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(CONSENT_COOKIE, self.client.cookies)
        self.assert_no_analytics()

    def test_unknown_disabled_uuid_origin_and_privacy_preferences(self):
        for accepted in (False, True):
            self.assertEqual(self.client.post('/api/referrals/decision', json={'accepted': accepted, 'link_id': str(uuid4())}).status_code, 404)
        self.assertEqual(self.choice(True, headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.choice(True, headers={'DNT': '1'}).json()['consented'], False)
        self.assertNotIn(CONSENT_COOKIE, self.client.cookies)
        self.assertEqual(self.client.get('/become-a-partner').status_code, 200)
        self.client.cookies.clear()
        response = self.client.get('/about?ref=' + str(uuid4()))
        self.assertNotIn('referral-session-config', response.text)
        with self.sessions() as db:
            db.get(InteractionLink, self.link_id).active = False
            db.commit()
        self.assertEqual(self.choice(False).status_code, 404)
        self.assertEqual(self.client.get('/become-a-partner?ref=' + self.link_id).status_code, 404)

    def test_admin_preview_access_and_settings_permissions(self):
        self.fixture.login()
        self.assertEqual(self.client.get('/become-a-partner').status_code, 200)
        self.assertNotIn('referral-session-config', self.client.get('/about?ref=' + self.link_id).text)
        response = self.client.post('/admin/become-a-partner/preview', data={'config': PartnershipConfig(uuid_only=True).model_dump_json()})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('referral-session-config', response.text)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/admin/analytics/referral-settings', follow_redirects=False).status_code, 303)
        self.fixture.login('regular')
        self.assertEqual(self.client.post('/admin/analytics/referral-settings', follow_redirects=False).status_code, 403)
