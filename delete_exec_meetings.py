"""
Delete all Executive Meetings organized by meetingcompany@gmail.com (Company #9).
Scoped ONLY to meeting_agent exec meetings — marketing / reply-agent untouched.
CASCADE removes each meeting's participants, notes, action items, documents.

Run:  python manage.py shell < delete_exec_meetings.py
"""
from django.db import transaction
from core.models import CompanyUser
from meeting_agent.models import ExecutiveMeeting

EMAIL = "meetingcompany@gmail.com"

cu_ids = list(CompanyUser.objects.filter(email__iexact=EMAIL).values_list("id", flat=True))
qs = ExecutiveMeeting.objects.filter(organizer_id__in=cu_ids)

print(f"CompanyUser id(s): {cu_ids}")
print(f"Meetings to delete: {qs.count()}")
for m in qs.order_by("scheduled_at"):
    print(f"  #{m.id}  {m.title!r}  status={m.status}")

with transaction.atomic():
    deleted_count, per_model = qs.delete()

print("\nDELETED. Rows removed per model:")
for model, n in per_model.items():
    print(f"  {model}: {n}")
print(f"Total rows: {deleted_count}")

remaining = ExecutiveMeeting.objects.filter(organizer_id__in=cu_ids).count()
print(f"\nVerification — exec meetings remaining for this user: {remaining}")
