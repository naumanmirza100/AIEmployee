"""A company's "when a ticket is created" workflows, for the tickets its customers open.

Found on 27 Oct 2026 (the client showcase's workflows "kept failing"): a chat hand-off or an emailed ticket ran no
workflow at all; the contact form's ran before the ticket was classified, so a workflow for "billing" or "urgent"
tickets never matched a customer's; and "email the customer" went to `created_by`, a bot or a staff login.
"""
from unittest import mock

from django.core import mail
from django.core.cache import cache

from api.views import frontline_agent as views
from core.Frontline_agent.frontline_agent import FrontlineAgent
from Frontline_agent import ticket_automation
from Frontline_agent.models import Contact, FrontlineWorkflow, FrontlineWorkflowExecution, NotificationTemplate, Ticket
from Frontline_agent.tasks import process_inbound_email

from .base import FrontlineTestCase
from .test_inbound_email import payload

BILLING = {'suggested_category': 'billing', 'suggested_priority': 'medium', 'intent': 'invoice', 'entities': {}}


class NewTicketWorkflowTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.triage = mock.patch.object(FrontlineAgent, '_extract_ticket_intent', return_value=BILLING).start()
        self.addCleanup(mock.patch.stopall)

    def switch_on(self, classify=False):
        self.company.frontline_widget_config = {
            'require_captcha': False, 'ticket_automation': {'classify_incoming': classify, 'resolve_from_knowledge': False}}
        self.company.save(update_fields=['frontline_widget_config'])

    def workflow(self, steps, **trigger):
        return FrontlineWorkflow.objects.create(company=self.company, name='wf', steps=steps, is_active=True,
                                                trigger_conditions={'on': 'ticket_created', **trigger})

    def test_an_emailed_billing_ticket_is_routed_once_it_is_classified(self):
        self.switch_on(classify=True)
        self.workflow([{'type': 'assign', 'assign_to_company_user_id': self.member.id}], category='billing')
        with self.captureOnCommitCallbacks(execute=True):
            result = process_inbound_email(payload(self.company.id))
        ticket = Ticket.objects.get(pk=result['ticket_id'])
        self.assertEqual(ticket.category, 'billing')
        self.assertEqual(ticket.assigned_to, views._get_or_create_user_for_company_user(self.member))

    def test_a_chat_hand_off_runs_them_with_both_switches_off(self):
        self.switch_on()
        wf = self.workflow([{'type': 'update_ticket', 'priority': 'high'}])
        ticket = self.make_ticket(title='Hand-off: menu page', priority='medium')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(ticket_automation.queue(ticket, 'chat'))
        self.assertEqual(FrontlineWorkflowExecution.objects.get(workflow=wf).status, 'completed')

    def test_with_no_such_workflow_and_both_switches_off_nothing_is_queued(self):
        self.switch_on()
        self.assertFalse(ticket_automation.queue(self.make_ticket(), 'chat'))

    def test_email_the_customer_goes_to_the_customer(self):
        self.switch_on()
        template = NotificationTemplate.objects.create(company=self.company, name='Got it', channel='email',
                                                       subject='We have {{ticket_title}}', body='Hi {{customer_name}}')
        self.workflow([{'type': 'send_email', 'template_id': template.id, 'recipient_email': '{{recipient_email}}'}])
        customer = Contact.objects.create(company=self.company, email='farhan@bakery.test', name='Farhan')
        ticket = self.make_ticket(title='Web form: Farhan', contact=customer)
        mail.outbox = []
        ticket_automation.run_new_ticket_workflows(ticket)
        [email] = mail.outbox
        self.assertEqual((email.to, email.body), (['farhan@bakery.test'], 'Hi Farhan'))


class TicketCustomerTests(FrontlineTestCase):

    def test_the_customer_is_the_contact_never_a_bot(self):
        customer = Contact.objects.create(company=self.company, email='farhan@bakery.test', name='Farhan')
        self.assertEqual(views._ticket_customer(self.make_ticket(contact=customer)), ('farhan@bakery.test', 'Farhan'))
        bot = views._ensure_handoff_system_user()
        self.assertEqual(views._ticket_customer(self.make_ticket(created_by=bot)), ('', ''))
        self.admin_user.email = 'dana@bakery.test'
        self.admin_user.save(update_fields=['email'])
        staff = self.make_ticket(created_by=self.admin_user)       # a staff ticket keeps who raised it
        self.assertEqual(views._ticket_customer(staff)[0], 'dana@bakery.test')
