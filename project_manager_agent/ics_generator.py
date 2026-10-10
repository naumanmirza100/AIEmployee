"""
ICS (iCalendar) file generator for meeting scheduling.
Generates .ics files that can be imported into Google Calendar, Outlook, Apple Calendar, etc.
"""

from datetime import datetime, timedelta
from django.utils import timezone
import uuid


def generate_meeting_ics(meeting, action='REQUEST') -> str:
    """
    Generate an .ics (iCalendar) file content for a meeting.

    Args:
        meeting: ScheduledMeeting model instance
        action: 'REQUEST' for new/updated meetings, 'CANCEL' for cancelled meetings

    Returns:
        str: iCalendar file content
    """
    # Generate a stable UID based on meeting ID
    uid = f"meeting-{meeting.id}@aiemployee.app"

    # Get times
    start = meeting.proposed_time
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    end = start + timedelta(minutes=meeting.duration_minutes)

    # Format datetimes as iCal UTC format
    now = timezone.now()
    dtstart = _format_dt(start)
    dtend = _format_dt(end)
    dtstamp = _format_dt(now)

    # Organizer info
    organizer_name = meeting.organizer.full_name
    organizer_email = meeting.organizer.email

    # Participants
    attendees = []
    for p in meeting.participants.all().select_related('user'):
        email = p.user.email
        name = p.user.get_full_name() or p.user.username
        if email:
            partstat = 'NEEDS-ACTION'
            if p.status == 'accepted':
                partstat = 'ACCEPTED'
            elif p.status == 'rejected':
                partstat = 'DECLINED'
            elif p.status == 'counter_proposed':
                partstat = 'TENTATIVE'
            attendees.append(f"ATTENDEE;CN={_escape(name)};PARTSTAT={partstat};RSVP=TRUE:mailto:{email}")

    # Fallback to legacy invitee if no participants
    if not attendees and meeting.invitee:
        email = meeting.invitee.email
        name = meeting.invitee.get_full_name() or meeting.invitee.username
        if email:
            attendees.append(f"ATTENDEE;CN={_escape(name)};PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}")

    attendees_str = "\r\n".join(attendees)

    # Description with agenda
    description = meeting.description or ''
    if meeting.agenda:
        agenda_items = [a['item'] for a in meeting.agenda if isinstance(a, dict) and a.get('item')]
        if agenda_items:
            description += "\\n\\nAgenda:\\n" + "\\n".join(f"- {item}" for item in agenda_items)

    # Recurrence rule
    rrule = ""
    if meeting.recurrence and meeting.recurrence != 'none' and not meeting.parent_meeting_id:
        rrule_map = {
            'daily': 'FREQ=DAILY',
            'weekly': f'FREQ=WEEKLY;BYDAY={_weekday_abbr(start)}',
            'weekly_weekdays': 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
            'biweekly': f'FREQ=WEEKLY;INTERVAL=2;BYDAY={_weekday_abbr(start)}',
            'monthly': f'FREQ=MONTHLY;BYMONTHDAY={start.day}',
        }
        rule = rrule_map.get(meeting.recurrence, '')
        if rule:
            if meeting.recurrence_end_date:
                until = datetime.combine(meeting.recurrence_end_date, datetime.max.time())
                if timezone.is_naive(until):
                    until = timezone.make_aware(until)
                rule += f";UNTIL={_format_dt(until)}"
            rrule = f"RRULE:{rule}"

    # Build the METHOD
    method = 'CANCEL' if action == 'CANCEL' else 'REQUEST'
    status = 'CANCELLED' if action == 'CANCEL' else 'CONFIRMED' if meeting.status == 'accepted' else 'TENTATIVE'

    # Build ICS content
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AIEmployee//Meeting Scheduler//EN",
        f"METHOD:{method}",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{_escape(meeting.title)}",
        f"DESCRIPTION:{_escape(description)}",
        f"ORGANIZER;CN={_escape(organizer_name)}:mailto:{organizer_email}",
        f"STATUS:{status}",
        f"SEQUENCE:{_sequence(meeting)}",
    ]

    if rrule:
        lines.append(rrule)

    if attendees_str:
        lines.append(attendees_str)

    # 15-minute reminder
    lines.extend([
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:Reminder: {_escape(meeting.title)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    return "\r\n".join(lines)


def _sequence(meeting) -> int:
    """The file's revision number: how many seconds after the meeting was
    created it last changed.

    A calendar program keeps the copy of an event with the highest SEQUENCE and
    ignores one that is not higher than what it has. Every file used to say 0,
    so a file sent after a meeting moved changed nothing in the invitee's own
    calendar. This number rises with every save of the meeting and costs no
    column to keep.
    """
    created, updated = getattr(meeting, 'created_at', None), getattr(meeting, 'updated_at', None)
    if not created or not updated:
        return 0
    return max(0, int((updated - created).total_seconds()))


def _format_dt(dt) -> str:
    """Format a datetime as iCal UTC string: 20260402T140000Z"""
    utc_dt = dt.astimezone(timezone.utc) if timezone.is_aware(dt) else dt
    return utc_dt.strftime('%Y%m%dT%H%M%SZ')


def _escape(text: str) -> str:
    """Escape special characters for iCal text fields."""
    if not text:
        return ''
    return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _weekday_abbr(dt) -> str:
    """Get iCal weekday abbreviation for a datetime."""
    days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
    return days[dt.weekday()]
