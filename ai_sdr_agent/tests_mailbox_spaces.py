"""A space around a mailbox setting does not stop a campaign.

The hosts are typed or pasted into the campaign form. "srv1983265.hstgr.cloud " (a space copied with it) passed
the check, which strips before it looks, and was saved as it was: every email failed with "Name or service not
known" and no reply was read, while the same settings without the space worked.
"""
from unittest import mock

from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import SDRCampaign
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views


class MailboxSpacesTests(SDRBase):

    def test_a_new_campaign_keeps_the_settings_without_the_spaces(self):
        campaign = SDRCampaign.objects.create(
            company_user=self.cu, name='Digital banking apps, Q4', from_email=' adeel@crestline.test ',
            smtp_host='srv1983265.hstgr.cloud ', smtp_username='\tadeel@crestline.test', imap_host=' srv1983265.hstgr.cloud')
        campaign.refresh_from_db()
        self.assertEqual((campaign.from_email, campaign.smtp_host, campaign.smtp_username, campaign.imap_host),
                         ('adeel@crestline.test', 'srv1983265.hstgr.cloud', 'adeel@crestline.test',
                          'srv1983265.hstgr.cloud'))

    def test_an_edit_through_the_screen_keeps_them_without_the_spaces_too(self):
        request = APIRequestFactory().put(f'/api/sdr/campaigns/{self.campaign.id}', {
            'smtp_host': 'smtp.gmail.com  ', 'imap_host': ' imap.gmail.com'}, format='json')
        force_authenticate(request, user=self.cu)
        with mock.patch.object(views, '_validate_mail_settings', return_value=None):     # no DNS lookups in tests
            response = views.sdr_campaign_detail(request, campaign_id=self.campaign.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.smtp_host, self.campaign.imap_host), ('smtp.gmail.com', 'imap.gmail.com'))
