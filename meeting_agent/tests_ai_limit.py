"""Looking at things in Executive Meeting does not use up its AI allowance.

Reading a meeting's stored notes shared an address, and so a limit, with writing them
(30 an hour), and the overview asked the AI for a new digest every time it opened.
After a morning of ordinary use the AI stopped, and stored notes showed as missing.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

import project_manager_ai.settings as base_settings
from api.views import meeting_agent as views
from core.models import Company, CompanyUser


class ExecAILimitTests(TestCase):

    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.hamza = CompanyUser.objects.create(company=company, email='hamza@test.local', full_name='Hamza',
                                                role='owner', password_hash='x', is_active=True)

    def request(self, method, data=None):
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=self.hamza)
        request.user = self.hamza
        return views.meeting_notes.cls().initialize_request(request)

    def counted(self, throttle, method, data=None):
        return throttle().get_cache_key(self.request(method, data), None) is not None

    def test_reading_notes_counts_as_an_ordinary_call_and_writing_them_as_ai(self):
        throttles = views.meeting_notes.cls.throttle_classes
        self.assertEqual(throttles, [views.ExecLLMWhenWritingThrottle, views.ExecCRUDWhenReadingThrottle])
        self.assertFalse(self.counted(views.ExecLLMWhenWritingThrottle, 'get'))
        self.assertTrue(self.counted(views.ExecCRUDWhenReadingThrottle, 'get'))
        self.assertTrue(self.counted(views.ExecLLMWhenWritingThrottle, 'post'))
        self.assertFalse(self.counted(views.ExecCRUDWhenReadingThrottle, 'post'))

    def test_the_ordinary_limit_matches_project_manager(self):
        rates = base_settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        self.assertEqual(rates['exec_crud'], rates['pm_crud'])

    def digest(self, refresh=None):
        data = {} if refresh is None else {'refresh': refresh}
        request = self.factory.post('/', data, format='json')
        force_authenticate(request, user=self.hamza)
        response = views.notification_daily_digest(request)
        response.render()
        return json.loads(response.content)['digest']

    def test_the_digest_is_made_once_a_day_and_again_only_when_asked(self):
        agent = mock.Mock()
        agent.generate_daily_digest.side_effect = [{'summary': 'First'}, {'summary': 'Second'}]
        with mock.patch.object(views, '_get_agent', return_value=agent):
            first = self.digest()
            again = self.digest()
            self.assertEqual(agent.generate_daily_digest.call_count, 1)
            self.assertEqual(again, first)
            self.assertIn('made_at', first)
            fresh = self.digest(refresh=True)
        self.assertEqual(agent.generate_daily_digest.call_count, 2)
        self.assertEqual(fresh['summary'], 'Second')

    def test_a_kept_digest_costs_nothing_from_the_ai_allowance(self):
        def key(data):
            request = self.factory.post('/', data, format='json')
            force_authenticate(request, user=self.hamza)
            request = views.notification_daily_digest.cls().initialize_request(request)
            request.user = self.hamza
            return views.ExecDigestThrottle().get_cache_key(request, None)
        self.assertIsNotNone(key({}))                     # nothing kept yet: the AI will be asked
        cache.set(views._digest_key(self.hamza), {'summary': 'Kept'})
        self.assertIsNone(key({}))
        self.assertIsNotNone(key({'refresh': True}))      # a new one asked for is counted
