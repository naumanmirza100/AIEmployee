"""A new agent in the Agent table is not a model change.

The fields that hold an agent's name took their choices from the Agent table, and Django wrote the
agents of the day into each migration. Adding CRM Sync to the live site's table on 24 Oct 2026 made the
deploy's `makemigrations --check` see a change nobody made, and it stopped the release of PR #289.
"""
from django.test import TestCase

from core.models import Agent, AgentSlugField, CompanyAPIKey, CompanyModulePurchase, KeyEventLog


class AgentSlugFieldTests(TestCase):

    FIELDS = [(CompanyAPIKey, 'agent_name'), (KeyEventLog, 'agent_name'), (CompanyModulePurchase, 'module_name')]

    def test_choices_are_left_out_of_migrations(self):
        Agent.objects.create(slug='crm_sync_agent', name='CRM Sync Agent', is_active=True, is_purchasable=False)
        Agent.objects.create(slug='new_agent', name='A New Agent', is_active=True, is_purchasable=True)
        for model, name in self.FIELDS:
            field = model._meta.get_field(name)
            self.assertIsInstance(field, AgentSlugField)
            _, path, _, kwargs = field.deconstruct()
            self.assertEqual(path, 'django.db.models.CharField', name)
            self.assertNotIn('choices', kwargs, f'{model.__name__}.{name}')

    def test_the_choices_still_come_from_the_table(self):
        Agent.objects.create(slug='crm_sync_agent', name='CRM Sync Agent', is_active=True, is_purchasable=False)
        field = CompanyAPIKey._meta.get_field('agent_name')
        self.assertIn(('crm_sync_agent', 'CRM Sync Agent'), list(field.choices))
        purchasable = [slug for slug, _ in CompanyModulePurchase._meta.get_field('module_name').choices]
        self.assertNotIn('crm_sync_agent', purchasable)
