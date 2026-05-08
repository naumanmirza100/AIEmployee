from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_add_provider_used_tokens'),
    ]

    operations = [
        # Remove the hardcoded per-provider columns added in 0050
        migrations.RemoveField(model_name='agenttokenquota', name='openai_used_tokens'),
        migrations.RemoveField(model_name='agenttokenquota', name='groq_used_tokens'),

        # Add flexible per-provider usage table
        migrations.CreateModel(
            name='AgentProviderUsage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(
                    choices=[
                        ('openai', 'OpenAI'),
                        ('claude', 'Claude / Anthropic'),
                        ('gemini', 'Google Gemini'),
                        ('groq', 'Groq (Llama)'),
                        ('grok', 'xAI Grok'),
                    ],
                    max_length=20,
                )),
                ('used_tokens', models.BigIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quota', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='provider_usage',
                    to='core.agenttokenquota',
                )),
            ],
            options={'unique_together': {('quota', 'provider')}},
        ),
    ]
