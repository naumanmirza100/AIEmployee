"""Run the AI SDR's automated tests from the dashboard and see which passed; and, for a company, check its live
AI SDR (sdr/live-checks…, see ai_sdr_agent.live_checks).

Two doors to the same runs:
  admin/sdr-checks…  a platform admin (IsAdmin: staff/superuser), from the Super Admin panel.
  sdr/checks…        a company's owner or admin, from AI SDR → Tests. The module-access middleware already
                     refuses sdr/ to a company without AI SDR.

The tests check the platform's code, not a company's data, so every company sees the same runs; only the name of
whoever started a run is kept to that run's own company. The tests themselves run in a separate process on a
throwaway database; see ai_sdr_agent.admin_checks.
"""
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ai_sdr_agent import admin_checks, live_checks
from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsAdmin, IsCompanyAdmin, IsCompanyUserOnly


def _as_seen_by(run, company_id):
    """A run as one company may see it: another company's person is not named. None sees everything."""
    if company_id is None or run.get('company_id') == company_id:
        return run
    return {**run, 'started_by': None}


def _overview(company_id):
    runs = [_as_seen_by(r, company_id) for r in admin_checks.list_runs()]
    latest = admin_checks.latest_by_suite(runs)
    current = admin_checks.current_run(runs)
    all_runs = [r for r in runs if r['suite'] == 'all' and r['status'] in admin_checks.FINISHED]
    return Response({
        'status': 'success',
        'data': {
            'suites': [{'key': s['key'], 'title': s['title'], 'description': s['description'],
                        'last': latest.get(s['key'])} for s in admin_checks.SUITES],
            'all_last': admin_checks.summary(all_runs[0]) if all_runs else None,
            'current': admin_checks.summary(current) if current else None,
            'runs': [admin_checks.summary(r) for r in runs[:20]],
        },
    })


def _start(request, started_by, company_id):
    key = (request.data.get('suite') or '').strip()
    if key not in admin_checks.SUITES_BY_KEY:
        return Response({'status': 'error', 'message': 'Unknown test suite.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        run = admin_checks.start_run(key, started_by, company_id)
    except admin_checks.AlreadyRunning as busy:
        return Response({'status': 'error', 'message': f"'{busy.run['suite_title']}' is still running.",
                         'data': admin_checks.summary(_as_seen_by(busy.run, company_id))},
                        status=status.HTTP_409_CONFLICT)
    return Response({'status': 'success', 'data': admin_checks.summary(run)}, status=status.HTTP_202_ACCEPTED)


def _detail(request, run_id, company_id):
    try:
        run = admin_checks.get_run(run_id)
    except ValueError:
        run = None
    if run is None:
        return Response({'status': 'error', 'message': 'Run not found.'}, status=status.HTTP_404_NOT_FOUND)
    run = _as_seen_by(run, company_id)
    suite = request.query_params.get('suite')
    if suite not in admin_checks.SUITES_BY_KEY or suite == 'all':
        suite = None
    tests = [t for t in run['tests'] if not suite or run['suite'] == suite or suite in t.get('suites', [])]
    return Response({'status': 'success', 'data': {
        **admin_checks.summary(run, suite), 'tests': tests, 'log_tail': run.get('log_tail'),
    }})


# --- Super Admin panel ------------------------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_overview(request):
    """The parts that can be checked with each one's latest result, the run in progress and the recent runs."""
    return _overview(None)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_start(request):
    """Body: {"suite": "<key>"}, or "all" for every AI SDR test."""
    return _start(request, request.user.get_username(), None)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_run_detail(request, run_id):
    """One run with every test's outcome. ?suite=<key> keeps only the tests of that part."""
    return _detail(request, run_id, None)


# --- A company's owner or admin, AI SDR → Tests ----------------------------------------------------------------

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly, IsCompanyAdmin])
def company_overview(request):
    return _overview(request.user.company_id)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly, IsCompanyAdmin])
def company_start(request):
    return _start(request, request.user.full_name or request.user.email, request.user.company_id)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly, IsCompanyAdmin])
def company_run_detail(request, run_id):
    return _detail(request, run_id, request.user.company_id)


# --- A company's owner or admin, AI SDR → Tests: checks of the live AI SDR (ai_sdr_agent.live_checks) -----------

# A live test spends AI credits or sends email; one press at a time per company and test.
LIVE_COOLDOWN = 20  # seconds


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly, IsCompanyAdmin])
def live_catalog(request):
    """The health checks and live tests, and the campaigns whose mailbox a live test may use."""
    company = request.user.company
    entry = lambda c: {k: c[k] for k in ('key', 'title', 'description') if k in c} | {'needs': c.get('needs', [])}  # noqa: E731
    campaigns = live_checks._mailbox_campaigns(company)
    return Response({'status': 'success', 'data': {
        'health': [entry(c) for c in live_checks.HEALTH],
        'live': [entry(c) for c in live_checks.LIVE],
        'campaigns': [{'id': c.id, 'name': c.name, 'status': c.status, 'from_email': c.from_email or c.smtp_username}
                      for c in campaigns],
        'website': company.website or '',
        'email': request.user.email,
    }})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly, IsCompanyAdmin])
def live_run(request, key):
    """Run one check now. Body: {email?, campaign_id?} for the live tests that need them."""
    if key not in live_checks.CHECKS:
        return Response({'status': 'error', 'message': 'Unknown check.'}, status=status.HTTP_404_NOT_FOUND)
    if key.startswith('live_') and not cache.add(f'sdr-live-check:{request.user.company_id}:{key}', 1, LIVE_COOLDOWN):
        return Response({'status': 'error', 'message': 'This test was just run. Wait a few seconds and try again.'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    params = {k: request.data.get(k) for k in ('email', 'campaign_id')}
    return Response({'status': 'success', 'data': live_checks.run(key, request.user, params)})
