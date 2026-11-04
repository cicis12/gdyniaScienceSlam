"""Present answers in the order defined by the submitted form version."""
import json
from urllib.parse import quote


def submission_answers(submission, version):
    fields = version.definition.get('fields', []) if version else []
    labels = {}
    for field in fields:
        for name, question in (('name', 'question'), ('name2', 'question2')):
            if field.get(name):
                labels[field[name]] = field.get(question) or field[name]
    order = {key: index for index, key in enumerate(labels)}
    file_fields = {field['name'] for field in fields if field.get('type') == 'file'}
    answers = []
    for key, value in sorted((submission.data or {}).items(), key=lambda item: order.get(item[0], len(order))):
        attachment = value if key in file_fields and isinstance(value, dict) and value.get('kind') == 'attachment' else None
        display = ('—' if value in (None, '') else
                   ('Tak' if value else 'Nie') if isinstance(value, bool) else
                   json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value))
        answers.append({'key': key, 'label': labels.get(key, key), 'attachment': attachment,
                        'upload_url': f"/admin/uploads/{submission.id}/{quote(key, safe='')}", 'value': display})
    return answers
