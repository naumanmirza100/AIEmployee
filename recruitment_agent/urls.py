from django.urls import path
from . import views

urlpatterns = [
    path('', views.recruitment_dashboard, name='recruitment_dashboard'),
    path('api/process/', views.process_cvs, name='recruitment_process_cvs'),
    # Interview scheduling endpoints
    path('api/interviews/schedule/', views.schedule_interview, name='schedule_interview'),
    path('api/interviews/<int:interview_id>/', views.get_interview_details, name='get_interview_details'),
    path('api/interviews/confirm/', views.confirm_interview_slot, name='confirm_interview_slot'),
    # Automatic follow-up email checking (can be called by cron/scheduled tasks)
    path('api/interviews/auto-check/', views.auto_check_interview_followups, name='auto_check_interview_followups'),
    # Recruiter email settings
    path('api/recruiter/email-settings/', views.recruiter_email_settings, name='recruiter_email_settings'),
    path('api/interviews/', views.list_interviews, name='list_interviews'),
    # Job Description endpoints
    path('api/job-descriptions/', views.list_job_descriptions, name='list_job_descriptions'),
    path('api/job-descriptions/create/', views.create_job_description, name='create_job_description'),
    path('api/job-descriptions/<int:job_description_id>/update/', views.update_job_description, name='update_job_description'),
    path('api/job-descriptions/<int:job_description_id>/delete/', views.delete_job_description, name='delete_job_description'),
    # Public candidate slot selection page (no auth required)
    path('interview/select/<str:token>/', views.candidate_select_slot, name='candidate_select_slot'),
    # Debug: View parsed CV data
    path('debug/parsed/<int:cv_id>/', views.view_parsed_cv, name='view_parsed_cv'),
]


