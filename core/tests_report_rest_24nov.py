"""The rest of the test report's "Next" and "Later" lists (24 Nov 2026): Marketing, Reply Draft, Recruitment,
Operations, the Data Analyst and CRM Sync. Each test names the item it is for."""
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from core.tests_do_not_email import MarketingBase


# ---- Marketing -----------------------------------------------------------------------------------------------------

class MarketingDocuments(MarketingBase):

    def test_an_empty_ai_reply_is_not_saved_as_a_created_document(self):
        """Marketing 2: "created successfully", and an empty document with a blank PDF."""
        from marketing_agent.agents.document_authoring_agent import DocumentAuthoringAgent
        from marketing_agent.models import MarketingDocument
        agent = DocumentAuthoringAgent()
        with mock.patch.object(DocumentAuthoringAgent, '_generate_document_content', return_value='  '):
            result = agent.process(action='create', user_id=self.owner.id, document_type='strategy',
                                   document_data={'title': 'Winter launch brief'})
        self.assertFalse(result['success'])
        self.assertIn('try again', result['error'])
        self.assertFalse(MarketingDocument.objects.exists())


class MarketingOptimisation(MarketingBase):

    def test_the_figures_follow_the_sequence_and_the_prompt_forbids_invented_proof(self):
        """Marketing 3: every email was "step 0" after the template's 3 days; the advice called 40% zero and made up
        "we've helped 30+ brands"."""
        from marketing_agent.agents.outreach_campaign_agent import OutreachCampaignAgent
        from marketing_agent.models import EmailSequenceStep, EmailTemplate
        second = EmailTemplate.objects.create(campaign=self.campaign, name='Follow-up', subject='Following up',
                                              html_content='<p>Again</p>')
        step = EmailSequenceStep.objects.get(sequence=self.sequence, step_order=2)
        step.template, step.delay_days, step.delay_minutes = second, 0, 5
        step.save()
        agent = OutreachCampaignAgent.__new__(OutreachCampaignAgent)
        emails = {e['subject']: e for e in agent._email_performance(self.campaign)['emails']}
        self.assertEqual((emails['Following up']['step'], emails['Following up']['wait']), (1, '5 minutes'))
        self.assertIn('sent 5 minutes after the previous one', agent._describe_email(2, emails['Following up']))
        with mock.patch.object(OutreachCampaignAgent, '_call_llm_for_reasoning', return_value='## What', create=True) as llm:
            agent.system_prompt = ''
            agent._generate_optimization_plan(self.campaign, agent._email_performance(self.campaign), None)
        self.assertIn('Invent nothing', llm.call_args[0][0])


class MarketingLeadsUpload(MarketingBase):

    def test_a_lead_already_in_the_campaign_is_updated_not_added(self):
        """Marketing 4: "4 added" for 3 leads."""
        from api.views import marketing_agent as views
        first = b'email,first_name,last_name\nann@p.example,Ann,A\n'
        views._upload_leads_from_file(self.campaign, self.owner, SimpleUploadedFile('a.csv', first))
        csv = (b'email,first_name,last_name\nann@p.example,Ann,A\nbob@p.example,Bob,B\ncid@p.example,Cid,C\n'
               b'dee@p.example,Dee,D\nbad,,\n')
        result, error = views._upload_leads_from_file(self.campaign, self.owner, SimpleUploadedFile('b.csv', csv))
        self.assertIsNone(error)
        self.assertEqual((result['created_count'], result['updated_count'], result['rejected_count']), (3, 1, 1))


class MarketingSender(SimpleTestCase):

    def test_the_address_in_brackets_is_the_sender_whatever_the_python(self):
        """Marketing 5: on an unpatched Python the display name billing@bank.com was taken as the sender."""
        from marketing_agent.management.commands.sync_inbox import Command
        self.assertEqual(Command._first_address('billing@bank.com <someone@else.com>', brackets_too=True),
                         'someone@else.com')
        self.assertEqual(Command._first_address('"Boss <ceo@firm.com>" <attacker@else.com>', brackets_too=True),
                         'attacker@else.com')
        self.assertEqual(Command._first_address('Mary <mary+work@gmail.com>', brackets_too=True), 'mary+work@gmail.com')
        self.assertEqual(Command._first_address('plain@example.com', brackets_too=True), 'plain@example.com')


# ---- Reply Draft ---------------------------------------------------------------------------------------------------

class ReplyDraftPrompts(SimpleTestCase):

    def test_drafts_promise_nothing_nobody_said(self):
        """Reply Draft 2 (decision D12): "our team is already investigating", "I am free on Tuesday"."""
        from reply_draft_agent.agents.reply_draft_agent import ReplyDraftAgent
        for prompt in (ReplyDraftAgent.SYSTEM_PROMPT, ReplyDraftAgent.INBOX_SYSTEM_PROMPT):
            self.assertIn('Promise nothing nobody said', prompt)
        self.assertIn('never treat it as a lead who is not interested', ReplyDraftAgent.INBOX_SYSTEM_PROMPT)

    def test_the_attachment_example_names_no_real_company(self):
        """Reply Draft 3: an invoice from CloudDesk was summarised "An invoice from Shifa Clinic"."""
        from reply_draft_agent import insights
        self.assertNotIn('Shifa', insights.DOCUMENT_PROMPT)


class ReplyDraftInbox(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        from marketing_agent.models import EmailAccount
        from reply_draft_agent.models import InboxEmail
        self.user = get_user_model().objects.create_user('rida', email='rida@acme.example', password='x')
        self.account = EmailAccount.objects.create(owner=self.user, name='Support', email='help@acme.example',
                                                   smtp_host='smtp.test', smtp_port=587, smtp_username='u',
                                                   smtp_password='p', is_active=True)
        self.angry = InboxEmail.objects.create(owner=self.user, email_account=self.account, direction='in',
                                               from_email='imran@c.example', message_id='<m1@c.example>',
                                               from_name='Imran', subject='Nothing works', body='Fix it now.',
                                               category='support', priority='urgent', needs_reply=True)

    def test_the_draft_is_told_it_is_a_complaint(self):
        """Reply Draft 4 and N8: an angry support customer got a sales-style "not interested" reply."""
        from reply_draft_agent.agents.reply_draft_agent import ReplyDraftAgent
        agent = ReplyDraftAgent.__new__(ReplyDraftAgent)
        with mock.patch.object(ReplyDraftAgent, '_signature', return_value='Rida'):
            prompt = agent._build_inbox_prompt(self.angry, '', 'professional', 'medium')
        self.assertIn('Triage: Support or complaint, urgent priority', prompt)

    def test_ask_reads_a_file_nobody_summarised_and_lists_the_urgent_mail(self):
        """Reply Draft 5 (decision D11): no amount until someone pressed "summarise"; the urgent list left out the
        high-priority refund."""
        from reply_draft_agent import insights
        from reply_draft_agent.models import InboxAttachment, InboxEmail
        invoice = InboxEmail.objects.create(owner=self.user, email_account=self.account, direction='in',
                                            from_email='bill@cloud.example', message_id='<m2@cloud.example>',
                                            subject='Invoice', body='Please find our invoice attached.',
                                            category='billing', priority='high', needs_reply=False)
        InboxAttachment.objects.create(inbox_email=invoice, filename='invoice.pdf', content_type='application/pdf',
                                       size_bytes=2000)
        with mock.patch.object(insights, 'attachment_text', return_value='Total due: USD 2,352.00 by 30 Nov'):
            files = insights._file_summaries([invoice])
        self.assertIn('USD 2,352.00', files[invoice.id][0][1])
        agent = mock.Mock()
        agent._call_llm.return_value = json.dumps({'answer': 'Imran [#%d]' % self.angry.id, 'sources': []})
        plan = {'language': '', 'terms': [], 'people': [], 'days': None, 'categories': [],
                'priorities': ['urgent', 'high'], 'waiting': False}
        with mock.patch.object(insights, '_plan', return_value=plan), \
             mock.patch.object(insights, 'attachment_text', return_value='Total due: USD 2,352.00'):
            insights.ask_inbox('Which emails are urgent?', self.account, agent)
        prompt = agent._call_llm.call_args.kwargs['prompt']
        self.assertIn(f'[#{self.angry.id}]', prompt.split('TRIAGE MARKED', 1)[1])
        self.assertIn(f'[#{invoice.id}]', prompt.split('TRIAGE MARKED', 1)[1])


# ---- Recruitment ---------------------------------------------------------------------------------------------------

from recruitment_agent.tests import test_workflows as _workflows  # noqa: E402  (the module: its class would run here too)


class RecruitmentTemplateTwice(_workflows.WorkflowTests):

    def test_the_same_copy_twice_is_refused_and_a_renamed_one_is_not(self):
        """Recruitment 2 (decision D25): a double click made two workflows, and every alert came twice."""
        from api.views import recruitment_workflows as views
        from recruitment_agent import workflows
        key = next(iter(workflows.TEMPLATES))
        first = self.call(views.workflow_from_template, self.owner, 'post', {'template_key': key})
        again = self.call(views.workflow_from_template, self.owner, 'post', {'template_key': key})
        renamed = self.call(views.workflow_from_template, self.owner, 'post', {'template_key': key, 'name': 'Copy B'})
        self.assertEqual([first.status_code, again.status_code, renamed.status_code], [201, 409, 201])


# The workflow tests themselves are not run a second time from here.
for _name in [n for n in dir(_workflows.WorkflowTests) if n.startswith('test_')]:
    setattr(RecruitmentTemplateTwice, _name, None)


# ---- Operations ----------------------------------------------------------------------------------------------------

class OperationsSums(SimpleTestCase):
    """Operations 1 (decision D14): PKR 129,500,000 for three months that add up to 129,150,000."""

    def test_a_wrong_total_is_corrected_wherever_it_is_written(self):
        from operations_agent.arithmetic import check_sums
        answer = ('Total revenue for Q3 was **PKR 129,500,000**.\n\n'
                  'PKR 41,300,000 + PKR 43,050,000 + PKR 44,800,000 = PKR 129,500,000\n\nTotal: 129,500,000')
        fixed, fixes = check_sums(answer)
        self.assertEqual(fixes, [('PKR 129,500,000', 'PKR 129,150,000')])
        self.assertNotIn('129,500,000', fixed)
        self.assertEqual(fixed.count('129,150,000'), 3)

    def test_right_sums_averages_and_decimals_are_left_alone(self):
        from operations_agent.arithmetic import check_sums
        for text in ('41,300,000 + 43,050,000 + 44,800,000 = 129,150,000', '(10 + 20 + 31) / 3 = 20.3',
                     '1,250,000 + 2,352.00 = 1,252,352.00', 'Up 5% + 3% = 8%', 'No sum here.'):
            self.assertEqual(check_sums(text), (text, []))
        self.assertEqual(check_sums('(10 + 20) / 2 = 16')[1], [('16', '15')])

    def test_both_prompts_ask_for_the_working(self):
        from operations_agent.agents import document_authoring_agent, knowledge_qa_agent
        for prompt in (knowledge_qa_agent.SYSTEM_PROMPT, document_authoring_agent.BASE_SYSTEM):
            self.assertIn('"A + B + C = total"', prompt)


# ---- Data Analyst ----------------------------------------------------------------------------------------------------

class DataAnalystTies(SimpleTestCase):
    """Data Analyst 3: three customers tied for third, and each source named a different one."""

    def test_a_tie_at_the_cut_off_is_named(self):
        from data_analyst_agent.engine import _tie_at_cut
        result = {'columns': ['customer', 'orders'],
                  'rows': [['Hira', 14], ['Omar', 12], ['Ayesha', 10], ['Saad', 10], ['Bilal', 10]]}
        said = _tie_at_cut('Who are our top 3 customers by number of orders?', result)
        self.assertIn('Place 3 is shared: 3 rows have orders 10', said)
        result['rows'][3][1] = 9
        self.assertEqual(_tie_at_cut('Who are our top 3 customers?', result), '')
        self.assertEqual(_tie_at_cut('How many customers do we have?', result), '')

    def test_the_prompts_fetch_past_n_round_money_and_count_everything_in_total(self):
        from data_analyst_agent import engine
        for prompt in (engine._SQL, engine._MONGO):
            self.assertIn('N + 2', prompt)
            self.assertIn('2 decimal places', prompt)
        self.assertIn('"in total"', engine._LIVE)               # decision D8


class DataAnalystPrivateAddress(SimpleTestCase):
    """Data Analyst 4b (decision D9): a database at 10.0.0.5 was saved, with status "failed"."""

    def test_only_an_address_that_is_itself_private_is_refused_at_once(self):
        from data_analyst_agent import guards
        for host in ('127.0.0.1', '10.0.0.5', '192.168.1.9', '169.254.169.254', 'localhost', '[::1]'):
            self.assertIn('not a public address', guards.private_address(host), host)
        for host in ('8.8.4.4', 'db.example.com', 'cluster0.abcd.mongodb.net', ''):
            self.assertEqual(guards.private_address(host), '', host)       # names are checked when connecting


# ---- CRM Sync ------------------------------------------------------------------------------------------------------

class CRMQueuedOnce(TestCase):

    def test_an_entry_waiting_for_the_key_is_not_queued_twice(self):
        """CRM 3b: a customer who wrote in while HubSpot refused the key got two contact entries."""
        from core.models import Company
        from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
        from crm_sync_agent.models import CRMIntegration, CRMSyncQueue
        company = Company.objects.create(name='Acme', email='acme@test.local')
        integration = CRMIntegration.objects.create(company=company, provider='hubspot')
        CRMSyncQueue.objects.create(company=company, integration=integration, object_type='contact',
                                    operation='upsert', source_type='frontline_contact', source_id=4,
                                    payload={'email': 'zara@c.example'}, status=CRMSyncQueue.STATUS_WAITING)
        agent = CRMSyncAgent.__new__(CRMSyncAgent)
        agent.company = company
        agent._enqueue(integration, 'contact', 'upsert', 'frontline_contact', 4, {'email': 'zara@c.example', 'n': 2})
        rows = list(CRMSyncQueue.objects.filter(source_id=4))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].status, rows[0].payload['n']), (CRMSyncQueue.STATUS_WAITING, 2))
