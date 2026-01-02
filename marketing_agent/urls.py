from django.urls import path
from . import views
from . import views_email_templates
from . import views_email_accounts
from . import views_email_tracking
from . import views_sequences
from . import views_email_status
from . import views_sequence_sender

urlpatterns = [
    path('', views.marketing_dashboard, name='marketing_dashboard'),
    path('agents/', views.marketing_agents_test, name='marketing_agents_test'),
    path('api/qa/', views.test_marketing_qa, name='test_marketing_qa'),
    path('api/market-research/', views.test_market_research, name='test_market_research'),
    path('api/outreach-campaign/', views.test_outreach_campaign, name='test_outreach_campaign'),
    # Campaign details endpoint
    path('api/campaign/<int:campaign_id>/', views.get_campaign_details, name='get_campaign_details'),
    # Campaign management
    path('campaigns/', views.campaigns_list, name='campaigns_list'),
    path('campaigns/<int:campaign_id>/', views.campaign_detail, name='campaign_detail'),
    path('campaigns/<int:campaign_id>/edit/', views.campaign_edit, name='campaign_edit'),
    path('campaigns/<int:campaign_id>/stop/', views.campaign_stop, name='campaign_stop'),
    path('campaigns/<int:campaign_id>/delete/', views.campaign_delete, name='campaign_delete'),
    # Lead management
    path('campaigns/<int:campaign_id>/leads/upload/', views.upload_leads, name='upload_leads'),
    path('campaigns/<int:campaign_id>/leads/add/', views.add_lead, name='add_lead'),
    path('campaigns/<int:campaign_id>/leads/<int:lead_id>/edit/', views.edit_lead, name='edit_lead'),
    path('campaigns/<int:campaign_id>/leads/<int:lead_id>/delete/', views.delete_lead, name='delete_lead'),
    path('campaigns/<int:campaign_id>/leads/<int:lead_id>/mark-replied/', views.mark_contact_replied, name='mark_contact_replied'),
    path('campaigns/<int:campaign_id>/leads/export/', views.export_leads, name='export_leads'),
    # Email template management
    path('campaigns/<int:campaign_id>/email-templates/', views_email_templates.email_templates_list, name='email_templates_list'),
    path('campaigns/<int:campaign_id>/email-templates/<int:template_id>/', views_email_templates.email_template_detail, name='email_template_detail'),
    path('campaigns/<int:campaign_id>/email-templates/<int:template_id>/test/', views_email_templates.test_email_template, name='test_email_template'),
    path('campaigns/<int:campaign_id>/email-sequences/', views_email_templates.email_sequences_list, name='email_sequences_list'),
    # Sequence management (new dedicated page)
    path('campaigns/<int:campaign_id>/sequences/', views_sequences.sequence_management, name='sequence_management'),
    path('campaigns/<int:campaign_id>/sequences/create/', views_sequences.create_sequence, name='create_sequence'),
    path('campaigns/<int:campaign_id>/sequences/<int:sequence_id>/', views_sequences.update_sequence, name='update_sequence'),
    path('campaigns/<int:campaign_id>/sequences/<int:sequence_id>/delete/', views_sequences.delete_sequence, name='delete_sequence'),
    path('campaigns/<int:campaign_id>/sequences/<int:sequence_id>/details/', views_sequences.get_sequence_details, name='get_sequence_details'),
    # Email account management
    path('email-accounts/', views_email_accounts.email_accounts_list, name='email_accounts_list'),
    path('email-accounts/<int:account_id>/', views_email_accounts.email_account_detail, name='email_account_detail'),
    path('email-accounts/<int:account_id>/test/', views_email_accounts.test_email_account, name='test_email_account'),
    # Email tracking
    path('track/email/<str:tracking_token>/open/', views_email_tracking.track_email_open, name='track_email_open'),
    path('track/email/<str:tracking_token>/click/', views_email_tracking.track_email_click, name='track_email_click'),
    # Email sending status
    path('campaigns/<int:campaign_id>/email-status/', views_email_status.email_sending_status, name='email_sending_status'),
    path('campaigns/<int:campaign_id>/email-status/api/', views_email_status.email_status_api, name='email_status_api'),
    # Manual sequence email trigger
    path('campaigns/<int:campaign_id>/trigger-sequence-emails/', views_sequence_sender.trigger_sequence_emails, name='trigger_sequence_emails'),
]


