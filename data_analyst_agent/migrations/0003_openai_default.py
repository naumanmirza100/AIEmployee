"""The AI Data Analyst's AI calls go to OpenAI, like the other agents' (3 Nov 2026).

0002 made the agent row without a provider, so it took the field's default, Groq. On the live site a question on a
database of 294 tables then failed: choosing its tables asked Groq for 11,536 tokens where the platform's Groq key
allows 8,000 a minute, and the fallback model was gone.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    apps.get_model('core', 'Agent').objects.filter(slug='data_analyst_agent').update(default_provider='openai')


class Migration(migrations.Migration):

    dependencies = [
        ('data_analyst_agent', '0002_on_sale'),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
