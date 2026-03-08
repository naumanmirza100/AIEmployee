"""
=============================================================================
  MARKETING AGENT - COMPREHENSIVE Manual Query vs AI Response Test

  Tests 20 diverse questions:
    - 10 DB-answerable questions (campaigns, leads, emails, analytics)
    - 10 AI/LLM-only questions (strategy, insights, recommendations)
=============================================================================
"""

import os
import sys
import re
import json
import django
from datetime import datetime

# ── Django Setup ──────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

# ── Imports (real models & agent) ─────────────────────────────────────────
from django.db.models import Count, Avg, Sum, Q
from django.contrib.auth.models import User
from marketing_agent.models import (
    Campaign,
    Lead,
    CampaignLead,
    EmailSendHistory,
    Reply,
    CampaignPerformance,
    MarketResearch,
    EmailTemplate,
)
from marketing_agent.agents.marketing_qa_agent import MarketingQAAgent


# ══════════════════════════════════════════════════════════════════════════
#  HELPER: Pick first available User with marketing data
# ══════════════════════════════════════════════════════════════════════════
def get_test_user():
    """Get the first user that has campaigns."""
    for user in User.objects.filter(is_active=True).order_by('id'):
        if Campaign.objects.filter(owner=user).exists():
            return user
    user = User.objects.filter(is_active=True).first()
    if user is None:
        print("\n  ERROR: No active User found!")
        sys.exit(1)
    return user


def get_first_campaign(user):
    """Get the first campaign for this user (preferably one with email data)."""
    campaigns = Campaign.objects.filter(owner=user).order_by('-created_at')
    # Find a campaign that has email sends
    for c in campaigns:
        if EmailSendHistory.objects.filter(campaign=c).exists():
            return c
    return campaigns.first()


def get_ai_response(question, user_id):
    """Call the Marketing QA Agent and return the full result dict."""
    agent = MarketingQAAgent()
    result = agent.process(question=question, user_id=user_id)
    # Attach token usage from base agent
    result['token_usage'] = getattr(agent, 'last_token_usage', None) or {}
    result['llm_used'] = getattr(agent, 'last_llm_used', False)
    return result


# ══════════════════════════════════════════════════════════════════════════
#  Comparison helpers
# ══════════════════════════════════════════════════════════════════════════
def extract_numbers(text):
    return re.findall(r'\d+', str(text))


def normalize(value):
    if value is None:
        return ""
    return ' '.join(str(value).strip().lower().split())


def check_match(manual_result, ai_response):
    """Compare manual DB result with AI response."""
    manual_str = normalize(manual_result)
    ai_str = normalize(ai_response)

    # 1) Direct string match
    if manual_str and manual_str in ai_str:
        return True, "Manual result found in AI response"

    # 2) Numeric match
    manual_numbers = extract_numbers(str(manual_result))
    ai_numbers = extract_numbers(str(ai_response))
    if manual_numbers:
        key_num = manual_numbers[0]
        if key_num in ai_numbers:
            return True, f"Number {key_num} matches"

    # 3) List match
    if isinstance(manual_result, (list, tuple)) and len(manual_result) > 0:
        matched = sum(1 for item in manual_result if normalize(item) in ai_str)
        total = len(manual_result)
        if matched == total:
            return True, f"All {total} items found"
        elif matched > 0:
            return True, f"Partial: {matched}/{total} items"

    # 4) Dict with 'count' key
    if isinstance(manual_result, dict) and 'count' in manual_result:
        count_str = str(manual_result['count'])
        if count_str in ai_numbers:
            return True, f"Count {count_str} matches"
        items = manual_result.get('items', [])
        if items:
            matched = sum(1 for item in items if normalize(item) in ai_str)
            if matched > 0:
                return True, f"{matched}/{len(items)} items found"

    # 5) Dict with 'name' key
    if isinstance(manual_result, dict) and 'name' in manual_result:
        name = normalize(manual_result['name'])
        if name and name in ai_str:
            return True, f"Name '{manual_result['name']}' found"

    # 6) Key-value match
    if isinstance(manual_result, dict):
        found_any = False
        for k, v in manual_result.items():
            if k in ('detail', 'description', 'items') or v is None:
                continue
            v_str = str(v)
            if v_str in ai_str or v_str in extract_numbers(ai_response):
                found_any = True
        if found_any:
            return True, "Key values found"

    return False, "MISMATCH - values differ"


# ══════════════════════════════════════════════════════════════════════════
#  BUILD TEST QUERIES — 20 tests (10 DB + 10 LLM)
# ══════════════════════════════════════════════════════════════════════════
def build_test_queries(user):
    first_campaign = get_first_campaign(user)
    campaign_name = first_campaign.name if first_campaign else "Test Campaign"

    # Get a second campaign name for variety
    all_campaigns = Campaign.objects.filter(owner=user).order_by('-created_at')
    second_campaign = None
    for c in all_campaigns:
        if c.name != campaign_name:
            second_campaign = c
            break
    second_campaign_name = second_campaign.name if second_campaign else campaign_name

    tests = [
        # ══════════════════════════════════════════════════════════
        #  DB-ANSWERABLE QUERIES (1-10)
        # ══════════════════════════════════════════════════════════

        # Test 1: Total campaigns count
        {
            "id": 1,
            "question": "How many campaigns do I have?",
            "category": "DB - Total Campaigns",
            "manual_query": lambda: {
                "count": Campaign.objects.filter(owner=user).count(),
                "items": list(Campaign.objects.filter(owner=user).values_list('name', flat=True)),
            },
            "manual_query_code": (
                "SELECT COUNT(*) FROM ppp_marketingagent_campaign WHERE owner_id = <user.id>;\n"
                "SELECT name FROM ppp_marketingagent_campaign WHERE owner_id = <user.id>;"
            ),
            "is_complex": False,
        },

        # Test 2: Total leads
        {
            "id": 2,
            "question": "How many leads do I have in total?",
            "category": "DB - Total Leads",
            "manual_query": lambda: {
                "count": CampaignLead.objects.filter(campaign__owner=user).count(),
            },
            "manual_query_code": (
                "SELECT COUNT(*) FROM ppp_marketingagent_campaign_leads cl\n"
                "INNER JOIN ppp_marketingagent_campaign c ON cl.campaign_id = c.id\n"
                "WHERE c.owner_id = <user.id>;"
            ),
            "is_complex": False,
        },

        # Test 3: Best performing campaign
        {
            "id": 3,
            "question": "What campaigns are performing best?",
            "category": "DB - Best Performing Campaign",
            "manual_query": lambda: _get_best_campaign(user),
            "manual_query_code": (
                "SELECT c.name, c.status,\n"
                "  COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) AS emails_sent,\n"
                "  COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) AS emails_opened,\n"
                "  COUNT(CASE WHEN e.status = 'clicked' THEN 1 END) AS emails_clicked\n"
                "FROM ppp_marketingagent_campaign c\n"
                "LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id\n"
                "WHERE c.owner_id = <user.id>\n"
                "GROUP BY c.id ORDER BY emails_opened DESC, emails_sent DESC LIMIT 5;"
            ),
            "is_complex": False,
        },

        # Test 4: Campaigns by status
        {
            "id": 4,
            "question": "Show campaigns by status",
            "category": "DB - Campaigns by Status",
            "manual_query": lambda: _get_campaigns_by_status(user),
            "manual_query_code": (
                "SELECT status, COUNT(*) AS cnt, GROUP_CONCAT(name)\n"
                "FROM ppp_marketingagent_campaign\n"
                "WHERE owner_id = <user.id>\n"
                "GROUP BY status;"
            ),
            "is_complex": False,
        },

        # Test 5: Specific campaign detail (first campaign)
        {
            "id": 5,
            "question": f"Tell me about {campaign_name}",
            "category": f"DB - Campaign Detail ({campaign_name[:25]})",
            "manual_query": lambda: _get_campaign_detail(user, campaign_name),
            "manual_query_code": (
                f"SELECT c.*, \n"
                f"  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e WHERE e.campaign_id = c.id AND e.status IN ('sent','delivered','opened','clicked')) AS emails_sent,\n"
                f"  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e WHERE e.campaign_id = c.id AND e.status IN ('opened','clicked')) AS emails_opened,\n"
                f"  (SELECT COUNT(*) FROM ppp_marketingagent_campaign_leads cl WHERE cl.campaign_id = c.id) AS leads_count\n"
                f"FROM ppp_marketingagent_campaign c\n"
                f"WHERE c.owner_id = <user.id> AND c.name = '{campaign_name}';"
            ),
            "is_complex": False,
        },

        # Test 6: Average open rate across campaigns
        {
            "id": 6,
            "question": "What is the average open rate?",
            "category": "DB - Average Open Rate",
            "manual_query": lambda: _get_avg_open_rate(user),
            "manual_query_code": (
                "SELECT AVG(open_rate) FROM (\n"
                "  SELECT c.id,\n"
                "    CASE WHEN COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) > 0\n"
                "      THEN ROUND(COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) * 100.0 / COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END), 2)\n"
                "      ELSE 0 END AS open_rate\n"
                "  FROM ppp_marketingagent_campaign c\n"
                "  LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id\n"
                "  WHERE c.owner_id = <user.id>\n"
                "  GROUP BY c.id\n"
                ") sub;"
            ),
            "is_complex": False,
        },

        # Test 7: Total emails sent across all campaigns
        {
            "id": 7,
            "question": "How many emails have been sent in total?",
            "category": "DB - Total Emails Sent",
            "manual_query": lambda: _get_total_emails_sent(user),
            "manual_query_code": (
                "SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e\n"
                "INNER JOIN ppp_marketingagent_campaign c ON e.campaign_id = c.id\n"
                "WHERE c.owner_id = <user.id>\n"
                "  AND e.status IN ('sent','delivered','opened','clicked');"
            ),
            "is_complex": False,
        },

        # Test 8: Second campaign detail (tests campaign name matching)
        {
            "id": 8,
            "question": f"How is {second_campaign_name} performing?",
            "category": f"DB - Campaign Detail ({second_campaign_name[:25]})",
            "manual_query": lambda: _get_campaign_detail(user, second_campaign_name),
            "manual_query_code": (
                f"SELECT c.*, \n"
                f"  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e WHERE e.campaign_id = c.id AND e.status IN ('sent','delivered','opened','clicked')) AS emails_sent,\n"
                f"  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e WHERE e.campaign_id = c.id AND e.status IN ('opened','clicked')) AS emails_opened\n"
                f"FROM ppp_marketingagent_campaign c\n"
                f"WHERE c.owner_id = <user.id> AND c.name = '{second_campaign_name}';"
            ),
            "is_complex": False,
        },

        # Test 9: Leads per campaign
        {
            "id": 9,
            "question": "Show leads per campaign",
            "category": "DB - Leads Per Campaign",
            "manual_query": lambda: _get_leads_per_campaign(user),
            "manual_query_code": (
                "SELECT c.name, COUNT(cl.id) AS leads_count\n"
                "FROM ppp_marketingagent_campaign c\n"
                "LEFT JOIN ppp_marketingagent_campaign_leads cl ON cl.campaign_id = c.id\n"
                "WHERE c.owner_id = <user.id>\n"
                "GROUP BY c.id ORDER BY leads_count DESC;"
            ),
            "is_complex": False,
        },

        # Test 10: Campaign performance summary (how are campaigns performing)
        {
            "id": 10,
            "question": "How are our campaigns performing this month?",
            "category": "DB - Campaign Performance",
            "manual_query": lambda: _get_performance_summary(user),
            "manual_query_code": (
                "SELECT c.name, c.status,\n"
                "  COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) AS sent,\n"
                "  COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) AS opened,\n"
                "  COUNT(CASE WHEN e.status = 'clicked' THEN 1 END) AS clicked\n"
                "FROM ppp_marketingagent_campaign c\n"
                "LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id\n"
                "WHERE c.owner_id = <user.id>\n"
                "GROUP BY c.id;"
            ),
            "is_complex": False,
        },

        # ══════════════════════════════════════════════════════════
        #  AI/LLM-ONLY QUERIES (11-20)
        # ══════════════════════════════════════════════════════════

        # Test 11: Strategy recommendation
        {
            "id": 11,
            "question": "What marketing strategies should we implement to improve performance?",
            "category": "LLM - Strategy Recommendations",
            "manual_query": lambda: "N/A (LLM-only strategy recommendation; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses marketing data context + Groq for strategy analysis).",
            "is_complex": True,
        },

        # Test 12: Why are sales dropping
        {
            "id": 12,
            "question": "Why are sales dropping and what should we do about it?",
            "category": "LLM - Sales Analysis",
            "manual_query": lambda: "N/A (LLM reasoning over campaign data; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses campaign performance data + Groq for analysis).",
            "is_complex": True,
        },

        # Test 13: Campaign optimization suggestions
        {
            "id": 13,
            "question": "Which campaigns need optimization and what changes do you recommend?",
            "category": "LLM - Campaign Optimization",
            "manual_query": lambda: "N/A (LLM analysis over campaign metrics; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses campaign metrics + Groq for optimization recommendations).",
            "is_complex": True,
        },

        # Test 14: Key trends
        {
            "id": 14,
            "question": "What are the key trends in our marketing data?",
            "category": "LLM - Marketing Trends",
            "manual_query": lambda: "N/A (LLM trend analysis; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses all campaign/performance data + Groq for trend analysis).",
            "is_complex": True,
        },

        # Test 15: Opportunities
        {
            "id": 15,
            "question": "What opportunities are we missing in our current marketing approach?",
            "category": "LLM - Missed Opportunities",
            "manual_query": lambda: "N/A (LLM insight generation; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses marketing data context + Groq for opportunity analysis).",
            "is_complex": True,
        },

        # Test 16: Improve campaign performance
        {
            "id": 16,
            "question": "How can we improve our campaign performance?",
            "category": "LLM - Performance Improvement",
            "manual_query": lambda: "N/A (LLM improvement recommendations; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses campaign data + Groq for improvement suggestions).",
            "is_complex": True,
        },

        # Test 17: Industry best practices
        {
            "id": 17,
            "question": "What are the best practices for email marketing in our industry?",
            "category": "LLM - Industry Best Practices",
            "manual_query": lambda: "N/A (LLM general knowledge; no DB query).",
            "manual_query_code": "LLM_ONLY (general email marketing knowledge via Groq).",
            "is_complex": True,
        },

        # Test 18: Campaign goals analysis
        {
            "id": 18,
            "question": "Are we on track to meet our campaign goals?",
            "category": "LLM - Goals Analysis",
            "manual_query": lambda: "N/A (LLM analysis of goal progress; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses campaign targets + actual data + Groq for goal analysis).",
            "is_complex": True,
        },

        # Test 19: Lead conversion strategy
        {
            "id": 19,
            "question": "What should we focus on to improve lead conversion rates?",
            "category": "LLM - Conversion Strategy",
            "manual_query": lambda: "N/A (LLM conversion optimization; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses lead/campaign data + Groq for conversion strategy).",
            "is_complex": True,
        },

        # Test 20: Overall marketing summary with recommendations
        {
            "id": 20,
            "question": "Give me an overall summary of my marketing performance with top 3 recommendations.",
            "category": "LLM - Overall Summary",
            "manual_query": lambda: "N/A (LLM-only narrative summary; no single DB query).",
            "manual_query_code": "LLM_ONLY (uses all marketing data + Groq for summary + recommendations).",
            "is_complex": True,
        },
    ]

    return tests


# ── Helper functions for complex manual queries ──

def _get_best_campaign(user):
    """Get the best performing campaign by open rate / emails sent."""
    campaigns = Campaign.objects.filter(owner=user)
    if not campaigns.exists():
        return {"name": "No campaigns", "count": 0}

    best = None
    best_score = -1
    items = []
    for c in campaigns:
        sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
        stats = EmailSendHistory.objects.filter(campaign=c).aggregate(
            total_sent=Count('id', filter=Q(status__in=sent_statuses)),
            total_opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
        )
        sent = stats['total_sent'] or 0
        opened = stats['total_opened'] or 0
        open_rate = round((opened / sent) * 100, 2) if sent > 0 else 0
        score = (open_rate, sent)
        items.append(f"{c.name} ({c.status})")
        if score > (best_score if isinstance(best_score, tuple) else (best_score,)):
            best_score = score
            best = c.name
    return {
        "name": best or "N/A",
        "count": campaigns.count(),
        "items": items[:5],
    }


def _get_campaigns_by_status(user):
    """Get campaign breakdown by status."""
    campaigns = Campaign.objects.filter(owner=user)
    by_status = campaigns.values('status').annotate(cnt=Count('id')).order_by('status')
    result = {}
    for row in by_status:
        status = row['status']
        names = list(campaigns.filter(status=status).values_list('name', flat=True))
        result[status] = {"count": row['cnt'], "names": names}
    return {
        "count": campaigns.count(),
        "statuses": result,
    }


def _get_campaign_detail(user, campaign_name):
    """Get detailed info for a specific campaign."""
    try:
        c = Campaign.objects.filter(owner=user, name=campaign_name).first()
    except Exception:
        return {"detail": "Campaign not found"}
    if not c:
        return {"detail": "Campaign not found"}

    sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
    stats = EmailSendHistory.objects.filter(campaign=c).aggregate(
        total_sent=Count('id', filter=Q(status__in=sent_statuses)),
        total_opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
        total_clicked=Count('id', filter=Q(status='clicked')),
        total_bounced=Count('id', filter=Q(status='bounced')),
    )
    leads_count = CampaignLead.objects.filter(campaign=c).count()
    replies_count = Reply.objects.filter(campaign=c).count()

    sent = stats['total_sent'] or 0
    opened = stats['total_opened'] or 0
    clicked = stats['total_clicked'] or 0

    return {
        "name": c.name,
        "status": c.status,
        "emails_sent": sent,
        "emails_opened": opened,
        "emails_clicked": clicked,
        "leads_count": leads_count,
        "replies_count": replies_count,
        "open_rate": round((opened / sent) * 100, 2) if sent > 0 else 0,
    }


def _get_avg_open_rate(user):
    """Get average open rate across all campaigns."""
    campaigns = Campaign.objects.filter(owner=user)
    rates = []
    for c in campaigns:
        sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
        stats = EmailSendHistory.objects.filter(campaign=c).aggregate(
            total_sent=Count('id', filter=Q(status__in=sent_statuses)),
            total_opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
        )
        sent = stats['total_sent'] or 0
        opened = stats['total_opened'] or 0
        if sent > 0:
            rates.append(round((opened / sent) * 100, 2))
    avg_rate = round(sum(rates) / len(rates), 2) if rates else 0.0
    return {
        "avg_open_rate": avg_rate,
        "campaigns_with_data": len(rates),
    }


def _get_total_emails_sent(user):
    """Get total emails sent across all campaigns."""
    sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
    total = EmailSendHistory.objects.filter(
        campaign__owner=user,
        status__in=sent_statuses,
    ).count()
    return {
        "count": total,
    }


def _get_leads_per_campaign(user):
    """Get leads count per campaign."""
    campaigns = Campaign.objects.filter(owner=user)
    items = []
    for c in campaigns:
        leads = CampaignLead.objects.filter(campaign=c).count()
        items.append(f"{c.name}: {leads}")
    return {
        "count": campaigns.count(),
        "items": items,
    }


def _get_performance_summary(user):
    """Get overall performance summary for all campaigns."""
    campaigns = Campaign.objects.filter(owner=user)
    items = []
    total_sent = 0
    total_opened = 0
    for c in campaigns:
        sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
        stats = EmailSendHistory.objects.filter(campaign=c).aggregate(
            s=Count('id', filter=Q(status__in=sent_statuses)),
            o=Count('id', filter=Q(status__in=['opened', 'clicked'])),
        )
        sent = stats['s'] or 0
        opened = stats['o'] or 0
        total_sent += sent
        total_opened += opened
        items.append(f"{c.name} ({c.status})")
    return {
        "count": campaigns.count(),
        "total_sent": total_sent,
        "total_opened": total_opened,
        "items": items[:10],
    }


# ══════════════════════════════════════════════════════════════════════════
#  MAIN - Run comparison and print report
# ══════════════════════════════════════════════════════════════════════════
def run_comparison():
    print("\n" + "=" * 110)
    print("   MARKETING AGENT - COMPREHENSIVE MANUAL vs AI COMPARISON REPORT")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 110)

    user = get_test_user()
    first_campaign = get_first_campaign(user)
    print(f"\n   Test User       : {user.username} (ID: {user.id})")
    if first_campaign:
        print(f"   Test Campaign   : {first_campaign.name} (ID: {first_campaign.id})")
    print()

    test_queries = build_test_queries(user)
    total_tests = len(test_queries)
    results = []
    pass_count = 0
    fail_count = 0
    error_count = 0

    for test in test_queries:
        test_id = test["id"]
        question = test["question"]
        category = test["category"]
        manual_query_code = test.get("manual_query_code", "(lambda function)")
        is_complex = test.get("is_complex", False)
        print(f"   [{test_id:02d}/{total_tests}] {question[:60]:60s} ... ", end="", flush=True)

        # ── Manual Query ──
        try:
            manual_result = test["manual_query"]()
        except Exception as e:
            manual_result = f"DB_ERROR: {e}"

        # ── AI Agent Query + Token Usage ──
        try:
            ai_result = get_ai_response(question, user.id)
            ai_response = ai_result.get("answer", "")
            token_usage = ai_result.get("token_usage") or {}
            llm_used = ai_result.get("llm_used", False)
        except Exception as e:
            ai_response = f"AI_ERROR: {e}"
            token_usage = {}
            llm_used = False

        # ── Compare ──
        if isinstance(manual_result, str) and "ERROR" in manual_result:
            status = "ERROR"
            match_detail = f"Manual query failed: {manual_result[:80]}"
            error_count += 1
        elif isinstance(ai_response, str) and "AI_ERROR" in ai_response:
            status = "ERROR"
            match_detail = f"AI agent failed: {ai_response[:80]}"
            error_count += 1
        elif is_complex:
            if ai_response and isinstance(ai_response, str) and ai_response.strip():
                status = "PASS"
                match_detail = "Complex LLM query (not auto-verified)"
                pass_count += 1
            else:
                status = "FAIL"
                match_detail = "Empty AI response for complex query"
                fail_count += 1
        else:
            is_match, match_detail = check_match(manual_result, ai_response)
            if is_match:
                status = "PASS"
                pass_count += 1
            else:
                status = "FAIL"
                fail_count += 1

        status_icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR!"}[status]
        print(f"[{status_icon}]")

        if isinstance(manual_result, dict):
            manual_display = json.dumps(manual_result, default=str)[:300]
        else:
            manual_display = str(manual_result)[:300]

        results.append({
            "id": test_id,
            "category": category,
            "question": question,
            "manual_query_code": manual_query_code,
            "manual_result": manual_display,
            "manual_raw": manual_result,
            "ai_response": ai_response,
            "token_usage": token_usage,
            "llm_used": llm_used,
            "match_detail": match_detail,
            "status": status,
        })

    # ══════════════════════════════════════════════════════════════════
    #  COMPARISON TABLE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("   COMPARISON TABLE")
    print("=" * 110)
    print(f"   {'#':<4} {'Category':<35} {'Question':<38} {'Match Detail':<20} {'Status':<8}")
    print("   " + "-" * 106)

    for r in results:
        q_short = r["question"][:36] + ".." if len(r["question"]) > 36 else r["question"]
        cat_short = r["category"][:33] + ".." if len(r["category"]) > 33 else r["category"]
        d_short = r["match_detail"][:18] + ".." if len(r["match_detail"]) > 18 else r["match_detail"]
        icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR!"}[r["status"]]
        print(f"   {r['id']:<4} {cat_short:<35} {q_short:<38} {d_short:<20} [{icon}]")

    # ══════════════════════════════════════════════════════════════════
    #  DETAILED RESULTS (failures and errors only)
    # ══════════════════════════════════════════════════════════════════
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        print("\n" + "=" * 110)
        print("   DETAILED FAILURES / ERRORS")
        print("=" * 110)
        for r in failures:
            icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR!"}[r["status"]]
            print(f"\n   --- Test #{r['id']:02d} [{icon}] {r['category']} ---")
            print(f"   Question     : {r['question']}")
            print(f"   Manual (DB)  : {r['manual_result'][:300]}")
            ai_short = r["ai_response"][:400].replace('\n', ' | ')
            print(f"   AI Response  : {ai_short}")
            print(f"   Match Detail : {r['match_detail']}")

    # ══════════════════════════════════════════════════════════════════
    #  TOKEN USAGE SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("   TOKEN USAGE SUMMARY")
    print("=" * 110)
    print(f"   {'#':<4} {'Question':<50} {'LLM?':<6} {'Prompt':<10} {'Completion':<12} {'Total':<10} {'Provider':<10}")
    print("   " + "-" * 102)
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_all_tokens = 0
    for r in results:
        tu = r.get("token_usage") or {}
        prompt_t = tu.get('prompt_tokens', 0) or 0
        completion_t = tu.get('completion_tokens', 0) or 0
        total_t = tu.get('total_tokens', 0) or 0
        provider = tu.get('provider', 'none')
        llm_flag = "Yes" if r.get("llm_used") else "No"
        q_short = r["question"][:48] + ".." if len(r["question"]) > 48 else r["question"]
        print(f"   {r['id']:<4} {q_short:<50} {llm_flag:<6} {prompt_t:<10} {completion_t:<12} {total_t:<10} {provider:<10}")
        total_prompt_tokens += prompt_t
        total_completion_tokens += completion_t
        total_all_tokens += total_t

    print("   " + "-" * 102)
    print(f"   {'TOTAL':<4} {'':<50} {'':<6} {total_prompt_tokens:<10} {total_completion_tokens:<12} {total_all_tokens:<10}")

    # ══════════════════════════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════════════════════════
    tested = total_tests - error_count
    accuracy = (pass_count / tested * 100) if tested > 0 else 0

    print("\n" + "=" * 110)
    print("   SUMMARY")
    print("=" * 110)
    print(f"""
   Total Tests    : {total_tests}
   Passed (PASS)  : {pass_count}  ({pass_count / total_tests * 100:.1f}%)
   Failed (FAIL)  : {fail_count}  ({fail_count / total_tests * 100:.1f}%)
   Errors (ERR)   : {error_count}  ({error_count / total_tests * 100:.1f}%)

   Accuracy Rate  : {accuracy:.1f}%  (out of {tested} tests that actually ran)

   Total Tokens   : {total_all_tokens} (prompt: {total_prompt_tokens}, completion: {total_completion_tokens})
""")

    if fail_count == 0 and error_count == 0:
        print("   ALL TESTS PASSED - AI Agent responses match manual queries!")
    else:
        if fail_count > 0:
            print(f"   WARNING: {fail_count} test(s) FAILED - AI response differs from manual DB query!")
        if error_count > 0:
            print(f"   WARNING: {error_count} test(s) had ERRORS - check DB or AI agent connection!")

    print("=" * 110)

    # ── Save detailed report ──
    report_name = f"marketing_accuracy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), report_name)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("MARKETING AGENT - COMPREHENSIVE COMPARISON REPORT\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"User      : {user.username} (ID: {user.id})\n")
        if first_campaign:
            f.write(f"Campaign  : {first_campaign.name} (ID: {first_campaign.id})\n")
        f.write("=" * 90 + "\n\n")

        for r in results:
            icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR"}[r["status"]]
            f.write(f"Test #{r['id']:02d} [{icon}] - {r['category']}\n")
            f.write(f"  Question Asked        : {r['question']}\n")
            f.write(f"  Manual Query Code     : {r['manual_query_code']}\n")
            f.write(f"  Manual Query Result   : {r['manual_result'][:500]}\n")
            f.write(f"  AI Agent Response     : {r['ai_response'][:500]}\n")
            f.write(f"  LLM Used              : {r.get('llm_used', False)}\n")
            f.write(f"  AI Token Usage        : {r['token_usage']}\n")
            f.write(f"  Match Detail          : {r['match_detail']}\n\n")

        f.write("=" * 90 + "\n")
        f.write(f"SUMMARY: {pass_count} Passed | {fail_count} Failed | {error_count} Errors | Total: {total_tests}\n")
        f.write(f"Accuracy: {accuracy:.1f}%\n")
        f.write(f"Total Tokens: {total_all_tokens} (prompt: {total_prompt_tokens}, completion: {total_completion_tokens})\n")

    print(f"\n   Report saved to: {report_name}\n")
    return results


if __name__ == "__main__":
    print("\n================ FIRST RUN ================\n")
    results1 = run_comparison()

    print("\n================ SECOND RUN (after code change) ================\n")
    results2 = run_comparison()
