"""When a campaign may start sending, asked the same way everywhere.

Launch made its checks (steps, templates, a sending mailbox, dates) but a scheduled start did not: Schedule took a past
date, Campaign.save made a scheduled campaign active at once, and the 15-minute starter looked for steps only (CO-130).
A launch with a future start date began emailing within five minutes, and one past its end date went on until a daily
job ran (CO-121). "Today" is the company's own day, not the server's.
"""
from datetime import date
from zoneinfo import ZoneInfo

from django.utils import timezone

NO_STEPS = ('No email sequences found. Please create at least one email sequence with steps before launching. '
            'Go to Sequence Management to add sequences.')
NO_TEMPLATES = 'No email templates found. Please create at least one email template before launching the campaign.'
NO_MAILBOX = ('No sending account is set for this campaign. Click "Set sending account" on the campaign and pick the '
              'email account you want to send from before launching.')
INACTIVE_MAILBOX = ('The campaign\'s sending account "{email}" is switched off. Switch it on under Email Accounts, or '
                    'pick another one with "Set sending account".')


def today_for(owner) -> date:
    """Today on the clock of the campaign owner's company; the server's (UTC) day when it has no time zone."""
    from core.logins import company_id_for
    from core.models import Company
    zone = ''
    company_id = company_id_for(owner) if owner is not None else None
    if company_id:
        zone = Company.objects.filter(id=company_id).values_list('timezone_name', flat=True).first() or ''
    try:
        return timezone.now().astimezone(ZoneInfo(zone)).date() if zone else timezone.now().date()
    except Exception:
        return timezone.now().date()


def launch_problem(campaign):
    """(message, code) saying why this campaign cannot start sending now, or None when it can."""
    from marketing_agent.models import EmailSequence, EmailTemplate
    sequences = list(EmailSequence.objects.filter(campaign=campaign))
    if not any(seq.steps.exists() for seq in sequences):
        return NO_STEPS, 'no_steps'
    if not EmailTemplate.objects.filter(campaign=campaign).exists():
        return NO_TEMPLATES, 'no_templates'
    account = campaign.email_account
    if account is None and any(seq.email_account_id is None for seq in sequences):
        return NO_MAILBOX, 'no_email_account'
    if account is not None and not account.is_active:
        return INACTIVE_MAILBOX.format(email=account.email), 'email_account_off'
    return None


def sending_window(campaign, today=None):
    """'early' before the start date, 'over' after the end date, else '' (inside its dates)."""
    today = today or today_for(campaign.owner)
    if campaign.start_date and campaign.start_date > today:
        return 'early'
    if campaign.end_date and campaign.end_date < today:
        return 'over'
    return ''
