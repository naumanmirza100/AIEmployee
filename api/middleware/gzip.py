"""Gzip, except for answers streamed as they are written.

Django's GZipMiddleware compresses a streaming response too, and the
compressor keeps the text until its buffer fills — so a streamed Q&A answer
(HR, Frontline, Project Manager, Recruitment, Operations authoring) reached
the browser all at once, at the end, defeating the point of streaming it.
Measured locally: 49 lines of an answer generated over several seconds all
arrived in the same instant.
"""
from django.middleware.gzip import GZipMiddleware

#: Response types that are read piece by piece as they arrive.
STREAMED_TYPES = ('application/x-ndjson', 'text/event-stream')


class GZipExceptStreamsMiddleware(GZipMiddleware):

    def process_response(self, request, response):
        content_type = (response.get('Content-Type') or '').split(';')[0].strip().lower()
        if response.streaming and content_type in STREAMED_TYPES:
            return response
        return super().process_response(request, response)
