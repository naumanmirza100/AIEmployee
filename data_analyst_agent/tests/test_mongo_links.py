"""MongoDB's links between collections (16 Nov 2026).

MongoDB has no foreign keys, and on the PayPerProject data copied into MongoDB the AI guessed what a field pointed at:
leave requests were joined straight to departments, and projects to themselves for their company (8 of 16 questions
right). A field named for a collection is now taken to point at it, and the link kept only where the data agrees: by
name core_task.assignee_id pointed at a collection of meeting assignees, while its values are users. Then 11 of 16.
"""
from unittest import mock

from django.test import SimpleTestCase

from data_analyst_agent import engine, mongo
from data_analyst_agent.models import DataSource


def collection(name, **fields):
    return {'name': name, 'schema': '', 'kind': 'collection', 'fks': [],
            'columns': [{'name': '_id', 'type': 'int'}] + [{'name': f, 'type': t} for f, t in fields.items()]}


def links(tables, name):
    table = next(t for t in engine._mongo_references(tables) if t['name'] == name)
    return {fk['columns'][0]: fk['references'] for fk in table['fks']}


class NamedLinkTests(SimpleTestCase):

    def test_a_field_named_for_a_collection_points_at_it(self):
        tables = [collection('orders', customer_id='int', companyId='objectId', status='string', owner='objectId',
                             department_obj_id='int', note='string'),
                  collection('customers'), collection('companies'), collection('departments')]
        self.assertEqual(links(tables, 'orders'), {'customer_id': 'customers(_id)', 'companyId': 'companies(_id)',
                                                   'department_obj_id': 'departments(_id)'})

    def test_the_longest_name_wins_and_the_same_app_breaks_a_tie(self):
        tables = [collection('hr_employee', company_user_id='int', user_id='int'),
                  collection('core_company_users'), collection('auth_user'),
                  collection('marketing_campaign_leads', lead_id='int'), collection('marketing_lead'),
                  collection('sales_lead')]
        self.assertEqual(links(tables, 'hr_employee'), {'company_user_id': 'core_company_users(_id)',
                                                        'user_id': 'auth_user(_id)'})
        self.assertEqual(links(tables, 'marketing_campaign_leads'), {'lead_id': 'marketing_lead(_id)'})

    def test_no_link_when_nothing_or_too_much_is_named_so(self):
        tables = [collection('tickets', assignee_id='int', lead_id='int'), collection('a_lead'), collection('b_lead')]
        self.assertEqual(links(tables, 'tickets'), {})


class FakeCollection:
    def __init__(self, docs, fail=False):
        self.docs, self.fail = docs, fail

    def find(self, flt, projection=None, limit=0, max_time_ms=None):
        field = next(iter(flt))
        return [d for d in self.docs if d.get(field) is not None][:limit or None]

    def count_documents(self, flt, maxTimeMS=None):
        if self.fail:
            raise RuntimeError('timed out')
        wanted = flt['_id']['$in']
        return sum(1 for d in self.docs if d['_id'] in wanted)


class FakeClient:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, name):
        return self

    def close(self):
        pass


class VerifiedLinkTests(SimpleTestCase):

    def check(self, collections, tables):
        client = FakeClient(collections)
        client.__getitem__ = None
        db = mock.Mock(__getitem__=lambda _self, name: collections[name])
        with mock.patch.object(mongo, '_client', return_value=client), \
                mock.patch.object(mongo, '_database', return_value=db):
            return mongo.verify_references(DataSource(kind=DataSource.KIND_MONGO), tables)

    def test_a_link_the_data_disagrees_with_is_dropped(self):
        tables = [{'name': 'tasks', 'fks': [{'columns': ['assignee_id'], 'references': 'task_assignees(_id)'},
                                            {'columns': ['project_id'], 'references': 'projects(_id)'}]}]
        collections = {
            'tasks': FakeCollection([{'_id': i, 'assignee_id': 100 + i, 'project_id': i % 3 + 1} for i in range(10)]),
            'task_assignees': FakeCollection([{'_id': i} for i in range(1, 5)]),     # the assignees are users
            'projects': FakeCollection([{'_id': i} for i in range(1, 4)]),
        }
        out = self.check(collections, tables)
        self.assertEqual([fk['columns'][0] for fk in out[0]['fks']], ['project_id'])

    def test_a_check_that_fails_keeps_the_link(self):
        tables = [{'name': 'tasks', 'fks': [{'columns': ['project_id'], 'references': 'projects(_id)'}]}]
        collections = {'tasks': FakeCollection([{'_id': 1, 'project_id': 9}]),
                       'projects': FakeCollection([], fail=True)}
        self.assertEqual(self.check(collections, tables), tables)
