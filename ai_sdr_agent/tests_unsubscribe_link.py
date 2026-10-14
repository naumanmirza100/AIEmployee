"""An unsubscribe link in a sales email keeps working after its campaign is gone.

The link named only the enrolment that sent the email. Deleting the campaign, or
pressing Clear Leads, deleted the enrolment; from then on the link showed 'This
link is no longer valid' with words about rescheduling a meeting, and answered
200, which a mail program's one-click unsubscribe takes to mean it worked. The
lead was still in the leads list, nothing was on the do-not-email list, and they
could be enrolled again.
"""
from django.test import Client
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRLead, SDRRemovedEnrollment
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.do_not_email import is_blocked
from core.models import Company, CompanyUser


class UnsubscribeLinkTests(SDRBase):

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead()
        self.enrolment = self.enroll(self.lead)
        self.new_link = self.path(oa.build_unsubscribe_url(self.enrolment))
        # As in an email sent before links carried the company and the address.
        self.old_link = '/api/sdr/unsubscribe/' + oa.make_unsubscribe_token(self.enrolment.id) + '/'

    def path(self, url):
        return '/api/sdr/unsubscribe/' + url.split('/api/sdr/unsubscribe/')[1]

    def as_owner(self, view, method='post', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=self.cu)
        return view(request, **kwargs)

    def blocked(self):
        return is_blocked(self.company.id, 'bob@acme.com')

    # ---- what the link carries ---------------------------------------------

    def test_a_new_link_names_the_company_and_the_address(self):
        claims = oa.read_unsubscribe_token(self.new_link.rstrip('/').rsplit('/', 1)[1])
        self.assertEqual(claims, {'e': self.enrolment.id, 'c': self.company.id, 'm': 'bob@acme.com'})

    def test_a_link_nobody_signed_is_refused_and_says_so(self):
        for bad in ('/api/sdr/unsubscribe/garbage/', self.new_link[:-6] + 'xxxxx/'):
            for response in (Client().get(bad), Client().post(bad)):
                self.assertEqual(response.status_code, 404)
                self.assertIn(b'could not unsubscribe you', response.content)
                self.assertNotIn(b'meeting', response.content.lower())
        self.assertFalse(self.blocked())

    # ---- campaign deleted ----------------------------------------------------

    def test_after_the_campaign_is_deleted_a_new_link_still_unsubscribes(self):
        self.assertEqual(self.as_owner(views.sdr_campaign_detail, 'delete', campaign_id=self.campaign.id).status_code,
                         200)
        self.assertFalse(SDRCampaignEnrollment.objects.filter(pk=self.enrolment.pk).exists())

        self.assertEqual(Client().get(self.new_link).status_code, 200)
        self.assertFalse(self.blocked())                                   # opening the link changes nothing
        response = Client().post(self.new_link)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You've been unsubscribed", response.content)
        self.assertTrue(self.blocked())
        self.assertEqual(SDRLead.all_objects.get(pk=self.lead.pk).status, 'disqualified')

    def test_a_new_link_needs_nothing_else_to_have_been_kept(self):
        self.campaign.delete()
        SDRRemovedEnrollment.objects.all().delete()
        self.assertEqual(Client().post(self.new_link).status_code, 200)
        self.assertTrue(self.blocked())

    def test_and_so_does_a_link_from_an_email_sent_before_this_change(self):
        self.campaign.delete()
        self.assertEqual(Client().post(self.old_link).status_code, 200)
        self.assertTrue(self.blocked())

    def test_after_clear_leads_both_kinds_of_link_still_work(self):
        # (Clear Leads removes them and then reports an error of its own, CO-147; only the removal matters here.)
        self.as_owner(views.sdr_clear_campaign_leads, campaign_id=self.campaign.id)
        self.assertFalse(SDRCampaignEnrollment.objects.filter(pk=self.enrolment.pk).exists())
        self.assertEqual(Client().post(self.old_link).status_code, 200)
        self.assertTrue(self.blocked())
        self.assertEqual(Client().post(self.new_link).status_code, 200)

    def test_they_cannot_then_be_emailed_from_a_new_campaign(self):
        self.campaign.delete()
        Client().post(self.new_link)
        again = SDRCampaign.objects.create(company_user=self.cu, name='Again', status='active', smtp_host='h',
                                           smtp_username='u', smtp_password='p')
        enrolment = self.enroll(self.lead, campaign=again)
        self.assertTrue(oa.is_email_suppressed(self.cu, 'bob@acme.com'))
        self.assertEqual(self.agent().process_enrollment(enrolment)['status'], 'suppressed')

    def test_other_enrolments_of_the_same_address_in_the_company_stop_too(self):
        other = SDRCampaign.objects.create(company_user=self.cu, name='Other', status='active', smtp_host='h',
                                           smtp_username='u', smtp_password='p')
        still_there = self.enroll(self.lead, campaign=other)
        self.campaign.delete()
        Client().post(self.new_link)
        still_there.refresh_from_db()
        self.assertEqual(still_there.status, 'unsubscribed')

    # ---- what is kept when an enrolment goes ----------------------------------

    def test_deleting_an_enrolment_leaves_who_its_link_was_for(self):
        number = self.enrolment.id
        self.enrolment.delete()
        kept = SDRRemovedEnrollment.objects.get(enrollment_id=number)
        self.assertEqual((kept.company_id, kept.email), (self.company.id, 'bob@acme.com'))

    def test_an_old_link_with_nothing_left_behind_says_it_did_not_work(self):
        self.campaign.delete()
        SDRRemovedEnrollment.objects.all().delete()          # as for a campaign deleted before this change
        for response in (Client().get(self.old_link), Client().post(self.old_link)):
            self.assertEqual(response.status_code, 410)
            self.assertIn(b'could not unsubscribe you', response.content)
            self.assertIn(b'reply to the email', response.content.lower())
        self.assertFalse(self.blocked())

    # ---- it only ever acts for the company in the link -------------------------

    def test_another_company_with_the_same_address_is_not_touched(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rita = CompanyUser.objects.create(company=rival, email='rita@rival.test', full_name='Rita', role='admin',
                                          password_hash='x', is_active=True)
        theirs = SDRLead.objects.create(company_user=rita, email='bob@acme.com', first_name='Bob')
        their_campaign = SDRCampaign.objects.create(company_user=rita, name='Rival outreach', status='active')
        their_enrolment = self.enroll(theirs, campaign=their_campaign)
        self.campaign.delete()
        Client().post(self.new_link)
        self.assertTrue(self.blocked())
        self.assertFalse(is_blocked(rival.id, 'bob@acme.com'))
        self.assertNotEqual(SDRLead.all_objects.get(pk=theirs.pk).status, 'disqualified')
        their_enrolment.refresh_from_db()
        self.assertEqual(their_enrolment.status, 'active')            # their campaign carries on

    def test_while_the_enrolment_exists_it_works_as_before(self):
        self.assertEqual(Client().post(self.new_link).status_code, 200)
        self.enrolment.refresh_from_db()
        self.assertEqual(self.enrolment.status, 'unsubscribed')
        self.assertTrue(self.blocked())
