"""Lead categories: leads from a dentistry search and an education search landed in one list with nothing to tell
them apart. Each lead is now filed under the industry it was gathered for, taken from the data (no fixed list), and
the list can be filtered, re-filed and exported by it."""
import csv
import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.categories import industry_for_lead
from ai_sdr_agent.models import SDRIcpProfile, SDRLead, SDRLeadCategory, SDRLeadResearchJob
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

    def call(self, view, method, path='/x', data=None, fmt='json', **kw):
        req = getattr(self.rf, method)(path, data or {}, format=fmt)
        force_authenticate(req, user=self.cu)
        return view(req, **kw)


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
        from core.models import CompanyUser
        other = CompanyUser.objects.create(company=self.company, email='o@test.local', full_name='O',
                                           role='admin', password_hash='x', is_active=True)
        theirs = SDRLeadCategory.objects.create(company_user=other, name='Theirs')
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
