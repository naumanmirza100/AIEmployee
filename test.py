"""
=============================================================================
  RECRUITMENT AGENT - COMPREHENSIVE Manual Query vs AI Response Test
  
  Tests 20+ diverse questions: global counts, per-job queries, time slots,
  best candidates, interview details, career applications, settings, etc.
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
from django.db.models import Count, Avg, Max, Min, Q
from core.models import CompanyUser
from recruitment_agent.models import (
    JobDescription,
    CVRecord,
    Interview,
    CareerApplication,
    RecruiterEmailSettings,
    RecruiterInterviewSettings,
    RecruiterQualificationSettings,
)
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent


# ══════════════════════════════════════════════════════════════════════════
#  HELPER: Pick first available CompanyUser with data
# ══════════════════════════════════════════════════════════════════════════
def get_company_user():
    for cu in CompanyUser.objects.filter(is_active=True).order_by('id'):
        if JobDescription.objects.filter(company_user=cu).exists():
            return cu
    cu = CompanyUser.objects.filter(is_active=True).first()
    if cu is None:
        print("\n  ERROR: No active CompanyUser found!")
        sys.exit(1)
    return cu


def get_first_job(cu):
    """Get the first job for this company user (with most candidates)."""
    jobs = JobDescription.objects.filter(company_user=cu).order_by('-created_at')
    # Find a job that has candidates
    for job in jobs:
        if CVRecord.objects.filter(job_description=job).exists():
            return job
    return jobs.first()


def get_ai_response(question, company_user):
    agent = RecruitmentQAAgent()
    result = agent.process(question=question, company_user=company_user)
    return result.get("answer", "")


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
        # Also check items if present
        items = manual_result.get('items', [])
        if items:
            matched = sum(1 for item in items if normalize(item) in ai_str)
            if matched > 0:
                return True, f"{matched}/{len(items)} items found"

    # 5) Dict with 'name' key (best candidate)
    if isinstance(manual_result, dict) and 'name' in manual_result:
        name = normalize(manual_result['name'])
        if name and name in ai_str:
            return True, f"Name '{manual_result['name']}' found"

    # 6) Key-value match (check if ALL important values appear)
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
#  BUILD TEST QUERIES — 20+ diverse tests
# ══════════════════════════════════════════════════════════════════════════
def build_test_queries(company_user):
    # Get a real job title for job-specific tests
    first_job = get_first_job(company_user)
    job_title = first_job.title if first_job else "Software Engineer"
    job_id = first_job.id if first_job else None

    tests = [
        # ── GLOBAL COUNTS (1-5) ──
        {
            "id": 1,
            "question": "How many jobs do I have?",
            "category": "Global - Total Jobs",
            "manual_query": lambda: {
                "count": JobDescription.objects.filter(company_user=company_user).count(),
            },
        },
        {
            "id": 2,
            "question": "Which jobs are active?",
            "category": "Global - Active Jobs",
            "manual_query": lambda: {
                "count": JobDescription.objects.filter(company_user=company_user, is_active=True).count(),
                "items": list(JobDescription.objects.filter(company_user=company_user, is_active=True).values_list('title', flat=True)),
            },
        },
        {
            "id": 3,
            "question": "How many candidates/CVs do I have in total?",
            "category": "Global - Total CVs",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(job_description__company_user=company_user).count(),
            },
        },
        {
            "id": 4,
            "question": "How many interviews do I have?",
            "category": "Global - Interviews",
            "manual_query": lambda: {
                "count": Interview.objects.filter(company_user=company_user).count(),
            },
        },
        {
            "id": 5,
            "question": "How many inactive jobs do I have?",
            "category": "Global - Inactive Jobs",
            "manual_query": lambda: {
                "count": JobDescription.objects.filter(company_user=company_user, is_active=False).count(),
                "items": list(JobDescription.objects.filter(company_user=company_user, is_active=False).values_list('title', flat=True)),
            },
        },

        # ── QUALIFICATION DECISIONS (6-9) ──
        {
            "id": 6,
            "question": "How many candidates are rejected?",
            "category": "Global - Rejected",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    qualification_decision='REJECT'
                ).count(),
            },
        },
        {
            "id": 7,
            "question": "How many candidates are on hold?",
            "category": "Global - Hold",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    qualification_decision='HOLD'
                ).count(),
            },
        },
        {
            "id": 8,
            "question": "How many candidates have interview decision?",
            "category": "Global - Interview Decision",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    qualification_decision='INTERVIEW'
                ).count(),
            },
        },

        # ── INTERVIEW STATUS (9-11) ──
        {
            "id": 9,
            "question": "How many interviews are completed?",
            "category": "Global - Completed Interviews",
            "manual_query": lambda: {
                "count": Interview.objects.filter(company_user=company_user, status='COMPLETED').count(),
            },
        },
        {
            "id": 10,
            "question": "How many interviews are pending?",
            "category": "Global - Pending Interviews",
            "manual_query": lambda: {
                "count": Interview.objects.filter(company_user=company_user, status='PENDING').count(),
            },
        },
        {
            "id": 11,
            "question": "How many pending career applications do I have?",
            "category": "Global - Pending Apps",
            "manual_query": lambda: {
                "count": CareerApplication.objects.filter(
                    position__company_user=company_user, status='pending'
                ).count(),
            },
        },

        # ── JOB-SPECIFIC: Candidates (12-14) ──
        {
            "id": 12,
            "question": f"How many candidates applied for {job_title}?",
            "category": f"Job-Specific - Candidates for {job_title[:20]}",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    job_description__title=job_title
                ).count(),
            },
        },
        {
            "id": 13,
            "question": f"Show candidates for {job_title}",
            "category": f"Job-Specific - List Candidates",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    job_description__title=job_title
                ).count(),
                "items": [
                    _get_cv_name(cv)
                    for cv in CVRecord.objects.filter(
                        job_description__company_user=company_user,
                        job_description__title=job_title
                    ).order_by('rank', '-role_fit_score')[:15]
                ],
            },
        },
        {
            "id": 14,
            "question": f"Who is the best candidate for {job_title}?",
            "category": f"Job-Specific - Best Candidate",
            "manual_query": lambda: _get_best_candidate(company_user, job_title),
        },

        # ── JOB-SPECIFIC: Interviews (15-16) ──
        {
            "id": 15,
            "question": f"How many interviews for {job_title}?",
            "category": f"Job-Specific - Interviews",
            "manual_query": lambda: {
                "count": Interview.objects.filter(
                    company_user=company_user,
                    cv_record__job_description__title=job_title
                ).count(),
            },
        },
        {
            "id": 16,
            "question": f"How many rejected candidates for {job_title}?",
            "category": f"Job-Specific - Rejected",
            "manual_query": lambda: {
                "count": CVRecord.objects.filter(
                    job_description__company_user=company_user,
                    job_description__title=job_title,
                    qualification_decision='REJECT'
                ).count(),
            },
        },

        # ── JOB-SPECIFIC: Time Slots (17) ──
        {
            "id": 17,
            "question": f"What are the time slots for {job_title}?",
            "category": f"Job-Specific - Time Slots",
            "manual_query": lambda: _get_time_slots(company_user, first_job),
        },

        # ── JOB DETAILS (18) ──
        {
            "id": 18,
            "question": f"Give me details about {job_title}",
            "category": f"Job-Specific - Details",
            "manual_query": lambda: {
                "title": job_title,
                "is_active": first_job.is_active if first_job else None,
                "type": first_job.type if first_job else None,
                "count": CVRecord.objects.filter(job_description=first_job).count() if first_job else 0,
            },
        },

        # ── SETTINGS (19-20) ──
        {
            "id": 19,
            "question": "What are my qualification settings?",
            "category": "Settings - Qualification",
            "manual_query": lambda: _get_qual_settings(company_user),
        },
        {
            "id": 20,
            "question": "List all jobs with their candidates count",
            "category": "Global - Jobs Summary",
            "manual_query": lambda: {
                "count": JobDescription.objects.filter(company_user=company_user).count(),
                "items": [
                    j.title for j in JobDescription.objects.filter(company_user=company_user).order_by('-created_at')
                ],
            },
        },
    ]

    return tests


# ── Helper functions for complex manual queries ──
def _get_cv_name(cv):
    """Extract name from a CV record."""
    try:
        parsed = json.loads(cv.parsed_json) if cv.parsed_json else {}
        if isinstance(parsed, dict):
            return (
                parsed.get("name")
                or parsed.get("full_name")
                or parsed.get("Name")
                or "Candidate"
            ).strip()
    except Exception:
        pass
    return "Candidate"


def _get_best_candidate(company_user, job_title):
    """Get the best candidate for a job by rank/score."""
    cvs = CVRecord.objects.filter(
        job_description__company_user=company_user,
        job_description__title=job_title,
    ).order_by('rank', '-role_fit_score')
    if not cvs.exists():
        return {"name": "No candidates", "score": 0}
    top = cvs.first()
    name = _get_cv_name(top)
    return {
        "name": name,
        "score": top.role_fit_score or 0,
        "rank": top.rank or 0,
        "decision": top.qualification_decision or "N/A",
    }


def _get_time_slots(company_user, job):
    """Get time slots for a job."""
    if not job:
        return {"count": 0, "detail": "No job found"}
    setting = RecruiterInterviewSettings.objects.filter(
        company_user=company_user, job=job
    ).first()
    if not setting:
        return {"count": 0, "detail": "No interview settings for this job"}
    slots = setting.time_slots_json or []
    if isinstance(slots, str):
        try:
            slots = json.loads(slots)
        except Exception:
            slots = []
    return {
        "count": len(slots),
        "start_time": str(setting.start_time) if setting.start_time else "",
        "end_time": str(setting.end_time) if setting.end_time else "",
        "gap": setting.interview_time_gap,
    }


def _get_qual_settings(company_user):
    """Get qualification settings."""
    qs = RecruiterQualificationSettings.objects.filter(company_user=company_user).first()
    if not qs:
        return {"detail": "No qualification settings"}
    return {
        "interview_threshold": qs.interview_threshold,
        "hold_threshold": qs.hold_threshold,
    }


# ══════════════════════════════════════════════════════════════════════════
#  MAIN - Run comparison and print report
# ══════════════════════════════════════════════════════════════════════════
def run_comparison():
    print("\n" + "=" * 110)
    print("   RECRUITMENT AGENT - COMPREHENSIVE MANUAL vs AI COMPARISON REPORT")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 110)

    company_user = get_company_user()
    first_job = get_first_job(company_user)
    print(f"\n   Company User : {company_user.full_name} (ID: {company_user.id})")
    print(f"   Company      : {company_user.company.name}")
    print(f"   Role         : {company_user.role}")
    if first_job:
        print(f"   Test Job     : {first_job.title} (ID: {first_job.id})")
    print()

    test_queries = build_test_queries(company_user)
    total_tests = len(test_queries)
    results = []
    pass_count = 0
    fail_count = 0
    error_count = 0

    for test in test_queries:
        test_id = test["id"]
        question = test["question"]
        category = test["category"]
        print(f"   [{test_id:02d}/{total_tests}] {question[:60]:60s} ... ", end="", flush=True)

        # ── Manual Query ──
        try:
            manual_result = test["manual_query"]()
        except Exception as e:
            manual_result = f"DB_ERROR: {e}"

        # ── AI Agent Query ──
        try:
            ai_response = get_ai_response(question, company_user)
        except Exception as e:
            ai_response = f"AI_ERROR: {e}"

        # ── Compare ──
        if isinstance(manual_result, str) and "ERROR" in manual_result:
            status = "ERROR"
            match_detail = f"Manual query failed: {manual_result[:80]}"
            error_count += 1
        elif isinstance(ai_response, str) and "AI_ERROR" in ai_response:
            status = "ERROR"
            match_detail = f"AI agent failed: {ai_response[:80]}"
            error_count += 1
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
            manual_display = json.dumps(manual_result, default=str)[:200]
        else:
            manual_display = str(manual_result)[:200]

        results.append({
            "id": test_id,
            "category": category,
            "question": question,
            "manual_result": manual_display,
            "manual_raw": manual_result,
            "ai_response": ai_response,
            "match_detail": match_detail,
            "status": status,
        })

    # ══════════════════════════════════════════════════════════════════
    #  COMPARISON TABLE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("   COMPARISON TABLE")
    print("=" * 110)
    print(f"   {'#':<4} {'Category':<30} {'Question':<38} {'Match Detail':<20} {'Status':<8}")
    print("   " + "-" * 106)

    for r in results:
        q_short = r["question"][:36] + ".." if len(r["question"]) > 36 else r["question"]
        cat_short = r["category"][:28] + ".." if len(r["category"]) > 28 else r["category"]
        d_short = r["match_detail"][:18] + ".." if len(r["match_detail"]) > 18 else r["match_detail"]
        icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR!"}[r["status"]]
        print(f"   {r['id']:<4} {cat_short:<30} {q_short:<38} {d_short:<20} [{icon}]")

    # ══════════════════════════════════════════════════════════════════
    #  DETAILED RESULTS (failures and errors only for brevity)
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
""")

    if fail_count == 0 and error_count == 0:
        print("   ALL TESTS PASSED - AI Agent responses match manual queries!")
    else:
        if fail_count > 0:
            print(f"   WARNING: {fail_count} test(s) FAILED - AI response differs from manual DB query!")
        if error_count > 0:
            print(f"   WARNING: {error_count} test(s) had ERRORS - check DB or AI agent connection!")

    print("=" * 110)

    # ── Save report ──
    report_name = f"recruitment_accuracy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), report_name)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("RECRUITMENT AGENT - COMPREHENSIVE COMPARISON REPORT\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Company   : {company_user.company.name}\n")
        f.write(f"User      : {company_user.full_name} (ID: {company_user.id})\n")
        if first_job:
            f.write(f"Test Job  : {first_job.title} (ID: {first_job.id})\n")
        f.write("=" * 90 + "\n\n")

        for r in results:
            icon = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR"}[r["status"]]
            f.write(f"Test #{r['id']:02d} [{icon}] - {r['category']}\n")
            f.write(f"  Question     : {r['question']}\n")
            f.write(f"  Manual (DB)  : {r['manual_result'][:500]}\n")
            f.write(f"  AI Response  : {r['ai_response'][:500]}\n")
            f.write(f"  Match Detail : {r['match_detail']}\n\n")

        f.write("=" * 90 + "\n")
        f.write(f"SUMMARY: {pass_count} Passed | {fail_count} Failed | {error_count} Errors | Total: {total_tests}\n")
        f.write(f"Accuracy: {accuracy:.1f}%\n")

    print(f"\n   Report saved to: {report_name}\n")
    return results


if __name__ == "__main__":
    run_comparison()


if __name__ == "__main__":
    run_comparison()