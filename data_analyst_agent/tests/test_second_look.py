"""The agent looks at its own result before answering (19 Nov 2026).

On Meridian and Lumora a query that ran could still be wrong in a way its result shows: amounts added up in their own
currencies, a repeat rate of 100% in every row, counts a join had multiplied, a group that came back empty, names empty
in every row. The result is read for these without the AI; when one shows, the query is written once more with what
looks wrong, and the second result is taken only when it no longer shows it. A doubt that remains is said in the answer.
"""
from data_analyst_agent import engine
from data_analyst_agent.models import DataQuestion

from .test_data_analyst import AnalystCase, FakeAI


def result(columns, rows):
    return {'columns': columns, 'rows': rows, 'truncated': False}


class Source:
    kind = 'mongo'                      # no row counts: the doubts read from the result alone


INVOICES = [{'name': 'invoices', 'columns': [{'name': 'amount', 'type': 'REAL'}, {'name': 'currency', 'type': 'TEXT'}]},
            {'name': 'ref_fx_monthly', 'columns': [{'name': 'month', 'type': 'TEXT'}, {'name': 'rate', 'type': 'REAL'}]}]


class WhatLooksWrong(AnalystCase):

    def doubt(self, sql, columns, rows, tables=(), situations=()):
        return engine._doubt(Source(), 'q', sql, result(columns, rows), list(tables), list(situations))

    def test_no_rows_or_a_total_that_came_back_empty(self):
        self.assertIn('no rows', self.doubt('SELECT id FROM t', ['id'], []))
        self.assertIn('empty or zero', self.doubt('SELECT count(*) AS n, sum(x) AS s FROM t', ['n', 's'], [[0, None]]))
        self.assertEqual(self.doubt('SELECT count(*) AS n FROM t', ['n'], [[3]]), '')
        self.assertEqual(self.doubt('SELECT region, 0 AS n FROM t', ['region', 'n'], [['EMEA', 0]]), '')

    def test_a_rate_of_100_in_every_row(self):
        said = self.doubt('...', ['quarter', 'customers', 'repeat_rate_pct'],
                          [['2024-Q1', 207, 100.0], ['2024-Q2', 264, 100]])
        self.assertIn('repeat_rate_pct is 100 in every row', said)
        self.assertIn('its own repeat', said)
        self.assertEqual(self.doubt('...', ['quarter', 'repeat_rate'], [['Q1', 37.2], ['Q2', 100.0]]), '')
        self.assertEqual(self.doubt('...', ['plan', 'paid_share'], [['Pro', 100.0]]), '')   # one row may be so

    def test_names_empty_in_every_row(self):
        self.assertIn('manager is empty in every row', self.doubt('...', ['manager', 'hours'], [[None, 4], ['', 7]]))
        self.assertEqual(self.doubt('...', ['manager', 'hours'], [[None, 4], ['Sana', 7]]), '')

    def test_amounts_added_up_in_their_own_currencies(self):
        sql = 'SELECT sum(amount) AS revenue FROM invoices'
        said = self.doubt(sql, ['revenue'], [[378_000_000]], INVOICES, ['currency'])
        self.assertIn('ref_fx_monthly', said)
        self.assertIn("at its own date's rate", said)
        converted = 'SELECT sum(i.amount * f.rate) AS revenue FROM invoices i JOIN ref_fx_monthly f ON f.month = 1'
        self.assertEqual(self.doubt(converted, ['revenue'], [[1_141_787]], INVOICES, ['currency']), '')
        self.assertEqual(self.doubt('SELECT sum(amount_usd) AS revenue FROM invoices', ['revenue'], [[1]],
                                    INVOICES, ['currency']), '')
        self.assertEqual(self.doubt('SELECT currency, sum(amount) AS revenue FROM invoices GROUP BY currency',
                                    ['currency', 'revenue'], [['EUR', 1], ['USD', 2]], INVOICES, ['currency']), '')
        self.assertEqual(self.doubt('SELECT count(*) AS invoices FROM invoices', ['invoices'], [[9]], INVOICES,
                                    ['currency']), '')


class ASecondLook(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()

    def test_counts_a_join_multiplied_are_written_again(self):
        doubled = ('SELECT c.city, count(*) AS orders FROM orders o JOIN orders o2 ON o2.customer_id = o.customer_id '
                   'JOIN customers c ON c.id = o.customer_id GROUP BY c.city')
        right = ('SELECT c.city, count(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id '
                 'GROUP BY c.city')
        fake = FakeAI({'sql': doubled}, {'sql': right}, 'Karachi has 3 orders, Lahore 1.')
        code, body = self.ask(self.member, self.shop, 'Orders per city?', fake)
        self.assertEqual(code, 200, body)
        self.assertIn('orders adds up to 6 over the rows, more than the 4 rows of the largest table', fake.prompts[1])
        self.assertIn('It ran, but its result looks wrong', fake.prompts[1])
        self.assertEqual(sorted(body['data']['rows']), [['Karachi', 3], ['Lahore', 1]])
        self.assertEqual(DataQuestion.objects.get(pk=body['data']['id']).sql, right)
        self.assertNotIn('A check of this result found', fake.prompts[2])

    def test_a_total_row_is_not_a_multiplied_count(self):
        with_total = ("SELECT c.city, count(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id "
                      "GROUP BY c.city UNION ALL SELECT 'Total', count(*) FROM orders")
        rollup = ('SELECT c.city, count(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id '
                  'GROUP BY c.city UNION ALL SELECT NULL, count(*) FROM orders')
        for sql in (with_total, rollup):
            with self.subTest(sql=sql[-30:]):
                fake = FakeAI({'sql': sql}, 'Karachi has 3 orders, Lahore 1, 4 in all.')
                code, body = self.ask(self.member, self.shop, 'Orders per city, with the total?', fake)
                self.assertEqual((code, len(fake.prompts)), (200, 2), body)

    def test_no_rows_get_a_second_try_with_the_form_of_the_values(self):
        fake = FakeAI({'sql': "SELECT id FROM orders WHERE created_at = '2026-10'"},
                      {'sql': "SELECT id FROM orders WHERE created_at LIKE '2026-10%'"}, 'Four orders in October.')
        code, body = self.ask(self.member, self.shop, 'Orders in October 2026?', fake)
        self.assertIn('a date or month in its full form', fake.prompts[1])
        self.assertEqual(len(body['data']['rows']), 4)

    def test_a_doubt_the_second_try_keeps_is_said_in_the_answer(self):
        same = 'SELECT city, 100.0 AS repeat_rate FROM customers GROUP BY city'
        fake = FakeAI({'sql': same}, {'sql': same}, 'Every city repeats 100%; the figures may be wrong.')
        code, body = self.ask(self.member, self.shop, 'Repeat rate per city?', fake)
        self.assertEqual(code, 200, body)
        self.assertIn('A check of this result found: repeat_rate is 100 in every row', fake.prompts[2])
        self.assertEqual(len(fake.prompts), 3)

    def test_a_second_query_that_fails_leaves_the_first_result(self):
        fake = FakeAI({'sql': "SELECT id FROM orders WHERE created_at = '2026-10'"}, {'sql': 'SELECT nope FROM orders'},
                      'Nothing matched.')
        code, body = self.ask(self.member, self.shop, 'Orders in October 2026?', fake)
        self.assertEqual((code, body['data']['rows']), (200, []))
        self.assertEqual(DataQuestion.objects.get(pk=body['data']['id']).sql,
                         "SELECT id FROM orders WHERE created_at = '2026-10'")

    def test_a_result_that_looks_right_costs_no_more_calls(self):
        fake = FakeAI({'sql': 'SELECT count(*) AS n FROM orders'}, 'There are 4 orders.')
        self.ask(self.member, self.shop, 'How many orders?', fake)
        self.assertEqual(len(fake.prompts), 2)

    def test_no_second_look_when_the_ai_may_not_see_rows(self):
        self.shop.send_rows_to_ai = False
        self.shop.save(update_fields=['send_rows_to_ai'])
        fake = FakeAI({'sql': "SELECT id FROM orders WHERE created_at = '2026-10'"})
        code, body = self.ask(self.member, self.shop, 'Orders in October 2026?', fake)
        self.assertEqual((code, len(fake.prompts)), (200, 1))
