import uuid

import django.utils.timezone
from django.db import migrations, models


def gen_approval_tokens(apps, schema_editor):
    SDRMeeting = apps.get_model('ai_sdr_agent', 'SDRMeeting')
    for meeting in SDRMeeting.objects.all():
        meeting.approval_token = uuid.uuid4()
        meeting.save(update_fields=['approval_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0015_merge_20260609_0258'),
    ]

    operations = [
        # Step 1: add approval_token as nullable (no unique yet)
        migrations.AddField(
            model_name='sdrmeeting',
            name='approval_token',
            field=models.UUIDField(null=True, blank=True),
        ),
        # Step 2: populate existing rows
        migrations.RunPython(gen_approval_tokens, migrations.RunPython.noop),
        # Step 3: make it non-null + unique
        migrations.AlterField(
            model_name='sdrmeeting',
            name='approval_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
        # Step 4: add approval_proposed_at
        migrations.AddField(
            model_name='sdrmeeting',
            name='approval_proposed_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Step 5: update status field choices to include awaiting_approval
        migrations.AlterField(
            model_name='sdrmeeting',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('pending', 'Pending'),
                    ('awaiting_approval', 'Awaiting Approval'),
                    ('scheduled', 'Scheduled'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                    ('no_show', 'No Show'),
                ],
                default='pending',
            ),
        ),
    ]
