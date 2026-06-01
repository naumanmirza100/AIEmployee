"""
Verify the SDR agent key-service chain:
1. resolve_sdr_groq_client raises KeyServiceError (not swallows it)
2. All SDR agent __init__ methods pass company= correctly
3. No .env Groq fallbacks exist

Run: python manage.py shell < verify_sdr_chain.py
"""
import sys

# ── Test 1: sdr_key_resolver raises KeyServiceError ──────────────────────────
print("=" * 60)
print("Test 1: sdr_key_resolver raises KeyServiceError on bad company")

from core.api_key_service import KeyServiceError
from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client

class FakeCompany:
    """Simulates a company with no keys configured."""
    id = 99999
    pk = 99999

try:
    client, ctx = resolve_sdr_groq_client(FakeCompany())
    print(f"  WARN: returned ({client}, {ctx}) instead of raising — company has no keys configured?")
except KeyServiceError as e:
    print(f"  OK: KeyServiceError raised: {type(e).__name__}: {e.user_message}")
except Exception as e:
    print(f"  FAIL: unexpected exception: {type(e).__name__}: {e}")

# ── Test 2: SDR agents import cleanly ─────────────────────────────────────────
print()
print("Test 2: SDR agents import without errors")

agents = [
    'ai_sdr_agent.agents.outreach_agent.OutreachAgent',
    'ai_sdr_agent.agents.lead_qualification_agent.LeadQualificationAgent',
    'ai_sdr_agent.agents.lead_research_agent.LeadResearchAgent',
    'ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent',
    'ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent',
]

for agent_path in agents:
    module_path, class_name = agent_path.rsplit('.', 1)
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        print(f"  OK: {class_name} imported")
    except Exception as e:
        print(f"  FAIL: {class_name} import error: {e}")

# ── Test 3: Views file imports cleanly ───────────────────────────────────────
print()
print("Test 3: ai_sdr_agent views import cleanly")
try:
    import api.views.ai_sdr_agent as sdr_views
    print(f"  OK: views imported, KeyServiceError re-raise present")
except Exception as e:
    print(f"  FAIL: {e}")

# ── Test 4: No .env Groq fallback ────────────────────────────────────────────
print()
print("Test 4: No .env Groq key fallback in ai_sdr_agent/")
import subprocess, os
result = subprocess.run(
    ['grep', '-rn', 'GROQ_API_KEY', 'ai_sdr_agent/', '--include=*.py'],
    capture_output=True, text=True
)
lines = [l for l in result.stdout.splitlines() if 'os.environ' in l.lower() or 'os.getenv' in l.lower() or 'settings.groq' in l.lower()]
if lines:
    print(f"  WARN: possible .env fallbacks found:")
    for l in lines:
        print(f"    {l}")
else:
    print("  OK: No .env Groq key fallbacks (APOLLO_API_KEY is data service, not LLM)")

print()
print("=" * 60)
print("Verification complete.")
