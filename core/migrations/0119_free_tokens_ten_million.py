"""Every agent's free tokens on purchase: 10,000,000, for now (25 Oct 2026).

Abdullah asked for it so testing and demos don't run out (the client meeting did at 100,000). Only the pricing
rows change: the amount a company gets when it buys an agent from now on. Existing companies' balances are left
as they are, unlike the super-admin Pricing page, which copies a new value into every company's quota.
"""
from django.db import migrations, models

TEN_MILLION = 10_000_000
BEFORE = 100_000


def raise_free_tokens(apps, schema_editor):
    apps.get_model('core', 'AdminPricingConfig').objects.update(free_tokens_on_purchase=TEN_MILLION)


def back_to_before(apps, schema_editor):
    apps.get_model('core', 'AdminPricingConfig').objects.filter(
        free_tokens_on_purchase=TEN_MILLION).update(free_tokens_on_purchase=BEFORE)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0118_project_source_fingerprint'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminpricingconfig',
            name='free_tokens_on_purchase',
            field=models.BigIntegerField(
                default=TEN_MILLION,
                help_text='Free tokens granted when a company purchases this agent (NOT on signup). '
                          'Superadmin can change this per agent.'),
        ),
        migrations.RunPython(raise_free_tokens, back_to_before),
    ]
