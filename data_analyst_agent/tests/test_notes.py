"""AI Data Analyst: what a database says about its own tables (17 Nov 2026).

A test database (Meridian, a retailer: 38 tables, ten currencies) got 3 of 9 questions right on the live site. Its own
data dictionary said that order totals are in the order's currency and are converted at the latest rate on or before
the order date, that a NULL customer is a guest checkout, and that negative payments are refunds. The AI never saw it:
it added up ten currencies, joined rates on the exact date (no rates on weekends), and left out a loyalty tier's last
day. Now the database's column comments and its dictionary table are notes beside the columns, how its periods end is
read from the data, and a UNION sorted by an expression is sorted outside it. The notes are read when a question is
asked and never kept.
"""
import json
import os
import sqlite3
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import force_authenticate

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, engine
from data_analyst_agent.models import DataQuestion, DataSource
from data_analyst_agent.tests.test_data_analyst import AnalystCase, FakeAI


def _make_retail(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT, country_code TEXT);
        CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(customer_id),
                             order_ts TEXT, currency_code TEXT, total_amount REAL);
        CREATE TABLE exchange_rates (rate_date TEXT, currency_code TEXT, rate_to_usd REAL,
                                     PRIMARY KEY (rate_date, currency_code));
        CREATE TABLE tiers (tier_id INTEGER PRIMARY KEY, tier_name TEXT);
        CREATE TABLE tier_history (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(customer_id),
                                   tier_id INTEGER REFERENCES tiers(tier_id), valid_from TEXT, valid_to TEXT);
        CREATE TABLE prices (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(customer_id),
                             price REAL, effective_from TEXT, effective_to TEXT);
        CREATE TABLE data_dictionary (table_name TEXT, column_name TEXT, description TEXT);
        INSERT INTO data_dictionary VALUES
            ('orders', 'total_amount', 'In the order''s currency. Convert with exchange_rates (latest rate_date <= order date).'),
            ('orders', 'customer_id', 'NULL for guest checkouts.'),
            ('orders', '', 'One row per order, cancelled ones too.');
        INSERT INTO customers VALUES (1, 'Ayesha', 'PK'), (2, 'Bilal', 'GB'), (3, 'Hira', 'PK'), (4, 'Omar', 'AE'),
                                     (5, 'Sana', 'PK'), (6, 'Zain', 'GB');
        INSERT INTO tiers VALUES (1, 'Bronze'), (2, 'Gold');
        INSERT INTO orders VALUES (1, 1, '2025-07-05 10:00:00', 'GBP', 100), (2, NULL, '2025-07-06 09:00:00', 'USD', 50);
        INSERT INTO exchange_rates VALUES ('2025-07-04', 'GBP', 1.25), ('2025-07-04', 'USD', 1.0);
    """)
    # Tier periods end on their last day: the next starts the day after. Price periods end on the day the next starts.
    for customer in range(1, 7):
        conn.execute('INSERT INTO tier_history (customer_id, tier_id, valid_from, valid_to) VALUES (?, 1, ?, ?)',
                     (customer, '2024-01-01', '2024-06-30'))
        conn.execute('INSERT INTO tier_history (customer_id, tier_id, valid_from, valid_to) VALUES (?, 2, ?, NULL)',
                     (customer, '2024-07-01'))
        conn.execute('INSERT INTO prices (customer_id, price, effective_from, effective_to) VALUES (?, 10, ?, ?)',
                     (customer, '2024-01-01', '2024-03-01'))
        conn.execute('INSERT INTO prices (customer_id, price, effective_from, effective_to) VALUES (?, 12, ?, NULL)',
                     (customer, '2024-03-01'))
    conn.commit()
    conn.close()


class NotesCase(AnalystCase):

    def retail(self, name='Meridian'):
        path = os.path.join(self.storage, 'retail.sqlite')
        _make_retail(path)
        with open(path, 'rb') as fh:
            content = fh.read()
        os.remove(path)
        request = self.factory.post('/', {'name': name, 'file': SimpleUploadedFile('retail.db', content)},
                                    format='multipart')
        force_authenticate(request, user=self.admin)
        response = views.sources(request)
        response.render()
        body = json.loads(response.content)
        self.assertEqual(response.status_code, 201, body)
        return DataSource.objects.get(pk=body['data']['id'])


class ReadingTheNotes(NotesCase):

    def test_the_dictionary_and_how_periods_end_become_notes(self):
        source = self.retail()
        notes = connectors.notes(source, source.tables)
        self.assertIn('Convert with exchange_rates', notes['orders']['total_amount'])
        self.assertEqual(notes['orders']['customer_id'], 'NULL for guest checkouts.')
        self.assertEqual(notes['orders'][''], 'One row per order, cancelled ones too.')
        self.assertIn("valid_to is the period's last day", notes['tier_history']['valid_to'])
        self.assertIn('valid_from <= d <= valid_to', notes['tier_history']['valid_to'])
        self.assertIn('effective_to is the day the next period starts', notes['prices']['effective_to'])

    def test_a_database_comment_is_a_note(self):
        source = DataSource(kind='postgres', host='db.example.com', database='shop', username='r')
        tables = [{'name': 'orders', 'schema': '', 'kind': 'table', 'fks': [],
                   'columns': [{'name': 'total', 'type': 'numeric'}]}]

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execution_options(self, **kwargs):
                return self

            def exec_driver_sql(self, sql):
                rows = [('orders', '', 'Every sale'), ('orders', 'total', 'In euros, tax included')]
                return mock.Mock(fetchall=mock.Mock(return_value=rows if 'pg_description' in sql else []))

            def rollback(self):
                pass

        with mock.patch.object(connectors, '_engine', return_value=mock.Mock(connect=Conn)):
            notes = connectors.notes(source, tables)
        self.assertEqual(notes, {'orders': {'': 'Every sale', 'total': 'In euros, tax included'}})

    def test_a_database_that_cannot_be_reached_has_no_notes(self):
        source = DataSource(kind='postgres', host='db.example.com', database='shop', username='r')
        with mock.patch.object(connectors, '_engine', side_effect=OSError('unreachable')):
            self.assertEqual(connectors.notes(source, []), {})


class TheNotesInTheQuestion(NotesCase):

    def test_the_writer_sees_the_notes_and_the_rules_and_nothing_is_kept(self):
        source = self.retail()
        sql = ("SELECT SUM(o.total_amount * (SELECT r.rate_to_usd FROM exchange_rates r WHERE r.currency_code = "
               "o.currency_code AND r.rate_date <= date(o.order_ts) ORDER BY r.rate_date DESC LIMIT 1)) AS revenue_usd "
               "FROM orders o")
        fake = FakeAI({'sql': sql}, 'Revenue was 175.0 USD.')
        code, body = self.ask(self.admin, source, "What was Meridian's revenue in USD?", fake)
        self.assertEqual((code, body['data']['status'], body['data']['rows']), (200, 'answered', [[175.0]]), body)
        prompt = ' '.join(fake.prompts[0].split())
        self.assertIn('The database: "Meridian"', prompt)
        self.assertIn("total_amount REAL (note: In the order's currency. Convert with exchange_rates", prompt)
        self.assertIn('Note on the table: One row per order, cancelled ones too.', prompt)
        self.assertIn("valid_to TEXT (note: valid_to is the period's last day", prompt)
        for rule in ('not a filter on a store, brand or customer with that name',
                     'Follow the notes on what a column means',
                     'convert each amount at the rate of its own date',          # orders has a currency column
                     'joining on the same date drops the days without a row',
                     'the one whose period covers it',                           # tier_history, prices
                     'not from an address',
                     'Joining on a column many rows share'):
            self.assertIn(rule, prompt)
        # Rules for situations this question and these tables don't have are left out.
        for rule in ('with no period condition in that step', 'walk it with a recursive CTE',
                     'Subtracting them again adds them back', 'UNION ALL inside a subquery', 'within 0 days'):
            self.assertNotIn(rule, prompt)
        source.refresh_from_db()
        kept = json.dumps(source.tables) + json.dumps(list(DataQuestion.objects.values()), default=str)
        self.assertNotIn('Convert with exchange_rates', kept)
        self.assertNotIn("period's last day", kept)

    def test_the_table_choice_sees_the_notes(self):
        source = self.retail()
        fake = FakeAI({'tables': ['orders', 'exchange_rates']}, {'sql': 'SELECT COUNT(*) AS n FROM orders'}, '2 orders.')
        with mock.patch.object(engine, 'TABLES_WITHOUT_CHOOSING', 2):
            code, body = self.ask(self.admin, source, 'How many orders?', fake)
        self.assertEqual(body['data']['status'], 'answered', body)
        self.assertIn("The database's own notes on its tables and columns:", fake.prompts[0])
        self.assertIn('- orders.customer_id: NULL for guest checkouts.', fake.prompts[0])
        self.assertIn('include the table of exchange rates', ' '.join(fake.prompts[0].split()))


class RulesOnlyWhenTheyApply(NotesCase):

    def test_a_plain_question_on_a_plain_database_gets_the_short_list(self):
        source = self.source()                      # customers and orders, one currency, no notes
        fake = FakeAI({'sql': 'SELECT COUNT(id) AS customers FROM customers'}, 'There are 3 customers.')
        self.ask(self.admin, source, 'How many customers are there?', fake)
        prompt = ' '.join(fake.prompts[0].split())
        for rule in ('Follow the notes', 'convert each amount at the rate', 'joining on the same date',
                     'whose period covers it', 'Subtracting them again', 'UNION ALL inside a subquery',
                     'with no period condition', 'recursive CTE', 'Some rows no longer count'):
            self.assertNotIn(rule, prompt)
        self.assertIn('Joining on a column many rows share', prompt)       # the general rules stay

    def test_each_situation_brings_its_rule(self):
        tree = {'name': 'categories', 'columns': [{'name': 'id'}, {'name': 'parent_id'}],
                'fks': [{'columns': ['parent_id'], 'references': 'categories(id)'}]}
        payments = {'name': 'payments', 'columns': [{'name': 'amount'}, {'name': 'currency_code'}], 'fks': []}
        self.assertEqual(engine._situations([tree], 'Units per top-level category', {}), ['tree'])
        self.assertEqual(engine._situations([payments], 'Net cash per region, and the grand total', {}),
                         ['currency', 'rates', 'signed', 'total_row'])
        self.assertEqual(engine._situations([payments], "Customers' first ever payment, by quarter", {}),
                         ['currency', 'rates', 'signed', 'first_ever'])
        self.assertEqual(engine._situations([payments], 'Payments last month', {'payments': {'amount': 'In cents'}}),
                         ['notes', 'currency', 'rates', 'signed'])
        # "Within 90 days" counts the same day: shown only for a question with a time window (18 Nov 2026).
        self.assertIn('window', engine._situations([tree], 'How many ordered again within 90 days of the first?', {}))
        self.assertNotIn('window', engine._situations([tree], 'Orders in the last 90 days', {}))


class ModelSeeingAI(FakeAI):
    """Records the model each call asked for (None: the agent's usual one)."""

    def __init__(self, *replies):
        super().__init__(*replies)
        self.models = []

    def _call_llm(self, prompt, system_prompt=None, **kwargs):
        self.models.append(getattr(self, 'openai_model', None))
        return super()._call_llm(prompt, system_prompt, **kwargs)


class TheStrongerModelForHarderQuestions(NotesCase):
    """18 Nov 2026: a harder question's query is written by DATA_ANALYST_COMPLEX_MODEL (gpt-4.1); every other call,
    and every simple question, keeps the usual model."""
    SQL = {'sql': 'SELECT COUNT(order_id) AS orders FROM orders'}

    def test_a_first_ever_or_time_window_question_gets_it_for_the_query_only(self):
        source = self.retail()
        for question in ("How many customers' first ever order was in 2025?",
                         'How many customers ordered again within 90 days?'):
            fake = ModelSeeingAI(self.SQL, '2 orders.')
            self.ask(self.admin, source, question, fake)
            self.assertEqual(fake.models, ['gpt-4.1', None])              # the query, then the answer
            self.assertIsNone(getattr(fake, 'openai_model', None))

    def test_a_simple_or_money_question_keeps_the_usual_model(self):
        source = self.retail()
        for question in ('How many customers are there?', 'What was our revenue in USD last quarter?'):
            fake = ModelSeeingAI(self.SQL, '6 customers.')
            self.ask(self.admin, source, question, fake)
            self.assertEqual(fake.models, [None, None])

    def test_a_second_try_gets_it_and_the_setting_can_turn_it_off(self):
        source = self.retail()
        fake = ModelSeeingAI({'sql': 'SELECT nothing FROM orders'}, self.SQL, '2 orders.')
        self.ask(self.admin, source, 'How many customers are there?', fake)
        self.assertEqual(fake.models, [None, 'gpt-4.1', None])            # the failed query was tried again
        with self.settings(DATA_ANALYST_COMPLEX_MODEL=''):
            fake = ModelSeeingAI(self.SQL, '2 orders.')
            self.ask(self.admin, source, 'How many customers ordered again within 90 days?', fake)
        self.assertEqual(fake.models, [None, None])

    def test_the_rules_on_leaving_rows_out(self):
        source = self.retail()
        fake = ModelSeeingAI(self.SQL, '2 orders.')
        self.ask(self.admin, source, 'How many orders did customers place?', fake)
        query, answer = (' '.join(p.split()) for p in fake.prompts)
        self.assertIn('a note that rows of some kind are usually left out of a figure (a segment, a channel, internal '
                      'accounts) applies only when the question says so', query)
        self.assertIn("When the query leaves out rows the question doesn't mention", answer)

    def test_the_shared_call_uses_the_asked_model_only_on_an_openai_key(self):
        from project_manager_agent.ai_agents.base_agent import BaseAgent
        agent = BaseAgent()
        agent.company_id, agent.agent_key_name = self.company.pk, 'data_analyst_agent'
        for provider, asked, used in (('openai', 'gpt-4.1', 'gpt-4.1'), ('openai', None, 'gpt-4.1-mini'),
                                      ('groq', 'gpt-4.1', agent.model)):
            client = mock.Mock()
            client.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content='ok'))], usage=None)
            agent.openai_model = asked
            with self.subTest(provider=provider, asked=asked), \
                 mock.patch.object(agent, '_resolve_company_client', return_value=(client, mock.Mock(provider=provider))), \
                 self.settings(OPENAI_MODEL='gpt-4.1-mini'):
                agent._call_llm('Hello?')
                self.assertEqual(client.chat.completions.create.call_args.kwargs['model'], used)


class SortingAUnion(NotesCase):

    def test_a_union_sorted_by_an_expression_is_sorted_outside_it(self):
        sql = ("WITH t AS (SELECT country_code AS region, COUNT(*) AS n FROM customers GROUP BY country_code) "
               "SELECT region, n FROM t UNION ALL SELECT 'Grand total', SUM(n) FROM t "
               "ORDER BY CASE WHEN region = 'Grand total' THEN 1 ELSE 0 END, n DESC")
        self.assertEqual(engine._sorted_outside(sql),
                         "SELECT * FROM (WITH t AS (SELECT country_code AS region, COUNT(*) AS n FROM customers GROUP BY "
                         "country_code) SELECT region, n FROM t UNION ALL SELECT 'Grand total', SUM(n) FROM t) AS "
                         "sorted_rows ORDER BY CASE WHEN region = 'Grand total' THEN 1 ELSE 0 END, n DESC")
        # Not a union, or the ORDER BY inside a window or a subquery: left alone.
        self.assertEqual(engine._sorted_outside('SELECT a FROM t ORDER BY a'), '')
        self.assertEqual(engine._sorted_outside('SELECT a, rank() OVER (ORDER BY b) FROM t UNION ALL SELECT 1, 2'), '')
        self.assertEqual(engine._sorted_outside("SELECT 'x UNION y' AS a FROM t ORDER BY a"), '')

        source = self.retail()
        fake = FakeAI({'sql': sql}, 'Pakistan has the most customers.')
        code, body = self.ask(self.admin, source, 'Customers per country, with the grand total', fake)
        self.assertEqual(body['data']['status'], 'answered', body)
        self.assertEqual(body['data']['rows'], [['PK', 3], ['GB', 2], ['AE', 1], ['Grand total', 6]])
        self.assertEqual(len(fake.prompts), 2)           # turned around without asking the AI again
        self.assertTrue(DataQuestion.objects.get().sql.startswith('SELECT * FROM (WITH t AS'))


class RowsThatNoLongerCount(NotesCase):
    """18 Nov 2026: cancelled orders, deleted records and disabled accounts are left out unless the question asks for
    them. The rule is shown only for tables that have such rows; closed, completed or discontinued ones still count."""

    def shop(self, script):
        path = os.path.join(self.storage, 'shop.sqlite')
        conn = sqlite3.connect(path)
        conn.executescript(script)
        conn.commit()
        conn.close()
        with open(path, 'rb') as fh:
            content = fh.read()
        os.remove(path)
        request = self.factory.post('/', {'name': 'Shop', 'file': SimpleUploadedFile('shop.db', content)},
                                    format='multipart')
        force_authenticate(request, user=self.admin)
        response = views.sources(request)
        response.render()
        self.assertEqual(response.status_code, 201, response.content)
        return DataSource.objects.get(pk=json.loads(response.content)['data']['id'])

    def test_the_marks_are_read_from_the_columns_and_the_values(self):
        def marks(table, *names, seen=None):
            t = {'name': table, 'columns': [{'name': n} for n in names]}
            return engine._dead_marks([t], {('', table): seen} if seen else None)
        # Deleted or cancelled, on any table. A deleted or disabled thing is left out only where it is counted or
        # listed itself; a cancelled one goes with its lines; a status is kept when the question asks by it.
        joined = ('; left out only when counting or listing {}: joined from another table to reach a name, city or '
                  'region, keep them')
        self.assertEqual(marks('customers', 'id', 'deleted_at'),
                         ['  - customers: deleted_at set' + joined.format('customers')])
        self.assertEqual(marks('customers', 'id', 'is_deleted'),
                         ['  - customers: is_deleted true' + joined.format('customers')])
        self.assertEqual(marks('notes', 'id', 'isDeleted'), ['  - notes: isDeleted true' + joined.format('notes')])
        self.assertEqual(marks('orders', 'id', 'cancelled_at'), ['  - orders: cancelled_at set'])
        self.assertEqual(marks('orders', 'id', 'status', seen={'status': ['delivered', 'Cancelled']}),
                         ["  - orders: status 'Cancelled' (unless the question asks by status)"])
        self.assertEqual(marks('payments', 'id', 'status', seen={'status': ['captured', 'failed']}),
                         ["  - payments: status 'failed' (unless the question asks by status)"])
        # Disabled, inactive or left: only for people and their logins, and by the values that say so.
        self.assertEqual(marks('auth_user', 'id', 'is_active'),
                         ['  - auth_user: is_active false' + joined.format('auth_user')])
        self.assertEqual(marks('employees', 'id', 'employment_status',
                               seen={'employment_status': ['active', 'probation', 'offboarded']}),
                         ["  - employees: employment_status 'offboarded' (unless the question asks by employment_status)"
                          + joined.format('employees')])
        for table, names, seen in (('products', ('id', 'is_active'), None), ('companies', ('id', 'is_active'), None),
                                   ('schools', ('id', 'status'), {'status': ['Active', 'Closed', 'Merged']}),
                                   ('tickets', ('id', 'status'), {'status': ['open', 'closed', 'resolved']}),
                                   ('products', ('id', 'status'), {'status': ['inactive']}),
                                   ('t', ('id', 'closed_at', 'discontinued_date', 'active_users', 'deleted_by_note'),
                                    None)):
            self.assertEqual(marks(table, *names, seen=seen), [], (table, names))

    def test_a_question_on_such_a_table_gets_the_rule(self):
        source = self.shop("""
            CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT, total REAL);
            INSERT INTO orders VALUES (1, 'delivered', 100), (2, 'cancelled', 40), (3, 'delivered', 60);""")
        fake = FakeAI({'sql': "SELECT SUM(total) AS total FROM orders WHERE status != 'cancelled'"},
                      'The orders come to 160, leaving out cancelled orders.')
        code, body = self.ask(self.admin, source, 'What do our orders come to?', fake)
        self.assertEqual(body['data']['status'], 'answered', body)
        self.assertEqual(body['data']['rows'], [[160.0]])
        query = ' '.join(fake.prompts[0].split())
        self.assertIn("Some rows no longer count, and are left out even when the question doesn't say so", query)
        self.assertIn("Here they are marked by: - orders: status 'cancelled' (unless the question asks by status)", query)
        self.assertIn('What they did (their orders, payments, meetings, tasks) still counts: never filter a table that '
                      'is joined only to reach their name, region or segment', query)
        self.assertIn('every other value counts (closed, completed, on probation, discontinued). Asked by the column '
                      'that marks them ("orders in each status", "employees by employment status")', query)

        # Closed tickets are finished, not gone: no rule.
        source = self.shop("""
            CREATE TABLE tickets (id INTEGER PRIMARY KEY, status TEXT);
            INSERT INTO tickets VALUES (1, 'open'), (2, 'closed');""")
        fake = FakeAI({'sql': 'SELECT COUNT(id) AS tickets FROM tickets'}, '2 tickets.')
        self.ask(self.admin, source, 'How many tickets are there?', fake)
        self.assertNotIn('Some rows no longer count', fake.prompts[0])

    def test_a_mongodb_collection_gets_it_too(self):
        users = {'name': 'users', 'columns': [{'name': '_id', 'type': 'objectId'}, {'name': 'isDeleted', 'type': 'bool'}]}
        plain = {'name': 'users', 'columns': [{'name': '_id', 'type': 'objectId'}, {'name': 'name', 'type': 'string'}]}
        for collection, shown in ((users, True), (plain, False)):
            fake = FakeAI({'collection': 'users', 'pipeline': [{'$count': 'users'}]})
            engine._write_aggregation(fake, None, 'How many users are there?', '', [collection])
            self.assertEqual('Some rows no longer count' in fake.prompts[0], shown)
            self.assertEqual('- users: isDeleted true' in fake.prompts[0], shown)
