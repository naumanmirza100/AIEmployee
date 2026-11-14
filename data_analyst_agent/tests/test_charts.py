"""The Data Analyst draws a chart when one is asked for (14 Nov 2026).

"Can you make a graph of users in each company?" got a table and an answer that it couldn't draw one. The AI that
writes the query now also says, when the question asks for a picture of the data, which chart (bar, line or pie) and
which two result columns it is drawn from; the server checks that against the result and keeps the description (never
the rows), and the screen draws it.
"""
from data_analyst_agent import engine
from data_analyst_agent.models import DataQuestion, DataSource

from api.views import data_analyst_agent as views

from .test_data_analyst import AnalystCase, FakeAI

BY_CITY = ('SELECT c.city AS city, SUM(o.total) AS total FROM orders o JOIN customers c ON c.id = o.customer_id '
           'GROUP BY c.city ORDER BY total DESC')
BAR = {'type': 'bar', 'x': 'city', 'y': 'total', 'title': 'Spending by city'}


class ChartTests(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()

    def ask_for(self, question, written, answer='Karachi spent the most: 3,500.50.', actor=None):
        fake = FakeAI(written, answer)
        code, body = self.ask(actor or self.member, self.shop, question, fake)
        self.assertEqual(code, 200, body)
        return body['data'], fake

    def test_a_chart_asked_for_is_described_kept_and_mentioned_in_the_answer(self):
        data, fake = self.ask_for('Make a graph of spending by city', {'sql': BY_CITY, 'chart': BAR})
        self.assertEqual(data['chart'], BAR)
        self.assertEqual(data['columns'], ['city', 'total'])
        self.assertEqual(DataQuestion.objects.get(pk=data['id']).chart, BAR)
        self.assertIn('"chart"', fake.prompts[0])                     # the query writer is told how to describe one
        self.assertIn('A bar chart of total by city is drawn from these rows', fake.prompts[1])
        self.assertIn("never say you can't draw one", fake.prompts[1])

    def test_no_chart_unless_one_is_asked_for(self):
        data, fake = self.ask_for('Spending by city?', {'sql': BY_CITY, 'chart': None})
        self.assertIsNone(data['chart'])
        self.assertNotIn('is drawn from these rows', fake.prompts[1])

    def test_a_chart_that_does_not_fit_the_result_is_left_out(self):
        for chart in ({'type': 'bar', 'x': 'town', 'y': 'total'},          # no such column
                      {'type': 'bar', 'x': 'city', 'y': 'city'},           # the same column twice
                      {'type': 'bar', 'x': 'total', 'y': 'city'},          # words where the figures should be
                      {'type': 'radar', 'x': 'city', 'y': 'total'},        # a kind it can't draw
                      'a bar chart'):
            with self.subTest(chart=chart):
                data, _ = self.ask_for('Make a graph of spending by city', {'sql': BY_CITY, 'chart': chart})
                self.assertIsNone(data['chart'])
                self.assertEqual(len(data['rows']), 2)                    # the answer and the table still show

    def test_names_match_whatever_their_case_and_a_list_of_figures_gives_its_first(self):
        data, _ = self.ask_for('Pie of spending by city', {'sql': BY_CITY, 'chart': {
            'type': 'Pie', 'x': 'CITY', 'y': ['Total', 'other'], 'title': ''}})
        self.assertEqual(data['chart'], {'type': 'pie', 'x': 'city', 'y': 'total', 'title': 'total by city'})

    def test_with_rows_kept_from_the_ai_the_answer_points_at_the_chart(self):
        DataSource.objects.filter(pk=self.shop.pk).update(send_rows_to_ai=False)
        fake = FakeAI({'sql': BY_CITY, 'chart': BAR})
        code, body = self.ask(self.member, self.shop, 'Graph of spending by city', fake)
        self.assertEqual(body['data']['answer'], '2 row(s): see the chart and the table.')
        self.assertEqual(len(fake.prompts), 1)

    def test_a_reopened_question_keeps_its_chart_for_drawing_again(self):
        data, _ = self.ask_for('Make a graph of spending by city', {'sql': BY_CITY, 'chart': BAR})
        code, body = self.call(views.questions, self.member, {'conversation': data['conversation']}, method='get')
        self.assertEqual(body['data'][0]['chart'], BAR)
        code, body = self.call(views.question_run, self.member, question_id=data['id'])
        self.assertEqual((code, body['data']['columns']), (200, ['city', 'total']))

    def test_a_mongodb_aggregation_can_describe_one_too(self):
        source = DataSource(kind=DataSource.KIND_MONGO, name='Shop')
        tables = [{'name': 'orders', 'columns': [{'name': 'city', 'type': 'string'}, {'name': 'total', 'type': 'double'}]}]
        fake = FakeAI({'collection': 'orders', 'pipeline': [{'$group': {'_id': '$city', 'total': {'$sum': '$total'}}}],
                       'chart': BAR})
        written = engine._write_sql(fake, source, 'Graph of spending by city', '', tables)
        self.assertEqual(written['chart'], BAR)
        self.assertIn('"chart"', fake.prompts[0])


class SameFigureTests(AnalystCase):
    """An amount written with its zeros ("4,300.50") was flagged as a figure the rows didn't have (4300.5)."""

    def test_trailing_zeros_are_the_same_figure(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT 4300.5 AS total, 1200 AS other'}, 'The total was 4,300.50 PKR, and 1,200.00 more.')
        body = self.ask(self.admin, source, 'Total?', fake)[1]
        self.assertEqual(body['data']['flagged'], [])

    def test_a_figure_not_in_the_rows_is_still_flagged(self):
        from core.assistant.engine import unchecked_numbers
        from data_analyst_agent.engine import _Fact
        self.assertEqual(unchecked_numbers('It was 4300.50, or 4301.', [_Fact('4300.5')]), ['4301'])
        self.assertEqual(unchecked_numbers('About 4300.55.', [_Fact('4300.5')]), ['4300.55'])
