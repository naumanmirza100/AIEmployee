"""Keep the server's own error text out of the API's error replies (CO-271).

Many views answer a failure with the exception's text, as `'error': str(e)` or as the whole
`message`, and some of them need no login. That text can name tables, columns, file paths and
outside services. Django already logs every 5xx reply ("Internal Server Error: ..."), and the
operators are emailed about them; the caller only needs to know it failed.

So for a JSON reply from /api/ with a 5xx status:
- `error`, `detail`, `details`, `traceback` and `exception` are replaced or removed, after the text
  is written to the log;
- `message` is kept when a person wrote it ("Failed to fetch project") and replaced when it is an
  exception's text or carries one, which `_looks_internal` tells by its shape.

4xx replies are left alone: their messages are meant for the person (a wrong field, a missing key).
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

GENERIC = 'Something went wrong on our side. It has been logged; please try again.'
RAW_KEYS = ('error', 'detail', 'details', 'traceback', 'exception')

_INTERNAL = re.compile(
    r'Traceback|File "|\.py\b|/app/|\b[A-Za-z]:\\'                        # stack traces and paths
    r'|\b[A-Z][A-Za-z]*(Error|Exception|DoesNotExist)\b'                  # exception class names
    r'|(?i:object has no attribute|NoneType|not subscriptable|unsupported operand'
    r'|list index out of range|invalid literal for|unexpected keyword argument'
    r'|required positional argument|matching query does not exist|is not JSON serializable'
    r'|Expecting value: line|Errno|Max retries exceeded|HTTPS?ConnectionPool|Connection refused'
    r'|Duplicate entry|foreign key constraint|Unknown column|no such (table|column))'
    r'|\(\d{4}, ["\']'                                                    # a MySQL error tuple
    r'|\bSELECT\b.+\bFROM\b|\bINSERT INTO\b|\bUPDATE\b.+\bSET\b'          # SQL, in capitals only
    r"|^'[\w.]+'$",                                                       # a bare KeyError
    re.DOTALL,
)
# Class names that are ordinary words in a sentence a person wrote, not exception names.
_HARMLESS = re.compile(r'\b(Validation|Permission|Network|Server|Unknown|Internal)\s?(Error)\b')


def _looks_internal(text):
    if not isinstance(text, str) or not text.strip():
        return False
    return bool(_INTERNAL.search(_HARMLESS.sub('', text)))


def clean(body):
    """The reply with server text taken out, and the texts taken out (for the log)."""
    removed = []
    raw_texts = []
    for key in RAW_KEYS:
        if key in body:
            value = body[key]
            if value not in (None, '', [], {}):
                removed.append(f'{key}={value!r}'[:2000])
                if isinstance(value, str):
                    raw_texts.append(value)
            if key == 'error':
                body[key] = GENERIC
            else:
                del body[key]
    message = body.get('message')
    if isinstance(message, str) and (
            _looks_internal(message) or any(raw and raw in message for raw in raw_texts)):
        removed.append(f'message={message!r}'[:2000])
        body['message'] = GENERIC
    return body, removed


class ServerErrorTextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.status_code < 500 or not request.path.startswith('/api/')
                or getattr(response, 'streaming', False)
                or 'json' not in (response.get('Content-Type') or '')):
            return response
        try:
            body = json.loads(response.content.decode(response.charset or 'utf-8'))
        except (ValueError, UnicodeDecodeError):
            return response
        if not isinstance(body, dict):
            return response
        body, removed = clean(body)
        if removed:
            logger.warning('Server error text kept out of the reply to %s %s (%s): %s',
                           request.method, request.path, response.status_code, '; '.join(removed))
            response.content = json.dumps(body).encode('utf-8')
            if response.has_header('Content-Length'):
                response['Content-Length'] = str(len(response.content))
        return response
