"""
Public meeting booking page — no authentication required.
The booking_token UUID in the URL acts as the credential.
"""
from django.shortcuts import render
from django.http import Http404


def book_meeting(request, token):
    """
    Render the prospect-facing scheduling page.
    The form submits via JS fetch to /api/sdr/book/<token>/confirm/.
    """
    from ai_sdr_agent.models import SDRMeeting

    try:
        meeting = SDRMeeting.objects.select_related(
            'lead', 'enrollment__campaign'
        ).get(booking_token=token)
    except SDRMeeting.DoesNotExist:
        raise Http404("Booking link not found or expired.")

    campaign = (
        meeting.enrollment.campaign
        if meeting.enrollment_id and meeting.enrollment else None
    )

    return render(request, 'ai_sdr_agent/book_meeting.html', {
        'token': str(token),
        'meeting_title': meeting.title or 'Discovery Call',
        'duration_minutes': meeting.duration_minutes or 30,
        'lead_first_name': (
            meeting.lead.first_name
            or (meeting.lead.display_name.split()[0] if meeting.lead.display_name else 'there')
        ),
        'sender_name': campaign.sender_name if campaign else '',
        'sender_title': campaign.sender_title if campaign else '',
        'sender_company': campaign.sender_company if campaign else '',
        'already_booked': meeting.status != 'pending',
        'status': meeting.status,
        'scheduled_at_display': (
            meeting.scheduled_at.strftime('%A, %B %d %Y at %I:%M %p UTC')
            if meeting.scheduled_at else None
        ),
    })
