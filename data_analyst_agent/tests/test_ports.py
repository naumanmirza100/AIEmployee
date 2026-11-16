"""AI Data Analyst: the port of a database added (16 Nov 2026). The port in a pasted connection string is kept; without
one, the kind's own is saved (PostgreSQL 5432, MySQL / MariaDB 3306, SQL Server 1433, MongoDB 27017), so the list
shows it; a port typed beside the string wins; and anything but 1 to 65535 is refused. The screen offers the same
defaults (PaPerProjectFront/src/utils/connectionString.js). Nothing is connected: the addresses are private, so the
test stops before connecting, or MongoDB is the fake client."""
from unittest import mock

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, mssql
from data_analyst_agent.models import DataSource
from data_analyst_agent.tests.test_data_analyst import AnalystCase
from data_analyst_agent.tests.test_mongo import ATLAS, FakeMongo, MongoCase

NAMED = 'Data Source=sqlprod01.example.com\\SALES;Initial Catalog=erp;User ID=reader;Password=x'


class SqlPorts(AnalystCase):

    def add(self, payload):
        with mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.1.1.1', 5432))]):
            return self.call(views.sources, self.admin, payload)

    def saved(self, payload):
        code, body = self.add(payload)
        self.assertEqual(code, 201, body)
        return DataSource.objects.get(pk=body['data']['id'])

    def test_a_string_without_a_port_gets_its_kinds_default_and_the_list_shows_it(self):
        for string, port in (('postgresql://r:p@db.example.com/shop', 5432), ('mysql://r:p@db.example.com/shop', 3306),
                             ('mariadb://r:p@db.example.com/shop', 3306),
                             ('Server=db.example.com;Database=erp;User ID=r;Password=p', 1433),
                             ('jdbc:sqlserver://db.example.com;databaseName=erp;user=r;password=p', 1433)):
            with self.subTest(string=string):
                code, body = self.add({'connection_string': string})
                self.assertEqual((code, body['data']['port']), (201, port))

    def test_the_port_in_the_string_is_kept(self):
        for string, port in (('postgresql://r:p@db.example.com:6543/shop', 6543),
                             ('mysql://r:p@db.example.com:25060/shop', 25060),
                             ('Server=tcp:db.example.com,14330;Database=erp;User ID=r;Password=p', 14330)):
            with self.subTest(string=string):
                self.assertEqual(self.saved({'connection_string': string}).port, port)

    def test_a_port_typed_beside_the_string_wins_over_the_strings(self):
        source = self.saved({'connection_string': 'postgresql://r:p@db.example.com:5432/shop', 'port': '6543'})
        self.assertEqual((source.host, source.port, source.database), ('db.example.com', 6543, 'shop'))

    def test_the_form_without_a_port_gets_the_default_and_a_typed_one_is_kept(self):
        fields = {'kind': 'mysql', 'host': 'db.example.com', 'database': 'erp', 'username': 'r', 'password': 'p'}
        self.assertEqual(self.saved({**fields, 'port': ''}).port, 3306)
        self.assertEqual(self.saved({**fields, 'port': '3307'}).port, 3307)
        self.assertEqual(connectors.default_port('mssql'), 1433)

    def test_a_port_that_is_not_one_is_refused_before_saving(self):
        for port in ('abc', '0', '70000', '54 32'):
            with self.subTest(port=port):
                code, body = self.add({'connection_string': 'postgresql://r:p@db.example.com/shop', 'port': port})
                self.assertEqual(code, 400)
                self.assertIn('1 to 65535', body['message'])
        self.assertFalse(DataSource.objects.exists())

    def test_a_named_sql_server_instance_takes_the_port_typed_beside_it(self):
        code, body = self.add({'connection_string': NAMED})
        self.assertEqual(code, 400)
        self.assertIn('needs its port', body['message'])
        source = self.saved({'connection_string': NAMED, 'port': '51433'})
        self.assertEqual((source.kind, source.host, source.port, source.database), ('mssql', 'sqlprod01.example.com',
                                                                                     51433, 'erp'))
        self.assertEqual(mssql.parse_connection_string(NAMED + ';Port=51433')['port'], 51433)


class MongoPorts(MongoCase):

    def port(self, string, **extra):
        code, body = self.add(FakeMongo(), string, **extra)
        self.assertEqual(code, 201, body)
        return DataSource.objects.get(pk=body['data']['id']).port

    def test_one_server_without_a_port_gets_27017_and_a_typed_one_is_kept(self):
        self.assertEqual(self.port('mongodb://reader:pw@db.example.com/shop'), 27017)
        self.assertEqual(self.port('mongodb://reader:pw@db.example.com/shop', port='27019'), 27019)
        self.assertEqual(self.port('mongodb://reader:pw@db.example.com:27018/shop'), 27018)

    def test_a_srv_name_and_several_servers_keep_no_single_port(self):
        self.assertIsNone(self.port(ATLAS, port='27018'))
        self.assertIsNone(self.port('mongodb://reader:pw@a.example.com:27017,b.example.com/shop?replicaSet=rs0'))
