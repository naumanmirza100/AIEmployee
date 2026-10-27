"""CSAT surveys.

Lives here rather than in the views module so every close path can reach it —
it used to be called from exactly one endpoint (the knowledge-gap task
update), so closing a ticket the normal way created no survey at all, despite
the model documenting "surveys are scheduled on ticket close" (FL-DATA-14).
"""
import logging
import secrets

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

logger = logging.getLogger(__name__)


def customer_email(ticket):
    """The customer's address: the ticket's contact. It used to be `ticket.created_by`, the login that opened the
    ticket — for chat and email tickets the hand-off bot (`noreply-handoff@frontline.local`), for web-form tickets the
    company's first login — so the customer was never asked and staff were asked to rate themselves."""
    contact = getattr(ticket, 'contact', None)
    email = (getattr(contact, 'email', '') or '').strip()
    if email.lower().endswith(('.local', '.invalid')):
        return ''
    return email


def ensure_satisfaction_survey(ticket):
    """Create the survey row and send the invitation. Returns the row or None.

    Safe to call on every close:

    * the row is unique per ticket, and a concurrent close used to turn the
      check-then-create into an uncaught IntegrityError — a 500 on an
      otherwise valid close;
    * a send that failed left `sent_at` NULL and the early return meant it was
      never retried, so the customer was never asked. Now an unsent survey is
      retried the next time a close path runs.
    """
    from Frontline_agent.models import TicketSatisfaction

    if ticket is None:
        return None

    recipient_email = customer_email(ticket)

    survey = TicketSatisfaction.objects.filter(ticket=ticket).first()
    if survey is None:
        if not recipient_email:
            # No-one to ask. Don't create a row, so a later close with a real
            # requester email can still seed the survey.
            logger.info("CSAT skip: ticket %s has no requester email", ticket.id)
            return None
        try:
            survey = TicketSatisfaction.objects.create(
                ticket=ticket, token=secrets.token_urlsafe(32)[:64],
            )
        except IntegrityError:
            # Another close won the race; use its row.
            survey = TicketSatisfaction.objects.filter(ticket=ticket).first()
            if survey is None:
                raise

    if survey.sent_at or not recipient_email:
        return survey

    try:
        from django.core.mail import send_mail
        from Frontline_agent.customer_mail import sender as customer_sender
        # FRONTLINE_PUBLIC_BASE_URL is set nowhere, so the email said "(token: …)" instead of a link; the site's own
        # address (FRONTEND_URL) serves the rating page.
        from core.notification_settings import frontend_url
        public_base = ((getattr(settings, 'FRONTLINE_PUBLIC_BASE_URL', '') or '').rstrip('/')
                       or frontend_url())
        link = f"{public_base}/embed/csat?t={survey.token}" if public_base else f"(token: {survey.token})"
        title = ticket.title or ''
        for label in ('Hand-off: ', 'Call requested: ', 'Problem: ', 'Web form: '):
            if title.startswith(label):
                title = title[len(label):]
        company = getattr(ticket, 'company', None)
        team = (getattr(company, 'name', '') or '').strip() or 'Support Team'
        send_mail(
            subject=f"How did we do? [FL-{ticket.id}]",
            message=(
                f"Hi,\n\n"
                f"Your request \"{title}\" has been resolved. "
                f"Would you mind rating how we did? It takes one click:\n\n"
                f"{link}\n\n"
                f"Thank you — {team}"
            ),
            from_email=customer_sender(company)[0],
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        survey.sent_at = timezone.now()
        survey.save(update_fields=['sent_at'])
    except Exception:
        # Left unsent on purpose: the next close path retries it.
        logger.exception("CSAT email send failed for ticket %s", ticket.id)
    return survey
