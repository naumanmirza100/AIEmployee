"""An agent that is not paid for stops working in the background too.

The API locks an agent's screens the moment its subscription lapses or a card
fails. Its scheduled jobs and automations never pass through the API, so they
carried on: sequences and follow-ups kept emailing customers and candidates,
reminders kept going out, automations kept changing records, and nobody could
open the screens to stop any of it. Each job now asks core/modules.py first.

Every test runs the same job for a company that pays and one that has lapsed.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyModulePurchase, CompanyUser
from core.modules import active_company_ids, has_module, may_run_for


def company(name, module=None, state='active'):
    """A company, optionally with a purchase of `module` in the given state."""
    c = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
    if module:
        now = timezone.now()
        fields = {
            'active': dict(status='active', is_complimentary=True),
            'cancelled': dict(status='cancelled', is_complimentary=True),
            'gift_ran_out': dict(status='active', is_complimentary=True, expires_at=now - timedelta(days=1)),
            'period_ended': dict(status='active', stripe_subscription_id=f'sub_{name}',
                                 current_period_end=now - timedelta(hours=2)),
            'payment_failed': dict(status='past_due', stripe_subscription_id=f'sub_{name}',
                                   current_period_end=now + timedelta(days=20)),
        }[state]
        CompanyModulePurchase.objects.create(company=c, module_name=module, **fields)
    return c


def login(c, email, role='admin'):
    return CompanyUser.objects.create(company=c, email=email, full_name=email.split('@')[0].title(), role=role,
                                      password_hash='x', is_active=True)


class OneRuleTests(TestCase):
    """core/modules.py: the answer the screens and the jobs share."""

    def test_only_an_active_purchase_counts(self):
        states = {'active': True, 'cancelled': False, 'gift_ran_out': False, 'period_ended': False,
                  'payment_failed': False}
        for state, expected in states.items():
            with self.subTest(state=state):
                c = company(state.title().replace('_', ''), 'hr_agent', state)
                self.assertIs(has_module(c, 'hr_agent'), expected)
                self.assertIs(has_module(c.id, 'hr_agent'), expected)          # an id works too
                self.assertIs(c.id in active_company_ids('hr_agent'), expected)
        self.assertFalse(has_module(company('Never'), 'hr_agent'))
        self.assertFalse(has_module(None, 'hr_agent'))

    def test_one_agent_does_not_stand_in_for_another(self):
        c = company('Acme', 'hr_agent')
        self.assertFalse(has_module(c, 'frontline_agent'))
        self.assertEqual(active_company_ids('frontline_agent'), frozenset())
        self.assertIn(c.id, active_company_ids('frontline_agent', 'hr_agent'))

    def test_work_with_no_known_company_still_runs(self):
        paying = frozenset({7})
        self.assertTrue(may_run_for(None, paying))
        self.assertTrue(may_run_for(7, paying))
        self.assertFalse(may_run_for(8, paying))

    def test_the_links_between_agents_use_the_same_rule(self):
        from Frontline_agent.ticket_tasks import pm_available
        from recruitment_agent.hr_handoff import hr_available
        # 'active' on paper, but the free period ran out yesterday.
        self.assertFalse(pm_available(company('Pm', 'project_manager_agent', 'gift_ran_out')))
        self.assertFalse(hr_available(company('Hr', 'hr_agent', 'gift_ran_out')))
        self.assertTrue(pm_available(company('Pm2', 'project_manager_agent')))
        self.assertTrue(hr_available(company('Hr2', 'hr_agent')))


class TwoCompanies(TestCase):
    MODULE = None

    def setUp(self):
        self.paying = company('Paying', self.MODULE)
        self.lapsed = company('Lapsed', self.MODULE, 'period_ended')
        mail.outbox = []


class HRBackgroundTests(TwoCompanies):
    MODULE = 'hr_agent'

    def test_scheduled_emails_go_out_only_for_the_paying_company(self):
        from hr_agent.models import HRNotificationTemplate, HRScheduledNotification
        from hr_agent.tasks import process_hr_scheduled_notifications
        rows = {}
        for c in (self.paying, self.lapsed):
            template = HRNotificationTemplate.objects.create(company=c, name='Reminder', subject='A reminder',
                                                             body='Please remember.', channel='email')
            rows[c.id] = HRScheduledNotification.objects.create(
                company=c, template=template, recipient_email=f'person@{c.name.lower()}.example',
                scheduled_at=timezone.now() - timedelta(minutes=1))
        process_hr_scheduled_notifications()
        self.assertEqual([m.to for m in mail.outbox], [['person@paying.example']])
        rows[self.lapsed.id].refresh_from_db()
        self.assertEqual(rows[self.lapsed.id].status, 'pending')              # waiting, not lost

    def test_an_automation_runs_only_for_the_paying_company(self):
        from hr_agent.models import Employee, HRWorkflow
        people = {}
        for c in (self.paying, self.lapsed):
            HRWorkflow.objects.create(company=c, name='On leave', is_active=True,
                                      trigger_conditions={'on': 'employee_on_leave'},
                                      steps=[{'type': 'update_employee', 'fields': {'job_title': 'Away'}}])
            people[c.id] = Employee.objects.create(company=c, full_name='Pat', work_email=f'pat@{c.name}.example',
                                                   employment_status='active')
        for person in people.values():
            person.employment_status = 'on_leave'
            person.save(update_fields=['employment_status', 'updated_at'])
            person.refresh_from_db()
        self.assertEqual(people[self.paying.id].job_title, 'Away')
        self.assertEqual(people[self.lapsed.id].job_title, '')

    def test_a_paused_run_does_not_carry_on_after_the_subscription_lapses(self):
        from hr_agent.models import HRWorkflow, HRWorkflowExecution
        from hr_agent.tasks import resume_hr_workflow_execution
        user = get_user_model().objects.create_user(username='sys', password='x')
        workflow = HRWorkflow.objects.create(company=self.lapsed, name='Later', is_active=True, steps=[])
        run = HRWorkflowExecution.objects.create(
            workflow=workflow, workflow_name='Later', executed_by=user, status='paused', context_data={},
            pause_state={'remaining_steps': [{'type': 'send_email', 'template_name': 'x', 'recipient_email': 'a@b.example'}]})
        result = resume_hr_workflow_execution(run.id)
        run.refresh_from_db()
        self.assertEqual((result['reason'], run.status), ('not_subscribed', 'failed'))
        self.assertIn('subscription is not active', run.error_message)


class FrontlineBackgroundTests(TwoCompanies):
    MODULE = 'frontline_agent'

    def test_scheduled_customer_emails_go_out_only_for_the_paying_company(self):
        from Frontline_agent.models import NotificationTemplate, ScheduledNotification
        from Frontline_agent.tasks import process_scheduled_notifications
        rows = {}
        for c in (self.paying, self.lapsed):
            template = NotificationTemplate.objects.create(company=c, name='Follow-up', subject='Your ticket',
                                                           body='It was updated.', channel='email')
            rows[c.id] = ScheduledNotification.objects.create(
                company=c, template=template, recipient_email=f'customer@{c.name.lower()}.example',
                scheduled_at=timezone.now() - timedelta(minutes=1))
        process_scheduled_notifications()
        self.assertEqual([m.to for m in mail.outbox], [['customer@paying.example']])
        rows[self.lapsed.id].refresh_from_db()
        self.assertEqual(rows[self.lapsed.id].status, 'pending')

    def test_mail_to_a_lapsed_company_opens_no_ticket(self):
        from Frontline_agent.models import Ticket
        from Frontline_agent.tasks import process_inbound_email
        payload = {'company_id': self.lapsed.id, 'from_address': 'vera@customer.example',
                   'subject': 'Help', 'body_text': 'My invoice is wrong.'}
        result = process_inbound_email(payload)
        self.assertEqual(result, {'status': 'ignored', 'reason': 'not_subscribed'})
        self.assertFalse(Ticket.objects.filter(company=self.lapsed).exists())

    def test_ticket_automations_run_only_for_the_paying_company(self):
        from Frontline_agent.models import Ticket
        user = get_user_model().objects.create_user(username='agent', password='x')
        tickets = [Ticket.objects.create(title='Printer', description='x', company=c, created_by=user)
                   for c in (self.paying, self.lapsed)]
        with mock.patch('api.views.frontline_agent._run_workflow_triggers') as run:
            for ticket in tickets:
                ticket.priority = 'high'
                ticket.save()
        self.assertEqual([call.args[0] for call in run.call_args_list], [self.paying.id])

    def test_old_resolved_tickets_are_closed_only_for_the_paying_company(self):
        from Frontline_agent.models import Ticket
        from Frontline_agent.tasks import auto_close_inactive_tickets
        user = get_user_model().objects.create_user(username='agent', password='x')
        tickets = {c.id: Ticket.objects.create(title='Printer', description='x', company=c, created_by=user,
                                               status='resolved')
                   for c in (self.paying, self.lapsed)}
        Ticket.objects.update(updated_at=timezone.now() - timedelta(days=30))
        auto_close_inactive_tickets()
        for ticket in tickets.values():
            ticket.refresh_from_db()
        self.assertEqual(tickets[self.paying.id].status, 'closed')
        self.assertEqual(tickets[self.lapsed.id].status, 'resolved')


class ProjectManagerBackgroundTests(TwoCompanies):
    MODULE = 'project_manager_agent'

    def test_only_the_paying_companys_unanswered_meetings_are_withdrawn(self):
        from project_manager_agent.models import ScheduledMeeting
        from project_manager_agent.tasks import check_stale_meetings
        invitee = get_user_model().objects.create_user(username='ivy', password='x', email='ivy@test.local')
        meetings = {}
        for c in (self.paying, self.lapsed):
            m = ScheduledMeeting.objects.create(organizer=login(c, f'org@{c.name.lower()}.example'), invitee=invitee,
                                                title='Planning', proposed_time=timezone.now() + timedelta(days=3),
                                                status='pending')
            ScheduledMeeting.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(days=8))
            meetings[c.id] = m
        check_stale_meetings()
        for m in meetings.values():
            m.refresh_from_db()
        self.assertEqual(meetings[self.paying.id].status, 'withdrawn')
        self.assertEqual(meetings[self.lapsed.id].status, 'pending')

    def test_recurring_tasks_are_made_only_for_the_paying_company(self):
        from core.models import Project, Task, TaskRecurrence
        from project_manager_agent.tasks import generate_recurring_tasks
        owner = get_user_model().objects.create_user(username='owner', password='x')
        today = timezone.localdate()
        projects = {}
        for c in (self.paying, self.lapsed):
            projects[c.id] = Project.objects.create(name='Ops', company=c, owner=owner)
            template = Task.objects.create(project=projects[c.id], title='Weekly report')
            TaskRecurrence.objects.create(template_task=template, starts_on=today, next_run_date=today)
        generate_recurring_tasks()
        self.assertEqual(Task.objects.filter(project=projects[self.paying.id]).count(), 2)
        self.assertEqual(Task.objects.filter(project=projects[self.lapsed.id]).count(), 1)


class ExecutiveMeetingBackgroundTests(TwoCompanies):
    MODULE = 'exec_meeting_agent'

    def test_reminders_are_raised_only_for_the_paying_company(self):
        from meeting_agent.models import ExecNotification, ExecutiveMeeting
        from meeting_agent.tasks import send_meeting_reminders
        organisers = {}
        for c in (self.paying, self.lapsed):
            organisers[c.id] = login(c, f'dana@{c.name.lower()}.example')
            ExecutiveMeeting.objects.create(organizer=organisers[c.id], title='Board prep',
                                            scheduled_at=timezone.now() + timedelta(minutes=10))
        send_meeting_reminders()
        self.assertTrue(ExecNotification.objects.filter(company_user=organisers[self.paying.id]).exists())
        self.assertFalse(ExecNotification.objects.filter(company_user=organisers[self.lapsed.id]).exists())


class CRMSyncBackgroundTests(TwoCompanies):
    MODULE = 'crm_sync_agent'

    def test_nothing_is_pushed_to_a_crm_for_a_lapsed_company(self):
        from crm_sync_agent.tasks import process_crm_sync_queue
        with mock.patch('crm_sync_agent.agents.crm_sync_agent.CRMSyncAgent') as agent:
            agent.return_value.process_pending.return_value = {'processed': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0}
            process_crm_sync_queue(company_id=self.lapsed.id)
            agent.assert_not_called()
            process_crm_sync_queue(company_id=self.paying.id)
            agent.assert_called_once()


class MarketingBackgroundTests(TwoCompanies):
    MODULE = 'marketing_agent'

    def owner(self, c, email, linked=False):
        """A campaign owner: the user behind a dashboard login, found by link or by email."""
        user = get_user_model().objects.create_user(username=email, password='x', email=email)
        dashboard = login(c, email if not linked else f'other-{email}')
        if linked:
            dashboard.login_user = user
            dashboard.save(update_fields=['login_user'])
        return user

    @staticmethod
    def campaign(owner):
        return SimpleNamespace(pk=1, owner=owner, owner_id=getattr(owner, 'pk', None))

    def test_a_campaign_runs_only_while_its_company_pays(self):
        from marketing_agent.services.subscription import PayingCampaigns
        check = PayingCampaigns()
        self.assertTrue(check.allows(self.campaign(self.owner(self.paying, 'pia@paying.example'))))
        self.assertFalse(check.allows(self.campaign(self.owner(self.lapsed, 'lars@lapsed.example'))))
        # found by the link between the login and its user, not only by email
        self.assertFalse(check.allows(self.campaign(self.owner(self.lapsed, 'lena@lapsed.example', linked=True))))

    def test_the_sequence_sender_skips_a_lapsed_companys_leads(self):
        from marketing_agent.management.commands.send_sequence_emails import Command
        from marketing_agent.models import Campaign, CampaignLead, EmailSequence, Lead
        campaigns = {}
        for c in (self.paying, self.lapsed):
            owner = self.owner(c, f'owner@{c.name.lower()}.example')
            campaign = Campaign.objects.create(name=f'{c.name} nurture', owner=owner, status='active')
            EmailSequence.objects.create(name='Welcome', campaign=campaign, is_active=True)
            lead = Lead.objects.create(email=f'lead@{c.name.lower()}-prospect.example', owner=owner)
            CampaignLead.objects.create(campaign=campaign, lead=lead)
            campaigns[c.id] = campaign
        with mock.patch.object(Command, '_process_main_sequence_contact', return_value='skipped') as send:
            Command()._run(dry_run=True)
        self.assertEqual([call.args[1].pk for call in send.call_args_list], [campaigns[self.paying.id].pk])

    def test_a_campaign_whose_company_cannot_be_told_keeps_running(self):
        from marketing_agent.services.subscription import PayingCampaigns
        stranger = get_user_model().objects.create_user(username='solo', password='x', email='solo@nowhere.example')
        check = PayingCampaigns()
        self.assertTrue(check.allows(self.campaign(stranger)))
        self.assertTrue(check.allows(self.campaign(None)))
        self.assertTrue(check.allows(None))

    def test_a_lapsed_companys_scheduled_campaign_is_not_started(self):
        from marketing_agent.models import Campaign, MarketingNotification
        from marketing_agent.tasks import auto_start_campaigns_task
        campaigns = {}
        for c in (self.paying, self.lapsed):
            owner = self.owner(c, f'owner@{c.name.lower()}.example')
            campaigns[c.id] = Campaign.objects.create(name=f'{c.name} launch', owner=owner)
            # Saving a campaign that is due starts it on the spot, so the date is set underneath it.
            Campaign.objects.filter(pk=campaigns[c.id].pk).update(status='scheduled',
                                                                  start_date=timezone.now().date())
        result = auto_start_campaigns_task()
        self.assertEqual(result.get('status'), 'success', result)      # the job swallows its own errors
        # With no sequence the job tells the owner; it should do even that only for the paying company.
        self.assertTrue(MarketingNotification.objects.filter(campaign=campaigns[self.paying.id]).exists())
        self.assertFalse(MarketingNotification.objects.filter(campaign=campaigns[self.lapsed.id]).exists())
