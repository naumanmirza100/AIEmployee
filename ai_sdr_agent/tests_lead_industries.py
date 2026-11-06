"""Lead industries: a lead's company_industry is its one industry, and the Leads tab filters on it. There used to be
a separate category as well, mostly a copy of the industry; migration 0036 kept what only the category knew before
0037 removed it. The endpoints (list, filter, rename, bulk set, CSV fill) are tested in tests_api_leads."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('ai_sdr_agent', '0035_lead_categories')]
AFTER = [('ai_sdr_agent', '0037_remove_lead_categories')]


class CategoriesBecomeIndustriesMigrationTests(TransactionTestCase):
    def setUp(self):
        # The test settings (project_manager_ai.settings_test, as GitHub's test job runs them) build the tables without
        # migrations, so there are none to step through: then this test can only skip, and says why.
        loader = MigrationExecutor(connection).loader
        if BEFORE[0] not in loader.graph.nodes:
            self.skipTest('needs migrations, which these settings switch off (MIGRATION_MODULES)')

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
