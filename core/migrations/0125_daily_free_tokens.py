from django.db import migrations, models


def five_percent_a_day(apps, schema_editor):
    """Existing agents start with a daily cap of 5% of their free allowance (about 20 days to use it all)."""
    Pricing = apps.get_model('core', 'AdminPricingConfig')
    for p in Pricing.objects.all():
        p.daily_free_tokens = max(0, int(p.free_tokens_on_purchase or 0) // 20)
        p.save(update_fields=['daily_free_tokens'])


class Migration(migrations.Migration):
    """A daily cap on free tokens per company and agent (27 Nov 2026)."""

    dependencies = [
        ('core', '0124_merge_calendars_backups'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminpricingconfig',
            name='daily_free_tokens',
            field=models.BigIntegerField(
                default=0, help_text='Most free tokens one company may use on this agent in a day (UTC). 0 = no daily limit.'),
        ),
        migrations.AddField(
            model_name='agenttokenquota',
            name='day_used_tokens',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='agenttokenquota',
            name='day_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(five_percent_a_day, migrations.RunPython.noop),
    ]
