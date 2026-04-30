# Hand-written migration: the auto-generated AlterField calls trigger a
# Django/MSSQL backend bug ("InboxEmail has no field named '-received_at'")
# when it tries to re-evaluate the model's `Meta.indexes` during column
# alterations. Skipping the ORM-level AlterField and issuing the column
# change as raw SQL avoids that codepath. The Python-side state_operations
# still inform Django that the model's fields have changed so future
# auto-generated migrations stay consistent.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0004_inboxemail_body_html_alter_inboxemail_body'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Allow NULL on body_html so any caller (including older
                # workers that haven't reloaded the model) can insert
                # without 23000 unique-constraint violations. nvarchar(max)
                # mirrors what `models.TextField` maps to on SQL Server.
                migrations.RunSQL(
                    sql="ALTER TABLE ppp_replydraftagent_inboxemail ALTER COLUMN body_html nvarchar(max) NULL;",
                    reverse_sql="ALTER TABLE ppp_replydraftagent_inboxemail ALTER COLUMN body_html nvarchar(max) NOT NULL;",
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='inboxemail',
                    name='body',
                    field=models.TextField(blank=True, default='', help_text='Plain-text body. Used for AI analysis and search; preferred over HTML when both are present in the source.'),
                ),
                migrations.AlterField(
                    model_name='inboxemail',
                    name='body_html',
                    field=models.TextField(blank=True, default='', help_text='Original HTML body if the source carried one. Rendered in the UI for fidelity (links, images, layout); plain `body` is used as fallback when this is empty.', null=True),
                ),
            ],
        ),
    ]
