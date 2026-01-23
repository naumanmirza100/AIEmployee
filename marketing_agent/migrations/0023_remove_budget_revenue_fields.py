# Generated manually to remove budget and revenue fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0022_rename_tables_to_ppp_prefix'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='campaign',
            name='budget',
        ),
        migrations.RemoveField(
            model_name='campaign',
            name='actual_spend',
        ),
        migrations.RemoveField(
            model_name='campaign',
            name='target_revenue',
        ),
        migrations.AlterField(
            model_name='campaignperformance',
            name='metric_name',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('impressions', 'Impressions'),
                    ('clicks', 'Clicks'),
                    ('conversions', 'Conversions'),
                    ('engagement', 'Engagement Rate'),
                    ('roi', 'ROI'),
                    ('cac', 'Customer Acquisition Cost'),
                    ('ltv', 'Lifetime Value'),
                    ('open_rate', 'Open Rate'),
                    ('click_through_rate', 'Click-Through Rate'),
                ]
            ),
        ),
    ]
