"""Run Recruitment's follow-up and reminder check once, by hand.

The check normally runs from Celery beat every five minutes (`recruitment-interview-followups`). This command ran its
own copy, which emailed every waiting candidate of every company on each run, ignored the recruiters' on/off switches
and companies without Recruitment, and never stopped (CO-230). It now runs the same check the scheduler does.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send the follow-ups and reminders that are due now (the same check Celery beat runs)."

    def handle(self, *args, **options):
        from recruitment_agent.tasks import check_and_send_followup_emails
        stats = check_and_send_followup_emails()
        self.stdout.write(f"Follow-ups sent: {stats.get('followups_sent', 0)}, reminders sent: "
                          f"{stats.get('reminders_sent', 0)}, errors: {stats.get('errors', 0)}")
