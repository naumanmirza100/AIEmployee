"""Only the people who run the account can change its AI keys.

Every dashboard login of a company, whatever its role, could add, replace or
delete the company's AI key for any agent, switch an agent's AI off for
everyone, change the spending cap and raise paid key requests. And any of them
could mark a key request as paid: the address took the company's word for it.
"""
from unittest import mock

from api.views import company_api_keys as views
from core.models import Agent, AgentTokenQuota, CompanyAPIKey, KeyRequest
from hr_agent.tests.base import HRTestCase
from project_manager_agent.models import PMNotification


class KeysAdminOnlyTests(HRTestCase):

    def setUp(self):
        super().setUp()
        Agent.objects.update_or_create(slug='hr_agent', defaults={'name': 'HR', 'default_provider': 'openai'})
        self.quota = AgentTokenQuota.objects.create(company=self.company, agent_name='hr_agent')

    def save_key(self, actor):
        with mock.patch.object(views, '_validate_byok_key', return_value=(True, '')):
            return self.call(views.upsert_byok_key, actor,
                             {'agent_name': 'hr_agent', 'provider': 'groq', 'api_key': 'synthetic-key-0123456789'})

    def own_key(self):
        key = CompanyAPIKey(company=self.company, agent_name='hr_agent', mode='byok', provider='groq',
                            status='active', encrypted_key='')
        key.set_plaintext_key('synthetic-key-0123456789')
        key.save()
        return key

    def refused(self, code, body):
        self.assertEqual((code, body.get('code')), (403, 'admins_only'), body)

    # ---- a member can look, not change -------------------------------------

    def test_a_member_can_see_the_keys_page_and_is_told_it_is_read_only(self):
        code, body = self.call(views.list_agent_keys, self.member, method='get')
        self.assertEqual((code, body['can_manage']), (200, False))
        self.assertEqual([a['agent_name'] for a in body['agents']], ['hr_agent'])
        self.assertTrue(self.call(views.list_agent_keys, self.admin, method='get')[1]['can_manage'])

    def test_a_member_cannot_add_or_replace_a_key(self):
        self.refused(*self.save_key(self.member))
        self.assertFalse(CompanyAPIKey.objects.exists())

    def test_or_delete_one(self):
        self.own_key()
        self.refused(*self.call(views.revoke_byok_key, self.member, method='delete', agent_name='hr_agent'))
        self.assertTrue(CompanyAPIKey.objects.exists())

    def test_or_switch_an_agents_ai_off_for_everyone(self):
        self.refused(*self.call(views.set_token_pool, self.member, {'agent_name': 'hr_agent', 'preferred_pool': 'none'}))
        self.quota.refresh_from_db()
        self.assertEqual(self.quota.preferred_pool, 'managed')

    def test_or_change_the_spending_cap(self):
        self.refused(*self.call(views.set_byok_limit, self.member, {'agent_name': 'hr_agent', 'limit': 5}))
        self.quota.refresh_from_db()
        self.assertEqual(self.quota.byok_token_limit, 0)

    def test_or_ask_for_a_paid_key_or_start_paying_for_one(self):
        self.refused(*self.call(views.create_key_request, self.member, {'agent_name': 'hr_agent', 'provider': 'openai'}))
        self.assertFalse(KeyRequest.objects.exists())
        request = KeyRequest.objects.create(company=self.company, agent_name='hr_agent', provider='openai',
                                            status='payment_pending')
        self.refused(*self.call(views.create_key_checkout_session, self.member, request_id=request.id))

    # ---- an admin still can ---------------------------------------------------

    def test_an_admin_can_do_all_of_it(self):
        code, body = self.save_key(self.admin)
        self.assertEqual(code, 200, body)
        self.assertEqual(self.call(views.set_byok_limit, self.admin, {'agent_name': 'hr_agent', 'limit': 5})[0], 200)
        self.assertEqual(self.call(views.set_token_pool, self.admin,
                                   {'agent_name': 'hr_agent', 'preferred_pool': 'free'})[0], 200)
        self.assertEqual(self.call(views.revoke_byok_key, self.admin, method='delete', agent_name='hr_agent')[0], 200)
        self.assertFalse(CompanyAPIKey.objects.exists())

    # ---- nobody marks a request paid by saying so -------------------------------

    def test_a_request_cannot_be_marked_paid_without_paying(self):
        request = KeyRequest.objects.create(company=self.company, agent_name='hr_agent', provider='openai',
                                            status='payment_pending', key_cost_snapshot=40, service_charge_snapshot=10)
        with mock.patch('core.notification_utils.notify_admins') as told:
            code, body = self.call(views.pay_for_key_request, self.admin, request_id=request.id)
        self.assertEqual((code, body['code']), (400, 'use_checkout'), body)
        request.refresh_from_db()
        self.assertEqual((request.status, request.amount_paid, request.paid_at), ('payment_pending', None, None))
        told.assert_not_called()                              # nobody is told "payment received"

    def test_another_companys_request_is_not_found(self):
        request = KeyRequest.objects.create(company=self.rival, agent_name='hr_agent', provider='openai',
                                            status='payment_pending')
        self.assertEqual(self.call(views.pay_for_key_request, self.admin, request_id=request.id)[0], 404)
