"""Shared file category choices for the editor, browser, and upload validation."""
FILE_CATEGORIES = {
    'videos': ('Filmy', {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm', '.mkv': 'video/x-matroska'}),
    'images': ('Obrazy', {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}),
    'documents': ('Dokumenty', {
        '.pdf': 'application/pdf', '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel', '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.odt': 'application/vnd.oasis.opendocument.text', '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
        '.odp': 'application/vnd.oasis.opendocument.presentation', '.txt': 'text/plain', '.csv': 'text/csv', '.rtf': 'application/rtf',
    }),
    'archives': ('Archiwa', {'.zip': 'application/zip', '.rar': 'application/vnd.rar', '.7z': 'application/x-7z-compressed', '.tar': 'application/x-tar', '.gz': 'application/gzip'}),
}
DEFAULT_FILE_CATEGORIES = ['videos', 'images', 'documents']
FILE_TYPES = {extension: mime for _, types in FILE_CATEGORIES.values() for extension, mime in types.items()}


def categories_for(field):
    if isinstance(field, dict):
        return field.get('accepted_types', DEFAULT_FILE_CATEGORIES)
    return field.accepted_types


def allowed_extensions(categories):
    return {extension for category in categories for extension in FILE_CATEGORIES[category][1]}


def file_accept(field):
    return ','.join(sorted(allowed_extensions(categories_for(field))))


def file_category_labels(field):
    return ', '.join(FILE_CATEGORIES[category][0].lower() for category in categories_for(field))
