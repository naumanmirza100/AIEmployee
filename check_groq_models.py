"""Resolve the marketing agent's Groq key from the DB and ask Groq which models
this key can actually use. Run: python check_groq_models.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

import requests
from core.models import CompanyAPIKey

# Grab any active Groq key stored for a company (marketing agents use these).
keys = CompanyAPIKey.objects.filter(provider='groq').order_by('-id')
print(f"Groq CompanyAPIKey rows: {keys.count()}")
if not keys:
    print("No Groq keys in DB — nothing to test.")
    raise SystemExit

for k in keys[:5]:
    try:
        raw = k.get_plaintext_key()
    except Exception as e:
        raw = None
        print("  decrypt failed:", e)
    label = f"id={k.id} company={getattr(k,'company_id',None)} agent={getattr(k,'agent_name','?')} mode={getattr(k,'mode','?')}"
    if not raw:
        print(f"\n[{label}] no readable key field, skipping")
        continue
    print(f"\n[{label}] key ...{raw[-6:]}")
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {raw}"},
            timeout=20,
        )
        print("  HTTP", r.status_code)
        if r.status_code == 200:
            data = r.json().get("data", [])
            ids = sorted(m.get("id") for m in data)
            print(f"  {len(ids)} models available:")
            for mid in ids:
                print("   -", mid)
        else:
            print("  body:", r.text[:400])
    except Exception as e:
        print("  ERROR:", e)
