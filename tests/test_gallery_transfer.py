from io import BytesIO
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations

import unittest
import test_site_content as content_tests
from models import FormInfo, FormVersion, FormSubmission, GalleryPhoto, TeamMember, SystemSetting, AdminUser
from gallery import FeaturedVideo, get_featured_video
from site_transfer import export_bundle, inspect_bundle, apply_bundle
from image_uploads import normalize_image
from partner_content import PartnersConfig, save_partners
from document_content import save_documents
from home_images import HomeImages, HomeImage, save_home_images
from about_content import DEFAULT_ENTRIES, TimelineEntry, get_timeline, save_timeline


class GalleryTransferTests(unittest.TestCase):
    login = content_tests.ContentTests.login
    photo = content_tests.ContentTests.photo
    def setUp(self):
        content_tests.ContentTests.setUp(self)
        self.media_temp = TemporaryDirectory()
        self.static_root = Path(self.media_temp.name)
        self.gallery_dir = self.static_root / 'uploads/gallery'
        self.gallery_dir.mkdir(parents=True)
        self.image_path = self.gallery_dir / 'test.webp'
        self.image_path.write_bytes(normalize_image(self.photo()[1]))
        with self.sessions() as db:
            save_partners(db, PartnersConfig())
            save_documents(db, [])
            home_photo = HomeImage(photo='/static/uploads/gallery/test.webp')
            save_home_images(db, HomeImages(hero=home_photo, about=home_photo, archive=home_photo))
            save_timeline(db, [TimelineEntry(**{**entry, 'photo': '/static/uploads/gallery/test.webp'}) for entry in DEFAULT_ENTRIES])
            db.query(TeamMember).update({'photo': '/static/uploads/gallery/test.webp'})
            db.add(GalleryPhoto(year=2025, caption='Stage photo', sort_order=0, photo='/static/uploads/gallery/test.webp'))
            db.commit()
        for target, value in [
            ('routers.gallery_admin.PHOTO_DIR', self.gallery_dir),
            ('site_transfer.STATIC_DIR', self.static_root),
            ('site_transfer.IMPORT_DIR', self.static_root / 'uploads/imports'),
            ('routers.site_transfer.STAGING_DIR', self.static_root / 'private-preview'),
        ]:
            item = patch(target, value)
            item.start()
            self.patches.append(item)

    def tearDown(self):
        content_tests.ContentTests.tearDown(self)
        self.media_temp.cleanup()

    def bundle(self):
        with self.sessions() as db:
            return export_bundle(db)

    def test_gallery_upload_edit_delete_and_batch_rollback(self):
        self.login()
        response = self.client.post('/admin/gallery/photos', data={'year': '2026', 'caption': 'New shot'},
                                    files=[('photos', self.photo()), ('photos', self.photo())])
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            photos = db.query(GalleryPhoto).filter_by(year=2026).order_by(GalleryPhoto.sort_order).all()
            self.assertEqual([photo.sort_order for photo in photos], [0, 1])
            photo_id = photos[0].id
        self.assertIn('New shot', self.client.get('/previous_editions').text)
        self.assertEqual(self.client.post(f'/admin/gallery/photos/{photo_id}', data={'year': 2024, 'caption': '<script>no</script>', 'sort_order': 5}).status_code, 200)
        self.assertIn('&lt;script&gt;', self.client.get('/previous_editions').text)
        count_before = len(list(self.gallery_dir.iterdir()))
        response = self.client.post('/admin/gallery/photos', data={'year': 2026},
                                    files=[('photos', self.photo()), ('photos', ('bad.png', b'not an image', 'image/png'))])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(list(self.gallery_dir.iterdir())), count_before)
        with self.sessions() as db:
            self.assertEqual(db.query(GalleryPhoto).count(), 3)
        self.assertEqual(self.client.post(f'/admin/gallery/photos/{photo_id}/delete').status_code, 200)
        self.assertEqual(self.client.post('/admin/gallery/photos/999/delete').status_code, 404)

    def test_featured_video_validation_and_visibility(self):
        self.login()
        response = self.client.post('/admin/gallery/video', data={'enabled': 'true', 'url': 'https://youtu.be/dQw4w9WgXcQ', 'title': 'Highlights'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ', self.client.get('/previous_editions').text)
        for url in ['javascript:alert(1)', 'https://evil.example/watch?v=dQw4w9WgXcQ', 'https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ', 'https://www.youtube.com/watch?v=bad']:
            self.assertEqual(self.client.post('/admin/gallery/video', data={'enabled': 'true', 'url': url}).status_code, 422)
        self.assertEqual(FeaturedVideo(url='https://vimeo.com/123456789/abcdef').embed_url, 'https://player.vimeo.com/video/123456789?h=abcdef')
        self.client.post('/admin/gallery/video', data={'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertNotIn('<iframe', self.client.get('/previous_editions').text)

    def test_export_contains_media_and_no_private_data(self):
        with self.sessions() as db:
            db.add(SystemSetting(key='secret-test', value='must-not-export'))
            db.commit()
        data = self.bundle()
        config, media = inspect_bundle(data)
        self.assertEqual(len(config.gallery), 1)
        self.assertEqual(len(config.team), 1)
        self.assertEqual(config.version, 4)
        self.assertEqual(len(config.about), 4)
        self.assertEqual(len(media), 1)  # Deduplicated photo shared by gallery and team.
        with ZipFile(BytesIO(data)) as archive:
            manifest = archive.read('manifest.json').decode()
            self.assertNotIn('password_hash', manifest)
            self.assertNotIn('secret-test', manifest)
            self.assertNotIn('must-not-export', manifest)
            self.assertNotIn('submissions', manifest)

    def test_full_import_remaps_forms_and_preserves_submission_history(self):
        with self.sessions() as db:
            form = FormInfo(slug='apply', name='Apply', enabled=True, cur_version_id=100, id=100)
            db.add(form)
            db.add(FormVersion(id=100, form_id=100, version_num=1, display_name='New form', definition={'fields': []}))
            db.add(SystemSetting(key='registration_form_ids', value='100'))
            db.commit()
            data = export_bundle(db)
            db.query(SystemSetting).filter_by(key='registration_form_ids').delete()
            db.query(FormVersion).delete()
            db.query(FormInfo).delete()
            db.add(FormInfo(id=7, slug='apply', name='Apply', enabled=False, cur_version_id=7))
            db.add(FormVersion(id=7, form_id=7, version_num=1, display_name='Production form', definition={'fields': []}))
            db.add(FormSubmission(form_id=7, form_version_id=7, data={'answer': 'keep me'}))
            db.commit()
        config, media = inspect_bundle(data)
        with self.sessions() as db:
            apply_bundle(db, config, media, 'all')
            form = db.query(FormInfo).filter_by(slug='apply').one()
            self.assertEqual(form.id, 7)
            self.assertTrue(form.enabled)
            self.assertEqual(db.get(FormVersion, form.cur_version_id).display_name, 'New form')
            self.assertEqual(db.get(SystemSetting, 'registration_form_ids').value, '7')
            self.assertEqual(db.query(FormSubmission).one().data, {'answer': 'keep me'})
            self.assertIsNotNone(db.get(FormVersion, 7))
            self.assertEqual(db.query(AdminUser).count(), 2)
            photo = db.query(GalleryPhoto).one()
            self.assertTrue((self.static_root / photo.photo.removeprefix('/static/')).is_file())
            apply_bundle(db, config, media, 'all')
            self.assertEqual(db.query(FormVersion).count(), 2)  # No duplicate versions on re-import.
            reexported, _ = inspect_bundle(export_bundle(db))
            self.assertEqual(reexported.registration_forms, ['apply'])

    def test_gallery_only_preview_and_apply_preserves_other_config(self):
        data = self.bundle()
        with self.sessions() as db:
            db.query(TeamMember).update({'name': 'Production person'})
            db.query(GalleryPhoto).update({'caption': 'Production gallery'})
            db.add(SystemSetting(key='page_visible:team', value='false'))
            db.commit()
        self.login()
        response = self.client.post('/admin/transfer/preview', data={'scope': 'gallery'}, files={'bundle': ('config.zip', data, 'application/zip')})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(GalleryPhoto).one().caption, 'Production gallery')
        token = BeautifulSoup(response.text, 'html.parser').select_one('input[name=token]')['value']
        self.assertEqual(self.client.post('/admin/transfer/apply', data={'token': token}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(GalleryPhoto).one().caption, 'Stage photo')
            self.assertEqual(db.query(TeamMember).one().name, 'Production person')
            self.assertEqual(db.get(SystemSetting, 'page_visible:team').value, 'false')
        self.assertEqual(self.client.post('/admin/transfer/apply', data={'token': token}).status_code, 422)

    def test_import_preview_token_is_bound_to_admin(self):
        self.login()
        response = self.client.post('/admin/transfer/preview', files={'bundle': ('config.zip', self.bundle(), 'application/zip')})
        token = BeautifulSoup(response.text, 'html.parser').select_one('input[name=token]')['value']
        with self.sessions() as db:
            db.add(AdminUser(username='another-super', password_hash='unused', is_superadmin=True))
            db.commit()
        self.login('another-super')
        self.assertEqual(self.client.post('/admin/transfer/apply', data={'token': token}).status_code, 422)
        self.login()
        self.assertEqual(self.client.post('/admin/transfer/apply', data={'token': token}).status_code, 200)

    def test_import_failure_rolls_back_database_and_files(self):
        config, media = inspect_bundle(self.bundle())
        with self.sessions() as db:
            with patch.object(db, 'commit', side_effect=RuntimeError('Database failure')):
                with self.assertRaises(RuntimeError):
                    apply_bundle(db, config, media, 'all')
            self.assertEqual(db.query(GalleryPhoto).one().photo, '/static/uploads/gallery/test.webp')
            self.assertEqual(db.query(TeamMember).one().photo, '/static/uploads/gallery/test.webp')
            self.assertEqual(get_timeline(db)[0].photo, '/static/uploads/gallery/test.webp')
        self.assertEqual(list((self.static_root / 'uploads/imports').iterdir()), [])

    def test_timeline_roundtrip_and_gallery_scope(self):
        # A photo used only by the timeline must travel with the ZIP too.
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(image, 'PNG')
        (self.gallery_dir / 'about-only.webp').write_bytes(normalize_image(image.getvalue()))
        with self.sessions() as db:
            entries = get_timeline(db)
            entries[0].photo = '/static/uploads/gallery/about-only.webp'
            save_timeline(db, entries)
            db.commit()
        config, media = inspect_bundle(self.bundle())
        self.assertEqual(len(media), 2)
        with self.sessions() as db:
            entries = get_timeline(db)
            entries[0].description = 'Production history'
            save_timeline(db, entries)
            db.commit()
            apply_bundle(db, config, media, 'gallery')
            self.assertEqual(get_timeline(db)[0].description, 'Production history')
            apply_bundle(db, config, media, 'all')
            actual = get_timeline(db)
            self.assertEqual(actual[0].description, config.about[0].description)
            self.assertEqual([entry.id for entry in actual], [entry.id for entry in config.about])
            for entry in actual:
                self.assertTrue((self.static_root / entry.photo.removeprefix('/static/')).is_file())
            reexported, _ = inspect_bundle(export_bundle(db))
            self.assertEqual(reexported.about, config.about)

    def test_legacy_bundle_preserves_timeline_and_v2_requires_it(self):
        with ZipFile(BytesIO(self.bundle())) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        config = json.loads(files['manifest.json'])
        config.pop('about')
        def pack():
            output = BytesIO()
            with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, json.dumps(config) if name == 'manifest.json' else data)
            return output.getvalue()
        with self.assertRaises(ValueError):
            inspect_bundle(pack())
        config['version'] = 1
        config.pop('partners', None)
        config.pop('documents', None)
        config.pop('home_images', None)
        bundle, media = inspect_bundle(pack())
        with self.sessions() as db:
            original = get_timeline(db)
            apply_bundle(db, bundle, media, 'all')
            self.assertEqual(get_timeline(db), original)

    def test_malicious_or_incomplete_archives_are_rejected(self):
        valid = self.bundle()
        with ZipFile(BytesIO(valid)) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for change in ['traversal', 'missing-image', 'bad-version', 'bad-color', 'bad-video', 'bad-hash']:
            entries = dict(original)
            config = json.loads(entries['manifest.json'])
            if change == 'traversal': entries['../../escape'] = b'no'
            if change == 'missing-image': entries.pop(next(name for name in entries if name.startswith('media/')))
            if change == 'bad-version': config['version'] = 999
            if change == 'bad-color': config['settings']['team_palette'] = '{"background":"red;evil"}'
            if change == 'bad-video': config['video']['url'] = 'https://evil.example/video'
            if change == 'bad-hash': entries[next(name for name in entries if name.startswith('media/'))] = self.photo()[1]
            entries['manifest.json'] = json.dumps(config).encode()
            output = BytesIO()
            with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                for name, contents in entries.items(): archive.writestr(name, contents)
            with self.subTest(change=change), self.assertRaises(ValueError): inspect_bundle(output.getvalue())
        with self.assertRaises(ValueError): inspect_bundle(b'not a zip')

    def test_gallery_and_transfer_superadmin_permissions(self):
        for username, expected in [(None, 303), ('regular', 403)]:
            if username: self.login(username)
            for path in ['/admin/gallery/photos', '/admin/gallery/photos/1/delete', '/admin/gallery/video', '/admin/transfer/preview', '/admin/transfer/apply']:
                self.assertEqual(self.client.post(path, follow_redirects=False).status_code, expected)
        self.assertEqual(self.client.get('/admin/transfer/export', follow_redirects=False).status_code, 303)

    def test_shared_settings_transfer_and_older_packages(self):
        from system_settings import DEFAULT_THEME, DEFAULT_HOME, THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY, DEFAULT_PAGE_MODES
        from site_transfer import SiteBundle
        theme = {**DEFAULT_THEME, 'light_background': '#abcdef'}
        home = {**DEFAULT_HOME, 'hero_title': 'Transfer title'}
        footer = {'email': '<a href="mailto:hello@example.com">Hello</a>', 'location': 'Gdynia', 'additional': '<strong>Footer</strong>'}
        with self.sessions() as db:
            for key, value in ((THEME_KEY, theme), (HOME_KEY, home), (FOOTER_KEY, footer), (PAGE_MODES_KEY, {**DEFAULT_PAGE_MODES, 'team': 'light'})):
                db.merge(SystemSetting(key=key, value=json.dumps(value)))
            db.commit()
            bundle, media = inspect_bundle(export_bundle(db))
            db.get(SystemSetting, HOME_KEY).value = json.dumps(DEFAULT_HOME)
            db.get(SystemSetting, PAGE_MODES_KEY).value = json.dumps(DEFAULT_PAGE_MODES)
            db.commit()
            apply_bundle(db, bundle, media, 'gallery')
            self.assertEqual(json.loads(db.get(SystemSetting, HOME_KEY).value)['hero_title'], DEFAULT_HOME['hero_title'])
            self.assertEqual(json.loads(db.get(SystemSetting, PAGE_MODES_KEY).value)['team'], 'default')
            apply_bundle(db, bundle, media, 'all')
            self.assertEqual(json.loads(db.get(SystemSetting, PAGE_MODES_KEY).value)['team'], 'light')
            self.assertEqual(json.loads(db.get(SystemSetting, HOME_KEY).value)['hero_title'], 'Transfer title')
            self.assertEqual(json.loads(db.get(SystemSetting, THEME_KEY).value)['light_background'], '#abcdef')
            for version in (1, 2):
                old = bundle.model_dump(mode='json')
                old['version'] = version
                old.pop('partners', None)
                old.pop('documents', None)
                old.pop('home_images', None)
                if version == 1:
                    old.pop('about')
                for key in (THEME_KEY, FOOTER_KEY, HOME_KEY, PAGE_MODES_KEY):
                    old['settings'].pop(key)
                apply_bundle(db, SiteBundle.model_validate(old), media, 'all')
                self.assertEqual(json.loads(db.get(SystemSetting, HOME_KEY).value)['hero_title'], 'Transfer title')
            invalid = bundle.model_dump(mode='json')
            invalid['settings'][THEME_KEY] = json.dumps({**theme, 'dark_text': 'red;evil'})
            with self.assertRaises(ValueError):
                SiteBundle.model_validate(invalid)
            unsafe = bundle.model_dump(mode='json')
            unsafe['settings'][FOOTER_KEY] = json.dumps({**footer, 'additional': '<script>alert(1)</script><b>Safe</b>'})
            self.assertNotIn('<script', SiteBundle.model_validate(unsafe).settings[FOOTER_KEY])

    def test_gallery_seed_migration(self):
        spec = importlib.util.spec_from_file_location('gallery_migration', 'alembic/versions/c92d03e54f21_add_gallery.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                with sessionmaker(bind=connection)() as db:
                    self.assertEqual(db.query(GalleryPhoto).count(), 33)
                    for photo in db.query(GalleryPhoto): self.assertTrue(Path(photo.photo.lstrip('/')).is_file())
                migration.downgrade()
        engine.dispose()
