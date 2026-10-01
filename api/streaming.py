"""Answers sent as they are written.

A streaming endpoint returns one JSON object per line (ndjson): the client
reads the body as it arrives and shows each piece of text straight away,
rather than a spinner until the whole answer is done. HR and Frontline
Knowledge Q&A started this; Project Manager and Recruitment Q&A use this
helper for the same wire format.
"""
import json

from django.http import StreamingHttpResponse


def ndjson_response(events):
    """Stream these event dicts, one per line, unbuffered."""
    response = StreamingHttpResponse((json.dumps(e, default=str) + '\n' for e in events),
                                     content_type='application/x-ndjson')
    # Proxies (nginx) would otherwise hold the body until it's complete.
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['X-Accel-Buffering'] = 'no'
    return response
