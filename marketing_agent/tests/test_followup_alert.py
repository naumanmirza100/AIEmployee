"""The "Create Follow-up Email Sequences" alert must not fire for a campaign whose sequence already follows up.

It looked for "follow" in a sequence's name, so "Care plan: three emails" (three emails over ten days) was told it
had no follow-ups, and it counted only delivered, opened or clicked sends, so seven emails read as "1 leads".
"""
from django.utils import timezone

from marketing_agent.agents.proactive_notification_agent import ProactiveNotificationAgent
from marketing_agent.models import EmailSendHistory, MarketingNotification
from marketing_agent.tests.base import MarketingTestCase


class FollowUpAlertTests(MarketingTestCase):

    def alerts_for(self, steps, name):
        care = self.campaign(self.ann, name='Care plan')
        self.sequence(care, steps=steps, name=name)
        for email, status in (('nadia@shop.test', 'opened'), ('faisal@north.test', 'sent')):
            lead = self.lead(self.ann, email, campaign=care)
            EmailSendHistory.objects.create(campaign=care, lead=lead, subject='Hi', recipient_email=email,
                                            status=status, sent_at=timezone.now())
        ProactiveNotificationAgent()._check_actionable_recommendations(care, self.ann)
        return list(MarketingNotification.objects.filter(campaign=care, title__contains='Create Follow-up')
                    .values_list('message', flat=True))

    def test_a_sequence_of_several_emails_needs_no_follow_up_alert(self):
        self.assertEqual(self.alerts_for(3, 'Care plan: three emails'), [])

    def test_a_single_email_sequence_is_told_to_follow_up(self):
        [message] = self.alerts_for(1, 'Care plan: one email')
        self.assertIn('has contacted 2 leads but no follow-up sequences', message)
