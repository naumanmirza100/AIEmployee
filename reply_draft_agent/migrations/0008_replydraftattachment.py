from django.db import migrations, models
import django.db.models.deletion
import reply_draft_agent.models


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0007_inboxemail_thread_key'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReplyDraftAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(help_text='Original filename uploaded by the user.', max_length=255)),
                ('content_type', models.CharField(blank=True, default='', max_length=120)),
                ('size_bytes', models.BigIntegerField(default=0)),
                ('file', models.FileField(help_text='Stored via default_storage (local FS now, S3 later).', max_length=1000, upload_to=reply_draft_agent.models._reply_draft_attachment_upload_path)),
                ('sha256', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('draft', models.ForeignKey(help_text='Draft this file is attached to. CASCADE drops the row when the draft is deleted; the underlying file is removed by the post_delete signal wired up in apps.py.', on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='reply_draft_agent.replydraft')),
            ],
            options={
                'db_table': 'ppp_replydraftagent_replydraftattachment',
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['draft', 'created_at'], name='ppp_replydr_draft_i_2a7864_idx')],
            },
        ),
    ]
