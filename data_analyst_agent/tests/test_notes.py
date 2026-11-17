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
                     'convert each amount at the rate of its own date',
                     'joining on the same date drops the days without a row',
                     'with no period condition in that step',
                     'walk it with a recursive CTE',
                     'Subtracting them again adds them back',
                     'Joining on a column many rows share',
                     'another one on the same day is within 0 days'):
            self.assertIn(rule, prompt)
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
