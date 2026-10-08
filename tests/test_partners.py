from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import json
from hashlib import sha256
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from bs4 import BeautifulSoup
from PIL import Image

import test_site_content as content_tests
import test_gallery_transfer as transfer_tests
from models import TeamMember
from partner_content import (Partner, PartnerSection, PartnersConfig, get_partners, save_partners,
                             normalize_svg)
from site_transfer import export_bundle, inspect_bundle, apply_bundle

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><path fill="#123456" d="M0 0h100v50H0z"/></svg>'


class PartnersTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()
        self.logo_dir = Path(self.fixture.temp.name) / 'partners'
        item = patch('routers.partners_admin.LOGO_DIR', self.logo_dir)
        item.start()
        self.fixture.patches.append(item)
        with self.sessions() as db:
            save_partners(db, PartnersConfig())
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def add_section(self, title='Test section', highlighted=False):
        response = self.client.post('/admin/partners/sections', data={
            'title': title, 'enabled': 'true', 'highlighted': str(highlighted).lower(), 'sort_order': '0'})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            return next(section.id for section in get_partners(db).sections if section.title == title)

    def add_partner(self, section_id, name='New partner', photo=None):
        response = self.client.post(f'/admin/partners/sections/{section_id}/partners', data={
            'name': name, 'website': 'https://example.com', 'logo_scale': '1.2', 'sort_order': '1'},
            files={'logo': photo or self.fixture.photo()})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            return next(partner for section in get_partners(db).sections for partner in section.partners if partner.name == name)

    def test_section_and_partner_crud_move_highlight_and_carousel(self):
        section = self.add_section()
        partner = self.add_partner(section)
        home = BeautifulSoup(self.client.get('/').text, 'html.parser')
        self.assertEqual(len(home.select('.partner-carousel-card img[alt="New partner"]')), 2)
        self.assertIn('New partner', self.client.get('/partners').text)
        second = self.add_section('Main sponsor', True)
        response = self.client.post(f'/admin/partners/sections/{section}/partners/{partner.id}', data={
            'name': 'Renamed partner', 'website': 'https://example.org', 'destination_section': second,
            'logo_scale': '1.5', 'sort_order': '0'})
        self.assertEqual(response.status_code, 200)
        with self.sessions() as db:
            config = get_partners(db)
            moved = next(s for s in config.sections if s.id == second).partners[0]
            self.assertEqual(moved.logo, partner.logo)
            self.assertFalse(next(s for s in config.sections if s.id == section).partners)
        soup = BeautifulSoup(self.client.get('/partners').text, 'html.parser')
        self.assertEqual(len(soup.select('.partners-section')), 1)
        self.assertTrue(soup.select_one('.partners-section-highlighted'))
        self.assertTrue(soup.select_one('a[href="https://example.org"]'))
        self.client.post(f'/admin/partners/sections/{second}', data={'title': 'Normal', 'enabled': 'true', 'sort_order': '0'})
        self.assertNotIn('partners-section-highlighted', self.client.get('/partners').text)
        self.client.post(f'/admin/partners/sections/{second}/partners/{partner.id}/delete')
        self.assertNotIn('Renamed partner', self.client.get('/partners').text)
        self.assertNotIn('partner-carousel-card', self.client.get('/').text)
        self.client.post(f'/admin/partners/sections/{section}/delete')
        self.client.post(f'/admin/partners/sections/{second}/delete')
        with self.sessions() as db:
            self.assertEqual(get_partners(db).sections, [])

    def test_global_and_section_visibility_preserve_data(self):
        section = self.add_section()
        self.add_partner(section)
        self.client.post('/admin/partners/settings')
        self.assertNotIn('New partner', self.client.get('/partners').text)
        self.assertNotIn('home-partners-section', self.client.get('/').text)
        with self.sessions() as db:
            self.assertEqual(len(get_partners(db).sections[0].partners), 1)
        self.client.post('/admin/partners/settings', data={'enabled': 'true'})
        self.client.post(f'/admin/partners/sections/{section}', data={'title': 'Hidden', 'sort_order': '0'})
        self.assertNotIn('New partner', self.client.get('/partners').text)
        self.assertNotIn('home-partners-section', self.client.get('/').text)
        self.client.post(f'/admin/partners/sections/{section}', data={'title': 'Visible', 'enabled': 'true', 'sort_order': '0'})
        self.assertIn('New partner', self.client.get('/partners').text)
        self.assertIn('New partner', self.client.get('/').text)

    def test_upload_validation_svg_and_transparency(self):
        section = self.add_section()
        endpoint = f'/admin/partners/sections/{section}/partners'
        for filename, data in [('bad.png', b'fake'), ('bad.svg', b'<svg><script>alert(1)</script></svg>'),
                               ('bad.svg', b'<!DOCTYPE svg [<!ENTITY a "bad">]><svg>&a;</svg>'),
                               ('bad.svg', b'<svg><use href="https://example.com/logo.svg"/></svg>')]:
            self.assertEqual(self.client.post(endpoint, data={'name': 'Invalid'}, files={'logo': (filename, data)}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, data={'name': 'Invalid', 'website': 'javascript:alert(1)'}, files={'logo': self.fixture.photo()}).status_code, 422)
        self.assertFalse(self.logo_dir.exists())
        svg_partner = self.add_partner(section, 'Vector', ('logo.svg', SVG, 'image/svg+xml'))
        self.assertTrue(svg_partner.logo.endswith('.svg'))
        self.assertNotIn(b'script', (self.logo_dir / Path(svg_partner.logo).name).read_bytes())
        source = Image.new('P', (8, 8))
        source.putpalette([255, 0, 0] + [0, 0, 0] * 255)
        source.info['transparency'] = 0
        output = BytesIO()
        source.save(output, 'PNG')
        partner = self.add_partner(section, 'Transparent', ('transparent.png', output.getvalue(), 'image/png'))
        with Image.open(self.logo_dir / Path(partner.logo).name) as image:
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_failed_commit_cleans_logo_and_rolls_back(self):
        section = self.add_section()
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('test rollback')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/admin/partners/sections/{section}/partners', data={'name': 'Fail'}, files={'logo': self.fixture.photo()})
        self.assertEqual(list(self.logo_dir.iterdir()), [])
        with self.sessions() as db:
            self.assertEqual(get_partners(db).sections[0].partners, [])

    def test_permissions_mode_and_back_link(self):
        response = self.client.post('/admin/content/page-mode/partners', data={'mode': 'dark'}, follow_redirects=False)
        self.assertEqual(response.headers['location'], '/admin/partners?saved=1')
        body = BeautifulSoup(self.client.get('/partners').text, 'html.parser').body
        self.assertEqual(body['data-display-mode'], 'dark')
        links = BeautifulSoup(self.client.get('/admin/partners').text, 'html.parser').select('.content-admin a')
        self.assertEqual([link['href'] for link in links], ['/admin/content'])
        for username, status in ((None, 303), ('regular', 403)):
            self.client.cookies.clear()
            if username:
                self.fixture.login(username)
            for path in ('/settings', '/sections', '/sections/missing', '/sections/missing/delete',
                         '/sections/missing/partners', '/sections/missing/partners/missing', '/sections/missing/partners/missing/delete'):
                self.assertEqual(self.client.post('/admin/partners' + path, follow_redirects=False).status_code, status)

    def test_existing_partners_are_preserved_and_exportable(self):
        with self.sessions() as db:
            from partner_content import PARTNERS_KEY
            from models import SystemSetting
            db.delete(db.get(SystemSetting, PARTNERS_KEY))
            db.query(TeamMember).update({'photo': '/static/assets/images/gallery6.webp'})
            db.commit()
            self.assertEqual(len(get_partners(db).carousel_partners), 9)
            bundle, media = inspect_bundle(export_bundle(db))
        self.assertEqual(bundle.version, 4)
        self.assertEqual(sum(len(section.partners) for section in bundle.partners.sections), 9)
        self.assertEqual(sum(name.endswith('.svg') for name in media), 2)
        for path in Path('static/assets/images/partners').glob('*.svg'):
            self.assertTrue(normalize_svg(path.read_bytes()).startswith(b'<?xml'))


class PartnerTransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture = transfer_tests.GalleryTransferTests()
        self.fixture.setUp()
        self.sessions = self.fixture.sessions
        (self.fixture.gallery_dir / 'logo.svg').write_bytes(SVG)
        self.config = PartnersConfig(enabled=False, sections=[PartnerSection(id='sponsors', title='Main sponsor', highlighted=True, partners=[
            Partner(id='png', name='Raster logo', logo='/static/uploads/gallery/test.webp'),
            Partner(id='svg', name='Vector logo', logo='/static/uploads/gallery/logo.svg')])])
        with self.sessions() as db:
            save_partners(db, self.config)
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def test_full_and_gallery_scope_and_old_packages(self):
        with self.sessions() as db:
            data = export_bundle(db)
            bundle, media = inspect_bundle(data)
            self.assertEqual(bundle.version, 4)
            save_partners(db, PartnersConfig())
            db.commit()
            apply_bundle(db, bundle, media, 'gallery')
            self.assertEqual(get_partners(db).sections, [])
            apply_bundle(db, bundle, media, 'all')
            actual = get_partners(db)
            self.assertFalse(actual.enabled)
            self.assertTrue(actual.sections[0].highlighted)
            for partner in actual.sections[0].partners:
                self.assertTrue((self.fixture.static_root / partner.logo.removeprefix('/static/')).is_file())
            reexported, _ = inspect_bundle(export_bundle(db))
            self.assertEqual([p.name for p in reexported.partners.sections[0].partners], ['Raster logo', 'Vector logo'])
            for version in (1, 2):
                with ZipFile(BytesIO(data)) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith('.svg')}
                manifest = json.loads(entries['manifest.json'])
                manifest['version'] = version
                manifest.pop('partners')
                manifest.pop('documents', None)
                manifest.pop('home_images', None)
                if version == 1:
                    manifest.pop('about')
                entries['manifest.json'] = json.dumps(manifest).encode()
                output = BytesIO()
                with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
                    for name, payload in entries.items():
                        archive.writestr(name, payload)
                legacy, old_media = inspect_bundle(output.getvalue())
                apply_bundle(db, legacy, old_media, 'all')
                self.assertEqual(get_partners(db), actual)

    def test_invalid_svg_and_missing_partner_media_are_rejected(self):
        with self.sessions() as db:
            data = export_bundle(db)
        with ZipFile(BytesIO(data)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        svg_name = next(name for name in entries if name.endswith('.svg'))
        original_entries = entries.copy()
        entries.pop(svg_name)
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        with self.assertRaises(ValueError):
            inspect_bundle(output.getvalue())
        # A matching checksum does not make executable SVG acceptable.
        entries = original_entries
        malicious = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        new_name = 'media/' + sha256(malicious).hexdigest() + '.svg'
        entries.pop(svg_name)
        entries[new_name] = malicious
        manifest = json.loads(entries['manifest.json'])
        for section in manifest['partners']['sections']:
            for partner in section['partners']:
                if partner['logo'] == svg_name:
                    partner['logo'] = new_name
        entries['manifest.json'] = json.dumps(manifest).encode()
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        with self.assertRaises(ValueError):
            inspect_bundle(output.getvalue())
