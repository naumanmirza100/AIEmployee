"""Reply checking only ever signs in with the campaign's own mailbox.

A campaign with no mailbox name did not skip reply checking: it borrowed the
platform's own mailbox name and password from the server settings, while the
inbox server stayed whatever had been typed for that campaign. So the platform's
login could be offered to a mail server the platform does not run, and mail in
the platform's own inbox could be read into a customer's campaign.
"""
from unittest import mock

from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views

PLATFORM = dict(EMAIL_HOST='smtp.platform.example', EMAIL_HOST_USER='platform@platform.example',
                EMAIL_HOST_PASSWORD='the-platforms-own')


@override_settings(**PLATFORM)
class ReplyMailboxTests(SDRBase):

    def credentials(self, **changed):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(**changed)
        self.campaign.refresh_from_db()
        return self.agent()._get_imap_credentials(self.campaign)

    def test_a_campaign_with_its_own_mailbox_uses_it(self):
        self.assertEqual(self.credentials(), ('imap.test', 993, 'u', 'p'))
        self.assertEqual(self.credentials(imap_host='mail.acme.example', imap_port=1993),
                         ('mail.acme.example', 1993, 'u', 'p'))

    def test_no_mailbox_name_means_no_login_at_all(self):
        for changed in (dict(smtp_username=''), dict(smtp_password=''), dict(smtp_username='', smtp_password='')):
            SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_username='u', smtp_password='p')
            host, _, username, password = self.credentials(imap_host='imap.somewhere-else.example', **changed)
            self.assertEqual((host, username, password), ('', '', ''), changed)

    def test_the_platforms_login_is_never_what_comes_back(self):
        with mock.patch.dict('os.environ', {'IMAP_HOST': 'imap.platform.example'}):
            for changed in (dict(), dict(smtp_username=''), dict(smtp_host='', imap_host=''),
                            dict(smtp_username='', smtp_host='', imap_host='')):
                SDRCampaign.objects.filter(pk=self.campaign.pk).update(
                    smtp_username='u', smtp_password='p', smtp_host='smtp.test', imap_host='')
                found = self.credentials(**changed)
                for platform_value in ('platform@platform.example', 'the-platforms-own', 'imap.platform.example',
                                       'smtp.platform.example'):
                    self.assertNotIn(platform_value, found, changed)

    def test_reply_checking_skips_such_a_campaign_without_connecting(self):
        enrolment = self.enroll(self.make_lead())
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_username='',
                                                               imap_host='imap.somewhere-else.example')
        self.campaign.refresh_from_db()
        with mock.patch.object(oa.imaplib, 'IMAP4_SSL') as connect:
            self.assertEqual(self.agent().check_inbox_for_replies(self.campaign, [enrolment]), [])
        connect.assert_not_called()

    def test_a_campaign_with_a_login_but_no_server_to_ask_is_skipped_too(self):
        enrolment = self.enroll(self.make_lead())
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_host='', imap_host='')
        self.campaign.refresh_from_db()
        with mock.patch.object(oa.imaplib, 'IMAP4_SSL') as connect:
            self.assertEqual(self.agent().check_inbox_for_replies(self.campaign, [enrolment]), [])
        connect.assert_not_called()


class MailboxCannotBeTakenAwayTests(SDRBase):
    """Once leads are enrolled, the mailbox settings can be changed but not blanked."""

    def put(self, **data):
        request = APIRequestFactory().put('/x', data, format='json')
        force_authenticate(request, user=self.cu)
        # The host check looks the server up on the internet; these tests are about something else.
        with mock.patch.object(views, '_validate_mail_settings', return_value=None):
            return views.sdr_campaign_detail(request, campaign_id=self.campaign.id)

    def saved(self):
        campaign = SDRCampaign.objects.get(pk=self.campaign.pk)
        return campaign.smtp_host, campaign.smtp_username

    def test_blanking_the_mailbox_is_refused_when_leads_are_enrolled(self):
        self.enroll(self.make_lead())
        for data in (dict(smtp_username=''), dict(smtp_host='  '), dict(smtp_username=None, smtp_host='')):
            response = self.put(**data)
            self.assertEqual(response.status_code, 400, data)
            self.assertIn('can be changed but not removed', response.data['message'])
            self.assertEqual(self.saved(), ('smtp.test', 'u'))

    def test_changing_it_is_still_allowed(self):
        self.enroll(self.make_lead())
        response = self.put(smtp_username='new@acme.example', smtp_host='smtp.acme.example')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.saved(), ('smtp.acme.example', 'new@acme.example'))

    def test_a_campaign_with_nobody_enrolled_can_still_be_emptied(self):
        response = self.put(smtp_username='')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.saved(), ('smtp.test', ''))

    def test_other_edits_are_not_held_up(self):
        self.enroll(self.make_lead())
        self.assertEqual(self.put(name='Renamed').status_code, 200)
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).name, 'Renamed')
