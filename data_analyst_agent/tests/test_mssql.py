"""AI Data Analyst with Microsoft SQL Server (12 Nov 2026): the connection strings people paste, the ODBC string our
server opens, the address and host checks, reading the tables, the guard's T-SQL refusals, and a question asked. SQL
Server itself is not needed: the engine and its rows are fakes; the real ODBC Driver 18 was tried by hand."""
import json
from unittest import mock

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, mssql
from data_analyst_agent.guards import Refused, check_sql
from data_analyst_agent.models import DataSource
from data_analyst_agent.tests.test_data_analyst import AnalystCase, FakeAI

AZURE = ('Server=tcp:shop-sql.database.windows.net,1433;Initial Catalog=shop;Persist Security Info=False;'
         'User ID=pp_reader;Password={p;a}}ss};MultipleActiveResultSets=False;Encrypt=True;'
         'TrustServerCertificate=False;Connection Timeout=30;')


def public(host, port, *args, **kwargs):
    return [(2, 1, 6, '', ('20.1.2.3', port))]


class FakeConnection:
    """What mssql.read_tables asks, answered from rows keyed by the query they belong to."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def execution_options(self, **kwargs):
        return self

    def exec_driver_sql(self, sql):
        self.asked.append(sql)
        for key, rows in self.answers.items():
            if key in sql:
                return rows
        return []


class TheConnectionStrings(AnalystCase):

    def test_azure_odbc_jdbc_and_url_strings_are_read(self):
        self.assertEqual(mssql.parse_connection_string(AZURE), {
            'host': 'shop-sql.database.windows.net', 'port': 1433, 'database': 'shop', 'username': 'pp_reader',
            'password': 'p;a}ss', 'use_ssl': True, 'options': {}})
        odbc = mssql.parse_connection_string('Driver={ODBC Driver 18 for SQL Server};Server=db.example.com,14330;'
                                             'Database=erp;Uid=reader;Pwd=secret;Encrypt=no;TrustServerCertificate=yes;')
        self.assertEqual((odbc['port'], odbc['use_ssl'], odbc['options']), (14330, False, {'trust_server_certificate': True}))
        jdbc = mssql.parse_connection_string('jdbc:sqlserver://db.example.com:1433;databaseName=erp;user=reader;password=s;')
        self.assertEqual((jdbc['host'], jdbc['port'], jdbc['database'], jdbc['username']), ('db.example.com', 1433, 'erp', 'reader'))
        url = mssql.parse_connection_string('mssql+pyodbc://reader:s%40cret@db.example.com:1433/erp?TrustServerCertificate=yes')
        self.assertEqual((url['password'], url['options']), ('s@cret', {'trust_server_certificate': True}))
        named = mssql.parse_connection_string('Data Source=SQLPROD01\\INVENTORY,51433;Initial Catalog=stock;User Id=r;Password=x;')
        self.assertEqual((named['host'], named['port']), ('SQLPROD01', 51433))

    def test_a_named_instance_without_its_port_and_a_string_without_a_server_are_refused(self):
        for text in ('Data Source=SQLPROD01\\INVENTORY;Initial Catalog=stock;User Id=r;Password=x;', 'Database=x;User ID=y;'):
            with self.subTest(text=text), self.assertRaises(Refused):
                mssql.parse_connection_string(text)

    def test_the_odbc_string_braces_every_value_and_refuses_a_host_that_adds_keywords(self):
        source = DataSource(kind='mssql', host='db.example.com', port=1433, database='erp;x', username='reader',
                            use_ssl=True, options={'trust_server_certificate': True})
        source.set_password('p;a}ss=1')
        self.assertEqual(mssql.odbc_connection_string(source),
                         'DRIVER={ODBC Driver 18 for SQL Server};SERVER=tcp:db.example.com,1433;DATABASE={erp;x};'
                         'UID={reader};PWD={p;a}}ss=1};Encrypt=yes;TrustServerCertificate=yes;ApplicationIntent=ReadOnly;')
        for host in ('db.example.com;Database=master', 'db{x}', 'db example.com'):
            with self.subTest(host=host), self.assertRaises(Refused):
                mssql.check_host(host)


class AddingASqlServer(AnalystCase):

    def add(self, payload):
        with mock.patch('socket.getaddrinfo', side_effect=public), \
             mock.patch('data_analyst_agent.connectors.read_tables', return_value=[
                 {'name': 'Orders', 'schema': '', 'kind': 'table', 'columns': [{'name': 'Id', 'type': 'int', 'pk': True}],
                  'fks': []}]), \
             mock.patch('data_analyst_agent.connectors.can_write', return_value=False):
            return self.call(views.sources, self.admin, payload)

    def test_an_azure_string_is_saved_its_password_encrypted_and_never_shown(self):
        code, body = self.add({'name': 'Shop', 'connection_string': AZURE})
        self.assertEqual(code, 201, body)
        data = body['data']
        self.assertEqual((data['kind'], data['kind_label'], data['status'], data['host'], data['port'], data['database']),
                         ('mssql', 'Microsoft SQL Server', 'ready', 'shop-sql.database.windows.net', 1433, 'shop'))
        self.assertNotIn('p;a}ss', json.dumps(body))
        source = DataSource.objects.get(pk=data['id'])
        self.assertEqual(source.get_password(), 'p;a}ss')
        self.assertNotIn('p;a}ss', source.password_encrypted)

    def test_the_fields_form_works_with_port_1433_by_default(self):
        code, body = self.add({'kind': 'mssql', 'host': 'db.example.com', 'database': 'erp', 'username': 'reader',
                               'password': 'x', 'use_ssl': True})
        self.assertEqual((body['data']['kind'], body['data']['status']), ('mssql', 'ready'))
        self.assertEqual(connectors._default_port('mssql'), 1433)

    def test_a_host_that_adds_keywords_is_refused_before_saving(self):
        code, body = self.add({'kind': 'mssql', 'host': 'db.example.com;Database=master', 'database': 'erp',
                               'username': 'reader', 'password': 'x'})
        self.assertEqual(code, 400)
        self.assertFalse(DataSource.objects.exists())

    def test_a_server_inside_our_network_is_never_connected_to(self):
        source = DataSource(kind='mssql', host='db', port=3306, database='app', username='root')
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('172.18.0.2', 3306))]), \
             mock.patch('data_analyst_agent.connectors.create_engine') as made, self.assertRaises(Refused):
            connectors._engine(source)
        made.assert_not_called()

    def test_the_engine_uses_odbc_driver_18_the_name_and_both_time_limits(self):
        source = DataSource(kind='mssql', host='shop-sql.database.windows.net', port=1433, database='shop',
                            username='reader', use_ssl=True)
        source.set_password('x')
        with mock.patch('socket.getaddrinfo', side_effect=public), \
             mock.patch('data_analyst_agent.connectors.create_engine') as made, \
             mock.patch('data_analyst_agent.connectors.event.listens_for', return_value=lambda f: f):
            connectors._engine(source)
        url, kwargs = made.call_args.args[0], made.call_args.kwargs
        self.assertEqual(url.drivername, 'mssql+pyodbc')
        self.assertIn('SERVER=tcp:shop-sql.database.windows.net,1433', url.query['odbc_connect'])
        self.assertIn('ApplicationIntent=ReadOnly', url.query['odbc_connect'])
        self.assertEqual(kwargs['connect_args'], {'timeout': connectors.CONNECT_TIMEOUT})


class ReadingTheTables(AnalystCase):

    def test_tables_views_columns_keys_and_foreign_keys(self):
        conn = FakeConnection({
            'INFORMATION_SCHEMA.TABLES': [('dbo', 'Orders', 'BASE TABLE'), ('sales', 'Targets', 'BASE TABLE'),
                                          ('dbo', 'BigOrders', 'VIEW')],
            'INFORMATION_SCHEMA.COLUMNS': [('dbo', 'Orders', 'Id', 'int', 'NO'), ('dbo', 'Orders', 'CustomerId', 'int', 'YES'),
                                           ('sales', 'Targets', 'Month', 'date', 'NO'),
                                           ('dbo', 'BigOrders', 'Id', 'int', 'NO')],
            "CONSTRAINT_TYPE = 'PRIMARY KEY'": [('dbo', 'Orders', 'Id')],
            'SYS.FOREIGN_KEY_COLUMNS': [('dbo', 'Orders', 'CustomerId', 'Customers', 'Id')],
        })
        tables = mssql.read_tables(conn, connectors._table_entry, 400)
        self.assertEqual([(t['schema'], t['name'], t['kind']) for t in tables],
                         [('', 'BigOrders', 'view'), ('', 'Orders', 'table'), ('sales', 'Targets', 'table')])
        orders = tables[1]
        self.assertEqual([(c['name'], c['type'], c['pk']) for c in orders['columns']],
                         [('Id', 'int', True), ('CustomerId', 'int', False)])
        self.assertEqual(orders['fks'], [{'columns': ['CustomerId'], 'references': 'Customers(Id)'}])
        self.assertTrue(all(q.upper() == q or 'INFORMATION_SCHEMA' in q for q in conn.asked))   # capitals throughout


class TheTsqlGuard(AnalystCase):

    def test_reading_queries_pass(self):
        for sql in ("SELECT TOP 200 c.[Name], COUNT(*) AS n FROM dbo.Orders o JOIN dbo.Customers c ON c.Id = o.CustomerId "
                    "GROUP BY c.[Name] ORDER BY n DESC",
                    'WITH x AS (SELECT * FROM dbo.Orders) SELECT TOP 5 * FROM x',
                    'SELECT * FROM dbo.Orders o OUTER APPLY (SELECT TOP 1 * FROM dbo.Items i WHERE i.OrderId = o.Id) x'):
            with self.subTest(sql=sql):
                check_sql(sql, 'mssql')

    def test_commands_files_other_servers_and_writes_are_refused(self):
        for sql in ("EXEC xp_cmdshell 'dir'", "SELECT * FROM OPENROWSET(BULK 'C:\\x.txt', SINGLE_CLOB) AS t",
                    "SELECT * FROM OPENQUERY(linkedsrv, 'select 1')", "WAITFOR DELAY '00:00:10'",
                    'SELECT * INTO dbo.Copy FROM dbo.Orders', 'SELECT 1; DROP TABLE dbo.Orders',
                    "SELECT * FROM sys.fn_get_audit_file('C:\\*.sqlaudit', DEFAULT, DEFAULT)",
                    'SELECT * FROM linkedsrv.otherdb.dbo.Orders'):
            with self.subTest(sql=sql), self.assertRaises(Refused):
                check_sql(sql, 'mssql')


class AskingASqlServer(AnalystCase):

    def test_the_ai_writes_sql_servers_dialect_and_the_answer_comes_back(self):
        source = DataSource.objects.create(company=self.company, name='Shop', kind='mssql', host='db.example.com',
                                           port=1433, database='shop', username='reader', status='ready',
                                           tables=[{'name': 'Orders', 'schema': '', 'kind': 'table', 'fks': [],
                                                    'columns': [{'name': 'Total', 'type': 'decimal', 'pk': False}]}])
        fake = FakeAI({'sql': 'SELECT TOP 200 SUM([Total]) AS total FROM dbo.Orders'}, 'Orders total 4750.50.')
        result = {'columns': ['total'], 'rows': [['4750.50']], 'truncated': False, 'duration_ms': 12}
        with mock.patch('data_analyst_agent.connectors.run', return_value=result) as ran:
            code, body = self.ask(self.admin, source, 'Total of all orders?', fake)
        self.assertEqual((code, body['data']['status'], body['data']['rows']), (200, 'answered', [['4750.50']]))
        self.assertIn('Microsoft SQL Server', fake.prompts[0])
        self.assertIn('TOP 200', fake.prompts[0])
        self.assertEqual(ran.call_args.args[1], 'SELECT TOP 200 SUM([Total]) AS total FROM dbo.Orders')


class SqlServerErrorsInPlainWords(AnalystCase):

    def test_login_reachability_and_certificates_say_what_to_do(self):
        login = Exception('''('28000', "[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for '''
                          '''user 'reader'. (18456) (SQLDriverConnect)")''')
        self.assertEqual(connectors.friendly_error(login), "Login failed for user 'reader'. (Check the user and password.)")
        timeout = Exception("('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Login timeout expired (0) "
                            "(SQLDriverConnect)')")
        self.assertIn("in Azure SQL, under the server's Networking", connectors.friendly_error(timeout))
        cert = Exception("('08001', '[08001] [Microsoft][ODBC Driver 18 for SQL Server]SSL Provider: The certificate chain "
                         "was issued by an authority that is not trusted. (-2146893019) (SQLDriverConnect)')")
        self.assertIn('TrustServerCertificate=yes', connectors.friendly_error(cert))
        self.assertTrue(connectors.timed_out(Exception("('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]"
                                                      "Query timeout expired (0) (SQLExecDirectW)')")))
