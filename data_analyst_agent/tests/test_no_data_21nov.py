"""A question the database can't answer (21 Nov 2026, Mahnoor's all-agents test).

- Data Analyst 1: "What is our employee headcount?" of a shop's database was answered with `SELECT 0 AS
  employee_headcount` and "The employee headcount is 0.", a figure made up and shown as data. A query that reads no
  table is now refused; the next try is told to say what is missing.
- Data Analyst 2: MongoDB's prompt answered the same question with the reply meant for a request to change data,
  "I only read your database, so I can't change it."
"""
from data_analyst_agent import engine
from data_analyst_agent.guards import NO_TABLE, Refused, check_sql
from data_analyst_agent.models import DataQuestion

from .test_data_analyst import AnalystCase, FakeAI


class AQueryThatReadsNoTable(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()

    def test_it_is_refused_and_one_that_reads_a_table_is_not(self):
        with self.assertRaisesMessage(Refused, 'reads no table'):
            check_sql('SELECT 0 AS employee_headcount', 'sqlite')
        self.assertTrue(check_sql('WITH o AS (SELECT * FROM orders) SELECT count(*) FROM o', 'sqlite'))

    def test_the_next_try_says_what_is_missing(self):
        fake = FakeAI({'sql': 'SELECT 0 AS employee_headcount'},
                      {'sql': '', 'ask_back': 'This database has no employee data: only customers and orders.'})
        code, body = self.ask(self.member, self.shop, 'What is our employee headcount?', fake)
        self.assertEqual(code, 200, body)
        self.assertIn(NO_TABLE, fake.prompts[1])
        question = DataQuestion.objects.get(pk=body['data']['id'])
        self.assertEqual((question.status, question.answer),
                         (DataQuestion.STATUS_ASKED_BACK, 'This database has no employee data: only customers and orders.'))

    def test_when_every_try_makes_a_figure_up_the_answer_is_that_the_data_isnt_there(self):
        fake = FakeAI(*[{'sql': 'SELECT 0 AS employee_headcount'}] * engine.QUERY_TRIES)
        code, body = self.ask(self.member, self.shop, 'What is our employee headcount?', fake)
        self.assertEqual(code, 200, body)
        question = DataQuestion.objects.get(pk=body['data']['id'])
        self.assertEqual((question.status, question.answer), (DataQuestion.STATUS_ASKED_BACK, engine.NO_DATA))
        self.assertNotIn('headcount is 0', body['data'].get('answer') or '')


class TheReadOnlyReply(AnalystCase):

    def test_it_is_kept_for_a_request_to_change_data(self):
        reply = "I only read your database, so I can't change it."
        self.assertEqual(engine._plain_ask_back('Delete all cancelled orders', reply), reply)
        self.assertEqual(engine._plain_ask_back('What is our employee headcount?', reply), engine.NO_DATA)
        self.assertEqual(engine._plain_ask_back('What is our employee headcount?', 'Which year?'), 'Which year?')
