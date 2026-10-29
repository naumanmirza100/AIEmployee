"""Marketing and Operations alerts that need someone reach the shared bell.

Both agents kept their alerts on their own Notifications page. A campaign that could
not start, or a document that could not be read, waited there until someone looked.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyUser
from marketing_agent.agents.proactive_notification_agent import ProactiveNotificationAgent
from marketing_agent.models import Campaign, MarketingNotification
from operations_agent.models import OperationsDocument
from project_manager_agent.models import PMNotification


class BellTestCase(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Averon', email='averon@test.local')
        self.login_user = User.objects.create_user('hamza', 'hamza@averon.test', 'x')
        self.hamza = CompanyUser.objects.create(company=self.company, email='hamza@averon.test', full_name='Hamza',
                                                role='owner', password_hash='x', is_active=True,
                                                login_user=self.login_user)

    def bell(self):
        return list(PMNotification.objects.filter(company_user=self.hamza).values_list('title', 'data'))


class MarketingBellTests(BellTestCase):

    def setUp(self):
        super().setUp()
        self.campaign = Campaign.objects.create(name='App Care Plan 2027', owner=self.login_user,
                                                start_date=timezone.now().date(),
                                                end_date=timezone.now().date() + timedelta(days=40))
        self.agent = ProactiveNotificationAgent()

    def alert(self, title, action_required=True):
        return self.agent._create_notification(self.login_user, self.campaign, 'campaign_status', 'high', title,
                                               'Add an email template before it can start.',
                                               action_required=action_required)

    def test_an_alert_that_needs_action_reaches_the_owner_s_bell_with_a_link_to_the_campaign(self):
        self.alert('Scheduled campaign cannot start: App Care Plan 2027')
        [(title, data)] = self.bell()
        self.assertEqual(title, 'Scheduled campaign cannot start: App Care Plan 2027')
        self.assertEqual(data['link'], f'/marketing/dashboard/campaign/{self.campaign.id}')

    def test_an_alert_for_information_only_stays_in_marketing(self):
        self.alert('Open rate is up 12%', action_required=False)
        self.assertEqual(self.bell(), [])

    def test_the_same_alert_is_raised_once_a_week_even_after_it_is_read(self):
        first = self.alert('Mailbox stopped sending')
        MarketingNotification.objects.filter(pk=first.pk).update(is_read=True)
        # Read is not "raise it again": it came back within half an hour, every day (CO-133).
        self.assertIsNone(self.alert('Mailbox stopped sending'))
        self.assertEqual(len(self.bell()), 1)


class OperationsBellTests(BellTestCase):

    def document(self, **fields):
        return OperationsDocument.objects.create(company=self.company, uploaded_by=self.hamza, title='FinEdge MSA',
                                                 original_filename='FinEdge_MSA.pdf', file='operations/msa.pdf',
                                                 **fields)

    def test_a_document_that_could_not_be_read_tells_its_uploader_once(self):
        doc = self.document()
        self.assertEqual(self.bell(), [])
        doc.processing_error = 'No text could be extracted from this document.'
        doc.processing_status = 'failed'
        doc.save()
        doc.save()
        [(title, data)] = self.bell()
        self.assertEqual(title, 'Could not read FinEdge_MSA.pdf')
        self.assertEqual(data['link'], '/operations/documents')

    def test_a_document_that_is_read_does_not_ring_the_bell(self):
        doc = self.document()
        doc.is_processed, doc.processed_at, doc.processing_status = True, timezone.now(), 'ready'
        doc.save()
        self.assertEqual(self.bell(), [])
