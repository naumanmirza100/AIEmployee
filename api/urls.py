from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter

from api.views import auth
from api.views import user
from api.views import project
from api.views import industry
from api.views import blog
from api.views import review
from api.views import contact
from api.views import consultation
from api.views import pricing
from api.views import payment
from api.views import referral
from api.views import analytics
from api.views import notification
from api.views import company
from api.views import company_auth
from api.views import career
from api.views import applicant
from api.views import quiz
from api.views import ai_predictor
from api.views import chatbot
from api.views import white_label
from api.views import company_jobs
from api.views import pm_agent
from api.views import company_dashboard
from api.views import recruitment_agent
from api.views import marketing_agent
from api.views.health import health_check

app_name = 'api'

urlpatterns = [
    # Health check
    re_path(r'^health/?$', health_check, name='health_check'),
    
    # Authentication endpoints
    re_path(r'^auth/register/?$', auth.register, name='register'),
    re_path(r'^auth/login/?$', auth.login, name='login'),
    re_path(r'^auth/refresh/?$', auth.refresh_token, name='refresh_token'),
    re_path(r'^auth/logout/?$', auth.logout, name='logout'),
    re_path(r'^auth/me/?$', auth.get_current_user, name='get_current_user'),
    
    # User endpoints
    re_path(r'^users/profile/?$', user.get_profile, name='get_profile'),  # GET
    re_path(r'^users/profile/update/?$', user.update_profile, name='update_profile'),  # PUT
    re_path(r'^users/dashboard/?$', user.get_dashboard_stats, name='get_dashboard_stats'),
    
    # Project endpoints
    re_path(r'^projects/?$', project.list_projects, name='list_projects'),
    re_path(r'^projects/(?P<id>\d+)/?$', project.get_project, name='get_project'),
    re_path(r'^projects/create/?$', project.create_project, name='create_project'),
    re_path(r'^projects/(?P<id>\d+)/update/?$', project.update_project, name='update_project'),
    re_path(r'^projects/(?P<id>\d+)/delete/?$', project.delete_project, name='delete_project'),
    re_path(r'^projects/(?P<id>\d+)/apply/?$', project.apply_to_project, name='apply_to_project'),
    re_path(r'^projects/(?P<id>\d+)/applications/?$', project.get_project_applications, name='get_project_applications'),
    
    # Industry endpoints
    re_path(r'^industries/?$', industry.list_industries, name='list_industries'),
    re_path(r'^industries/(?P<slug>[\w-]+)/?$', industry.get_industry_by_slug, name='get_industry_by_slug'),
    re_path(r'^industries/(?P<slug>[\w-]+)/challenges/?$', industry.get_industry_challenges, name='get_industry_challenges'),
    
    # Blog endpoints
    re_path(r'^blog/posts/?$', blog.list_blog_posts, name='list_blog_posts'),
    re_path(r'^blog/posts/(?P<slug>[\w-]+)/?$', blog.get_blog_post_by_slug, name='get_blog_post_by_slug'),
    re_path(r'^blog/categories/?$', blog.get_blog_categories, name='get_blog_categories'),
    re_path(r'^blog/tags/?$', blog.list_blog_tags, name='list_blog_tags'),
    
    # Review endpoints
    re_path(r'^reviews/?$', review.list_reviews, name='list_reviews'),
    re_path(r'^reviews/summary/?$', review.get_reviews_summary, name='get_reviews_summary'),
    
    # Contact endpoints
    re_path(r'^contact/?$', contact.submit_contact_form, name='submit_contact_form'),
    re_path(r'^contact/complaints/?$', contact.submit_complaint, name='submit_complaint'),
    re_path(r'^contact/admin/?$', contact.list_contact_messages, name='list_contact_messages'),
    re_path(r'^contact/admin/(?P<id>\d+)/?$', contact.get_contact_message, name='get_contact_message'),
    re_path(r'^contact/admin/(?P<id>\d+)/status/?$', contact.update_contact_message_status, name='update_contact_message_status'),
    
    # Consultation endpoints
    re_path(r'^consultations/?$', consultation.create_consultation, name='create_consultation'),  # POST
    re_path(r'^consultations/list/?$', consultation.list_consultations, name='list_consultations'),  # GET
    re_path(r'^consultations/(?P<id>\d+)/?$', consultation.get_consultation, name='get_consultation'),
    
    # Pricing endpoints
    re_path(r'^pricing/plans/?$', pricing.list_pricing_plans, name='list_pricing_plans'),
    re_path(r'^pricing/subscriptions/?$', pricing.list_subscriptions, name='list_subscriptions'),  # GET
    re_path(r'^pricing/subscriptions/?$', pricing.create_subscription, name='create_subscription'),  # POST
    
    # Payment endpoints
    re_path(r'^payments/?$', payment.process_payment, name='process_payment'),  # POST
    re_path(r'^payments/list/?$', payment.list_payments, name='list_payments'),  # GET
    re_path(r'^payments/invoices/?$', pricing.list_invoices, name='list_invoices'),  # GET (invoices)
    re_path(r'^payments/methods/?$', payment.list_payment_methods, name='list_payment_methods'),  # GET
    re_path(r'^payments/methods/?$', payment.add_payment_method, name='add_payment_method'),  # POST
    
    # Referral endpoints
    re_path(r'^referrals/my-code/?$', referral.get_my_referral_code, name='get_my_referral_code'),
    re_path(r'^referrals/use-code/?$', referral.use_referral_code, name='use_referral_code'),
    re_path(r'^referrals/my-referrals/?$', referral.get_my_referrals, name='get_my_referrals'),
    
    # Analytics endpoints
    re_path(r'^analytics/events/?$', analytics.log_analytics_event, name='log_analytics_event'),
    re_path(r'^analytics/page-views/?$', analytics.log_page_view, name='log_page_view'),
    
    # Notification endpoints
    re_path(r'^notifications/?$', notification.list_notifications, name='list_notifications'),
    re_path(r'^notifications/(?P<id>\d+)/read/?$', notification.mark_notification_read, name='mark_notification_read'),
    re_path(r'^notifications/read-all/?$', notification.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Company endpoints
    re_path(r'^companies/?$', company.list_companies, name='list_companies'),  # GET
    re_path(r'^companies/create/?$', company.create_company, name='create_company'),  # POST
    re_path(r'^companies/(?P<companyId>\d+)/tokens/?$', company.get_company_tokens, name='get_company_tokens'),  # GET
    re_path(r'^companies/(?P<companyId>\d+)/tokens/generate/?$', company.generate_company_token, name='generate_company_token'),  # POST
    
    # Company Auth endpoints
    re_path(r'^company/verify-token/?$', company_auth.verify_registration_token, name='verify_registration_token'),
    re_path(r'^company/register/?$', company_auth.register_company_user, name='register_company_user'),
    re_path(r'^company/login/?$', company_auth.login_company_user, name='login_company_user'),
    
    # Career endpoints
    re_path(r'^careers/positions/?$', career.list_job_positions, name='list_job_positions'),
    re_path(r'^careers/applications/?$', career.submit_career_application, name='submit_career_application'),  # POST
    re_path(r'^careers/admin/applications/?$', career.list_career_applications, name='list_career_applications'),  # GET (admin)
    re_path(r'^careers/admin/applications/(?P<id>\d+)/?$', career.get_career_application, name='get_career_application'),  # GET (admin)
    re_path(r'^careers/admin/applications/(?P<id>\d+)/status/?$', career.update_career_application_status, name='update_career_application_status'),  # PATCH (admin)
    
    # Applicant endpoints
    re_path(r'^applicant/status/?$', applicant.get_application_status, name='get_application_status'),
    
    # Quiz endpoints
    re_path(r'^quiz/responses/?$', quiz.submit_quiz_response, name='submit_quiz_response'),
    
    # AI Predictor endpoints
    re_path(r'^ai-predictor/?$', ai_predictor.submit_ai_predictor, name='submit_ai_predictor'),  # POST
    re_path(r'^ai-predictor/admin/?$', ai_predictor.list_ai_predictions, name='list_ai_predictions'),  # GET (admin)
    re_path(r'^ai-predictor/admin/(?P<id>\d+)/?$', ai_predictor.get_ai_prediction, name='get_ai_prediction'),  # GET (admin)

    # Project Manager Dashboard endpoint
    re_path(r'^project-manager/dashboard/?$', company_dashboard.project_manager_dashboard, name='pm_dashboard'),
    # Company User Projects endpoint
    re_path(r'^company/projects/?$', company_dashboard.get_company_user_projects, name='get_company_user_projects'),

    # Project Manager AI Agent endpoints (token-auth friendly)
    re_path(r'^project-manager/ai/project-pilot/?$', pm_agent.project_pilot, name='pm_project_pilot'),
    re_path(r'^project-manager/ai/task-prioritization/?$', pm_agent.task_prioritization, name='pm_task_prioritization'),
    re_path(r'^project-manager/ai/generate-subtasks/?$', pm_agent.generate_subtasks, name='pm_generate_subtasks'),
    re_path(r'^project-manager/ai/timeline-gantt/?$', pm_agent.timeline_gantt, name='pm_timeline_gantt'),
    re_path(r'^project-manager/ai/knowledge-qa/?$', pm_agent.knowledge_qa, name='pm_knowledge_qa'),
    
    # Manual Project and Task Creation endpoints (Company User)
    re_path(r'^project-manager/projects/create/?$', pm_agent.create_project_manual, name='pm_create_project_manual'),
    re_path(r'^project-manager/tasks/create/?$', pm_agent.create_task_manual, name='pm_create_task_manual'),
    re_path(r'^project-manager/users/?$', pm_agent.get_available_users, name='pm_get_available_users'),
    
    # Chatbot endpoints
    re_path(r'^chatbot/conversations/?$', chatbot.create_conversation, name='create_conversation'),  # POST
    re_path(r'^chatbot/messages/?$', chatbot.send_chatbot_message, name='send_chatbot_message'),  # POST
    re_path(r'^chatbot/conversations/(?P<id>\d+)/messages/?$', chatbot.get_conversation_messages, name='get_conversation_messages'),
    
    # White Label endpoints
    re_path(r'^white-label/products/?$', white_label.list_white_label_products, name='list_white_label_products'),
    re_path(r'^white-label/products/(?P<id>\d+)/?$', white_label.get_white_label_product, name='get_white_label_product'),
    re_path(r'^white-label/categories/?$', white_label.get_white_label_categories, name='get_white_label_categories'),
    
    # Company Jobs endpoints
    re_path(r'^company/jobs/?$', company_jobs.create_company_job, name='create_company_job'),  # POST
    re_path(r'^company/jobs/list/?$', company_jobs.list_company_jobs, name='list_company_jobs'),  # GET
    re_path(r'^company/jobs/(?P<id>\d+)/?$', company_jobs.update_company_job, name='update_company_job'),  # PUT
    re_path(r'^company/jobs/(?P<jobId>\d+)/applications/?$', company_jobs.get_company_job_applications, name='get_company_job_applications'),
    re_path(r'^company/applications/(?P<id>\d+)/status/?$', company_jobs.update_company_application_status, name='update_company_application_status'),
    
    # Recruitment Agent endpoints (Company User)
    re_path(r'^recruitment/process-cvs/?$', recruitment_agent.process_cvs, name='recruitment_process_cvs'),  # POST
    re_path(r'^recruitment/job-descriptions/?$', recruitment_agent.list_job_descriptions, name='recruitment_list_job_descriptions'),  # GET
    re_path(r'^recruitment/job-descriptions/create/?$', recruitment_agent.create_job_description, name='recruitment_create_job_description'),  # POST
    re_path(r'^recruitment/job-descriptions/(?P<job_description_id>\d+)/update/?$', recruitment_agent.update_job_description, name='recruitment_update_job_description'),  # PUT/PATCH
    re_path(r'^recruitment/job-descriptions/(?P<job_description_id>\d+)/delete/?$', recruitment_agent.delete_job_description, name='recruitment_delete_job_description'),  # DELETE
    re_path(r'^recruitment/interviews/?$', recruitment_agent.list_interviews, name='recruitment_list_interviews'),  # GET
    re_path(r'^recruitment/interviews/schedule/?$', recruitment_agent.schedule_interview, name='recruitment_schedule_interview'),  # POST
    re_path(r'^recruitment/interviews/(?P<interview_id>\d+)/?$', recruitment_agent.get_interview_details, name='recruitment_get_interview_details'),  # GET
    re_path(r'^recruitment/cv-records/?$', recruitment_agent.list_cv_records, name='recruitment_list_cv_records'),  # GET
    re_path(r'^recruitment/settings/email/?$', recruitment_agent.email_settings, name='recruitment_email_settings'),  # GET/POST
    re_path(r'^recruitment/settings/interview/?$', recruitment_agent.interview_settings, name='recruitment_interview_settings'),  # GET/POST
    
    # Marketing Agent endpoints (Company User)
    re_path(r'^marketing/dashboard/?$', marketing_agent.marketing_dashboard, name='marketing_dashboard'),  # GET
    re_path(r'^marketing/campaigns/?$', marketing_agent.list_campaigns, name='marketing_list_campaigns'),  # GET
    re_path(r'^marketing/campaigns/create/?$', marketing_agent.create_campaign, name='marketing_create_campaign'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/?$', marketing_agent.get_campaign, name='marketing_get_campaign'),  # GET
    re_path(r'^marketing/qa/?$', marketing_agent.marketing_qa, name='marketing_qa'),  # POST
    re_path(r'^marketing/market-research/?$', marketing_agent.market_research, name='marketing_market_research'),  # POST
    re_path(r'^marketing/outreach-campaign/?$', marketing_agent.outreach_campaign, name='marketing_outreach_campaign'),  # POST
    re_path(r'^marketing/document-authoring/?$', marketing_agent.document_authoring, name='marketing_document_authoring'),  # POST
    re_path(r'^marketing/notifications/?$', marketing_agent.get_notifications, name='marketing_get_notifications'),  # GET
]
