"""Answers sent as they are written.

A streaming endpoint returns one JSON object per line (ndjson): the client
reads the body as it arrives and shows each piece of text straight away,
rather than a spinner until the whole answer is done. HR and Frontline
Knowledge Q&A started this; Project Manager and Recruitment Q&A use this
helper for the same wire format.
"""
import json

from django.http import StreamingHttpResponse


def error_event(exc):
    """What to send down a stream that is already open when the answer cannot
    be written.

    A key problem (out of AI tokens, a cap reached, the agent switched off, a
    key the provider refused) carries the words meant for the person, in
    `user_message`. Most of these are raised with no arguments, so `str(exc)`
    is empty: the chats were sent an error with no text and showed "(no
    answer)". Anything else gets a plain sentence, never the exception's text.
    """
    from core.api_key_service import KeyServiceError
    if isinstance(exc, KeyServiceError):
        return {'type': 'error', 'message': exc.user_message, 'code': exc.reason}
    return {'type': 'error', 'message': 'Something went wrong while writing the answer. Please try again.'}


def ndjson_response(events):
    """Stream these event dicts, one per line, unbuffered."""
    response = StreamingHttpResponse((json.dumps(e, default=str) + '\n' for e in events),
                                     content_type='application/x-ndjson')
    # Proxies (nginx) would otherwise hold the body until it's complete.
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['X-Accel-Buffering'] = 'no'
    return response
