"""Allow formatted admin copy without executable HTML, CSS, or SVG."""
from functools import lru_cache
import re
import nh3
from markupsafe import Markup

TEXT_TAGS = {'details', 'summary', 'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3',
             'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 's', 'small',
             'span', 'strong', 'sub', 'sup', 'u', 'ul', 'table', 'thead', 'tbody', 'tr', 'th', 'td'}
SVG_TAGS = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'title', 'desc'}
SVG_ATTRS = {'viewBox', 'width', 'height', 'fill', 'fill-rule', 'clip-rule', 'stroke', 'stroke-width',
             'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-dashoffset',
             'stroke-miterlimit', 'opacity', 'fill-opacity', 'stroke-opacity', 'd', 'cx', 'cy',
             'r', 'rx', 'ry', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'points', 'transform', 'focusable'}


def filter_attribute(tag, attr, value):
    if tag in SVG_TAGS and attr in {'fill', 'stroke'}:
        if not re.fullmatch(r'(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]+|rgba?\([0-9.,%\s]+\))', value):
            return None
    if attr == 'class':
        # Tailwind utility names remain available; arbitrary external CSS URLs do not.
        return ' '.join(part for part in value.split() if not any(c in part.lower() for c in ('url(', '\\', 'javascript:')))
    return value


cleaner = nh3.Cleaner(
    tags=TEXT_TAGS | SVG_TAGS,
    clean_content_tags={'script', 'style', 'iframe', 'object', 'embed', 'template', 'math', 'foreignObject'},
    attributes={
        '*': {'class', 'title', 'lang', 'dir', 'role', 'aria-label', 'aria-hidden'},
        'a': {'href', 'target'},
        'img': {'src', 'alt', 'width', 'height', 'loading'},
        'th': {'colspan', 'rowspan', 'scope'}, 'td': {'colspan', 'rowspan'},
        **{tag: SVG_ATTRS for tag in SVG_TAGS},
    },
    attribute_filter=filter_attribute,
    url_schemes={'http', 'https', 'mailto', 'tel'},
    link_rel='noopener noreferrer',
)


@lru_cache(maxsize=256)
def clean_html(value):
    """Return an ordinary string, so Jinja still escapes it in HTML attributes."""
    return cleaner.clean(str(value or ''))


def safe_html(value):
    return Markup(clean_html(value))
