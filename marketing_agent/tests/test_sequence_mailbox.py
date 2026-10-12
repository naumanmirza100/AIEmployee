"""A sequence can only send through its own login's mailbox.

The sending mailbox of a sequence arrived as a bare number and was saved without
asking whose mailbox it was. The scheduled sender then logged in to that mailbox
with its stored password, so a login could send its campaign from another
company's address, and replies landed in that company's inbox. The campaign-level
setting checked ownership; the sequence-level one did not.
"""
import importlib

from django.apps import apps

from api.views import marketing_agent as views
from marketing_agent.models import EmailSequence
from marketing_agent.tests.base import MarketingTestCase


class SequenceMailboxTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.own = self.mailbox(self.ann, 'ann@acme.test')
        self.theirs = self.mailbox(self.rita, 'sales@rival.test')
        self.spring = self.campaign(self.ann)

    def create(self, **body):
        body.setdefault('name', 'Main')
        return self.call(views.create_sequence, self.ann_login, body, campaign_id=self.spring.id)

    def update(self, sequence, **body):
        return self.call(views.update_sequence, self.ann_login, body, method='put',
                         campaign_id=self.spring.id, sequence_id=sequence.id)

    def test_a_new_sequence_cannot_name_another_companys_mailbox(self):
        code, reply = self.create(email_account_id=self.theirs.id)
        self.assertEqual(code, 400, reply)
        self.assertIn('not owned by you', reply['message'])
        self.assertFalse(EmailSequence.objects.filter(campaign=self.spring).exists())

    def test_an_edit_cannot_point_a_sequence_at_another_companys_mailbox(self):
        sequence = self.sequence(self.spring, email_account=self.own)
        code, reply = self.update(sequence, name='Renamed', email_account_id=str(self.theirs.id))
        self.assertEqual(code, 400, reply)
        sequence.refresh_from_db()
        self.assertEqual((sequence.email_account_id, sequence.name), (self.own.id, 'Main'))

    def test_its_own_mailbox_is_accepted_as_a_number_or_as_text(self):
        code, reply = self.create(email_account_id=str(self.own.id))
        self.assertEqual(code, 201, reply)
        sequence = EmailSequence.objects.get(campaign=self.spring)
        self.assertEqual(sequence.email_account_id, self.own.id)

        other = self.mailbox(self.ann, 'ann.second@acme.test')
        self.assertEqual(self.update(sequence, email_account_id=other.id)[0], 200)
        sequence.refresh_from_db()
        self.assertEqual(sequence.email_account_id, other.id)

    def test_blank_means_use_the_campaigns_mailbox(self):
        sequence = self.sequence(self.spring, email_account=self.own)
        for blank in ('', None, 0):
            sequence.email_account = self.own
            sequence.save()
            self.assertEqual(self.update(sequence, email_account_id=blank)[0], 200, blank)
            sequence.refresh_from_db()
            self.assertIsNone(sequence.email_account_id, blank)
        self.assertEqual(self.create()[0], 400)              # a second main sequence, nothing to do with mailboxes

    def test_an_edit_that_does_not_mention_the_mailbox_leaves_it(self):
        sequence = self.sequence(self.spring, email_account=self.own)
        self.assertEqual(self.update(sequence, name='Renamed')[0], 200)
        sequence.refresh_from_db()
        self.assertEqual((sequence.email_account_id, sequence.name), (self.own.id, 'Renamed'))

    def test_something_that_is_not_a_number_is_refused_not_crashed_on(self):
        code, _ = self.create(email_account_id='the first one')
        self.assertEqual(code, 400)

    def test_a_mailbox_connected_only_for_reply_draft_is_not_a_sending_mailbox(self):
        inbox_only = self.mailbox(self.ann, 'support@acme.test', is_marketing_account=False)
        self.assertEqual(self.create(email_account_id=inbox_only.id)[0], 400)


class SendingAccountTests(MarketingTestCase):
    """The lock where the stored password would be used, whatever the row says."""

    def setUp(self):
        super().setUp()
        self.own = self.mailbox(self.ann, 'ann@acme.test')
        self.theirs = self.mailbox(self.rita, 'sales@rival.test')
        self.spring = self.campaign(self.ann)

    def test_a_borrowed_mailbox_already_on_a_row_is_never_sent_through(self):
        sequence = self.sequence(self.spring, email_account=self.theirs)
        self.assertIsNone(sequence.get_sending_account())

        self.spring.email_account = self.own
        self.spring.save()
        self.assertEqual(EmailSequence.objects.get(pk=sequence.pk).get_sending_account(), self.own)

    def test_a_borrowed_mailbox_on_the_campaign_is_not_used_either(self):
        self.spring.email_account = self.theirs
        self.spring.save()
        self.assertIsNone(self.sequence(self.spring).get_sending_account())

    def test_the_usual_order_still_holds(self):
        second = self.mailbox(self.ann, 'ann.second@acme.test')
        self.spring.email_account = self.own
        self.spring.save()
        self.assertEqual(self.sequence(self.spring, name='A').get_sending_account(), self.own)
        self.assertEqual(self.sequence(self.spring, name='B', email_account=second).get_sending_account(), second)

    def test_rows_saved_before_the_check_are_cleared(self):
        borrowed = self.sequence(self.spring, name='Borrowed', email_account=self.theirs)
        fine = self.sequence(self.spring, name='Fine', email_account=self.own)
        unset = self.sequence(self.spring, name='Unset')

        migration = importlib.import_module('marketing_agent.migrations.0040_sequence_mailbox_is_the_owners')
        migration.clear_borrowed_mailboxes(apps, None)
        migration.clear_borrowed_mailboxes(apps, None)        # and it can run again

        for sequence in (borrowed, fine, unset):
            sequence.refresh_from_db()
        self.assertEqual((borrowed.email_account_id, fine.email_account_id, unset.email_account_id),
                         (None, self.own.id, None))
