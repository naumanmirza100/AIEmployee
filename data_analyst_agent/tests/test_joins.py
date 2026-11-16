"""Questions that join several tables (16 Nov 2026).

Tested on the PayPerProject database itself (263 tables, a phpMyAdmin dump) with gpt-4.1-mini: 3 of 10 questions
needing 3 to 5 tables came back right at first. What went wrong, and what these tests hold:
- a filter spelled as the AI guessed ('in progress' for 'in_progress'): the values of short status-like columns are
  now named to it, when the source lets the AI see rows;
- a join through the wrong table, because the choice of tables left out the one both point at (auth_user): the
  tables a chosen table points at come with it;
- the leave balances chosen for "approved leave days": the list for choosing shows each table's telling columns
  first, and the rows of each event are preferred over running totals;
- ids instead of names, COUNT(contact_id) leaving out tickets without a contact, and conditions nobody asked for:
  rules in the prompt.
Afterwards 16 of 16 (10 questions plus 6 new ones) twice.
"""
import json
import os
import sqlite3

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import force_authenticate

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, engine
from data_analyst_agent.models import DataSource

from .test_data_analyst import AnalystCase, FakeAI

SUPPORT = """
    CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE tickets (id INTEGER PRIMARY KEY, company_id INTEGER REFERENCES companies(id), status TEXT,
                          ticket_type TEXT, category TEXT, note TEXT);
    INSERT INTO companies VALUES (1, 'Margalla Software'), (2, 'Crestline Technologies');
"""


class JoinHelpTests(AnalystCase):

    def make(self, script, extra_tables=0):
        path = os.path.join(self.storage, 'support.db')
        conn = sqlite3.connect(path)
        conn.executescript(script)
        rows = [(i, 1 + i % 2, ['in_progress', 'open', 'closed'][i % 3], f'type {i}',
                 'x' * 50 if i == 1 else 'billing', f'note {i}') for i in range(1, 31)]
        conn.executemany('INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)', rows)
        for n in range(extra_tables):
            conn.execute(f'CREATE TABLE other_{n} (id INTEGER PRIMARY KEY, label TEXT)')
        conn.commit()
        conn.close()
        with open(path, 'rb') as fh:
            content = fh.read()
        os.remove(path)
        request = self.factory.post('/', {'name': 'Support', 'file': SimpleUploadedFile('support.db', content)},
                                    format='multipart')
        force_authenticate(request, user=self.admin)
        response = views.sources(request)
        response.render()
        return DataSource.objects.get(pk=json.loads(response.content)['data']['id'])

    def test_a_status_column_comes_with_its_values(self):
        source = self.make(SUPPORT)
        fake = FakeAI({'sql': "SELECT COUNT(*) AS n FROM tickets WHERE status = 'in_progress'"}, '10 tickets.')
        self.ask(self.admin, source, 'How many tickets are in progress?', fake)
        prompt = fake.prompts[0]
        self.assertIn("status TEXT (values: 'closed', 'in_progress', 'open')", prompt)
        self.assertIn('filter with them exactly as spelled there', prompt)

    def test_only_short_lists_of_choices_are_named(self):
        source = self.make(SUPPORT)
        fake = FakeAI({'sql': 'SELECT COUNT(*) AS n FROM tickets'}, '30 tickets.')
        self.ask(self.admin, source, 'How many tickets?', fake)
        prompt = fake.prompts[0]
        self.assertNotIn("'type 1'", prompt)              # 30 different ticket types: not a list of choices
        self.assertNotIn("'billing'", prompt)             # one value longer than the limit: left out
        self.assertNotIn("'note 1'", prompt)              # "note" is not a choice column

    def test_no_values_when_the_ai_may_not_see_rows(self):
        source = self.make(SUPPORT)
        DataSource.objects.filter(pk=source.pk).update(send_rows_to_ai=False)
        source.refresh_from_db()
        fake = FakeAI({'sql': 'SELECT COUNT(*) AS n FROM tickets'})
        self.ask(self.admin, source, 'How many tickets?', fake)
        self.assertNotIn('(values:', fake.prompts[0])

    def test_a_chosen_table_brings_the_tables_it_points_at(self):
        source = self.make(SUPPORT, extra_tables=35)       # over 30 tables: they are chosen first
        fake = FakeAI({'tables': ['tickets']}, {'sql': 'SELECT COUNT(*) AS n FROM tickets'}, '30 tickets.')
        self.ask(self.admin, source, 'Tickets per company, with the company name?', fake)
        self.assertIn('- tickets:', fake.prompts[1])
        self.assertIn('- companies:', fake.prompts[1])     # not chosen, but tickets point at it
        self.assertNotIn('- other_3:', fake.prompts[1])
        self.assertIn('a running total', fake.prompts[0])
        self.assertIn('hold the names of what the answer lists', fake.prompts[0])

    def test_the_rules_ask_for_names_whole_counts_and_no_extra_conditions(self):
        source = self.make(SUPPORT)
        fake = FakeAI({'sql': 'SELECT COUNT(*) AS n FROM tickets'}, '30 tickets.')
        self.ask(self.admin, source, 'How many tickets?', fake)
        prompt = fake.prompts[0]
        self.assertIn('Show what things are called, not only their ids', prompt)
        self.assertIn("Count rows by the counted table's own id", prompt)
        self.assertIn("Add no condition the question doesn't ask for", prompt)


class TableListTests(AnalystCase):

    def test_the_list_for_choosing_shows_telling_columns_first(self):
        table = {'name': 'leave_requests', 'schema': '', 'kind': 'table', 'fks': [],
                 'columns': [{'name': n, 'type': 'TEXT'} for n in
                             ('id', 'employee_id', 'created_at', 'start_date', 'status', 'leave_type', 'days')]}
        self.assertEqual(engine._table_text(table, full=False, columns=4),
                         '- leave_requests (status, leave_type, start_date, days)')

    def test_the_tables_pointed_at_are_added_up_to_a_ceiling(self):
        tables = [{'name': f't{i}', 'schema': '', 'columns': [], 'fks': []} for i in range(30)]
        tables[0]['fks'] = [{'columns': [f'r{i}'], 'references': f't{i}(id)'} for i in range(1, 30)]
        out = engine._with_references(tables, [tables[0]])
        self.assertEqual(len(out), engine.TABLES_WITH_LINKS)
        self.assertEqual([t['name'] for t in out[:3]], ['t0', 't1', 't2'])

    def test_choice_columns_are_short_text_columns_named_like_choices(self):
        table = {'columns': [{'name': 'status', 'type': 'VARCHAR(20)'}, {'name': 'ticket_type', 'type': 'TEXT'},
                             {'name': 'priority', 'type': 'INTEGER'}, {'name': 'description', 'type': 'TEXT'},
                             {'name': 'statusbar', 'type': 'TEXT'}]}
        self.assertEqual(connectors.choice_columns(table), ['status', 'ticket_type'])
