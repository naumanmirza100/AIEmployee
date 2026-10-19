"""The website chat works on the websites its company lists, and nowhere else.

The chat runs in a frame served from our own site, so its requests carry our
origin, never the website's: with any list of allowed websites set, the chat
was refused on the very site listed. The embed pages now send the origin of
the page they are framed in, and the server takes it from them, and only from
them.
"""
from django.test import Client, override_settings

from .base import FrontlineTestCase

APP = 'https://app.payper.test'
SITE = 'https://crestline.test'


@override_settings(FRONTEND_URL=APP)
class AllowedWebsitesTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.company.frontline_widget_key = 'k-123'
        self.company.frontline_allowed_origins = SITE
        self.company.save()

    def config(self, origin, parent=None):
        url = '/api/frontline/widget/public-config/?widget_key=k-123'
        if parent is not None:
            url += f'&parent_origin={parent}'
        return Client().get(url, HTTP_ORIGIN=origin).status_code

    def test_the_chat_framed_on_a_listed_website_is_served(self):
        self.assertEqual(self.config(APP, SITE), 200)
        self.assertEqual(self.config('https://www.app.payper.test', SITE), 200)    # the embed code's www. address

    def test_framed_on_any_other_website_it_is_refused(self):
        self.assertEqual(self.config(APP, 'https://elsewhere.test'), 403)
        self.assertEqual(self.config(APP, 'unknown'), 403)                          # the browser would not say
        self.assertEqual(self.config(APP), 403)                                     # not in a frame at all

    def test_another_website_cannot_claim_to_be_a_listed_one(self):
        # Only our own embed pages are believed about where they are.
        self.assertEqual(self.config('https://elsewhere.test', SITE), 403)

    def test_a_request_from_the_listed_website_itself_still_works(self):
        self.assertEqual(self.config(SITE), 200)

    def test_with_no_list_any_website_is_served(self):
        self.company.frontline_allowed_origins = ''
        self.company.save()
        self.assertEqual(self.config(APP, 'https://elsewhere.test'), 200)
