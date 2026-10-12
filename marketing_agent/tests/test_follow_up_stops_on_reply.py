"""A follow-up series stops for a lead once they reply to it.

A reply to a main-sequence email stops the main sequence and starts the matching
follow-up series. A reply to one of the follow-up emails was recorded and
nothing else: the remaining steps of the follow-up went out whatever the lead
had answered. A comment in the code said the sender cleared the series; it did
not.
"""
from unittest import mock

from marketing_agent.models import ReplySubSequenceRun
from marketing_agent.services import reply_processor
from marketing_agent.tests.base import MarketingTestCase


class FollowUpStopsOnReplyTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.spring = self.campaign(self.ann, name='Spring')
        self.main = self.sequence(self.spring, steps=1, name='Spring')
        self.series = self.sequence(self.spring, steps=3, name='Thanks', is_sub_sequence=True,
                                    parent_sequence=self.main, interest_level='positive')
        self.bilal = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring)
        self.sana = self.lead(self.ann, 'sana@customer.test', campaign=self.spring)

    def replies(self, lead, subject, text='Sounds good', reads_as='positive', campaign=None):
        with mock.patch.object(reply_processor.ReplyAnalyzer, 'analyze_reply',
                               return_value={'interest_level': reads_as, 'analysis': ''}):
            result = reply_processor.process_reply_directly(campaign or self.spring, lead, subject, text)
        self.assertTrue(result['success'], result)
        return result

    def runs(self, lead, campaign=None):
        return list(ReplySubSequenceRun.objects.filter(campaign=campaign or self.spring, lead=lead).order_by('id'))

    def sent_to(self, lead, sent):
        return [subject for email, subject in sent if email == lead.email]

    def start_follow_ups(self):
        """Both leads get the first email, reply to it, and get the first follow-up."""
        self.run_sender()
        for lead in (self.bilal, self.sana):
            self.replies(lead, 'Re: Spring 1')
        sent = self.run_sender()
        self.assertEqual(self.sent_to(self.bilal, sent), ['Thanks 1'])

    def test_replying_to_a_follow_up_email_ends_that_series_for_that_lead(self):
        self.start_follow_ups()

        result = self.replies(self.bilal, 'Re: Thanks 1', 'Not right now, thanks', reads_as='neutral')

        [run] = self.runs(self.bilal)
        self.assertEqual((run.cancelled, run.completed, run.step), (True, False, 1))
        self.assertIn('will not be sent', result['message'])
        later = self.run_sender() + self.run_sender()
        self.assertEqual(self.sent_to(self.bilal, later), [])
        # Sana said nothing more and gets the rest of hers.
        self.assertEqual(self.sent_to(self.sana, later), ['Thanks 2', 'Thanks 3'])
        self.assertFalse(self.runs(self.sana)[0].cancelled)

    def test_without_a_reply_the_series_runs_to_its_end(self):
        self.start_follow_ups()
        later = self.run_sender() + self.run_sender() + self.run_sender()
        self.assertEqual(self.sent_to(self.bilal, later), ['Thanks 2', 'Thanks 3'])

    def test_a_reply_to_the_main_email_does_not_close_a_series_already_running(self):
        self.start_follow_ups()
        self.replies(self.bilal, 'Re: Spring 1', 'One more thing')
        first, second = self.runs(self.bilal)
        self.assertEqual((first.cancelled, second.cancelled), (False, False))

    def test_only_the_series_that_was_answered_is_closed(self):
        other = self.sequence(self.spring, steps=2, name='Details', is_sub_sequence=True,
                              parent_sequence=self.main, interest_level='requested_info')
        self.run_sender()
        self.replies(self.bilal, 'Re: Spring 1')                                       # starts 'Thanks'
        self.replies(self.bilal, 'Re: Spring 1', 'Send details', reads_as='requested_info')   # starts 'Details'
        self.run_sender()

        self.replies(self.bilal, 'Re: Thanks 1', 'ok', reads_as='neutral')

        by_series = {run.sub_sequence_id: run.cancelled for run in self.runs(self.bilal)}
        self.assertEqual(by_series, {self.series.id: True, other.id: False})

    def test_a_series_that_has_finished_is_left_as_it_is(self):
        self.start_follow_ups()
        self.run_sender()
        self.run_sender()
        [run] = self.runs(self.bilal)
        self.assertTrue(run.completed)
        self.replies(self.bilal, 'Re: Thanks 3', 'Got them all')
        run.refresh_from_db()
        self.assertEqual((run.completed, run.cancelled), (True, False))

    def test_the_same_lead_in_another_campaign_is_not_touched(self):
        autumn = self.campaign(self.ann, name='Autumn')
        autumn_main = self.sequence(autumn, steps=1, name='Autumn')
        self.sequence(autumn, steps=2, name='Autumn thanks', is_sub_sequence=True, parent_sequence=autumn_main,
                      interest_level='positive')
        autumn.leads.add(self.bilal)
        self.start_follow_ups()
        self.replies(self.bilal, 'Re: Autumn 1', campaign=autumn)

        self.replies(self.bilal, 'Re: Thanks 1', 'ok', reads_as='neutral')

        self.assertTrue(self.runs(self.bilal)[0].cancelled)
        self.assertFalse(self.runs(self.bilal, autumn)[0].cancelled)

    def test_a_template_used_by_two_series_closes_both(self):
        shared = self.series.steps.get(step_order=1).template
        twin = self.sequence(self.spring, steps=0, name='Twin', is_sub_sequence=True, parent_sequence=self.main,
                             interest_level='neutral')
        twin.steps.create(template=shared, step_order=1, delay_days=0)
        self.start_follow_ups()
        [run] = self.runs(self.bilal)
        twin_run = ReplySubSequenceRun.objects.create(
            reply=self.replies_record(self.bilal), contact=run.contact, campaign=self.spring, lead=self.bilal,
            sub_sequence=twin)

        self.replies(self.bilal, 'Re: Thanks 1', 'ok', reads_as='neutral')

        run.refresh_from_db()
        twin_run.refresh_from_db()
        self.assertEqual((run.cancelled, twin_run.cancelled), (True, True))

    def replies_record(self, lead):
        from marketing_agent.models import CampaignContact, Reply
        contact = CampaignContact.objects.filter(campaign=self.spring, lead=lead).first()
        return Reply.objects.create(contact=contact, campaign=self.spring, lead=lead, reply_subject='Re: x',
                                    reply_content='y')
