"""
Add Stripe subscription fields for recurring billing.

- Company: stripe_customer_id
- AgentPlan: billing_interval, stripe_product_id, stripe_price_id
- CompanyModulePurchase: stripe_subscription_id, current_period_start,
  current_period_end, cancel_at_period_end, is_complimentary, billing_interval,
  past_due status choice
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0095_agentplan'),
    ]

    operations = [
        # Company: Stripe Customer ID
        migrations.AddField(
            model_name='company',
            name='stripe_customer_id',
            field=models.CharField(
                blank=True, db_index=True, help_text='Stripe Customer ID for this company',
                max_length=255, null=True,
            ),
        ),

        # AgentPlan: billing interval + Stripe product/price references
        migrations.AddField(
            model_name='agentplan',
            name='billing_interval',
            field=models.CharField(
                choices=[('month', 'Monthly'), ('year', 'Yearly')],
                default='month', help_text='Stripe billing interval for recurring subscriptions.',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='agentplan',
            name='stripe_product_id',
            field=models.CharField(
                blank=True, help_text='Stripe Product ID (auto-synced)',
                max_length=255, null=True,
            ),
        ),
        migrations.AddField(
            model_name='agentplan',
            name='stripe_price_id',
            field=models.CharField(
                blank=True, help_text='Stripe Price ID (auto-synced)',
                max_length=255, null=True,
            ),
        ),

        # CompanyModulePurchase: Stripe subscription fields
        migrations.AddField(
            model_name='companymodulepurchase',
            name='stripe_subscription_id',
            field=models.CharField(
                blank=True, help_text='Stripe Subscription ID',
                max_length=255, null=True, unique=True,
            ),
        ),
        migrations.AddField(
            model_name='companymodulepurchase',
            name='current_period_start',
            field=models.DateTimeField(
                blank=True, help_text='Current billing period start (from Stripe)',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='companymodulepurchase',
            name='current_period_end',
            field=models.DateTimeField(
                blank=True,
                help_text='Current billing period end (from Stripe). Source of truth for Stripe subscriptions.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='companymodulepurchase',
            name='cancel_at_period_end',
            field=models.BooleanField(
                default=False,
                help_text='True if user cancelled; subscription active until period end',
            ),
        ),
        migrations.AddField(
            model_name='companymodulepurchase',
            name='is_complimentary',
            field=models.BooleanField(
                default=False,
                help_text='True if admin granted free access (bypasses Stripe lifecycle)',
            ),
        ),
        migrations.AddField(
            model_name='companymodulepurchase',
            name='billing_interval',
            field=models.CharField(
                blank=True,
                choices=[('month', 'Monthly'), ('year', 'Yearly')],
                help_text='Billing interval for Stripe subscriptions',
                max_length=10, null=True,
            ),
        ),

        # Add 'past_due' to status choices (Django stores choices as text,
        # so this only affects validation — existing rows are untouched).
        migrations.AlterField(
            model_name='companymodulepurchase',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('past_due', 'Past Due'),
                    ('cancelled', 'Cancelled'),
                    ('expired', 'Expired'),
                    ('trial', 'Trial'),
                ],
                default='active', max_length=20,
            ),
        ),
    ]
