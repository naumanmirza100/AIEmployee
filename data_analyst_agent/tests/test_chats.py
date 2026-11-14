"""The Data Analyst's chats (14 Nov 2026): a list on the left, each chat on one database, each only its asker's.

The screen asked for a database first and listed only that database's past conversations. Now every chat is listed,
with the database it is about, and a chat stays on that database: asking another one in it is refused, and the screen
offers the last chat on the other database, or a new one. A chat's id named by someone else was taken as theirs.
"""
from api.views import data_analyst_agent as views
from data_analyst_agent.models import DataQuestion, DataSource

from .test_data_analyst import AnalystCase, FakeAI

COUNT = {'sql': 'SELECT count(*) AS n FROM orders'}


class ChatTests(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()
        code, body = self.upload(self.admin, name='Sales')
        self.assertEqual(code, 201, body)
        self.sales = DataSource.objects.get(pk=body['data']['id'])

    def asked(self, actor, source, question, **extra):
        code, body = self.ask(actor, source, question, FakeAI(COUNT, '4 orders.'), **extra)
        return code, body

    def chats(self, actor):
        code, body = self.call(views.chats, actor, method='get')
        self.assertEqual(code, 200, body)
        return body['data']

    def test_every_chat_is_listed_newest_first_with_its_database_and_first_question(self):
        first = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        self.asked(self.member, self.shop, 'And last week?', conversation=first)
        second = self.asked(self.member, self.sales, 'Orders in Lahore?')[1]['data']['conversation']
        chats = self.chats(self.member)
        self.assertEqual([c['id'] for c in chats], [second, first])
        self.assertEqual((chats[1]['title'], chats[1]['questions'], chats[1]['source']['name']),
                         ('How many orders?', 2, 'Shop'))
        self.assertEqual(chats[0]['source']['name'], 'Sales')
        self.assertEqual(self.chats(self.admin), [])                      # only one's own chats

    def test_a_chat_stays_on_its_database(self):
        chat = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        code, body = self.asked(self.member, self.sales, 'And in Sales?', conversation=chat)
        self.assertEqual(code, 409, body)
        self.assertIn('This chat is about Shop. Start a new chat to ask about Sales.', body['message'])
        self.assertEqual(DataQuestion.objects.filter(conversation=chat).count(), 1)

    def test_someone_elses_chat_is_not_theirs_to_continue(self):
        chat = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        code, body = self.asked(self.admin, self.shop, 'And more?', conversation=chat)
        self.assertEqual(code, 404, body)
        self.assertEqual(DataQuestion.objects.filter(conversation=chat).count(), 1)

    def test_a_chat_is_read_and_removed_by_its_asker_only(self):
        chat = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        code, body = self.call(views.questions, self.member, {'conversation': chat}, method='get')
        self.assertEqual([q['question'] for q in body['data']], ['How many orders?'])
        self.assertEqual(self.call(views.chat_detail, self.admin, method='delete', conversation=chat)[0], 404)
        code, body = self.call(views.chat_detail, self.member, method='delete', conversation=chat)
        self.assertEqual((code, body['data']['removed']), (200, 1))
        self.assertIn("stays in your company's History", body['message'])
        self.assertEqual(self.chats(self.member), [])
        self.assertEqual(self.call(views.chat_detail, self.member, method='delete', conversation=chat)[0], 404)

    def test_a_deleted_chat_stays_in_the_admins_history_as_a_record(self):
        # Decided 14 Nov 2026: deleting hides a chat from its asker; History stays a full record of what was asked.
        chat = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        question = DataQuestion.objects.get(conversation=chat)
        self.call(views.chat_detail, self.member, method='delete', conversation=chat)
        question.refresh_from_db()
        self.assertIsNotNone(question.hidden_at)

        mine = self.call(views.questions, self.member, method='get')[1]['data']
        self.assertEqual(mine, [])
        everyone = self.call(views.questions, self.admin, {'all': '1'}, method='get')[1]['data']
        self.assertEqual([(q['question'], q['hidden']) for q in everyone], [('How many orders?', True)])
        self.assertEqual(self.call(views.question_detail, self.member, method='get', question_id=question.pk)[0], 404)
        self.assertEqual(self.call(views.question_detail, self.admin, method='get', question_id=question.pk)[0], 200)

    def test_a_deleted_chat_cannot_be_continued(self):
        chat = self.asked(self.member, self.shop, 'How many orders?')[1]['data']['conversation']
        self.call(views.chat_detail, self.member, method='delete', conversation=chat)
        code, body = self.asked(self.member, self.shop, 'And last week?', conversation=chat)
        self.assertEqual(code, 404, body)
        self.assertEqual(DataQuestion.objects.filter(conversation=chat).count(), 1)

    def test_a_chat_id_that_is_not_one_finds_nothing(self):
        self.asked(self.member, self.shop, 'How many orders?')
        code, body = self.call(views.questions, self.member, {'conversation': 'nonsense'}, method='get')
        self.assertEqual((code, body['data']), (200, []))
