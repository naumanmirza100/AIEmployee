"""
Signals for the marketing agent app.
Re-activates completed contacts when new steps are added to a sequence.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender='marketing_agent.EmailSequenceStep')
@receiver(post_delete, sender='marketing_agent.EmailSequenceStep')
def reactivate_completed_contacts_on_step_change(sender, instance, **kwargs):
    """
    When a sequence step is added or removed, check if any contacts were marked
    'completed' but haven't actually finished all steps. If so, un-complete them
    so the sequence continues.
    """
    from marketing_agent.models import CampaignContact

    sequence = instance.sequence
    total_steps = sequence.steps.count()

    # Find contacts that are marked completed but have done fewer steps than now exist
    contacts_to_reactivate = CampaignContact.objects.filter(
        sequence=sequence,
        completed=True,
        current_step__lt=total_steps,
    )

    count = contacts_to_reactivate.count()
    if count > 0:
        contacts_to_reactivate.update(completed=False, completed_at=None)
        print(
            f'[SIGNAL] Reactivated {count} contact(s) for sequence "{sequence.name}" '
            f'(now has {total_steps} steps, contacts had done fewer)'
        )
