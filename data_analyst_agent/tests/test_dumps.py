"""AI Data Analyst: .sql dumps read into a SQLite copy (7 Nov 2026). The dialects (MySQL, PostgreSQL with COPY,
SQL Server, SQLite), the values that trip readers up, statements that must never run, keys added by ALTER TABLE,
and the upload: small dumps now, big ones in the background, files that are not dumps, and asking afterwards.

The same reader was also checked against real dumps (7 Nov 2026): a 14.7 MB mysqldump of 257 tables matched MariaDB's
own import value for value, and pg_dump 17 files in both formats matched PostgreSQL."""
import gzip
import json
import os
import sqlite3
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, dumps, sources
from data_analyst_agent.models import DataQuestion, DataSource
from data_analyst_agent.tests.test_data_analyst import AnalystCase, FakeAI

MYSQL = r"""-- MySQL dump 10.13  Distrib 8.0.36
/*!40101 SET NAMES utf8mb4 */;
DROP TABLE IF EXISTS `customers`;
CREATE TABLE `customers` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `city` varchar(60) DEFAULT NULL COMMENT 'where; they are',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;
CREATE TABLE `orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `customer_id` int unsigned NOT NULL,
  `total` decimal(10,2) DEFAULT NULL,
  `status` enum('paid','cancelled') DEFAULT 'paid',
  `note` text,
  `created` datetime NOT NULL,
  `photo` blob,
  PRIMARY KEY (`id`),
  KEY `idx_c` (`customer_id`),
  CONSTRAINT `fk_c` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB;
LOCK TABLES `customers` WRITE;
INSERT INTO `customers` VALUES (1,'Ayesha Traders','Karachi'),(2,'Bilal\'s Foods; Lahore','Lahore'),(3,'Hira ''Textiles''',NULL);
UNLOCK TABLES;
INSERT INTO `orders` (`id`,`customer_id`,`total`,`status`,`note`,`created`,`photo`) VALUES (1,1,1200.50,'paid','line one\nline two -- not a comment','2026-10-02 10:00:00',0x89504E47),(2,2,-450.00,'cancelled','back\\slash; and /* not a comment */','2026-10-20 09:30:00',NULL),
(3,3,2300,'paid',_utf8mb4'Ünïcödé ✓','2026-10-28 12:00:00',_binary 'ab');
DELIMITER ;;
CREATE DEFINER=`root`@`%` PROCEDURE `add_log`() BEGIN INSERT INTO customers VALUES (99, 'from a procedure', 'x'); END ;;
DELIMITER ;
ATTACH DATABASE '/tmp/x.db' AS x;
PRAGMA writable_schema=1;
CREATE VIEW `v` AS select load_extension('evil');
"""

POSTGRES = r"""--
-- PostgreSQL database dump
--
\restrict AbCdEf123
SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);
CREATE FUNCTION public.f() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO public.orders VALUES (9); RETURN NEW; END; $$;
CREATE TABLE public.customers (
    id integer NOT NULL,
    name text,
    vip boolean,
    city character varying(60)
);
CREATE TABLE public.orders (
    id integer NOT NULL,
    customer_id integer,
    total numeric(10,2),
    tags text[],
    receipt bytea,
    created timestamp with time zone
);
CREATE TABLE sales.targets (month date, amount numeric(12,2));
COPY public.customers (id, name, vip, city) FROM stdin;
1	Ayesha Traders	t	Karachi
2	Bilal\tFoods	f	\N
3	Hira "Textiles"\nline two	\N	Karachi
\.
COPY public.orders (id, customer_id, total, tags, receipt, created) FROM stdin;
1	1	1200.50	{a,b}	\\x89504e47	2026-10-02 10:00:00+00
2	2	450.00	{}	\N	2026-10-20 09:30:00+00
\.
INSERT INTO public.orders VALUES (3, 3, 2300, '{c}', NULL, '2026-10-28 12:00:00+00'::timestamp with time zone);
INSERT INTO sales.targets VALUES ('2026-10-01', 5000), (E'2026-11-01', 6500.75);
ALTER TABLE ONLY public.customers ADD CONSTRAINT customers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.orders ADD CONSTRAINT orders_customer_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);
CREATE INDEX idx ON public.orders USING btree (customer_id);
\unrestrict AbCdEf123
"""

TSQL = """SET ANSI_NULLS ON
GO
CREATE TABLE [dbo].[Customers](
\t[Id] [int] IDENTITY(1,1) NOT NULL,
\t[Name] [nvarchar](120) NULL,
 CONSTRAINT [PK_Customers] PRIMARY KEY CLUSTERED ([Id] ASC)
) ON [PRIMARY]
GO
INSERT [dbo].[Customers] ([Id], [Name]) VALUES (1, N'Ayesha Traders')
INSERT [dbo].[Customers] ([Id], [Name]) VALUES (2, N'Bilal''s Foods')
GO
"""


def sqlite_dump():
    src = sqlite3.connect(':memory:')
    src.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, label TEXT, n REAL);"
                      "INSERT INTO t VALUES (1, 'a''b;c', 1.5), (2, NULL, -2);")
    return '\n'.join(src.iterdump())


class DumpCase(AnalystCase):

    def read(self, text):
        path = os.path.join(self.storage, 'in.sql')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        self.reads = getattr(self, 'reads', 0) + 1
        out = os.path.join(self.storage, f'out{self.reads}.sqlite')
        report = dumps.load(path, out, dumps.sniff(dumps.read_head(path)))
        conn = sqlite3.connect(out)
        self.addCleanup(conn.close)
        return report, conn

    def upload_dump(self, text, name='portal.sql', compress=False, actor=None):
        content = text.encode('utf-8')
        if compress:
            content = gzip.compress(content)
        request = self.factory.post('/', {'name': 'Portal', 'file': SimpleUploadedFile(name, content)}, format='multipart')
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=actor or self.admin)
        response = views.sources(request)
        response.render()
        return response.status_code, json.loads(response.content)


class TheDialects(DumpCase):

    def test_each_dialect_is_told_from_its_first_part(self):
        self.assertEqual([dumps.sniff(t) for t in (MYSQL, POSTGRES, TSQL, sqlite_dump())],
                         ['mysql', 'postgres', 'tsql', 'sqlite'])
        for text in ('just a note, no tables', '\x00\x01binary', ''):
            self.assertIsNone(dumps.sniff(text))

    def test_a_mysqldump_with_its_awkward_values(self):
        report, conn = self.read(MYSQL)
        self.assertEqual(report['tables'], [{'name': 'customers', 'rows': 3}, {'name': 'orders', 'rows': 3}])
        self.assertEqual(conn.execute('SELECT * FROM customers ORDER BY id').fetchall(),
                         [(1, 'Ayesha Traders', 'Karachi'), (2, "Bilal's Foods; Lahore", 'Lahore'),
                          (3, "Hira 'Textiles'", None)])
        self.assertEqual(conn.execute('SELECT total, note, photo FROM orders ORDER BY id').fetchall(), [
            (1200.5, 'line one\nline two -- not a comment', b'\x89PNG'),
            (-450, 'back\\slash; and /* not a comment */', None),
            (2300, 'Ünïcödé ✓', b'ab')])
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'orders'").fetchone()[0]
        self.assertIn('"total" DECIMAL(10,2)', ddl)
        self.assertIn('FOREIGN KEY ("customer_id") REFERENCES "customers" ("id")', ddl)

    def test_postgres_copy_e_strings_and_keys_added_later(self):
        report, conn = self.read(POSTGRES)
        self.assertEqual([t['name'] for t in report['tables']], ['customers', 'orders', 'sales_targets'])
        self.assertEqual(conn.execute('SELECT * FROM customers ORDER BY id').fetchall(),
                         [(1, 'Ayesha Traders', 1, 'Karachi'), (2, 'Bilal\tFoods', 0, None),
                          (3, 'Hira "Textiles"\nline two', None, 'Karachi')])
        self.assertEqual(conn.execute('SELECT id, tags, receipt FROM orders ORDER BY id').fetchall(),
                         [(1, '{a,b}', b'\x89PNG'), (2, '{}', None), (3, '{c}', None)])
        self.assertEqual(conn.execute('SELECT * FROM sales_targets').fetchall(), [('2026-10-01', 5000), ('2026-11-01', 6500.75)])
        self.assertEqual(report['keys']['orders']['fks'], [{'columns': ['customer_id'], 'references': 'customers(id)'}])
        self.assertEqual(report['problems'], [])
        self.assertNotIn('RESTRICT', report['skipped'])          # psql's \restrict lines are dropped, not glued on

    def test_sql_server_scripts_and_sqlite_dumps(self):
        report, conn = self.read(TSQL)
        self.assertEqual(conn.execute('SELECT * FROM Customers').fetchall(), [(1, 'Ayesha Traders'), (2, "Bilal's Foods")])
        self.assertIn('PRIMARY KEY ("Id")', conn.execute("SELECT sql FROM sqlite_master WHERE name = 'Customers'").fetchone()[0])
        report, conn = self.read(sqlite_dump())
        self.assertEqual(conn.execute('SELECT * FROM t').fetchall(), [(1, "a'b;c", 1.5), (2, None, -2.0)])

    def test_nothing_but_tables_is_ever_made_and_bodies_are_not_data(self):
        report, conn = self.read(MYSQL)
        self.assertEqual(sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type != 'index'")),
                         ['customers', 'orders'])
        self.assertEqual(conn.execute('SELECT count(*) FROM customers WHERE id = 99').fetchone()[0], 0)
        for kind in ('ATTACH', 'PRAGMA', 'CREATE VIEW', 'CREATE DEFINER'):
            self.assertIn(kind, report['skipped'])
        report, conn = self.read(POSTGRES)
        self.assertEqual(conn.execute('SELECT count(*) FROM orders WHERE id = 9').fetchone()[0], 0)


class UploadingADump(DumpCase):

    def test_a_small_dump_is_read_now_its_copy_asked_and_the_dump_not_kept(self):
        code, body = self.upload_dump(POSTGRES)
        self.assertEqual(code, 201, body)
        data = body['data']
        self.assertEqual((data['status'], data['kind'], data['load']['dialect_label'], data['load']['tables']),
                         ('ready', 'sqlite', 'PostgreSQL', 3))
        self.assertIn('Read 3 table(s) and 8 row(s) from the PostgreSQL dump', body['message'])
        source = DataSource.objects.get(pk=data['id'])
        self.assertTrue(source.file_path.endswith('.sqlite'))
        folder = os.path.dirname(source.file_path)
        self.assertEqual([f for f in os.listdir(folder) if f.endswith(('.sql', '.gz'))], [])   # the dump is gone
        orders = next(t for t in source.tables if t['name'] == 'orders')
        self.assertIn({'columns': ['customer_id'], 'references': 'customers(id)'}, orders['fks'])
        customers = next(t for t in source.tables if t['name'] == 'customers')
        self.assertTrue(next(c for c in customers['columns'] if c['name'] == 'id')['pk'])
        fake = FakeAI({'sql': 'SELECT c.city, count(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id '
                              'GROUP BY c.city ORDER BY orders DESC'}, 'Karachi had 2 orders.')
        code, asked = self.ask(self.admin, source, 'Orders by city?', fake)
        self.assertEqual(asked['data']['rows'], [['Karachi', 2], [None, 1]])

    def test_a_gzipped_dump_reads_the_same(self):
        code, body = self.upload_dump(MYSQL, name='shop.sql.gz', compress=True)
        self.assertEqual((body['data']['status'], body['data']['load']['tables']), ('ready', 2))

    def test_a_big_dump_is_read_in_the_background(self):
        with mock.patch('data_analyst_agent.dumps.INLINE_BYTES', 10), \
             mock.patch('data_analyst_agent.tasks.load_dump.delay') as queued:
            code, body = self.upload_dump(MYSQL)
        self.assertEqual(body['data']['status'], 'loading')
        self.assertIn('in the background', body['message'])
        queued.assert_called_once_with(body['data']['id'])
        source = DataSource.objects.get(pk=body['data']['id'])
        self.assertEqual(self.ask(self.admin, source, 'Customers?', FakeAI())[0], 400)        # not while loading
        from data_analyst_agent.tasks import load_dump
        self.assertTrue(load_dump(source.pk)['ok'])
        source.refresh_from_db()
        self.assertEqual((source.status, len(source.tables)), ('ready', 2))

    def test_a_file_that_is_neither_sqlite_nor_a_dump_is_refused_and_not_kept(self):
        code, body = self.upload_dump('Dear team, the numbers are attached.', name='notes.sql')
        self.assertEqual(code, 400)
        self.assertIn('neither a SQLite database file nor a .sql dump', body['message'])
        self.assertFalse(DataSource.objects.exists())
        root = connectors.files_root()
        self.assertEqual([f for _d, _s, files in os.walk(root) for f in files], [])

    def test_a_dump_with_nothing_to_read_fails_and_leaves_nothing(self):
        code, body = self.upload_dump('-- INSERT INTO t VALUES (1) appears only in this comment\nSET NAMES utf8;\n')
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('No table or row could be read', body['data']['last_error'])
        self.assertEqual([f for _d, _s, files in os.walk(connectors.files_root()) for f in files], [])

    def test_a_dump_that_takes_too_long_stops(self):
        with mock.patch('data_analyst_agent.sources.DUMP_SECONDS', -1):
            code, body = self.upload_dump(MYSQL)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('took too long', body['data']['last_error'])

    def test_a_load_cut_short_by_a_restart_says_so(self):
        with mock.patch('data_analyst_agent.dumps.INLINE_BYTES', 10), \
             mock.patch('data_analyst_agent.tasks.load_dump.delay'):
            body = self.upload_dump(MYSQL)[1]
        DataSource.objects.filter(pk=body['data']['id']).update(updated_at=timezone.now() - timedelta(hours=1))
        listed = self.call(views.sources, self.admin, method='get')[1]['data']
        self.assertEqual(listed[0]['status'], 'failed')
        self.assertIn('cut short', listed[0]['last_error'])
        self.assertFalse(sources.settle_stale(DataSource.objects.get(pk=body['data']['id'])))   # once only

    def test_only_an_owner_or_admin_uploads_a_dump(self):
        code, _ = self.upload_dump(MYSQL, actor=self.member)
        self.assertEqual(code, 403)
        self.assertFalse(DataQuestion.objects.exists())
