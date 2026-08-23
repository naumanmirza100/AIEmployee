# -*- coding: utf-8 -*-
"""Diagnose why campaign auto-fill returns empty fields.

Run:  python debug_autofill.py

(Standalone — sets up Django itself. Do NOT pipe into `manage.py shell`,
which feeds lines one at a time and breaks on indentation.)
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from project_manager_agent.ai_agents.agents_registry import AgentRegistry  # noqa: E402
from core.models import CompanyUser  # noqa: E402

print("=" * 72)
print("CAMPAIGN AUTO-FILL DIAGNOSTIC")
print("=" * 72)

company_user = CompanyUser.objects.filter(company_id__isnull=False).order_by('-id').first()
if not company_user:
    print("NO CompanyUser with a company_id found - cannot resolve an API key.")
    sys.exit(1)

print("CompanyUser :", company_user)
print("Company id  :", company_user.company_id)

agent = AgentRegistry.get_agent("outreach_campaign")
agent.last_token_usage = None
agent.last_llm_used = False
agent.company_id = company_user.company_id
agent.agent_key_name = 'marketing_agent'
print("Model       :", getattr(agent, 'model', None))

# ---- 1. The real auto-fill call ----------------------------------------
result = agent.auto_fill_campaign(
    user_id=getattr(company_user, 'id', None),
    campaign_data={
        'name': 'age neg',
        'description': 'compagin with negative 70 ages',
        'start_date': '2026-08-20',
        'end_date': '2026-08-27',
    },
)

fields = result.get('suggested_fields') or {}
filled = {k: v for k, v in fields.items() if v not in (None, '')}

print()
print("-" * 72)
print("RESULT")
print("-" * 72)
print("success :", result.get('success'))
print("error   :", result.get('error'))
print("warning :", result.get('warning'))
print()
for k, v in fields.items():
    print("   %-20s %r" % (k, v))

# ---- 2. Raw reply -------------------------------------------------------
print()
print("-" * 72)
print("RAW MODEL REPLY")
print("-" * 72)
raw = None
try:
    raw = agent._call_llm_for_reasoning(
        'Reply with ONLY this JSON and nothing else: '
        '{"target_leads": 1500, "industry": "Technology"}',
        agent.system_prompt, temperature=0.4, max_tokens=1500,
    )
    print("length      :", len(raw or ''))
    print("has <think> :", '<think>' in (raw or '').lower())
    print("has '{'     :", '{' in (raw or ''))
    print()
    print(raw)
except Exception as e:
    print("raw call FAILED:", type(e).__name__, e)

# ---- 3. Verdict ---------------------------------------------------------
print()
print("-" * 72)
print("VERDICT")
print("-" * 72)
if result.get('success') is False:
    print("FAIL - the call errored:", result.get('error'))
    print("       Likely an API key / quota issue, not parsing.")
elif len(filled) <= 1:
    print("FAIL - still empty (%d field populated)." % len(filled))
    if raw and '<think>' in raw.lower():
        print("       Model IS emitting <think> blocks.")
    if raw and '{' not in raw:
        print("       Model returned NO JSON at all - it ignored the format.")
    print("       Send me the RAW MODEL REPLY above.")
else:
    print("PASS - %d fields populated. Fix worked." % len(filled))
    for k, v in filled.items():
        print("       %-20s %r" % (k, v))
    print("       Try it in the browser now.")
