# -*- coding: utf-8 -*-
"""Print the EXACT campaign context the Q&A agent sends to the model.

Run:  python debug_qa_data.py

Use this to check whether an answer was invented. Anything the model states
that is not visible here is a hallucination.
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.db.models import Count  # noqa: E402

from project_manager_agent.ai_agents.agents_registry import AgentRegistry  # noqa: E402
from marketing_agent.models import Campaign  # noqa: E402


def w(text):
    """Windows consoles choke on the box-drawing chars in the context."""
    sys.stdout.write(str(text).encode('ascii', 'replace').decode('ascii') + '\n')


# Campaign.owner is a Django User, NOT a CompanyUser — pick the owner that
# actually has campaigns rather than guessing.
owners = (Campaign.objects.values('owner_id', 'owner__username')
          .annotate(n=Count('id')).order_by('-n'))
if not owners:
    w("No campaigns exist in the database at all.")
    sys.exit(1)

w("Campaign owners found:")
for o in owners:
    w("   owner_id=%s  %-30s  %s campaign(s)" % (
        o['owner_id'], o['owner__username'], o['n']))

owner_id = owners[0]['owner_id']
w("")
w("Using owner_id=%s (the one with the most campaigns)" % owner_id)

agent = AgentRegistry.get_agent("marketing_qa")
data = agent._get_marketing_data(owner_id)
campaigns = data.get('campaigns', [])

w("")
w("=" * 78)
w("RAW TARGETING FIELDS PER CAMPAIGN (straight from the DB)")
w("=" * 78)
w("%-20s %-7s %-5s %-10s %-20s %s" % ("NAME", "STATUS", "LEAD", "AGE", "INDUSTRY", "LOCATION"))
w("-" * 78)
for c in campaigns:
    w("%-20s %-7s %-5s %-10s %-20s %s" % (
        (c.get('name') or '')[:20],
        (c.get('status') or '')[:7],
        c.get('leads_count', 0),
        (c.get('age_range') or '-')[:10],
        (c.get('industry') or '-')[:20],
        (c.get('location') or '-'),
    ))

filled = sum(1 for c in campaigns if c.get('industry') or c.get('location'))
w("")
w("%d of %d campaigns have ANY industry/location set." % (filled, len(campaigns)))
if filled == 0:
    w("")
    w(">>> NOTHING has industry/location set. So if the assistant listed")
    w(">>> countries or industries per campaign, it INVENTED all of them.")

w("")
w("=" * 78)
w("FULL CONTEXT STRING SENT TO THE MODEL")
w("=" * 78)
w(agent._build_context(data, None))
