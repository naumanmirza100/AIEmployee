"""Tests for ModuleAccessMiddleware — the server-side subscription guard.

Deliberately DB-free: `_resolve_company` and `_has_module` are patched out so the
routing and decision logic can be exercised without a test database (this project
points at a live SQL Server, and spinning up `test_<db>` is neither cheap nor safe).

What these lock down is the part that silently rots: which URLs are gated. A
regression here doesn't raise — it just quietly stops enforcing, which is the exact
failure mode the middleware exists to prevent.

Run:  venv/Scripts/python.exe -m pytest api/tests_module_access.py -q
  or: venv/Scripts/python.exe api/tests_module_access.py
"""
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')

import django  # noqa: E402
from django.conf import settings  # noqa: E402

if not settings.configured or not hasattr(django, 'apps') or not django.apps.apps.ready:
    django.setup()

from api.middleware.module_access import ModuleAccessMiddleware, PREFIX_TO_MODULE  # noqa: E402


def _request(path, method='GET'):
    r = types.SimpleNamespace()
    r.path = path
    r.method = method
    r.META = {}
    r.user = None
    return r


class ModuleForPathTests(unittest.TestCase):
    """`_module_for` decides what is gated. It is the whole blast radius."""

    def test_every_agent_prefix_is_gated(self):
        for prefix, module in PREFIX_TO_MODULE.items():
            self.assertEqual(
                ModuleAccessMiddleware._module_for(f'/api/{prefix}/anything/here'),
                module,
                f'{prefix} should gate to {module}',
            )

    def test_non_api_paths_ignored(self):
        for path in ('/admin/', '/static/x.js', '/hr/tickets', '/'):
            self.assertIsNone(ModuleAccessMiddleware._module_for(path))

    def test_ungated_api_prefixes_pass(self):
        # Platform routes that are not agent-specific must never be gated.
        for path in ('/api/company/profile', '/api/agents', '/api/modules/prices',
                     '/api/auth/login', '/api/projects/1'):
            self.assertIsNone(ModuleAccessMiddleware._module_for(path))

    def test_buy_back_routes_stay_reachable(self):
        """A lapsed company must still be able to see pricing and resubscribe.

        Gating these would trap the customer: they cannot use the agent, and cannot
        reach the endpoints that would let them pay to fix that.
        """
        for path in ('/api/hr/access', '/api/hr/plans', '/api/marketing/prices',
                     '/api/frontline/access/'):
            self.assertIsNone(
                ModuleAccessMiddleware._module_for(path),
                f'{path} must stay reachable without a subscription',
            )

    def test_prefix_must_match_whole_segment(self):
        """'/api/hrmagic' must not be gated by the 'hr' prefix."""
        self.assertIsNone(ModuleAccessMiddleware._module_for('/api/hrmagic/x'))
        self.assertIsNone(ModuleAccessMiddleware._module_for('/api/marketingxyz/x'))


class EnforcementTests(unittest.TestCase):
    """The allow/deny decision, with company resolution stubbed."""

    def setUp(self):
        self.downstream_called = False

        def downstream(request):
            self.downstream_called = True
            return 'PASSED_THROUGH'

        self.mw = ModuleAccessMiddleware(downstream)
        self.company = types.SimpleNamespace(id=7, name='Acme')

    def _run(self, path, company, has_module):
        with mock.patch.object(ModuleAccessMiddleware, '_resolve_company',
                               staticmethod(lambda req: company)), \
             mock.patch.object(ModuleAccessMiddleware, '_has_module',
                               staticmethod(lambda c, m: has_module)):
            return self.mw(_request(path))

    def test_blocks_when_no_active_subscription(self):
        resp = self._run('/api/hr/employees', self.company, has_module=False)
        self.assertFalse(self.downstream_called, 'view must not run')
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b'subscription_required', resp.content)

    def test_allows_when_subscribed(self):
        resp = self._run('/api/hr/employees', self.company, has_module=True)
        self.assertTrue(self.downstream_called)
        self.assertEqual(resp, 'PASSED_THROUGH')

    def test_falls_open_when_company_unresolved(self):
        """Anonymous / staff / non-company callers are someone else's problem.

        This layer only answers "has this company paid"; auth is enforced by DRF
        immediately after, so falling open here does not expose anything.
        """
        resp = self._run('/api/hr/employees', None, has_module=False)
        self.assertTrue(self.downstream_called)
        self.assertEqual(resp, 'PASSED_THROUGH')

    def test_ungated_route_never_blocked(self):
        resp = self._run('/api/company/profile', self.company, has_module=False)
        self.assertTrue(self.downstream_called)

    def test_all_ten_agents_block_without_subscription(self):
        for prefix in PREFIX_TO_MODULE:
            self.downstream_called = False
            resp = self._run(f'/api/{prefix}/some/endpoint', self.company, has_module=False)
            self.assertEqual(resp.status_code, 403, f'{prefix} should have been blocked')
            self.assertFalse(self.downstream_called, f'{prefix} view ran despite no subscription')


if __name__ == '__main__':
    unittest.main(verbosity=2)
