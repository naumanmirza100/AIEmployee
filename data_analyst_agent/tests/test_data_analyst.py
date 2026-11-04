"""AI Data Analyst, phase 1 (3 Nov 2026): the guards, a SQLite file asked end to end, what is and isn't kept, and who
may do what. The AI is a fake that returns what each test needs; the database is a real SQLite file."""
import json
import os
import shutil
import sqlite3
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import data_analyst_agent as views
from core.models import Agent
from data_analyst_agent.guards import Refused, check_sql, resolve_public
from data_analyst_agent.models import DataQuestion, DataSource
from hr_agent.tests.base import HRTestCase


class FakeAI:
    """Answers each AI call from a queue: dicts become JSON (the table choice, the SQL), strings are the answer."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def _call_llm(self, prompt, system_prompt=None, **kwargs):
        self.prompts.append(prompt)
        reply = self.replies.pop(0) if self.replies else ''
        return json.dumps(reply) if isinstance(reply, dict) else reply


def _make_shop(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total REAL,
                             created_at TEXT);
        INSERT INTO customers VALUES (1, 'Ayesha Traders', 'Karachi'), (2, 'Bilal Foods', 'Lahore'),
                                     (3, 'Hira Textiles', 'Karachi');
        INSERT INTO orders VALUES (1, 1, 1200.5, '2026-10-02'), (2, 1, 800, '2026-10-15'), (3, 2, 450, '2026-10-20'),
                                  (4, 3, 2300, '2026-10-28');
    """)
    conn.commit()
    conn.close()


class AnalystCase(HRTestCase):

    def setUp(self):
        super().setUp()
        Agent.objects.get_or_create(slug='data_analyst_agent', defaults={'name': 'AI Data Analyst'})
        self.buy_module(self.company, 'data_analyst_agent')
        self.storage = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.storage, ignore_errors=True)
        override = override_settings(LOCAL_STORAGE_ROOT=self.storage)
        override.enable()
        self.addCleanup(override.disable)
        self.factory = APIRequestFactory()

    def upload(self, actor, name='Shop'):
        path = os.path.join(self.storage, 'upload.sqlite')
        _make_shop(path)
        with open(path, 'rb') as fh:
            content = fh.read()
        os.remove(path)
        request = self.factory.post('/', {'name': name, 'file': SimpleUploadedFile('shop.db', content)},
                                    format='multipart')
        force_authenticate(request, user=actor)
        response = views.sources(request)
        response.render()
        return response.status_code, json.loads(response.content)

    def source(self):
        code, body = self.upload(self.admin)
        self.assertEqual(code, 201, body)
        return DataSource.objects.get(pk=body['data']['id'])

    def ask(self, actor, source, question, fake, **extra):
        with mock.patch('data_analyst_agent.engine.AnalystAI', return_value=fake):
            return self.call(views.ask, actor, {'source': source.pk, 'question': question, **extra})


class TheChecks(AnalystCase):

    def test_only_one_read_only_select_passes(self):
        self.assertEqual(check_sql('SELECT city, count(*) FROM customers GROUP BY city;', 'sqlite'),
                         'SELECT city, count(*) FROM customers GROUP BY city')
        for sql in ('DELETE FROM orders', 'SELECT 1; DROP TABLE orders', 'WITH d AS (DELETE FROM t RETURNING *) SELECT 1',
                    'SELECT pg_sleep(5)', 'SELECT * FROM t FOR UPDATE', 'SELECT * INTO x FROM t', "SELECT nextval('s')",
                    "SELECT load_extension('x')", 'PRAGMA table_info(t)', 'SET statement_timeout = 0'):
            with self.subTest(sql=sql), self.assertRaises(Refused):
                check_sql(sql, 'postgres' if 'pg_' in sql or 'RETURNING' in sql else 'sqlite')

    def test_a_host_that_is_not_public_is_refused(self):
        for address in ('127.0.0.1', '10.0.0.5', '172.18.0.3', '192.168.1.9', '169.254.169.254', '::1', '0.0.0.0'):
            with self.subTest(address=address), \
                 mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', (address, 5432))]), \
                 self.assertRaises(Refused):
                resolve_public('db', 5432)

    @override_settings(DATA_ANALYST_SERVER_IP='203.0.113.10')
    def test_our_own_server_is_refused_and_a_public_host_is_its_checked_address(self):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('203.0.113.10', 3306))]), \
             self.assertRaises(Refused):
            resolve_public('api.example.com', 3306)
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.4.4', 5432))]):
            self.assertEqual(resolve_public('db.example.com', 5432), '8.8.4.4')

    def test_a_connection_to_our_own_database_is_never_made(self):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('172.18.0.2', 3306))]), \
             mock.patch('data_analyst_agent.connectors.create_engine') as made:
            code, body = self.call(views.sources, self.admin, {'name': 'Ours', 'kind': 'mysql', 'host': 'db',
                                                               'database': 'app', 'username': 'root', 'password': 'x'})
        self.assertEqual(code, 201)
        made.assert_not_called()
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('not a public address', body['data']['last_error'])


class AFileAskedEndToEnd(AnalystCase):

    def test_an_upload_is_read_kept_privately_and_its_tables_known(self):
        code, body = self.upload(self.admin)
        self.assertEqual(code, 201, body)
        self.assertEqual(body['data']['status'], 'ready')
        self.assertEqual(sorted(t['name'] for t in body['data']['tables']), ['customers', 'orders'])
        source = DataSource.objects.get(pk=body['data']['id'])
        self.assertTrue(source.file_path.startswith(os.path.realpath(self.storage)) or self.storage in source.file_path)
        self.assertFalse(source.user_can_write)

    def test_a_file_that_is_not_sqlite_is_refused(self):
        request = self.factory.post('/', {'file': SimpleUploadedFile('x.db', b'not a database at all')},
                                    format='multipart')
        force_authenticate(request, user=self.admin)
        response = views.sources(request)
        response.render()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DataSource.objects.exists())

    def test_only_an_owner_or_admin_adds_a_database(self):
        code, _ = self.upload(self.member)
        self.assertEqual(code, 403)

    def test_a_question_is_answered_and_only_the_answer_and_sql_are_kept(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT c.city, round(sum(o.total), 1) AS total FROM orders o JOIN customers c ON '
                              'c.id = o.customer_id GROUP BY c.city ORDER BY total DESC', 'ask_back': ''},
                      'Karachi sold the most: 4300.5, then Lahore with 450.')
        code, body = self.ask(self.member, source, 'Which city sold the most?', fake)
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual(data['columns'], ['city', 'total'])
        self.assertEqual(data['rows'], [['Karachi', 4300.5], ['Lahore', 450.0]])
        self.assertEqual(data['flagged'], [])
        record = DataQuestion.objects.get(pk=data['id'])
        self.assertEqual((record.row_count, record.columns, record.status), (2, ['city', 'total'], 'answered'))
        self.assertNotIn('rows', [f.name for f in DataQuestion._meta.get_fields()])
        self.assertIn('Rows:', fake.prompts[1])                     # the AI saw the rows it answered from

    def test_a_query_that_writes_goes_back_to_the_ai_once_with_the_reason(self):
        source = self.source()
        fake = FakeAI({'sql': 'DELETE FROM orders'}, {'sql': 'SELECT count(*) AS n FROM orders'}, 'There are 4 orders.')
        code, body = self.ask(self.admin, source, 'How many orders?', fake)
        self.assertEqual(body['data']['rows'], [[4]])
        self.assertIn('It failed: Only queries that read', fake.prompts[1])
        with sqlite3.connect(source.file_path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM orders').fetchone()[0], 4)

    def test_a_database_error_goes_back_to_the_ai_with_the_databases_words(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT amount FROM orders'}, {'sql': 'SELECT sum(total) AS total FROM orders'},
                      'Orders total 4750.5.')
        code, body = self.ask(self.admin, source, 'Total of all orders?', fake)
        self.assertEqual(body['data']['status'], 'answered')
        self.assertIn('no such column: amount', fake.prompts[1])

    def test_two_failures_are_said_plainly_and_nothing_runs(self):
        source = self.source()
        fake = FakeAI({'sql': 'DROP TABLE orders'}, {'sql': 'UPDATE orders SET total = 0'})
        code, body = self.ask(self.admin, source, 'Clear the orders', fake)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('could not be run', body['data']['answer'])
        with sqlite3.connect(source.file_path) as conn:
            self.assertEqual(conn.execute('SELECT sum(total) FROM orders').fetchone()[0], 4750.5)

    def test_a_query_stopped_at_the_time_limit_is_said_plainly_and_not_tried_again(self):
        # Live, 3 Nov 2026: a count over RNAcentral's rna table ran 30 s twice, and the site cut the request at 60 s.
        source = self.source()
        heavy = 'WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 5000000) SELECT count(*) AS c FROM n'
        fake = FakeAI({'sql': heavy}, {'sql': heavy})
        with mock.patch('data_analyst_agent.connectors.QUERY_TIMEOUT', 0):
            code, body = self.ask(self.admin, source, 'Count to five million', fake)
        self.assertEqual(code, 200, body)
        self.assertEqual(len(fake.prompts), 1)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('the database stopped it. Ask about a smaller part', body['data']['answer'])

    def test_a_slow_failure_leaves_no_time_for_another_try(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT amount FROM orders'}, {'sql': 'SELECT sum(total) AS total FROM orders'})
        calls = []

        def clock():
            calls.append(1)
            return 0.0 if len(calls) == 1 else 25.0      # the first query took 25 s before it failed

        with mock.patch('data_analyst_agent.connectors.run', side_effect=Exception('no such column: amount')), \
             mock.patch('data_analyst_agent.engine.time.monotonic', side_effect=clock):
            code, body = self.ask(self.admin, source, 'Total of all orders?', fake)
        self.assertEqual(len(fake.prompts), 1)
        self.assertEqual(body['data']['answer'], 'The query could not be run: no such column: amount')

    def test_a_question_the_tables_cant_answer_is_asked_back(self):
        source = self.source()
        fake = FakeAI({'sql': '', 'ask_back': 'There is no table of refunds.'})
        code, body = self.ask(self.admin, source, 'How many refunds?', fake)
        self.assertEqual((body['data']['status'], body['data']['answer']), ('asked_back', 'There is no table of refunds.'))

    def test_a_number_not_in_the_rows_is_flagged(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT count(*) AS n FROM customers'}, 'There are 7 customers.')
        code, body = self.ask(self.admin, source, 'How many customers?', fake)
        self.assertEqual(body['data']['flagged'], ['7'])

    def test_thousands_separators_are_not_new_figures(self):
        source = self.source()
        fake = FakeAI({'sql': 'SELECT 314950 AS revenue, 1200 AS orders'}, 'Revenue was 314,950 PKR from 1,200 orders.')
        code, body = self.ask(self.admin, source, 'Revenue?', fake)
        self.assertEqual(body['data']['flagged'], [])

    def test_with_rows_kept_from_the_ai_it_writes_only_the_sql(self):
        source = self.source()
        source.send_rows_to_ai = False
        source.save()
        fake = FakeAI({'sql': 'SELECT name FROM customers'})
        code, body = self.ask(self.admin, source, 'List the customers', fake)
        self.assertEqual(len(fake.prompts), 1)
        self.assertEqual(body['data']['answer'], '3 row(s): see the table.')

    def test_a_follow_up_sees_the_last_question_and_its_sql(self):
        source = self.source()
        first = self.ask(self.admin, source, 'Orders in Karachi?',
                         FakeAI({'sql': "SELECT count(*) AS n FROM orders o JOIN customers c ON c.id = o.customer_id "
                                        "WHERE c.city = 'Karachi'"}, '3 orders.'))[1]['data']
        fake = FakeAI({'sql': "SELECT count(*) AS n FROM orders o JOIN customers c ON c.id = o.customer_id "
                              "WHERE c.city = 'Lahore'"}, '1 order.')
        self.ask(self.admin, source, 'And Lahore?', fake, conversation=first['conversation'])
        self.assertIn("WHERE c.city = 'Karachi'", fake.prompts[0])

    def test_a_big_database_has_its_tables_chosen_first(self):
        source = self.source()
        source.tables = source.tables + [{'name': f'extra_{i}', 'schema': '', 'kind': 'table',
                                          'columns': [{'name': 'id', 'type': 'INTEGER', 'pk': True}], 'fks': []}
                                         for i in range(40)]
        source.save()
        fake = FakeAI({'tables': ['orders']}, {'sql': 'SELECT count(*) AS n FROM orders'}, '4 orders.')
        self.ask(self.admin, source, 'How many orders?', fake)
        self.assertIn('extra_39', fake.prompts[0])
        self.assertNotIn('extra_39', fake.prompts[1])

    def test_a_very_big_database_is_listed_within_the_budget_with_every_table(self):
        # Like RNAcentral on the live site: 294 tables with 25 columns each asked Groq for 11,536 tokens (3 Nov 2026).
        source = self.source()
        source.tables = source.tables + [{'name': f'rnc_table_{i}', 'schema': 'rnacen', 'kind': 'table',
                                          'columns': [{'name': f'some_long_column_{c}', 'type': 'TEXT'} for c in range(25)],
                                          'fks': []} for i in range(294)]
        source.save()
        fake = FakeAI({'tables': ['orders']}, {'sql': 'SELECT count(*) AS n FROM orders'}, '4 orders.')
        code, body = self.ask(self.admin, source, 'How many orders?', fake)
        self.assertEqual(body['data']['status'], 'answered')
        self.assertLess(len(fake.prompts[0]), 21000)
        self.assertIn('rnacen.rnc_table_293', fake.prompts[0])        # fewer columns, never fewer tables
        self.assertIn('some_long_column_0', fake.prompts[0])


class AfterwardsAndWhoSeesWhat(AnalystCase):

    def _asked(self, actor):
        source = self.source()
        body = self.ask(actor, source, 'Customers?', FakeAI({'sql': 'SELECT name FROM customers ORDER BY id'},
                                                            'Three customers.'))[1]
        return source, DataQuestion.objects.get(pk=body['data']['id'])

    def test_opening_it_again_runs_the_query_now(self):
        source, record = self._asked(self.member)
        code, body = self.call(views.question_run, self.member, question_id=record.pk)
        self.assertEqual(body['data']['rows'], [['Ayesha Traders'], ['Bilal Foods'], ['Hira Textiles']])

    def test_a_csv_is_streamed_not_kept(self):
        source, record = self._asked(self.member)
        request = self.factory.get('/')
        force_authenticate(request, user=self.member)
        response = views.question_csv(request, question_id=record.pk)
        text = b''.join(response.streaming_content).decode()
        self.assertEqual(text.splitlines(), ['name', 'Ayesha Traders', 'Bilal Foods', 'Hira Textiles'])

    def test_someone_elses_question_is_not_theirs_to_open_but_an_admin_sees_all(self):
        source, record = self._asked(self.admin)
        self.assertEqual(self.call(views.question_detail, self.member, method='get', question_id=record.pk)[0], 404)
        mine = self.call(views.questions, self.member, method='get')[1]['data']
        self.assertEqual(mine, [])
        request = self.factory.get('/', {'all': '1'})
        force_authenticate(request, user=self.admin)
        response = views.questions(request)
        response.render()
        self.assertEqual(len(json.loads(response.content)['data']), 1)

    def test_a_database_kept_to_some_people_refuses_the_others(self):
        source = self.source()
        source.everyone_may_ask = False
        source.save()
        code, _ = self.ask(self.member, source, 'Customers?', FakeAI({'sql': 'SELECT 1'}))
        self.assertEqual(code, 404)
        source.allowed_users.add(self.member)
        code, _ = self.ask(self.member, source, 'Customers?', FakeAI({'sql': 'SELECT 1 AS one'}, 'One.'))
        self.assertEqual(code, 200)

    def test_removing_a_database_removes_its_file_and_its_questions(self):
        source, record = self._asked(self.admin)
        path = source.file_path
        code, body = self.call(views.source_detail, self.admin, method='delete', source_id=source.pk)
        self.assertEqual(code, 200)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(DataQuestion.objects.exists())

    def test_a_connection_string_requires_ssl_only_when_it_says_so(self):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.1.1.1', 5432))]):
            body = self.call(views.sources, self.admin, {'connection_string': 'postgresql://r:p@db.example.com/shop'})[1]
        self.assertFalse(DataSource.objects.get(pk=body['data']['id']).use_ssl)

    def test_the_ai_is_told_it_only_reads_and_to_give_figures(self):
        source = self.source()
        fake = FakeAI({'sql': '', 'ask_back': "I only read your database, so I can't change it."})
        code, body = self.ask(self.admin, source, 'Delete the cancelled orders.', fake)
        self.assertIn('Asked to change data', fake.prompts[0])
        self.assertIn('Return the figures the question is about', fake.prompts[0])
        self.assertEqual(body['data']['status'], 'asked_back')

    def test_a_password_is_kept_encrypted_and_never_shown(self):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.1.1.1', 5432))]):
            code, body = self.call(views.sources, self.admin, {
                'name': 'Shop', 'connection_string': 'postgresql://reader:S3cret-pass@db.example.com:5433/shop?sslmode=require'})
        source = DataSource.objects.get(pk=body['data']['id'])
        self.assertEqual((source.kind, source.host, source.port, source.database, source.username, source.use_ssl),
                         ('postgres', 'db.example.com', 5433, 'shop', 'reader', True))
        self.assertNotIn('S3cret-pass', source.password_encrypted)
        self.assertEqual(source.get_password(), 'S3cret-pass')
        self.assertNotIn('S3cret-pass', json.dumps(body))
        self.assertTrue(body['data']['has_password'])

    def test_a_company_without_the_agent_is_kept_out(self):
        from core.models import Company
        other = Company.objects.create(name='Other', email='other@test.local')
        stranger = self.login(other, 'zara@test.local', 'Zara Owner', 'owner')
        code, _ = self.send(self.http(stranger), 'get', '/api/data-analyst/sources')
        self.assertIn(code, (402, 403))
        code, _ = self.send(self.http(self.admin), 'get', '/api/data-analyst/sources')
        self.assertEqual(code, 200)
