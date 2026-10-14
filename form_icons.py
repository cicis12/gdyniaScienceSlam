"""Validation shared by the form editor and configuration transfer."""
import xml.etree.ElementTree as ET


def check_svg(svg):
    if not svg or not svg.strip():
        return
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        raise ValueError('Nieprawidłowa ikona SVG formularza.') from None
    if root.tag.split('}')[-1] != 'svg':
        raise ValueError('Ikona musi być plikiem SVG.')
    tags = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'title', 'desc'}
    attrs = {'class', 'viewBox', 'width', 'height', 'fill', 'fill-rule', 'clip-rule', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-miterlimit', 'opacity', 'fill-opacity', 'stroke-opacity', 'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'points', 'transform', 'aria-hidden', 'role', 'focusable'}
    for node in root.iter():
        if node.tag.split('}')[-1] not in tags:
            raise ValueError('Niedozwolony element w ikonie SVG.')
        for key, value in node.attrib.items():
            if key not in attrs or 'url(' in value.lower():
                raise ValueError('Niedozwolony atrybut w ikonie SVG.')

