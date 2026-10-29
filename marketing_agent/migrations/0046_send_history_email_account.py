"""Each send records the mailbox it went from (CO-194). Existing sends are given the mailbox their sequence named, else
their campaign's, as the counts used to infer."""
import django.db.models.deletion
from django.db import migrations, models


def fill_in(apps, schema_editor):
    EmailSendHistory = apps.get_model('marketing_agent', 'EmailSendHistory')
    EmailSequenceStep = apps.get_model('marketing_agent', 'EmailSequenceStep')
    by_template = dict(EmailSequenceStep.objects.filter(sequence__email_account__isnull=False)
                       .values_list('template_id', 'sequence__email_account_id'))
    for template_id, account_id in by_template.items():
        EmailSendHistory.objects.filter(email_account__isnull=True, email_template_id=template_id).update(
            email_account_id=account_id)
    for send in (EmailSendHistory.objects.filter(email_account__isnull=True, email_template__isnull=False,
                                                 campaign__email_account__isnull=False)
                 .values('id', 'campaign__email_account_id')):
        EmailSendHistory.objects.filter(id=send['id']).update(email_account_id=send['campaign__email_account_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0045_dismissed_marketing_alert'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailsendhistory',
            name='email_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='sends_made', to='marketing_agent.emailaccount'),
        ),
        migrations.RunPython(fill_in, migrations.RunPython.noop),
    ]
