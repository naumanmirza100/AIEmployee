from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0013_parity_with_frontline'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaverequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Approval'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('cancelled', 'Cancelled (before decision)'),
                    ('withdrawn', 'Withdrawn (after approval)'),
                ],
                db_index=True,
                default='pending',
                max_length=12,
            ),
        ),
    ]
