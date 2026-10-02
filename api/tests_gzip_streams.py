"""Streamed answers aren't gzipped; everything else still is.

Django's GZipMiddleware held a streamed answer back until its compressor's
buffer filled, so every "streaming" Q&A answer reached the browser at once.
"""
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory, SimpleTestCase

from api.middleware.gzip import GZipExceptStreamsMiddleware
from api.streaming import ndjson_response


class GZipExceptStreamsTests(SimpleTestCase):

    def run_through(self, response):
        request = RequestFactory().get('/', HTTP_ACCEPT_ENCODING='gzip')
        return GZipExceptStreamsMiddleware(lambda r: response)(request)

    def test_a_streamed_answer_goes_out_as_written(self):
        response = self.run_through(ndjson_response(iter([{'type': 'token', 'value': 'Hi'}])))
        self.assertFalse(response.has_header('Content-Encoding'))
        self.assertEqual(b''.join(response.streaming_content), b'{"type": "token", "value": "Hi"}\n')

    def test_other_responses_are_still_compressed(self):
        self.assertEqual(self.run_through(HttpResponse('x' * 1000))['Content-Encoding'], 'gzip')
        streamed_file = StreamingHttpResponse(iter([b'x' * 1000]), content_type='text/csv')
        self.assertEqual(self.run_through(streamed_file)['Content-Encoding'], 'gzip')
