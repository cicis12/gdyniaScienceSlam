from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZIP_DEFLATED

from bs4 import BeautifulSoup
from pydantic import ValidationError
import requests

import test_site_content as content_tests
import test_gallery_transfer as transfer_tests
from models import SystemSetting
from partnership_content import (PartnershipConfig, PersonSection, GridSection, IconsSection, FAQSection,
                                 ContactSection, ParagraphSection, HeadingSection, get_partnership, save_partnership)
from site_pages import PUBLIC_PAGES
from site_transfer import apply_bundle, export_bundle, inspect_bundle
import mail

SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="8"/></svg>'


class PartnershipTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()
        self.photo_dir = Path(self.fixture.temp.name) / 'partnership'
        self.photo_patch = patch('routers.partnership.PHOTO_DIR', self.photo_dir)
        self.photo_patch.start()

    def tearDown(self):
        self.photo_patch.stop()
        self.fixture.tearDown()

    def save(self, config):
        with self.sessions() as db:
            save_partnership(db, config)
            db.commit()

    def config(self):
        with self.sessions() as db:
            return get_partnership(db)

    def submit(self, config, action='save', files=None):
        return self.client.post('/admin/become-a-partner/' + action,
                                data={'config': config.model_dump_json()}, files=files)

    def test_whole_page_save_multi_person_and_rendering(self):
        from partnership_content import ContactPerson
        config = PartnershipConfig(sections=[
            GridSection(id='grid', enabled=True, items=[{'title': 'Item', 'text': 'Description'}] * 6),
            ParagraphSection(id='paragraph', enabled=True, text='<strong>Body copy</strong><script>alert(1)</script>'),
            IconsSection(id='icons', enabled=True, items=[{'svg': SVG, 'text': 'Icon copy'}] * 3),
            HeadingSection(id='heading', enabled=True, title='Big heading'),
            PersonSection(id='people', enabled=True, team_link=True, team_link_label='Meet the team', people=[
                ContactPerson(id='jane', name='Jane Partner', occupation='Coordinator'),
                ContactPerson(id='john', name='John Partner', occupation='Organiser')]),
            FAQSection(id='faq', enabled=True, items=[{'question': 'First?', 'answer': 'First answer'}, {'question': 'Second?', 'answer': 'Second answer'}]),
            ContactSection(id='contact', enabled=True)])
        response = self.submit(config, files={'photo:people:jane': self.fixture.photo(), 'photo:people:john': self.fixture.photo()})
        self.assertEqual(response.status_code, 200, response.text[:500])
        self.assertTrue(response.json()['config']['sections'][4]['people'][0]['photo'])
        soup = BeautifulSoup(self.client.get('/become-a-partner').text, 'html.parser')
        self.assertEqual(len(soup.select('.about-benefits-grid article')), 6)
        self.assertEqual(len(soup.select('.partnership-icon-grid article')), 3)
        self.assertEqual(len(soup.select('.partnership-icon svg')), 3)
        self.assertEqual(len(soup.select('.partnership-faq details')), 2)
        self.assertTrue(soup.select_one('.partnership-faq details').has_attr('open'))
        self.assertEqual(len(soup.select('.partnership-big-heading')), 1)
        self.assertEqual([image['alt'] for image in soup.select('.partnership-portrait')], ['Jane Partner', 'John Partner'])
        self.assertEqual(len(soup.select('.partnership-team-link')), 1)
        self.assertNotIn('alert(1)', str(soup))
        self.assertIn('<strong>Body copy</strong>', str(soup))
        self.assertEqual(len(list(self.photo_dir.glob('*.webp'))), 2)
        updated = self.config()
        updated.sections[4].people.pop()
        updated.sections = updated.sections[:-1]
        self.assertEqual(self.submit(updated).status_code, 200)
        self.assertEqual(len(self.config().sections), 6)
        self.assertEqual(len(self.config().sections[4].people), 1)
        admin = BeautifulSoup(self.client.get('/admin/become-a-partner').text, 'html.parser')
        self.assertEqual(len(admin.select('#partnership-editor-form button[type="submit"]')), 1)
        self.assertEqual(admin.select_one('#partnership-editor-form button[type="submit"]').text, 'Zapisz całą stronę')
        self.assertIsNotNone(admin.select_one('#preview-partnership'))
        self.assertIsNotNone(admin.select_one('#partnership-preview-frame'))

    def test_paragraph_image_preview_save_validation_and_removal(self):
        draft = PartnershipConfig(sections=[ParagraphSection(
            id='story', title='Work with us', text='<strong>Our story</strong>', enabled=True,
            photo_alt='People working together')])
        response = self.submit(draft, 'preview', files={'paragraph_photo:story': self.fixture.photo()})
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.text, 'html.parser')
        layout = soup.select_one('.partnership-paragraph-with-photo')
        self.assertEqual(layout.select_one('h2').text, 'Work with us')
        self.assertTrue(layout.img['src'].startswith('data:image/webp;base64,'))
        self.assertEqual(layout.img['alt'], 'People working together')
        self.assertFalse(list(self.photo_dir.glob('*')))
        self.assertEqual(self.config().sections, [])
        response = self.submit(draft, files={'paragraph_photo:story': self.fixture.photo()})
        self.assertEqual(response.status_code, 200)
        stored = self.config()
        self.assertTrue(stored.sections[0].photo.startswith('/static/uploads/partnership/'))
        self.assertEqual(len(list(self.photo_dir.glob('*.webp'))), 1)
        soup = BeautifulSoup(self.client.get('/become-a-partner').text, 'html.parser')
        self.assertEqual(soup.select_one('.partnership-paragraph-photo')['src'], stored.sections[0].photo)
        failed = self.submit(stored, files={'paragraph_photo:story': ('bad.png', b'not an image', 'image/png')})
        self.assertEqual(failed.status_code, 422)
        self.assertEqual(self.config(), stored)
        stored.sections[0].photo = ''
        self.assertEqual(self.submit(stored).status_code, 200)
        soup = BeautifulSoup(self.client.get('/become-a-partner').text, 'html.parser')
        self.assertIsNone(soup.select_one('.partnership-paragraph-photo'))
        self.assertIn('Our story', soup.text)
        self.assertEqual(ParagraphSection.model_validate({'type': 'paragraph', 'text': 'Legacy'}).photo, '')
        for path in ('https://external.example/image.jpg', 'data:image/png;base64,x'):
            with self.assertRaises(ValidationError):
                ParagraphSection(photo=path)

    def test_preview_email_is_readable_without_decoding_scripts(self):
        from partnership_content import ContactPerson
        draft = PartnershipConfig(sections=[PersonSection(id='people', enabled=True, people=[
            ContactPerson(name='Jane', occupation='Lead', photo='/static/uploads/contact.webp',
                          details='<a href="mailto:partners@example.com">partners@example.com</a>')])])
        response = self.submit(draft, 'preview')
        self.assertEqual(response.status_code, 200)
        # Cloudflare must leave script-free preview email addresses untouched.
        start = response.text.index('<!--email_off-->')
        end = response.text.index('<!--/email_off-->')
        self.assertIn('mailto:partners@example.com', response.text[start:end])
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertEqual(soup.select_one('.partnership-person a').text, 'partners@example.com')
        self.assertFalse(soup.select('script'))

    def test_settings_independent_home_section_visibility_and_order(self):
        config = PartnershipConfig(title='Join us', link_label='Partner with us', teaser='Build the next edition',
                                   featured=True, recipient='private-recipient@example.com')
        self.assertEqual(self.submit(config).status_code, 200)
        soup = BeautifulSoup(self.client.get('/').text, 'html.parser')
        feature = soup.select_one('section.partnership-home-feature')
        self.assertIsNotNone(feature)
        self.assertIn('home-editorial', feature['class'])
        self.assertIsNotNone(feature.select_one('img'))
        self.assertIsNotNone(feature.select_one('h2'))
        self.assertIsNone(feature.find_parent(class_='home-partners-section'))
        self.assertEqual(feature.find_previous_sibling('section')['class'][0], 'home-scroll-section')
        self.assertNotIn('private-recipient@example.com', str(soup) + self.client.get('/become-a-partner').text)
        # The feature is its own section even when Partners is disabled.
        self.client.post('/admin/content/home/sections', data={'visible': ['hero', 'about', 'archive']})
        self.assertIsNotNone(BeautifulSoup(self.client.get('/').text, 'html.parser').select_one('section.partnership-home-feature'))
        config.sections = [ParagraphSection(id='later', text='Later copy', sort_order=10, enabled=True),
                           ParagraphSection(id='first', text='First copy', sort_order=0, enabled=True)]
        self.assertEqual(self.submit(config).status_code, 200)
        text = self.client.get('/become-a-partner').text
        self.assertLess(text.index('First copy'), text.index('Later copy'))
        self.client.post('/admin/content/pages', data={'visible': [key for key, _, _ in PUBLIC_PAGES if key != 'become_partner']})
        self.assertEqual(self.client.get('/become-a-partner').status_code, 404)
        self.assertEqual(self.client.post('/become-a-partner/contact/missing', json={}).status_code, 404)
        self.assertNotIn('href="/become-a-partner"', self.client.get('/').text)
        # Admin draft preview remains accessible when the public page is hidden.
        self.assertEqual(self.submit(config, 'preview').status_code, 200)

    def test_preview_is_unsaved_sanitized_and_includes_new_photos(self):
        from partnership_content import ContactPerson
        draft = PartnershipConfig(title='Unsaved title', sections=[
            PersonSection(id='people', enabled=True, people=[ContactPerson(id='jane', name='Jane', occupation='Lead')]),
            ParagraphSection(id='paragraph', enabled=True, text='<strong>Preview body</strong><script>alert(1)</script>'),
            ContactSection(id='contact', enabled=True)])
        response = self.submit(draft, 'preview', files={'photo:people:jane': self.fixture.photo()})
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertEqual(soup.h1.text, 'Unsaved title')
        gallery = BeautifulSoup(self.client.get('/previous_editions').text, 'html.parser')
        self.assertEqual(soup.select_one('link[href*="fonts.googleapis.com/css2"]')['href'],
                         gallery.select_one('link[href*="fonts.googleapis.com/css2"]')['href'])
        self.assertTrue(soup.select_one('.partnership-portrait')['src'].startswith('data:image/webp;base64,'))
        self.assertTrue(soup.select_one('[data-partner-contact]').has_attr('inert'))
        self.assertNotIn('alert(1)', response.text)
        self.assertNotIn('/static/js/partnership.js', response.text)
        self.assertIn("form-action 'none'", response.text)
        self.assertIn("script-src 'none'", response.text)
        self.assertEqual(soup.find_all('script'), [])
        self.assertTrue(soup.select_one('.partnership-submit').has_attr('disabled'))
        self.assertFalse(list(self.photo_dir.glob('*')))
        self.assertEqual(self.config().sections, [])
        self.assertNotIn('Unsaved title', self.client.get('/become-a-partner').text)

    def test_preview_frame_has_normal_navigation_and_empty_draft_feedback(self):
        admin = BeautifulSoup(self.client.get('/admin/become-a-partner').text, 'html.parser')
        frame = admin.select_one('#partnership-preview-frame')
        self.assertEqual(frame['name'], 'partnership-preview-frame')
        self.assertEqual(frame['sandbox'], ['allow-same-origin'])
        self.assertIsNotNone(admin.select_one('#partnership-preview-status[role="status"]'))
        self.assertNotIn('Wysyłanie formularzy jest wyłączone', admin.text)
        draft = PartnershipConfig(sections=[ParagraphSection(id='draft', enabled=False, text='Hidden text')])
        response = self.submit(draft, 'preview')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertIsNotNone(soup.select_one('.partnership-preview-empty'))
        self.assertIn('Pokaż sekcję', soup.select_one('.partnership-preview-empty').text)
        self.assertNotIn('Hidden text', response.text)
        self.assertEqual(self.config().sections, [])

    def test_atomic_validation_permissions_and_legacy_person(self):
        legacy = PartnershipConfig.model_validate({'sections': [{'type': 'person', 'id': 'person', 'name': 'Legacy person',
                                                                'occupation': 'Lead', 'photo': '/static/uploads/test.webp'}]})
        self.assertEqual(legacy.sections[0].people[0].name, 'Legacy person')
        self.assertEqual(legacy.sections[0].people[0].id, 'contact')
        self.save(legacy)
        original = self.config()
        config = self.config()
        config.title = 'Must not save'
        config.sections[0].enabled = True
        config.sections[0].people[0].occupation = ''
        response = self.submit(config, files={'photo:person:contact': self.fixture.photo()})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.config(), original)
        self.assertFalse(list(self.photo_dir.glob('*')))
        config = self.config()
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('Database failure')):
            with self.assertRaises(RuntimeError):
                self.submit(config, files={'photo:person:contact': self.fixture.photo()})
        self.assertFalse(list(self.photo_dir.glob('*')))
        self.assertEqual(self.config(), original)
        for value in ({'items': []}, {'items': [{}] * 7}):
            with self.assertRaises(ValidationError):
                GridSection(**value)
        with self.assertRaises(ValidationError):
            IconsSection(items=[{'svg': '<svg onload="alert(1)"/>'}] * 3)
        for username, expected in ((None, 303), ('regular', 403)):
            self.client.cookies.clear()
            if username:
                self.fixture.login(username)
            for path in ('/save', '/preview'):
                self.assertEqual(self.client.post('/admin/become-a-partner' + path, follow_redirects=False).status_code, expected)

    def test_contact_validation_delivery_failures_and_limits(self):
        self.save(PartnershipConfig(recipient='partners@example.com', sections=[ContactSection(id='contact', enabled=True)]))
        endpoint = '/become-a-partner/contact/contact'
        message = dict(name='Jane', email='jane@example.com', topic='A partnership', content='Hello <b>team</b>')
        with patch('mail.API_KEY', 'test-key'), patch('mail.EMAIL_FROM', 'sender@example.com'), patch('mail.requests.post') as send:
            send.return_value = Mock(status_code=202)
            self.assertEqual(self.client.post(endpoint, json=message).status_code, 200)
            payload = send.call_args.kwargs['json']
            self.assertEqual(payload['to'], [{'email': 'partners@example.com'}])
            self.assertEqual(payload['reply_to']['email'], 'jane@example.com')
            self.assertEqual(payload['from']['email'], 'sender@example.com')
            self.assertNotIn('html', payload)
            self.assertIn('<b>team</b>', payload['text'])
            send.reset_mock()
            for invalid in ({'email': 'bad'}, {'topic': '  '}, {'name': 'Jane\nInjected'}, {'content': 'a' * 10001}, {'website': 'bot.example'}):
                self.assertEqual(self.client.post(endpoint, json={**message, **invalid}).status_code, 422)
            send.assert_not_called()
            send.return_value = Mock(status_code=422)
            self.assertEqual(self.client.post(endpoint, json=message).status_code, 502)
            send.side_effect = requests.Timeout()
            self.assertEqual(self.client.post(endpoint, json=message).status_code, 502)
            send.side_effect = None
            with patch('mail.API_KEY', None):
                self.assertEqual(self.client.post(endpoint, json=message).status_code, 503)
        # Consume the tenth allowed request; the next is rejected before parsing.
        self.assertEqual(self.client.post(endpoint, json=message).status_code, 503)
        self.assertEqual(self.client.post(endpoint, json=message).status_code, 429)
        from request_limits import form_rate_storage
        form_rate_storage.reset()
        self.assertEqual(self.client.post(endpoint, content=b'x' * 32769).status_code, 413)
        self.assertEqual(self.client.post('/become-a-partner/contact/missing', json=message).status_code, 404)
        config = self.config()
        config.sections[0].enabled = False
        self.save(config)
        self.assertEqual(self.client.post(endpoint, json=message).status_code, 404)


class PartnershipTransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture = transfer_tests.GalleryTransferTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_roundtrip_photo_icons_and_old_bundle(self):
        with self.fixture.sessions() as db:
            original = PartnershipConfig(featured=True, uuid_only=True, feature_photo='/static/uploads/gallery/test.webp', sections=[
                PersonSection(id='person', name='Person', photo='/static/uploads/gallery/test.webp'),
                IconsSection(id='icons', items=[{'svg': SVG}] * 3),
                ParagraphSection(id='story', photo='/static/uploads/gallery/test.webp', photo_alt='Our team')])
            save_partnership(db, original)
            db.commit()
            raw = export_bundle(db)
            bundle, media = inspect_bundle(raw)
            self.assertTrue(bundle.partnership.featured)
            save_partnership(db, PartnershipConfig())
            db.commit()
            apply_bundle(db, bundle, media, 'gallery')
            self.assertFalse(get_partnership(db).featured)
            apply_bundle(db, bundle, media, 'all')
            actual = get_partnership(db)
            self.assertTrue(actual.featured)
            self.assertTrue(actual.uuid_only)
            self.assertTrue((self.fixture.static_root / actual.feature_photo.removeprefix('/static/')).is_file())
            person = actual.sections[0]
            self.assertTrue((self.fixture.static_root / person.people[0].photo.removeprefix('/static/')).is_file())
            self.assertEqual(actual.sections[1].items[0].svg, SVG)
            self.assertTrue((self.fixture.static_root / actual.sections[2].photo.removeprefix('/static/')).is_file())
            self.assertEqual(actual.sections[2].photo_alt, 'Our team')
            # An old bundle lacks the optional page data and visibility setting.
            with ZipFile(BytesIO(raw)) as archive:
                entries = {name: archive.read(name) for name in archive.namelist()}
            manifest = json.loads(entries['manifest.json'])
            # The previous format stored the contact directly on its section.
            legacy_manifest = json.loads(entries['manifest.json'])
            section = legacy_manifest['partnership']['sections'][0]
            contact = section.pop('people')[0]
            contact.pop('id')
            section.update(contact)
            legacy_manifest['partnership'].pop('feature_photo')
            old_shape = type(bundle).model_validate(legacy_manifest)
            self.assertEqual(old_shape.partnership.sections[0].people[0].name, 'Person')
            manifest.pop('partnership')
            manifest['settings'].pop('page_visible:become_partner')
            entries['manifest.json'] = json.dumps(manifest).encode()
            output = BytesIO()
            with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            old_bundle, old_media = inspect_bundle(output.getvalue())
            apply_bundle(db, old_bundle, old_media, 'all')
            self.assertEqual(get_partnership(db), actual)
