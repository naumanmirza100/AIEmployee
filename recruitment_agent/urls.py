from django.conf import settings
from django.urls import path
from . import views

# Pages a candidate reaches from a link in an email. There is no login: the
# token in the address is the key. Always on.
urlpatterns = [
    path('interview/select/<str:token>/', views.candidate_select_slot, name='candidate_select_slot'),
    path('application/track/<str:token>/', views.candidate_application_status, name='candidate_application_status'),
    path('api/interview/available-slots/<str:token>/', views.get_available_slots_for_interview, name='get_available_slots_for_interview'),
    path('api/interviews/confirm/', views.confirm_interview_slot, name='confirm_interview_slot'),
]

# The old session-login recruiter pages. The React app uses /api/recruitment/
# instead. These list and change every company's interviews and jobs, so they
# stay off unless LEGACY_SITE_ENABLED is set (see settings).
if settings.LEGACY_SITE_ENABLED:
    urlpatterns += [
        path('', views.recruitment_dashboard, name='recruitment_dashboard'),
        path('api/process/', views.process_cvs, name='recruitment_process_cvs'),
        # Interview scheduling endpoints
        path('api/interviews/schedule/', views.schedule_interview, name='schedule_interview'),
        path('api/interviews/<int:interview_id>/', views.get_interview_details, name='get_interview_details'),
        # Recruiter email settings
        path('api/recruiter/email-settings/', views.recruiter_email_settings, name='recruiter_email_settings'),
        # Recruiter interview settings
        path('api/recruiter/interview-settings/', views.recruiter_interview_settings, name='recruiter_interview_settings'),
        path('api/interviews/', views.list_interviews, name='list_interviews'),
        # Job Description endpoints
        path('api/job-descriptions/', views.list_job_descriptions, name='list_job_descriptions'),
        path('api/job-descriptions/create/', views.create_job_description, name='create_job_description'),
        path('api/job-descriptions/<int:job_description_id>/update/', views.update_job_description, name='update_job_description'),
        path('api/job-descriptions/<int:job_description_id>/delete/', views.delete_job_description, name='delete_job_description'),
    ]
