"""Decode and normalize user-provided images before publishing them."""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def normalize_image(data, max_size=2400):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Zdjęcie może mieć maksymalnie 10 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 20_000_000:
                    raise ValueError('Zdjęcie może mieć maksymalnie 20 megapikseli.')
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((max_size, max_size))
                output = BytesIO()
                image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB').save(output, 'WEBP', quality=88)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Wybierz poprawne zdjęcie JPG, PNG lub WebP.') from None
