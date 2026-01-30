"""
Interview Scheduling Agent for AI-based recruitment system.

This agent handles interview coordination and communication after a candidate
has been approved for interview by the screening and scoring system.
"""

import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from django.utils import timezone
from django.core.mail import send_mail
from django.core.mail.message import sanitize_address
from django.conf import settings
from django.template.loader import render_to_string

from recruitment_agent.log_service import LogService
from recruitment_agent.models import Interview


class InterviewSchedulingAgent:
    """
    Interview Scheduling Agent responsible for:
    - Generating available interview time slots
    - Sending interview invitation emails
    - Handling candidate slot selection
    - Sending confirmation and reminder emails
    """

    def __init__(
        self,
        log_service: Optional[LogService] = None,
    ) -> None:
        self.log_service = log_service or LogService()
        # Default recruiter availability (can be customized)
        self.default_working_hours = {
            'start': 9,  # 9 AM
            'end': 17,   # 5 PM
        }
        self.default_slot_duration = 60  # 60 minutes per interview

    def schedule_interview(
        self,
        candidate_name: str,
        candidate_email: str,
        job_role: str,
        interview_type: str = 'ONLINE',
        candidate_phone: Optional[str] = None,
        cv_record_id: Optional[int] = None,
        recruiter_id: Optional[int] = None,
        company_user_id: Optional[int] = None,
        email_settings: Optional[Dict[str, Any]] = None,
        custom_slots: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Main method to schedule an interview for an approved candidate.
        
        Args:
            candidate_name: Name of the candidate
            candidate_email: Email address of the candidate
            job_role: Job role/position
            interview_type: 'ONLINE' or 'ONSITE'
            candidate_phone: Optional phone number
            cv_record_id: Optional ID of related CV record
            recruiter_id: Optional ID of recruiter user
            custom_slots: Optional custom time slots (list of dicts with 'datetime' and 'display')
        
        Returns:
            Dict with interview details and status
        """
        self._log_step("interview_scheduling_start", {
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "job_role": job_role,
            "interview_type": interview_type,
        })

        # No longer generate pre-selected slots - candidates will use date-time picker
        # Store empty array for backward compatibility
        available_slots = []

        # Generate unique secure token for candidate slot selection
        confirmation_token = secrets.token_urlsafe(32)
        
        # Get recruiter email settings to apply to interview
        from recruitment_agent.models import RecruiterEmailSettings
        followup_delay = 48
        reminder_hours = 24
        max_followups = 3
        min_between = 24
        
        print("\n⚙️  APPLYING RECRUITER EMAIL SETTINGS TO INTERVIEW")
        print(f"   Recruiter ID: {recruiter_id}")
        print(f"   Company User ID: {company_user_id}")
        
        # Use provided email_settings if available
        if email_settings:
            followup_delay = email_settings.get('followup_delay_hours', followup_delay)
            reminder_hours = email_settings.get('reminder_hours_before', reminder_hours)
            max_followups = email_settings.get('max_followup_emails', max_followups)
            min_between = email_settings.get('min_hours_between_followups', min_between)
            print(f"   ✅ Using provided email settings:")
            print(f"      • Follow-up delay: {followup_delay} hours ({followup_delay * 60} minutes)")
            print(f"      • Reminder hours before: {reminder_hours} hours")
            print(f"      • Max follow-ups: {max_followups}")
            print(f"      • Min hours between follow-ups: {min_between} hours ({min_between * 60} minutes)")
        elif company_user_id:
            # Try to get company user email settings
            try:
                from core.models import CompanyUser
                company_user = CompanyUser.objects.get(id=company_user_id)
                settings = company_user.recruiter_email_settings
                followup_delay = settings.followup_delay_hours
                reminder_hours = settings.reminder_hours_before
                max_followups = settings.max_followup_emails
                min_between = settings.min_hours_between_followups
                print(f"   ✅ Using company user custom settings:")
                print(f"      • Follow-up delay: {followup_delay} hours ({followup_delay * 60} minutes)")
                print(f"      • Reminder hours before: {reminder_hours} hours")
                print(f"      • Max follow-ups: {max_followups}")
                print(f"      • Min hours between follow-ups: {min_between} hours ({min_between * 60} minutes)")
            except CompanyUser.DoesNotExist:
                print(f"   ⚠️  Company user not found (ID: {company_user_id}), using defaults")
            except RecruiterEmailSettings.DoesNotExist:
                print(f"   ⚠️  No email settings found for company user, using defaults")
            except Exception as e:
                print(f"   ⚠️  Error getting company user settings: {str(e)}, using defaults")
        elif recruiter_id:
            try:
                from django.contrib.auth.models import User
                recruiter = User.objects.get(id=recruiter_id)
                print(f"   Recruiter: {recruiter.username}")
                settings = recruiter.recruiter_email_settings
                followup_delay = settings.followup_delay_hours
                reminder_hours = settings.reminder_hours_before
                max_followups = settings.max_followup_emails
                min_between = settings.min_hours_between_followups
                print(f"   ✅ Using recruiter custom settings:")
                print(f"      • Follow-up delay: {followup_delay} hours ({followup_delay * 60} minutes)")
                print(f"      • Reminder hours before: {reminder_hours} hours")
                print(f"      • Max follow-ups: {max_followups}")
                print(f"      • Min hours between follow-ups: {min_between} hours ({min_between * 60} minutes)")
            except User.DoesNotExist:
                print(f"   ⚠️  Recruiter not found (ID: {recruiter_id}), using defaults")
            except RecruiterEmailSettings.DoesNotExist:
                print(f"   ⚠️  No email settings found for recruiter, using defaults")
            except Exception as e:
                print(f"   ⚠️  Error getting recruiter settings: {str(e)}, using defaults")
        else:
            print(f"   ⚠️  No recruiter ID or company user ID provided, using defaults")
        
        print(f"   📝 Final settings to apply:")
        print(f"      • Follow-up delay: {followup_delay} hours ({followup_delay * 60} minutes)")
        print(f"      • Reminder hours before: {reminder_hours} hours")
        print(f"      • Max follow-ups: {max_followups}")
        print(f"      • Min hours between follow-ups: {min_between} hours ({min_between * 60} minutes)")
        
        # Create interview record with recruiter/company_user preferences
        interview_data = {
            'candidate_name': candidate_name,
            'candidate_email': candidate_email,
            'candidate_phone': candidate_phone,
            'job_role': job_role,
            'interview_type': interview_type,
            'status': 'PENDING',
            'available_slots_json': json.dumps(available_slots, default=str),
            'cv_record_id': cv_record_id,
            'recruiter_id': recruiter_id,
            'confirmation_token': confirmation_token,
            'invitation_sent_at': timezone.now(),
            # Apply email timing preferences
            'followup_delay_hours': followup_delay,
            'reminder_hours_before': reminder_hours,
            'max_followup_emails': max_followups,
            'min_hours_between_followups': min_between,
        }
        
        # Add company_user if provided
        if company_user_id:
            from core.models import CompanyUser
            try:
                company_user = CompanyUser.objects.get(id=company_user_id)
                interview_data['company_user'] = company_user
            except CompanyUser.DoesNotExist:
                pass
        
        interview = Interview.objects.create(**interview_data)
        
        print(f"   ✅ Interview created with ID: {interview.id}")
        print(f"   ✅ Email settings saved to interview record")
        print(f"   📋 Interview will be checked for follow-ups after {followup_delay} hours ({followup_delay * 60} minutes)")

        # Send invitation email
        email_sent = self.send_invitation_email(interview, available_slots)
        
        # Trigger an immediate follow-up check (for testing - will skip if not enough time has passed)
        try:
            print(f"\n🔄 Triggering immediate follow-up check (for testing)...")
            from recruitment_agent.tasks import check_and_send_followup_emails
            import threading
            def run_check():
                import time
                time.sleep(2)  # Wait 2 seconds to ensure interview is saved
                stats = check_and_send_followup_emails()
                print(f"✅ Immediate check completed: {stats}")
            thread = threading.Thread(target=run_check)
            thread.daemon = True
            thread.start()
        except Exception as e:
            print(f"⚠️  Could not trigger immediate check: {str(e)}")

        if not email_sent:
            self._log_error("invitation_email_failed", {
                "interview_id": interview.id,
                "candidate_email": candidate_email,
            })

        result = {
            "interview_id": interview.id,
            "status": interview.status,
            "available_slots": available_slots,
            "invitation_sent": email_sent,
            "message": "Interview invitation sent successfully" if email_sent else "Interview created but email failed",
        }

        self._log_step("interview_scheduling_complete", {
            "interview_id": interview.id,
            "status": interview.status,
        })

        return result

    def generate_available_slots(
        self,
        days_ahead: int = 14,
        slots_per_day: int = 3,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None,
        recruiter_id: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Generate a list of available interview time slots.
        
        Args:
            days_ahead: Number of days ahead to generate slots (default: 14)
            slots_per_day: Number of slots per day (default: 3)
            start_hour: Start hour (default: from default_working_hours or recruiter settings)
            end_hour: End hour (default: from default_working_hours or recruiter settings)
            recruiter_id: Optional recruiter ID to use their interview settings
        
        Returns:
            List of dicts with 'datetime' (ISO format) and 'display' (human-readable)
        """
        # Get recruiter interview settings if available
        schedule_from_date = None
        schedule_to_date = None
        start_time_obj = None
        end_time_obj = None
        
        if recruiter_id:
            try:
                from django.contrib.auth.models import User
                from recruitment_agent.models import RecruiterInterviewSettings
                recruiter = User.objects.get(id=recruiter_id)
                try:
                    interview_settings = recruiter.recruiter_interview_settings
                    schedule_from_date = interview_settings.schedule_from_date
                    schedule_to_date = interview_settings.schedule_to_date
                    start_time_obj = interview_settings.start_time
                    end_time_obj = interview_settings.end_time
                    interview_time_gap = interview_settings.interview_time_gap
                    
                    # Convert time objects to hours for compatibility
                    if start_time_obj:
                        start_hour = start_time_obj.hour
                    if end_time_obj:
                        end_hour = end_time_obj.hour
                    
                    print(f"\n📅 Using recruiter interview settings:")
                    print(f"   • Schedule from: {schedule_from_date or 'Today'}")
                    print(f"   • Schedule to: {schedule_to_date or 'No limit'}")
                    print(f"   • Time range: {start_time_obj} - {end_time_obj}")
                    print(f"   • Interview time gap: {interview_time_gap} minutes")
                except RecruiterInterviewSettings.DoesNotExist:
                    print(f"   ⚠️  No interview settings found for recruiter, using defaults")
            except User.DoesNotExist:
                pass
        
        # Use defaults if not set from settings
        start_hour = start_hour or self.default_working_hours['start']
        end_hour = end_hour or self.default_working_hours['end']
        
        slots = []
        now = timezone.now()
        
        # Determine start date
        if schedule_from_date:
            current_date = max(now.date(), schedule_from_date)
        else:
            current_date = now.date()
        
        days_generated = 0
        day_offset = 1  # Start from tomorrow (or from schedule_from_date if set)
        
        # Calculate max days to generate based on date range
        if schedule_to_date:
            max_days = (schedule_to_date - current_date).days
            if max_days < 0:
                print(f"⚠️  schedule_to_date is in the past, no slots generated")
                return []
            days_ahead = min(days_ahead, max_days)
        
        while days_generated < days_ahead and len(slots) < (days_ahead * slots_per_day):
            target_date = current_date + timedelta(days=day_offset)
            
            # Check if date is within allowed range
            if schedule_to_date and target_date > schedule_to_date:
                break
            
            day_of_week = target_date.weekday()  # 0 = Monday, 6 = Sunday
            
            # Skip weekends (optional - can be made configurable)
            if day_of_week < 5:  # Monday to Friday
                # Generate slots for this day
                hours_between = end_hour - start_hour
                if hours_between <= 0:
                    day_offset += 1
                    continue
                    
                slot_interval = hours_between / (slots_per_day + 1)
                
                for i in range(slots_per_day):
                    slot_hour = start_hour + (i + 1) * slot_interval
                    
                    # Use time object if available (for minute precision), otherwise use hour only
                    if start_time_obj:
                        slot_minute = start_time_obj.minute if i == 0 else 0
                    else:
                        slot_minute = 0
                    
                    slot_datetime = timezone.make_aware(
                        datetime.combine(target_date, datetime.min.time().replace(hour=int(slot_hour), minute=slot_minute))
                    )
                    
                    # Only add future slots
                    if slot_datetime > now:
                        slots.append({
                            'datetime': slot_datetime.isoformat(),
                            'display': slot_datetime.strftime('%A, %B %d, %Y at %I:%M %p'),
                        })
                        days_generated += 1
                        
                        if len(slots) >= (days_ahead * slots_per_day):
                            break
            
            day_offset += 1
        
        # Return 2-3 slots as per requirements
        return slots[:3]

    def send_invitation_email(
        self,
        interview: Interview,
        available_slots: List[Dict[str, str]],
    ) -> bool:
        """
        Send interview invitation email to candidate.
        
        Args:
            interview: Interview instance
            available_slots: List of available time slots
        
        Returns:
            True if email sent successfully, False otherwise
        """
        print("\n" + "="*60)
        print("📧 SENDING INTERVIEW INVITATION EMAIL")
        print("="*60)
        try:
            # Use job title for subject and body (from job description or truncated job_role)
            job_title = self._get_job_title_for_email(interview)
            clean_job_title = self._clean_email_header(job_title)
            if len(clean_job_title) > 50:
                clean_job_title = clean_job_title[:47] + "..."
            
            subject = f"Interview Invitation - {clean_job_title}"
            
            # Slot selection link: BACKEND URL (Django). Candidate clicks and lands on Django-served page to pick a slot.
            # Set BACKEND_URL in .env to your Django server URL, e.g. http://localhost:8000 or https://api.yourapp.com
            backend_base = (getattr(settings, 'BACKEND_URL', None) or '').strip().replace('\n', '').replace('\r', '')
            if backend_base and not backend_base.startswith('http'):
                backend_base = f'https://{backend_base}'
            slot_selection_url = f"{backend_base}/recruitment/interview/select/{interview.confirmation_token}/" if backend_base else ''
            if slot_selection_url:
                print(f"✓ Slot selection URL: {slot_selection_url}")
            else:
                print("⚠ BACKEND_URL not set in .env – slot selection link will be empty in email")
            
            # Prepare email context (job_title for display in templates)
            context = {
                'candidate_name': interview.candidate_name,
                'job_role': interview.job_role,
                'job_title': job_title,
                'interview_type': interview.interview_type,
                'available_slots': available_slots,
                'interview_id': interview.id,
                'slot_selection_url': slot_selection_url,
            }
            
            print(f"✓ Interview ID: {interview.id}")
            print(f"✓ Candidate: {interview.candidate_name}")
            print(f"✓ Email: {interview.candidate_email}")
            print(f"✓ Job Role: {interview.job_role}")
            print(f"✓ Interview Type: {interview.interview_type}")
            
            # Render email template
            print("\n📝 Rendering email templates...")
            try:
                message = render_to_string('recruitment_agent/emails/interview_invitation.txt', context)
                html_message = render_to_string('recruitment_agent/emails/interview_invitation.html', context)
                print("✓ Templates rendered successfully")
            except Exception as template_error:
                print(f"❌ ERROR: Template rendering failed: {template_error}")
                raise
            
            # Get from email and clean all email addresses
            from_email_raw = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            from_email = self._clean_email_header(from_email_raw)
            to_email = self._clean_email_header(interview.candidate_email)
            email_backend = getattr(settings, 'EMAIL_BACKEND', 'Not configured')
            
            print(f"\n📤 Email Configuration:")
            print(f"  Backend: {email_backend}")
            print(f"  From: {from_email}")
            print(f"  To: {to_email}")
            print(f"  Subject: {subject}")
            
            self._log_step("sending_invitation_email", {
                "interview_id": interview.id,
                "to": interview.candidate_email,
                "from": from_email,
                "subject": subject,
                "backend": email_backend,
            })
            
            # Send email
            print("\n🚀 Attempting to send email...")
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=from_email,
                    recipient_list=[to_email],
                    html_message=html_message,
                    fail_silently=False,  # Raise exception on error
                )
                print("✅ Email sent successfully!")
            except Exception as send_error:
                print(f"❌ ERROR: Email sending failed: {send_error}")
                print(f"   Error Type: {type(send_error).__name__}")
                raise
            
            # Update interview record
            interview.invitation_sent_at = timezone.now()
            interview.save(update_fields=['invitation_sent_at'])
            
            print(f"✓ Timestamp updated: {interview.invitation_sent_at}")
            print("="*60 + "\n")
            
            self._log_step("invitation_email_sent", {
                "interview_id": interview.id,
                "candidate_email": interview.candidate_email,
                "sent_at": interview.invitation_sent_at.isoformat(),
            })
            
            return True
            
        except Exception as exc:
            import traceback
            print(f"\n❌ EXCEPTION OCCURRED:")
            print(f"   Error: {str(exc)}")
            print(f"   Type: {type(exc).__name__}")
            print(f"\n📋 Full Traceback:")
            print(traceback.format_exc())
            print("="*60 + "\n")
            
            error_details = {
                "interview_id": interview.id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
            self._log_error("invitation_email_error", error_details)
            # Still update timestamp to track attempt
            try:
                interview.invitation_sent_at = timezone.now()
                interview.save(update_fields=['invitation_sent_at'])
            except:
                pass
            return False

    def confirm_slot(
        self,
        interview_id: int,
        selected_slot_datetime: str,
    ) -> Dict[str, Any]:
        """
        Confirm a selected interview slot.
        
        Args:
            interview_id: ID of the interview
            selected_slot_datetime: ISO format datetime string of selected slot
        
        Returns:
            Dict with confirmation details
        """
        try:
            interview = Interview.objects.get(id=interview_id)
            
            # Parse and validate the selected slot
            try:
                # Handle ISO format with or without timezone
                if selected_slot_datetime.endswith('Z'):
                    selected_slot_datetime = selected_slot_datetime[:-1] + '+00:00'
                selected_datetime = datetime.fromisoformat(selected_slot_datetime)
                if timezone.is_naive(selected_datetime):
                    selected_datetime = timezone.make_aware(selected_datetime)
            except (ValueError, AttributeError) as e:
                return {
                    "success": False,
                    "error": f"Invalid datetime format: {str(e)}",
                }
            
            # Get recruiter interview settings
            from recruitment_agent.models import RecruiterInterviewSettings
            recruiter = interview.recruiter
            schedule_from_date = None
            schedule_to_date = None
            start_time = None
            end_time = None
            
            if recruiter:
                try:
                    settings = recruiter.recruiter_interview_settings
                    schedule_from_date = settings.schedule_from_date
                    schedule_to_date = settings.schedule_to_date
                    start_time = settings.start_time
                    end_time = settings.end_time
                except RecruiterInterviewSettings.DoesNotExist:
                    # Use defaults
                    from datetime import time as dt_time
                    start_time = dt_time(9, 0)
                    end_time = dt_time(17, 0)
            
            # Validate date range
            selected_date = selected_datetime.date()
            now = timezone.now()
            
            if schedule_from_date:
                if selected_date < schedule_from_date:
                    return {
                        "success": False,
                        "error": f"Selected date is before the allowed start date ({schedule_from_date})",
                    }
            else:
                # Default: can't select past dates
                if selected_date < now.date():
                    return {
                        "success": False,
                        "error": "Cannot select a date in the past",
                    }
            
            if schedule_to_date:
                if selected_date > schedule_to_date:
                    return {
                        "success": False,
                        "error": f"Selected date is after the allowed end date ({schedule_to_date})",
                    }
            
            # Validate time range
            selected_time = selected_datetime.time()
            if start_time and selected_time < start_time:
                return {
                    "success": False,
                    "error": f"Selected time is before the allowed start time ({start_time.strftime('%H:%M')})",
                }
            if end_time and selected_time > end_time:
                return {
                    "success": False,
                    "error": f"Selected time is after the allowed end time ({end_time.strftime('%H:%M')})",
                }
            
            # Check if the selected slot is available in recruiter settings and mark as scheduled atomically
            from django.db import transaction
            
            selected_datetime_str = selected_datetime.strftime('%Y-%m-%dT%H:%M')
            slot_found = False
            slot_available = False
            slot_scheduled = False
            settings = None
            
            if recruiter:
                try:
                    settings = recruiter.recruiter_interview_settings
                    if settings.time_slots_json:
                        # Check if the selected datetime matches an available slot
                        for slot in settings.time_slots_json:
                            slot_datetime = slot.get('datetime', '')
                            # Normalize for comparison
                            slot_datetime_normalized = slot_datetime
                            if 'T' in slot_datetime:
                                date_part, time_part = slot_datetime.split('T')
                                if ':' in time_part:
                                    time_hour_min = ':'.join(time_part.split(':')[:2])
                                    slot_datetime_normalized = f"{date_part}T{time_hour_min}"
                            
                            if slot_datetime_normalized == selected_datetime_str or slot_datetime == selected_datetime_str:
                                slot_found = True
                                slot_available = slot.get('available', True)
                                slot_scheduled = slot.get('scheduled', False)
                                break
                        
                        if not slot_found:
                            return {
                                "success": False,
                                "error": "Selected time slot not found in available slots. Please select a valid time slot.",
                            }
                        
                        if not slot_available:
                            return {
                                "success": False,
                                "error": "This time slot is not available. Please select another time slot.",
                            }
                        
                        if slot_scheduled:
                            return {
                                "success": False,
                                "error": "This time slot is already selected by another candidate. Please select a different time slot.",
                            }
                except RecruiterInterviewSettings.DoesNotExist:
                    pass
            
            # Check for double-booking: same job + same time = only one candidate (doosra bande use select na kr ske)
            existing_q = Interview.objects.filter(
                status__in=['SCHEDULED', 'CONFIRMED'],
                scheduled_datetime=selected_datetime,
            ).exclude(id=interview_id)
            # Same job: only interviews for this job can block the slot
            if interview.cv_record and interview.cv_record.job_description_id:
                existing_q = existing_q.filter(cv_record__job_description_id=interview.cv_record.job_description_id)
            # Same org (company_user or recruiter)
            if interview.company_user_id:
                existing_q = existing_q.filter(company_user_id=interview.company_user_id)
            else:
                existing_q = existing_q.filter(recruiter=recruiter)
            existing_interview = existing_q.first()
            if existing_interview:
                return {
                    "success": False,
                    "error": "This time slot is already taken by another candidate for this position. Please select a different time.",
                }
            
            # Use transaction to atomically mark slot as scheduled and save interview
            with transaction.atomic():
                # Reload settings to get latest data (prevent race condition)
                if recruiter and settings:
                    settings.refresh_from_db()
                    if settings.time_slots_json:
                        # Mark slot as scheduled in time_slots_json
                        slot_marked = False
                        for slot in settings.time_slots_json:
                            slot_datetime = slot.get('datetime', '')
                            slot_datetime_normalized = slot_datetime
                            if 'T' in slot_datetime:
                                date_part, time_part = slot_datetime.split('T')
                                if ':' in time_part:
                                    time_hour_min = ':'.join(time_part.split(':')[:2])
                                    slot_datetime_normalized = f"{date_part}T{time_hour_min}"
                            
                            if slot_datetime_normalized == selected_datetime_str or slot_datetime == selected_datetime_str:
                                # Double-check it's not already scheduled (race condition check)
                                if slot.get('scheduled', False):
                                    return {
                                        "success": False,
                                        "error": "This time slot was just selected by another candidate. Please select a different time slot.",
                                    }
                                # Mark as scheduled
                                slot['scheduled'] = True
                                slot_marked = True
                                break
                        
                        if slot_marked:
                            settings.save()  # Save the updated time_slots_json
                
                # Format display string
                selected_slot_display = selected_datetime.strftime('%A, %B %d, %Y at %I:%M %p')
                
                # Update interview
                interview.status = 'SCHEDULED'
                interview.scheduled_datetime = selected_datetime
                interview.selected_slot = selected_slot_display
                interview.save()
            
            # Send confirmation email
            confirmation_sent = self.send_confirmation_email(interview)
            
            # Trigger automatic follow-up check (signal will handle pre-interview reminders)
            # The signal will automatically check if reminder needs to be sent
            
            result = {
                "success": True,
                "interview_id": interview.id,
                "status": interview.status,
                "scheduled_datetime": interview.scheduled_datetime.isoformat(),
                "confirmation_sent": confirmation_sent,
            }
            
            self._log_step("slot_confirmed", {
                "interview_id": interview.id,
                "scheduled_datetime": interview.scheduled_datetime.isoformat(),
            })
            
            return result
            
        except Interview.DoesNotExist:
            return {
                "success": False,
                "error": "Interview not found",
            }
        except Exception as exc:
            self._log_error("slot_confirmation_error", {
                "interview_id": interview_id,
                "error": str(exc),
            })
            return {
                "success": False,
                "error": str(exc),
            }

    def get_reschedule_slots(self, interview_id: int) -> Dict[str, Any]:
        """
        Get available slots for rescheduling an interview. Returns slots from the
        interview's recruiter/job settings (time_slots_json) with an 'available' flag:
        True if not scheduled by another interview, or scheduled by this interview.
        """
        from recruitment_agent.models import RecruiterInterviewSettings

        try:
            interview = Interview.objects.select_related(
                'cv_record__job_description', 'company_user', 'recruiter'
            ).get(id=interview_id)
        except Interview.DoesNotExist:
            return {"success": False, "error": "Interview not found", "slots": []}

        job = interview.cv_record.job_description if (interview.cv_record and interview.cv_record.job_description_id) else None
        settings = None
        if interview.company_user_id:
            if job:
                settings = RecruiterInterviewSettings.objects.filter(
                    company_user=interview.company_user, job=job
                ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    company_user=interview.company_user, job__isnull=True
                ).first()
        if not settings and interview.recruiter_id:
            if job:
                settings = RecruiterInterviewSettings.objects.filter(
                    recruiter=interview.recruiter, job=job
                ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    recruiter=interview.recruiter, job__isnull=True
                ).first()

        slots_out = []
        time_slots = getattr(settings, 'time_slots_json', None) if settings else None
        if not time_slots:
            return {"success": True, "slots": [], "message": "No slots configured. Add slots in Interview Settings."}

        now = timezone.now()
        current_dt_str = None
        if interview.scheduled_datetime:
            current_dt_str = interview.scheduled_datetime.strftime('%Y-%m-%dT%H:%M')

        for slot in time_slots:
            slot_datetime = slot.get('datetime', '')
            slot_display = slot.get('display', slot_datetime)
            slot_norm = slot_datetime
            if 'T' in slot_datetime and ':' in slot_datetime:
                date_part, time_part = slot_datetime.split('T')
                time_hour_min = ':'.join(time_part.split(':')[:2])
                slot_norm = f"{date_part}T{time_hour_min}"
            # Available if not scheduled, or scheduled by this interview (current slot)
            is_current = current_dt_str and (slot_norm == current_dt_str or slot_datetime == current_dt_str)
            scheduled = slot.get('scheduled', False)
            available = (not scheduled) or is_current
            # Only include future slots (optional: filter past slots for display)
            try:
                dt_parsed = datetime.fromisoformat(slot_datetime.replace('Z', '+00:00'))
                if timezone.is_naive(dt_parsed):
                    dt_parsed = timezone.make_aware(dt_parsed)
                if dt_parsed < now and not is_current:
                    available = False
            except (ValueError, AttributeError):
                pass
            slots_out.append({
                'datetime': slot_datetime,
                'display': slot_display,
                'available': available,
            })

        return {"success": True, "slots": slots_out}

    def reschedule_interview(
        self,
        interview_id: int,
        new_slot_datetime: str,
    ) -> Dict[str, Any]:
        """
        Reschedule an existing interview to a new slot. Unmarks old slot, marks new slot,
        updates interview, and sends reschedule email to candidate.
        """
        from recruitment_agent.models import RecruiterInterviewSettings
        from django.db import transaction
        from datetime import time as dt_time

        try:
            interview = Interview.objects.select_related(
                'cv_record__job_description', 'company_user', 'recruiter'
            ).get(id=interview_id)
        except Interview.DoesNotExist:
            return {"success": False, "error": "Interview not found"}

        job = interview.cv_record.job_description if (interview.cv_record and interview.cv_record.job_description_id) else None
        settings = None
        if interview.company_user_id:
            if job:
                settings = RecruiterInterviewSettings.objects.filter(
                    company_user=interview.company_user, job=job
                ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    company_user=interview.company_user, job__isnull=True
                ).first()
        if not settings and interview.recruiter_id:
            if job:
                settings = RecruiterInterviewSettings.objects.filter(
                    recruiter=interview.recruiter, job=job
                ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    recruiter=interview.recruiter, job__isnull=True
                ).first()

        schedule_from_date = getattr(settings, 'schedule_from_date', None) if settings else None
        schedule_to_date = getattr(settings, 'schedule_to_date', None) if settings else None
        start_time = getattr(settings, 'start_time', None) if settings else dt_time(9, 0)
        end_time = getattr(settings, 'end_time', None) if settings else dt_time(17, 0)

        try:
            if new_slot_datetime.endswith('Z'):
                new_slot_datetime = new_slot_datetime[:-1] + '+00:00'
            selected_datetime = datetime.fromisoformat(new_slot_datetime)
            if timezone.is_naive(selected_datetime):
                selected_datetime = timezone.make_aware(selected_datetime)
        except (ValueError, AttributeError) as e:
            return {"success": False, "error": f"Invalid datetime format: {str(e)}"}

        now = timezone.now()
        selected_date = selected_datetime.date()
        if schedule_from_date and selected_date < schedule_from_date:
            return {"success": False, "error": f"Selected date is before the allowed start date ({schedule_from_date})"}
        if not schedule_from_date and selected_date < now.date():
            return {"success": False, "error": "Cannot select a date in the past"}
        if schedule_to_date and selected_date > schedule_to_date:
            return {"success": False, "error": f"Selected date is after the allowed end date ({schedule_to_date})"}

        # Company can select any future time for reschedule - no start_time/end_time restriction
        # (avoids timezone issues and gives recruiters full flexibility)

        selected_datetime_str = selected_datetime.strftime('%Y-%m-%dT%H:%M')
        existing_q = Interview.objects.filter(
            status__in=['SCHEDULED', 'CONFIRMED'],
            scheduled_datetime=selected_datetime,
        ).exclude(id=interview_id)
        if interview.cv_record and interview.cv_record.job_description_id:
            existing_q = existing_q.filter(cv_record__job_description_id=interview.cv_record.job_description_id)
        if interview.company_user_id:
            existing_q = existing_q.filter(company_user_id=interview.company_user_id)
        else:
            existing_q = existing_q.filter(recruiter=interview.recruiter)
        if existing_q.exists():
            return {"success": False, "error": "This time is already selected by another candidate for this job. Please choose a different time."}

        # Allow any valid datetime (company picker). If the chosen time is in time_slots_json and already scheduled, reject.
        slot_found_in_config = False
        if settings and getattr(settings, 'time_slots_json', None):
            for slot in settings.time_slots_json:
                slot_datetime = slot.get('datetime', '')
                slot_datetime_normalized = slot_datetime
                if 'T' in slot_datetime:
                    date_part, time_part = slot_datetime.split('T')
                    if ':' in time_part:
                        time_hour_min = ':'.join(time_part.split(':')[:2])
                        slot_datetime_normalized = f"{date_part}T{time_hour_min}"
                if slot_datetime_normalized == selected_datetime_str or slot_datetime == selected_datetime_str:
                    slot_found_in_config = True
                    if slot.get('scheduled', False):
                        return {"success": False, "error": "This time is already selected by another candidate for this job. Please choose a different time."}
                    break
            # If not in config, still allow (company can pick any time within range)

        old_scheduled_datetime = interview.scheduled_datetime
        old_datetime_str = old_scheduled_datetime.strftime('%Y-%m-%dT%H:%M') if old_scheduled_datetime else None

        with transaction.atomic():
            # Only update time_slots_json if the selected slot is in the config (unmark old, mark new)
            if settings and getattr(settings, 'time_slots_json', None):
                settings.refresh_from_db()
                if old_datetime_str:
                    for slot in settings.time_slots_json:
                        slot_dt = slot.get('datetime', '')
                        slot_norm = slot_dt
                        if 'T' in slot_dt:
                            dp, tp = slot_dt.split('T')
                            if ':' in tp:
                                slot_norm = f"{dp}T{':'.join(tp.split(':')[:2])}"
                        if slot_norm == old_datetime_str or slot_dt == old_datetime_str:
                            slot['scheduled'] = False
                            break
                if slot_found_in_config:
                    for slot in settings.time_slots_json:
                        slot_dt = slot.get('datetime', '')
                        slot_norm = slot_dt
                        if 'T' in slot_dt:
                            dp, tp = slot_dt.split('T')
                            if ':' in tp:
                                slot_norm = f"{dp}T{':'.join(tp.split(':')[:2])}"
                        if slot_norm == selected_datetime_str or slot_dt == selected_datetime_str:
                            slot['scheduled'] = True
                            break
                    settings.save()

            selected_slot_display = selected_datetime.strftime('%A, %B %d, %Y at %I:%M %p')
            interview.status = 'SCHEDULED'
            interview.scheduled_datetime = selected_datetime
            interview.selected_slot = selected_slot_display
            interview.save(update_fields=['status', 'scheduled_datetime', 'selected_slot', 'updated_at'])

        email_sent = self.send_reschedule_email(interview)
        return {
            "success": True,
            "interview_id": interview.id,
            "scheduled_datetime": interview.scheduled_datetime.isoformat(),
            "selected_slot": selected_slot_display,
            "email_sent": email_sent,
        }

    def send_confirmation_email(self, interview: Interview) -> bool:
        """
        Send confirmation email to candidate and recruiter.
        
        Args:
            interview: Interview instance
        
        Returns:
            True if emails sent successfully, False otherwise
        """
        print("\n" + "="*60)
        print("📧 SENDING INTERVIEW CONFIRMATION EMAILS")
        print("="*60)
        try:
            from_email_raw = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            from_email = self._clean_email_header(from_email_raw)
            email_backend = getattr(settings, 'EMAIL_BACKEND', 'Not configured')
            
            # Use job title for subject and body
            job_title = self._get_job_title_for_email(interview)
            clean_job_title = self._clean_email_header(job_title)
            if len(clean_job_title) > 50:
                clean_job_title = clean_job_title[:47] + "..."
            
            subject = f"Interview Confirmed - {clean_job_title}"
            
            print(f"✓ Interview ID: {interview.id}")
            print(f"✓ Candidate: {interview.candidate_name} ({interview.candidate_email})")
            print(f"✓ Scheduled: {interview.scheduled_datetime}")
            print(f"✓ Email Backend: {email_backend}")
            
            # Candidate confirmation
            print("\n📝 Preparing candidate confirmation email...")
            candidate_context = {
                'candidate_name': interview.candidate_name,
                'job_role': interview.job_role,
                'job_title': job_title,
                'interview_type': interview.interview_type,
                'scheduled_datetime': interview.scheduled_datetime,
                'selected_slot': interview.selected_slot,
            }
            
            try:
                candidate_message = render_to_string('recruitment_agent/emails/interview_confirmation.txt', candidate_context)
                candidate_html = render_to_string('recruitment_agent/emails/interview_confirmation.html', candidate_context)
                print("✓ Candidate email templates rendered")
            except Exception as template_error:
                print(f"❌ ERROR: Candidate template rendering failed: {template_error}")
                raise
            
            to_email = self._clean_email_header(interview.candidate_email)
            
            self._log_step("sending_confirmation_email_candidate", {
                "interview_id": interview.id,
                "to": to_email,
            })
            
            print(f"\n🚀 Sending to candidate: {to_email}")
            try:
                send_mail(
                    subject=subject,
                    message=candidate_message,
                    from_email=from_email,
                    recipient_list=[to_email],
                    html_message=candidate_html,
                    fail_silently=False,
                )
                print("✅ Candidate email sent successfully!")
            except Exception as send_error:
                print(f"❌ ERROR: Candidate email failed: {send_error}")
                raise
            
            # Recruiter notification (if recruiter email available)
            recruiter_email_sent = False
            
            # Get recruiter email: try user email first, then env variable
            recruiter_email = None
            recruiter_name = "Recruiter"
            
            if interview.recruiter and interview.recruiter.email:
                recruiter_email = interview.recruiter.email
                recruiter_name = interview.recruiter.get_full_name() or interview.recruiter.username
            else:
                # Fallback to environment variable
                recruiter_email = getattr(settings, 'RECRUITER_EMAIL', '')
                if recruiter_email:
                    if interview.recruiter:
                        recruiter_name = interview.recruiter.get_full_name() or interview.recruiter.username
                    else:
                        recruiter_name = "Recruiter"
                    print(f"✓ Using recruiter email from environment variable")
            
            if recruiter_email:
                print(f"\n📝 Preparing recruiter notification email...")
                recruiter_context = {
                    'recruiter_name': recruiter_name,
                    'candidate_name': interview.candidate_name,
                    'candidate_email': interview.candidate_email,
                    'job_role': interview.job_role,
                    'job_title': job_title,
                    'interview_type': interview.interview_type,
                    'scheduled_datetime': interview.scheduled_datetime,
                }
                
                # Use job title for recruiter subject
                clean_recruiter_title = self._clean_email_header(job_title)
                if len(clean_recruiter_title) > 40:
                    clean_recruiter_title = clean_recruiter_title[:37] + "..."
                recruiter_subject = f"Interview Scheduled - {interview.candidate_name} for {clean_recruiter_title}"
                
                try:
                    recruiter_message = render_to_string('recruitment_agent/emails/interview_confirmation_recruiter.txt', recruiter_context)
                    recruiter_html = render_to_string('recruitment_agent/emails/interview_confirmation_recruiter.html', recruiter_context)
                    print("✓ Recruiter email templates rendered")
                except Exception as template_error:
                    print(f"❌ ERROR: Recruiter template rendering failed: {template_error}")
                    raise
                
                recruiter_email_clean = self._clean_email_header(recruiter_email)
                
                self._log_step("sending_confirmation_email_recruiter", {
                    "interview_id": interview.id,
                    "to": recruiter_email_clean,
                })
                
                print(f"\n🚀 Sending to recruiter: {recruiter_email_clean}")
                try:
                    send_mail(
                        subject=recruiter_subject,
                        message=recruiter_message,
                        from_email=from_email,
                        recipient_list=[recruiter_email_clean],
                        html_message=recruiter_html,
                        fail_silently=False,
                    )
                    print("✅ Recruiter email sent successfully!")
                    recruiter_email_sent = True
                except Exception as send_error:
                    print(f"❌ ERROR: Recruiter email failed: {send_error}")
                    raise
            else:
                print(f"\n⚠️  No recruiter email configured (skipping recruiter notification)")
                print(f"   Tip: Set RECRUITER_EMAIL in .env file or add email to user account")
            
            interview.confirmation_sent_at = timezone.now()
            interview.save(update_fields=['confirmation_sent_at'])
            
            print(f"\n✓ Confirmation timestamp updated: {interview.confirmation_sent_at}")
            print("="*60 + "\n")
            
            self._log_step("confirmation_emails_sent", {
                "interview_id": interview.id,
                "candidate_email_sent": True,
                "recruiter_email_sent": recruiter_email_sent,
            })
            
            return True
            
        except Exception as exc:
            import traceback
            print(f"\n❌ EXCEPTION OCCURRED:")
            print(f"   Error: {str(exc)}")
            print(f"   Type: {type(exc).__name__}")
            print(f"\n📋 Full Traceback:")
            print(traceback.format_exc())
            print("="*60 + "\n")
            
            error_details = {
                "interview_id": interview.id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
            self._log_error("confirmation_email_error", error_details)
            return False

    def send_reschedule_email(self, interview: Interview) -> bool:
        """Send reschedule notification email to candidate with new date/time. Must go to candidate."""
        try:
            job_title = self._get_job_title_for_email(interview)
            clean_job_title = self._clean_email_header(job_title)
            if len(clean_job_title) > 50:
                clean_job_title = clean_job_title[:47] + "..."
            subject = f"Interview Rescheduled - {clean_job_title}"
            # Include scheduled_datetime so template can show the new time clearly
            scheduled_dt = interview.scheduled_datetime
            scheduled_display = scheduled_dt.strftime('%A, %B %d, %Y at %I:%M %p') if scheduled_dt else (interview.selected_slot or '')
            context = {
                'candidate_name': interview.candidate_name,
                'job_title': job_title,
                'interview_type': interview.interview_type,
                'selected_slot': interview.selected_slot,
                'scheduled_datetime': scheduled_dt,
                'scheduled_display': scheduled_display,
            }
            message = render_to_string('recruitment_agent/emails/interview_rescheduled.txt', context)
            html_message = render_to_string('recruitment_agent/emails/interview_rescheduled.html', context)
            from_email = (getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com') or '').strip()
            from_email = self._clean_email_header(from_email)
            to_email = self._clean_email_header(interview.candidate_email)
            if not to_email:
                print("⚠ Reschedule email skipped: no candidate email for interview", interview.id)
                return False
            send_mail(subject, message, from_email, [to_email], html_message=html_message, fail_silently=False)
            print(f"✓ Reschedule email sent to candidate: {to_email} (interview {interview.id})")
            return True
        except Exception as e:
            print(f"✗ Reschedule email failed for interview {interview.id}: {e}")
            self._log_error("reschedule_email_error", {"interview_id": interview.id, "error": str(e)})
            return False

    def send_followup_reminder(
        self,
        interview_id: int,
    ) -> Dict[str, Any]:
        """
        Send a follow-up reminder if candidate hasn't responded.
        This is for PENDING interviews that haven't been confirmed.
        
        Args:
            interview_id: ID of the interview
        
        Returns:
            Dict with reminder status
        """
        print("\n" + "="*60)
        print("📧 SENDING FOLLOW-UP REMINDER EMAIL")
        print("="*60)
        try:
            interview = Interview.objects.get(id=interview_id)
            
            if interview.status != 'PENDING':
                return {
                    "success": False,
                    "error": f"Interview is not in PENDING status (current: {interview.status})",
                }
            
            # Don't send if interview is in the past
            if interview.scheduled_datetime and interview.scheduled_datetime < timezone.now():
                return {
                    "success": False,
                    "error": "Interview is in the past",
                }
            
            # Send reminder - use job title for subject
            job_title = self._get_job_title_for_email(interview)
            clean_job_title = self._clean_email_header(job_title)
            if len(clean_job_title) > 50:
                clean_job_title = clean_job_title[:47] + "..."
            subject = f"Reminder: Please Confirm Your Interview - {clean_job_title}"
            
            # Slot selection link: BACKEND URL (Django). Set BACKEND_URL in .env.
            backend_base = (getattr(settings, 'BACKEND_URL', None) or '').strip().replace('\n', '').replace('\r', '')
            if backend_base and not backend_base.startswith('http'):
                backend_base = f'https://{backend_base}'
            slot_selection_url = f"{backend_base}/recruitment/interview/select/{interview.confirmation_token}/" if backend_base else ''
            
            available_slots = json.loads(interview.available_slots_json) if interview.available_slots_json else []
            context = {
                'candidate_name': interview.candidate_name,
                'job_role': interview.job_role,
                'job_title': job_title,
                'interview_type': interview.interview_type,
                'available_slots': available_slots,
                'interview_id': interview.id,
                'slot_selection_url': slot_selection_url,
                'followup_number': interview.followup_count + 1,
            }
            
            from_email_raw = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            from_email = self._clean_email_header(from_email_raw)
            to_email = self._clean_email_header(interview.candidate_email)
            email_backend = getattr(settings, 'EMAIL_BACKEND', 'Not configured')
            
            print(f"✓ Interview ID: {interview.id}")
            print(f"✓ Candidate: {interview.candidate_name}")
            print(f"✓ Email: {to_email}")
            print(f"✓ Follow-up #: {interview.followup_count + 1}")
            print(f"✓ Email Backend: {email_backend}")
            
            print("\n📝 Rendering email templates...")
            try:
                message = render_to_string('recruitment_agent/emails/interview_followup.txt', context)
                html_message = render_to_string('recruitment_agent/emails/interview_followup.html', context)
                print("✓ Templates rendered successfully")
            except Exception as template_error:
                print(f"❌ ERROR: Template rendering failed: {template_error}")
                # Fallback to reminder template if followup template doesn't exist
                try:
                    message = render_to_string('recruitment_agent/emails/interview_reminder.txt', context)
                    html_message = render_to_string('recruitment_agent/emails/interview_reminder.html', context)
                    print("✓ Using fallback reminder templates")
                except:
                    raise template_error
            
            self._log_step("sending_followup_reminder", {
                "interview_id": interview.id,
                "to": to_email,
                "followup_number": interview.followup_count + 1,
            })
            
            print(f"\n🚀 Sending follow-up reminder email...")
            print(f"   From: {from_email}")
            print(f"   To: {to_email}")
            print(f"   Subject: {subject[:60]}...")
            try:
                result = send_mail(
                    subject=subject,
                    message=message,
                    from_email=from_email,
                    recipient_list=[to_email],
                    html_message=html_message,
                    fail_silently=False,
                )
                print(f"✅ Follow-up reminder email sent successfully!")
                print(f"   Django send_mail returned: {result} (1 = success)")
                print(f"   📧 Email should be delivered to: {to_email}")
                print(f"   ⚠️  If email not received, check spam folder or email provider settings")
            except Exception as send_error:
                print(f"❌ ERROR: Follow-up reminder email failed: {send_error}")
                print(f"   Error Type: {type(send_error).__name__}")
                import traceback
                print(f"\n📋 Full Traceback:")
                print(traceback.format_exc())
                raise
            
            print(f"✓ Timestamp will be updated by caller")
            print("="*60 + "\n")
            
            self._log_step("followup_reminder_sent", {
                "interview_id": interview.id,
                "followup_number": interview.followup_count + 1,
            })
            
            return {
                "success": True,
                "interview_id": interview.id,
                "message": "Follow-up reminder sent successfully",
            }
            
        except Interview.DoesNotExist:
            print(f"\n❌ ERROR: Interview not found (ID: {interview_id})")
            print("="*60 + "\n")
            return {
                "success": False,
                "error": "Interview not found",
            }
        except Exception as exc:
            import traceback
            print(f"\n❌ EXCEPTION OCCURRED:")
            print(f"   Error: {str(exc)}")
            print(f"   Type: {type(exc).__name__}")
            print(f"\n📋 Full Traceback:")
            print(traceback.format_exc())
            print("="*60 + "\n")
            
            self._log_error("followup_reminder_error", {
                "interview_id": interview_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            })
            return {
                "success": False,
                "error": str(exc),
            }

    def send_pre_interview_reminder(
        self,
        interview_id: int,
        hours_before: int = 24,
    ) -> Dict[str, Any]:
        """
        Send automated reminder before the interview.
        
        Args:
            interview_id: ID of the interview
            hours_before: Hours before interview to send reminder (default: 24)
        
        Returns:
            Dict with reminder status
        """
        try:
            interview = Interview.objects.get(id=interview_id)
            
            if interview.status != 'SCHEDULED' or not interview.scheduled_datetime:
                return {
                    "success": False,
                    "error": "Interview is not scheduled or missing scheduled datetime",
                }
            
            # Calculate when to send reminder
            reminder_time = interview.scheduled_datetime - timedelta(hours=hours_before)
            now = timezone.now()
            
            # Only send if we're within 1 hour of the reminder time
            if abs((reminder_time - now).total_seconds()) > 3600:
                return {
                    "success": False,
                    "error": f"Not the right time to send reminder (should be {hours_before} hours before interview)",
                }
            
            # Send reminder - use job title for subject and body
            job_title = self._get_job_title_for_email(interview)
            clean_job_title = self._clean_email_header(job_title)
            if len(clean_job_title) > 40:
                clean_job_title = clean_job_title[:37] + "..."
            
            if hours_before == 24:
                subject = f"Reminder: Interview Tomorrow - {clean_job_title}"
            else:
                subject = f"Reminder: Interview in {hours_before} hours - {clean_job_title}"
            
            context = {
                'candidate_name': interview.candidate_name,
                'job_role': interview.job_role,
                'job_title': job_title,
                'interview_type': interview.interview_type,
                'scheduled_datetime': interview.scheduled_datetime,
                'selected_slot': interview.selected_slot,
                'hours_before': hours_before,
            }
            
            print("\n" + "="*60)
            print(f"📧 SENDING PRE-INTERVIEW REMINDER ({hours_before}h before)")
            print("="*60)
            print(f"✓ Interview ID: {interview.id}")
            print(f"✓ Candidate: {interview.candidate_name} ({interview.candidate_email})")
            print(f"✓ Scheduled: {interview.scheduled_datetime}")
            
            from_email_raw = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            from_email = self._clean_email_header(from_email_raw)
            to_email = self._clean_email_header(interview.candidate_email)
            email_backend = getattr(settings, 'EMAIL_BACKEND', 'Not configured')
            print(f"✓ Email Backend: {email_backend}")
            
            print("\n📝 Rendering email templates...")
            try:
                message = render_to_string('recruitment_agent/emails/interview_pre_reminder.txt', context)
                html_message = render_to_string('recruitment_agent/emails/interview_pre_reminder.html', context)
                print("✓ Templates rendered successfully")
            except Exception as template_error:
                print(f"❌ ERROR: Template rendering failed: {template_error}")
                raise
            
            self._log_step("sending_pre_interview_reminder", {
                "interview_id": interview.id,
                "to": to_email,
                "hours_before": hours_before,
            })
            
            print(f"\n🚀 Sending pre-interview reminder...")
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=from_email,
                    recipient_list=[to_email],
                    html_message=html_message,
                    fail_silently=False,
                )
                print("✅ Pre-interview reminder sent successfully!")
                print("="*60 + "\n")
            except Exception as send_error:
                print(f"❌ ERROR: Pre-interview reminder failed: {send_error}")
                print(f"   Error Type: {type(send_error).__name__}")
                import traceback
                print(f"\n📋 Full Traceback:")
                print(traceback.format_exc())
                print("="*60 + "\n")
                raise
            
            # Update interview record (timestamp will be updated by management command)
            # interview.pre_interview_reminder_sent_at = timezone.now()
            # interview.save(update_fields=['pre_interview_reminder_sent_at'])
            
            self._log_step("pre_interview_reminder_sent", {
                "interview_id": interview.id,
                "hours_before": hours_before,
            })
            
            return {
                "success": True,
                "interview_id": interview.id,
                "message": f"Pre-interview reminder sent ({hours_before} hours before)",
            }
            
        except Interview.DoesNotExist:
            return {
                "success": False,
                "error": "Interview not found",
            }
        except Exception as exc:
            self._log_error("pre_interview_reminder_error", {
                "interview_id": interview_id,
                "error": str(exc),
            })
            return {
                "success": False,
                "error": str(exc),
            }

    def get_interview_details(self, interview_id: int) -> Optional[Dict[str, Any]]:
        """
        Get interview details.
        
        Args:
            interview_id: ID of the interview
        
        Returns:
            Dict with interview details or None if not found
        """
        try:
            interview = Interview.objects.get(id=interview_id)
            available_slots = json.loads(interview.available_slots_json) if interview.available_slots_json else []
            
            return {
                "interview_id": interview.id,
                "candidate_name": interview.candidate_name,
                "candidate_email": interview.candidate_email,
                "candidate_phone": interview.candidate_phone,
                "job_role": interview.job_role,
                "interview_type": interview.interview_type,
                "status": interview.status,
                "scheduled_datetime": interview.scheduled_datetime.isoformat() if interview.scheduled_datetime else None,
                "selected_slot": interview.selected_slot,
                "available_slots": available_slots,
                "created_at": interview.created_at.isoformat(),
                "updated_at": interview.updated_at.isoformat(),
            }
        except Interview.DoesNotExist:
            return None

    def _log_step(
        self, event_name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an event step"""
        self.log_service.log_event(event_name, metadata or {})

    def _log_error(
        self, event_name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an error"""
        self.log_service.log_error(event_name, metadata or {})

    def _get_job_title_for_email(self, interview: Interview) -> str:
        """Get job title for email display (from job description or truncated job_role)."""
        if interview.cv_record and interview.cv_record.job_description:
            title = (interview.cv_record.job_description.title or '').strip()
            if title:
                return title
        if interview.job_role:
            first_line = (interview.job_role.split('\n')[0] or interview.job_role).strip()
            return self._clean_email_header(first_line)[:80] if first_line else 'the position'
        return 'the position'

    def _clean_email_header(self, text: str) -> str:
        """
        Clean text for use in email headers (subject, from, to).
        Removes newlines, carriage returns, and extra whitespace.
        
        Args:
            text: Text to clean
        
        Returns:
            Cleaned text safe for email headers
        """
        if not text:
            return ""
        
        # Remove newlines, carriage returns, tabs
        cleaned = re.sub(r'[\r\n\t]+', ' ', str(text))
        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        # Strip leading/trailing whitespace
        cleaned = cleaned.strip()
        
        return cleaned

