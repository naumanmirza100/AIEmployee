from django.db import migrations, models


class Migration(migrations.Migration):
    """Add a partial-unique constraint on EmailAccount.email where
    is_reply_agent_account=True so the same mailbox can't be attached
    as a Reply Draft Agent inbox by two different companies. Race-safe
    backstop for the app-level check in api.views.reply_draft_agent.
    """

    dependencies = [
        ('marketing_agent', '0032_emailaccount_is_reply_agent_account'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='emailaccount',
            constraint=models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(is_reply_agent_account=True),
                name='unique_reply_agent_email',
            ),
        ),
    ]
