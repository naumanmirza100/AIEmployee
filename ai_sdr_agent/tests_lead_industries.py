"""Lead industries: a lead's company_industry is its one industry, and the Leads tab filters on it. There used to be
a separate category as well, mostly a copy of the industry; migration 0036 kept what only the category knew before
0037 removed it. The endpoints (list, filter, rename, bulk set, CSV fill) are tested in tests_api_leads; this file
also keeps the list's other filters, its counts and the export, which came with the categories' tests."""
import csv
import io
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import SDRIcpProfile, SDRLead
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views

BEFORE = [('ai_sdr_agent', '0035_lead_categories')]
AFTER = [('ai_sdr_agent', '0037_remove_lead_categories')]


class CategoriesBecomeIndustriesMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(executor_leaf_nodes())

    def test_a_leads_category_fills_its_industry_only_when_it_has_none(self):
        apps = self.migrate(BEFORE)
        Company = apps.get_model('core', 'Company')
        CompanyUser = apps.get_model('core', 'CompanyUser')
        Category = apps.get_model('ai_sdr_agent', 'SDRLeadCategory')
        Lead = apps.get_model('ai_sdr_agent', 'SDRLead')
        company = Company.objects.create(name='Acme', email='acme@test.local')
        cu = CompanyUser.objects.create(company=company, email='cu@test.local', full_name='CU', role='admin',
                                        password_hash='x', is_active=True)
        dentistry = Category.objects.create(company_user=cu, name='Dentistry')
        blank = Lead.objects.create(company_user=cu, email='a@x.example', category=dentistry)
        own = Lead.objects.create(company_user=cu, email='b@x.example', category=dentistry,
                                  company_industry='Medical Practice')
        none = Lead.objects.create(company_user=cu, email='c@x.example')

        Lead = self.migrate(AFTER).get_model('ai_sdr_agent', 'SDRLead')
        got = {l.pk: l.company_industry for l in Lead.objects.filter(pk__in=[blank.pk, own.pk, none.pk])}
        self.assertEqual(got, {blank.pk: 'Dentistry', own.pk: 'Medical Practice', none.pk: ''})


def executor_leaf_nodes():
    """Every app's latest migration: where the test database is left for the tests after this one."""
    executor = MigrationExecutor(connection)
    return executor.loader.graph.leaf_nodes()


class LeadListTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()
        self.a = self.make_lead('a@x.example', company_industry='Dentistry')
        self.b = self.make_lead('b@x.example', company_industry='Education')
        self.c = self.make_lead('c@x.example', source='csv_import')

    def call(self, view, method, path='/x', **kw):
        req = getattr(self.rf, method)(path, {}, format='json')
        force_authenticate(req, user=self.cu)
        return view(req, **kw)

    def listed(self, query):
        return {l['email'] for l in self.call(views.leads_list, 'get', path=f'/x?{query}').data['data']}

    def test_the_list_filters_by_enrichment(self):
        SDRLead.objects.filter(pk=self.a.pk).update(enrichment_status='done')
        SDRLead.objects.filter(pk=self.b.pk).update(enrichment_status='pending')
        # Enriched before the field existed: only raw_data says so.
        self.make_lead('old@x.example', raw_data={'enrichment': {'status': 'completed'}})
        self.make_lead('bad@x.example', enrichment_status='failed')
        self.assertEqual(self.listed('enrichment=done'), {'a@x.example', 'old@x.example'})
        self.assertEqual(self.listed('enrichment=not'), {'c@x.example'})
        self.assertEqual(self.listed('enrichment=in_progress'), {'b@x.example'})
        self.assertEqual(self.listed('enrichment=failed'), {'bad@x.example'})
        self.assertEqual(self.listed('enrichment=done&industry=dentistry'), {'a@x.example'})

    def test_export_has_the_industry_and_follows_the_filter(self):
        r = self.call(views.sdr_leads_export, 'get', path='/x?industry=Education')
        rows = list(csv.reader(io.StringIO(b''.join(r.streaming_content).decode())))
        self.assertIn('Industry', rows[0])
        self.assertNotIn('Industry Category', rows[0])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index('Industry')], 'Education')

    def test_qualifying_one_lead_takes_it_out_of_the_queue_and_clears_an_old_failure(self):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['Owner'])
        lead = self.make_lead('f@x.example', qualification_status='failed', qualification_attempts=3,
                              qualification_error='No active ICP profile - set one up, then qualify again.')
        agent = mock.Mock()
        agent.qualify_lead.return_value = {'score': 82, 'temperature': 'hot'}
        with mock.patch.object(views, '_get_qualification_agent', return_value=agent):
            r = self.call(views.qualify_lead, 'post', lead_id=lead.id)
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.score, lead.qualification_status, lead.qualification_error), (82, 'done', ''))

    def test_qualify_more_counts_unscored_leads_the_queue_will_not_pick_up(self):
        SDRLead.objects.all().delete()
        self.make_lead('new@x.example')                                         # never queued
        self.make_lead('failed@x.example', qualification_status='failed')        # gave up
        self.make_lead('queued@x.example', qualification_status='pending')       # the queue has it
        self.make_lead('running@x.example', qualification_status='processing')
        self.make_lead('scored@x.example', score=70)
        stats = views._lead_stats(self.cu)
        self.assertEqual((stats['unqueued'], stats['qualifying'], stats['unscored']), (2, 2, 4))
