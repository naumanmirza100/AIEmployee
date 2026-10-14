"""The sales agent's part when a dashboard login is switched off (core/leavers.py).

Every campaign here is filed under the login that made it. A switched-off
login's campaigns kept sending, kept reading its mailbox with the stored
password and kept answering leads, and nobody else could see or stop them.

Now they are paused the moment the login goes off, the background jobs pass over
anything a switched-off login owns, and an owner or admin can list, open, pause
and delete any campaign in the company (api/views/ai_sdr_agent.py).
"""
from core.leavers import is_admin


def login_switched_off(company_user, by=None) -> str:
    """Pause this login's running and scheduled campaigns. Says how many."""
    from ai_sdr_agent.models import SDRCampaign

    name = company_user.full_name or company_user.email
    reason = (f"Paused: {name}'s login was switched off. It stays paused when the login is switched back on, "
              "until someone resumes it.")[:500]
    running = list(SDRCampaign.objects.filter(company_user=company_user, status__in=('active', 'scheduled')))
    for campaign in running:
        SDRCampaign.objects.filter(pk=campaign.pk).update(status='paused', paused_reason=reason)
    if not running:
        return ''
    titles = ', '.join(f'"{c.name}"' for c in running[:5]) + (f' and {len(running) - 5} more' if len(running) > 5 else '')
    return (f'{len(running)} sales campaign{"" if len(running) == 1 else "s"} of theirs '
            f'{"was" if len(running) == 1 else "were"} paused: {titles}.')


def campaigns_for(company_user):
    """The campaigns this login may see: its own, and for an owner or admin every one in the company."""
    from ai_sdr_agent.models import SDRCampaign

    if is_admin(company_user):
        return SDRCampaign.objects.filter(company_user__company_id=company_user.company_id)
    return SDRCampaign.objects.filter(company_user=company_user)


def owner_of(campaign, viewer) -> dict:
    """Whose campaign this is, for the screen."""
    owner = campaign.company_user
    return {
        'id': owner.id,
        'name': owner.full_name or owner.email,
        'is_you': owner.id == viewer.id,
        'is_active': owner.is_active,
    }
