"""
Read-only inspection: what exec-meeting data exists for meetingcompany@gmail.com?
Run:  python manage.py shell < inspect_exec_meetings.py
"""
from core.models import Company, CompanyUser
from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant

EMAIL = "meetingcompany@gmail.com"

print("=" * 60)
print("COMPANIES with this email:")
for c in Company.objects.filter(email__iexact=EMAIL):
    print(f"  Company #{c.id}  name={c.name!r}")

print("\nCOMPANY USERS with this email:")
cu_qs = CompanyUser.objects.filter(email__iexact=EMAIL)
for u in cu_qs:
    print(f"  CompanyUser #{u.id}  {u.full_name!r}  role={u.role}  company=#{u.company_id} {u.company.name!r}")

cu_ids = list(cu_qs.values_list("id", flat=True))

# Meetings where this user is the ORGANIZER
organized = ExecutiveMeeting.objects.filter(organizer_id__in=cu_ids)
print(f"\nMEETINGS ORGANIZED by these user(s): {organized.count()}")
for m in organized.order_by("scheduled_at"):
    print(f"  Meeting #{m.id}  {m.title!r}  status={m.status}  at={m.scheduled_at}")

# Meetings where this user is only a PARTICIPANT (organized by someone else)
part_meeting_ids = (ExecutiveMeetingParticipant.objects
                    .filter(company_user_id__in=cu_ids)
                    .exclude(meeting__organizer_id__in=cu_ids)
                    .values_list("meeting_id", flat=True).distinct())
part_only = ExecutiveMeeting.objects.filter(id__in=part_meeting_ids)
print(f"\nMEETINGS where user is PARTICIPANT ONLY (organized by others): {part_only.count()}")
for m in part_only.order_by("scheduled_at"):
    print(f"  Meeting #{m.id}  {m.title!r}  organizer=#{m.organizer_id}  status={m.status}")

print("=" * 60)
print("SUMMARY: 'delete meetings for this company' would remove the",
      organized.count(), "organized meeting(s) above (CASCADE takes their",
      "participants, notes, action items, documents).")
