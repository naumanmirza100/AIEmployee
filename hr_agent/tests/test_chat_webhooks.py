"""The Slack and Teams addresses HR and Frontline post to can be set, by the owner or an admin (CO-64).

The four Company fields existed but no screen filled them in; the template forms offered Slack and Teams ("uses PM
webhook", which they did not), so every such message was dropped with a log line.
"""
from unittest import mock

from api.views import notification_settings as views

from .base import HRTestCase

SLACK = 'https://hooks.slack.com/services/T000/B000/abcdefghijklmnopqrstuvwx'


class ChatWebhooksTests(HRTestCase):

    def test_an_admin_sets_one_and_sees_it_masked(self):
        code, body = self.call(views.chat_webhooks, self.admin, {'agent': 'hr_agent', 'channel': 'slack', 'url': SLACK},
                               method='patch')
        self.assertEqual(code, 200, body)
        self.company.refresh_from_db()
        self.assertEqual(self.company.hr_slack_webhook_url, SLACK)
        code, body = self.call(views.chat_webhooks, self.admin, method='get')
        hr = body['data']['agents'][0]
        self.assertEqual(hr['agent'], 'hr_agent')
        self.assertTrue(hr['slack']['set'])
        self.assertNotIn('abcdefghijklmnop', hr['slack']['shown'])
        self.assertFalse(hr['teams']['set'])
        self.assertTrue(body['data']['can_edit'])

    def test_only_agents_the_company_has_are_listed(self):
        _, body = self.call(views.chat_webhooks, self.admin, method='get')
        self.assertEqual([a['agent'] for a in body['data']['agents']], ['hr_agent'])
        self.buy_module(self.company, 'frontline_agent')
        _, body = self.call(views.chat_webhooks, self.admin, method='get')
        self.assertEqual([a['agent'] for a in body['data']['agents']], ['hr_agent', 'frontline_agent'])

    def test_a_wrong_address_is_refused_with_why(self):
        code, body = self.call(views.chat_webhooks, self.admin,
                               {'agent': 'hr_agent', 'channel': 'slack', 'url': 'https://example.com/hook'},
                               method='patch')
        self.assertEqual(code, 400)
        self.assertIn('hooks.slack.com', body['message'])
        code, body = self.call(views.chat_webhooks, self.admin,
                               {'agent': 'hr_agent', 'channel': 'teams', 'url': 'http://x.webhook.office.com/a'},
                               method='patch')
        self.assertEqual(code, 400)
        self.assertIn('https://', body['message'])
        self.company.refresh_from_db()
        self.assertEqual(self.company.hr_teams_webhook_url, '')

    def test_a_member_cannot_set_or_test_and_is_told_why(self):
        code, body = self.call(views.chat_webhooks, self.member, {'agent': 'hr_agent', 'channel': 'slack', 'url': SLACK},
                               method='patch')
        self.assertEqual(code, 403)
        self.assertEqual(body['code'], 'admins_only')
        self.assertIn("Only the company's owner or an admin", body['message'])
        self.company.refresh_from_db()
        self.assertEqual(self.company.hr_slack_webhook_url, '')
        _, body = self.call(views.chat_webhooks, self.member, method='get')
        self.assertFalse(body['data']['can_edit'])

    def test_an_agent_the_company_lacks_is_refused(self):
        code, _ = self.call(views.chat_webhooks, self.admin,
                            {'agent': 'frontline_agent', 'channel': 'slack', 'url': SLACK}, method='patch')
        self.assertEqual(code, 400)

    def test_the_test_message_goes_to_the_saved_address(self):
        code, body = self.call(views.chat_webhooks, self.admin, {'agent': 'hr_agent', 'channel': 'slack'})
        self.assertEqual(code, 400)
        self.assertIn('No Slack address is set for HR', body['message'])
        self.company.hr_slack_webhook_url = SLACK
        self.company.save(update_fields=['hr_slack_webhook_url'])
        with mock.patch('api.views.hr_agent._send_hr_notification_slack', return_value=True) as send:
            code, _ = self.call(views.chat_webhooks, self.admin, {'agent': 'hr_agent', 'channel': 'slack'})
        self.assertEqual(code, 200)
        self.assertEqual(send.call_args.args[0].hr_slack_webhook_url, SLACK)
        with mock.patch('api.views.hr_agent._send_hr_notification_slack', return_value=False):
            code, body = self.call(views.chat_webhooks, self.admin, {'agent': 'hr_agent', 'channel': 'slack'})
        self.assertEqual(code, 502)
        self.assertIn('did not accept', body['message'])

    def test_clearing_one(self):
        self.company.hr_teams_webhook_url = 'https://acme.webhook.office.com/webhookb2/abc'
        self.company.save(update_fields=['hr_teams_webhook_url'])
        code, _ = self.call(views.chat_webhooks, self.admin, {'agent': 'hr_agent', 'channel': 'teams', 'url': ''},
                            method='patch')
        self.assertEqual(code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.hr_teams_webhook_url, '')
