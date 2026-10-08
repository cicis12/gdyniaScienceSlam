from pathlib import Path
from unittest.mock import patch
import unittest
from bs4 import BeautifulSoup

import test_site_content as content_tests
from about_content import get_timeline


class AboutTests(unittest.TestCase):
    login = content_tests.ContentTests.login
    photo = content_tests.ContentTests.photo
    tearDown = content_tests.ContentTests.tearDown

    def setUp(self):
        content_tests.ContentTests.setUp(self)
        item = patch('routers.about_admin.PHOTO_DIR', Path(self.temp.name))
        item.start()
        self.patches.append(item)

    def fields(self, **changes):
        return dict(label='2026', title='Nowy etap', description='Nasza historia', sort_order=0, **changes)

    def test_defaults_crud_reorder_and_escaping(self):
        self.assertEqual(len(BeautifulSoup(self.client.get('/about').text, 'html.parser').select('.timeline-stage')), 4)
        self.login()
        response = self.client.post('/admin/about/entries', data=self.fields(), files={'photo': self.photo()})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            entry = next(entry for entry in get_timeline(db) if entry.title == 'Nowy etap')
        fields = self.fields()
        fields.update(sort_order=100, description='<script>unsafe</script>\nNew description')
        self.assertEqual(self.client.post('/admin/about/entries/' + entry.id, data=fields).status_code, 200)
        with self.sessions() as db:
            edited = get_timeline(db)[-1]
            self.assertEqual(edited.id, entry.id)
            self.assertEqual(edited.photo, entry.photo)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', self.client.get('/about').text)
        self.assertEqual(self.client.post('/admin/about/entries/' + entry.id, data=fields, files={'photo': self.photo()}).status_code, 200)
        with self.sessions() as db:
            self.assertNotEqual(get_timeline(db)[-1].photo, entry.photo)
        self.assertEqual(self.client.post('/admin/about/entries/' + entry.id + '/delete').status_code, 200)
        self.assertNotIn('New description', self.client.get('/about').text)
        self.assertEqual(self.client.post('/admin/about/entries/missing/delete').status_code, 404)

    def test_invalid_image_and_fields_preserve_content(self):
        self.login()
        with self.sessions() as db:
            original = get_timeline(db)
        self.assertEqual(self.client.post('/admin/about/entries', data=self.fields(), files={'photo': ('bad.png', b'no', 'image/png')}).status_code, 422)
        fields = self.fields()
        fields['description'] = '   '
        self.assertEqual(self.client.post('/admin/about/entries', data=fields, files={'photo': self.photo()}).status_code, 422)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        with self.sessions() as db:
            self.assertEqual(get_timeline(db), original)

    def test_superadmin_required(self):
        for username, status in [(None, 303), ('regular', 403)]:
            if username:
                self.login(username)
            self.assertEqual(self.client.get('/admin/about', follow_redirects=False).status_code, 303)
            for path in ['/admin/about/entries', '/admin/about/entries/idea', '/admin/about/entries/idea/delete']:
                self.assertEqual(self.client.post(path, follow_redirects=False).status_code, status)

    def test_empty_timeline_persists(self):
        self.login()
        with self.sessions() as db:
            ids = [entry.id for entry in get_timeline(db)]
        for entry_id in ids:
            self.client.post('/admin/about/entries/' + entry_id + '/delete')
        with self.sessions() as db:
            self.assertEqual(get_timeline(db), [])
        self.assertIn('Nasza historia pojawi się', self.client.get('/about').text)
