from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from core.models import Subtask, Task

# The development test views that used to live here (`ai_agents_test`,
# `test_task_prioritization`, `test_knowledge_qa`, `test_project_pilot`,
# `test_timeline_gantt`, `generate_subtasks`) were removed — audit item SEC-4.
# They were routed at /ai-agents/ and /api/ai/*, bypassed the module-purchase
# gate, rate limits, audit log and per-company API keys, and gave the model
# every user in the system (all companies) to assign tasks to. The React app
# uses the /api/project-manager/ endpoints for all of this.


@login_required
def view_task_subtasks(request, task_id):
    """View all subtasks for a specific task"""
    task = get_object_or_404(Task, id=task_id, project__owner=request.user)
    subtasks = Subtask.objects.filter(task=task).order_by('order', 'created_at')

    return render(request, 'tasks/subtasks.html', {
        'task': task,
        'subtasks': subtasks,
        'project': task.project
    })
