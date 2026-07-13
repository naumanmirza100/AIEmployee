"""Verify ExecutiveTask parent/subtask nesting end-to-end at the DB + serializer level.
Run: python manage.py shell < test_subtask.py
"""
from core.models import CompanyUser
from meeting_agent.models import ExecutiveTask
from api.views.meeting_agent import _serialize_task

cu = CompanyUser.objects.first()
print("Using company_user:", cu.id, cu.email)

# Clean up any prior test rows
ExecutiveTask.objects.filter(company_user=cu, title__startswith="ZZTEST").delete()

parent = ExecutiveTask.objects.create(company_user=cu, title="ZZTEST parent task")
child = ExecutiveTask.objects.create(company_user=cu, title="ZZTEST child subtask", parent_task=parent)

print("\n-- Raw DB --")
print("parent.id:", parent.id, "parent.parent_task_id:", parent.parent_task_id)
print("child.id:", child.id, "child.parent_task_id:", child.parent_task_id)
print("parent.subtasks:", list(parent.subtasks.values_list("id", "title")))

print("\n-- Top-level list query (what GET /tasks returns) --")
top = ExecutiveTask.objects.filter(company_user=cu, parent_task__isnull=True, title__startswith="ZZTEST")
print("top-level count (should be 1, not 2):", top.count())

print("\n-- Serialized parent --")
s = _serialize_task(parent)
print("subtask_count:", s.get("subtask_count"))
print("subtasks:", [(st["id"], st["title"], st["parent_task_id"]) for st in s.get("subtasks", [])])

# cleanup
ExecutiveTask.objects.filter(company_user=cu, title__startswith="ZZTEST").delete()
print("\nDone (test rows cleaned up).")
