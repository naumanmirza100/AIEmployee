"""The two engagement alerts of the campaign check: "No Engagement Detected" and "Emails Opened But No Clicks/Replies".

Since the campaign figures were shared (29 Oct 2026) that block still read a variable the change removed, so the
check failed with a NameError for every campaign that had sent 10 emails, every 30 minutes, and neither alert ever came.
"""
from datetime import timedelta

from django.utils import timezone

from marketing_agent.agents.proactive_notification_agent import ProactiveNotificationAgent
from marketing_agent.models import EmailSendHistory, MarketingNotification
from marketing_agent.tests.base import MarketingTestCase


class EngagementAlertTests(MarketingTestCase):

    def sent(self, campaign, status, hours_ago, count=10):
        when = timezone.now() - timedelta(hours=hours_ago)
        template = self.template(campaign)   # the campaign's own emails have a template (campaign_sends)
        for i in range(count):
            email = f'person{i}@clinic{i}.test'
            lead = self.lead(self.ann, email, campaign=campaign)
            EmailSendHistory.objects.create(campaign=campaign, lead=lead, email_template=template, subject='Hi',
                                            recipient_email=email, status=status, sent_at=when)

    def titles(self, campaign):
        ProactiveNotificationAgent()._check_performance_metrics(campaign, self.ann)
        return list(MarketingNotification.objects.filter(campaign=campaign).values_list('title', flat=True))

    def test_ten_emails_a_day_ago_with_no_click_or_reply_raise_no_engagement(self):
        quiet = self.campaign(self.ann, name='Clinic intro')
        self.sent(quiet, 'delivered', hours_ago=30)
        titles = self.titles(quiet)
        self.assertTrue(any('No Engagement Detected' in t for t in titles), titles)

    def test_opens_without_clicks_or_replies_after_two_days_raise_their_alert(self):
        opened = self.campaign(self.ann, name='Clinic follow-up')
        self.sent(opened, 'opened', hours_ago=60)
        titles = self.titles(opened)
        self.assertTrue(any('Emails Opened But No Clicks/Replies' in t for t in titles), titles)

    def test_emails_sent_an_hour_ago_raise_neither_yet(self):
        fresh = self.campaign(self.ann, name='Clinic launch')
        self.sent(fresh, 'delivered', hours_ago=1)
        titles = self.titles(fresh)
        self.assertFalse(any('Engagement' in t or 'No Clicks/Replies' in t for t in titles), titles)
