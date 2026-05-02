from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0008_replydraftattachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='replydraft',
            name='compose_to_email',
            field=models.EmailField(
                blank=True, default='', max_length=254,
                help_text='Recipient address for fresh-compose drafts (no source email)',
            ),
        ),
        migrations.AddField(
            model_name='replydraft',
            name='body_format',
            field=models.CharField(
                choices=[('text', 'Plain text'), ('html', 'HTML')],
                default='text', max_length=4,
            ),
        ),
    ]
