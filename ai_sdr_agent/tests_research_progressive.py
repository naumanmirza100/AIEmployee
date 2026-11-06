"""A lead search keeps every lead it paid for. A 1,000-lead Apify search runs for up to 25 minutes and saved nothing
until the very end, so a network error, our time limit, a failed run or a restart lost every lead Apify had already
charged for (6 Nov 2026). Leads are now saved while the run goes on, a failed request is tried again, an orphaned
search goes on with the same run, and Stop keeps what was found. No real Apify call is made."""
from datetime import timedelta
from unittest import mock

import requests
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
from ai_sdr_agent.models import SDRIcpProfile, SDRLead, SDRLeadResearchJob
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views


class FakeApify:
    """An Apify run whose dataset grows by ``per_poll`` items at each status check, like a real one."""

    def __init__(self, total=30, per_poll=10, statuses=('RUNNING', 'RUNNING', 'SUCCEEDED'), fail_polls=(),
                 on_poll=None):
        self.items = [{'full_name': f'Person {i}', 'email': f'p{i}@lead.example', 'job_title': 'CEO',
                       'company_name': f'Co {i}'} for i in range(total)]
        self.per_poll, self.statuses, self.fail_polls, self.on_poll = per_poll, list(statuses), set(fail_polls), on_poll
        self.polls = 0
        self.posts, self.offsets, self.saved_at_poll = [], [], []

    def response(self, body, status=200):
        r = mock.MagicMock(status_code=status)
        r.json.return_value = body
        return r

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append(url)
        return self.response({'data': {'id': 'RUN1', 'defaultDatasetId': 'DS1'}}, 201)

    def get(self, url, params=None, headers=None, timeout=None):
        if '/actor-runs/' in url:
            self.polls += 1
            self.saved_at_poll.append(SDRLead.objects.count())
            if self.on_poll:
                self.on_poll(self.polls)
            if self.polls in self.fail_polls:
                raise requests.ConnectionError('network down')
            status = self.statuses[min(self.polls, len(self.statuses)) - 1]
            return self.response({'data': {'status': status, 'defaultDatasetId': 'DS1'}})
        visible = self.items[:self.per_poll * self.polls]
        self.offsets.append(params['offset'])
        return self.response(visible[params['offset']:params['offset'] + params['limit']])

    def patch(self):
        return [mock.patch('requests.post', side_effect=self.post), mock.patch('requests.get', side_effect=self.get),
                mock.patch('time.sleep')]


class ProgressiveSearchTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.icp = SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['CEO'])
        self.agent = LeadResearchAgent(apify_token='tok', apify_actor='code_crafter/leads-finder')

    def job(self, count=30, **kw):
        return SDRLeadResearchJob.objects.create(
            company_user=self.cu, icp_profile=self.icp, status='running', source='apify',
            search_params={'count': count, 'source': 'apify'}, started_at=timezone.now(), **kw)

    def run_job(self, job, fake):
        patches = fake.patch() + [mock.patch.object(views, '_get_research_agent', return_value=self.agent)]
        for p in patches:
            p.start()
        try:
            views._execute_research_job(job.pk)
        finally:
            for p in reversed(patches):
                p.stop()
        job.refresh_from_db()
        return job

    def test_leads_are_saved_while_the_run_goes_on(self):
        fake = FakeApify(total=30, per_poll=10)
        job = self.run_job(self.job(30), fake)
        self.assertEqual(fake.saved_at_poll, [0, 10, 20])          # saved before the run had finished
        self.assertEqual((job.status, job.leads_created, job.items_read, job.apify_run_id), ('completed', 30, 30, 'RUN1'))
        self.assertEqual(SDRLead.objects.filter(enrichment_status='pending').count(), 30)
        self.assertIn('maxItems=30', fake.posts[0])                  # Apify itself never charges for more
        self.assertIn('timeout=', fake.posts[0])
        self.assertFalse(job.search_params.get('stopped_reason'))

    def test_a_network_error_mid_run_is_tried_again_and_nothing_is_lost(self):
        fake = FakeApify(total=30, per_poll=10, statuses=['RUNNING'] * 4 + ['SUCCEEDED'], fail_polls={2, 3})
        job = self.run_job(self.job(30), fake)
        self.assertEqual((job.status, job.leads_created), ('completed', 30))
        self.assertEqual(SDRLead.objects.values('email').distinct().count(), 30)
        self.assertFalse(any(url.endswith('/abort') for url in fake.posts))

    def test_a_run_that_fails_partway_keeps_the_leads_it_found(self):
        fake = FakeApify(total=30, per_poll=5, statuses=('RUNNING', 'RUNNING', 'FAILED'))
        job = self.run_job(self.job(30), fake)
        self.assertEqual((job.status, job.leads_created), ('completed', 15))
        self.assertIn('FAILED', job.search_params['stopped_reason'])

    def test_a_run_that_fails_with_nothing_found_still_fails(self):
        fake = FakeApify(total=30, per_poll=0, statuses=('FAILED',))
        job = self.run_job(self.job(30), fake)
        self.assertEqual((job.status, job.leads_created), ('failed', 0))
        self.assertIn('FAILED', job.error_message)

    def test_our_time_limit_keeps_the_leads_and_aborts_the_run(self):
        fake = FakeApify(total=4, per_poll=1, statuses=('RUNNING',))
        job = self.run_job(self.job(5), fake)
        self.assertEqual((job.status, job.leads_created), ('completed', 4))
        self.assertIn('timed out', job.search_params['stopped_reason'])
        self.assertTrue(fake.posts[-1].endswith('/actor-runs/RUN1/abort'))

    def test_apify_out_of_reach_leaves_the_search_running_for_resume(self):
        fake = FakeApify(total=30, per_poll=10, statuses=('RUNNING',), fail_polls=set(range(2, 500)))
        job = self.run_job(self.job(30), fake)
        self.assertEqual((job.status, job.leads_created, job.items_read), ('running', 10, 10))
        self.assertFalse(any(url.endswith('/abort') for url in fake.posts))

    def test_an_orphaned_search_goes_on_with_the_same_run_from_where_it_was(self):
        stale = timezone.now() - views.RESEARCH_HEARTBEAT_STALE - timedelta(minutes=1)
        job = self.job(30, apify_run_id='RUN1', apify_dataset_id='DS1', items_read=10, heartbeat_at=stale,
                       leads_created=10)
        for i in range(10):   # what the dead thread had saved
            SDRLead.objects.create(company_user=self.cu, email=f'p{i}@lead.example', full_name=f'Person {i}',
                                   company_name=f'Co {i}')
        live = self.job(30, apify_run_id='RUN2', heartbeat_at=timezone.now())   # still beating: left alone
        fake = FakeApify(total=30, per_poll=30, statuses=('SUCCEEDED',))

        def run_now(target, args, name, daemon):
            return mock.Mock(start=lambda: target(*args))
        patches = fake.patch() + [mock.patch.object(views, '_get_research_agent', return_value=self.agent),
                                  mock.patch('api.views.ai_sdr_agent.threading.Thread', side_effect=run_now)]
        for p in patches:
            p.start()
        try:
            self.assertEqual(views.resume_orphaned_research_jobs(), 1)
        finally:
            for p in reversed(patches):
                p.stop()
        job.refresh_from_db()
        self.assertEqual((job.status, job.leads_created, job.items_read), ('completed', 30, 30))
        self.assertEqual(fake.offsets[0], 10)                          # read on from where it was
        self.assertFalse(any('/acts/' in url for url in fake.posts))   # no new run: nothing bought twice
        self.assertEqual(SDRLead.objects.count(), 30)
        live.refresh_from_db()
        self.assertEqual(live.status, 'running')

    def test_stop_aborts_the_run_and_keeps_what_was_found(self):
        job = self.job(30)

        def press_stop(poll):
            if poll == 2:
                request = APIRequestFactory().post('/x')
                force_authenticate(request, user=self.cu)
                self.assertEqual(views.research_job_stop(request, job.pk).status_code, 200)
        fake = FakeApify(total=30, per_poll=10, statuses=('RUNNING',), on_poll=press_stop)
        job = self.run_job(job, fake)
        self.assertEqual((job.status, job.search_params['stopped_reason']), ('completed', 'Stopped'))
        self.assertEqual(job.leads_created, 20)
        self.assertTrue(fake.posts[-1].endswith('/actor-runs/RUN1/abort'))

    def test_a_finished_search_cannot_be_stopped(self):
        job = self.job(30)
        job.status = 'completed'
        job.save()
        request = APIRequestFactory().post('/x')
        force_authenticate(request, user=self.cu)
        self.assertEqual(views.research_job_stop(request, job.pk).status_code, 400)

    def test_the_status_says_when_a_search_ended_early(self):
        job = self.job(30, leads_created=12)
        job.status = 'completed'
        job.search_params = {**job.search_params, 'stopped_reason': 'Stopped'}
        job.save()
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=self.cu)
        data = views.research_job_status(request, job.pk).data['job']
        self.assertEqual((data['partial'], data['stopped_reason'], data['leads_created']), (True, 'Stopped', 12))


class ApolloKeepsItsPagesTests(SDRBase):
    def test_a_page_that_fails_after_two_keeps_the_first_two(self):
        icp = SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['CEO'])
        agent = LeadResearchAgent(apollo_api_key='k')
        agent.stop_reason = None
        page = lambda n: mock.Mock(status_code=200, json=mock.Mock(return_value={
            'people': [{'id': f'{n}-{i}', 'name': f'P {n}-{i}'} for i in range(100)]}))
        with mock.patch('requests.post', side_effect=[page(1), page(2), mock.Mock(status_code=401)]):
            leads = agent._search_apollo(icp, 300)
        self.assertEqual(len(leads), 200)
        self.assertIn('after 200 leads', agent.stop_reason)
