# Frontline_agent/agent_logic.py

from django.contrib.auth.models import User

#from Frontline_agent.models import Document
from core.models import Project  # only import what EXISTS


# =========================
# SYSTEM PROMPT
# =========================
SYSTEM_PROMPT = """
You are Frontline AI Customer Support for PayPerProject.
You respond professionally, politely, and clearly.
You only answer using PayPerProject database information.
"""


# =========================
# Database Helpers
# =========================

def get_documents(limit=5):
    docs = Document.objects.all()[:limit]
    return [
        {
            "id": d.id,
            "title": d.title,
            "type": d.document_type,
            "uploaded_by": d.uploaded_by.username if d.uploaded_by else None,
        }
        for d in docs
    ]


def get_projects(limit=5):
    projects = Project.objects.all()[:limit]
    return [
        {
            "id": p.id,
            "title": getattr(p, "title", "N/A"),
            "status": getattr(p, "status", "N/A"),
        }
        for p in projects
    ]


def get_users(limit=5):
    users = User.objects.all()[:limit]
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
        }
        for u in users
    ]


# =========================
# Main Agent Function
# =========================

def agent_reply(user_input):
    text = user_input.lower().strip()

    # 1️⃣ Greetings (VERY IMPORTANT)
    if text in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]:
        return (
            "👋 Hello! Welcome to PayPerProject Support.\n\n"
            "I’m your **Frontline AI Customer Support Agent**. I can help you with:\n"
            "• Project details\n"
            "• Documents & files\n"
            "• Tickets & issues\n"
            "• Users & roles\n\n"
            "How can I assist you today?"
        )

    # 2️⃣ Document queries
    if "document" in text:
        docs = get_documents()
        if not docs:
            return "📄 There are currently no documents available in the system."
        return f"📄 Here are some documents:\n{docs}"

    # 3️⃣ Project queries
    if "project" in text:
        projects = get_user_projects(user_id=1)  # demo user
        if not projects:
            return "📁 No projects found for this user."
        return f"📁 Here are the projects:\n{projects}"

    # 4️⃣ User queries
    if "user" in text:
        users = get_users()
        return f"👥 Registered users:\n{users}"

    # 5️⃣ Fallback to AI (ONLY for real questions)
    return generate_response(user_input, SYSTEM_PROMPT)
