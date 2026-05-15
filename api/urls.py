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
from api.views import company_users
from api.views import user_tasks
from api.views import company_user_tasks
from api.views import career
from api.views import applicant
from api.views import quiz
from api.views import ai_predictor
from api.views import chatbot
from api.views import white_label
from api.views import company_jobs
from api.views import pm_agent
from api.views import company_dashboard
from api.views import company_projects_tasks
from api.views import user_project_manager
from api.views import recruitment_agent
from api.views import marketing_agent
from api.views import reply_draft_agent as reply_draft_api
from api.views import frontline_agent
from api.views import hr_agent
from api.views import module_purchase
from api.views import company_api_keys
from api.views import admin_api_keys
from api.views import operations_agent
from api.views import ai_sdr_agent as sdr_api
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
    
    # User Tasks endpoints (for regular users to manage their tasks)
    re_path(r'^user/tasks/?$', user_tasks.get_my_tasks, name='get_my_tasks'),  # GET
    re_path(r'^user/projects/?$', user_tasks.get_my_projects, name='get_my_projects'),  # GET
    re_path(r'^user/tasks/(?P<taskId>\d+)/status/?$', user_tasks.update_task_status, name='update_task_status'),  # PATCH
    re_path(r'^user/tasks/(?P<taskId>\d+)/progress/?$', user_tasks.update_task_progress, name='update_task_progress'),  # PATCH
    
    # Project Manager endpoints (for users with project_manager role)
    re_path(r'^user/project-manager/projects-tasks/?$', user_project_manager.get_project_manager_projects_tasks, name='get_project_manager_projects_tasks'),  # GET
    re_path(r'^user/project-manager/projects/?$', user_project_manager.get_project_manager_projects, name='get_project_manager_projects'),  # GET
    re_path(r'^user/project-manager/projects/create/?$', user_project_manager.create_project_manager_project, name='create_project_manager_project'),  # POST
    re_path(r'^user/project-manager/projects/(?P<project_id>\d+)/update/?$', user_project_manager.update_project_manager_project, name='update_project_manager_project'),  # PUT/PATCH
    re_path(r'^user/project-manager/tasks/create/?$', user_project_manager.create_project_manager_task, name='create_project_manager_task'),  # POST
    re_path(r'^user/project-manager/tasks/(?P<task_id>\d+)/update/?$', user_project_manager.update_project_manager_task, name='update_project_manager_task'),  # PUT/PATCH
    re_path(r'^user/project-manager/company-users/?$', user_project_manager.get_company_users_for_pm, name='get_company_users_for_pm'),  # GET
    
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

    # Meeting endpoints for project users (Django Users)
    re_path(r'^meetings/?$', notification.meeting_list_for_user, name='user_meeting_list'),
    re_path(r'^meetings/(?P<meeting_id>\d+)/respond/?$', notification.meeting_respond, name='user_meeting_respond'),
    
    # Company endpoints
    re_path(r'^companies/?$', company.list_companies, name='list_companies'),  # GET
    re_path(r'^companies/create/?$', company.create_company, name='create_company'),  # POST
    re_path(r'^companies/(?P<companyId>\d+)/tokens/?$', company.get_company_tokens, name='get_company_tokens'),  # GET
    re_path(r'^companies/(?P<companyId>\d+)/tokens/generate/?$', company.generate_company_token, name='generate_company_token'),  # POST

    # Admin - Company AI Agents Management
    re_path(r'^admin/company-agents/?$', company.list_company_agents, name='list_company_agents'),  # GET
    re_path(r'^admin/company-agents/(?P<purchaseId>\d+)/toggle-status/?$', company.toggle_company_agent_status, name='toggle_company_agent_status'),  # PATCH

    # Company User Management endpoints (for company users to manage regular users)
    re_path(r'^company/users/create/?$', company_users.create_user, name='company_create_user'),  # POST
    re_path(r'^company/users/?$', company_users.list_users, name='company_list_users'),  # GET
    re_path(r'^company/users/(?P<userId>\d+)/?$', company_users.get_user, name='company_get_user'),  # GET
    re_path(r'^company/users/(?P<userId>\d+)/update/?$', company_users.update_user, name='company_update_user'),  # PUT/PATCH
    re_path(r'^company/users/(?P<userId>\d+)/delete/?$', company_users.delete_user, name='company_delete_user'),  # DELETE
    re_path(r'^company/users/(?P<userId>\d+)/reactivate/?$', company_users.reactivate_user, name='company_reactivate_user'),  # POST
    re_path(r'^company/users/tasks/?$', company_user_tasks.get_all_users_tasks, name='company_get_all_users_tasks'),  # GET
    
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
    re_path(r'^company/projects/list/?$', company_dashboard.get_company_user_projects_list, name='get_company_user_projects_list'),
    re_path(r'^company/projects/?$', company_dashboard.get_company_user_projects, name='get_company_user_projects'),
    re_path(r'^company/projects/(?P<project_id>\d+)/update/?$', company_projects_tasks.update_company_project, name='update_company_project'),
    
    # Company User Tasks endpoints
    re_path(r'^company/tasks/(?P<task_id>\d+)/update/?$', company_projects_tasks.update_company_task, name='update_company_task'),
    re_path(r'^company/users/for-assignment/?$', company_projects_tasks.get_company_users_for_assignment, name='get_company_users_for_assignment'),

    # Project Manager AI Agent endpoints (token-auth friendly)
    re_path(r'^project-manager/ai/project-pilot/?$', pm_agent.project_pilot, name='pm_project_pilot'),
    re_path(r'^project-manager/ai/project-pilot/upload-file/?$', pm_agent.project_pilot_from_file, name='pm_project_pilot_from_file'),
    re_path(r'^project-manager/ai/task-prioritization/?$', pm_agent.task_prioritization, name='pm_task_prioritization'),
    re_path(r'^project-manager/ai/generate-subtasks/?$', pm_agent.generate_subtasks, name='pm_generate_subtasks'),
    re_path(r'^project-manager/ai/timeline-gantt/?$', pm_agent.timeline_gantt, name='pm_timeline_gantt'),
    re_path(r'^project-manager/ai/knowledge-qa/?$', pm_agent.knowledge_qa, name='pm_knowledge_qa'),
    re_path(r'^project-manager/ai/generate-graph/?$', pm_agent.pm_generate_graph, name='pm_generate_graph'),
    re_path(r'^project-manager/ai/knowledge-qa/chats/?$', pm_agent.list_knowledge_qa_chats, name='pm_knowledge_qa_chats_list'),
    re_path(r'^project-manager/ai/knowledge-qa/chats/create/?$', pm_agent.create_knowledge_qa_chat, name='pm_knowledge_qa_chats_create'),
    re_path(r'^project-manager/ai/knowledge-qa/chats/(?P<chat_id>\d+)/update/?$', pm_agent.update_knowledge_qa_chat, name='pm_knowledge_qa_chats_update'),
    re_path(r'^project-manager/ai/knowledge-qa/chats/(?P<chat_id>\d+)/delete/?$', pm_agent.delete_knowledge_qa_chat, name='pm_knowledge_qa_chats_delete'),
    re_path(r'^project-manager/ai/project-pilot/chats/?$', pm_agent.list_project_pilot_chats, name='pm_project_pilot_chats_list'),
    re_path(r'^project-manager/ai/project-pilot/chats/create/?$', pm_agent.create_project_pilot_chat, name='pm_project_pilot_chats_create'),
    re_path(r'^project-manager/ai/project-pilot/chats/(?P<chat_id>\d+)/update/?$', pm_agent.update_project_pilot_chat, name='pm_project_pilot_chats_update'),
    re_path(r'^project-manager/ai/project-pilot/chats/(?P<chat_id>\d+)/delete/?$', pm_agent.delete_project_pilot_chat, name='pm_project_pilot_chats_delete'),
    
    # Manual Project and Task Creation endpoints (Company User)
    re_path(r'^project-manager/projects/create/?$', pm_agent.create_project_manual, name='pm_create_project_manual'),
    re_path(r'^project-manager/tasks/create/?$', pm_agent.create_task_manual, name='pm_create_task_manual'),
    re_path(r'^project-manager/users/?$', pm_agent.get_available_users, name='pm_get_available_users'),
    # New PM Agent endpoints
    re_path(r'^project-manager/ai/daily-standup/?$', pm_agent.daily_standup, name='pm_daily_standup'),
    re_path(r'^project-manager/ai/project-health/?$', pm_agent.project_health_score, name='pm_project_health'),
    re_path(r'^project-manager/ai/status-report/?$', pm_agent.project_status_report, name='pm_status_report'),
    re_path(r'^project-manager/ai/meeting-notes/?$', pm_agent.meeting_notes, name='pm_meeting_notes'),
    re_path(r'^project-manager/ai/workflow-suggest/?$', pm_agent.workflow_suggest, name='pm_workflow_suggest'),
    re_path(r'^project-manager/ai/calendar-schedule/?$', pm_agent.calendar_schedule, name='pm_calendar_schedule'),
    re_path(r'^project-manager/ai/notifications/scan/?$', pm_agent.scan_notifications, name='pm_scan_notifications'),
    re_path(r'^project-manager/ai/notifications/?$', pm_agent.list_notifications, name='pm_list_notifications'),
    re_path(r'^project-manager/ai/notifications/read/?$', pm_agent.mark_notifications_read, name='pm_mark_notifications_read'),
    re_path(r'^project-manager/ai/team-performance/?$', pm_agent.team_performance, name='pm_team_performance'),
    re_path(r'^project-manager/ai/time-estimation/?$', pm_agent.time_estimation, name='pm_time_estimation'),

    # Meeting Scheduler endpoints
    re_path(r'^project-manager/ai/meetings/schedule/?$', pm_agent.meeting_schedule, name='pm_meeting_schedule'),
    re_path(r'^project-manager/ai/meetings/respond/?$', pm_agent.meeting_respond, name='pm_meeting_respond'),
    re_path(r'^project-manager/ai/meetings/?$', pm_agent.meeting_list, name='pm_meeting_list'),
    # Meeting Scheduler Chat CRUD
    re_path(r'^project-manager/ai/meeting-scheduler/chats/?$', pm_agent.list_meeting_scheduler_chats, name='pm_meeting_scheduler_chats_list'),
    re_path(r'^project-manager/ai/meeting-scheduler/chats/create/?$', pm_agent.create_meeting_scheduler_chat, name='pm_meeting_scheduler_chats_create'),
    re_path(r'^project-manager/ai/meeting-scheduler/chats/(?P<chat_id>\d+)/update/?$', pm_agent.update_meeting_scheduler_chat, name='pm_meeting_scheduler_chats_update'),
    re_path(r'^project-manager/ai/meeting-scheduler/chats/(?P<chat_id>\d+)/delete/?$', pm_agent.delete_meeting_scheduler_chat, name='pm_meeting_scheduler_chats_delete'),
    re_path(r'^project-manager/ai/audit-logs/?$', pm_agent.list_audit_logs, name='pm_audit_logs'),
    re_path(r'^project-manager/health/?$', pm_agent.pm_health_check, name='pm_health_check'),

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
    re_path(r'^recruitment/process-cvs/?$', recruitment_agent.process_cvs, name='recruitment_process_cvs'),  # POST (full pipeline)
    re_path(r'^recruitment/agents/cv/parse/?$', recruitment_agent.api_cv_parse, name='recruitment_api_cv_parse'),  # POST
    re_path(r'^recruitment/agents/cv/summarize/?$', recruitment_agent.api_cv_summarize, name='recruitment_api_cv_summarize'),  # POST
    re_path(r'^recruitment/agents/cv/enrich/?$', recruitment_agent.api_cv_enrich, name='recruitment_api_cv_enrich'),  # POST
    re_path(r'^recruitment/agents/cv/qualify/?$', recruitment_agent.api_cv_qualify, name='recruitment_api_cv_qualify'),  # POST
    re_path(r'^recruitment/agents/job-description/parse/?$', recruitment_agent.api_job_description_parse, name='recruitment_api_job_description_parse'),  # POST
    re_path(r'^recruitment/ai/suggest-interview-questions/?$', recruitment_agent.suggest_interview_questions, name='recruitment_suggest_interview_questions'),  # POST
    re_path(r'^recruitment/qa/?$', recruitment_agent.recruitment_qa, name='recruitment_qa'),  # POST
    re_path(r'^recruitment/qa/chats/?$', recruitment_agent.list_qa_chats, name='recruitment_qa_chats_list'),  # GET
    re_path(r'^recruitment/qa/chats/create/?$', recruitment_agent.create_qa_chat, name='recruitment_qa_chats_create'),  # POST
    re_path(r'^recruitment/qa/chats/(?P<chat_id>\d+)/update/?$', recruitment_agent.update_qa_chat, name='recruitment_qa_chats_update'),  # PATCH/PUT
    re_path(r'^recruitment/qa/chats/(?P<chat_id>\d+)/delete/?$', recruitment_agent.delete_qa_chat, name='recruitment_qa_chats_delete'),  # DELETE
    re_path(r'^recruitment/job-descriptions/?$', recruitment_agent.list_job_descriptions, name='recruitment_list_job_descriptions'),  # GET
    re_path(r'^recruitment/job-descriptions/generate/?$', recruitment_agent.generate_job_description, name='recruitment_generate_job_description'),  # POST
    re_path(r'^recruitment/job-descriptions/create/?$', recruitment_agent.create_job_description, name='recruitment_create_job_description'),  # POST
    re_path(r'^recruitment/job-descriptions/(?P<job_description_id>\d+)/update/?$', recruitment_agent.update_job_description, name='recruitment_update_job_description'),  # PUT/PATCH
    re_path(r'^recruitment/job-descriptions/(?P<job_description_id>\d+)/delete/?$', recruitment_agent.delete_job_description, name='recruitment_delete_job_description'),  # DELETE
    re_path(r'^recruitment/interviews/?$', recruitment_agent.list_interviews, name='recruitment_list_interviews'),  # GET
    re_path(r'^recruitment/interviews/schedule/?$', recruitment_agent.schedule_interview, name='recruitment_schedule_interview'),  # POST
    re_path(r'^recruitment/interviews/(?P<interview_id>\d+)/?$', recruitment_agent.get_interview_details, name='recruitment_get_interview_details'),  # GET
    re_path(r'^recruitment/interviews/(?P<interview_id>\d+)/update/?$', recruitment_agent.update_interview, name='recruitment_update_interview'),  # PATCH/PUT
    re_path(r'^recruitment/interviews/(?P<interview_id>\d+)/reschedule-slots/?$', recruitment_agent.get_reschedule_slots, name='recruitment_get_reschedule_slots'),  # GET
    re_path(r'^recruitment/interviews/(?P<interview_id>\d+)/reschedule/?$', recruitment_agent.reschedule_interview, name='recruitment_reschedule_interview'),  # POST
    re_path(r'^recruitment/cv-records/?$', recruitment_agent.list_cv_records, name='recruitment_list_cv_records'),  # GET
    re_path(r'^recruitment/cv-records/bulk-update/?$', recruitment_agent.bulk_update_cv_records, name='recruitment_bulk_update_cv_records'),  # POST
    re_path(r'^recruitment/settings/email/?$', recruitment_agent.email_settings, name='recruitment_email_settings'),  # GET/POST
    re_path(r'^recruitment/settings/interview/?$', recruitment_agent.interview_settings, name='recruitment_interview_settings'),  # GET/POST
    re_path(r'^recruitment/settings/qualification/?$', recruitment_agent.qualification_settings, name='recruitment_qualification_settings'),  # GET/POST
    re_path(r'^recruitment/analytics/?$', recruitment_agent.recruitment_analytics, name='recruitment_analytics'),  # GET
    
    # AI Graph Generator endpoints
    re_path(r'^recruitment/ai/generate-graph/?$', recruitment_agent.api_generate_graph, name='recruitment_generate_graph'),  # POST
    re_path(r'^recruitment/ai/graph-prompts/?$', recruitment_agent.api_get_saved_prompts, name='recruitment_get_saved_prompts'),  # GET
    re_path(r'^recruitment/ai/graph-prompts/save/?$', recruitment_agent.api_save_prompt, name='recruitment_save_prompt'),  # POST
    re_path(r'^recruitment/ai/graph-prompts/(?P<prompt_id>\d+)/delete/?$', recruitment_agent.api_delete_prompt, name='recruitment_delete_prompt'),  # DELETE
    re_path(r'^recruitment/ai/graph-prompts/(?P<prompt_id>\d+)/favorite/?$', recruitment_agent.api_toggle_prompt_favorite, name='recruitment_toggle_prompt_favorite'),  # PATCH
    re_path(r'^recruitment/ai/graph-prompts/(?P<prompt_id>\d+)/dashboard/?$', recruitment_agent.api_toggle_prompt_dashboard, name='recruitment_toggle_prompt_dashboard'),  # PATCH

    # Marketing AI Graph endpoints (Company User)
    re_path(r'^marketing/ai/generate-graph/?$', marketing_agent.api_marketing_generate_graph, name='marketing_generate_graph'),  # POST
    re_path(r'^marketing/ai/graph-prompts/?$', marketing_agent.api_marketing_get_saved_prompts, name='marketing_get_saved_prompts'),  # GET
    re_path(r'^marketing/ai/graph-prompts/save/?$', marketing_agent.api_marketing_save_prompt, name='marketing_save_prompt'),  # POST
    re_path(r'^marketing/ai/graph-prompts/(?P<prompt_id>\d+)/delete/?$', marketing_agent.api_marketing_delete_prompt, name='marketing_delete_prompt'),  # DELETE
    re_path(r'^marketing/ai/graph-prompts/(?P<prompt_id>\d+)/favorite/?$', marketing_agent.api_marketing_toggle_prompt_favorite, name='marketing_toggle_prompt_favorite'),  # PATCH
    re_path(r'^marketing/ai/graph-prompts/(?P<prompt_id>\d+)/dashboard/?$', marketing_agent.api_marketing_toggle_prompt_dashboard, name='marketing_toggle_prompt_dashboard'),  # PATCH

    # Marketing Agent endpoints (Company User)
    re_path(r'^marketing/dashboard/?$', marketing_agent.marketing_dashboard, name='marketing_dashboard'),  # GET
    re_path(r'^marketing/campaigns/?$', marketing_agent.list_campaigns, name='marketing_list_campaigns'),  # GET
    re_path(r'^marketing/campaigns/create/?$', marketing_agent.create_campaign, name='marketing_create_campaign'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/?$', marketing_agent.get_campaign, name='marketing_get_campaign'),  # GET
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/update/?$', marketing_agent.update_campaign, name='marketing_update_campaign'),  # PUT/PATCH
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/stop/?$', marketing_agent.campaign_stop, name='marketing_campaign_stop'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/delete/?$', marketing_agent.campaign_delete, name='marketing_campaign_delete'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/?$', marketing_agent.list_campaign_leads, name='marketing_list_campaign_leads'),  # GET
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/add/?$', marketing_agent.add_campaign_lead, name='marketing_add_campaign_lead'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/upload/?$', marketing_agent.upload_campaign_leads, name='marketing_upload_campaign_leads'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/export/?$', marketing_agent.export_campaign_leads, name='marketing_export_campaign_leads'),  # GET
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/(?P<lead_id>\d+)/?$', marketing_agent.update_campaign_lead, name='marketing_update_campaign_lead'),  # PUT/PATCH
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/leads/(?P<lead_id>\d+)/delete/?$', marketing_agent.delete_campaign_lead, name='marketing_delete_campaign_lead'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/sequences/?$', marketing_agent.list_sequences, name='marketing_list_sequences'),  # GET
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/sequences/create/?$', marketing_agent.create_sequence, name='marketing_create_sequence'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/sequences/(?P<sequence_id>\d+)/?$', marketing_agent.get_sequence_details, name='marketing_get_sequence_details'),  # GET
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/sequences/(?P<sequence_id>\d+)/update/?$', marketing_agent.update_sequence, name='marketing_update_sequence'),  # PUT/PATCH
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/sequences/(?P<sequence_id>\d+)/delete/?$', marketing_agent.delete_sequence, name='marketing_delete_sequence'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/templates/?$', marketing_agent.create_template, name='marketing_create_template'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/templates/(?P<template_id>\d+)/update/?$', marketing_agent.update_template, name='marketing_update_template'),  # PUT/PATCH
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/templates/(?P<template_id>\d+)/delete/?$', marketing_agent.delete_template, name='marketing_delete_template'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/templates/(?P<template_id>\d+)/test/?$', marketing_agent.test_email_template, name='marketing_test_email_template'),  # POST
    re_path(r'^marketing/campaigns/(?P<campaign_id>\d+)/email-status/full/?$', marketing_agent.get_email_status_full, name='marketing_email_status_full'),  # GET
    re_path(r'^marketing/email-accounts/?$', marketing_agent.list_email_accounts, name='marketing_list_email_accounts'),  # GET
    re_path(r'^marketing/email-accounts/create/?$', marketing_agent.create_email_account, name='marketing_create_email_account'),  # POST
    re_path(r'^marketing/email-accounts/(?P<account_id>\d+)/?$', marketing_agent.get_email_account, name='marketing_get_email_account'),  # GET
    re_path(r'^marketing/email-accounts/(?P<account_id>\d+)/update/?$', marketing_agent.update_email_account, name='marketing_update_email_account'),  # PUT/PATCH
    re_path(r'^marketing/email-accounts/(?P<account_id>\d+)/delete/?$', marketing_agent.delete_email_account, name='marketing_delete_email_account'),  # POST
    re_path(r'^marketing/email-accounts/(?P<account_id>\d+)/test/?$', marketing_agent.test_email_account, name='marketing_test_email_account'),  # POST
    re_path(r'^marketing/qa/?$', marketing_agent.marketing_qa, name='marketing_qa'),  # POST
    re_path(r'^marketing/qa/chats/?$', marketing_agent.list_qa_chats, name='marketing_qa_chats_list'),  # GET
    re_path(r'^marketing/qa/chats/create/?$', marketing_agent.create_qa_chat, name='marketing_qa_chats_create'),  # POST
    re_path(r'^marketing/qa/chats/(?P<chat_id>\d+)/update/?$', marketing_agent.update_qa_chat, name='marketing_qa_chats_update'),  # PATCH/PUT
    re_path(r'^marketing/qa/chats/(?P<chat_id>\d+)/delete/?$', marketing_agent.delete_qa_chat, name='marketing_qa_chats_delete'),  # DELETE
    re_path(r'^marketing/market-research/?$', marketing_agent.market_research, name='marketing_market_research'),  # POST
    re_path(r'^marketing/market-research/chats/?$', marketing_agent.list_research_chats, name='marketing_research_chats_list'),  # GET
    re_path(r'^marketing/market-research/chats/create/?$', marketing_agent.create_research_chat, name='marketing_research_chats_create'),  # POST
    re_path(r'^marketing/market-research/chats/(?P<chat_id>\d+)/update/?$', marketing_agent.update_research_chat, name='marketing_research_chats_update'),  # PATCH/PUT
    re_path(r'^marketing/market-research/chats/(?P<chat_id>\d+)/delete/?$', marketing_agent.delete_research_chat, name='marketing_research_chats_delete'),  # DELETE
    re_path(r'^marketing/outreach-campaign/?$', marketing_agent.outreach_campaign, name='marketing_outreach_campaign'),  # POST
    re_path(r'^marketing/documents/?$', marketing_agent.list_documents, name='marketing_list_documents'),  # GET
    re_path(r'^marketing/documents/(?P<document_id>\d+)/?$', marketing_agent.document_detail, name='marketing_document_detail'),  # GET
    re_path(r'^marketing/documents/(?P<document_id>\d+)/delete/?$', marketing_agent.document_delete, name='marketing_document_delete'),  # POST, DELETE
    re_path(r'^marketing/documents/(?P<document_id>\d+)/download/(?P<format_type>pdf|pptx)/?$', marketing_agent.document_download, name='marketing_document_download'),  # GET
    re_path(r'^marketing/document-authoring/?$', marketing_agent.document_authoring, name='marketing_document_authoring'),  # POST
    re_path(r'^marketing/notifications/?$', marketing_agent.get_notifications, name='marketing_get_notifications'),  # GET
    re_path(r'^marketing/notifications/monitor/?$', marketing_agent.proactive_notification_monitor, name='marketing_notifications_monitor'),  # POST
    re_path(r'^marketing/notifications/(?P<notification_id>\d+)/read/?$', marketing_agent.mark_notification_read, name='marketing_notification_read'),  # POST
    re_path(r'^marketing/notifications/(?P<notification_id>\d+)/delete/?$', marketing_agent.delete_notification, name='marketing_notification_delete'),  # POST

    # Frontline Agent endpoints (Company User)
    # Public widget/form (no auth – use widget_key to identify company)
    re_path(r'^frontline/public/qa/?$', frontline_agent.public_qa, name='frontline_public_qa'),  # POST
    re_path(r'^frontline/public/submit/?$', frontline_agent.public_submit, name='frontline_public_submit'),  # POST
    re_path(r'^frontline/widget-config/?$', frontline_agent.frontline_widget_config, name='frontline_widget_config'),  # GET
    re_path(r'^frontline/widget-config/update/?$', frontline_agent.update_frontline_widget_config, name='frontline_update_widget_config'),  # PATCH
    re_path(r'^frontline/widget/public-config/?$', frontline_agent.public_widget_config, name='frontline_public_widget_config'),  # GET (public, needs widget_key)
    re_path(r'^frontline/dashboard/?$', frontline_agent.frontline_dashboard, name='frontline_dashboard'),  # GET
    re_path(r'^frontline/documents/?$', frontline_agent.list_documents, name='frontline_list_documents'),  # GET
    re_path(r'^frontline/documents/upload/?$', frontline_agent.upload_document, name='frontline_upload_document'),  # POST
    re_path(r'^frontline/documents/(?P<document_id>\d+)/?$', frontline_agent.get_document, name='frontline_get_document'),  # GET
    re_path(r'^frontline/documents/(?P<document_id>\d+)/delete/?$', frontline_agent.delete_document, name='frontline_delete_document'),  # POST
    re_path(r'^frontline/documents/(?P<document_id>\d+)/summarize/?$', frontline_agent.summarize_document, name='frontline_summarize_document'),  # POST
    re_path(r'^frontline/documents/(?P<document_id>\d+)/extract/?$', frontline_agent.extract_document, name='frontline_extract_document'),  # POST
    # Document lifecycle (Phase 2 Batch 5)
    re_path(r'^frontline/documents/(?P<document_id>\d+)/status/?$', frontline_agent.document_processing_status, name='frontline_document_status'),  # GET
    re_path(r'^frontline/documents/(?P<document_id>\d+)/metadata/?$', frontline_agent.update_document_metadata, name='frontline_update_document_metadata'),  # PATCH
    re_path(r'^frontline/knowledge/qa/?$', frontline_agent.knowledge_qa, name='frontline_knowledge_qa'),  # POST
    re_path(r'^frontline/knowledge/feedback/?$', frontline_agent.knowledge_feedback, name='frontline_knowledge_feedback'),  # POST
    re_path(r'^frontline/knowledge/search/?$', frontline_agent.search_knowledge, name='frontline_search_knowledge'),  # GET
    re_path(r'^frontline/qa/chats/?$', frontline_agent.list_qa_chats, name='frontline_qa_chats_list'),  # GET
    re_path(r'^frontline/qa/chats/create/?$', frontline_agent.create_qa_chat, name='frontline_qa_chats_create'),  # POST
    re_path(r'^frontline/qa/chats/(?P<chat_id>\d+)/update/?$', frontline_agent.update_qa_chat, name='frontline_qa_chats_update'),  # PATCH/PUT
    re_path(r'^frontline/qa/chats/(?P<chat_id>\d+)/delete/?$', frontline_agent.delete_qa_chat, name='frontline_qa_chats_delete'),  # DELETE
    re_path(r'^frontline/tickets/?$', frontline_agent.list_tickets, name='frontline_list_tickets'),  # GET
    re_path(r'^frontline/tickets/aging/?$', frontline_agent.list_tickets_aging, name='frontline_list_tickets_aging'),  # GET
    re_path(r'^frontline/tickets/create/?$', frontline_agent.create_ticket, name='frontline_create_ticket'),  # POST
    re_path(r'^frontline/ticket-tasks/?$', frontline_agent.list_ticket_tasks, name='frontline_list_ticket_tasks'),  # GET
    re_path(r'^frontline/ticket-tasks/(?P<ticket_id>\d+)/?$', frontline_agent.update_ticket_task, name='frontline_update_ticket_task'),  # PATCH/PUT
    # Meetings (Phase 2 Batch 6)
    re_path(r'^frontline/meetings/?$', frontline_agent.list_meetings, name='frontline_list_meetings'),  # GET
    re_path(r'^frontline/meetings/create/?$', frontline_agent.create_meeting, name='frontline_create_meeting'),  # POST
    re_path(r'^frontline/meetings/availability/?$', frontline_agent.check_meeting_availability, name='frontline_check_meeting_availability'),  # GET
    re_path(r'^frontline/meetings/(?P<meeting_id>\d+)/?$', frontline_agent.get_meeting, name='frontline_get_meeting'),  # GET
    re_path(r'^frontline/meetings/(?P<meeting_id>\d+)/update/?$', frontline_agent.update_meeting, name='frontline_update_meeting'),  # PATCH
    re_path(r'^frontline/meetings/(?P<meeting_id>\d+)/delete/?$', frontline_agent.delete_meeting, name='frontline_delete_meeting'),  # DELETE
    re_path(r'^frontline/meetings/(?P<meeting_id>\d+)/extract-action-items/?$', frontline_agent.extract_meeting_action_items, name='frontline_extract_meeting_action_items'),  # POST
    # Ticket lifecycle (Phase 2 Batch 2)
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/notes/?$', frontline_agent.list_ticket_notes, name='frontline_list_ticket_notes'),  # GET
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/notes/create/?$', frontline_agent.create_ticket_note, name='frontline_create_ticket_note'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/notes/(?P<note_id>\d+)/?$', frontline_agent.update_or_delete_ticket_note, name='frontline_update_delete_ticket_note'),  # PATCH/DELETE
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/snooze/?$', frontline_agent.snooze_ticket, name='frontline_snooze_ticket'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/unsnooze/?$', frontline_agent.unsnooze_ticket, name='frontline_unsnooze_ticket'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/sla/pause/?$', frontline_agent.pause_ticket_sla, name='frontline_pause_ticket_sla'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/sla/resume/?$', frontline_agent.resume_ticket_sla, name='frontline_resume_ticket_sla'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/retriage/?$', frontline_agent.retriage_ticket, name='frontline_retriage_ticket'),  # POST
    # Ticket email thread (inbound + outbound messages on one ticket)
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/messages/?$', frontline_agent.list_ticket_messages, name='frontline_list_ticket_messages'),  # GET
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/reply/?$', frontline_agent.reply_to_ticket, name='frontline_reply_to_ticket'),  # POST
    # Inbound email webhook (public, signature-verified). `provider` is one of 'sendgrid', 'mailgun', 'generic'.
    re_path(r'^frontline/webhooks/inbound-email/(?P<provider>[a-z]+)/?$', frontline_agent.inbound_email_webhook, name='frontline_inbound_email_webhook'),  # POST
    # Customer 360 — Contacts + ticket context panel
    re_path(r'^frontline/contacts/?$', frontline_agent.list_contacts, name='frontline_list_contacts'),  # GET
    re_path(r'^frontline/contacts/create/?$', frontline_agent.create_contact, name='frontline_create_contact'),  # POST
    re_path(r'^frontline/contacts/(?P<contact_id>\d+)/?$', frontline_agent.get_contact, name='frontline_get_contact'),  # GET
    re_path(r'^frontline/contacts/(?P<contact_id>\d+)/update/?$', frontline_agent.update_contact, name='frontline_update_contact'),  # PATCH/PUT
    re_path(r'^frontline/contacts/(?P<contact_id>\d+)/tickets/?$', frontline_agent.list_contact_tickets, name='frontline_list_contact_tickets'),  # GET
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/context/?$', frontline_agent.get_ticket_context, name='frontline_get_ticket_context'),  # GET
    # Hand-off queue + reply-draft assist (Phase 3 §3.2)
    re_path(r'^frontline/tickets/handoffs/?$', frontline_agent.list_handoff_queue, name='frontline_list_handoff_queue'),  # GET
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/accept-handoff/?$', frontline_agent.accept_ticket_handoff, name='frontline_accept_ticket_handoff'),  # POST
    re_path(r'^frontline/tickets/(?P<ticket_id>\d+)/suggest-reply/?$', frontline_agent.suggest_ticket_reply, name='frontline_suggest_ticket_reply'),  # POST
    # HubSpot CRM integration (Phase 3 §3.3)
    re_path(r'^frontline/crm/hubspot/status/?$', frontline_agent.hubspot_status, name='frontline_hubspot_status'),  # GET
    re_path(r'^frontline/crm/hubspot/config/?$', frontline_agent.hubspot_update_config, name='frontline_hubspot_update_config'),  # PATCH/PUT
    re_path(r'^frontline/crm/hubspot/test/?$', frontline_agent.hubspot_test_connection, name='frontline_hubspot_test_connection'),  # POST
    re_path(r'^frontline/crm/hubspot/sync-all/?$', frontline_agent.hubspot_sync_all, name='frontline_hubspot_sync_all'),  # POST
    # Notifications
    re_path(r'^frontline/notifications/templates/?$', frontline_agent.list_notification_templates, name='frontline_list_notification_templates'),  # GET
    re_path(r'^frontline/notifications/templates/create/?$', frontline_agent.create_notification_template, name='frontline_create_notification_template'),  # POST
    re_path(r'^frontline/notifications/templates/(?P<template_id>\d+)/?$', frontline_agent.get_notification_template, name='frontline_get_notification_template'),  # GET
    re_path(r'^frontline/notifications/templates/(?P<template_id>\d+)/update/?$', frontline_agent.update_notification_template, name='frontline_update_notification_template'),  # PATCH/PUT
    re_path(r'^frontline/notifications/templates/(?P<template_id>\d+)/delete/?$', frontline_agent.delete_notification_template, name='frontline_delete_notification_template'),  # DELETE
    re_path(r'^frontline/notifications/templates/(?P<template_id>\d+)/preview/?$', frontline_agent.preview_notification_template, name='frontline_preview_notification_template'),  # POST
    re_path(r'^frontline/notifications/scheduled/?$', frontline_agent.list_scheduled_notifications, name='frontline_list_scheduled_notifications'),  # GET
    re_path(r'^frontline/notifications/dead-lettered/?$', frontline_agent.list_dead_lettered_notifications, name='frontline_list_dlq'),  # GET
    re_path(r'^frontline/notifications/(?P<notification_id>\d+)/retry/?$', frontline_agent.retry_dead_lettered_notification, name='frontline_retry_dlq'),  # POST
    re_path(r'^frontline/unsubscribe/?$', frontline_agent.public_unsubscribe, name='frontline_public_unsubscribe'),  # GET/POST (public, no auth)
    re_path(r'^frontline/notifications/schedule/?$', frontline_agent.schedule_notification, name='frontline_schedule_notification'),  # POST
    re_path(r'^frontline/notifications/send/?$', frontline_agent.send_notification_now, name='frontline_send_notification_now'),  # POST
    re_path(r'^frontline/notifications/preferences/?$', frontline_agent.get_notification_preferences, name='frontline_get_notification_preferences'),  # GET
    re_path(r'^frontline/notifications/preferences/update/?$', frontline_agent.update_notification_preferences, name='frontline_update_notification_preferences'),  # PATCH/PUT
    # Workflows
    re_path(r'^frontline/workflows/?$', frontline_agent.list_workflows, name='frontline_list_workflows'),  # GET
    re_path(r'^frontline/workflows/create/?$', frontline_agent.create_workflow, name='frontline_create_workflow'),  # POST
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/?$', frontline_agent.get_workflow, name='frontline_get_workflow'),  # GET
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/update/?$', frontline_agent.update_workflow, name='frontline_update_workflow'),  # PATCH/PUT
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/delete/?$', frontline_agent.delete_workflow, name='frontline_delete_workflow'),  # DELETE
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/execute/?$', frontline_agent.execute_workflow, name='frontline_execute_workflow'),  # POST
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/dry-run/?$', frontline_agent.dry_run_workflow, name='frontline_dry_run_workflow'),  # POST
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/versions/?$', frontline_agent.list_workflow_versions, name='frontline_list_workflow_versions'),  # GET
    re_path(r'^frontline/workflows/(?P<workflow_id>\d+)/versions/(?P<version>\d+)/rollback/?$', frontline_agent.rollback_workflow, name='frontline_rollback_workflow'),  # POST
    re_path(r'^frontline/workflows/executions/?$', frontline_agent.list_workflow_executions, name='frontline_list_workflow_executions'),  # GET
    re_path(r'^frontline/workflows/executions/(?P<execution_id>\d+)/approve/?$', frontline_agent.approve_workflow_execution, name='frontline_approve_workflow_execution'),  # POST
    re_path(r'^frontline/workflows/company-users/?$', frontline_agent.list_workflow_company_users, name='frontline_list_workflow_company_users'),  # GET
    # Analytics
    re_path(r'^frontline/analytics/?$', frontline_agent.frontline_analytics, name='frontline_analytics'),  # GET
    re_path(r'^frontline/analytics/ask/?$', frontline_agent.frontline_nl_analytics, name='frontline_nl_analytics'),  # POST
    re_path(r'^frontline/analytics/generate-graph/?$', frontline_agent.frontline_generate_graph, name='frontline_generate_graph'),  # POST
    re_path(r'^frontline/analytics/graph-prompts/?$', frontline_agent.frontline_graph_prompts_list, name='frontline_graph_prompts_list'),  # GET
    re_path(r'^frontline/analytics/graph-prompts/save/?$', frontline_agent.frontline_graph_prompts_save, name='frontline_graph_prompts_save'),  # POST
    re_path(r'^frontline/analytics/graph-prompts/(?P<prompt_id>\d+)/delete/?$', frontline_agent.frontline_graph_prompts_delete, name='frontline_graph_prompts_delete'),  # DELETE
    re_path(r'^frontline/analytics/graph-prompts/(?P<prompt_id>\d+)/favorite/?$', frontline_agent.frontline_graph_prompts_favorite, name='frontline_graph_prompts_favorite'),  # PATCH
    re_path(r'^frontline/analytics/export/?$', frontline_agent.frontline_analytics_export, name='frontline_analytics_export'),  # GET
    re_path(r'^frontline/analytics/agent-performance/?$', frontline_agent.frontline_agent_performance, name='frontline_agent_performance'),  # GET

    # Operations Agent endpoints
    re_path(r'^operations/dashboard/?$', operations_agent.dashboard_stats, name='operations_dashboard_stats'),  # GET
    re_path(r'^operations/documents/upload/?$', operations_agent.upload_document, name='operations_upload_document'),  # POST
    re_path(r'^operations/documents/?$', operations_agent.list_documents, name='operations_list_documents'),  # GET
    re_path(r'^operations/documents/(?P<document_id>\d+)/?$', operations_agent.get_document, name='operations_get_document'),  # GET
    re_path(r'^operations/documents/(?P<document_id>\d+)/delete/?$', operations_agent.delete_document, name='operations_delete_document'),  # DELETE
    re_path(r'^operations/summaries/upload/?$', operations_agent.upload_and_summarize, name='operations_upload_and_summarize'),  # POST
    re_path(r'^operations/summaries/?$', operations_agent.list_summaries, name='operations_list_summaries'),  # GET
    re_path(r'^operations/summaries/(?P<summary_id>\d+)/?$', operations_agent.get_summary, name='operations_get_summary'),  # GET
    re_path(r'^operations/summaries/(?P<summary_id>\d+)/delete/?$', operations_agent.delete_summary, name='operations_delete_summary'),  # DELETE

    # Operations Knowledge Q&A endpoints
    re_path(r'^operations/qa/ask/?$', operations_agent.ask_qa_question, name='operations_qa_ask'),  # POST
    re_path(r'^operations/qa/chats/?$', operations_agent.list_qa_chats, name='operations_qa_list_chats'),  # GET
    re_path(r'^operations/qa/chats/create/?$', operations_agent.create_qa_chat, name='operations_qa_create_chat'),  # POST
    re_path(r'^operations/qa/chats/(?P<chat_id>\d+)/?$', operations_agent.get_qa_chat, name='operations_qa_get_chat'),  # GET
    re_path(r'^operations/qa/chats/(?P<chat_id>\d+)/rename/?$', operations_agent.rename_qa_chat, name='operations_qa_rename_chat'),  # PATCH
    re_path(r'^operations/qa/chats/(?P<chat_id>\d+)/delete/?$', operations_agent.delete_qa_chat, name='operations_qa_delete_chat'),  # DELETE

    # Operations Document Authoring endpoints
    re_path(r'^operations/authoring/generate/?$', operations_agent.generate_document, name='operations_authoring_generate'),  # POST
    re_path(r'^operations/authoring/documents/?$', operations_agent.list_generated_documents, name='operations_authoring_list'),  # GET
    re_path(r'^operations/authoring/documents/(?P<doc_id>\d+)/?$', operations_agent.get_generated_document, name='operations_authoring_get'),  # GET
    re_path(r'^operations/authoring/documents/(?P<doc_id>\d+)/update/?$', operations_agent.update_generated_document, name='operations_authoring_update'),  # PATCH
    re_path(r'^operations/authoring/documents/(?P<doc_id>\d+)/delete/?$', operations_agent.delete_generated_document, name='operations_authoring_delete'),  # DELETE
    re_path(r'^operations/authoring/documents/(?P<doc_id>\d+)/regenerate/?$', operations_agent.regenerate_document, name='operations_authoring_regenerate'),  # POST
    re_path(r'^operations/authoring/documents/(?P<doc_id>\d+)/export/pdf/?$', operations_agent.export_generated_document_pdf, name='operations_authoring_export_pdf'),  # GET
    re_path(r'^operations/authoring/generate/stream/?$', operations_agent.stream_generate_document, name='operations_authoring_generate_stream'),  # POST

    # Operations Analytics
    re_path(r'^operations/analytics/?$', operations_agent.operations_analytics, name='operations_analytics'),  # GET
    # Reply Draft Agent endpoints
    re_path(r'^reply-draft/dashboard/?$', reply_draft_api.dashboard, name='reply_draft_dashboard'),
    re_path(r'^reply-draft/pending-replies/?$', reply_draft_api.list_pending_replies, name='reply_draft_list_pending'),
    re_path(r'^reply-draft/inbox/(?P<email_id>\d+)/?$', reply_draft_api.get_inbox_email, name='reply_draft_get_inbox_email'),
    re_path(r'^reply-draft/inbox/(?P<email_id>\d+)/attachments/?$', reply_draft_api.list_inbox_attachments, name='reply_draft_list_attachments'),
    re_path(r'^reply-draft/inbox/(?P<email_id>\d+)/fetch-attachments/?$', reply_draft_api.fetch_inbox_attachments, name='reply_draft_fetch_attachments'),
    re_path(r'^reply-draft/inbox/(?P<email_id>\d+)/attachments/(?P<attachment_id>\d+)/download/?$', reply_draft_api.download_inbox_attachment, name='reply_draft_download_attachment'),
    re_path(r'^reply-draft/reply/(?P<reply_id>\d+)/?$', reply_draft_api.get_reply, name='reply_draft_get_reply'),
    re_path(r'^reply-draft/campaigns/?$', reply_draft_api.list_campaigns, name='reply_draft_list_campaigns'),
    re_path(r'^reply-draft/sync-accounts/?$', reply_draft_api.list_sync_accounts, name='reply_draft_list_sync_accounts'),
    re_path(r'^reply-draft/leads/?$', reply_draft_api.list_leads, name='reply_draft_list_leads'),
    re_path(r'^reply-draft/drafts/?$', reply_draft_api.list_drafts, name='reply_draft_list_drafts'),
    re_path(r'^reply-draft/drafts/generate/?$', reply_draft_api.generate_draft, name='reply_draft_generate'),
    # Fresh-compose flow (Gmail-style "+ Compose"). compose/create makes a
    # blank ReplyDraft tied to no source email, which the user then fills
    # via compose/<id>/update before going through the existing /approve
    # + /send pipeline.
    re_path(r'^reply-draft/drafts/compose/?$', reply_draft_api.compose_create_draft, name='reply_draft_compose_create'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/compose/?$', reply_draft_api.compose_update_draft, name='reply_draft_compose_update'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/regenerate/?$', reply_draft_api.regenerate_draft, name='reply_draft_regenerate'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/approve/?$', reply_draft_api.approve_draft, name='reply_draft_approve'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/reject/?$', reply_draft_api.reject_draft, name='reply_draft_reject'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/send/?$', reply_draft_api.send_draft, name='reply_draft_send'),
    # Outgoing-attachment endpoints — companion to the inbound /inbox/<id>/attachments/...
    # routes above. The composer uploads here AFTER an AI draft is generated so the file
    # rows can be linked to the draft FK; on Send the agent reads them back and attaches
    # them to the SMTP message.
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/attachments/?$', reply_draft_api.list_draft_attachments, name='reply_draft_list_draft_attachments'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/attachments/upload/?$', reply_draft_api.upload_draft_attachment, name='reply_draft_upload_draft_attachment'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/attachments/(?P<attachment_id>\d+)/download/?$', reply_draft_api.download_draft_attachment, name='reply_draft_download_draft_attachment'),
    re_path(r'^reply-draft/drafts/(?P<draft_id>\d+)/attachments/(?P<attachment_id>\d+)/?$', reply_draft_api.delete_draft_attachment, name='reply_draft_delete_draft_attachment'),
    re_path(r'^reply-draft/accounts/create/?$', reply_draft_api.create_reply_account, name='reply_draft_create_account'),
    re_path(r'^reply-draft/accounts/delete/?$', reply_draft_api.delete_reply_account, name='reply_draft_delete_account'),
    re_path(r'^reply-draft/analytics/?$', reply_draft_api.reply_analytics, name='reply_draft_analytics'),

    # Operations Notifications
    re_path(r'^operations/notifications/?$', operations_agent.list_notifications, name='operations_notifications_list'),  # GET
    re_path(r'^operations/notifications/unread-count/?$', operations_agent.unread_notifications_count, name='operations_notifications_unread_count'),  # GET
    re_path(r'^operations/notifications/mark-all-read/?$', operations_agent.mark_all_notifications_read, name='operations_notifications_mark_all_read'),  # POST
    re_path(r'^operations/notifications/clear/?$', operations_agent.clear_all_notifications, name='operations_notifications_clear'),  # DELETE
    re_path(r'^operations/notifications/(?P<notification_id>\d+)/read/?$', operations_agent.mark_notification_read, name='operations_notifications_mark_read'),  # POST
    re_path(r'^operations/notifications/(?P<notification_id>\d+)/delete/?$', operations_agent.delete_notification, name='operations_notifications_delete'),  # DELETE

    # Module Purchase endpoints
    re_path(r'^modules/prices/?$', module_purchase.get_module_prices, name='get_module_prices'),  # GET (public)
    re_path(r'^modules/purchased/?$', module_purchase.get_purchased_modules, name='get_purchased_modules'),  # GET
    re_path(r'^modules/purchase/?$', module_purchase.purchase_module, name='purchase_module'),  # POST (legacy)
    re_path(r'^modules/checkout/?$', module_purchase.create_checkout_session, name='create_checkout_session'),  # POST
    re_path(r'^modules/stripe-webhook/?$', module_purchase.stripe_webhook, name='stripe_webhook'),  # POST (raw, no auth)
    re_path(r'^modules/verify-session/?$', module_purchase.verify_session, name='verify_session'),  # POST (public)
    re_path(r'^modules/(?P<module_name>[a-z_]+)/access/?$', module_purchase.check_module_access, name='check_module_access'),  # GET

    # Company API Key management (user-side: BYOK + key requests)
    re_path(r'^company/agent-keys/?$', company_api_keys.list_agent_keys, name='list_agent_keys'),  # GET
    re_path(r'^company/agent-keys/byok/?$', company_api_keys.upsert_byok_key, name='upsert_byok_key'),  # POST
    re_path(r'^company/agent-keys/byok/(?P<agent_name>[a-z_]+)/?$', company_api_keys.revoke_byok_key, name='revoke_byok_key'),  # DELETE
    re_path(r'^company/key-requests/?$', company_api_keys.list_key_requests, name='list_key_requests'),  # GET
    re_path(r'^company/key-requests/create/?$', company_api_keys.create_key_request, name='create_key_request'),  # POST
    re_path(r'^company/key-requests/(?P<request_id>\d+)/pay/?$', company_api_keys.pay_for_key_request, name='pay_for_key_request'),  # POST
    re_path(r'^company/key-requests/(?P<request_id>\d+)/checkout/?$', company_api_keys.create_key_checkout_session, name='create_key_checkout_session'),  # POST
    re_path(r'^company/key-requests/verify-session/(?P<session_id>[^/]+)/?$', company_api_keys.verify_key_session, name='verify_key_session'),  # GET

    # Super Admin — API keys, pricing, quotas, requests
    re_path(r'^admin/api-keys/overview/?$', admin_api_keys.admin_overview, name='admin_overview'),  # GET
    re_path(r'^admin/api-keys/?$', admin_api_keys.list_all_keys, name='admin_list_keys'),  # GET
    re_path(r'^admin/api-keys/assign/?$', admin_api_keys.assign_managed_key, name='admin_assign_key'),  # POST
    re_path(r'^admin/api-keys/(?P<key_id>\d+)/revoke/?$', admin_api_keys.revoke_key, name='admin_revoke_key'),  # POST
    re_path(r'^admin/pricing-config/?$', admin_api_keys.list_pricing, name='admin_list_pricing'),  # GET
    re_path(r'^admin/pricing-config/(?P<agent_name>[a-z_]+)/?$', admin_api_keys.update_pricing, name='admin_update_pricing'),  # PUT
    re_path(r'^admin/token-quotas/?$', admin_api_keys.list_quotas, name='admin_list_quotas'),  # GET
    re_path(r'^admin/token-quotas/(?P<quota_id>\d+)/?$', admin_api_keys.adjust_quota, name='admin_adjust_quota'),  # PATCH
    re_path(r'^admin/key-requests/?$', admin_api_keys.list_requests, name='admin_list_requests'),  # GET
    re_path(r'^admin/key-requests/(?P<request_id>\d+)/approve/?$', admin_api_keys.approve_key_request, name='admin_approve_request'),  # POST
    re_path(r'^admin/key-requests/(?P<request_id>\d+)/reject/?$', admin_api_keys.reject_request, name='admin_reject_request'),  # POST

    # Platform keys (shared default keys, one per provider)
    re_path(r'^admin/platform-keys/?$', admin_api_keys.list_platform_keys, name='admin_list_platform_keys'),  # GET
    re_path(r'^admin/platform-keys/upsert/?$', admin_api_keys.upsert_platform_key, name='admin_upsert_platform_key'),  # POST
    re_path(r'^admin/platform-keys/(?P<provider>[a-z]+)/revoke/?$', admin_api_keys.revoke_platform_key, name='admin_revoke_platform_key'),  # POST

    # Company picker for admin forms
    re_path(r'^admin/companies-list/?$', admin_api_keys.list_companies_simple, name='admin_list_companies'),  # GET

    # AI SDR Agent endpoints
    re_path(r'^sdr/dashboard/?$', sdr_api.sdr_dashboard, name='sdr_dashboard'),  # GET
    re_path(r'^sdr/icp/?$', sdr_api.icp_profile, name='sdr_icp_profile'),  # GET, POST
    re_path(r'^sdr/leads/?$', sdr_api.leads_list, name='sdr_leads_list'),  # GET, POST
    re_path(r'^sdr/leads/research/?$', sdr_api.research_leads, name='sdr_research_leads'),  # POST
    re_path(r'^sdr/leads/import/?$', sdr_api.import_leads_csv, name='sdr_import_leads_csv'),  # POST
    re_path(r'^sdr/leads/qualify-all/?$', sdr_api.qualify_all_leads, name='sdr_qualify_all_leads'),  # POST
    re_path(r'^sdr/leads/(?P<lead_id>\d+)/?$', sdr_api.lead_detail, name='sdr_lead_detail'),  # GET, PUT, DELETE
    re_path(r'^sdr/leads/(?P<lead_id>\d+)/qualify/?$', sdr_api.qualify_lead, name='sdr_qualify_lead'),  # POST
    # Campaigns
    re_path(r'^sdr/campaigns/?$', sdr_api.sdr_campaigns_list, name='sdr_campaigns_list'),  # GET, POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/?$', sdr_api.sdr_campaign_detail, name='sdr_campaign_detail'),  # GET, PUT, DELETE
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/steps/?$', sdr_api.sdr_campaign_steps, name='sdr_campaign_steps'),  # GET, POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/steps/(?P<step_id>\d+)/?$', sdr_api.sdr_campaign_step_detail, name='sdr_campaign_step_detail'),  # PUT, DELETE
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/generate-steps/?$', sdr_api.sdr_generate_steps, name='sdr_generate_steps'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/enroll/?$', sdr_api.sdr_enroll_leads, name='sdr_enroll_leads'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/contacts/?$', sdr_api.sdr_campaign_enrollments, name='sdr_campaign_enrollments'),  # GET
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/process/?$', sdr_api.sdr_process_outreach, name='sdr_process_outreach'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/enrollments/(?P<enrollment_id>\d+)/reply/?$', sdr_api.sdr_mark_replied, name='sdr_mark_replied'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/enrollments/(?P<enrollment_id>\d+)/reset/?$', sdr_api.sdr_reset_enrollment, name='sdr_reset_enrollment'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/check-replies/?$', sdr_api.sdr_check_replies, name='sdr_check_replies'),  # POST
    re_path(r'^sdr/campaigns/(?P<campaign_id>\d+)/clear-leads/?$', sdr_api.sdr_clear_campaign_leads, name='sdr_clear_campaign_leads'),  # POST
    re_path(r'^sdr/meetings/?$', sdr_api.sdr_meetings_list, name='sdr_meetings_list'),  # GET, POST
    re_path(r'^sdr/meetings/(?P<meeting_id>\d+)/?$', sdr_api.sdr_meeting_detail, name='sdr_meeting_detail'),  # GET, PUT, DELETE
    # ---------------------------------------------------------------------
    # HR Support Agent
    # ---------------------------------------------------------------------
    # Dashboard
    re_path(r'^hr/dashboard/?$', hr_agent.hr_dashboard, name='hr_dashboard'),  # GET

    # Employees
    re_path(r'^hr/employees/?$', hr_agent.list_employees, name='hr_list_employees'),  # GET
    re_path(r'^hr/employees/create/?$', hr_agent.create_employee, name='hr_create_employee'),  # POST
    re_path(r'^hr/departments/?$', hr_agent.list_departments, name='hr_list_departments'),  # GET
    re_path(r'^hr/departments/create/?$', hr_agent.create_department, name='hr_create_department'),  # POST
    re_path(r'^hr/departments/(?P<dept_id>\d+)/update/?$', hr_agent.update_department, name='hr_update_department'),  # PATCH/POST
    re_path(r'^hr/departments/(?P<dept_id>\d+)/delete/?$', hr_agent.delete_department, name='hr_delete_department'),  # DELETE/POST

    # Knowledge Q&A
    re_path(r'^hr/knowledge-qa/?$', hr_agent.hr_knowledge_qa, name='hr_knowledge_qa'),  # POST
    # Persisted HR Q&A chats — sidebar history (mirrors PM agent's chat shape)
    re_path(r'^hr/ai/knowledge-qa/chats/?$', hr_agent.list_hr_knowledge_chats, name='hr_list_knowledge_chats'),  # GET
    re_path(r'^hr/ai/knowledge-qa/chats/create/?$', hr_agent.create_hr_knowledge_chat, name='hr_create_knowledge_chat'),  # POST
    re_path(r'^hr/ai/knowledge-qa/chats/(?P<chat_id>\d+)/update/?$', hr_agent.update_hr_knowledge_chat, name='hr_update_knowledge_chat'),  # PATCH
    re_path(r'^hr/ai/knowledge-qa/chats/(?P<chat_id>\d+)/delete/?$', hr_agent.delete_hr_knowledge_chat, name='hr_delete_knowledge_chat'),  # DELETE

    # Documents
    re_path(r'^hr/documents/?$', hr_agent.list_hr_documents, name='hr_list_documents'),  # GET
    re_path(r'^hr/documents/upload/?$', hr_agent.upload_hr_document, name='hr_upload_document'),  # POST
    re_path(r'^hr/documents/(?P<document_id>\d+)/?$', hr_agent.get_hr_document, name='hr_get_document'),  # GET
    re_path(r'^hr/documents/(?P<document_id>\d+)/summarize/?$', hr_agent.summarize_hr_document, name='hr_summarize_document'),  # POST
    re_path(r'^hr/documents/(?P<document_id>\d+)/extract/?$', hr_agent.extract_hr_document, name='hr_extract_document'),  # POST
    re_path(r'^hr/documents/(?P<document_id>\d+)/delete/?$', hr_agent.delete_hr_document, name='hr_delete_document'),  # DELETE/POST

    # Workflows / SOPs
    re_path(r'^hr/workflows/?$', hr_agent.list_hr_workflows, name='hr_list_workflows'),  # GET
    re_path(r'^hr/workflows/create/?$', hr_agent.create_hr_workflow, name='hr_create_workflow'),  # POST
    re_path(r'^hr/workflows/(?P<workflow_id>\d+)/?$', hr_agent.get_hr_workflow, name='hr_get_workflow'),  # GET
    re_path(r'^hr/workflows/(?P<workflow_id>\d+)/update/?$', hr_agent.update_hr_workflow, name='hr_update_workflow'),  # PATCH
    re_path(r'^hr/workflows/(?P<workflow_id>\d+)/delete/?$', hr_agent.delete_hr_workflow, name='hr_delete_workflow'),  # DELETE/POST
    re_path(r'^hr/workflows/(?P<workflow_id>\d+)/execute/?$', hr_agent.execute_hr_workflow, name='hr_execute_workflow'),  # POST
    re_path(r'^hr/workflows/executions/?$', hr_agent.list_hr_workflow_executions, name='hr_list_workflow_executions'),  # GET
    re_path(r'^hr/workflows/executions/(?P<execution_id>\d+)/approve/?$', hr_agent.approve_hr_workflow_execution, name='hr_approve_workflow_execution'),  # POST
    re_path(r'^hr/workflows/executions/(?P<execution_id>\d+)/reject/?$', hr_agent.reject_hr_workflow_execution, name='hr_reject_workflow_execution'),  # POST

    # Notifications
    re_path(r'^hr/notifications/templates/?$', hr_agent.list_hr_notification_templates, name='hr_list_notification_templates'),  # GET
    re_path(r'^hr/notifications/templates/create/?$', hr_agent.create_hr_notification_template, name='hr_create_notification_template'),  # POST
    re_path(r'^hr/notifications/scheduled/?$', hr_agent.list_hr_scheduled_notifications, name='hr_list_scheduled_notifications'),  # GET

    # Meetings
    re_path(r'^hr/meetings/?$', hr_agent.list_hr_meetings, name='hr_list_meetings'),  # GET
    re_path(r'^hr/meetings/create/?$', hr_agent.create_hr_meeting, name='hr_create_meeting'),  # POST
    re_path(r'^hr/meetings/availability/?$', hr_agent.hr_meeting_availability, name='hr_meeting_availability'),  # GET
    re_path(r'^hr/meetings/(?P<meeting_id>\d+)/?$', hr_agent.get_hr_meeting, name='hr_get_meeting'),  # GET
    re_path(r'^hr/meetings/(?P<meeting_id>\d+)/update/?$', hr_agent.update_hr_meeting, name='hr_update_meeting'),  # PATCH
    re_path(r'^hr/meetings/(?P<meeting_id>\d+)/cancel/?$', hr_agent.cancel_hr_meeting, name='hr_cancel_meeting'),  # POST
    re_path(r'^hr/meetings/(?P<meeting_id>\d+)/extract-action-items/?$', hr_agent.extract_hr_meeting_action_items, name='hr_extract_meeting_action_items'),  # POST
    # Meeting Scheduler — natural-language LLM scheduling (mirrors PM agent)
    re_path(r'^hr/ai/meetings/schedule/?$', hr_agent.hr_meeting_schedule, name='hr_meeting_schedule'),  # POST
    re_path(r'^hr/ai/meeting-scheduler/chats/?$', hr_agent.list_hr_meeting_scheduler_chats, name='hr_list_meeting_scheduler_chats'),  # GET
    re_path(r'^hr/ai/meeting-scheduler/chats/create/?$', hr_agent.create_hr_meeting_scheduler_chat, name='hr_create_meeting_scheduler_chat'),  # POST
    re_path(r'^hr/ai/meeting-scheduler/chats/(?P<chat_id>\d+)/update/?$', hr_agent.update_hr_meeting_scheduler_chat, name='hr_update_meeting_scheduler_chat'),  # PATCH
    re_path(r'^hr/ai/meeting-scheduler/chats/(?P<chat_id>\d+)/delete/?$', hr_agent.delete_hr_meeting_scheduler_chat, name='hr_delete_meeting_scheduler_chat'),  # DELETE

    # Leave requests
    re_path(r'^hr/leave-requests/?$', hr_agent.list_leave_requests, name='hr_list_leave_requests'),  # GET
    re_path(r'^hr/leave-requests/submit/?$', hr_agent.submit_leave_request, name='hr_submit_leave_request'),  # POST
    re_path(r'^hr/leave-requests/(?P<request_id>\d+)/decide/?$', hr_agent.decide_leave_request, name='hr_decide_leave_request'),  # POST

    # Holiday calendar
    re_path(r'^hr/holidays/?$', hr_agent.list_holidays, name='hr_list_holidays'),  # GET
    re_path(r'^hr/holidays/create/?$', hr_agent.create_holiday, name='hr_create_holiday'),  # POST (also upserts)
    re_path(r'^hr/holidays/(?P<holiday_id>\d+)/delete/?$', hr_agent.delete_holiday, name='hr_delete_holiday'),  # DELETE

    # Leave accrual policies
    re_path(r'^hr/leave-accrual-policies/?$', hr_agent.list_accrual_policies, name='hr_list_accrual_policies'),  # GET
    re_path(r'^hr/leave-accrual-policies/upsert/?$', hr_agent.upsert_accrual_policy, name='hr_upsert_accrual_policy'),  # POST
    re_path(r'^hr/leave-accrual-policies/(?P<policy_id>\d+)/delete/?$', hr_agent.delete_accrual_policy, name='hr_delete_accrual_policy'),  # DELETE

    # Employee detail bundle
    re_path(r'^hr/employees/(?P<employee_id>\d+)/?$', hr_agent.get_employee_detail, name='hr_get_employee_detail'),  # GET

    # Compensation history (HR-admin only)
    re_path(r'^hr/employees/(?P<employee_id>\d+)/compensation/?$', hr_agent.list_compensation_history, name='hr_list_compensation'),  # GET
    re_path(r'^hr/employees/(?P<employee_id>\d+)/compensation/create/?$', hr_agent.create_compensation, name='hr_create_compensation'),  # POST
    re_path(r'^hr/compensation/(?P<comp_id>\d+)/delete/?$', hr_agent.delete_compensation, name='hr_delete_compensation'),  # DELETE

    # Performance reviews
    re_path(r'^hr/review-cycles/?$', hr_agent.list_review_cycles, name='hr_list_review_cycles'),  # GET
    re_path(r'^hr/review-cycles/create/?$', hr_agent.create_review_cycle, name='hr_create_review_cycle'),  # POST
    re_path(r'^hr/review-cycles/(?P<cycle_id>\d+)/activate/?$', hr_agent.activate_review_cycle, name='hr_activate_review_cycle'),  # POST
    re_path(r'^hr/review-cycles/(?P<cycle_id>\d+)/delete/?$', hr_agent.delete_review_cycle, name='hr_delete_review_cycle'),  # POST/DELETE
    re_path(r'^hr/employees/(?P<employee_id>\d+)/reviews/?$', hr_agent.list_employee_reviews, name='hr_list_employee_reviews'),  # GET
    re_path(r'^hr/reviews/(?P<review_id>\d+)/update/?$', hr_agent.update_perf_review, name='hr_update_perf_review'),  # POST/PATCH
]


# -------------------------------------------------------------------------
# API versioning (Phase 1 §1.6 — close "no API versioning" loophole)
# -------------------------------------------------------------------------
# Mirror every ^frontline/ route under ^v1/frontline/. Legacy /frontline/* stays
# live so existing embed widgets / integrations keep working; new clients should
# use /api/v1/frontline/*. Names get a `v1_` prefix so reverse() can pick a version.
from django.urls import URLPattern as _URLPattern  # noqa: E402

_v1_aliases = []
for _pat in list(urlpatterns):
    if not isinstance(_pat, _URLPattern):
        continue
    _name = getattr(_pat, 'name', '') or ''
    if not _name.startswith('frontline_'):
        continue
    # `_regex` is the raw pattern string we passed to re_path. It's been stable
    # through Django 3.x/4.x — if that ever changes we'd fall back to
    # str(_pat.pattern) which yields the same thing.
    _raw_regex = getattr(_pat.pattern, '_regex', '') or str(_pat.pattern)
    if not _raw_regex.startswith('^frontline/'):
        continue
    _new_regex = '^v1/' + _raw_regex.lstrip('^')
    _v1_aliases.append(re_path(_new_regex, _pat.callback, name='v1_' + _name))
urlpatterns += _v1_aliases
