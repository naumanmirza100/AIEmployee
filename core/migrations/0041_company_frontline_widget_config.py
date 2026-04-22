from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_company_frontline_allowed_origins'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='frontline_widget_config',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='Widget theming + pre-chat form + operating hours + captcha toggle.'),
        ),
    ]
