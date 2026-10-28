"""
Django signals for Recruitment: default qualification settings for new company users.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import RecruiterQualificationSettings
from core.models import CompanyUser
import logging

logger = logging.getLogger(__name__)

# Follow-ups and reminders are sent by recruitment_agent.tasks.check_and_send_followup_emails alone. A thread
# started on every save of an interview sent them too: up to three copies of one reminder (CO-185), and a
# fresh database connection for each save (CO-189).


@receiver(post_save, sender=CompanyUser)
def create_default_qualification_settings(sender, instance, created, **kwargs):
   
    if created:
        try:
            RecruiterQualificationSettings.objects.get_or_create(
                company_user=instance,
                defaults={
                    'interview_threshold': 65,
                    'hold_threshold': 45,
                    'use_custom_thresholds': False,
                }
            )
            logger.info(f"✅ Created default qualification settings for company user {instance.id}")
        except Exception as e:
            logger.error(f"Error creating default qualification settings for company user {instance.id}: {str(e)}", exc_info=True)

