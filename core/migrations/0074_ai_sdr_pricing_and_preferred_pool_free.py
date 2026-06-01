from django.db import migrations, models


def seed_ai_sdr_pricing(apps, schema_editor):
    AdminPricingConfig = apps.get_model('core', 'AdminPricingConfig')
    AdminPricingConfig.objects.get_or_create(
        agent_name='ai_sdr_agent',
        defaults={
            'free_tokens_on_purchase': 1_000_000,
            'managed_key_tokens': 0,
            'monthly_flat_usd': 0,
            'service_charge_usd': 0,
        },
    )


def fix_preferred_pool(apps, schema_editor):
    AgentTokenQuota = apps.get_model('core', 'AgentTokenQuota')
    AgentTokenQuota.objects.filter(
        preferred_pool='managed',
        managed_included_tokens=0,
    ).update(preferred_pool='free')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0073_add_ai_sdr_agent_choice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agenttokenquota',
            name='preferred_pool',
            field=models.CharField(
                blank=True,
                choices=[
                    ('free', 'Free Platform Tokens'),
                    ('managed', 'Managed Key Tokens'),
                    ('byok', 'BYOK Key'),
                    ('none', 'Disabled (no key)'),
                ],
                default='free',
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(seed_ai_sdr_pricing, migrations.RunPython.noop),
        migrations.RunPython(fix_preferred_pool, migrations.RunPython.noop),
    ]
