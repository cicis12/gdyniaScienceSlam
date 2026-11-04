import csv
from io import BytesIO, StringIO
from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from bs4 import BeautifulSoup

import test_form_fixes as form_tests
from models import FormInfo, FormSubmission, FormVersion


class FormAnswersExportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = form_tests.FormFixTests()
        self.fixture.setUp()
        self.client, self.sessions = self.fixture.client, self.fixture.sessions
        self.upload_dir = Path(self.fixture.fixture.temp.name) / 'uploads'
        self.upload_dir.mkdir()
        self.upload_patch = patch('form_uploads.UPLOAD_DIR', self.upload_dir)
        self.upload_patch.start()

    def tearDown(self):
        self.upload_patch.stop()
        self.fixture.tearDown()

    def test_all_answers_original_order_attachments_and_temporary_cleanup(self):
        form = self.fixture.create([
            {'name': 'z_first', 'type': 'text', 'question': '<strong>Pierwsze pytanie</strong>'},
            {'name': 'file1', 'type': 'file', 'question': 'Pierwszy plik'},
            {'name': 'file2', 'type': 'file', 'question': 'Drugi plik'},
            {'name': 'a_last', 'type': 'text', 'question': 'Ostatnie pytanie'},
        ])
        another = self.fixture.create([], slug='other')
        records = []
        for index in range(2):
            stored_name = str(index) * 32 + '.pdf'
            (self.upload_dir / stored_name).write_bytes(b'%PDF-' + bytes([index]))
            records.append({'kind': 'attachment', 'stored_name': stored_name,
                            'filename': '../../oferta.pdf', 'media_type': 'application/pdf', 'size': 6})
        with self.sessions() as db:
            for index in range(51):
                db.add(FormSubmission(form_id=form['form_id'], form_version_id=form['version_id'],
                                      data={'z_first': f'Answer {index}'}))
            detailed = FormSubmission(form_id=form['form_id'], form_version_id=form['version_id'], data={
                'a_last': '=SUM(1,2)', 'file2': records[1], 'z_first': 'Zażółć\nLine; two', 'file1': records[0]})
            db.add(detailed)
            db.flush()
            submission_id = detailed.id
            version = FormVersion(form_id=form['form_id'], version_num=2, display_name='New',
                                  definition={'fields': [
                                      {'name': 'a_last', 'type': 'text', 'question': 'Now first'},
                                      {'name': 'z_first', 'type': 'text', 'question': 'Now last'}]})
            db.add(version)
            db.flush()
            db.get(FormInfo, form['form_id']).cur_version_id = version.id
            db.add(FormSubmission(form_id=form['form_id'], form_version_id=version.id,
                                  data={'z_first': 'New text', 'a_last': 'New first'}))
            db.add(FormSubmission(form_id=another['form_id'], form_version_id=another['version_id'],
                                  data={'secret': 'OTHER FORM PRIVATE ANSWER'}))
            db.commit()
        export_dir = Path(self.fixture.fixture.temp.name) / 'export'
        export_dir.mkdir()
        self.fixture.fixture.login('regular')
        url = f"/admin/form-submissions/{form['form_id']}/export"
        with patch('form_answers_export.tempfile.mkdtemp', return_value=str(export_dir)):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertFalse(export_dir.exists())
        self.assertEqual(response.headers['content-type'], 'application/zip')
        self.assertIn('attachment;', response.headers['content-disposition'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertIn('attachments/', archive.namelist())
            text = archive.read('answers.txt').decode('utf-8')
            self.assertIn('Liczba zgłoszeń: 53', text)
            self.assertIn('=SUM(1,2)', text)
            self.assertNotIn('OTHER FORM PRIVATE ANSWER', text)
            self.assertNotIn('stored_name', text)
            rows = list(csv.DictReader(StringIO(archive.read('answers.csv').decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(len({row['Zgłoszenie'] for row in rows}), 53)
            detailed_rows = [row for row in rows if row['Zgłoszenie'] == str(submission_id)]
            self.assertEqual([row['Pole'] for row in detailed_rows], ['z_first', 'file1', 'file2', 'a_last'])
            self.assertEqual(detailed_rows[0]['Pytanie'], 'Pierwsze pytanie')
            self.assertEqual(detailed_rows[0]['Odpowiedź'], 'Zażółć\nLine; two')
            self.assertEqual(detailed_rows[-1]['Odpowiedź'], "'=SUM(1,2)")
            self.assertEqual([row['Pytanie'] for row in rows[:2]], ['Now first', 'Now last'])
            files = [row['Załącznik'] for row in detailed_rows if row['Załącznik']]
            self.assertEqual(len(set(files)), 2)
            self.assertEqual([archive.read(name) for name in files], [b'%PDF-\x00', b'%PDF-\x01'])
            self.assertTrue(all('..' not in Path(name).parts and not name.startswith('/') for name in archive.namelist()))
        soup = BeautifulSoup(self.client.get(f"/admin/form-submissions?form_id={form['form_id']}").text, 'html.parser')
        self.assertIsNotNone(soup.select_one(f'a[href="{url}"]'))

    def test_missing_and_unsafe_attachments_are_reported_and_access_is_authenticated(self):
        form = self.fixture.create([
            {'name': 'file', 'type': 'file', 'question': 'Attachment'},
        ])
        with self.sessions() as db:
            for stored_name in ('0' * 32 + '.pdf', '../private.pdf'):
                db.add(FormSubmission(form_id=form['form_id'], form_version_id=form['version_id'], data={
                    'file': {'kind': 'attachment', 'filename': 'missing.pdf', 'stored_name': stored_name}}))
            db.commit()
        url = f"/admin/form-submissions/{form['form_id']}/export"
        self.client.cookies.clear()
        self.assertEqual(self.client.get(url, follow_redirects=False).status_code, 303)
        self.fixture.fixture.login('regular')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(archive.namelist(), ['attachments/', 'answers.csv', 'answers.txt'])
            self.assertEqual(archive.read('answers.txt').decode('utf-8').count('missing.pdf (brak pliku)'), 2)
            self.assertNotIn('../private.pdf', archive.read('answers.txt').decode('utf-8'))
        self.assertEqual(self.client.get('/admin/form-submissions/999999/export').status_code, 404)

    def test_empty_form_export_and_failed_generation_cleanup(self):
        form = self.fixture.create([])
        url = f"/admin/form-submissions/{form['form_id']}/export"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertIn('Liczba zgłoszeń: 0', archive.read('answers.txt').decode('utf-8'))
        export_dir = Path(self.fixture.fixture.temp.name) / 'failed-export'
        export_dir.mkdir()
        with patch('form_answers_export.tempfile.mkdtemp', return_value=str(export_dir)), \
                patch('form_answers_export.ZipFile', side_effect=OSError('Disk failure')):
            with self.assertRaises(OSError):
                self.client.get(url)
        self.assertFalse(export_dir.exists())
