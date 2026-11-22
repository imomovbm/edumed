"""Reading test files.

    result = parse_file(data, filename)   # bytes of an uploaded file
    result = parse_text(text)             # text edited in the preview page

Both return a :class:`~.base.ParseResult`: the questions plus every problem found
(with question numbers and line numbers). Nothing is skipped silently — the
caller decides; the import page refuses to save while there are errors.

To support another format, write a :class:`~.base.BaseParser` subclass with its
``extensions`` and ``parse_text`` and add an instance to ``PARSERS``.
"""
from pathlib import Path

from . import messages as M
from .base import ERROR, WARNING, ParsedOption, ParsedQuestion, ParseResult, Problem
from .encoding import DecodeError, decode, normalize
from .plain_text import PlainTextParser
from .validation import validate

MAX_FILE_BYTES = 2 * 1024 * 1024

PARSERS = [PlainTextParser()]

__all__ = [
    'ERROR', 'WARNING', 'MAX_FILE_BYTES', 'PARSERS', 'ParsedOption', 'ParsedQuestion', 'ParseResult',
    'Problem', 'accepted_extensions', 'parse_file', 'parse_text',
]


def accepted_extensions():
    return [ext for parser in PARSERS for ext in parser.extensions]


def _parser_for(filename):
    ext = Path(filename or '').suffix.lower()
    return next((p for p in PARSERS if ext in p.extensions), None), ext


def _size(n):
    return f'{n / 1024 / 1024:.1f} MB'.replace('.', ',') if n >= 1024 * 1024 else f'{max(1, n // 1024)} KB'


def _failed(message):
    result = ParseResult()
    result.add(Problem(message))
    return result


def parse_file(data, filename):
    """Read an uploaded test file (``data`` = its bytes). Never raises for bad input."""
    if not filename:
        return _failed(M.NO_FILE)
    parser, ext = _parser_for(filename)
    if parser is None:
        return _failed(M.WRONG_TYPE.format(ext=ext or filename, allowed=', '.join(accepted_extensions())))
    if len(data) > MAX_FILE_BYTES:
        return _failed(M.TOO_LARGE.format(size=_size(len(data)), limit=_size(MAX_FILE_BYTES)))
    if not data.strip():
        return _failed(M.EMPTY_FILE)
    try:
        text, encoding = decode(data)
    except DecodeError as exc:
        return _failed(str(exc))
    result = parse_text(text, parser=parser)
    result.encoding = encoding
    return result


def parse_text(text, parser=None):
    """Parse text that is already decoded (e.g. corrected in the preview editor)."""
    text = normalize(text or '')
    size = len(text.encode('utf-8'))
    if size > MAX_FILE_BYTES:
        return _failed(M.TEXT_TOO_LARGE.format(size=_size(size), limit=_size(MAX_FILE_BYTES)))
    if not text.strip():
        result = _failed(M.EMPTY_FILE)
        result.text = text
        return result
    result = (parser or PARSERS[0]).parse_text(text)
    return validate(result)
