"""AI Data Analyst with MongoDB (6 Nov 2026): the connection string, the address checks, the structure read from
samples, the aggregation guard, a question asked end to end, and running it again. MongoDB itself is a fake client that
records what it was asked; the AI is the FakeAI of the SQL tests."""
import datetime
import json
from unittest import mock

import dns.resolver  # noqa: F401  (loaded, so its lookup can be replaced)
from bson import Decimal128, ObjectId
from pymongo.errors import ExecutionTimeout, OperationFailure, ServerSelectionTimeoutError

from api.views import data_analyst_agent as views
from data_analyst_agent import connectors, mongo
from data_analyst_agent.guards import Refused, check_pipeline
from data_analyst_agent.models import DataQuestion, DataSource
from data_analyst_agent.tests.test_data_analyst import AnalystCase, FakeAI

ATLAS = 'mongodb+srv://reader:S3cret-pass@cluster0.ab1cd.mongodb.net/shop?retryWrites=true&w=majority&authSource=admin'
KARACHI, LAHORE = ObjectId('64b000000000000000000001'), ObjectId('64b000000000000000000002')
DATA = {
    'customers': [{'_id': KARACHI, 'name': 'Ayesha Traders', 'city': 'Karachi'},
                  {'_id': LAHORE, 'name': 'Bilal Foods', 'city': 'Lahore', 'address': {'street': 'Mall Road'}}],
    'orders': [{'_id': ObjectId(), 'customer': KARACHI, 'total': Decimal128('1200.50'), 'items': [{'sku': 'A1', 'qty': 2}],
                'created': datetime.datetime(2026, 10, 2, tzinfo=datetime.timezone.utc)},
               {'_id': ObjectId(), 'customer': LAHORE, 'total': Decimal128('450'), 'items': [],
                'created': datetime.datetime(2026, 10, 20, tzinfo=datetime.timezone.utc)}],
}


class FakeCursor(list):
    closed = False

    def close(self):
        self.closed = True


class FakeCollection:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def aggregate(self, pipeline, **options):
        if pipeline and '$sample' in pipeline[0]:
            return FakeCursor(self.client.data.get(self.name, [])[:pipeline[0]['$sample']['size']])
        self.client.asked.append((self.name, pipeline, options))
        if self.client.fail_with:
            raise self.client.fail_with
        return FakeCursor(self.client.answer)

    def find(self, *args, **kwargs):
        return FakeCursor(self.client.data.get(self.name, []))


class FakeDatabase:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def __getitem__(self, name):
        return FakeCollection(self.client, name)

    def list_collections(self, **kwargs):
        return [{'name': name, 'type': 'collection'} for name in self.client.data]

    def command(self, command):
        actions = list(self.client.actions)
        return {'authInfo': {'authenticatedUsers': [{'user': 'reader', 'db': 'admin'}],
                             'authenticatedUserPrivileges': [{'resource': {'db': '', 'collection': ''},
                                                               'actions': actions}]}}


class FakeMongo:
    """What _client returns: records the database used and every aggregation asked of it."""

    def __init__(self, data=None, answer=(), databases=('shop',), actions=('find', 'listCollections'), members=()):
        self.data, self.answer, self.databases, self.actions = dict(data or DATA), list(answer), databases, actions
        self.asked, self.used, self.fail_with, self.closed = [], [], None, 0
        self.admin = mock.Mock(command=mock.Mock(return_value={'ok': 1}))
        self.topology_description = mock.Mock(server_descriptions=mock.Mock(return_value={m: None for m in members}))

    def __getitem__(self, name):
        self.used.append(name)
        return FakeDatabase(self, name)

    def list_database_names(self):
        return list(self.databases)

    def close(self):
        self.closed += 1


def public(host, port, *args, **kwargs):
    return [(2, 1, 6, '', ('8.8.4.4', port))]


class MongoCase(AnalystCase):

    def add(self, fake, string=ATLAS, **extra):
        with mock.patch('data_analyst_agent.mongo._client', return_value=fake):
            return self.call(views.sources, self.admin, {'name': 'App', 'connection_string': string, **extra})

    def mongo_source(self, fake=None):
        code, body = self.add(fake or FakeMongo())
        self.assertEqual(code, 201, body)
        return DataSource.objects.get(pk=body['data']['id'])

    def ask_mongo(self, source, question, ai, fake):
        with mock.patch('data_analyst_agent.mongo._client', return_value=fake):
            return self.ask(self.admin, source, question, ai)


class TheConnectionString(MongoCase):

    def test_an_atlas_string_is_read_into_its_parts(self):
        parts = mongo.parse_uri('mongodb+srv://pp%40reader:p%2Fss@cluster0.ab1cd.mongodb.net/shop'
                                '?retryWrites=true&w=majority&authSource=admin&appName=Cluster0')
        self.assertEqual(parts, {'srv': True, 'host': 'cluster0.ab1cd.mongodb.net', 'port': None, 'database': 'shop',
                                 'username': 'pp@reader', 'password': 'p/ss', 'options': {'authSource': 'admin'},
                                 'tls': True})

    def test_a_plain_string_keeps_its_hosts_and_asks_for_tls_only_when_it_says_so(self):
        parts = mongo.parse_uri('mongodb://u:p@h1.example.com:27017,h2.example.com:27018/app?replicaSet=rs0&tls=true')
        self.assertEqual((parts['host'], parts['port'], parts['options'], parts['tls']),
                         ('h1.example.com:27017,h2.example.com:27018', None, {'replicaSet': 'rs0'}, True))
        self.assertFalse(mongo.parse_uri('mongodb://u:p@db.example.com:27019')['tls'])
        self.assertEqual(mongo.parse_uri('mongodb://u:p@db.example.com:27019')['port'], 27019)

    def test_other_strings_are_refused(self):
        for text in ('postgres://u:p@h/db', 'mongodb+srv://u:p@cluster0.example.net:27017/db', 'mongodb://u:p@/db',
                     'mongodb://u:p@db.example.com:port/db'):
            with self.subTest(text=text), self.assertRaises(Refused):
                mongo.parse_uri(text)


class AddingAMongoDatabase(MongoCase):

    def test_an_atlas_string_is_saved_its_password_encrypted_and_its_collections_read(self):
        code, body = self.add(FakeMongo())
        self.assertEqual(code, 201, body)
        data = body['data']
        self.assertEqual((data['kind'], data['status'], data['host'], data['database'], data['username'], data['use_srv']),
                         ('mongodb', 'ready', 'cluster0.ab1cd.mongodb.net', 'shop', 'reader', True))
        self.assertEqual(body['message'], 'Connected to "shop". 2 collection(s) read.')
        self.assertFalse(data['user_can_write'])
        self.assertNotIn('S3cret-pass', json.dumps(body))
        source = DataSource.objects.get(pk=data['id'])
        self.assertNotIn('S3cret-pass', source.password_encrypted)
        self.assertEqual(source.get_password(), 'S3cret-pass')
        self.assertEqual(source.options, {'authSource': 'admin'})          # w and retryWrites are about writing

    def test_the_structure_is_field_names_and_types_never_a_value(self):
        source = self.mongo_source()
        orders = next(t for t in source.tables if t['name'] == 'orders')
        fields = {c['name']: c['type'] for c in orders['columns']}
        self.assertEqual(fields, {'_id': 'objectId', 'customer': 'objectId', 'total': 'decimal',
                                  'items': 'array<object>', 'items.sku': 'string', 'items.qty': 'int', 'created': 'date'})
        self.assertTrue(next(c for c in orders['columns'] if c['name'] == '_id')['pk'])
        customers = next(t for t in source.tables if t['name'] == 'customers')
        self.assertIn({'name': 'address.street', 'type': 'string', 'pk': False, 'nullable': True}, customers['columns'])
        stored = json.dumps(source.tables)
        for value in ('Ayesha', 'Karachi', 'Mall Road', '1200.50', 'A1'):
            self.assertNotIn(value, stored)

    def test_without_a_database_named_the_only_one_the_user_sees_is_taken(self):
        code, body = self.add(FakeMongo(databases=('admin', 'local', 'test')), string=ATLAS.replace('/shop', '/'))
        self.assertEqual((body['data']['status'], body['data']['database']), ('ready', 'test'))
        self.assertEqual(body['message'], 'Connected to "test". 2 collection(s) read.')

    def test_with_several_databases_it_asks_which_naming_them(self):
        code, body = self.add(FakeMongo(databases=('shop', 'blog', 'admin')), string=ATLAS.replace('/shop', '/'))
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('this user can see blog, shop', body['data']['last_error'])

    def test_a_database_typed_beside_the_string_wins(self):
        fake = FakeMongo()
        code, body = self.add(fake, database='tutors')
        self.assertEqual(body['data']['database'], 'tutors')
        self.assertIn('tutors', fake.used)

    def test_a_user_that_could_write_is_said(self):
        code, body = self.add(FakeMongo(actions=('find', 'insert', 'update')))
        self.assertTrue(body['data']['user_can_write'])

    def test_a_string_without_a_user_is_refused(self):
        code, body = self.add(FakeMongo(), string='mongodb+srv://cluster0.ab1cd.mongodb.net/shop')
        self.assertEqual(code, 400)
        self.assertIn('needs a user', body['message'])


class OnlyPublicAddresses(MongoCase):

    def test_a_service_record_pointing_inside_is_refused_before_connecting(self):
        record = mock.Mock(target='shard-00.evil.example.', port=27017)
        with mock.patch('dns.resolver.resolve', return_value=[record]), \
             mock.patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('172.18.0.3', 27017))]), \
             mock.patch('pymongo.MongoClient') as client:
            code, body = self.call(views.sources, self.admin, {'connection_string': ATLAS})
        client.assert_not_called()
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('not a public address', body['data']['last_error'])

    def test_a_single_plain_host_is_reached_at_its_checked_address_only(self):
        with mock.patch('socket.getaddrinfo', side_effect=public), mock.patch('pymongo.MongoClient') as client:
            self.call(views.sources, self.admin, {'connection_string': 'mongodb://reader:pw@db.example.com:27019/shop'})
        kwargs = client.call_args.kwargs
        self.assertEqual((kwargs['host'], kwargs['port'], kwargs['directConnection'], kwargs['tls']),
                         ('8.8.4.4', 27019, True, False))
        self.assertEqual(kwargs['readPreference'], 'secondaryPreferred')

    def test_a_member_of_a_replica_set_that_is_not_public_closes_the_connection(self):
        fake = FakeMongo(members=[('cluster0-shard-00.ab1cd.mongodb.net', 27017), ('redis', 6379)])

        def lookup(host, port, *args, **kwargs):
            return [(2, 1, 6, '', ('172.18.0.4' if host == 'redis' else '8.8.4.4', port))]

        with mock.patch('data_analyst_agent.mongo._client', return_value=fake), \
             mock.patch('socket.getaddrinfo', side_effect=lookup):
            body = self.call(views.sources, self.admin, {'connection_string': ATLAS})[1]
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('"redis" points to 172.18.0.4', body['data']['last_error'])
        self.assertEqual(fake.used, [])                # nothing was read


class TheAggregationGuard(MongoCase):
    COLLECTIONS = {'orders', 'customers'}

    def test_reading_stages_and_joins_pass(self):
        query = {'collection': 'orders', 'pipeline': [
            {'$match': {'created': {'$gte': {'$date': '2026-10-01T00:00:00Z'}}}},
            {'$lookup': {'from': 'customers', 'localField': 'customer', 'foreignField': '_id', 'as': 'c'}},
            {'$unwind': '$c'}, {'$group': {'_id': '$c.city', 'orders': {'$sum': 1}}}, {'$sort': {'orders': -1}},
            {'$facet': {'top': [{'$limit': 5}], 'count': [{'$count': 'n'}]}},
            {'$unionWith': {'coll': 'customers', 'pipeline': [{'$project': {'name': 1}}]}}]}
        self.assertTrue(check_pipeline(json.dumps(query), self.COLLECTIONS))

    def test_writing_javascript_and_other_databases_are_refused(self):
        cases = {
            '$out': [{'$out': 'copy'}],
            '$merge': [{'$group': {'_id': 1}}, {'$merge': {'into': 'copy'}}],
            'in a facet': [{'$facet': {'a': [{'$merge': 'x'}]}}],
            'in a lookup': [{'$lookup': {'from': 'customers', 'as': 'c', 'pipeline': [{'$out': 'x'}]}}],
            '$where': [{'$match': {'$where': 'this.total > 1'}}],
            '$function': [{'$addFields': {'x': {'$function': {'body': 'function(){}', 'args': [], 'lang': 'js'}}}}],
            '$accumulator': [{'$group': {'_id': 1, 'x': {'$accumulator': {'init': 'f'}}}}],
            '$code': [{'$match': {'total': {'$code': 'x'}}}],
            'server stage': [{'$currentOp': {}}],
            'system collection': [{'$lookup': {'from': 'system.users', 'as': 'u', 'pipeline': []}}],
            'unknown collection': [{'$lookup': {'from': 'payments', 'as': 'p', 'pipeline': []}}],
            'other database': [{'$lookup': {'from': {'db': 'admin', 'coll': 'users'}, 'as': 'u', 'pipeline': []}}],
            'two keys in a stage': [{'$match': {}, '$limit': 1}],
        }
        for label, pipeline in cases.items():
            with self.subTest(label), self.assertRaises(Refused):
                check_pipeline(json.dumps({'collection': 'orders', 'pipeline': pipeline}), self.COLLECTIONS)
        for text in ('db.orders.deleteMany({})', '[]', json.dumps({'collection': 'orders', 'pipeline': [], 'x': 1}),
                     json.dumps({'collection': 'payments', 'pipeline': []})):
            with self.subTest(text), self.assertRaises(Refused):
                check_pipeline(text, self.COLLECTIONS)


class AskingAMongoDatabase(MongoCase):
    PIPELINE = [{'$match': {'created': {'$gte': {'$date': '2026-10-01T00:00:00Z'}}}},
                {'$lookup': {'from': 'customers', 'localField': 'customer', 'foreignField': '_id', 'as': 'c'}},
                {'$unwind': '$c'},
                {'$group': {'_id': '$c.city', 'orders': {'$sum': 1}, 'total': {'$sum': '$total'}}},
                {'$sort': {'total': -1}}]
    ANSWER = [{'_id': 'Karachi', 'orders': 1, 'total': Decimal128('1200.50')},
              {'_id': 'Lahore', 'orders': 1, 'total': Decimal128('450')}]

    def test_a_question_is_answered_by_one_aggregation_and_only_its_text_kept(self):
        fake = FakeMongo(answer=self.ANSWER)
        source = self.mongo_source(fake)
        ai = FakeAI({'collection': 'orders', 'pipeline': self.PIPELINE},
                    'Karachi sold the most since 1 October: 1200.50, then Lahore with 450.')
        code, body = self.ask_mongo(source, 'Which city sold the most since October?', ai, fake)
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual((data['status'], data['query_kind'], data['flagged']), ('answered', 'mongodb', []))
        self.assertEqual(data['columns'], ['_id', 'orders', 'total'])
        self.assertEqual(data['rows'], [['Karachi', 1, '1200.50'], ['Lahore', 1, '450']])
        collection, pipeline, options = fake.asked[0]
        self.assertEqual(collection, 'orders')
        self.assertEqual(pipeline[0]['$match']['created']['$gte'], datetime.datetime(2026, 10, 1))   # a real date
        self.assertEqual(options['maxTimeMS'], connectors.QUERY_TIMEOUT * 1000)
        record = DataQuestion.objects.get(pk=data['id'])
        self.assertEqual(json.loads(record.sql), {'collection': 'orders', 'pipeline': self.PIPELINE})
        self.assertEqual((record.row_count, record.columns), (2, ['_id', 'orders', 'total']))
        self.assertIn('customer objectId', ai.prompts[0])          # the AI saw the fields and their types
        self.assertIn('never $out or $merge', ai.prompts[0])
        self.assertIn('Rows:', ai.prompts[1])

    def test_a_pipeline_that_writes_goes_back_to_the_ai_with_the_reason_and_never_runs(self):
        fake = FakeMongo(answer=[{'n': 2}])
        source = self.mongo_source(fake)
        ai = FakeAI({'collection': 'orders', 'pipeline': [{'$match': {}}, {'$out': 'copy'}]},
                    {'collection': 'orders', 'pipeline': [{'$count': 'n'}]}, 'There are 2 orders.')
        code, body = self.ask_mongo(source, 'How many orders?', ai, fake)
        self.assertEqual(body['data']['rows'], [[2]])
        self.assertIn('It failed: Only reading is allowed: the query contains $out.', ai.prompts[1])
        self.assertEqual([p for _c, p, _o in fake.asked], [[{'$count': 'n'}]])

    def test_a_collection_it_does_not_have_is_said_to_the_ai(self):
        fake = FakeMongo(answer=[{'n': 2}])
        source = self.mongo_source(fake)
        ai = FakeAI({'collection': 'payments', 'pipeline': []}, {'collection': 'orders', 'pipeline': [{'$count': 'n'}]},
                    '2 orders.')
        self.ask_mongo(source, 'How many payments?', ai, fake)
        self.assertIn('There is no collection "payments"', ai.prompts[1])

    def test_a_request_to_change_data_is_answered_without_a_query(self):
        fake = FakeMongo()
        source = self.mongo_source(fake)
        ai = FakeAI({'collection': '', 'pipeline': [], 'ask_back': "I only read your database, so I can't change it."})
        code, body = self.ask_mongo(source, 'Delete the old orders.', ai, fake)
        self.assertEqual((body['data']['status'], body['data']['answer']),
                         ('asked_back', "I only read your database, so I can't change it."))
        self.assertIn('Asked to change data', ai.prompts[0])
        self.assertEqual(fake.asked, [])

    def test_the_time_limit_is_said_plainly_and_not_tried_again(self):
        fake = FakeMongo()
        source = self.mongo_source(fake)
        fake.fail_with = ExecutionTimeout('operation exceeded time limit', 50)
        ai = FakeAI({'collection': 'orders', 'pipeline': [{'$count': 'n'}]}, {'collection': 'orders', 'pipeline': []})
        code, body = self.ask_mongo(source, 'Count everything', ai, fake)
        self.assertEqual(len(ai.prompts), 1)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('the database stopped it. Ask about a smaller part', body['data']['answer'])

    def test_running_it_again_checks_the_stored_query_first(self):
        fake = FakeMongo(answer=self.ANSWER)
        source = self.mongo_source(fake)
        body = self.ask_mongo(source, 'By city?', FakeAI({'collection': 'orders', 'pipeline': self.PIPELINE}, 'Karachi.'),
                              fake)[1]
        record = DataQuestion.objects.get(pk=body['data']['id'])
        with mock.patch('data_analyst_agent.mongo._client', return_value=fake):
            again = self.call(views.question_run, self.admin, question_id=record.pk)[1]
            self.assertEqual(again['data']['rows'], [['Karachi', 1, '1200.50'], ['Lahore', 1, '450']])
            record.sql = json.dumps({'collection': 'orders', 'pipeline': [{'$merge': {'into': 'orders'}}]})
            record.save()
            code, refused = self.call(views.question_run, self.admin, question_id=record.pk)
        self.assertEqual(code, 400)
        self.assertIn('$merge', refused['message'])
        self.assertEqual(len(fake.asked), 2)            # the question, and the first run again; never the $merge


class MongoErrorsInPlainWords(MongoCase):

    def test_an_unreachable_cluster_points_at_atlas_network_access(self):
        message = connectors.friendly_error(ServerSelectionTimeoutError('cluster0-shard-00: timed out, Topology ...'))
        self.assertIn('Network Access', message)
        self.assertNotIn('Topology', message)

    def test_a_wrong_password_and_a_missing_role_say_what_to_do(self):
        self.assertIn('Check the user and password',
                      connectors.friendly_error(OperationFailure('bad auth : Authentication failed.', 8000)))
        self.assertIn('give it the read role', connectors.friendly_error(
            OperationFailure('not authorized on shop to execute command { aggregate: "orders" }', 13)))

    def test_the_time_limit_is_known(self):
        self.assertTrue(connectors.timed_out(ExecutionTimeout('operation exceeded time limit', 50)))
