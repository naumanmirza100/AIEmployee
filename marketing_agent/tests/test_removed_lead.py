"""A lead taken out of a campaign stops getting that campaign's emails.

Removing a lead dropped the link between lead and campaign and nothing else.
The sender builds its work from contact rows and follow-up run rows, which stay
(the stored replies hang off them), and it never looked at the campaign's lead
list. So someone who was also in another campaign, and therefore not deleted
outright, went on receiving the remaining steps, and the 'upcoming emails' list
still showed them.
"""
from django.utils import timezone

from api.views import marketing_agent as views
from marketing_agent.models import CampaignContact, Lead, Reply, ReplySubSequenceRun
from marketing_agent.tests.base import MarketingTestCase


class RemovedLeadTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.spring = self.campaign(self.ann, name='Spring')
        self.autumn = self.campaign(self.ann, name='Autumn')
        self.spring_main = self.sequence(self.spring, steps=3, name='Spring')
        self.autumn_main = self.sequence(self.autumn, steps=3, name='Autumn')
        self.bilal = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring)
        self.autumn.leads.add(self.bilal)
        self.sana = self.lead(self.ann, 'sana@customer.test', campaign=self.spring)

    def remove(self, lead, campaign=None):
        campaign = campaign or self.spring
        code, body = self.call(views.delete_campaign_lead, self.ann_login, campaign_id=campaign.id, lead_id=lead.id)
        self.assertEqual(code, 200, body)
        return body['message']

    def follow_up(self, lead, campaign, **more):
        """A follow-up series started by a reply from `lead`, part-way through."""
        series = self.sequence(campaign, steps=2, name=f'{campaign.name} follow-up', is_sub_sequence=True,
                               parent_sequence=campaign.email_sequences.get(is_sub_sequence=False))
        contact = CampaignContact.objects.get_or_create(
            campaign=campaign, lead=lead, sequence=campaign.email_sequences.get(is_sub_sequence=False),
            defaults={'current_step': 0})[0]
        reply = Reply.objects.create(contact=contact, campaign=campaign, lead=lead, reply_subject='Re: hello',
                                     reply_content='Tell me more', replied_at=timezone.now())
        fields = dict(step=0)
        fields.update(more)
        return ReplySubSequenceRun.objects.create(reply=reply, contact=contact, campaign=campaign, lead=lead,
                                                  sub_sequence=series, **fields)

    def test_no_more_steps_of_that_campaign_but_the_other_campaign_carries_on(self):
        first = self.run_sender()
        self.assertCountEqual(first, [('bilal@customer.test', 'Spring 1'), ('bilal@customer.test', 'Autumn 1'),
                                      ('sana@customer.test', 'Spring 1')])

        self.assertEqual(self.remove(self.bilal), 'Lead removed from campaign')

        self.assertCountEqual(self.run_sender(), [('bilal@customer.test', 'Autumn 2'),
                                                  ('sana@customer.test', 'Spring 2')])
        self.assertCountEqual(self.run_sender(), [('bilal@customer.test', 'Autumn 3'),
                                                  ('sana@customer.test', 'Spring 3')])

    def test_the_contact_row_and_its_replies_are_kept(self):
        self.run_sender()
        run = self.follow_up(self.bilal, self.spring)
        self.remove(self.bilal)
        self.assertTrue(CampaignContact.objects.filter(campaign=self.spring, lead=self.bilal).exists())
        self.assertTrue(Reply.objects.filter(pk=run.reply_id).exists())

    def test_an_open_follow_up_series_is_closed_and_sends_nothing_more(self):
        self.run_sender()
        spring_run = self.follow_up(self.bilal, self.spring)
        autumn_run = self.follow_up(self.bilal, self.autumn)
        sanas_run = self.follow_up(self.sana, self.spring)
        finished = self.follow_up(self.bilal, self.spring, step=2, completed=True)

        self.remove(self.bilal)

        for run in (spring_run, autumn_run, sanas_run, finished):
            run.refresh_from_db()
        self.assertEqual([spring_run.cancelled, autumn_run.cancelled, sanas_run.cancelled, finished.cancelled],
                         [True, False, False, False])
        sent = self.run_sender()
        self.assertNotIn(('bilal@customer.test', 'Spring follow-up 1'), sent)
        self.assertIn(('bilal@customer.test', 'Autumn follow-up 1'), sent)
        self.assertIn(('sana@customer.test', 'Spring follow-up 1'), sent)

    def test_a_follow_up_row_left_open_for_a_removed_lead_is_still_not_sent(self):
        # The sender's own check, for rows closed by nothing (removed before this fix).
        self.run_sender()
        self.remove(self.bilal)
        self.follow_up(self.bilal, self.spring)
        self.assertNotIn(('bilal@customer.test', 'Spring follow-up 1'), self.run_sender())

    def test_the_upcoming_list_stops_showing_them(self):
        def listed():
            pending, upcoming = views._get_pending_and_upcoming_emails(self.spring)
            return sorted({row.get('recipient_email') or row.get('lead_email') for row in pending + upcoming})

        self.run_sender()                       # creates the contact rows; step one goes out
        self.follow_up(self.bilal, self.spring)
        self.assertEqual(listed(), ['bilal@customer.test', 'sana@customer.test'])
        self.remove(self.bilal)
        self.assertEqual(listed(), ['sana@customer.test'])
        # A follow-up row closed by nothing (removed before this fix) is not listed either.
        self.follow_up(self.bilal, self.spring)
        self.assertEqual(listed(), ['sana@customer.test'])

    def test_put_back_they_carry_on_from_where_they_were_not_from_the_start(self):
        self.run_sender()
        self.remove(self.bilal)
        self.spring.leads.add(self.bilal)
        sent = self.run_sender()
        self.assertIn(('bilal@customer.test', 'Spring 2'), sent)
        self.assertNotIn(('bilal@customer.test', 'Spring 1'), sent)

    def test_removed_from_the_lead_side_counts_as_well(self):
        self.run_sender()
        run = self.follow_up(self.bilal, self.spring)
        elsewhere = self.follow_up(self.bilal, self.autumn)
        self.bilal.campaigns.remove(self.spring)
        run.refresh_from_db()
        elsewhere.refresh_from_db()
        self.assertTrue(run.cancelled)
        self.assertFalse(elsewhere.cancelled)             # only the campaign they were taken out of
        self.assertNotIn('Spring 2', [subject for email, subject in self.run_sender()
                                      if email == 'bilal@customer.test'])

    def test_clearing_a_campaigns_list_closes_every_open_follow_up_in_it(self):
        self.run_sender()
        runs = [self.follow_up(self.bilal, self.spring), self.follow_up(self.sana, self.spring)]
        other = self.follow_up(self.bilal, self.autumn)
        self.spring.leads.clear()
        self.assertEqual([ReplySubSequenceRun.objects.get(pk=run.pk).cancelled for run in runs], [True, True])
        self.assertFalse(ReplySubSequenceRun.objects.get(pk=other.pk).cancelled)

    def test_a_lead_in_no_other_campaign_is_still_deleted_outright(self):
        self.assertEqual(self.remove(self.sana), 'Lead deleted successfully')
        self.assertFalse(Lead.objects.filter(pk=self.sana.pk).exists())
