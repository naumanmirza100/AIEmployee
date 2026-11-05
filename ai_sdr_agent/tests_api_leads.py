"""API tests for the SDR lead endpoints: the ICP, the lead list and lead detail, soft delete and restore (one and
in bulk), categories, CSV import and export, qualification, enrichment, research, the Apify fetch and the SDR key
settings. Each endpoint is checked for refused input (with a readable message, never a crash), for keeping one
login's and one company's data away from another, for refusing callers who are not signed-in company users, and
for doing the right thing in the database when the input is good. No outside service is called."""
import csv
import io
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import (
    SDRAgentSettings, SDRIcpProfile, SDRLead, SDRLeadCategory, SDRLeadResearchJob,
)
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.models import Company, CompanyUser


class LeadApiBase(SDRBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()
        self.other_company = Company.objects.create(name='Rival', email='rival@test.local')
        self.outsider = CompanyUser.objects.create(
            company=self.other_company, email='out@test.local', full_name='Out',
            role='admin', password_hash='x', is_active=True,
        )

    def call(self, view, method='get', path='/x', data=None, fmt='json', user='me', **kw):
        """Call a view as `user` (default: self.cu; None: nobody signed in). An exception the view lets out is
        what the server would answer with a 500, so it comes back as one, with the error as its message."""
        req = getattr(self.rf, method)(path, data if data is not None else {}, format=fmt)
        if user is not None:
            force_authenticate(req, user=self.cu if user == 'me' else user)
        try:
            return view(req, **kw)
        except Exception as exc:  # noqa: BLE001 - reported as the 500 the server would send
            return SimpleNamespace(status_code=500, data={'message': f'unhandled {type(exc).__name__}: {exc}'})

    def assertRefused(self, r, status=400):
        self.assertEqual(r.status_code, status, getattr(r, 'data', None))
        msg = (r.data or {}).get('message') or (r.data or {}).get('detail')
        self.assertTrue(isinstance(msg, str) and msg.strip(), f'no readable message in {r.data!r}')

    def same_company_login(self):
        return CompanyUser.objects.create(company=self.company, email='o@test.local', full_name='O',
                                          role='admin', password_hash='x', is_active=True)

    def their_lead(self, owner=None, email='their@rival.example', **kw):
        return SDRLead.objects.create(company_user=owner or self.outsider, email=email,
                                      full_name='Their Lead', **kw)

    def icp(self, owner=None, **kw):
        return SDRIcpProfile.objects.create(company_user=owner or self.cu, is_active=True,
                                            job_titles=['CEO'], **kw)


# ==========================================================================
# Auth
# ==========================================================================

class OnlySignedInCompanyUsersGetInTests(LeadApiBase):
    def endpoints(self):
        lead = self.make_lead()
        return [
            (views.icp_profile, 'get', {}), (views.icp_profile, 'post', {}),
            (views.leads_list, 'get', {}), (views.leads_list, 'post', {}),
            (views.lead_detail, 'get', {'lead_id': lead.id}), (views.lead_detail, 'delete', {'lead_id': lead.id}),
            (views.restore_lead, 'post', {'lead_id': lead.id}),
            (views.sdr_bulk_delete_leads, 'post', {}), (views.sdr_bulk_restore_leads, 'post', {}),
            (views.sdr_bulk_set_category, 'post', {}),
            (views.sdr_lead_categories, 'get', {}), (views.sdr_lead_category_detail, 'delete', {'category_id': 1}),
            (views.import_leads_csv, 'post', {}), (views.sdr_leads_export, 'get', {}),
            (views.qualify_all_leads, 'post', {}), (views.qualify_lead, 'post', {'lead_id': lead.id}),
            (views.enrich_lead_endpoint, 'post', {'lead_id': lead.id}), (views.enrich_leads_batch_endpoint, 'post', {}),
            (views.research_leads, 'post', {}), (views.research_sources, 'get', {}),
            (views.research_job_status, 'get', {'job_id': 1}),
            (views.research_lead_endpoint, 'post', {'lead_id': lead.id}),
            (views.research_leads_batch_endpoint, 'post', {}), (views.fetch_apify_leads, 'post', {}),
            (views.sdr_agent_settings, 'get', {}),
        ]

    def check_all_refused(self, user):
        for view, method, kw in self.endpoints():
            with self.subTest(view=view.__name__, method=method):
                r = self.call(view, method, user=user, **kw)
                self.assertIn(r.status_code, (401, 403), r.data)
        self.assertTrue(SDRLead.objects.filter(email='bob@acme.com').exists())   # the delete did not go through

    def test_a_request_with_nobody_signed_in_is_refused_everywhere(self):
        self.check_all_refused(None)

    def test_an_employee_login_that_is_not_a_company_user_is_refused_everywhere(self):
        self.check_all_refused(User.objects.create_user('emp', 'emp@test.local', 'pw'))

    def test_a_deactivated_company_user_is_refused_everywhere(self):
        self.cu.is_active = False
        self.cu.save(update_fields=['is_active'])
        self.check_all_refused(self.cu)


# ==========================================================================
# ICP
# ==========================================================================

class IcpProfileTests(LeadApiBase):
    def save(self, **data):
        return self.call(views.icp_profile, 'post', data={'name': 'Mine', 'industries': ['SaaS'], **data})

    def test_with_no_icp_the_answer_is_empty_not_an_error(self):
        r = self.call(views.icp_profile)
        self.assertEqual((r.status_code, r.data['data'], r.data['all']), (200, None, []))

    def test_a_saved_icp_comes_back_and_a_second_save_updates_it(self):
        r = self.save(hot_threshold=80, warm_threshold=50, company_size_min=10, company_size_max=500)
        self.assertEqual(r.status_code, 200)
        self.save(name='Renamed', hot_threshold=90, warm_threshold=40)
        self.assertEqual(SDRIcpProfile.objects.filter(company_user=self.cu).count(), 1)
        got = self.call(views.icp_profile).data['data']
        self.assertEqual((got['name'], got['hot_threshold'], got['warm_threshold']), ('Renamed', 90, 40))

    def test_left_out_thresholds_take_the_model_defaults(self):
        self.save()
        icp = SDRIcpProfile.objects.get(company_user=self.cu)
        self.assertEqual((icp.hot_threshold, icp.warm_threshold), (75, 60))

    def test_another_logins_and_another_companys_icp_are_not_shown_or_overwritten(self):
        theirs = self.icp(owner=self.outsider, name='Theirs')
        colleague = self.icp(owner=self.same_company_login(), name='Colleague')
        self.assertIsNone(self.call(views.icp_profile).data['data'])
        self.save(name='Mine')
        theirs.refresh_from_db(); colleague.refresh_from_db()
        self.assertEqual((theirs.name, colleague.name), ('Theirs', 'Colleague'))

    def test_a_threshold_that_is_not_a_number_is_refused(self):
        self.assertRefused(self.save(hot_threshold='high'))
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.cu).exists())

    def test_a_threshold_outside_0_to_100_is_refused(self):
        for bad in ({'hot_threshold': 150}, {'warm_threshold': -5}, {'hot_threshold': 101, 'warm_threshold': 60}):
            with self.subTest(bad):
                self.assertRefused(self.save(**bad))
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.cu).exists())

    def test_a_warm_threshold_above_the_hot_one_is_refused(self):
        self.assertRefused(self.save(hot_threshold=50, warm_threshold=70))
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.cu).exists())

    def test_a_company_size_that_is_not_a_number_is_refused(self):
        self.assertRefused(self.save(company_size_min='ten'))
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.cu).exists())

    def test_a_negative_or_back_to_front_company_size_range_is_refused(self):
        for bad in ({'company_size_min': -10}, {'company_size_min': 500, 'company_size_max': 10}):
            with self.subTest(bad):
                self.assertRefused(self.save(**bad))
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.cu).exists())

    def test_industries_given_as_text_instead_of_a_list_are_refused(self):
        # A string is walked letter by letter wherever the ICP's industries are used.
        self.assertRefused(self.save(industries='SaaS'))

    def test_an_over_long_icp_name_is_refused(self):
        self.assertRefused(self.save(name='x' * 300))


# ==========================================================================
# Leads — create
# ==========================================================================

class CreatingALeadTests(LeadApiBase):
    def create(self, **data):
        return self.call(views.leads_list, 'post', data=data)

    def test_a_valid_lead_is_saved_lower_cased_and_queued_for_scoring_and_enrichment(self):
        r = self.create(full_name='Jane Doe', email='Jane@Corp.Example', company_size='40',
                        linkedin_url='https://www.linkedin.com/in/jane')
        self.assertEqual(r.status_code, 201, r.data)
        lead = SDRLead.objects.get(pk=r.data['data']['id'])
        self.assertEqual((lead.email, lead.source, lead.company_size, lead.company_user_id),
                         ('jane@corp.example', 'manual', 40, self.cu.id))
        self.assertEqual((lead.qualification_status, lead.enrichment_status), ('pending', 'pending'))

    def test_a_name_alone_is_enough(self):
        self.assertEqual(self.create(full_name='Only Name').status_code, 201)

    def test_first_and_last_name_make_the_full_name(self):
        r = self.create(first_name='Ann', last_name='Lee')
        self.assertEqual(r.data['data']['full_name'], 'Ann Lee')

    def test_a_lead_without_a_name_or_an_email_is_refused(self):
        for data in ({}, {'full_name': '', 'email': ''}, {'full_name': '   ', 'email': '  '}):
            with self.subTest(data):
                self.assertRefused(self.create(**data))
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_a_malformed_email_is_refused(self):
        for bad in ('bob@', 'bob', 'bob@acme', 'bob @acme.com', '@acme.com'):
            with self.subTest(bad):
                self.assertRefused(self.create(full_name='Bob', email=bad))
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_a_linkedin_url_that_is_not_linkedin_is_refused(self):
        for bad in ('https://evil.example/in/x', 'linkedin.com.evil.example/in/x', 'not a url'):
            with self.subTest(bad):
                self.assertRefused(self.create(full_name='Bob', linkedin_url=bad))

    def test_a_company_size_that_is_not_a_whole_number_is_refused(self):
        for bad in ('ten', '-5', '4.5', 'abc'):
            with self.subTest(bad):
                self.assertRefused(self.create(full_name='Bob', company_size=bad))

    def test_an_over_long_name_is_refused(self):
        self.assertRefused(self.create(full_name='x' * 300, email='long@corp.example'))
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_a_website_that_is_not_a_web_address_is_refused(self):
        self.assertRefused(self.create(full_name='Bob', company_website='not a website'))

    def test_the_same_email_twice_is_not_a_second_lead(self):
        self.make_lead(email='dup@corp.example')
        r = self.create(full_name='Again', email='DUP@corp.example')
        self.assertEqual(r.data['status'], 'duplicate')
        self.assertEqual(SDRLead.objects.filter(email__iexact='dup@corp.example').count(), 1)

    def test_another_companys_lead_with_the_same_email_does_not_block_mine(self):
        self.their_lead(email='shared@corp.example')
        self.assertEqual(self.create(full_name='Mine', email='shared@corp.example').status_code, 201)

    def test_another_companys_category_id_is_refused(self):
        cat = SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertRefused(self.create(full_name='Bob', category=cat.id))


# ==========================================================================
# Leads — list
# ==========================================================================

class ListingLeadsTests(LeadApiBase):
    def ids(self, query=''):
        r = self.call(views.leads_list, path=f'/x{query}')
        self.assertEqual(r.status_code, 200, r.data)
        return {l['id'] for l in r.data['data']}

    def test_only_my_own_not_deleted_leads_are_listed(self):
        mine = self.make_lead()
        gone = self.make_lead(email='gone@acme.com')
        gone.soft_delete()
        self.their_lead()
        self.their_lead(owner=self.same_company_login(), email='colleague@acme.com')
        self.assertEqual(self.ids(), {mine.id})

    def test_search_and_temperature_filters_narrow_the_list(self):
        hot = self.make_lead(email='hot@acme.com', company_name='Zebra Ltd', temperature='hot', score=90)
        self.make_lead(email='cold@acme.com', company_name='Yak Inc', temperature='cold', score=10)
        self.assertEqual(self.ids('?search=zebra'), {hot.id})
        self.assertEqual(self.ids('?temperature=hot'), {hot.id})

    def test_page_size_is_kept_between_5_and_100_and_junk_falls_back_to_25(self):
        for q, size in (('?page_size=1000', 100), ('?page_size=1', 5), ('?page_size=abc&page=xyz', 25)):
            with self.subTest(q):
                r = self.call(views.leads_list, path=f'/x{q}')
                self.assertEqual((r.status_code, r.data['pagination']['page_size']), (200, size))

    def test_a_page_past_the_end_gives_the_last_page(self):
        for i in range(6):
            self.make_lead(email=f'p{i}@acme.com')
        r = self.call(views.leads_list, path='/x?page=999&page_size=5')
        self.assertEqual((r.data['pagination']['page'], len(r.data['data'])), (2, 1))

    def test_stats_count_only_my_leads(self):
        self.make_lead(score=None)
        self.their_lead()
        self.assertEqual(self.call(views.leads_list).data['stats']['total'], 1)


# ==========================================================================
# Lead detail — get / update / delete
# ==========================================================================

class LeadDetailTests(LeadApiBase):
    def put(self, lead, **data):
        return self.call(views.lead_detail, 'put', data=data, lead_id=lead.id)

    def test_my_lead_can_be_read(self):
        lead = self.make_lead()
        r = self.call(views.lead_detail, lead_id=lead.id)
        self.assertEqual((r.status_code, r.data['data']['email']), (200, 'bob@acme.com'))

    def test_an_unknown_lead_is_not_found(self):
        self.assertRefused(self.call(views.lead_detail, lead_id=999999), 404)

    def test_another_companys_or_logins_lead_is_not_found(self):
        for lead in (self.their_lead(), self.their_lead(owner=self.same_company_login(), email='c@acme.com')):
            with self.subTest(owner=lead.company_user_id):
                self.assertRefused(self.call(views.lead_detail, lead_id=lead.id), 404)

    def test_an_update_changes_the_fields_sent(self):
        lead = self.make_lead()
        r = self.put(lead, job_title='CTO', company_name='NewCo')
        self.assertEqual(r.status_code, 200, r.data)
        lead.refresh_from_db()
        self.assertEqual((lead.job_title, lead.company_name, lead.email), ('CTO', 'NewCo', 'bob@acme.com'))

    def test_another_companys_lead_cannot_be_updated(self):
        lead = self.their_lead(job_title='CEO')
        self.assertRefused(self.put(lead, job_title='Hacked'), 404)
        lead.refresh_from_db()
        self.assertEqual(lead.job_title, 'CEO')

    def test_an_update_with_a_malformed_email_is_refused(self):
        lead = self.make_lead()
        self.assertRefused(self.put(lead, email='not-an-email'))
        lead.refresh_from_db()
        self.assertEqual(lead.email, 'bob@acme.com')

    def test_an_update_with_a_company_size_that_is_not_a_number_is_refused(self):
        lead = self.make_lead(company_size=10)
        self.assertRefused(self.put(lead, company_size='lots'))
        lead.refresh_from_db()
        self.assertEqual(lead.company_size, 10)

    def test_an_update_with_a_linkedin_url_that_is_not_linkedin_is_refused(self):
        lead = self.make_lead()
        self.assertRefused(self.put(lead, linkedin_url='https://evil.example/in/x'))

    def test_an_update_that_blanks_both_name_and_email_is_refused(self):
        lead = self.make_lead()
        self.assertRefused(self.put(lead, full_name='', first_name='', email=''))

    def test_an_update_to_an_unknown_status_is_refused(self):
        lead = self.make_lead()
        self.assertRefused(self.put(lead, status='banana'))
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'new')

    def test_an_update_to_another_companys_category_is_refused(self):
        lead = self.make_lead()
        cat = SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertRefused(self.put(lead, category=cat.id))

    def test_patch_is_not_allowed(self):
        self.assertEqual(self.call(views.lead_detail, 'patch', data={'job_title': 'x'},
                                   lead_id=self.make_lead().id).status_code, 405)

    def test_delete_hides_the_lead_but_keeps_the_row(self):
        lead = self.make_lead()
        r = self.call(views.lead_detail, 'delete', lead_id=lead.id)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SDRLead.objects.filter(pk=lead.pk).exists())
        self.assertTrue(SDRLead.all_objects.get(pk=lead.pk).is_deleted)

    def test_another_companys_lead_cannot_be_deleted(self):
        lead = self.their_lead()
        self.assertRefused(self.call(views.lead_detail, 'delete', lead_id=lead.id), 404)
        self.assertFalse(SDRLead.all_objects.get(pk=lead.pk).is_deleted)


# ==========================================================================
# Restore — one and bulk; bulk delete
# ==========================================================================

class RestoreLeadTests(LeadApiBase):
    def test_a_deleted_lead_comes_back_after_restore(self):
        lead = self.make_lead()
        self.call(views.lead_detail, 'delete', lead_id=lead.id)
        r = self.call(views.restore_lead, 'post', lead_id=lead.id)
        self.assertEqual((r.status_code, r.data['data']['id']), (200, lead.id))
        self.assertTrue(SDRLead.objects.filter(pk=lead.pk).exists())
        self.assertIsNone(SDRLead.objects.get(pk=lead.pk).deleted_at)

    def test_restoring_a_lead_that_was_never_deleted_does_no_harm(self):
        lead = self.make_lead()
        self.assertEqual(self.call(views.restore_lead, 'post', lead_id=lead.id).status_code, 200)
        self.assertTrue(SDRLead.objects.filter(pk=lead.pk).exists())

    def test_an_unknown_lead_is_not_found(self):
        self.assertRefused(self.call(views.restore_lead, 'post', lead_id=999999), 404)

    def test_another_companys_deleted_lead_cannot_be_restored(self):
        lead = self.their_lead()
        lead.soft_delete()
        self.assertRefused(self.call(views.restore_lead, 'post', lead_id=lead.id), 404)
        self.assertTrue(SDRLead.all_objects.get(pk=lead.pk).is_deleted)


class BulkDeleteLeadsTests(LeadApiBase):
    def bulk(self, data):
        return self.call(views.sdr_bulk_delete_leads, 'post', data=data)

    def test_only_the_listed_leads_are_deleted(self):
        a, b, keep = (self.make_lead(email=f'{n}@acme.com') for n in 'abk')
        r = self.bulk({'ids': [a.id, b.id]})
        self.assertEqual((r.status_code, r.data['deleted'], set(r.data['deleted_ids'])), (200, 2, {a.id, b.id}))
        self.assertEqual(set(SDRLead.objects.values_list('id', flat=True)), {keep.id})

    def test_another_companys_or_logins_ids_in_the_list_are_left_alone(self):
        mine = self.make_lead()
        theirs = self.their_lead()
        colleague = self.their_lead(owner=self.same_company_login(), email='c@acme.com')
        r = self.bulk({'ids': [mine.id, theirs.id, colleague.id]})
        self.assertEqual(r.data['deleted_ids'], [mine.id])
        self.assertFalse(SDRLead.all_objects.get(pk=theirs.pk).is_deleted)
        self.assertFalse(SDRLead.all_objects.get(pk=colleague.pk).is_deleted)

    def test_an_empty_missing_or_non_list_ids_is_refused(self):
        self.make_lead()
        for data in ({'ids': []}, {}, {'ids': '1,2'}, {'ids': None}):
            with self.subTest(data):
                self.assertRefused(self.bulk(data))
        self.assertEqual(SDRLead.objects.count(), 1)

    def test_ids_that_are_not_numbers_are_refused_not_a_crash(self):
        self.assertRefused(self.bulk({'ids': ['abc']}))

    def test_deleted_leads_can_be_brought_back_with_bulk_restore(self):
        a, b = self.make_lead(email='a@acme.com'), self.make_lead(email='b@acme.com')
        ids = self.bulk({'ids': [a.id, b.id]}).data['deleted_ids']
        r = self.call(views.sdr_bulk_restore_leads, 'post', data={'ids': ids})
        self.assertEqual(r.data['restored'], 2)
        self.assertEqual(SDRLead.objects.count(), 2)


class BulkRestoreLeadsTests(LeadApiBase):
    def restore(self, data):
        return self.call(views.sdr_bulk_restore_leads, 'post', data=data)

    def test_only_my_listed_deleted_leads_come_back(self):
        a, b = self.make_lead(email='a@acme.com'), self.make_lead(email='b@acme.com')
        a.soft_delete(); b.soft_delete()
        r = self.restore({'ids': [a.id]})
        self.assertEqual((r.status_code, r.data['restored']), (200, 1))
        self.assertEqual(set(SDRLead.objects.values_list('id', flat=True)), {a.id})

    def test_another_companys_deleted_lead_stays_deleted(self):
        theirs = self.their_lead()
        theirs.soft_delete()
        r = self.restore({'ids': [theirs.id]})
        self.assertEqual(r.data['restored'], 0)
        self.assertTrue(SDRLead.all_objects.get(pk=theirs.pk).is_deleted)

    def test_an_empty_missing_or_non_list_ids_is_refused(self):
        for data in ({'ids': []}, {}, {'ids': 'all'}):
            with self.subTest(data):
                self.assertRefused(self.restore(data))

    def test_ids_that_are_not_numbers_are_refused_not_a_crash(self):
        self.assertRefused(self.restore({'ids': ['abc']}))


# ==========================================================================
# Categories
# ==========================================================================

class CategoryEndpointsTests(LeadApiBase):
    def test_a_new_category_is_made_and_listed_with_its_lead_count(self):
        r = self.call(views.sdr_lead_categories, 'post', data={'name': '  Dentistry  '})
        self.assertEqual((r.status_code, r.data['data']['name']), (201, 'Dentistry'))
        self.make_lead(category_id=r.data['data']['id'])
        data = self.call(views.sdr_lead_categories).data['data']
        self.assertEqual([(c['name'], c['lead_count']) for c in data], [('Dentistry', 1)])

    def test_an_empty_or_blank_name_is_refused(self):
        for name in ('', '   ', None):
            with self.subTest(name=name):
                self.assertRefused(self.call(views.sdr_lead_categories, 'post', data={'name': name}))
        self.assertFalse(SDRLeadCategory.objects.exists())

    def test_an_over_long_name_is_refused(self):
        self.assertRefused(self.call(views.sdr_lead_categories, 'post', data={'name': 'x' * 101}))

    def test_another_companys_categories_are_not_listed(self):
        SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertEqual(self.call(views.sdr_lead_categories).data['data'], [])

    def test_another_companys_category_cannot_be_renamed_or_deleted(self):
        cat = SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertRefused(self.call(views.sdr_lead_category_detail, 'put', data={'name': 'X'},
                                     category_id=cat.id), 404)
        self.assertRefused(self.call(views.sdr_lead_category_detail, 'delete', category_id=cat.id), 404)
        cat.refresh_from_db()
        self.assertEqual(cat.name, 'Theirs')

    def test_renaming_to_a_name_already_used_is_refused(self):
        SDRLeadCategory.objects.create(company_user=self.cu, name='Law')
        cat = SDRLeadCategory.objects.create(company_user=self.cu, name='Dental')
        self.assertRefused(self.call(views.sdr_lead_category_detail, 'put', data={'name': 'law'},
                                     category_id=cat.id))
        self.assertRefused(self.call(views.sdr_lead_category_detail, 'put', data={'name': '  '},
                                     category_id=cat.id))

    def test_deleting_a_category_keeps_its_leads_uncategorised(self):
        cat = SDRLeadCategory.objects.create(company_user=self.cu, name='Dental')
        lead = self.make_lead(category=cat)
        self.assertEqual(self.call(views.sdr_lead_category_detail, 'delete', category_id=cat.id).status_code, 200)
        lead.refresh_from_db()
        self.assertIsNone(lead.category_id)

    def test_an_unknown_category_is_not_found(self):
        self.assertRefused(self.call(views.sdr_lead_category_detail, 'delete', category_id=999999), 404)


class BulkSetCategoryTests(LeadApiBase):
    def bulk(self, data, path='/x'):
        return self.call(views.sdr_bulk_set_category, 'post', path=path, data=data)

    def test_only_my_listed_leads_are_moved(self):
        a, b = self.make_lead(email='a@acme.com'), self.make_lead(email='b@acme.com')
        theirs = self.their_lead()
        r = self.bulk({'category': 'Dental', 'ids': [a.id, theirs.id]})
        self.assertEqual((r.status_code, r.data['updated']), (200, 1))
        self.assertEqual(SDRLead.objects.get(pk=a.pk).category.name, 'Dental')
        self.assertIsNone(SDRLead.objects.get(pk=b.pk).category_id)
        self.assertIsNone(SDRLead.objects.get(pk=theirs.pk).category_id)

    def test_all_matching_follows_the_filter(self):
        hot = self.make_lead(email='h@acme.com', temperature='hot')
        self.make_lead(email='c@acme.com', temperature='cold')
        r = self.bulk({'category': 'Hot ones', 'all_matching': True}, path='/x?temperature=hot')
        self.assertEqual(r.data['updated'], 1)
        self.assertEqual(SDRLead.objects.get(pk=hot.pk).category.name, 'Hot ones')

    def test_no_ids_is_refused(self):
        for data in ({'category': 'X'}, {'category': 'X', 'ids': []}, {'category': 'X', 'ids': 'all'}):
            with self.subTest(data):
                self.assertRefused(self.bulk(data))

    def test_an_unknown_category_id_is_refused(self):
        self.assertRefused(self.bulk({'category': 999999, 'ids': [self.make_lead().id]}))

    def test_ids_that_are_not_numbers_are_refused_not_a_crash(self):
        self.assertRefused(self.bulk({'category': 'X', 'ids': ['abc']}))


# ==========================================================================
# CSV import / export
# ==========================================================================

class ImportCsvTests(LeadApiBase):
    def upload(self, content, name='leads.csv', ctype='text/csv', **extra):
        f = SimpleUploadedFile(name, content if isinstance(content, bytes) else content.encode(), content_type=ctype)
        return self.call(views.import_leads_csv, 'post', data={'file': f, **extra}, fmt='multipart')

    def rows(self, header, *rows):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        return buf.getvalue()

    def test_good_rows_are_imported_and_queued(self):
        r = self.upload(self.rows(['Full Name', 'E-mail', 'Company', 'Employees'],
                                  ['Ann', 'ANN@corp.example', 'Corp', '1,200'], ['Ben', 'ben@corp.example', '', '']))
        self.assertEqual((r.status_code, r.data['created']), (200, 2), r.data)
        ann = SDRLead.objects.get(email='ann@corp.example')
        self.assertEqual((ann.source, ann.company_size, ann.company_user_id, ann.qualification_status),
                         ('csv_import', 1200, self.cu.id, 'pending'))

    def test_no_file_is_refused(self):
        self.assertRefused(self.call(views.import_leads_csv, 'post', data={}, fmt='multipart'))

    def test_an_empty_file_is_refused(self):
        self.assertRefused(self.upload(b''))
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_a_file_that_is_not_text_is_refused_not_a_crash(self):
        self.assertRefused(self.upload(b'PK\x03\x04\xff\xfe\x00\x81binary', name='leads.xlsx',
                                       ctype='application/vnd.ms-excel'))
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_a_file_without_a_header_row_imports_nothing_and_says_why(self):
        r = self.upload('Ann,ann@corp.example,Corp\nBen,ben@corp.example,Corp\n')
        self.assertEqual(SDRLead.objects.count(), 0)
        self.assertIn('header', r.data['message'])

    def test_a_file_with_no_email_column_still_imports_named_leads(self):
        r = self.upload(self.rows(['Name', 'Company'], ['Ann', 'Corp']))
        self.assertEqual(r.data['created'], 1)
        self.assertEqual(SDRLead.objects.get().email, '')

    def test_a_row_with_a_malformed_email_is_refused_with_the_reason(self):
        r = self.upload(self.rows(['Name', 'Email'], ['Ann', 'ann@'], ['Ben', 'ben@corp.example']))
        self.assertEqual(r.data['created'], 1)
        self.assertIn('ann@', r.data['refused'][0])
        self.assertFalse(SDRLead.objects.filter(full_name='Ann').exists())

    def test_duplicates_in_the_file_and_in_my_leads_are_skipped(self):
        self.make_lead(email='old@corp.example')
        r = self.upload(self.rows(['Name', 'Email'], ['A', 'old@corp.example'], ['B', 'new@corp.example'],
                                  ['C', 'NEW@corp.example']))
        self.assertEqual((r.data['created'], r.data['skipped_duplicates']), (1, 2))

    def test_another_companys_lead_with_the_same_email_does_not_block_the_import(self):
        self.their_lead(email='shared@corp.example')
        self.assertEqual(self.upload(self.rows(['Name', 'Email'], ['A', 'shared@corp.example'])).data['created'], 1)

    def test_more_than_the_row_limit_is_refused(self):
        r = self.upload(self.rows(['Name'], *[[f'n{i}'] for i in range(views.CSV_IMPORT_MAX_ROWS + 1)]))
        self.assertRefused(r)
        self.assertEqual(r.data['code'], 'too_many_rows')
        self.assertEqual(SDRLead.objects.count(), 0)

    def test_another_companys_category_id_is_refused(self):
        cat = SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertRefused(self.upload(self.rows(['Name'], ['A']), category=str(cat.id)))
        self.assertEqual(SDRLead.objects.count(), 0)


class ExportCsvTests(LeadApiBase):
    def export(self, query=''):
        r = self.call(views.sdr_leads_export, path=f'/x{query}')
        self.assertEqual(r.status_code, 200)
        return list(csv.reader(io.StringIO(b''.join(r.streaming_content).decode())))

    def test_only_my_not_deleted_leads_are_exported(self):
        self.make_lead(email='mine@acme.com')
        self.make_lead(email='gone@acme.com').soft_delete()
        self.their_lead(email='their@rival.example')
        self.their_lead(owner=self.same_company_login(), email='colleague@acme.com')
        rows = self.export()
        self.assertEqual(rows[0][:2], ['Name', 'Email'])
        self.assertEqual([r[1] for r in rows[1:]], ['mine@acme.com'])

    def test_the_export_follows_the_filters(self):
        self.make_lead(email='h@acme.com', temperature='hot')
        self.make_lead(email='c@acme.com', temperature='cold')
        self.assertEqual([r[1] for r in self.export('?temperature=hot')[1:]], ['h@acme.com'])

    def test_a_cell_that_looks_like_a_formula_is_kept_as_text(self):
        SDRLead.objects.create(company_user=self.cu, email='f@acme.com', full_name='=HYPERLINK("http://x")',
                               phone='+1 555 0100')
        row = self.export()[1]
        self.assertEqual((row[0], row[2]), ('\'=HYPERLINK("http://x")', '+1 555 0100'))


# ==========================================================================
# Qualification
# ==========================================================================

class QualifyAllLeadsTests(LeadApiBase):
    def test_without_an_icp_nothing_is_queued(self):
        self.make_lead()
        self.icp(owner=self.same_company_login())   # a colleague's ICP is not mine
        self.assertRefused(self.call(views.qualify_all_leads, 'post'))
        self.assertEqual(SDRLead.objects.get().qualification_status, 'none')

    def test_only_my_unscored_leads_not_already_queued_are_queued(self):
        self.icp()
        fresh = self.make_lead(email='fresh@acme.com')
        failed = self.make_lead(email='failed@acme.com', qualification_status='failed',
                                qualification_attempts=3, qualification_error='boom')
        scored = self.make_lead(email='scored@acme.com', score=80, temperature='hot', qualification_status='done')
        running = self.make_lead(email='run@acme.com', qualification_status='processing')
        theirs = self.their_lead()
        self.icp(owner=self.outsider)
        r = self.call(views.qualify_all_leads, 'post')
        self.assertEqual((r.status_code, r.data['queued']), (200, 2), r.data)
        got = {l.pk: (l.qualification_status, l.qualification_attempts)
               for l in SDRLead.all_objects.filter(pk__in=[fresh.pk, failed.pk, scored.pk, running.pk, theirs.pk])}
        self.assertEqual(got, {fresh.pk: ('pending', 0), failed.pk: ('pending', 0), scored.pk: ('done', 0),
                               running.pk: ('processing', 0), theirs.pk: ('none', 0)})
        self.assertEqual(SDRLead.objects.get(pk=failed.pk).qualification_error, '')

    def test_running_it_twice_queues_nothing_new(self):
        self.icp()
        self.make_lead()
        self.call(views.qualify_all_leads, 'post')
        self.assertEqual(self.call(views.qualify_all_leads, 'post').data['queued'], 0)


class QualifyOneLeadTests(LeadApiBase):
    RESULT = {'score': 82, 'temperature': 'hot', 'score_breakdown': {'fit': 40},
              'qualification_reasoning': 'Good fit', 'key_strengths': ['size'], 'concerns': [],
              'outreach_strategy': 'Email'}

    def qualify(self, lead_id, result=None):
        agent = mock.Mock()
        agent.qualify_lead.return_value = result or self.RESULT
        with mock.patch.object(views, '_get_qualification_agent', return_value=agent):
            r = self.call(views.qualify_lead, 'post', lead_id=lead_id)
        return r, agent

    def test_the_score_is_saved_and_the_lead_leaves_the_queue(self):
        self.icp()
        lead = self.make_lead(qualification_status='pending')
        r, _ = self.qualify(lead.id)
        self.assertEqual(r.status_code, 200, r.data)
        lead.refresh_from_db()
        self.assertEqual((lead.score, lead.temperature, lead.qualification_status), (82, 'hot', 'done'))
        self.assertIsNotNone(lead.qualified_at)

    def test_without_an_icp_it_is_refused(self):
        r, agent = self.qualify(self.make_lead().id)
        self.assertRefused(r)
        agent.qualify_lead.assert_not_called()

    def test_an_unknown_lead_is_not_found(self):
        self.icp()
        self.assertRefused(self.qualify(999999)[0], 404)

    def test_another_companys_lead_is_not_scored(self):
        self.icp()
        lead = self.their_lead()
        r, agent = self.qualify(lead.id)
        self.assertRefused(r, 404)
        agent.qualify_lead.assert_not_called()
        lead.refresh_from_db()
        self.assertIsNone(lead.score)


# ==========================================================================
# Enrichment
# ==========================================================================

class EnrichOneLeadTests(LeadApiBase):
    OK = {'status': 'success', 'contract': {'status': 'completed'}, 'changes': {'phone': '+1'}, 'summary': {}}

    def post(self, lead_id, data=None, result=None):
        with mock.patch('ai_sdr_agent.tasks.enrich_lead_impl', return_value=result or self.OK) as impl:
            r = self.call(views.enrich_lead_endpoint, 'post', data=data or {}, lead_id=lead_id)
        return r, impl

    def test_enriching_my_lead_runs_the_enrichment_and_reports_it(self):
        lead = self.make_lead()
        r, impl = self.post(lead.id, {'force': True})
        self.assertEqual((r.status_code, r.data['enrichment_status'], r.data['cached']), (200, 'completed', False))
        impl.assert_called_once_with(lead.id, force=True)

    def test_a_lead_already_being_enriched_answers_409(self):
        self.assertRefused(self.post(self.make_lead().id, result={'status': 'already_running'})[0], 409)

    def test_a_provider_failure_comes_back_with_its_message(self):
        r, _ = self.post(self.make_lead().id, result={'status': 'failed', 'error': 'Apollo is down'})
        self.assertGreaterEqual(r.status_code, 400)
        self.assertEqual(r.data['message'], 'Apollo is down')

    def test_async_queues_a_background_job(self):
        lead = self.make_lead()
        with mock.patch('ai_sdr_agent.tasks.enrich_lead_task.delay', return_value=mock.Mock(id='t1')) as delay:
            r = self.call(views.enrich_lead_endpoint, 'post', data={'async': True}, lead_id=lead.id)
        self.assertEqual((r.data['status'], r.data['task_id']), ('queued', 't1'))
        delay.assert_called_once_with(lead.id, force=False)

    def test_an_unknown_lead_is_not_found(self):
        self.assertRefused(self.post(999999)[0], 404)

    def test_another_companys_or_logins_lead_is_not_enriched(self):
        for lead in (self.their_lead(), self.their_lead(owner=self.same_company_login(), email='c@acme.com')):
            with self.subTest(owner=lead.company_user_id):
                r, impl = self.post(lead.id)
                self.assertRefused(r, 404)
                impl.assert_not_called()
                self.assertRefused(self.call(views.enrich_lead_endpoint, lead_id=lead.id), 404)

    def test_get_returns_the_saved_enrichment(self):
        lead = self.make_lead(raw_data={'enrichment': {'status': 'partial', 'personal_email': ''}})
        r = self.call(views.enrich_lead_endpoint, lead_id=lead.id)
        self.assertEqual((r.status_code, r.data['enrichment_status']), (200, 'partial'))


class EnrichLeadsBatchTests(LeadApiBase):
    def post(self, data):
        with mock.patch('ai_sdr_agent.tasks.enrich_leads_batch_impl',
                        return_value={'total': 1, 'completed': 1, 'failed': 0, 'results': []}) as impl:
            r = self.call(views.enrich_leads_batch_endpoint, 'post', data=data)
        return r, impl

    def test_only_my_listed_leads_are_enriched(self):
        mine = self.make_lead()
        theirs = self.their_lead()
        r, impl = self.post({'lead_ids': [mine.id, theirs.id]})
        self.assertEqual(r.status_code, 200, r.data)
        impl.assert_called_once_with([mine.id], force=False)

    def test_a_batch_of_only_other_peoples_leads_is_not_found(self):
        r, impl = self.post({'lead_ids': [self.their_lead().id]})
        self.assertRefused(r, 404)
        impl.assert_not_called()

    def test_an_empty_missing_or_non_list_lead_ids_is_refused(self):
        for data in ({'lead_ids': []}, {}, {'lead_ids': '1,2'}, {'lead_ids': 5}):
            with self.subTest(data):
                self.assertRefused(self.post(data)[0])

    def test_ids_that_are_not_numbers_are_refused_not_a_crash(self):
        self.assertRefused(self.post({'lead_ids': ['abc']})[0])

    def test_at_most_50_leads_are_taken_in_one_batch(self):
        ids = [self.make_lead(email=f'b{i}@acme.com').id for i in range(55)]
        _, impl = self.post({'lead_ids': ids})
        self.assertEqual(len(impl.call_args.args[0]), 50)

    def test_async_queues_the_owned_ids(self):
        mine = self.make_lead()
        with mock.patch('ai_sdr_agent.tasks.enrich_leads_batch_task.delay', return_value=mock.Mock(id='t')) as d:
            r = self.call(views.enrich_leads_batch_endpoint, 'post',
                          data={'lead_ids': [mine.id, self.their_lead().id], 'async': True})
        self.assertEqual((r.data['status'], r.data['lead_count']), ('queued', 1))
        d.assert_called_once_with([mine.id], force=False)


# ==========================================================================
# Research
# ==========================================================================

class ResearchOneLeadTests(LeadApiBase):
    def post(self, lead_id, result=None, data=None):
        result = result or {'status': 'success', 'profile': {'research_status': 'completed'}}
        with mock.patch('ai_sdr_agent.tasks.research_lead_impl', return_value=result) as impl:
            r = self.call(views.research_lead_endpoint, 'post', data=data or {}, lead_id=lead_id)
        return r, impl

    def test_researching_my_lead_returns_the_profile(self):
        lead = self.make_lead()
        r, impl = self.post(lead.id, data={'campaign_id': self.campaign.id})
        self.assertEqual((r.status_code, r.data['research_status']), (200, 'completed'))
        impl.assert_called_once_with(lead.id, campaign_id=self.campaign.id, force=False)

    def test_a_lead_already_being_researched_answers_409(self):
        self.assertRefused(self.post(self.make_lead().id, result={'status': 'already_running'})[0], 409)

    def test_async_queues_a_background_job(self):
        lead = self.make_lead()
        with mock.patch('ai_sdr_agent.tasks.research_lead_task.delay', return_value=mock.Mock(id='t')) as d:
            r = self.call(views.research_lead_endpoint, 'post', data={'async': True}, lead_id=lead.id)
        self.assertEqual(r.data['status'], 'queued')
        d.assert_called_once_with(lead.id, campaign_id=None, force=False)

    def test_an_unknown_or_another_companys_lead_is_not_found(self):
        for lead_id in (999999, self.their_lead().id):
            with self.subTest(lead_id=lead_id):
                r, impl = self.post(lead_id)
                self.assertRefused(r, 404)
                impl.assert_not_called()
                self.assertRefused(self.call(views.research_lead_endpoint, lead_id=lead_id), 404)


class ResearchLeadsBatchTests(LeadApiBase):
    def post(self, data):
        with mock.patch('ai_sdr_agent.tasks.research_leads_batch_impl',
                        return_value={'total': 1, 'completed': 1, 'failed': 0, 'results': []}) as impl:
            r = self.call(views.research_leads_batch_endpoint, 'post', data=data)
        return r, impl

    def test_only_my_listed_leads_are_researched(self):
        mine = self.make_lead()
        r, impl = self.post({'lead_ids': [mine.id, self.their_lead().id]})
        self.assertEqual(r.status_code, 200)
        impl.assert_called_once_with([mine.id], campaign_id=None, force=False)

    def test_an_empty_list_or_only_other_peoples_leads_is_refused(self):
        self.assertRefused(self.post({'lead_ids': []})[0])
        self.assertRefused(self.post({'lead_ids': 'x'})[0])
        self.assertRefused(self.post({'lead_ids': [self.their_lead().id]})[0], 404)

    def test_ids_that_are_not_numbers_are_refused_not_a_crash(self):
        self.assertRefused(self.post({'lead_ids': ['abc']})[0])


class ResearchNewLeadsTests(LeadApiBase):
    def start(self, data, sources=('apollo',)):
        agent = mock.Mock(available_sources=list(sources), source_label='apollo')
        with mock.patch.object(views, '_get_research_agent', return_value=agent), \
                mock.patch('threading.Thread') as thread:
            r = self.call(views.research_leads, 'post', data=data)
        return r, thread

    def test_a_search_starts_a_background_job_for_my_icp(self):
        icp = self.icp()
        r, thread = self.start({'count': 30})
        self.assertEqual(r.status_code, 202, r.data)
        job = SDRLeadResearchJob.objects.get(pk=r.data['job_id'])
        self.assertEqual((job.company_user_id, job.icp_profile_id, job.search_params['count']), (self.cu.id, icp.id, 30))
        thread.return_value.start.assert_called_once()

    def test_without_an_icp_it_is_refused(self):
        r, thread = self.start({})
        self.assertRefused(r)
        thread.assert_not_called()

    def test_another_companys_icp_id_is_not_used(self):
        theirs = self.icp(owner=self.outsider)
        r, _ = self.start({'icp_id': theirs.id})
        self.assertRefused(r)
        self.assertFalse(SDRLeadResearchJob.objects.exists())

    def test_with_no_lead_source_set_up_it_is_refused(self):
        self.icp()
        r, _ = self.start({}, sources=())
        self.assertRefused(r)
        self.assertEqual(r.data['code'], 'no_lead_source')

    def test_a_count_that_is_not_a_number_is_refused(self):
        self.icp()
        self.assertRefused(self.start({'count': 'lots'})[0])

    def test_an_icp_id_that_is_not_a_number_is_refused(self):
        self.icp()
        self.assertRefused(self.start({'icp_id': 'abc'})[0])

    def test_another_companys_category_is_refused(self):
        self.icp()
        cat = SDRLeadCategory.objects.create(company_user=self.outsider, name='Theirs')
        self.assertRefused(self.start({'category': cat.id})[0])


class ResearchJobStatusAndSourcesTests(LeadApiBase):
    def test_my_job_can_be_polled(self):
        job = SDRLeadResearchJob.objects.create(company_user=self.cu, status='completed', leads_created=4)
        r = self.call(views.research_job_status, job_id=job.id)
        self.assertEqual((r.status_code, r.data['job']['leads_created'], r.data['job']['done']), (200, 4, True))

    def test_an_unknown_or_another_companys_job_is_not_found(self):
        theirs = SDRLeadResearchJob.objects.create(company_user=self.outsider, status='running')
        for job_id in (999999, theirs.id):
            with self.subTest(job_id=job_id):
                self.assertRefused(self.call(views.research_job_status, job_id=job_id), 404)

    def test_sources_come_from_my_own_keys(self):
        agent = mock.Mock(available_sources=['apify'], source_label='apify', apify_token='t', apify_actor='a/b')
        with mock.patch.object(views, '_get_research_agent', return_value=agent) as factory:
            r = self.call(views.research_sources)
        self.assertEqual((r.data['sources'], r.data['apify_actor']), (['apify'], 'a/b'))
        self.assertEqual(factory.call_args.kwargs['company_user'], self.cu)


# ==========================================================================
# Apify fetch
# ==========================================================================

class FetchApifyLeadsTests(LeadApiBase):
    def fetch(self, data=None, leads=None, token='tok'):
        if token:
            SDRAgentSettings.objects.update_or_create(company_user=self.cu, defaults={'apify_api_token': token})
        agent = mock.Mock()
        agent.fetch_apify_runs.return_value = leads if leads is not None else []
        with mock.patch.object(views, '_get_research_agent', return_value=agent):
            return self.call(views.fetch_apify_leads, 'post', data=data or {}), agent

    def test_new_leads_are_imported_and_duplicates_skipped(self):
        self.make_lead(email='old@corp.example')
        self.their_lead(email='theirs@corp.example')   # another company's lead does not count as a duplicate
        r, _ = self.fetch(leads=[{'full_name': 'Old', 'email': 'OLD@corp.example'},
                                 {'full_name': 'New', 'email': 'new@corp.example', 'company_name': 'Corp'},
                                 {'full_name': 'Theirs', 'email': 'theirs@corp.example'}])
        self.assertEqual((r.status_code, r.data['leads_created'], r.data['skipped_duplicates']), (200, 2, 1), r.data)
        self.assertEqual(SDRLead.objects.get(email='new@corp.example').source, 'apify')

    def test_without_my_own_apify_token_it_is_refused(self):
        SDRAgentSettings.objects.create(company_user=self.outsider, apify_api_token='their-token')
        r, agent = self.fetch(token=None)
        self.assertRefused(r)
        self.assertEqual(r.data['code'], 'no_lead_source')
        agent.fetch_apify_runs.assert_not_called()

    def test_no_runs_found_is_a_readable_refusal(self):
        self.assertRefused(self.fetch(leads=[])[0])

    def test_a_count_that_is_not_a_number_is_refused(self):
        self.assertRefused(self.fetch(data={'count': 'all'})[0])


# ==========================================================================
# SDR key settings
# ==========================================================================

class SdrSettingsTests(LeadApiBase):
    def test_saved_keys_are_masked_when_read_back(self):
        r = self.call(views.sdr_agent_settings, 'post', data={'apollo_api_key': '  apollo-secret-1234  ',
                                                               'apify_actor_id': 'a/b'})
        self.assertEqual((r.status_code, r.data['apollo_api_key_set']), (200, True))
        self.assertEqual(SDRAgentSettings.objects.get(company_user=self.cu).apollo_api_key, 'apollo-secret-1234')
        got = self.call(views.sdr_agent_settings).data
        self.assertNotIn('secret', got['apollo_api_key'])
        self.assertEqual(got['apify_actor_id'], 'a/b')

    def test_an_empty_string_clears_a_key_and_unsent_keys_are_kept(self):
        SDRAgentSettings.objects.create(company_user=self.cu, apollo_api_key='k' * 20, apify_api_token='t' * 20)
        self.call(views.sdr_agent_settings, 'post', data={'apollo_api_key': ''})
        s = SDRAgentSettings.objects.get(company_user=self.cu)
        self.assertEqual((s.apollo_api_key, s.apify_api_token), ('', 't' * 20))

    def test_saving_my_keys_leaves_other_logins_keys_alone(self):
        SDRAgentSettings.objects.create(company_user=self.outsider, apollo_api_key='theirs-key-123')
        self.call(views.sdr_agent_settings, 'post', data={'apollo_api_key': 'mine-key-456'})
        self.assertEqual(SDRAgentSettings.objects.get(company_user=self.outsider).apollo_api_key, 'theirs-key-123')
        self.assertFalse(self.call(views.sdr_agent_settings, user=self.same_company_login()).data['apollo_api_key_set'])

    def test_a_key_that_is_not_text_is_refused_not_a_crash(self):
        self.assertRefused(self.call(views.sdr_agent_settings, 'post', data={'apollo_api_key': 12345}))
