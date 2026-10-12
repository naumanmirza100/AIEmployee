# The six-digit password reset code of a dashboard login was kept as typed and
# could be tried again and again for its ten minutes. It is now kept as a keyed
# fingerprint (so the column is wider) and tries against it are counted on the
# login: five and the code is void. A code that is waiting when this runs was
# stored the old way and can no longer match, so it is cleared; its owner asks
# for a new one.

from django.db import migrations, models


def clear_codes_stored_as_typed(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    CompanyUser._base_manager.exclude(reset_otp=None).update(reset_otp=None, reset_otp_expires=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0113_calendarblock_sales_and_executive_sources'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyuser',
            name='reset_otp_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='companyuser',
            name='reset_otp',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.RunPython(clear_codes_stored_as_typed, migrations.RunPython.noop),
    ]
