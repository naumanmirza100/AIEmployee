"""The campaign side of the sales AI, through its API, so nobody has to click through it by hand.

Each screen action is called the way the browser calls it: campaigns and their steps, adding leads, sending,
replies (by hand, from the inbox, and the AI's held answers), the dashboard and analytics figures, and the email
assistant. Bad input gets a 4xx with words a person can read, never a 500; another company's (or, for a plain
member, a colleague's) campaign can be neither seen nor used; and the normal path leaves the right rows behind. No
AI, mail server or DNS is reached.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import (
    SDRCampaign, SDRCampaignEnrollment, SDRCampaignStep, SDRLead, SDRMeeting, SDROutreachLog, SDRReplyDraft,
)
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.do_not_email import block
from core.models import Company, CompanyUser

NOT_INTERESTED = {'category': 'not_interested', 'action': 'stop', 'label': 'Not interested',
                  'is_interested': False, 'reason': 'said no', 'resume_date': None}


def fake_dns(host, *args, **kwargs):
    """Names resolve without the network: loopback stays loopback, anything else is a public address."""
    ip = '127.0.0.1' if host in ('localhost', '127.0.0.1') else '93.184.216.34'
    return [(2, 1, 6, '', (ip, 0))]


class CampaignApiBase(SDRBase):

    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()
        self.logins = self.patch('ai_sdr_agent.agents.outreach_agent.try_mailbox_logins', return_value='')
        self.patch('ai_sdr_agent.agents.sdr_key_resolver.resolve_sdr_groq_client', return_value=(None, None))
        self.smtp = self.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent._send_via_smtp')
        self.inbox = self.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent.check_inbox_for_replies',
                                return_value=[])
        self.patch('socket.getaddrinfo', side_effect=fake_dns)
        for name in ('smtplib.SMTP', 'smtplib.SMTP_SSL', 'imaplib.IMAP4_SSL'):
            self.patch(name)

    def patch(self, target, **kw):
        patcher = mock.patch(target, **kw)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def call(self, view, method='get', data=None, user=None, **kwargs):
        request = getattr(self.rf, method)('/x', data if data is not None else {}, format='json')
        force_authenticate(request, user=user or self.cu)
        return view(request, **kwargs)

    def assert_refused(self, resp, status=400, says=''):
        self.assertEqual(resp.status_code, status, getattr(resp, 'data', resp))
        message = str(resp.data.get('message', ''))
        self.assertTrue(message.strip(), resp.data)
        self.assertIn(says.lower(), message.lower())

    def rival(self):
        """Another company, with its own campaign, step, lead and enrolment."""
        company = Company.objects.create(name='Rival', email='rival@test.local')
        cu = CompanyUser.objects.create(company=company, email='boss@rival.test', full_name='Boss',
                                        role='admin', password_hash='x', is_active=True)
        campaign = SDRCampaign.objects.create(company_user=cu, name='Theirs', status='active',
                                              smtp_host='smtp.rival.test', smtp_username='r', smtp_password='p')
        step = SDRCampaignStep.objects.create(campaign=campaign, step_order=1, delay_days=1,
                                              subject_template='Their subject', body_template='Their body')
        lead = SDRLead.objects.create(company_user=cu, email='lead@rival-customer.test', first_name='Ann',
                                      full_name='Ann A', temperature='hot', score=95)
        enrolment = SDRCampaignEnrollment.objects.create(campaign=campaign, lead=lead, status='active')
        return cu, campaign, step, lead, enrolment

    def colleague(self, role='company_user'):
        return CompanyUser.objects.create(company=self.company, email=f'{role}@test.local', full_name='Col',
                                          role=role, password_hash='x', is_active=True)


# ── Who may call at all ──────────────────────────────────────────────────────

class SignInTests(CampaignApiBase):

    def every_view(self):
        c = self.campaign.id
        return [
            (views.sdr_campaigns_list, 'get', {}), (views.sdr_campaign_detail, 'get', {'campaign_id': c}),
            (views.sdr_campaign_steps, 'get', {'campaign_id': c}),
            (views.sdr_campaign_step_detail, 'delete', {'campaign_id': c, 'step_id': 1}),
            (views.sdr_enroll_leads, 'post', {'campaign_id': c}),
            (views.sdr_campaign_enrollments, 'get', {'campaign_id': c}),
            (views.sdr_process_outreach, 'post', {'campaign_id': c}),
            (views.sdr_mark_replied, 'post', {'campaign_id': c, 'enrollment_id': 1}),
            (views.sdr_reset_enrollment, 'post', {'campaign_id': c, 'enrollment_id': 1}),
            (views.sdr_check_replies, 'post', {'campaign_id': c}), (views.sdr_check_all_replies, 'post', {}),
            (views.sdr_clear_campaign_leads, 'post', {'campaign_id': c}),
            (views.sdr_retry_failed, 'post', {'campaign_id': c}),
            (views.sdr_generate_steps, 'post', {'campaign_id': c}),
            (views.sdr_reply_drafts, 'get', {'campaign_id': c}),
            (views.sdr_reply_draft_decide, 'post', {'draft_id': 1, 'decision': 'discard'}),
            (views.sdr_dashboard, 'get', {}), (views.sdr_analytics, 'get', {}),
            (views.sdr_send_daily_summary, 'post', {}), (views.sdr_scheduler_status, 'get', {}),
            (views.sdr_assistant_write, 'post', {}), (views.sdr_assistant_read, 'post', {}),
        ]

    def test_a_request_with_nobody_signed_in_is_refused_everywhere(self):
        for view, method, kwargs in self.every_view():
            resp = view(getattr(self.rf, method)('/x', {}, format='json'), **kwargs)
            self.assertIn(resp.status_code, (401, 403), view.__name__)

    def test_a_staff_login_that_is_not_a_company_user_is_refused_everywhere(self):
        staff = User.objects.create_user('staff', 'staff@test.local', 'pw')
        for view, method, kwargs in self.every_view():
            request = getattr(self.rf, method)('/x', {}, format='json')
            force_authenticate(request, user=staff)
            self.assertEqual(view(request, **kwargs).status_code, 403, view.__name__)

    def test_a_switched_off_company_login_is_refused(self):
        CompanyUser.objects.filter(pk=self.cu.pk).update(is_active=False)
        self.cu.refresh_from_db()
        self.assertEqual(self.call(views.sdr_campaigns_list).status_code, 403)
        self.assertEqual(self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id).status_code, 403)
        self.assertEqual(SDROutreachLog.objects.count(), 0)


# ── Campaigns: list and create ───────────────────────────────────────────────

class CampaignCreateTests(CampaignApiBase):

    def create(self, **data):
        return self.call(views.sdr_campaigns_list, 'post', {'name': 'Spring push', 'generate_steps': False, **data})

    def test_a_campaign_without_a_name_is_refused(self):
        for name in (None, '', '   '):
            data = {} if name is None else {'name': name}
            resp = self.call(views.sdr_campaigns_list, 'post', data)
            self.assert_refused(resp, says='name')
        self.assertEqual(SDRCampaign.objects.count(), 1)

    def test_a_mail_server_inside_the_network_is_refused(self):
        self.assert_refused(self.create(smtp_host='127.0.0.1'), says='public host')
        self.assert_refused(self.create(smtp_host='localhost'), says='public host')

    def test_a_mail_server_name_with_odd_characters_is_refused(self):
        self.assert_refused(self.create(smtp_host='smtp example!.com'), says='not valid')

    def test_ports_that_are_not_mail_ports_or_not_numbers_are_refused(self):
        self.assert_refused(self.create(smtp_host='smtp.example.com', smtp_port=8080), says='port')
        self.assert_refused(self.create(smtp_host='smtp.example.com', smtp_port=-1), says='port')
        self.assert_refused(self.create(smtp_host='smtp.example.com', smtp_port='abc'), says='port')
        self.assert_refused(self.create(imap_host='imap.example.com', imap_port=12), says='port')
        self.assertEqual(SDRCampaign.objects.count(), 1)

    def test_a_port_that_is_not_a_number_is_refused_even_without_a_host(self):
        self.assert_refused(self.create(smtp_port='abc'), says='port')
        self.assertEqual(SDRCampaign.objects.count(), 1)

    def test_a_mailbox_whose_login_fails_is_not_saved_and_says_why(self):
        self.logins.return_value = 'The sending server refused the login (535 bad password).'
        resp = self.create(smtp_host='smtp.example.com', smtp_username='me', smtp_password='wrong')
        self.assert_refused(resp, says='refused the login')
        self.assertFalse(SDRCampaign.objects.filter(name='Spring push').exists())

    def test_a_calendar_link_that_is_not_a_link_is_refused(self):
        self.assert_refused(self.create(calendar_link='my calendar'), says='calendar')

    def test_a_from_address_that_is_not_an_email_is_refused(self):
        resp = self.create(from_email='not-an-email')
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertFalse(SDRCampaign.objects.filter(name='Spring push').exists())

    def test_a_start_date_that_is_not_a_date_is_refused(self):
        resp = self.create(start_date='next tuesday')
        self.assert_refused(resp)
        self.assertFalse(SDRCampaign.objects.filter(name='Spring push').exists())

    def test_a_good_campaign_is_saved_as_a_draft_with_its_steps(self):
        resp = self.call(views.sdr_campaigns_list, 'post', {
            'name': 'Spring push', 'smtp_host': 'smtp.example.com', 'smtp_port': 587, 'smtp_username': 'me',
            'smtp_password': 'pw', 'from_email': 'me@example.com', 'calendar_link': 'https://cal.com/me'})
        self.assertEqual(resp.status_code, 201, resp.data)
        campaign = SDRCampaign.objects.get(pk=resp.data['data']['id'])
        self.assertEqual((campaign.company_user, campaign.status, campaign.smtp_host), (self.cu, 'draft',
                                                                                         'smtp.example.com'))
        self.assertTrue(campaign.steps.exists())                   # the default sequence, with no AI behind it
        self.assertNotIn('smtp_password', resp.data['data'])
        self.logins.assert_called_once()

    def test_a_start_date_makes_it_scheduled_and_the_end_date_comes_after_it(self):
        start = (timezone.now().date() + timedelta(days=3)).isoformat()
        resp = self.create(start_date=start, end_date='2000-01-01')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['data']['status'], 'scheduled')
        self.assertGreaterEqual(resp.data['data']['end_date'], start)

    def test_the_list_shows_my_campaigns_and_not_another_companys(self):
        self.rival()
        names = [c['name'] for c in self.call(views.sdr_campaigns_list).data['data']]
        self.assertEqual(names, ['C1'])

    def test_an_admin_sees_a_colleagues_campaign_but_a_member_does_not_see_the_admins(self):
        member = self.colleague()
        SDRCampaign.objects.create(company_user=member, name='Mine as member')
        admin_sees = {c['name'] for c in self.call(views.sdr_campaigns_list).data['data']}
        member_sees = {c['name'] for c in self.call(views.sdr_campaigns_list, user=member).data['data']}
        self.assertEqual(admin_sees, {'C1', 'Mine as member'})
        self.assertEqual(member_sees, {'Mine as member'})


# ── Campaigns: read, change, delete ──────────────────────────────────────────

class CampaignDetailTests(CampaignApiBase):

    def put(self, data, campaign=None, user=None):
        return self.call(views.sdr_campaign_detail, 'put', data, user=user,
                         campaign_id=(campaign or self.campaign).id)

    def test_it_shows_the_campaign_with_its_steps(self):
        data = self.call(views.sdr_campaign_detail, campaign_id=self.campaign.id).data['data']
        self.assertEqual((data['name'], [s['subject_template'] for s in data['steps']]),
                         ('C1', ['Hello', 'Follow up']))

    def test_an_unknown_campaign_is_not_found(self):
        for method in ('get', 'put', 'delete'):
            resp = self.call(views.sdr_campaign_detail, method, {'name': 'x'}, campaign_id=999999)
            self.assert_refused(resp, 404, 'not found')

    def test_another_companys_campaign_cannot_be_read_changed_or_deleted(self):
        _, theirs, *_ = self.rival()
        for method in ('get', 'put', 'delete'):
            resp = self.call(views.sdr_campaign_detail, method, {'name': 'Hijacked', 'status': 'paused'},
                             campaign_id=theirs.id)
            self.assert_refused(resp, 404, 'not found')
        theirs.refresh_from_db()
        self.assertEqual((theirs.name, theirs.status), ('Theirs', 'active'))

    def test_a_member_cannot_see_or_change_the_admins_campaign(self):
        member = self.colleague()
        self.assertEqual(self.call(views.sdr_campaign_detail, user=member, campaign_id=self.campaign.id)
                         .status_code, 404)
        self.assertEqual(self.put({'status': 'paused'}, user=member).status_code, 404)
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).status, 'active')

    def test_an_admin_may_pause_a_colleagues_campaign_but_not_rewrite_it(self):
        member = self.colleague()
        theirs = SDRCampaign.objects.create(company_user=member, name='Member C', status='active',
                                            smtp_host='smtp.test', smtp_username='u', smtp_password='p')
        self.assert_refused(self.put({'name': 'Renamed'}, theirs), 403, "colleague's campaign")
        self.assertEqual(self.put({'status': 'paused'}, theirs).status_code, 200)
        theirs.refresh_from_db()
        self.assertEqual((theirs.name, theirs.status), ('Member C', 'paused'))

    def test_a_name_cannot_be_emptied(self):
        resp = self.put({'name': '   '})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).name, 'C1')

    def test_an_unknown_status_is_refused(self):
        self.assert_refused(self.put({'status': 'flying'}), says='status')

    def test_a_port_that_is_not_a_number_is_refused(self):
        self.assert_refused(self.put({'smtp_port': 'abc'}), says='port')
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).smtp_port, 587)

    def test_a_start_date_that_is_not_a_date_is_refused(self):
        resp = self.put({'start_date': '31/31/2031'})
        self.assert_refused(resp)

    def test_the_mailbox_of_a_campaign_with_leads_cannot_be_removed(self):
        self.enroll(self.make_lead())
        self.assert_refused(self.put({'smtp_host': ''}), says='not removed')
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).smtp_host, 'smtp.test')

    def test_a_campaign_without_steps_cannot_be_started(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='paused')
        self.campaign.steps.all().delete()
        self.assert_refused(self.put({'status': 'active'}), says='step')

    def test_a_good_change_is_saved(self):
        resp = self.put({'name': 'Renamed', 'sender_name': 'Sue', 'smtp_port': 465})
        self.assertEqual(resp.status_code, 200, resp.data)
        campaign = SDRCampaign.objects.get(pk=self.campaign.pk)
        self.assertEqual((campaign.name, campaign.sender_name, campaign.smtp_port), ('Renamed', 'Sue', 465))

    def test_patch_is_not_offered(self):
        resp = self.call(views.sdr_campaign_detail, 'patch', {'name': 'x'}, campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 405)

    def test_deleting_removes_it_and_cancels_its_open_call(self):
        enrolment = self.enroll(self.make_lead())
        meeting = SDRMeeting.objects.create(company_user=self.cu, lead=enrolment.lead, enrollment=enrolment,
                                            status='pending')
        self.assertEqual(self.call(views.sdr_campaign_detail, 'delete', campaign_id=self.campaign.id).status_code,
                         200)
        self.assertFalse(SDRCampaign.objects.filter(pk=self.campaign.pk).exists())
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'cancelled')


# ── Steps ────────────────────────────────────────────────────────────────────

class StepListTests(CampaignApiBase):

    def add(self, user=None, campaign=None, **data):
        body = {'subject_template': 'Quick idea', 'body_template': 'Hi {{first_name}}', 'delay_days': 4, **data}
        return self.call(views.sdr_campaign_steps, 'post', body, user=user,
                         campaign_id=(campaign or self.campaign).id)

    def test_a_good_step_is_added_at_the_end(self):
        resp = self.add()
        self.assertEqual(resp.status_code, 201, resp.data)
        step = SDRCampaignStep.objects.get(pk=resp.data['data']['id'])
        self.assertEqual((step.step_order, step.delay_days, step.subject_template), (3, 4, 'Quick idea'))

    def test_the_steps_are_listed(self):
        data = self.call(views.sdr_campaign_steps, campaign_id=self.campaign.id).data['data']
        self.assertEqual([s['step_order'] for s in data], [1, 2])

    def test_a_step_without_a_subject_or_text_is_refused(self):
        for field in ('subject_template', 'body_template'):
            for empty in ('', '   '):
                resp = self.add(**{field: empty})
                self.assertEqual(resp.status_code, 400, (field, empty, resp.data))
        self.assertEqual(self.campaign.steps.count(), 2)

    def test_a_delay_that_is_not_a_number_is_refused(self):
        self.assert_refused(self.add(delay_days='soon'))
        self.assertEqual(self.campaign.steps.count(), 2)

    def test_a_negative_delay_is_refused(self):
        resp = self.add(delay_days=-3)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertFalse(self.campaign.steps.filter(delay_days__lt=0).exists())

    def test_a_step_order_that_is_not_a_number_is_refused(self):
        self.assert_refused(self.add(step_order='first'))

    def test_an_unknown_step_type_is_refused(self):
        resp = self.add(step_type='fax')
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertFalse(self.campaign.steps.filter(step_type='fax').exists())

    def test_another_companys_campaign_gets_no_step_and_shows_none(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.add(campaign=theirs), 404, 'not found')
        self.assertEqual(self.call(views.sdr_campaign_steps, campaign_id=theirs.id).status_code, 404)
        self.assertEqual(theirs.steps.count(), 1)

    def test_an_admin_sees_a_colleagues_steps_but_cannot_add_one(self):
        member = self.colleague()
        theirs = SDRCampaign.objects.create(company_user=member, name='Member C')
        self.assertEqual(self.call(views.sdr_campaign_steps, campaign_id=theirs.id).status_code, 200)
        self.assertEqual(self.add(campaign=theirs).status_code, 404)
        self.assertFalse(theirs.steps.exists())


class StepDetailTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.step = self.campaign.steps.get(step_order=1)

    def put(self, data, step=None, campaign=None, user=None):
        step = step or self.step
        return self.call(views.sdr_campaign_step_detail, 'put', data, user=user,
                         campaign_id=(campaign or step.campaign).id, step_id=step.id)

    def test_a_good_change_is_saved(self):
        resp = self.put({'subject_template': 'New hello', 'body_template': 'New text', 'delay_days': 2,
                         'step_order': 1, 'ai_personalize': True})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.step.refresh_from_db()
        self.assertEqual((self.step.subject_template, self.step.body_template, self.step.delay_days,
                          self.step.ai_personalize), ('New hello', 'New text', 2, True))

    def test_a_delay_that_is_not_a_number_is_refused_and_the_step_kept(self):
        self.assert_refused(self.put({'delay_days': 'two'}))
        self.step.refresh_from_db()
        self.assertEqual(self.step.delay_days, 1)

    def test_a_negative_delay_is_refused(self):
        resp = self.put({'delay_days': -5})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.step.refresh_from_db()
        self.assertEqual(self.step.delay_days, 1)

    def test_a_step_order_that_is_not_a_number_is_refused(self):
        self.assert_refused(self.put({'step_order': 'one'}))

    def test_the_subject_or_text_cannot_be_emptied(self):
        for field in ('subject_template', 'body_template'):
            resp = self.put({field: '  '})
            self.assertEqual(resp.status_code, 400, (field, resp.data))
        self.step.refresh_from_db()
        self.assertEqual((self.step.subject_template, self.step.body_template), ('Hello', 'Hi there'))

    def test_an_unknown_step_is_not_found(self):
        resp = self.call(views.sdr_campaign_step_detail, 'put', {'name': 'x'}, campaign_id=self.campaign.id,
                         step_id=999999)
        self.assert_refused(resp, 404, 'not found')

    def test_a_step_named_under_the_wrong_campaign_is_not_found(self):
        other = SDRCampaign.objects.create(company_user=self.cu, name='Other')
        self.assertEqual(self.put({'name': 'x'}, campaign=other).status_code, 404)
        self.assertEqual(self.call(views.sdr_campaign_step_detail, 'delete', campaign_id=other.id,
                                   step_id=self.step.id).status_code, 404)
        self.assertTrue(SDRCampaignStep.objects.filter(pk=self.step.pk).exists())

    def test_another_companys_step_cannot_be_changed_or_deleted(self):
        _, theirs, their_step, *_ = self.rival()
        self.assert_refused(self.put({'subject_template': 'Hijacked'}, step=their_step), 404, 'not found')
        resp = self.call(views.sdr_campaign_step_detail, 'delete', campaign_id=theirs.id, step_id=their_step.id)
        self.assertEqual(resp.status_code, 404)
        their_step.refresh_from_db()
        self.assertEqual(their_step.subject_template, 'Their subject')

    def test_a_member_cannot_change_the_admins_step(self):
        self.assertEqual(self.put({'subject_template': 'x'}, user=self.colleague()).status_code, 404)
        self.step.refresh_from_db()
        self.assertEqual(self.step.subject_template, 'Hello')

    def test_deleting_removes_only_that_step(self):
        resp = self.call(views.sdr_campaign_step_detail, 'delete', campaign_id=self.campaign.id,
                         step_id=self.step.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(self.campaign.steps.values_list('step_order', flat=True)), [2])


class GenerateStepsTests(CampaignApiBase):

    def generate(self, campaign=None):
        return self.call(views.sdr_generate_steps, 'post', campaign_id=(campaign or self.campaign).id)

    def test_not_while_leads_are_part_way_through_a_sending_campaign(self):
        self.enroll(self.make_lead())
        resp = self.generate()
        self.assert_refused(resp, 409, 'pause the campaign')
        self.assertEqual(self.campaign.steps.count(), 2)

    def test_a_paused_campaign_gets_a_new_sequence(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='paused')
        resp = self.generate()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.campaign.steps.count(), len(resp.data['data']))
        self.assertFalse(self.campaign.steps.filter(subject_template='Hello').exists())

    def test_another_companys_steps_are_not_replaced(self):
        _, theirs, their_step, *_ = self.rival()
        self.assert_refused(self.generate(theirs), 404, 'not found')
        self.assertTrue(SDRCampaignStep.objects.filter(pk=their_step.pk).exists())


# ── Adding leads ─────────────────────────────────────────────────────────────

class EnrolTests(CampaignApiBase):

    def enrol(self, lead_ids, campaign=None, user=None):
        return self.call(views.sdr_enroll_leads, 'post', {'lead_ids': lead_ids}, user=user,
                         campaign_id=(campaign or self.campaign).id)

    def test_an_empty_list_is_refused(self):
        self.assert_refused(self.enrol([]), says='lead')
        self.assert_refused(self.call(views.sdr_enroll_leads, 'post', {}, campaign_id=self.campaign.id))

    def test_ids_that_are_not_numbers_are_refused(self):
        resp = self.enrol(['abc'])
        self.assert_refused(resp)
        self.assertFalse(SDRCampaignEnrollment.objects.exists())

    def test_unknown_leads_enrol_nobody(self):
        resp = self.enrol([999998, 999999])
        self.assertEqual((resp.status_code, resp.data['enrolled']), (200, 0))
        self.assertFalse(SDRCampaignEnrollment.objects.exists())

    def test_another_companys_lead_is_not_enrolled(self):
        *_, their_lead, _ = self.rival()
        self.assertEqual(self.enrol([their_lead.id]).data['enrolled'], 0)
        self.assertFalse(SDRCampaignEnrollment.objects.filter(campaign=self.campaign).exists())

    def test_an_address_on_the_do_not_email_list_is_skipped_with_a_reason(self):
        lead = self.make_lead('gone@customer.test')
        block(self.company, lead.email)
        resp = self.enrol([lead.id])
        self.assertEqual((resp.data['enrolled'], resp.data['skipped']), (0, 1))
        self.assertIn('unsubscribed', resp.data['skipped_reasons'][0])

    def test_a_lead_made_up_by_the_ai_is_skipped(self):
        lead = self.make_lead('made@up.test', source='ai_generated')
        resp = self.enrol([lead.id])
        self.assertEqual(resp.data['enrolled'], 0)
        self.assertIn('made up', resp.data['skipped_reasons'][0])

    def test_a_lead_already_in_the_campaign_is_not_enrolled_twice(self):
        lead = self.make_lead()
        self.enroll(lead)
        resp = self.enrol([lead.id])
        self.assertEqual((resp.data['enrolled'], resp.data['skipped']), (0, 1))
        self.assertEqual(SDRCampaignEnrollment.objects.filter(lead=lead).count(), 1)

    def test_a_campaign_without_a_mailbox_takes_no_leads(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_password='')
        self.assert_refused(self.enrol([self.make_lead().id]), says='smtp')
        self.assertFalse(SDRCampaignEnrollment.objects.exists())

    def test_good_leads_are_enrolled_and_counted(self):
        leads = [self.make_lead(f'p{n}@customer.test') for n in range(3)]
        resp = self.enrol([lead.id for lead in leads])
        self.assertEqual((resp.status_code, resp.data['enrolled'], resp.data['total_leads']), (200, 3, 3))
        enrolment = SDRCampaignEnrollment.objects.get(lead=leads[0])
        self.assertEqual((enrolment.status, enrolment.current_step), ('active', 0))
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).total_leads, 3)

    def test_leads_cannot_be_added_to_another_companys_campaign(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.enrol([self.make_lead().id], campaign=theirs), 404, 'not found')
        self.assertEqual(theirs.enrollments.count(), 1)

    def test_an_admin_cannot_add_leads_to_a_colleagues_campaign(self):
        member = self.colleague()
        theirs = SDRCampaign.objects.create(company_user=member, name='M', smtp_host='h', smtp_username='u',
                                            smtp_password='p')
        self.assertEqual(self.enrol([self.make_lead().id], campaign=theirs).status_code, 404)
        self.assertFalse(theirs.enrollments.exists())


class EnrolmentListTests(CampaignApiBase):

    def test_the_campaigns_leads_are_listed_with_their_progress(self):
        self.enroll(self.make_lead())
        [row] = self.call(views.sdr_campaign_enrollments, campaign_id=self.campaign.id).data['data']
        self.assertEqual((row['lead_email'], row['status'], row['total_steps']), ('bob@acme.com', 'active', 2))

    def test_another_companys_leads_are_not_listed(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.call(views.sdr_campaign_enrollments, campaign_id=theirs.id), 404, 'not found')

    def test_a_member_cannot_list_the_admins_leads(self):
        resp = self.call(views.sdr_campaign_enrollments, user=self.colleague(), campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 404)


# ── Sending ──────────────────────────────────────────────────────────────────

class ProcessOutreachTests(CampaignApiBase):

    def test_nothing_to_send_is_a_plain_success(self):
        resp = self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id)
        self.assertEqual((resp.status_code, resp.data['processed']), (200, 0))

    def test_a_due_lead_is_sent_the_first_step(self):
        enrolment = self.enroll(self.make_lead())
        resp = self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id)
        self.assertEqual((resp.status_code, resp.data['sent']), (200, 1), resp.data)
        self.smtp.assert_called_once()
        enrolment.refresh_from_db()
        self.assertEqual(enrolment.current_step, 1)
        self.assertEqual(SDROutreachLog.objects.filter(enrollment=enrolment, status='sent').count(), 1)

    def test_another_companys_campaign_cannot_be_sent(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.call(views.sdr_process_outreach, 'post', campaign_id=theirs.id), 404, 'not found')
        self.smtp.assert_not_called()

    def test_an_admin_cannot_send_a_colleagues_campaign(self):
        member = self.colleague()
        theirs = SDRCampaign.objects.create(company_user=member, name='M', status='active')
        self.assertEqual(self.call(views.sdr_process_outreach, 'post', campaign_id=theirs.id).status_code, 404)


class RetryAndClearTests(CampaignApiBase):

    def test_leads_parked_after_failed_sends_go_back_in(self):
        enrolment = self.enroll(self.make_lead(), reply_sentiment='send_failed')
        SDRCampaignEnrollment.objects.filter(pk=enrolment.pk).update(status='paused')
        resp = self.call(views.sdr_retry_failed, 'post', campaign_id=self.campaign.id)
        self.assertEqual(resp.data['retried'], 1)
        enrolment.refresh_from_db()
        self.assertEqual((enrolment.status, enrolment.reply_sentiment), ('active', ''))

    def test_another_companys_failed_leads_are_not_retried(self):
        _, theirs, _, _, their_enrolment = self.rival()
        SDRCampaignEnrollment.objects.filter(pk=their_enrolment.pk).update(status='paused',
                                                                           reply_sentiment='send_failed')
        self.assert_refused(self.call(views.sdr_retry_failed, 'post', campaign_id=theirs.id), 404, 'not found')
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=their_enrolment.pk).status, 'paused')

    def test_clearing_removes_the_leads_and_recounts(self):
        self.enroll(self.make_lead('a@customer.test'))
        self.enroll(self.make_lead('b@customer.test'))
        resp = self.call(views.sdr_clear_campaign_leads, 'post', campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(self.campaign.enrollments.exists())
        self.assertEqual(resp.data['data']['total_leads'], 0)

    def test_clearing_chosen_ids_never_reaches_another_campaigns_leads(self):
        mine = self.enroll(self.make_lead('a@customer.test'))
        *_, their_enrolment = self.rival()
        self.call(views.sdr_clear_campaign_leads, 'post', {'enrollment_ids': [mine.id, their_enrolment.id]},
                  campaign_id=self.campaign.id)
        self.assertFalse(SDRCampaignEnrollment.objects.filter(pk=mine.pk).exists())
        self.assertTrue(SDRCampaignEnrollment.objects.filter(pk=their_enrolment.pk).exists())

    def test_another_companys_campaign_cannot_be_cleared(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.call(views.sdr_clear_campaign_leads, 'post', campaign_id=theirs.id), 404)
        self.assertEqual(theirs.enrollments.count(), 1)


# ── Replies marked by hand, and undoing them ─────────────────────────────────

class MarkRepliedTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead()
        self.enrolment = self.enroll(self.lead)
        self.meetings = self.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent')
        self.meetings.return_value.generate_prep_notes.return_value = {'summary': 'prep'}
        self.meetings.return_value.send_scheduling_email_once.return_value = True

    def mark(self, data=None, enrolment=None, campaign=None, user=None):
        enrolment = enrolment or self.enrolment
        return self.call(views.sdr_mark_replied, 'post', data or {}, user=user,
                         campaign_id=(campaign or enrolment.campaign).id, enrollment_id=enrolment.id)

    def test_marking_without_text_counts_as_interest_and_stops_the_sequence(self):
        resp = self.mark()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual((resp.data['category'], resp.data['meeting_created']), ('positive_interest', True))
        self.enrolment.refresh_from_db()
        self.assertEqual(self.enrolment.status, 'replied')
        self.assertTrue(SDRMeeting.objects.filter(enrollment=self.enrolment).exists())
        sent = self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id)
        self.assertEqual(sent.data['processed'], 0)                 # no more steps go to them
        self.smtp.assert_not_called()

    def test_a_reply_saying_no_ends_this_campaign_for_the_lead(self):
        with mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent.classify_reply',
                        return_value=NOT_INTERESTED):
            resp = self.mark({'reply_content': 'No thanks'})
        self.assertEqual((resp.status_code, resp.data['action_taken']), (200, 'not_interested'))
        self.enrolment.refresh_from_db(); self.lead.refresh_from_db()
        self.assertEqual((self.enrolment.status, self.enrolment.reply_content, self.lead.status),
                         ('completed', 'No thanks', 'disqualified'))

    def test_reply_text_that_is_not_text_is_refused(self):
        resp = self.mark({'reply_content': ['not', 'text']})
        self.assert_refused(resp)
        self.enrolment.refresh_from_db()
        self.assertEqual(self.enrolment.status, 'active')

    def test_an_unknown_enrolment_is_not_found(self):
        resp = self.call(views.sdr_mark_replied, 'post', {}, campaign_id=self.campaign.id, enrollment_id=999999)
        self.assert_refused(resp, 404, 'not found')

    def test_an_enrolment_named_under_another_campaign_is_not_found(self):
        other = SDRCampaign.objects.create(company_user=self.cu, name='Other')
        self.assertEqual(self.mark(campaign=other).status_code, 404)
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=self.enrolment.pk).status, 'active')

    def test_another_companys_lead_cannot_be_marked(self):
        *_, their_enrolment = self.rival()
        self.assert_refused(self.mark(enrolment=their_enrolment), 404, 'not found')
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=their_enrolment.pk).status, 'active')
        self.assertFalse(SDRMeeting.objects.exists())


class ResetEnrolmentTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead()
        self.enrolment = self.enroll(self.lead)

    def reset(self, enrolment=None, campaign=None, user=None):
        enrolment = enrolment or self.enrolment
        return self.call(views.sdr_reset_enrollment, 'post', user=user,
                         campaign_id=(campaign or enrolment.campaign).id, enrollment_id=enrolment.id)

    def test_a_finished_lead_is_put_back_at_the_start(self):
        SDRCampaignEnrollment.objects.filter(pk=self.enrolment.pk).update(
            status='completed', current_step=2, reply_content='hi', reply_sentiment='neutral',
            replied_at=timezone.now(), completed_at=timezone.now())
        resp = self.reset()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn('reset', resp.data['message'])
        self.enrolment.refresh_from_db()
        self.assertEqual((self.enrolment.status, self.enrolment.current_step, self.enrolment.reply_content,
                          self.enrolment.reply_sentiment, self.enrolment.replied_at, self.enrolment.completed_at),
                         ('active', 0, '', '', None, None))

    def test_a_lead_who_unsubscribed_is_not_put_back(self):
        SDRCampaignEnrollment.objects.filter(pk=self.enrolment.pk).update(status='unsubscribed')
        block(self.company, self.lead.email)
        resp = self.reset()
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=self.enrolment.pk).status, 'unsubscribed')

    def test_an_unknown_enrolment_or_campaign_is_not_found(self):
        self.assert_refused(self.call(views.sdr_reset_enrollment, 'post', campaign_id=self.campaign.id,
                                      enrollment_id=999999), 404, 'not found')
        self.assert_refused(self.call(views.sdr_reset_enrollment, 'post', campaign_id=999999,
                                      enrollment_id=self.enrolment.id), 404, 'not found')

    def test_an_enrolment_named_under_another_campaign_is_not_found(self):
        other = SDRCampaign.objects.create(company_user=self.cu, name='Other')
        self.assertEqual(self.reset(campaign=other).status_code, 404)

    def test_another_companys_lead_cannot_be_reset(self):
        *_, their_enrolment = self.rival()
        SDRCampaignEnrollment.objects.filter(pk=their_enrolment.pk).update(status='completed', current_step=1)
        self.assertEqual(self.reset(enrolment=their_enrolment).status_code, 404)
        their_enrolment.refresh_from_db()
        self.assertEqual((their_enrolment.status, their_enrolment.current_step), ('completed', 1))


# ── Replies read from the inbox ──────────────────────────────────────────────

class CheckRepliesTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead()
        self.enrolment = self.enroll(self.lead)
        self.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent.classify_reply',
                   return_value=NOT_INTERESTED)

    def lead_writes(self, text='Not for us, thanks'):
        def replies(campaign, enrollments):
            return [{'enrollment': e, 'reply_text': text, 'sender_email': e.lead.email, 'subject': 'Re: Hello',
                     'message_id': f'<{e.id}@mail>', 'received_at': timezone.now()} for e in enrollments]
        self.inbox.side_effect = replies

    def test_a_reply_in_the_inbox_is_acted_on(self):
        self.lead_writes()
        resp = self.call(views.sdr_check_replies, 'post', campaign_id=self.campaign.id)
        self.assertEqual((resp.status_code, resp.data['checked'], resp.data['new_replies']), (200, 1, 1), resp.data)
        self.enrolment.refresh_from_db()
        self.assertEqual((self.enrolment.status, self.enrolment.reply_sentiment), ('completed', 'not_interested'))
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).replies_received, 1)

    def test_the_same_reply_read_twice_is_counted_once(self):
        self.lead_writes()
        self.call(views.sdr_check_replies, 'post', campaign_id=self.campaign.id)
        again = self.call(views.sdr_check_replies, 'post', campaign_id=self.campaign.id)
        self.assertEqual(again.data['new_replies'], 0)
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).replies_received, 1)

    def test_an_inbox_that_cannot_be_read_says_so(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_password='')
        resp = self.call(views.sdr_check_replies, 'post', campaign_id=self.campaign.id)
        self.assert_refused(resp, says='inbox')
        self.assertEqual(resp.data['code'], 'inbox_unreadable')
        self.assertTrue(SDRCampaign.objects.get(pk=self.campaign.pk).inbox_error)

    def test_another_companys_inbox_is_not_read(self):
        _, theirs, *_ = self.rival()
        self.assert_refused(self.call(views.sdr_check_replies, 'post', campaign_id=theirs.id), 404, 'not found')
        self.inbox.assert_not_called()

    def test_check_all_reads_only_my_campaigns(self):
        _, theirs, _, _, their_enrolment = self.rival()
        self.lead_writes()
        resp = self.call(views.sdr_check_all_replies, 'post')
        self.assertEqual((resp.status_code, resp.data['campaigns_checked'], resp.data['new_replies']), (200, 1, 1))
        self.assertEqual([c.args[0].id for c in self.inbox.call_args_list], [self.campaign.id])
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=their_enrolment.pk).status, 'active')
        self.assertIsNotNone(SDRCampaign.objects.get(pk=self.campaign.pk).last_replies_checked_at)
        self.assertIsNone(SDRCampaign.objects.get(pk=theirs.pk).last_replies_checked_at)

    def test_check_all_names_a_campaign_whose_inbox_cannot_be_read(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_password='')
        resp = self.call(views.sdr_check_all_replies, 'post')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['errors']), 1)
        self.assertIn('C1', resp.data['errors'][0])

    def test_check_all_skips_campaigns_whose_owner_turned_reading_off(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(auto_check_replies=False)
        resp = self.call(views.sdr_check_all_replies, 'post')
        self.assertEqual(resp.data['campaigns_checked'], 0)
        self.inbox.assert_not_called()


# ── The AI's answers held for a person ───────────────────────────────────────

class ReplyDraftTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.enrolment = self.enroll(self.make_lead())
        self.draft = SDRReplyDraft.objects.create(enrollment=self.enrolment, lead_reply='Tell me more',
                                                  subject='More about Acme', body='Here is more.')

    def decide(self, decision, draft=None, data=None, user=None):
        return self.call(views.sdr_reply_draft_decide, 'post', data or {}, user=user,
                         draft_id=(draft or self.draft).id, decision=decision)

    def their_draft(self):
        *_, their_enrolment = self.rival()
        return SDRReplyDraft.objects.create(enrollment=their_enrolment, subject='S', body='B')

    def test_the_waiting_answers_are_listed(self):
        [row] = self.call(views.sdr_reply_drafts, campaign_id=self.campaign.id).data['data']
        self.assertEqual((row['id'], row['subject']), (self.draft.id, 'More about Acme'))

    def test_another_companys_answers_are_not_listed(self):
        self.their_draft()
        theirs = SDRCampaign.objects.get(name='Theirs')
        self.assert_refused(self.call(views.sdr_reply_drafts, campaign_id=theirs.id), 404, 'not found')

    def test_discarding_keeps_it_from_being_sent(self):
        resp = self.decide('discard')
        self.assertEqual((resp.status_code, resp.data['data']['status']), (200, 'discarded'))
        self.smtp.assert_not_called()

    def test_sending_with_an_empty_subject_is_refused(self):
        resp = self.decide('send', data={'subject': '  ', 'body': 'x'})
        self.assert_refused(resp, says='subject')
        self.assertEqual(SDRReplyDraft.objects.get(pk=self.draft.pk).status, 'pending')

    def test_sending_sends_the_changed_words_once(self):
        with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent.send_email') as send:
            resp = self.decide('send', data={'subject': 'Edited', 'body': 'Edited text'})
            again = self.decide('send')
        self.assertEqual((resp.status_code, resp.data['data']['status']), (200, 'sent'))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[2:4], ('Edited', 'Edited text'))
        self.assert_refused(again, says='already')

    def test_another_companys_answer_cannot_be_sent_or_discarded(self):
        theirs = self.their_draft()
        for decision in ('send', 'discard'):
            self.assert_refused(self.decide(decision, draft=theirs), 404, 'not found')
        self.assertEqual(SDRReplyDraft.objects.get(pk=theirs.pk).status, 'pending')

    def test_an_unknown_answer_is_not_found(self):
        resp = self.call(views.sdr_reply_draft_decide, 'post', draft_id=999999, decision='discard')
        self.assert_refused(resp, 404, 'not found')


# ── Dashboard, analytics, daily summary, scheduler ───────────────────────────

class DashboardTests(CampaignApiBase):

    def test_the_figures_count_my_leads_only(self):
        self.make_lead('h@c.test', temperature='hot', score=90)
        self.make_lead('w@c.test', temperature='warm', score=65)
        self.make_lead('c@c.test', temperature='cold', score=20)
        self.make_lead('u@c.test')
        self.rival()                                         # a hot lead of theirs
        data = self.call(views.sdr_dashboard).data['data']
        self.assertEqual({k: data['stats'][k] for k in ('total', 'hot', 'warm', 'cold', 'unscored')},
                         {'total': 4, 'hot': 1, 'warm': 1, 'cold': 1, 'unscored': 1})
        self.assertEqual([l['email'] for l in data['recent_hot_leads']], ['h@c.test'])

    def test_an_empty_account_shows_zeros(self):
        data = self.call(views.sdr_dashboard).data['data']
        self.assertEqual((data['stats']['total'], data['recent_hot_leads']), (0, []))


class AnalyticsTests(CampaignApiBase):

    def test_the_figures_match_the_rows(self):
        now = timezone.now()
        a = self.enroll(self.make_lead('a@c.test'))
        b = self.enroll(self.make_lead('b@c.test'))
        for enrolment in (a, b):
            SDROutreachLog.objects.create(enrollment=enrolment, step_order=1, action_type='email', status='sent',
                                          sent_at=now)
        SDROutreachLog.objects.create(enrollment=b, step_order=2, action_type='email', status='failed', sent_at=now)
        SDRCampaignEnrollment.objects.filter(pk=a.pk).update(status='replied', reply_content='Yes please',
                                                             reply_sentiment='positive', replied_at=now)
        SDRMeeting.objects.create(company_user=self.cu, lead=a.lead, enrollment=a, status='scheduled',
                                  scheduled_at=now + timedelta(days=2), confirmed_at=now)
        self.rival()
        data = self.call(views.sdr_analytics).data['data']
        self.assertEqual({k: data[k] for k in ('leads_total', 'emails_total', 'emails_today', 'emails_failed',
                                                'replied_total', 'meetings_total', 'meetings_scheduled',
                                                'campaigns_active', 'campaigns_total', 'meeting_rate')},
                         {'leads_total': 2, 'emails_total': 2, 'emails_today': 2, 'emails_failed': 1,
                          'replied_total': 1, 'meetings_total': 1, 'meetings_scheduled': 1,
                          'campaigns_active': 1, 'campaigns_total': 1, 'meeting_rate': 100.0})
        self.assertEqual([s['count'] for s in data['funnel'][:4]], [2, 2, 1, 1])

    def test_an_away_message_is_not_a_reply_and_an_unconfirmed_call_is_not_booked(self):
        enrolment = self.enroll(self.make_lead())
        SDRCampaignEnrollment.objects.filter(pk=enrolment.pk).update(
            reply_content='Out until Monday', reply_sentiment='out_of_office', replied_at=timezone.now())
        SDRMeeting.objects.create(company_user=self.cu, lead=enrolment.lead, enrollment=enrolment, status='pending')
        data = self.call(views.sdr_analytics).data['data']
        self.assertEqual((data['replied_total'], data['meetings_total']), (0, 0))


class DailySummaryTests(CampaignApiBase):

    def test_the_summary_goes_to_the_signed_in_person_only(self):
        resp = self.call(views.sdr_send_daily_summary, 'post')
        self.assertEqual((resp.status_code, resp.data['sent']), (200, True))
        self.assertEqual([m.to for m in mail.outbox], [['cu@test.local']])

    def test_a_login_without_an_email_sends_nothing(self):
        CompanyUser.objects.filter(pk=self.cu.pk).update(email='')
        self.cu.refresh_from_db()
        resp = self.call(views.sdr_send_daily_summary, 'post')
        self.assertEqual((resp.status_code, resp.data['sent']), (200, False))
        self.assertEqual(mail.outbox, [])


class SchedulerStatusTests(CampaignApiBase):

    def test_it_says_whether_the_scheduler_runs_and_lists_jobs(self):
        resp = self.call(views.sdr_scheduler_status)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('running', resp.data['data'])
        self.assertIsInstance(resp.data['data']['jobs'], list)

    def test_a_running_scheduler_lists_its_jobs(self):
        job = mock.MagicMock(id='send_due_steps', next_run_time=timezone.now())
        job.name = 'Send due steps'
        fake = mock.MagicMock(running=True)
        fake.get_jobs.return_value = [job]
        with mock.patch('ai_sdr_agent.scheduler._scheduler', fake):
            data = self.call(views.sdr_scheduler_status).data['data']
        self.assertEqual((data['running'], [j['id'] for j in data['jobs']]), (True, ['send_due_steps']))


# ── The email assistant ──────────────────────────────────────────────────────

class EmailAssistantTests(CampaignApiBase):

    def setUp(self):
        super().setUp()
        self.ask = self.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent._ask_json',
                              return_value={'subject': 'Hi Ann', 'body': 'Short note.'})

    def write(self, **data):
        return self.call(views.sdr_assistant_write, 'post', {'name': 'Ann', 'company': 'Globex', **data})

    def test_writing_needs_a_name_or_a_company(self):
        resp = self.call(views.sdr_assistant_write, 'post', {'name': '', 'company': '', 'notes': 'x'})
        self.assert_refused(resp, says='name or company')
        self.ask.assert_not_called()

    def test_an_email_is_written_from_what_was_typed(self):
        resp = self.write(kind='follow_up', tone='friendly', offer='Payroll software')
        self.assertEqual((resp.status_code, resp.data['data']), (200, {'subject': 'Hi Ann', 'body': 'Short note.'}))
        prompt = self.ask.call_args.args[0]
        self.assertIn('Globex', prompt)
        self.assertIn('follow-up', prompt)
        self.assertIn('Payroll software', prompt)

    def test_an_unknown_kind_or_tone_is_refused(self):
        for bad in ({'kind': 'ransom_note'}, {'tone': 'rude'}):
            resp = self.write(**bad)
            self.assertEqual(resp.status_code, 400, (bad, resp.data))
        self.ask.assert_not_called()

    def test_another_companys_campaign_lends_nothing_to_the_email(self):
        _, theirs, *_ = self.rival()
        SDRCampaign.objects.filter(pk=theirs.pk).update(sender_name='Mallory', description='Secret rival offer')
        self.write(campaign_id=theirs.id)
        prompt = self.ask.call_args.args[0]
        self.assertNotIn('Mallory', prompt)
        self.assertNotIn('Secret rival offer', prompt)

    def test_my_campaign_supplies_the_sender_and_offer(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(description='Bookkeeping for clinics')
        self.write(campaign_id=self.campaign.id)
        prompt = self.ask.call_args.args[0]
        self.assertIn('Sam', prompt)
        self.assertIn('Bookkeeping for clinics', prompt)

    def test_the_ai_failing_is_a_readable_502_not_a_500(self):
        self.ask.side_effect = RuntimeError('connection reset')
        resp = self.write()
        self.assert_refused(resp, 502, 'could not write')

    def test_reading_needs_a_reply(self):
        for empty in ('', '   ', None):
            resp = self.call(views.sdr_assistant_read, 'post', {'reply': empty})
            self.assert_refused(resp, says='reply')
        self.ask.assert_not_called()

    def test_a_reply_is_read_and_answered(self):
        with mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent.classify_reply',
                        return_value={**NOT_INTERESTED}), \
                mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent._checked_answer',
                           side_effect=lambda facts, words, body: body):
            resp = self.call(views.sdr_assistant_read, 'post', {'reply': 'Not for us, thanks'})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual((resp.data['data']['category'], resp.data['data']['answer']['body']),
                         ('not_interested', 'Short note.'))

    def test_no_ai_available_is_a_readable_400(self):
        self.ask.side_effect = ValueError('The AI is not available for your company right now.')
        resp = self.call(views.sdr_assistant_read, 'post', {'reply': 'Interested, call me'})
        self.assertIn(resp.status_code, (400,))
        self.assertIn('not available', resp.data['message'])
