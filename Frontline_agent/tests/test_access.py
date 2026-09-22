"""Who may call what: the subscription gate, roles, and rate-limit wiring
(FL-SEC-6, -7, -11, -14)."""
from django.test import override_settings

from api.views import frontline_agent as views
from core.models import CompanyModulePurchase

from .base import FrontlineTestCase


def throttles(view):
    return [cls.__name__ for cls in getattr(view, 'cls', view).throttle_classes]


class ModuleGateTests(FrontlineTestCase):
    """FL-SEC-6 — the /api/v1/ mirror used to skip the subscription gate."""

    def test_legacy_url_is_gated(self):
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        code, _ = self.send(self.http(self.admin), 'get', '/api/frontline/tickets/')
        self.assertEqual(code, 403)

    def test_v1_mirror_is_gated_too(self):
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        code, _ = self.send(self.http(self.admin), 'get', '/api/v1/frontline/tickets/')
        self.assertEqual(code, 403)

    def test_v1_mirror_works_with_the_module(self):
        code, _ = self.send(self.http(self.admin), 'get', '/api/v1/frontline/tickets/')
        self.assertEqual(code, 200)

    def test_module_gate_maps_versioned_paths(self):
        from api.middleware.module_access import ModuleAccessMiddleware
        self.assertEqual(
            ModuleAccessMiddleware._module_for('/api/v1/frontline/tickets/'), 'frontline_agent')
        self.assertEqual(
            ModuleAccessMiddleware._module_for('/api/frontline/tickets/'), 'frontline_agent')


class AdminOnlyEndpointTests(FrontlineTestCase):
    """FL-SEC-7 — credential and destructive endpoints are admin-only."""

    ADMIN_ONLY = [
        ('patch', '/api/frontline/crm/hubspot/config/', {'enabled': False}),
        ('get', '/api/frontline/audit-log/', None),
        ('get', '/api/frontline/analytics/export/', None),
    ]

    def test_member_is_refused(self):
        client = self.http(self.member)
        for method, url, payload in self.ADMIN_ONLY:
            with self.subTest(url=url):
                code, _ = self.send(client, method, url, payload)
                self.assertEqual(code, 403)

    def test_admin_is_allowed(self):
        client = self.http(self.admin)
        for method, url, payload in self.ADMIN_ONLY:
            with self.subTest(url=url):
                code, _ = self.send(client, method, url, payload)
                self.assertNotEqual(code, 403)

    def test_everyday_endpoints_stay_open_to_members(self):
        code, _ = self.send(self.http(self.member), 'get', '/api/frontline/tickets/')
        self.assertEqual(code, 200)

    def test_hubspot_token_is_never_returned_in_full(self):
        client = self.http(self.admin)
        code, _ = self.send(client, 'patch', '/api/frontline/crm/hubspot/config/',
                            {'access_token': 'pat-test-0123456789abcdef'})
        self.assertEqual(code, 200)
        code, body = self.send(client, 'get', '/api/frontline/crm/hubspot/status/')
        self.assertEqual(code, 200)
        self.assertTrue(body['data']['has_token'])
        self.assertNotIn('pat-test-0123456789abcdef', str(body))

    def test_hubspot_token_is_encrypted_at_rest(self):
        """FL-SEC-5 — the raw token must not sit in the database."""
        code, _ = self.send(self.http(self.admin), 'patch',
                            '/api/frontline/crm/hubspot/config/',
                            {'access_token': 'pat-test-0123456789abcdef'})
        self.assertEqual(code, 200)
        self.company.refresh_from_db()
        stored = self.company.hubspot_config.get('access_token')
        self.assertTrue(stored)
        self.assertNotEqual(stored, 'pat-test-0123456789abcdef')
        from Frontline_agent.crm.hubspot import decrypt_access_token
        self.assertEqual(decrypt_access_token(stored), 'pat-test-0123456789abcdef')


class ThrottleWiringTests(FrontlineTestCase):
    """FL-SEC-11 — every LLM endpoint is billable, so none may be unlimited."""

    def test_llm_endpoints_are_throttled(self):
        for name in ('knowledge_qa', 'search_knowledge', 'suggest_ticket_reply',
                     'retriage_ticket', 'summarize_document', 'extract_document',
                     'frontline_nl_analytics', 'frontline_generate_graph'):
            with self.subTest(endpoint=name):
                self.assertIn('FrontlineLLMThrottle', throttles(getattr(views, name)))

    def test_streaming_has_its_own_tighter_budget(self):
        self.assertIn('FrontlineStreamThrottle', throttles(views.knowledge_qa_stream))

    def test_public_endpoints_are_throttled_by_ip_and_widget_key(self):
        for name in ('public_qa', 'public_submit', 'public_widget_config',
                     'submit_satisfaction', 'inbound_email_webhook'):
            with self.subTest(endpoint=name):
                applied = throttles(getattr(views, name))
                self.assertIn('FrontlinePublicThrottle', applied)
                self.assertIn('FrontlineWidgetKeyThrottle', applied)


class InboundWebhookSignatureTests(FrontlineTestCase):
    """FL-SEC-14 — DEBUG alone must not make the webhook accept anything."""

    @override_settings(DEBUG=True, FRONTLINE_INBOUND_SHARED_SECRET='')
    def test_debug_alone_does_not_authenticate(self):
        from Frontline_agent.inbound_email import verify_signature

        class _Req:
            META = {}
            headers = {}
        self.assertFalse(verify_signature('generic', _Req()))

    @override_settings(DEBUG=True, FRONTLINE_INBOUND_SHARED_SECRET='',
                       FRONTLINE_INBOUND_ALLOW_UNSIGNED=True)
    def test_explicit_opt_in_allows_unsigned_locally(self):
        from Frontline_agent.inbound_email import verify_signature

        class _Req:
            META = {}
            headers = {}
        self.assertTrue(verify_signature('generic', _Req()))

    @override_settings(DEBUG=False, FRONTLINE_INBOUND_SHARED_SECRET='s3cret')
    def test_matching_secret_authenticates(self):
        from Frontline_agent.inbound_email import verify_signature

        class _Req:
            META = {'HTTP_X_FRONTLINE_SIGNATURE': 's3cret'}
            headers = {}
        self.assertTrue(verify_signature('generic', _Req()))

    @override_settings(DEBUG=False, FRONTLINE_INBOUND_SHARED_SECRET='s3cret')
    def test_wrong_secret_is_refused(self):
        from Frontline_agent.inbound_email import verify_signature

        class _Req:
            META = {'HTTP_X_FRONTLINE_SIGNATURE': 'nope'}
            headers = {}
        self.assertFalse(verify_signature('generic', _Req()))


class OutboundUrlValidationTests(FrontlineTestCase):
    """FL-SEC-8 — workflow webhook steps must not be an SSRF primitive."""

    @override_settings(DEBUG=False)
    def test_internal_addresses_are_refused(self):
        for url in ('http://127.0.0.1:8000/admin', 'http://169.254.169.254/latest/meta-data',
                    'http://10.0.0.5/internal', 'file:///etc/passwd'):
            with self.subTest(url=url):
                clean, err = views._validate_outbound_url(url)
                self.assertIsNone(clean)
                self.assertTrue(err)

    @override_settings(DEBUG=False)
    def test_a_public_https_url_is_accepted(self):
        clean, err = views._validate_outbound_url('https://example.com/hook')
        # Either accepted, or refused only because DNS didn't resolve in CI.
        if err:
            self.assertIn('resolve', err)
        else:
            self.assertEqual(clean, 'https://example.com/hook')
