"""A mailbox counts the emails it sent.

The count took only emails whose sequence named the mailbox. A sequence left on
"use the campaign's mailbox" names none, so its emails were counted for no mailbox
and the Marketing dashboard said 0 emails sent after a campaign had sent seven.
"""
from django.utils import timezone

from api.views import marketing_agent as views
from marketing_agent.models import EmailSendHistory
from marketing_agent.tests.base import MarketingTestCase


class MailboxSentCountTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.hello = self.mailbox(self.ann, 'hello@acme.test')
        self.sales = self.mailbox(self.ann, 'sales@acme.test')
        self.campaign_one = self.campaign(self.ann, email_account=self.hello)

    def sent(self, sequence, count):
        template = sequence.steps.first().template
        for i in range(count):
            address = f'p{sequence.id}{i}@client.test'
            EmailSendHistory.objects.create(subject='Hi', recipient_email=address, status='sent', sent_at=timezone.now(),
                                            campaign=self.campaign_one, email_template=template,
                                            lead=self.lead(self.ann, address))

    def counts(self):
        code, body = self.call(views.list_email_accounts, self.ann_login, method='get')
        self.assertEqual(code, 200, body)
        return {row['email']: row['sent_count'] for row in body['data']}

    def test_emails_from_a_sequence_on_the_campaign_mailbox_count_for_that_mailbox(self):
        self.sent(self.sequence(self.campaign_one, name='Default'), 7)
        self.assertEqual(self.counts(), {'hello@acme.test': 7, 'sales@acme.test': 0})

    def test_a_sequence_that_names_another_mailbox_counts_for_that_one_only(self):
        self.sent(self.sequence(self.campaign_one, name='Own', email_account=self.sales), 3)
        self.sent(self.sequence(self.campaign_one, name='Default'), 2)
        self.assertEqual(self.counts(), {'hello@acme.test': 2, 'sales@acme.test': 3})
