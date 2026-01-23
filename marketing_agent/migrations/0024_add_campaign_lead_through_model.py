# Generated migration to add CampaignLead through model with explicit table name
# Note: The table ppp_marketingagent_campaign_leads already exists (renamed in migration 0022)
# This migration creates the model to map to the existing table

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0023_remove_budget_revenue_fields'),
    ]

    operations = [
        # Create the CampaignLead through model (maps to existing table)
        # Use SeparateDatabaseAndState because the table already exists
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='CampaignLead',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marketing_agent.campaign')),
                        ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marketing_agent.lead')),
                    ],
                    options={
                        'db_table': 'ppp_marketingagent_campaign_leads',
                    },
                ),
                migrations.AlterUniqueTogether(
                    name='campaignlead',
                    unique_together={('campaign', 'lead')},
                ),
                migrations.AlterField(
                    model_name='campaign',
                    name='leads',
                    field=models.ManyToManyField(blank=True, related_name='campaigns', through='marketing_agent.CampaignLead', to='marketing_agent.lead'),
                ),
            ],
            database_operations=[
                # Do nothing - table already exists from migration 0022
            ],
        ),
    ]
