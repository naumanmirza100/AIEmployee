from django.urls import path, include
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
from api.views.health import health_check

app_name = 'api'

urlpatterns = [
    # Health check
    path('health/', health_check, name='health_check'),
    
    # Authentication endpoints
    path('auth/register/', auth.register, name='register'),
    path('auth/login/', auth.login, name='login'),
    path('auth/refresh/', auth.refresh_token, name='refresh_token'),
    path('auth/logout/', auth.logout, name='logout'),
    path('auth/me/', auth.get_current_user, name='get_current_user'),
    
    # User endpoints
    path('users/profile/', user.get_profile, name='get_profile'),  # GET
    path('users/profile/update/', user.update_profile, name='update_profile'),  # PUT
    path('users/dashboard/', user.get_dashboard_stats, name='get_dashboard_stats'),
    
    # Project endpoints
    path('projects/', project.list_projects, name='list_projects'),
    path('projects/<int:id>/', project.get_project, name='get_project'),
    path('projects/create/', project.create_project, name='create_project'),
    path('projects/<int:id>/update/', project.update_project, name='update_project'),
    path('projects/<int:id>/delete/', project.delete_project, name='delete_project'),
    path('projects/<int:id>/apply/', project.apply_to_project, name='apply_to_project'),
    path('projects/<int:id>/applications/', project.get_project_applications, name='get_project_applications'),
    
    # Industry endpoints
    path('industries/', industry.list_industries, name='list_industries'),
    path('industries/<slug:slug>/', industry.get_industry_by_slug, name='get_industry_by_slug'),
    path('industries/<slug:slug>/challenges/', industry.get_industry_challenges, name='get_industry_challenges'),
    
    # Blog endpoints
    path('blog/posts/', blog.list_blog_posts, name='list_blog_posts'),
    path('blog/posts/<slug:slug>/', blog.get_blog_post_by_slug, name='get_blog_post_by_slug'),
    path('blog/categories/', blog.get_blog_categories, name='get_blog_categories'),
    path('blog/tags/', blog.list_blog_tags, name='list_blog_tags'),
    
    # Review endpoints
    path('reviews/', review.list_reviews, name='list_reviews'),
    path('reviews/summary/', review.get_reviews_summary, name='get_reviews_summary'),
    
    # Contact endpoints
    path('contact/', contact.submit_contact_form, name='submit_contact_form'),
    path('contact/complaints/', contact.submit_complaint, name='submit_complaint'),
    path('contact/admin/', contact.list_contact_messages, name='list_contact_messages'),
    path('contact/admin/<int:id>/', contact.get_contact_message, name='get_contact_message'),
    path('contact/admin/<int:id>/status/', contact.update_contact_message_status, name='update_contact_message_status'),
    
    # Consultation endpoints
    path('consultations/', consultation.create_consultation, name='create_consultation'),  # POST
    path('consultations/list/', consultation.list_consultations, name='list_consultations'),  # GET
    path('consultations/<int:id>/', consultation.get_consultation, name='get_consultation'),
    
    # Pricing endpoints
    path('pricing/plans/', pricing.list_pricing_plans, name='list_pricing_plans'),
    path('pricing/subscriptions/', pricing.list_subscriptions, name='list_subscriptions'),  # GET
    path('pricing/subscriptions/', pricing.create_subscription, name='create_subscription'),  # POST
    
    # Payment endpoints
    path('payments/', payment.process_payment, name='process_payment'),  # POST
    path('payments/list/', payment.list_payments, name='list_payments'),  # GET
    path('payments/invoices/', pricing.list_invoices, name='list_invoices'),  # GET (invoices)
    path('payments/methods/', payment.list_payment_methods, name='list_payment_methods'),  # GET
    path('payments/methods/', payment.add_payment_method, name='add_payment_method'),  # POST
    
    # Referral endpoints
    path('referrals/my-code/', referral.get_my_referral_code, name='get_my_referral_code'),
    path('referrals/use-code/', referral.use_referral_code, name='use_referral_code'),
    path('referrals/my-referrals/', referral.get_my_referrals, name='get_my_referrals'),
    
    # Analytics endpoints
    path('analytics/events/', analytics.log_analytics_event, name='log_analytics_event'),
    path('analytics/page-views/', analytics.log_page_view, name='log_page_view'),
    
    # Notification endpoints
    path('notifications/', notification.list_notifications, name='list_notifications'),
    path('notifications/<int:id>/read/', notification.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', notification.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Company endpoints
    path('companies/', company.list_companies, name='list_companies'),  # GET
    path('companies/create/', company.create_company, name='create_company'),  # POST
    path('companies/<int:companyId>/tokens/', company.get_company_tokens, name='get_company_tokens'),  # GET
    path('companies/<int:companyId>/tokens/generate/', company.generate_company_token, name='generate_company_token'),  # POST
    
    # Company Auth endpoints
    path('company/verify-token/', company_auth.verify_registration_token, name='verify_registration_token'),
    path('company/register/', company_auth.register_company_user, name='register_company_user'),
    path('company/login/', company_auth.login_company_user, name='login_company_user'),
    
    # Career endpoints
    path('careers/positions/', career.list_job_positions, name='list_job_positions'),
    path('careers/applications/', career.submit_career_application, name='submit_career_application'),  # POST
    path('careers/admin/applications/', career.list_career_applications, name='list_career_applications'),  # GET (admin)
    path('careers/admin/applications/<int:id>/', career.get_career_application, name='get_career_application'),  # GET (admin)
    path('careers/admin/applications/<int:id>/status/', career.update_career_application_status, name='update_career_application_status'),  # PATCH (admin)
    
    # Applicant endpoints
    path('applicant/status/', applicant.get_application_status, name='get_application_status'),
    
    # Quiz endpoints
    path('quiz/responses/', quiz.submit_quiz_response, name='submit_quiz_response'),
    
    # AI Predictor endpoints
    path('ai-predictor/', ai_predictor.submit_ai_predictor, name='submit_ai_predictor'),  # POST
    path('ai-predictor/admin/', ai_predictor.list_ai_predictions, name='list_ai_predictions'),  # GET (admin)
    path('ai-predictor/admin/<int:id>/', ai_predictor.get_ai_prediction, name='get_ai_prediction'),  # GET (admin)
    
    # Chatbot endpoints
    path('chatbot/conversations/', chatbot.create_conversation, name='create_conversation'),  # POST
    path('chatbot/messages/', chatbot.send_chatbot_message, name='send_chatbot_message'),  # POST
    path('chatbot/conversations/<int:id>/messages/', chatbot.get_conversation_messages, name='get_conversation_messages'),
    
    # White Label endpoints
    path('white-label/products/', white_label.list_white_label_products, name='list_white_label_products'),
    path('white-label/products/<int:id>/', white_label.get_white_label_product, name='get_white_label_product'),
    path('white-label/categories/', white_label.get_white_label_categories, name='get_white_label_categories'),
    
    # Company Jobs endpoints
    path('company/jobs/', company_jobs.create_company_job, name='create_company_job'),  # POST
    path('company/jobs/list/', company_jobs.list_company_jobs, name='list_company_jobs'),  # GET
    path('company/jobs/<int:id>/', company_jobs.update_company_job, name='update_company_job'),  # PUT
    path('company/jobs/<int:jobId>/applications/', company_jobs.get_company_job_applications, name='get_company_job_applications'),
    path('company/applications/<int:id>/status/', company_jobs.update_company_application_status, name='update_company_application_status'),
]
