import unittest
from unittest.mock import patch
from http.cookies import SimpleCookie

from bs4 import BeautifulSoup
from pydantic import ValidationError

import test_site_content as content_tests
from forms import FormDefinition, build_submission_model
from models import FormInfo, FormVersion, FormSubmission, SystemSetting, Voter
from site_transfer import FormRecord

SVG = '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'


class FormFixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = content_tests.ContentTests()
        self.fixture.setUp()
        self.client = self.fixture.client
        self.sessions = self.fixture.sessions
        self.fixture.login()

    def tearDown(self):
        self.fixture.tearDown()

    def create(self, fields, svg=None, slug='test'):
        response = self.client.post('/admin/forms/create', json={
            'name': slug, 'slug': slug, 'display_name': 'Zgłoszenie',
            'description': '<strong>Opis</strong>', 'svg': svg, 'fields': fields,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_optional_blanks_and_nulls_across_input_types(self):
        fields = [dict(name=kind, type=kind, question=kind, options=['A', 'B'])
                  for kind in ('text', 'email', 'phone', 'list_choice', 'textarea', 'school', 'checkbox')]
        model = build_submission_model(FormDefinition(fields=fields))
        for value in ('', '  ', None):
            result = model.model_validate({field['name']: value for field in fields}).model_dump()
            self.assertTrue(all(value is None for value in result.values()))
        self.assertTrue(all(value is None for value in model.model_validate({}).model_dump().values()))
        for answers in ({'email': 'wrong'}, {'list_choice': 'invalid'}):
            with self.assertRaises(ValidationError):
                model.model_validate(answers)

    def test_submission_saves_optional_email_and_rejects_invalid_required_answers(self):
        record = self.create([
            dict(name='email', type='email', question='Adres e-mail'),
            dict(name='consent', type='checkbox', question='<b>Akceptuję</b> regulamin', required=True),
        ])
        payload = dict(form_id=record['form_id'], form_version_id=record['version_id'], answers={'email': '', 'consent': 'true'})
        self.assertEqual(self.client.post('/api/forms/submit', json=payload).status_code, 200)
        with self.sessions() as db:
            self.assertIsNone(db.query(FormSubmission).one().data['email'])
        for answers in ({'email': 'bad', 'consent': 'true'}, {'consent': 'false'}, {}):
            response = self.client.post('/api/forms/submit', json={**payload, 'answers': answers})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['code'], 'invalid_answers')
            self.assertNotIn('DynamicSubmission', response.text)
            self.assertNotIn('input_value', response.text)
            self.assertNotIn('<b>', response.json()['message'])
        with self.sessions() as db:
            self.assertEqual(db.query(FormSubmission).count(), 1)

    def test_svg_absent_blank_present_and_invalid(self):
        for icon in (None, '', ' \n ', SVG):
            record = FormRecord(slug='test', name='Test', display_name='Test', enabled=True,
                                definition={'svg': icon, 'fields': [{'name': 'email', 'type': 'email', 'question': 'Email', 'svg': icon}]})
            self.assertEqual(record.definition.svg, SVG if icon == SVG else None)
        with self.assertRaisesRegex(ValidationError, 'email'):
            FormRecord(slug='test', name='Test', display_name='Test', enabled=True,
                       definition={'fields': [{'name': 'email', 'type': 'email', 'question': 'Email', 'svg': '<svg'}]})
        record = self.create([dict(name='text', type='text', question='Imię', svg=SVG)], SVG)
        page = BeautifulSoup(self.client.get('/forms/test').text, 'html.parser')
        self.assertFalse(page.select_one('.form-icon svg'))
        self.assertTrue(page.select_one('.form-field-icon svg'))
        response = self.client.post(f"/admin/forms/{record['form_id']}/new-version", json={
            'display_name': 'Version 2', 'fields': [], 'svg': SVG,
        })
        version_id = response.json()['version_id']
        response = self.client.get(f"/admin/forms/{record['form_id']}/version/{version_id}")
        self.assertEqual(response.json()['svg'], SVG)
        self.assertEqual(self.client.post('/admin/forms/create', json={
            'name': 'bad', 'slug': 'bad', 'display_name': 'Bad', 'fields': [], 'svg': '<svg',
        }).status_code, 422)

    def test_html_and_registration_tabs(self):
        first = self.create([dict(name='consent', type='checkbox', question='Akceptuję <a href="/documents">regulamin</a>')])
        with self.sessions() as db:
            db.merge(SystemSetting(key='registration_form_ids', value=str(first['form_id'])))
            db.commit()
        for path in ('/registration', '/forms/test'):
            soup = BeautifulSoup(self.client.get(path).text, 'html.parser')
            self.assertTrue(soup.select_one('.checkbox-copy a[href="/documents"]'))
            self.assertFalse(soup.select('.registration-form-tabs'))
        second = self.create([], slug='second')
        with self.sessions() as db:
            db.merge(SystemSetting(key='registration_form_ids', value=f"{first['form_id']},{second['form_id']}"))
            db.commit()
        self.assertEqual(len(BeautifulSoup(self.client.get('/registration').text, 'html.parser').select('.registration-form-tabs .tab')), 2)
        with self.sessions() as db:
            db.get(FormInfo, second['form_id']).enabled = False
            db.commit()
        self.assertNotIn('id="tab-slider"', self.client.get('/registration').text)

    def test_cookies_expire_with_tokens(self):
        with patch('main.verify_password', return_value=True):
            response = self.client.post('/adminLogin', data={'username': 'super', 'password': 'test'}, follow_redirects=False)
        cookie = SimpleCookie(response.headers['set-cookie'])['admin_session']
        self.assertEqual(cookie['max-age'], '14400')
        self.assertTrue(cookie['expires'])
        self.assertTrue(cookie['httponly'])
        with self.sessions() as db:
            db.add(Voter(email='voter@example.com'))
            db.commit()
        response = self.client.post('/vote/login', data={'email': 'voter@example.com'}, follow_redirects=False)
        cookie = SimpleCookie(response.headers['set-cookie'])['voter_session']
        self.assertEqual(cookie['max-age'], '43200')
        self.assertTrue(cookie['expires'])
