"""Lead categories: leads from a dentistry search and an education search landed in one list with nothing to tell
them apart. Each lead is now filed under the industry it was gathered for, taken from the data (no fixed list), and
the list can be filtered, re-filed and exported by it."""
import csv
import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import tasks
from ai_sdr_agent.categories import industry_for_lead
from ai_sdr_agent.models import SDRAgentSettings, SDRIcpProfile, SDRLead, SDRLeadCategory, SDRLeadResearchJob
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views


class IndustryForLeadTests(SDRBase):
    def test_one_searched_industry_files_every_lead_under_it(self):
        self.assertEqual(industry_for_lead(['Educational Institutes'], 'Higher Education'), 'Educational Institutes')
        self.assertEqual(industry_for_lead(['Dentistry'], ''), 'Dentistry')

    def test_several_searched_industries_pick_the_one_the_company_matches(self):
        self.assertEqual(industry_for_lead(['Dentistry', 'Education'], 'Education Management'), 'Education')
        self.assertEqual(industry_for_lead(['Dentistry', 'Education'], 'dentistry'), 'Dentistry')

    def test_no_match_falls_back_to_the_leads_own_industry(self):
        self.assertEqual(industry_for_lead(['Dentistry', 'Education'], 'Real Estate'), 'Real Estate')
        self.assertEqual(industry_for_lead(None, '  Real   Estate '), 'Real Estate')

    def test_nothing_to_go_by_is_no_category(self):
        self.assertEqual(industry_for_lead([], ''), '')


class CategoryApiBase(SDRBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()

    def call(self, view, method, path='/x', data=None, fmt='json', user=None, **kw):
        req = getattr(self.rf, method)(path, data or {}, format=fmt)
        force_authenticate(req, user=user or self.cu)
        return view(req, **kw)

    def other_user(self):
        """A second login with its own leads and categories."""
        from core.models import CompanyUser
        return CompanyUser.objects.create(company=self.company, email='o@test.local', full_name='O',
                                          role='admin', password_hash='x', is_active=True)


class CreatingLeadsFilesThemTests(CategoryApiBase):
    def test_a_hand_added_lead_takes_the_picked_category_or_a_new_name(self):
        dent = SDRLeadCategory.objects.create(company_user=self.cu, name='Dentistry')
        r = self.call(views.leads_list, 'post', data={'full_name': 'A', 'email': 'a@x.example', 'category': dent.id})
        self.assertEqual(r.data['data']['category'], 'Dentistry')
        r = self.call(views.leads_list, 'post', data={'full_name': 'B', 'email': 'b@x.example', 'category': 'Law Firms'})
        self.assertEqual(r.data['data']['category'], 'Law Firms')
        self.assertTrue(SDRLeadCategory.objects.filter(company_user=self.cu, name='Law Firms').exists())

    def test_a_hand_added_lead_with_no_pick_goes_under_its_industry(self):
        SDRLeadCategory.objects.create(company_user=self.cu, name='Dentistry')
        r = self.call(views.leads_list, 'post',
                      data={'full_name': 'C', 'email': 'c@x.example', 'company_industry': 'dentistry'})
        self.assertEqual(r.data['data']['category'], 'Dentistry')   # matched, not a second "dentistry"
        self.assertEqual(SDRLeadCategory.objects.filter(company_user=self.cu).count(), 1)

    def test_another_users_category_id_is_refused(self):
        theirs = SDRLeadCategory.objects.create(company_user=self.other_user(), name='Theirs')
        r = self.call(views.leads_list, 'post', data={'full_name': 'D', 'email': 'd@x.example', 'category': theirs.id})
        self.assertEqual(r.status_code, 400)

    def csv_file(self, rows):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['Full Name', 'Email', 'Industry'])
        w.writerows(rows)
        return SimpleUploadedFile('leads.csv', buf.getvalue().encode(), content_type='text/csv')

    def test_a_csv_row_goes_under_its_industry_column(self):
        f = self.csv_file([['A', 'a@x.example', 'Dentistry'], ['B', 'b@x.example', 'Education'], ['C', 'c@x.example', '']])
        self.call(views.import_leads_csv, 'post', data={'file': f}, fmt='multipart')
        got = {l.email: (l.category.name if l.category else None) for l in SDRLead.objects.all()}
        self.assertEqual(got, {'a@x.example': 'Dentistry', 'b@x.example': 'Education', 'c@x.example': None})

    def test_a_category_picked_for_the_import_wins(self):
        f = self.csv_file([['A', 'a@x.example', 'Dentistry'], ['B', 'b@x.example', '']])
        self.call(views.import_leads_csv, 'post', data={'file': f, 'category': 'UK Dentists'}, fmt='multipart')
        self.assertEqual(set(SDRLead.objects.values_list('category__name', flat=True)), {'UK Dentists'})

    def test_a_search_files_its_leads_under_the_industry_searched_for(self):
        icp = SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, industries=['Educational Institutes'])
        job = SDRLeadResearchJob.objects.create(company_user=self.cu, icp_profile=icp, status='running',
                                                search_params={'count': 5, 'source': 'apify'})
        agent = mock.Mock(source_label='apify')
        agent.search_leads.return_value = [
            {'full_name': 'P One', 'email': 'p1@school.example', 'company_name': 'School 1',
             'company_industry': 'Primary/Secondary Education'},
            {'full_name': 'P Two', 'email': 'p2@school.example', 'company_name': 'School 2'},
        ]
        with mock.patch.object(views, '_get_research_agent', return_value=agent):
            views._execute_research_job(job.id)
        self.assertEqual(set(SDRLead.objects.values_list('category__name', flat=True)), {'Educational Institutes'})

    @override_settings(APIFY_API_TOKEN='tok')
    def test_the_daily_auto_research_files_its_leads_under_the_icp_industry(self):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, industries=['Dentistry'], job_titles=['Owner'])
        found = [{'full_name': 'Ann Lee', 'first_name': 'Ann', 'last_name': 'Lee', 'email': 'ann@smile.example',
                  'job_title': 'Owner', 'company_name': 'Smile Co', 'company_industry': 'Health, Wellness & Fitness'}]
        with mock.patch('ai_sdr_agent.agents.lead_research_agent.LeadResearchAgent.search_leads', return_value=found):
            tasks.auto_research_leads_impl(leads_per_run=5)
        self.assertEqual(SDRLead.objects.get(email='ann@smile.example').category.name, 'Dentistry')

    def fetch_from_apify(self, data):
        SDRAgentSettings.objects.update_or_create(company_user=self.cu, defaults={'apify_api_token': 'own-tok'})
        agent = mock.Mock()
        agent.fetch_apify_runs.return_value = [
            {'full_name': 'Ann Lee', 'email': 'ann@smile.example', 'company_name': 'Smile Co', 'company_industry': 'Dentistry'},
            {'full_name': 'Bo Ray', 'email': 'bo@school.example', 'company_name': 'School', 'company_industry': 'Education'},
        ]
        with mock.patch.object(views, '_get_research_agent', return_value=agent):
            r = self.call(views.fetch_apify_leads, 'post', data=data)
        self.assertEqual(r.status_code, 200, r.data)
        return {l.email: l.category.name for l in SDRLead.objects.select_related('category')}

    def test_an_apify_import_files_each_lead_under_its_industry(self):
        self.assertEqual(self.fetch_from_apify({}), {'ann@smile.example': 'Dentistry', 'bo@school.example': 'Education'})

    def test_a_category_picked_for_the_apify_import_wins(self):
        self.assertEqual(set(self.fetch_from_apify({'category': 'Apify Batch 1'}).values()), {'Apify Batch 1'})


class OneLeadTests(CategoryApiBase):
    def test_the_detail_panel_sets_changes_and_clears_a_category(self):
        lead = self.make_lead('a@x.example')
        dent = SDRLeadCategory.objects.create(company_user=self.cu, name='Dentistry')
        r = self.call(views.lead_detail, 'put', data={'category': dent.id}, lead_id=lead.id)
        self.assertEqual(r.data['data']['category'], 'Dentistry')
        r = self.call(views.lead_detail, 'put', data={'category': 'Orthodontists'}, lead_id=lead.id)   # a new one
        self.assertEqual(r.data['data']['category'], 'Orthodontists')
        r = self.call(views.lead_detail, 'put', data={'category': None}, lead_id=lead.id)
        self.assertEqual((r.data['data']['category'], r.data['data']['category_id']), ('', None))

    def test_the_detail_panel_refuses_another_accounts_category(self):
        lead = self.make_lead('a@x.example')
        theirs = SDRLeadCategory.objects.create(company_user=self.other_user(), name='Theirs')
        r = self.call(views.lead_detail, 'put', data={'category': theirs.id}, lead_id=lead.id)
        self.assertEqual(r.status_code, 400)
        lead.refresh_from_db()
        self.assertIsNone(lead.category)

    def test_qualifying_one_lead_takes_it_out_of_the_queue_and_clears_an_old_failure(self):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['Owner'])
        lead = self.make_lead('a@x.example', qualification_status='failed', qualification_attempts=3,
                              qualification_error='No active ICP profile - set one up, then qualify again.')
        agent = mock.Mock()
        agent.qualify_lead.return_value = {'score': 82, 'temperature': 'hot'}
        with mock.patch.object(views, '_get_qualification_agent', return_value=agent):
            r = self.call(views.qualify_lead, 'post', lead_id=lead.id)
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.score, lead.qualification_status, lead.qualification_error), (82, 'done', ''))

    def test_qualify_more_counts_unscored_leads_the_queue_will_not_pick_up(self):
        self.make_lead('new@x.example')                                         # never queued
        self.make_lead('failed@x.example', qualification_status='failed')        # gave up
        self.make_lead('queued@x.example', qualification_status='pending')       # the queue has it
        self.make_lead('running@x.example', qualification_status='processing')
        self.make_lead('scored@x.example', score=70)
        stats = views._lead_stats(self.cu)
        self.assertEqual((stats['unqueued'], stats['qualifying'], stats['unscored']), (2, 2, 4))


class FilterRefileAndExportTests(CategoryApiBase):
    def setUp(self):
        super().setUp()
        self.dent = SDRLeadCategory.objects.create(company_user=self.cu, name='Dentistry')
        self.edu = SDRLeadCategory.objects.create(company_user=self.cu, name='Education')
        self.a = self.make_lead('a@x.example', category=self.dent)
        self.b = self.make_lead('b@x.example', category=self.edu)
        self.c = self.make_lead('c@x.example', source='csv_import')

    def listed(self, query):
        return {l['email'] for l in self.call(views.leads_list, 'get', path=f'/x?{query}').data['data']}

    def test_the_list_filters_by_category_or_none(self):
        self.assertEqual(self.listed(f'category={self.dent.id}'), {'a@x.example'})
        self.assertEqual(self.listed('category=none'), {'c@x.example'})
        self.assertEqual(self.listed(''), {'a@x.example', 'b@x.example', 'c@x.example'})

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
        self.assertEqual(self.listed(f'enrichment=done&category={self.dent.id}'), {'a@x.example'})

    def test_categories_come_with_their_lead_counts(self):
        self.make_lead('gone@x.example', category=self.dent).soft_delete()
        r = self.call(views.sdr_lead_categories, 'get')
        self.assertEqual({c['name']: c['lead_count'] for c in r.data['data']}, {'Dentistry': 1, 'Education': 1})
        self.assertEqual(r.data['uncategorized'], 1)

    def test_bulk_refile_by_ids(self):
        r = self.call(views.sdr_bulk_set_category, 'post', data={'ids': [self.a.id, self.c.id], 'category': self.edu.id})
        self.assertEqual(r.data['updated'], 2)
        self.c.refresh_from_db()
        self.assertEqual(self.c.category, self.edu)

    def test_bulk_refile_everything_the_filters_match(self):
        self.call(views.sdr_bulk_set_category, 'post', path='/x?source=csv_import',
                  data={'all_matching': True, 'category': 'Imported Dentists'})
        self.c.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual(self.c.category.name, 'Imported Dentists')
        self.assertEqual(self.a.category, self.dent)   # not matched by the filter, left alone

    def test_bulk_clear(self):
        self.call(views.sdr_bulk_set_category, 'post', data={'ids': [self.a.id], 'category': None})
        self.a.refresh_from_db()
        self.assertIsNone(self.a.category)

    def test_another_account_sees_none_of_these_categories_and_cannot_refile_these_leads(self):
        other = self.other_user()
        r = self.call(views.sdr_lead_categories, 'get', user=other)
        self.assertEqual((r.data['data'], r.data['uncategorized']), ([], 0))
        mine = SDRLeadCategory.objects.create(company_user=other, name='Mine')
        r = self.call(views.sdr_bulk_set_category, 'post', data={'ids': [self.a.id, self.b.id], 'category': mine.id}, user=other)
        self.assertEqual(r.data.get('updated', 0), 0)
        r = self.call(views.sdr_bulk_set_category, 'post', path='/x', data={'all_matching': True, 'category': mine.id}, user=other)
        self.assertEqual(r.data.get('updated', 0), 0)
        self.a.refresh_from_db()
        self.assertEqual(self.a.category, self.dent)
        r = self.call(views.sdr_lead_category_detail, 'delete', category_id=self.dent.id, user=other)
        self.assertEqual(r.status_code, 404)

    def test_rename_refuses_a_name_already_used(self):
        r = self.call(views.sdr_lead_category_detail, 'put', data={'name': 'education'}, category_id=self.dent.id)
        self.assertEqual(r.status_code, 400)
        r = self.call(views.sdr_lead_category_detail, 'put', data={'name': 'Dental Clinics'}, category_id=self.dent.id)
        self.assertEqual(r.data['data']['name'], 'Dental Clinics')

    def test_deleting_a_category_keeps_its_leads(self):
        self.call(views.sdr_lead_category_detail, 'delete', category_id=self.dent.id)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.category)

    def test_export_has_the_category_and_follows_the_filter(self):
        r = self.call(views.sdr_leads_export, 'get', path=f'/x?category={self.edu.id}')
        rows = list(csv.reader(io.StringIO(b''.join(r.streaming_content).decode())))
        self.assertIn('Industry Category', rows[0])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][rows[0].index('Industry Category')], 'Education')
