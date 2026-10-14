"""When a salesperson's login is switched off, the company keeps control of their campaigns.

Every campaign is filed under the login that made it and every screen asked
only for that login's rows. The background jobs picked campaigns by status and
never looked at whether the owning login was still active. So switching a login
off left its campaigns sending, its stored mailbox password in use every five
minutes and the AI answering leads for someone who had left, and nobody else in
the company, the owner included, could see or stop them.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import leavers
from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign, SDRCampaignStep, SDRMeeting
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from api.views import company_logins
from core.leavers import login_switched_off
from core.models import Company, CompanyUser
from hr_agent import access
from hr_agent.models import Employee
from project_manager_agent.models import PMNotification


class LeaversTestCase(SDRBase):
    """`self.cu` is the admin. Sal sells; it is Sal who leaves."""

    def setUp(self):
        super().setUp()
        self.sal = CompanyUser.objects.create(company=self.company, email='sal@acme.test', full_name='Sal Seller',
                                              role='company_user', password_hash='x', is_active=True)
        self.sals = SDRCampaign.objects.create(
            company_user=self.sal, name='Sal spring', status='active', sender_name='Sal', smtp_host='smtp.test',
            smtp_username='u', smtp_password='p')
        SDRCampaignStep.objects.create(campaign=self.sals, step_order=1, delay_days=1, step_type='email',
                                       subject_template='Hello', body_template='Hi', ai_personalize=False)
        self.sals_lead = self.make_lead_for(self.sal, 'lead@customer.test')
        self.enroll(self.sals_lead, campaign=self.sals)

    def make_lead_for(self, login, email):
        from ai_sdr_agent.models import SDRLead
        return SDRLead.objects.create(company_user=login, email=email, first_name='Lee', full_name='Lee Lead')

    def switch_off(self, login=None, by=None):
        login = login or self.sal
        CompanyUser.objects.filter(pk=login.pk).update(is_active=False)
        login.refresh_from_db()
        return login_switched_off(login, by=by)

    def status(self, campaign=None):
        return SDRCampaign.objects.get(pk=(campaign or self.sals).pk).status

    def call(self, view, actor, method='get', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=actor)
        with mock.patch.object(views, '_validate_mail_settings', return_value=None):
            return view(request, **kwargs)


class SwitchedOffTests(LeaversTestCase):

    def test_their_running_and_scheduled_campaigns_are_paused_and_say_why(self):
        later = SDRCampaign.objects.create(company_user=self.sal, name='Sal autumn', status='scheduled',
                                           start_date=timezone.now().date() + timedelta(days=3))
        draft = SDRCampaign.objects.create(company_user=self.sal, name='Sal draft', status='draft')

        said = self.switch_off()

        self.assertEqual((self.status(), self.status(later), self.status(draft)), ('paused', 'paused', 'draft'))
        self.assertIn("Sal Seller's login was switched off", SDRCampaign.objects.get(pk=self.sals.pk).paused_reason)
        self.assertEqual(len(said), 1)
        self.assertIn('2 sales campaigns of theirs were paused', said[0])
        self.assertIn('"Sal spring"', said[0])

    def test_nobody_elses_campaigns_are_touched(self):
        self.switch_off()
        self.assertEqual(self.status(self.campaign), 'active')            # the admin's own

    def test_the_admins_are_told(self):
        self.switch_off()
        [alert] = PMNotification.objects.filter(company_user=self.cu)
        self.assertIn("Sal Seller's login was switched off", alert.title)
        self.assertIn('Sal spring', alert.message)

    def test_someone_with_nothing_running_makes_no_noise(self):
        SDRCampaign.objects.filter(company_user=self.sal).update(status='draft')
        self.assertEqual(self.switch_off(), [])
        self.assertFalse(PMNotification.objects.filter(company_user=self.cu).exists())

    def test_switching_the_login_back_on_does_not_start_them_again(self):
        self.switch_off()
        CompanyUser.objects.filter(pk=self.sal.pk).update(is_active=True)
        self.assertEqual(self.status(), 'paused')


class BothWaysOfSwitchingOffTests(LeaversTestCase):

    def test_an_admin_switching_the_login_off_on_logins_and_roles(self):
        response = self.call(company_logins.company_login, self.cu, 'patch', {'is_active': False},
                             login_id=self.sal.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.status(), 'paused')
        self.assertIn('1 sales campaign of theirs was paused', response.data['switched_off'][0])

    def test_changing_only_a_role_pauses_nothing(self):
        response = self.call(company_logins.company_login, self.cu, 'patch', {'role': 'manager'},
                             login_id=self.sal.id)
        self.assertEqual((response.status_code, response.data['switched_off'], self.status()), (200, [], 'active'))

    def test_hr_offboarding_the_person(self):
        from api.views.hr_agent import _hr_get_or_create_user_for_company_user
        employee = Employee.objects.create(
            company=self.company, company_user=self.sal, user=_hr_get_or_create_user_for_company_user(self.sal),
            full_name='Sal Seller', work_email='sal@acme.test', employment_status='active')
        access.end_access(employee)
        self.assertFalse(CompanyUser.objects.get(pk=self.sal.pk).is_active)
        self.assertEqual(self.status(), 'paused')


class BackgroundJobsTests(LeaversTestCase):
    """For a campaign that is still marked active although its login is off (missed, or from before)."""

    def setUp(self):
        super().setUp()
        CompanyUser.objects.filter(pk=self.sal.pk).update(is_active=False)

    def test_nothing_is_sent_for_it(self):
        from ai_sdr_agent.tasks import send_due_steps_impl
        agent = self.agent()
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=agent):
            send_due_steps_impl()
        smtp.assert_not_called()

    def test_its_mailbox_is_not_read(self):
        from ai_sdr_agent.tasks import check_inbox_replies_impl
        reader = mock.MagicMock()
        reader.check_inbox_for_replies.return_value = []
        with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=reader), \
                mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent'):
            check_inbox_replies_impl()
        self.assertEqual([call.args[0].id for call in reader.check_inbox_for_replies.call_args_list],
                         [])            # the admin's campaign has nobody enrolled; Sal's is passed over

    def test_a_scheduled_campaign_of_theirs_does_not_start(self):
        from ai_sdr_agent.tasks import auto_start_campaigns_impl
        SDRCampaign.objects.filter(pk=self.sals.pk).update(status='scheduled',
                                                           start_date=timezone.now().date() - timedelta(days=1))
        auto_start_campaigns_impl()
        self.assertEqual(self.status(), 'scheduled')

    def test_no_meeting_reminder_goes_out_in_their_name(self):
        from ai_sdr_agent.tasks import send_meeting_reminders_impl
        SDRMeeting.objects.create(company_user=self.sal, lead=self.sals_lead, status='scheduled',
                                  scheduled_at=timezone.now() + timedelta(hours=25))
        with mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent') as scheduler:
            send_meeting_reminders_impl()
        scheduler.return_value.send_reminder_email.assert_not_called()
        self.assertIsNone(SDRMeeting.objects.get().reminder_sent_at)


class OwnersAndAdminsTests(LeaversTestCase):

    def names(self, actor):
        return sorted(c['name'] for c in self.call(views.sdr_campaigns_list, actor).data['data'])

    def test_an_admin_sees_every_campaign_in_the_company_and_whose_each_is(self):
        self.assertEqual(self.names(self.cu), ['C1', 'Sal spring'])
        rows = {c['name']: c['owner'] for c in self.call(views.sdr_campaigns_list, self.cu).data['data']}
        self.assertEqual((rows['C1']['is_you'], rows['Sal spring']['is_you'], rows['Sal spring']['name']),
                         (True, False, 'Sal Seller'))

    def test_a_salesperson_sees_only_their_own(self):
        self.assertEqual(self.names(self.sal), ['Sal spring'])
        self.assertEqual(self.call(views.sdr_campaign_detail, self.sal, campaign_id=self.campaign.id).status_code,
                         404)

    def test_never_another_companys(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rita = CompanyUser.objects.create(company=rival, email='rita@rival.test', full_name='Rita', role='admin',
                                          password_hash='x', is_active=True)
        self.assertEqual(self.names(rita), [])
        for method in ('get', 'put', 'delete'):
            response = self.call(views.sdr_campaign_detail, rita, method, {'status': 'paused'},
                                 campaign_id=self.sals.id)
            self.assertEqual(response.status_code, 404, method)
        self.assertEqual(self.status(), 'active')

    def test_an_admin_can_open_a_colleagues_campaign_its_steps_and_its_leads(self):
        detail = self.call(views.sdr_campaign_detail, self.cu, campaign_id=self.sals.id)
        self.assertEqual((detail.status_code, detail.data['data']['owner']['name']), (200, 'Sal Seller'))
        self.assertEqual(len(self.call(views.sdr_campaign_steps, self.cu, campaign_id=self.sals.id).data['data']), 1)
        self.assertEqual(len(self.call(views.sdr_campaign_enrollments, self.cu, campaign_id=self.sals.id).data['data']),
                         1)

    def test_an_admin_can_pause_it_and_start_it_again(self):
        self.assertEqual(self.call(views.sdr_campaign_detail, self.cu, 'put', {'status': 'paused'},
                                   campaign_id=self.sals.id).status_code, 200)
        self.assertEqual(self.status(), 'paused')
        self.assertEqual(self.call(views.sdr_campaign_detail, self.cu, 'put', {'status': 'active'},
                                   campaign_id=self.sals.id).status_code, 200)
        self.assertEqual(self.status(), 'active')

    def test_but_cannot_change_anything_else_about_it(self):
        for change in ({'name': 'Mine now'}, {'status': 'paused', 'smtp_username': 'me@acme.test'},
                       {'status': 'completed'}, {}):
            response = self.call(views.sdr_campaign_detail, self.cu, 'put', change, campaign_id=self.sals.id)
            self.assertEqual(response.status_code, 403, change)
        campaign = SDRCampaign.objects.get(pk=self.sals.pk)
        self.assertEqual((campaign.name, campaign.smtp_username, campaign.status), ('Sal spring', 'u', 'active'))
        response = self.call(views.sdr_campaign_steps, self.cu, 'post', {'subject_template': 'x'},
                             campaign_id=self.sals.id)
        self.assertEqual(response.status_code, 404)

    def test_a_campaign_of_a_switched_off_login_can_be_deleted_but_not_started(self):
        self.switch_off()
        response = self.call(views.sdr_campaign_detail, self.cu, 'put', {'status': 'active'},
                             campaign_id=self.sals.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('switched off', response.data['message'])
        self.assertEqual(self.status(), 'paused')
        self.assertEqual(self.call(views.sdr_campaign_detail, self.cu, 'delete', campaign_id=self.sals.id).status_code,
                         200)
        self.assertFalse(SDRCampaign.objects.filter(pk=self.sals.pk).exists())

    def test_the_owner_can_still_change_their_own(self):
        response = self.call(views.sdr_campaign_detail, self.sal, 'put', {'name': 'Renamed', 'status': 'paused'},
                             campaign_id=self.sals.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(SDRCampaign.objects.get(pk=self.sals.pk).name, 'Renamed')

    def test_who_counts_as_running_the_company(self):
        self.assertTrue(leavers.is_admin(self.cu))
        self.assertFalse(leavers.is_admin(self.sal))
        self.cu.is_active = False
        self.assertFalse(leavers.is_admin(self.cu))
