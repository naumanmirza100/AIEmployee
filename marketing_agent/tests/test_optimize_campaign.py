"""Optimizing a campaign reads what its emails did.

The optimizer was asked about impressions, clicks and A/B tests, numbers an email campaign never records, so its advice
was built on zeros. It had no button either: the action was left out of the Outreach screen's list.
"""
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from api.views import marketing_agent as views
from marketing_agent.agents.outreach_campaign_agent import OutreachCampaignAgent
from marketing_agent.models import CampaignContact, EmailSendHistory, Reply
from marketing_agent.tests.base import MarketingTestCase

ADVICE = '## What the numbers say\nToo few emails to judge.'


class OptimizeCampaignTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.spring = self.campaign(self.ann, name='Spring offer', industry='Retail', target_conversions=5)
        self.first = self.template(self.spring, name='First', subject='A better till for your shop')
        self.follow_up = self.template(self.spring, name='Nudge', subject='Did you see this?',
                                       followup_sequence_number=1, followup_delay_days=3)
        self.bilal = self.lead(self.ann, 'bilal@shop.test', campaign=self.spring)
        self.sana = self.lead(self.ann, 'sana@shop.test', campaign=self.spring)
        self.lead(self.ann, 'usman@shop.test', campaign=self.spring)          # not emailed yet

    def send(self, lead, template, status):
        return EmailSendHistory.objects.create(campaign=self.spring, lead=lead, email_template=template,
                                               subject=template.subject, recipient_email=lead.email, status=status,
                                               sent_at=timezone.now())

    def reply(self, lead, to_email, reads_as):
        contact, _ = CampaignContact.objects.get_or_create(campaign=self.spring, lead=lead)
        Reply.objects.create(contact=contact, campaign=self.spring, lead=lead, triggering_email=to_email,
                             interest_level=reads_as, reply_content='Tell me more')

    def optimize(self, campaign=None, user=None):
        agent = OutreachCampaignAgent()
        with mock.patch.object(OutreachCampaignAgent, '_call_llm_for_reasoning', return_value=ADVICE) as llm:
            result = agent.optimize_campaign((campaign or self.spring).id, (user or self.ann).id)
        prompt = llm.call_args[0][0] if llm.called else ''
        return result, prompt

    def test_the_advice_is_asked_for_with_the_campaigns_email_results(self):
        to_bilal = self.send(self.bilal, self.first, 'opened')
        self.send(self.sana, self.first, 'clicked')
        self.send(self.bilal, self.follow_up, 'failed')
        self.reply(self.sana, to_bilal, 'positive')

        result, prompt = self.optimize()

        self.assertTrue(result['success'], result)
        self.assertEqual(result['optimization_plan']['optimization_plan'], ADVICE)
        self.assertIn('Leads: 3 (1 not emailed yet)', prompt)
        self.assertIn('Emails sent: 2 (failed 1, bounced 0)', prompt)
        self.assertIn('Replies: 1 (50.0% of sent): interested 1', prompt)
        self.assertIn('1. "A better till for your shop" (first email): sent 2, opened 2, clicked 1, replies 1', prompt)
        self.assertIn('2. "Did you see this?" (follow-up 1, sent 3 days after the previous one): sent 0', prompt)
        self.assertIn('Targeting: industry: Retail', prompt)
        self.assertNotIn('Impressions', prompt)

    def test_a_campaign_with_nothing_sent_still_gets_advice_on_its_emails(self):
        result, prompt = self.optimize()
        self.assertTrue(result['success'], result)
        self.assertIn('Emails sent: 0', prompt)
        self.assertIn('Starts: Hi', prompt)

    def test_the_queries_do_not_grow_with_the_campaign(self):
        self.send(self.bilal, self.first, 'sent')
        with CaptureQueriesContext(connection) as small:
            self.optimize()
        for n in range(15):
            lead = self.lead(self.ann, f'lead{n}@shop.test', campaign=self.spring)
            self.send(lead, self.first, 'opened')
            self.send(lead, self.follow_up, 'sent')
        self.template(self.spring, name='Last try', subject='Last try', followup_sequence_number=2)
        with CaptureQueriesContext(connection) as big:
            self.optimize()
        self.assertEqual(len(big), len(small))

    def test_someone_elses_campaign_is_refused(self):
        theirs = self.campaign(self.rita, name='Rival offer')
        result, prompt = self.optimize(campaign=theirs)
        self.assertEqual(result, {'success': False, 'error': 'Access denied'})
        self.assertEqual(prompt, '')

    def test_the_outreach_endpoint_runs_it(self):
        with mock.patch.object(OutreachCampaignAgent, '_call_llm_for_reasoning', return_value=ADVICE):
            code, body = self.call(views.outreach_campaign, self.ann_login,
                                   {'action': 'optimize', 'campaign_id': self.spring.id})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['optimization_plan']['optimization_plan'], ADVICE)
