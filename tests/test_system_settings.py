import json
import unittest
from bs4 import BeautifulSoup

import test_site_content as content_tests
from models import SystemSetting
from site_pages import PUBLIC_PAGES
from system_settings import DEFAULT_THEME, DEFAULT_HOME, THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY, DEFAULT_PAGE_MODES


class SystemSettingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()

    def tearDown(self):
        self.fixture.tearDown()

    def test_navigation_and_separate_editors(self):
        for path in ('/admin/content', '/admin/forms', '/admin/content/home', '/admin/content/team',
                     '/admin/content/partners/placeholder', '/admin/content/documents/placeholder'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            nav = BeautifulSoup(response.text, 'html.parser').select_one('.site-nav')
            self.assertIn('Ustawienia systemowe', nav.get_text())
            self.assertIn('Formularze', nav.get_text())
            self.assertNotIn('Panel główny', nav.get_text())
            self.assertNotIn('Wyślij Maile', nav.get_text())
            self.assertFalse(nav.select('a[href="/registration"]'))
        dashboard = self.client.get('/admin/dashboard').text
        self.assertNotIn('Zespół, galeria i konfiguracja strony', dashboard)
        votes = self.client.get('/admin/manage_votes')
        self.assertEqual(votes.status_code, 200)
        self.assertNotIn('Data wydarzenia', votes.text)
        self.assertIn('Data wydarzenia', self.client.get('/admin/content').text)

    def test_date_saves_and_redirects_to_system_settings(self):
        response = self.client.post('/admin/event-settings', data={'event_datetime': '2027-03-21T12:30'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/admin/content?saved=1#event')
        self.assertIn('2027-03-21T12:30', self.client.get('/').text)
        self.assertEqual(self.client.post('/admin/event-settings', data={'event_datetime': 'invalid'}).status_code, 400)

    def test_every_homepage_destination_respects_visibility(self):
        for key, path, _ in PUBLIC_PAGES:
            if key == 'home':
                continue
            self.client.post('/admin/content/pages', data={'visible': [name for name, _, _ in PUBLIC_PAGES if name != key]})
            soup = BeautifulSoup(self.client.get('/').text, 'html.parser')
            links = [link['href'].split('#')[0] for link in soup.select('a[href]')]
            self.assertNotIn(path, links)

    def test_theme_validates_atomically_renders_and_resets(self):
        palette = {**DEFAULT_THEME, 'dark_background': '#123456', 'header_logo': '#ABCDEF'}
        self.assertEqual(self.client.post('/admin/content/theme', data=palette).status_code, 200)
        for path in ('/', '/team', '/about', '/previous_editions', '/topics', '/partners', '/documents', '/registration', '/vote'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('--theme-dark-background: #123456;', response.text)
            self.assertIn('--theme-header-logo: #abcdef;', response.text)
        self.assertEqual(self.client.post('/admin/content/theme', data={**palette, 'light_text': 'red;evil'}).status_code, 422)
        self.assertEqual(self.client.post('/admin/content/theme', data={'dark_background': '#123456'}).status_code, 422)
        with self.sessions() as db:
            self.assertEqual(json.loads(db.get(SystemSetting, THEME_KEY).value)['dark_background'], '#123456')
        self.client.post('/admin/content/theme/reset')
        with self.sessions() as db:
            self.assertIsNone(db.get(SystemSetting, THEME_KEY))

    def test_footer_markup_and_home_text(self):
        self.client.post('/admin/content/footer', data={
            'email': '<a href="mailto:contact@example.com">Contact</a>',
            'location': '<strong>Gdynia</strong><script>alert(1)</script>',
            'additional': '<a href="javascript:alert(1)" onclick="alert(2)">More</a><img src=x onerror=alert(3)>',
        })
        soup = BeautifulSoup(self.client.get('/').text, 'html.parser')
        footer = soup.select_one('.site-footer')
        self.assertTrue(footer.select_one('a[href="mailto:contact@example.com"]'))
        self.assertTrue(footer.select_one('strong'))
        self.assertFalse(footer.select('script, img, [onclick], [onerror], a[href^="javascript:"]'))
        self.client.post('/admin/content/home', data={**DEFAULT_HOME, 'hero_title': '<script>Custom heading</script>', 'archive_description': 'New archive copy'})
        home = self.client.get('/').text
        self.assertIn('&lt;script&gt;Custom heading&lt;/script&gt;', home)
        self.assertIn('New archive copy', home)
        self.assertIn('New archive copy', self.client.get('/admin/content/home').text)

    def test_new_settings_are_superadmin_only_and_preview_does_not_save(self):
        with self.sessions() as db:
            count = db.query(SystemSetting).count()
        self.assertEqual(self.client.get('/admin/content/preview').status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(SystemSetting).count(), count)
        for username, expected in (('regular', 403), (None, 303)):
            self.client.cookies.clear()
            if username:
                self.fixture.login(username)
            for path in ('/admin/content/theme', '/admin/content/theme/reset', '/admin/content/footer', '/admin/content/home', '/admin/content/page-modes', '/admin/content/page-mode/team'):
                self.assertEqual(self.client.post(path, follow_redirects=False).status_code, expected)
            response = self.client.get('/admin/content/preview', follow_redirects=False)
            self.assertEqual(response.status_code, 303)

    def test_page_modes_save_independently_and_validate(self):
        response = self.client.post('/admin/content/page-mode/team', data={'mode': 'light'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/admin/content/team?saved=1')
        soup = BeautifulSoup(self.client.get('/team').text, 'html.parser')
        self.assertEqual(soup.body['data-display-mode'], 'light')
        self.assertEqual(soup.body['data-display-page'], 'team')
        self.assertEqual(BeautifulSoup(self.client.get('/about').text, 'html.parser').body['data-display-mode'], 'default')
        for path, mode in (('/admin/content/page-mode/team', 'invalid'), ('/admin/content/page-mode/unknown', 'light'), ('/admin/content/page-mode/home', 'dark')):
            self.assertEqual(self.client.post(path, data={'mode': mode}).status_code, 422)
        with self.sessions() as db:
            self.assertEqual(json.loads(db.get(SystemSetting, PAGE_MODES_KEY).value), {**DEFAULT_PAGE_MODES, 'team': 'light'})
        self.assertEqual(self.client.post('/admin/content/page-modes', data={**DEFAULT_PAGE_MODES, 'about': 'invalid'}).status_code, 422)
        self.assertEqual(self.client.post('/admin/content/page-modes', data={'about': 'dark'}).status_code, 422)
        modes = {key: 'dark' for key in DEFAULT_PAGE_MODES}
        self.assertEqual(self.client.post('/admin/content/page-modes', data=modes).status_code, 200)
        for key, path, _ in PUBLIC_PAGES:
            body = BeautifulSoup(self.client.get(path).text, 'html.parser').body
            self.assertEqual(body['data-display-mode'], 'default' if key == 'home' else 'dark')
            self.assertEqual(body['data-display-page'], key)
        self.assertNotIn('display-mode-home', self.client.get('/admin/content').text)
        self.assertNotIn('page-mode/home', self.client.get('/admin/content/home').text)
        self.client.post('/admin/content/page-mode/team', data={'mode': 'default'})
        self.assertEqual(BeautifulSoup(self.client.get('/team').text, 'html.parser').body['data-display-mode'], 'default')

    def test_preview_works_when_homepage_hidden(self):
        self.client.post('/admin/content/pages')
        self.assertEqual(self.client.get('/').status_code, 404)
        response = self.client.get('/admin/content/preview')
        self.assertEqual(response.status_code, 200)
        self.assertIn('countdown-hero', response.text)


if __name__ == '__main__':
    unittest.main()
