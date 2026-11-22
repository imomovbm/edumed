"""Turning uploaded bytes into text: detect the encoding, refuse binary files."""
import codecs
import re
import unicodedata

from . import messages as M

# Files teachers sometimes upload by mistake, recognised by their first bytes.
MAGIC = [
    (b'PK\x03\x04', 'Word (.docx), Excel yoki ZIP fayl'),
    (b'%PDF', 'PDF fayl'),
    (b'\xd0\xcf\x11\xe0', 'eski Word (.doc) yoki Excel fayl'),
    (b'{\\rtf', 'RTF fayl'),
    (b'\x89PNG', 'rasm'),
    (b'\xff\xd8\xff', 'rasm'),
    (b'GIF8', 'rasm'),
]
CONTROL_CHARS = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class DecodeError(ValueError):
    pass


def decode(data):
    """Return (text, encoding label) or raise DecodeError with a user-facing message.

    UTF-8 (with or without BOM) and UTF-16 with BOM ("Unicode" in Notepad) are read
    as such; other non-UTF-8 files are read as Windows-1251 (Russian/Uzbek Cyrillic
    on Windows), whose Latin part matches Windows-1252.
    """
    for magic, kind in MAGIC:
        if data.startswith(magic):
            raise DecodeError(M.NOT_TEXT.format(kind=kind))
    try:
        if data.startswith(codecs.BOM_UTF8):
            text, label = data[len(codecs.BOM_UTF8):].decode('utf-8'), 'UTF-8 (BOM)'
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            text, label = data.decode('utf-16'), 'UTF-16'
        elif b'\x00' in data:
            raise DecodeError(M.NOT_TEXT.format(kind='binar fayl'))
        else:
            try:
                text, label = data.decode('utf-8'), 'UTF-8'
            except UnicodeDecodeError:
                text, label = data.decode('cp1251'), 'Windows-1251'
    except UnicodeDecodeError:
        raise DecodeError(M.BAD_ENCODING) from None
    return normalize(text), label


def normalize(text):
    """Unix line ends, NFC letters, no stray BOM or invisible control characters."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff')
    text = CONTROL_CHARS.sub('', text)
    return unicodedata.normalize('NFC', text)
