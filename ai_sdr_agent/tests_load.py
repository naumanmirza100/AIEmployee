"""Load: the AI SDR's busiest screens under many requests at once, and at the size of a real account.

Run on the throwaway test database, never against the live site: what is measured is the code (errors under
concurrent use, how the number of database queries grows with the data, how long bulk work takes), not the live
server's hardware. The limits are generous on purpose, several times what a laptop needs, so a slow machine does not
fail them; a change that makes a screen run one query per lead, or break when used by many at once, does.
"""
import csv
import io
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import LiveServerTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import SDRCampaign, SDRLead
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken

SCREENS = ['/api/sdr/dashboard', '/api/sdr/leads', '/api/sdr/campaigns', '/api/sdr/analytics', '/api/sdr/meetings']


def seed(company_user, leads=300, campaigns=5):
    SDRLead.objects.bulk_create([
        SDRLead(company_user=company_user, email=f'lead{i}@load.test', first_name=f'Lead{i}', full_name=f'Lead {i}',
                company_name=f'Company {i % 40}', job_title='Head of Sales', score=i % 100,
                temperature=('hot', 'warm', 'cold')[i % 3])
        for i in range(leads)])
    for i in range(campaigns):
        SDRCampaign.objects.create(company_user=company_user, name=f'Campaign {i}', status='active')


class ConcurrentRequestsTests(LiveServerTestCase):
    """Many people using the AI SDR at once, through the real server, middleware and sign-in."""

    host = '127.0.0.1'  # 'localhost' tries IPv6 first on Windows and waits 2 s on every request
    USERS, REQUESTS_EACH = 20, 5          # 100 requests, 20 at a time
    SLOWEST_ALLOWED = 5.0                 # seconds, any single request
    MEDIAN_ALLOWED = 1.5                  # seconds

    def setUp(self):
        company = Company.objects.create(name='Load Co', email='load@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='ai_sdr_agent', status='active',
                                             is_complimentary=True)
        self.cu = CompanyUser.objects.create(company=company, email='owner@load.test', full_name='Owner',
                                             role='owner', password_hash='x', is_active=True)
        self.token = CompanyUserToken.objects.create(company_user=self.cu).key
        seed(self.cu)

    def get(self, path):
        started = time.monotonic()
        response = requests.get(self.live_server_url + path, headers={'Authorization': f'Token {self.token}'},
                                timeout=30)
        return path, response.status_code, time.monotonic() - started

    def test_a_hundred_requests_twenty_at_a_time_all_succeed_quickly(self):
        paths = [SCREENS[i % len(SCREENS)] for i in range(self.USERS * self.REQUESTS_EACH)]
        with ThreadPoolExecutor(max_workers=self.USERS) as pool:
            results = list(pool.map(self.get, paths))
        failed = [(p, s) for p, s, _t in results if s != 200]
        self.assertEqual(failed, [], 'requests that did not answer 200')
        times = [t for _p, _s, t in results]
        self.assertLess(max(times), self.SLOWEST_ALLOWED)
        self.assertLess(statistics.median(times), self.MEDIAN_ALLOWED)



class QueryGrowthTests(SDRBase):
    """A screen asks the database the same number of questions for 300 leads as for 30: one query per lead is
    what makes a page fine in a demo and unusable for a real account."""

    SMALL, LARGE = 30, 300
    EXTRA_ALLOWED = 5   # a few queries more are noise; one per lead would be 270

    def queries(self, view, path):
        request = APIRequestFactory().get(path)
        force_authenticate(request, user=self.cu)
        with CaptureQueriesContext(connection) as captured:
            response = view(request)
        self.assertEqual(response.status_code, 200)
        return len(captured)

    def growth(self, view, path):
        seed(self.cu, leads=self.SMALL, campaigns=2)
        small = self.queries(view, path)
        seed(self.cu, leads=self.LARGE - self.SMALL, campaigns=0)
        return small, self.queries(view, path)

    def assert_flat(self, view, path):
        small, large = self.growth(view, path)
        self.assertLessEqual(large, small + self.EXTRA_ALLOWED,
                             f'{path}: {small} queries for {self.SMALL} leads, {large} for {self.LARGE}')

    def test_the_leads_list(self):
        self.assert_flat(views.leads_list, '/api/sdr/leads')

    def test_the_dashboard(self):
        self.assert_flat(views.sdr_dashboard, '/api/sdr/dashboard')

    def test_the_campaigns_list(self):
        self.assert_flat(views.sdr_campaigns_list, '/api/sdr/campaigns')

    def test_the_analytics(self):
        self.assert_flat(views.sdr_analytics, '/api/sdr/analytics')

    def test_the_meetings_list(self):
        self.assert_flat(views.sdr_meetings_list, '/api/sdr/meetings')


class BulkWorkTests(SDRBase):
    """The bulk jobs at the size of a real account finish, completely, in reasonable time."""

    ROWS = 1000

    def call(self, view, method, path='/', data=None, fmt=None):
        request = getattr(APIRequestFactory(), method)(path, data or {}, format=fmt)
        force_authenticate(request, user=self.cu)
        return view(request)

    def timed(self, fn):
        started = time.monotonic()
        result = fn()
        return result, time.monotonic() - started

    def test_importing_a_thousand_row_csv(self):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Full Name', 'Email', 'Company', 'Job Title'])
        writer.writerows([f'Person {i}', f'person{i}@import.test', f'Firm {i % 50}', 'CEO'] for i in range(self.ROWS))
        upload = SimpleUploadedFile('leads.csv', buf.getvalue().encode(), content_type='text/csv')
        response, took = self.timed(lambda: self.call(views.import_leads_csv, 'post', data={'file': upload},
                                                      fmt='multipart'))
        self.assertIn(response.status_code, (200, 201))
        self.assertEqual(SDRLead.objects.filter(company_user=self.cu).count(), self.ROWS)
        self.assertLess(took, 60)

    def test_exporting_a_thousand_leads(self):
        seed(self.cu, leads=self.ROWS, campaigns=0)
        response, took = self.timed(lambda: self.call(views.sdr_leads_export, 'get', '/x'))
        rows = list(csv.reader(io.StringIO(b''.join(response.streaming_content).decode('utf-8'))))
        self.assertEqual(len(rows), self.ROWS + 1)  # and the header
        self.assertLess(took, 30)

    def test_deleting_and_restoring_five_hundred_leads(self):
        seed(self.cu, leads=500, campaigns=0)
        ids = list(SDRLead.objects.filter(company_user=self.cu).values_list('id', flat=True))
        response, took = self.timed(lambda: self.call(views.sdr_bulk_delete_leads, 'post', data={'ids': ids},
                                                      fmt='json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SDRLead.objects.filter(company_user=self.cu).count(), 0)
        self.assertLess(took, 30)
        response, took = self.timed(lambda: self.call(views.sdr_bulk_restore_leads, 'post', data={'ids': ids},
                                                      fmt='json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SDRLead.objects.filter(company_user=self.cu).count(), 500)
        self.assertLess(took, 30)
