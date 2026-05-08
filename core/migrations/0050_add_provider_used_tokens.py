from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_add_managed_token_fields_to_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenttokenquota',
            name='openai_used_tokens',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='agenttokenquota',
            name='groq_used_tokens',
            field=models.BigIntegerField(default=0),
        ),
    ]
