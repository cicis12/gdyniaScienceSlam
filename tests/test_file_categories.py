import json
from pathlib import Path
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from pydantic import ValidationError
from forms import FormField
from models import SystemSetting
from site_transfer import FormRecord
import test_site_content

SVG = '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'

class FileCategoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_site_content.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.fixture.login()
        self.patch = patch('form_uploads.UPLOAD_DIR', Path(self.fixture.temp.name) / 'files')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.fixture.tearDown()

    def create(self, name, types):
        field = {'name': 'attachment', 'type': 'file', 'question': 'Załącznik', 'required': True, 'accepted_types': types}
        response = self.client.post('/admin/forms/create', json={
            'name': name, 'slug': name, 'display_name': name, 'svg': SVG, 'fields': [field]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), field

    def upload(self, record, filename, content):
        return self.client.post('/api/forms/submit', data={'payload': json.dumps({
            'form_id': record['form_id'], 'form_version_id': record['version_id'], 'answers': {}})},
            files={'file:attachment': (filename, content, 'application/octet-stream')})

    def test_categories_enforced_and_archives_download_without_extraction(self):
        record, field = self.create('archives', ['archives'])
        for name, body in [('file.zip', b'PK\x05\x06' + b'\0' * 18), ('file.rar', b'Rar!\x1a\x07\x01\0test'), ('file.7z', b'7z\xbc\xaf\x27\x1ctest')]:
            response = self.upload(record, name, body)
            self.assertEqual(response.status_code, 200, response.text)
            download = self.client.get(f"/admin/uploads/{response.json()['submission_id']}/attachment")
            self.assertEqual(download.content, body)
            self.assertIn('attachment', download.headers['content-disposition'])
        for name, body in [('film.mp4', b'\0\0\0\x18ftypmp42'), ('fake.zip', b'not a zip')]:
            response = self.upload(record, name, body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['code'], 'invalid_answers')
        restored = FormRecord(slug='test', name='Test', display_name='Test', enabled=True, definition={'fields': [field]})
        self.assertEqual(restored.definition.fields[0].accepted_types, ['archives'])

    def test_editor_roundtrip_accept_attribute_and_single_file_note(self):
        record, _ = self.create('images', ['images'])
        version = self.client.get(f"/admin/forms/{record['form_id']}/version/{record['version_id']}").json()
        self.assertEqual(version['fields'][0]['accepted_types'], ['images'])
        soup = BeautifulSoup(self.client.get('/forms/images').text, 'html.parser')
        control = soup.select_one('input[type=file]')
        self.assertIn('.png', control['accept'])
        self.assertNotIn('.zip', control['accept'])
        self.assertNotIn('.mp4', control['accept'])
        self.assertNotIn('multiple', control.attrs)
        self.assertIn('tylko jeden plik', soup.select_one('.form-note').text)
        self.assertEqual(self.upload(record, 'photo.png', b'\x89PNG\r\n\x1a\nimage').status_code, 200)
        self.assertEqual(self.upload(record, 'document.pdf', b'%PDF-1.7').status_code, 422)

    def test_form_icon_only_in_selector(self):
        first, _ = self.create('first', ['videos'])
        second, _ = self.create('second', ['documents'])
        with self.fixture.sessions() as db:
            db.merge(SystemSetting(key='registration_form_ids', value=f"{first['form_id']},{second['form_id']}"))
            db.commit()
        soup = BeautifulSoup(self.client.get('/registration').text, 'html.parser')
        self.assertEqual(len(soup.select('.registration-form-tabs .form-tab-icon svg')), 2)
        self.assertFalse(soup.select('form .form-icon'))
        self.assertFalse(BeautifulSoup(self.client.get('/forms/first').text, 'html.parser').select('.form-icon'))

    def test_unknown_or_empty_categories_rejected_and_legacy_default(self):
        base = {'name': 'file', 'question': 'File', 'type': 'file'}
        self.assertEqual(FormField(**base).accepted_types, ['videos', 'images', 'documents'])
        for choices in ([], ['executables']):
            with self.assertRaises(ValidationError):
                FormField(**base, accepted_types=choices)
