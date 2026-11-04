"""Build private, disk-backed ZIP exports of all answers to a selected form."""
import csv
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from fastapi import HTTPException
from form_answers import submission_answers
from form_uploads import attachment_path
from models import FormSubmission, FormVersion


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {'br', 'p', 'div', 'li'}:
            self.parts.append('\n')


def plain_label(value):
    parser = PlainText()
    parser.feed(str(value))
    return ''.join(parser.parts).strip()


def csv_cell(value):
    text = str(value)
    # Keep submitted text from becoming a spreadsheet formula when opened in Excel.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def filename(value):
    name = str(value).replace('\\', '/').split('/')[-1]
    return re.sub(r'[^\w.\-]', '_', name)[:140].strip('.') or 'file'


def export_form_answers(db, form):
    directory = Path(tempfile.mkdtemp(prefix='gss-form-export-'))
    archive_path = directory / 'answers.zip'
    try:
        versions = {v.id: v for v in db.query(FormVersion).filter_by(form_id=form.id)}
        submissions = (db.query(FormSubmission).filter_by(form_id=form.id)
                       .order_by(FormSubmission.submitted_at.desc(), FormSubmission.id.desc()).yield_per(100))
        with ZipFile(archive_path, 'w', compression=ZIP_DEFLATED, allowZip64=True) as archive, \
                (directory / 'answers.csv').open('w', encoding='utf-8-sig', newline='') as csv_file, \
                (directory / 'answers.txt').open('w', encoding='utf-8') as txt_file:
            writer = csv.writer(csv_file, delimiter=';')
            writer.writerow(['Zgłoszenie', 'Data', 'Wersja', 'Pole', 'Pytanie', 'Odpowiedź', 'Załącznik'])
            txt_file.write(f'Formularz: {form.name}\n\n')
            archive.writestr('attachments/', b'')
            count = 0
            for submission in submissions:
                count += 1
                version = versions.get(submission.form_version_id)
                version_num = version.version_num if version else ''
                date = submission.submitted_at.isoformat(sep=' ', timespec='seconds') if submission.submitted_at else ''
                txt_file.write(f'Zgłoszenie #{submission.id}\nData: {date}\nWersja: {version_num}\n')
                answers = submission_answers(submission, version)
                if not answers:
                    writer.writerow([submission.id, date, version_num, '', '', '', ''])
                    txt_file.write('Brak odpowiedzi.\n')
                for index, answer in enumerate(answers, 1):
                    value, relative = answer['value'], ''
                    if answer['attachment']:
                        record = answer['attachment']
                        value = record.get('filename', 'file')
                        try:
                            path = attachment_path(record)
                            relative = f"attachments/{submission.id}/{index:03d}-{filename(value)}"
                            archive.write(path, relative, compress_type=ZIP_STORED)
                        except (HTTPException, FileNotFoundError):
                            relative = ''
                            value += ' (brak pliku)'
                    label = plain_label(answer['label'])
                    writer.writerow([csv_cell(cell) for cell in [submission.id, date, version_num,
                                                                answer['key'], label, value, relative]])
                    txt_file.write(f'\n{label}\n{value}\n')
                    if relative:
                        txt_file.write(f'Załącznik: {relative}\n')
                txt_file.write('\n' + '—' * 40 + '\n\n')
            txt_file.write(f'Liczba zgłoszeń: {count}\n')
        with ZipFile(archive_path, 'a', compression=ZIP_DEFLATED) as archive:
            archive.write(directory / 'answers.csv', 'answers.csv')
            archive.write(directory / 'answers.txt', 'answers.txt')
        return archive_path
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
