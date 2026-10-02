"""Floating Quick Chat history is kept on the server, per login.

PM's, HR's and Frontline's floating chats kept their history in the browser:
lost on another device or after clearing it, and shown to whoever logged in
next on a shared computer.
"""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import quick_chats as views
from core.models import Company, CompanyUser, QuickChat


def message(role, content, **extra):
    return {'role': role, 'content': content, **extra}


class QuickChatTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.ann = self.login(company, 'ann@test.local')
        self.ben = self.login(company, 'ben@test.local')

    def login(self, company, email):
        return CompanyUser.objects.create(company=company, email=email, full_name=email.split('@')[0],
                                          role='admin', password_hash='x', is_active=True)

    def call(self, method, actor, data=None, client_id=None, query=''):
        factory = APIRequestFactory()
        path = '/?' + query
        request = (factory.get(path) if method == 'get' else
                   factory.delete(path) if method == 'delete' else
                   getattr(factory, method)(path, data or {}, format='json'))
        force_authenticate(request, user=actor)
        if client_id is None:
            response = views.list_quick_chats(request)
        else:
            response = views.quick_chat(request, client_id=client_id)
        response.render()
        return response.status_code, response.data

    def save(self, client_id, messages, actor=None, agent='pm', mode='pilot', title='Plan the launch', method='put'):
        return self.call(method, actor or self.ann, {'agent': agent, 'mode': mode, 'title': title,
                                                     'messages': messages}, client_id=client_id)

    def listing(self, actor=None, agent='pm', mode='pilot'):
        code, body = self.call('get', actor or self.ann, query=f'agent={agent}&mode={mode}')
        self.assertEqual(code, 200, body)
        return body['data']

    def test_a_conversation_saved_in_one_browser_is_there_in_another(self):
        code, body = self.save('pmfc_1', [message('user', 'Create a task'),
                                          message('assistant', 'Review this', draftState='open')])
        self.assertEqual(code, 200, body)
        [chat] = self.listing()
        self.assertEqual((chat['id'], chat['title'], len(chat['messages'])), ('pmfc_1', 'Plan the launch', 2))
        self.assertEqual(chat['messages'][1]['draftState'], 'open')      # everything the chat keeps, kept
        self.assertIsInstance(chat['updated_at'], int)

    def test_saving_again_replaces_it(self):
        self.save('pmfc_1', [message('assistant', 'Review this', draftState='open')])
        self.save('pmfc_1', [message('assistant', 'Review this', draftState='done'), message('assistant', 'Done.')])
        [chat] = self.listing()
        self.assertEqual([m.get('draftState') for m in chat['messages']], ['done', None])
        self.assertEqual(QuickChat.objects.count(), 1)

    def test_the_page_closing_saves_with_post_too(self):
        self.assertEqual(self.save('hrfc_1', [message('user', 'Leave policy?')], agent='hr', mode='',
                                   method='post')[0], 200)
        self.assertEqual(len(self.listing(agent='hr', mode='')), 1)

    def test_each_login_sees_only_its_own(self):
        self.save('pmfc_1', [message('user', 'Mine')])
        self.assertEqual(self.listing(actor=self.ben), [])
        # The same id from another login is a different conversation.
        self.save('pmfc_1', [message('user', 'Ben too')], actor=self.ben)
        self.assertEqual(self.listing()[0]['messages'][0]['content'], 'Mine')
        self.call('delete', self.ben, client_id='pmfc_1', query='agent=pm')
        self.assertEqual(len(self.listing()), 1)

    def test_each_agent_and_mode_has_its_own_list(self):
        self.save('pmfc_1', [message('user', 'Pilot')])
        self.save('pmfc_2', [message('user', 'Q&A')], mode='qa')
        self.save('fc_3', [message('user', 'Frontline')], agent='frontline', mode='')
        self.assertEqual([c['id'] for c in self.listing()], ['pmfc_1'])
        self.assertEqual([c['id'] for c in self.listing(mode='qa')], ['pmfc_2'])
        self.assertEqual([c['id'] for c in self.listing(agent='frontline', mode='')], ['fc_3'])

    def test_deleting_forgets_it(self):
        self.save('pmfc_1', [message('user', 'x')])
        self.assertEqual(self.call('delete', self.ann, client_id='pmfc_1', query='agent=pm')[0], 200)
        self.assertEqual(self.listing(), [])

    def test_only_the_newest_are_kept(self):
        for n in range(views.KEEP + 3):
            self.save(f'pmfc_{n}', [message('user', str(n))])
        chats = self.listing()
        self.assertEqual(len(chats), views.KEEP)
        self.assertEqual(chats[0]['id'], f'pmfc_{views.KEEP + 2}')
        self.assertNotIn('pmfc_0', [c['id'] for c in chats])

    def test_bad_input_is_refused(self):
        self.assertEqual(self.save('x1', [message('user', 'x')], agent='sales')[0], 400)
        self.assertEqual(self.save('x1', [message('user', 'x')], mode='nope')[0], 400)
        self.assertEqual(self.save('x1', 'not a list')[0], 400)
        self.assertEqual(self.save('x1', [message('user', 'x')] * (views.MAX_MESSAGES + 1))[0], 413)
        self.assertEqual(self.call('get', self.ann, query='agent=sales')[0], 400)
        self.assertFalse(QuickChat.objects.exists())
