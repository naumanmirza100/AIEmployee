from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers 4 KeyRequest fields that already exist in SQL Server but were
    missing from the Django model state. Uses SeparateDatabaseAndState so no
    DDL is emitted (avoids touching the live table).
    """

    dependencies = [
        ('core', '0058_keyrequest_key_cost_snapshot'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='keyrequest',
                    name='service_charge_snapshot',
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                migrations.AddField(
                    model_name='keyrequest',
                    name='amount_paid',
                    field=models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True),
                ),
                migrations.AddField(
                    model_name='keyrequest',
                    name='linked_key_id',
                    field=models.BigIntegerField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name='keyrequest',
                    name='paid_at',
                    field=models.DateTimeField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name='keyrequest',
                    name='stripe_session_id',
                    field=models.CharField(max_length=255, null=True, blank=True),
                ),
            ],
        ),
    ]
