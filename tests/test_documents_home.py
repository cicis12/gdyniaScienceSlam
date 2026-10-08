from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED
from hashlib import sha256
import json
import unittest

from bs4 import BeautifulSoup
from pypdf import PdfWriter

import test_site_content as content_tests
import test_gallery_transfer as transfer_tests
from document_content import get_documents, save_documents, document_path, Document, DOCUMENTS_KEY
from home_images import get_home_images, HomeImages, HomeImage, save_home_images
from models import SystemSetting
from system_settings import DEFAULT_HOME
from site_pages import PUBLIC_PAGES
from site_transfer import export_bundle, inspect_bundle, apply_bundle


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentsHomeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()
        self.documents_dir = Path(self.fixture.temp.name) / 'documents'
        self.photos_dir = Path(self.fixture.temp.name) / 'home'
        for target, value in (('document_content.DOCUMENTS_DIR', self.documents_dir), ('routers.site_content.HOME_PHOTO_DIR', self.photos_dir)):
            item = patch(target, value)
            item.start()
            self.fixture.patches.append(item)
        with self.sessions() as db:
            save_documents(db, [])
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def add_document(self):
        response = self.client.post('/admin/documents', data={'title': 'Uploaded document', 'year': '2027', 'enabled': 'true'},
                                    files={'pdf': ('test.pdf', pdf_bytes(), 'application/pdf')})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            return get_documents(db)[0]

    def test_document_upload_download_edit_replace_hide_delete(self):
        document = self.add_document()
        response = self.client.get('/documents')
        self.assertNotIn('document-hero', response.text)
        self.assertNotIn('hero.webp', response.text)
        self.assertIn('Edycja 2027', response.text)
        self.assertIn('Uploaded document', response.text)
        url = '/documents/download/' + document.id
        download = self.client.get(url)
        self.assertEqual(download.content, pdf_bytes())
        self.assertEqual(download.headers['content-type'], 'application/pdf')
        self.assertTrue(download.headers['content-disposition'].startswith('attachment'))
        self.assertEqual(self.client.get('/' + document.file).status_code, 404)
        self.client.post('/admin/documents/' + document.id, data={'title': 'Hidden document', 'year': '2026'})
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotIn('Hidden document', self.client.get('/documents').text)
        self.client.post('/admin/documents/' + document.id, data={'title': 'Updated document', 'year': '2028', 'enabled': 'true'},
                         files={'pdf': ('replacement.pdf', pdf_bytes(), 'application/pdf')})
        with self.sessions() as db:
            updated = get_documents(db)[0]
            self.assertNotEqual(updated.file, document.file)
            self.assertEqual(updated.filename, 'replacement.pdf')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post('/admin/documents/' + document.id + '/delete')
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.sessions() as db:
            self.assertEqual(get_documents(db), [])

    def test_invalid_uploads_and_rollback(self):
        for data in (b'not pdf', b'%PDF-1.7\nfake\n%%EOF'):
            self.assertEqual(self.client.post('/admin/documents', data={'title': 'Invalid'}, files={'pdf': ('bad.pdf', data)}).status_code, 422)
        self.assertFalse(self.documents_dir.exists())
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError):
                self.client.post('/admin/documents', data={'title': 'Invalid'}, files={'pdf': ('test.pdf', pdf_bytes())})
        self.assertEqual(list(self.documents_dir.iterdir()), [])
        with self.sessions() as db:
            self.assertEqual(get_documents(db), [])

    def test_defaults_page_visibility_and_permissions(self):
        with self.sessions() as db:
            db.delete(db.get(SystemSetting, DOCUMENTS_KEY))
            db.commit()
            defaults = get_documents(db)
        self.assertEqual(len(defaults), 6)
        for document in defaults:
            self.assertEqual(self.client.get('/documents/download/' + document.id).status_code, 200)
        self.client.post('/admin/content/pages', data={'visible': [key for key, _, _ in PUBLIC_PAGES if key != 'documents']})
        self.assertEqual(self.client.get('/documents/download/' + defaults[0].id).status_code, 404)
        self.assertEqual(self.client.get('/admin/documents').status_code, 200)
        for username, expected in ((None, 303), ('regular', 403)):
            self.client.cookies.clear()
            if username:
                self.fixture.login(username)
            for path in ('/admin/documents', '/admin/documents/test', '/admin/documents/test/delete',
                         '/admin/content/home/images/hero', '/admin/content/home/images/hero/reset'):
                self.assertEqual(self.client.post(path, follow_redirects=False).status_code, expected)

    def test_home_image_upload_crop_alt_reset_and_copy_preserved(self):
        self.client.post('/admin/content/home', data=DEFAULT_HOME)
        for slot in ('hero', 'about', 'archive'):
            response = self.client.post('/admin/content/home/images/' + slot, data={'position': 'top', 'alt': '<script>Text</script>'},
                                        files={'photo': self.fixture.photo()})
            self.assertEqual(response.status_code, 200)
            with self.sessions() as db:
                image = getattr(get_home_images(db), slot)
                self.assertTrue((self.photos_dir / Path(image.photo).name).is_file())
                self.assertEqual(image.position, 'top')
            home = self.client.get('/').text
            self.assertIn(image.photo, home)
            self.assertIn('background-position: top' if slot == 'hero' else 'object-position: top', home)
            if slot != 'hero':
                self.assertIn('&lt;script&gt;Text&lt;/script&gt;', home)
            self.client.post('/admin/content/home/images/' + slot + '/reset')
            with self.sessions() as db:
                self.assertEqual(getattr(get_home_images(db), slot), getattr(HomeImages(), slot))
        self.assertIn('Nauka, która zostaje z Tobą.', self.client.get('/').text)
        self.assertEqual(self.client.post('/admin/content/home/images/unknown').status_code, 404)
        self.assertEqual(self.client.post('/admin/content/home/images/hero', data={'position': 'center;evil'}).status_code, 422)

    def test_home_image_invalid_data_and_failed_commit_are_atomic(self):
        self.assertEqual(self.client.post('/admin/content/home/images/hero', files={'photo': ('bad.png', b'fake')}).status_code, 422)
        self.assertFalse(self.photos_dir.exists())
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError):
                self.client.post('/admin/content/home/images/hero', files={'photo': self.fixture.photo()})
        self.assertEqual(list(self.photos_dir.iterdir()), [])
        with self.sessions() as db:
            self.assertEqual(get_home_images(db), HomeImages())


class DocumentsHomeTransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture = transfer_tests.GalleryTransferTests()
        self.fixture.setUp()
        self.sessions = self.fixture.sessions
        self.documents_dir = Path(self.fixture.temp.name) / 'documents'
        self.documents_dir.mkdir()
        item = patch('document_content.DOCUMENTS_DIR', self.documents_dir)
        item.start()
        self.fixture.patches.append(item)
        path = self.documents_dir / ('a' * 32 + '.pdf')
        path.write_bytes(pdf_bytes())
        self.document = Document(title='Portable document', filename='test.pdf', file='uploads/documents/' + path.name)
        with self.sessions() as db:
            save_documents(db, [self.document])
            images = get_home_images(db)
            images.hero.position = 'bottom'
            images.about.alt = 'Portable image'
            save_home_images(db, images)
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def test_roundtrip_gallery_scope_and_legacy_imports(self):
        with self.sessions() as db:
            data = export_bundle(db)
            bundle, media = inspect_bundle(data)
            self.assertEqual(bundle.version, 4)
            self.assertEqual(bundle.documents[0].title, 'Portable document')
            save_documents(db, [])
            images = get_home_images(db)
            images.hero.position = 'top'
            save_home_images(db, images)
            db.commit()
            apply_bundle(db, bundle, media, 'gallery')
            self.assertEqual(get_documents(db), [])
            self.assertEqual(get_home_images(db).hero.position, 'top')
            apply_bundle(db, bundle, media, 'all')
            actual_documents = get_documents(db)
            actual_images = get_home_images(db)
            self.assertEqual(document_path(actual_documents[0]).read_bytes(), pdf_bytes())
            self.assertEqual(actual_images.hero.position, 'bottom')
            self.assertEqual(actual_images.about.alt, 'Portable image')
            self.assertTrue((self.fixture.static_root / actual_images.hero.photo.removeprefix('/static/')).is_file())
            for version in (1, 2, 3):
                with ZipFile(BytesIO(data)) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist() if not name.startswith('documents/')}
                manifest = json.loads(entries['manifest.json'])
                manifest['version'] = version
                manifest.pop('documents')
                manifest.pop('home_images')
                if version < 3:
                    manifest.pop('partners')
                if version == 1:
                    manifest.pop('about')
                entries['manifest.json'] = json.dumps(manifest).encode()
                output = BytesIO()
                with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                    for name, payload in entries.items():
                        archive.writestr(name, payload)
                legacy, old_media = inspect_bundle(output.getvalue())
                apply_bundle(db, legacy, old_media, 'all')
                self.assertEqual(get_documents(db), actual_documents)
                self.assertEqual(get_home_images(db), actual_images)

    def test_missing_and_invalid_pdf_archives_are_rejected(self):
        with self.sessions() as db:
            data = export_bundle(db)
        with ZipFile(BytesIO(data)) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        document_name = next(name for name in original if name.startswith('documents/'))
        for missing in (True, False):
            entries = original.copy()
            entries.pop(document_name)
            if not missing:
                fake = b'%PDF-1.7\nfake\n%%EOF'
                name = 'documents/' + sha256(fake).hexdigest() + '.pdf'
                entries[name] = fake
                manifest = json.loads(entries['manifest.json'])
                manifest['documents'][0]['file'] = name
                entries['manifest.json'] = json.dumps(manifest).encode()
            output = BytesIO()
            with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                for name, payload in entries.items():
                    archive.writestr(name, payload)
            with self.assertRaises(ValueError):
                inspect_bundle(output.getvalue())

    def test_import_failure_cleans_new_documents(self):
        with self.sessions() as db:
            bundle, media = inspect_bundle(export_bundle(db))
            files = set(self.documents_dir.iterdir())
            with patch.object(db, 'commit', side_effect=RuntimeError('rollback')):
                with self.assertRaises(RuntimeError):
                    apply_bundle(db, bundle, media, 'all')
            self.assertEqual(set(self.documents_dir.iterdir()), files)

