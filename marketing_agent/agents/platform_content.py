"""
Shared content for platform/website/system and single-agent questions.
Used by Market Research and Marketing Q&A agents so answers stay consistent.
"""

PLATFORM_OVERVIEW = """**What it is:** The **Marketing Agent** is a platform that helps you with market research, Q&A on your marketing data, campaigns, notifications, and outreach—all in one place.

**How to use it:** Use the tabs at the top: **Research** for market/competitor reports, **Q&A** for questions on your campaigns and performance, **Campaigns** to create and run campaigns, **Notifications** for alerts, and **Outreach** for outreach campaigns.

**How to build and run a campaign:** Go to the **Campaigns** tab → create a new campaign (name, goal, audience) → add or import leads → set up your emails and content → launch. You can track performance in the campaign dashboard and ask the **Q&A** agent things like "How is this campaign performing?" or "What's our conversion rate?"

**Agents and what they do:**
• **Research agent** (this tab): Market trends, competitor analysis, customer behavior, opportunities, and risks. Pick a type (General, Market Trend, Competitor, etc.) and enter a topic.
• **Q&A agent**: Answers questions about your campaigns, ROI, conversion, leads, and performance. Use suggested questions or type your own.
• **Campaign agent**: Create and manage marketing campaigns—emails, targeting, launch, and track.
• **Notifications agent**: Alerts and updates on marketing events.
• **Outreach agent**: Run outreach campaigns and follow-ups."""

# When user asks specifically about ONE agent only (e.g. "what does the research agent do?").
AGENT_DETAILS = {
    'research': (
        "**Market & Competitive Research agent:** Gets you reports on **market trends**, **competitors**, **customer behavior**, **opportunities**, and **risks**. "
        "Choose a type (General, Market Trend Analysis, Competitor Analysis, etc.) and enter a topic (e.g. \"web and AI companies\", \"cloud adoption\") to get a full report."
    ),
    'qa': (
        "**Q&A agent:** Answers questions about **your marketing data**—campaigns, ROI, conversion rate, leads, performance. "
        "Use the suggested questions or type your own (e.g. \"How many campaigns?\", \"What's performing best?\")."
    ),
    'campaign': (
        "**Campaign agent:** Create and run **marketing campaigns**. Set name, goal, audience, add leads, design emails, then launch. "
        "Track sends, opens, clicks, and conversions in the campaign dashboard and ask the Q&A agent for performance insights."
    ),
    'notification': (
        "**Notifications agent:** Sends **alerts and notifications** so you stay updated on marketing events and campaign activity."
    ),
    'outreach': (
        "**Outreach agent:** Runs **outreach campaigns** and follow-ups—reach out to leads and manage sequences."
    ),
}

# Phrases that indicate the user is asking about ONE specific agent (order matters: more specific first).
SINGLE_AGENT_PHRASES = [
    ('research', ['research agent', 'market research agent', 'market research tab', 'this research tab', 'research tab']),

    ('qa', ['qa agent', 'q&a agent', 'knowledge qa', 'knowledge q&a', 'qa tab', 'q&a tab', 'this qa tab', 'this agent']),
    ('campaign', ['campaign agent', 'campaigns agent', 'campaign tab', 'campaigns tab', 'how to run campaign', 'how to build campaign', 'how to create campaign']),
    ('notification', ['notification agent', 'notifications agent', 'notification tab', 'notifications tab']),
    ('outreach', ['outreach agent', 'outreach tab', 'outreach campaign agent']),
]


def get_platform_response(question: str) -> str:
    """
    If the question is specifically about one agent, return that agent's detail.
    Otherwise return the full platform overview.
    """
    if not question or not isinstance(question, str):
        return PLATFORM_OVERVIEW
    q = question.strip().lower()
    for agent_key, phrases in SINGLE_AGENT_PHRASES:
        if any(p in q for p in phrases):
            return AGENT_DETAILS.get(agent_key, PLATFORM_OVERVIEW)
    return PLATFORM_OVERVIEW
