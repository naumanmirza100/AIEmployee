"""
=============================================================================
  CRM SYNC AGENT - Manual Test Script

  Tests:
    1. CRM Integration list karo (kaunse CRMs connected hain)
    2. HubSpot ping test (connection check)
    3. Queue status dekho (pending/done/failed)
    4. Ek lead manually queue mein daalo
    5. Queue process karo (actual sync)
    6. Sync logs dekho
    7. Failed items retry karo

  Run:
    python test_crm_sync.py
    python test_crm_sync.py --company <company_id>
=============================================================================
"""

import os
import sys
import json
import django
import argparse
from datetime import datetime

# ── Django Setup ─────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

# ── Imports ──────────────────────────────────────────────────────────────────
from core.models import Company
from crm_sync_agent.models import CRMIntegration, CRMSyncQueue, CRMSyncLog, CRMContactMapping
from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent

# ── Argument Parser ──────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--company', type=int, help='Company ID to test with')
args = parser.parse_args()

# ── Colors for terminal output ────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}✓ {msg}{RESET}")
def fail(msg): print(f"  {RED}✗ {msg}{RESET}")
def info(msg): print(f"  {CYAN}→ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}! {msg}{RESET}")
def header(msg): print(f"\n{BOLD}{'='*60}\n  {msg}\n{'='*60}{RESET}")

# ── Pick Company User ─────────────────────────────────────────────────────────
def get_company():
    if args.company:
        try:
            company = Company.objects.get(id=args.company)
            info(f"Using company: {company.name} (ID: {company.id})")
            return company
        except Company.DoesNotExist:
            fail(f"Company ID {args.company} nahi mili")
            sys.exit(1)

    # Pehli company jo CRM integration rakhi ho
    integration = CRMIntegration.objects.select_related('company').first()
    if integration:
        info(f"Auto-picked company: {integration.company.name} (ID: {integration.company.id})")
        return integration.company

    # Koi bhi pehli company
    company = Company.objects.first()
    if company:
        warn(f"Koi CRM integration nahi mili, using first company: {company.name}")
        return company

    fail("Database mein koi company nahi hai")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 1: CRM Integrations List
# ─────────────────────────────────────────────────────────────────────────────
def test_list_integrations(company):
    header("TEST 1: Connected CRM Integrations")
    integrations = CRMIntegration.objects.filter(company=company)

    if not integrations.exists():
        warn("Koi CRM integration nahi mili is company ke liye")
        warn("Pehle Settings > CRM mein jaake HubSpot/Salesforce/Pipedrive connect karo")
        return []

    ok(f"{integrations.count()} integration(s) mili")
    for i in integrations:
        status = f"{GREEN}Active{RESET}" if i.is_active else f"{RED}Inactive{RESET}"
        ping   = f"{GREEN}OK{RESET}" if i.last_ping_ok else f"{RED}FAIL{RESET}"
        print(f"    Provider  : {BOLD}{i.provider.upper()}{RESET}")
        print(f"    Status    : {status}")
        print(f"    Last Ping : {ping} ({i.last_ping_at or 'kabhi nahi'})")
        print(f"    Sync On   : Contacts={i.sync_contacts} | Emails={i.sync_emails} | Meetings={i.sync_meetings} | Notes={i.sync_notes}")
        print()

    return list(integrations)

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 2: CRM Ping (Connection Test)
# ─────────────────────────────────────────────────────────────────────────────
def test_ping(integrations):
    header("TEST 2: CRM Connection Ping Test")

    if not integrations:
        warn("Koi integration nahi — skip")
        return

    from crm_sync_agent.connectors.hubspot    import HubSpotConnector
    from crm_sync_agent.connectors.salesforce import SalesforceConnector
    from crm_sync_agent.connectors.pipedrive  import PipedriveConnector

    connector_map = {
        'hubspot':    HubSpotConnector,
        'salesforce': SalesforceConnector,
        'pipedrive':  PipedriveConnector,
    }

    for integration in integrations:
        provider = integration.provider
        ConnectorClass = connector_map.get(provider)
        if not ConnectorClass:
            warn(f"{provider} ka connector nahi mila")
            continue

        try:
            connector = ConnectorClass(integration.credentials)
            result = connector.ping()
            if result:
                ok(f"{provider.upper()} ping successful — credentials valid hain")
            else:
                fail(f"{provider.upper()} ping failed — credentials check karo")
        except Exception as e:
            fail(f"{provider.upper()} ping error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 3: Queue Status
# ─────────────────────────────────────────────────────────────────────────────
def test_queue_status(company):
    header("TEST 3: CRM Sync Queue Status")

    integrations = CRMIntegration.objects.filter(company=company)
    if not integrations.exists():
        warn("Koi integration nahi — skip")
        return

    total   = CRMSyncQueue.objects.filter(integration__company=company).count()
    pending = CRMSyncQueue.objects.filter(integration__company=company, status='pending').count()
    done    = CRMSyncQueue.objects.filter(integration__company=company, status='done').count()
    failed  = CRMSyncQueue.objects.filter(integration__company=company, status='failed').count()
    processing = CRMSyncQueue.objects.filter(integration__company=company, status='processing').count()

    ok(f"Queue status:")
    print(f"    Total      : {total}")
    print(f"    Pending    : {YELLOW}{pending}{RESET}")
    print(f"    Processing : {CYAN}{processing}{RESET}")
    print(f"    Done       : {GREEN}{done}{RESET}")
    print(f"    Failed     : {RED}{failed}{RESET}")

    if failed > 0:
        warn(f"{failed} failed items hain — Test 6 mein retry hogi")

    return {'pending': pending, 'failed': failed}

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 4: Manually Queue Mein Lead Daalo
# ─────────────────────────────────────────────────────────────────────────────
def test_manual_enqueue(company):
    header("TEST 4: Manually Queue Mein Contact Daalo")

    integration = CRMIntegration.objects.filter(company=company, is_active=True).first()
    if not integration:
        warn("Koi active integration nahi — skip")
        return False

    # Test payload
    test_payload = {
        "email":      "test.lead@example.com",
        "first_name": "Test",
        "last_name":  "Lead",
        "company":    "Test Company Pvt Ltd",
        "job_title":  "CEO",
        "lead_score": 85,
        "lead_status": "hot",
        "source":     "manual_test",
    }

    try:
        # Existing check
        existing = CRMSyncQueue.objects.filter(
            integration=integration,
            object_type='contact',
            source_type='test',
            source_id='999999',
        ).first()

        if existing:
            warn(f"Test item pehle se queue mein hai (status: {existing.status}) — reuse kar rahe hain")
            existing.status = 'pending'
            existing.attempts = 0
            existing.payload = test_payload
            existing.save()
            ok("Existing test item reset karke pending kar diya")
        else:
            item = CRMSyncQueue.objects.create(
                integration=integration,
                object_type='contact',
                operation='create',
                source_type='test',
                source_id='999999',
                payload=test_payload,
                priority=3,
                status='pending',
                attempts=0,
                max_attempts=3,
            )
            ok(f"Naya test contact queue mein add hua (Queue ID: {item.id})")

        info(f"Provider: {integration.provider.upper()}")
        info(f"Payload: {json.dumps(test_payload, indent=6)}")
        return True

    except Exception as e:
        fail(f"Queue mein add karte waqt error: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 5: Queue Process Karo (Actual Sync)
# ─────────────────────────────────────────────────────────────────────────────
def test_process_queue(company):
    header("TEST 5: Queue Process Karo (CRM Ko Bhejo)")

    integration = CRMIntegration.objects.filter(company=company, is_active=True).first()
    if not integration:
        warn("Koi active integration nahi — skip")
        return

    pending_before = CRMSyncQueue.objects.filter(
        integration__company=company, status='pending'
    ).count()
    info(f"Process karne se pehle pending items: {pending_before}")

    try:
        agent = CRMSyncAgent()
        processed = agent.process_pending(company=company, limit=10)
        ok(f"Process complete — {processed} item(s) process kiye gaye")
    except TypeError:
        # Agar company argument support nahi karta
        try:
            agent = CRMSyncAgent()
            processed = agent.process_pending(limit=10)
            ok(f"Process complete — {processed} item(s) process kiye gaye")
        except Exception as e:
            fail(f"Queue process error: {e}")
            return

    pending_after = CRMSyncQueue.objects.filter(
        integration__company=company, status='pending'
    ).count()
    done_after = CRMSyncQueue.objects.filter(
        integration__company=company, status='done'
    ).count()
    failed_after = CRMSyncQueue.objects.filter(
        integration__company=company, status='failed'
    ).count()

    info(f"Process karne ke baad:")
    print(f"    Pending : {YELLOW}{pending_after}{RESET}")
    print(f"    Done    : {GREEN}{done_after}{RESET}")
    print(f"    Failed  : {RED}{failed_after}{RESET}")

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 6: Sync Logs Dekho
# ─────────────────────────────────────────────────────────────────────────────
def test_sync_logs(company):
    header("TEST 6: Recent Sync Logs")

    logs = CRMSyncLog.objects.filter(
        integration__company=company
    ).order_by('-attempted_at')[:10]

    if not logs.exists():
        warn("Abhi tak koi sync log nahi hai")
        return

    ok(f"Last {logs.count()} sync log(s):")
    print()
    for log in logs:
        status_color = GREEN if log.status == 'success' else RED
        print(f"    [{status_color}{log.status.upper()}{RESET}] "
              f"{log.object_type} | "
              f"{log.integration.provider.upper()} | "
              f"{log.attempted_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if log.error_message:
            print(f"           Error: {RED}{log.error_message[:80]}{RESET}")
    print()

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 7: Contact Mappings Dekho
# ─────────────────────────────────────────────────────────────────────────────
def test_contact_mappings(company):
    header("TEST 7: CRM Contact Mappings")

    mappings = CRMContactMapping.objects.filter(
        integration__company=company
    ).order_by('-id')[:5]

    if not mappings.exists():
        warn("Abhi tak koi contact mapping nahi hai (koi sync successful nahi hua)")
        return

    ok(f"Last {mappings.count()} mapping(s) — (hamare lead ID → CRM contact ID):")
    print()
    for m in mappings:
        print(f"    Source: {m.source_type} ID={m.source_id}")
        print(f"    CRM Contact ID : {GREEN}{m.crm_contact_id}{RESET}")
        if m.crm_deal_id:
            print(f"    CRM Deal ID    : {m.crm_deal_id}")
        print()

# ─────────────────────────────────────────────────────────────────────────────
#  TEST 8: Failed Items Retry
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_failed(company):
    header("TEST 8: Failed Items Retry")

    failed_count = CRMSyncQueue.objects.filter(
        integration__company=company, status='failed'
    ).count()

    if failed_count == 0:
        ok("Koi failed item nahi — retry ki zarurat nahi")
        return

    warn(f"{failed_count} failed item(s) hain — retry kar rahe hain...")

    try:
        # Reset failed items to pending
        updated = CRMSyncQueue.objects.filter(
            integration__company=company,
            status='failed',
            attempts__lt=3
        ).update(status='pending')

        ok(f"{updated} item(s) pending mein wapas kar diye gaye")
        info("Ab Test 5 dobara chalao ya 2 minute wait karo Celery ke liye")
    except Exception as e:
        fail(f"Retry error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"\n{BOLD}{CYAN}CRM SYNC TEST SCRIPT{RESET}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'─'*60}")

    company = get_company()

    integrations = test_list_integrations(company)
    test_ping(integrations)
    test_queue_status(company)
    enqueued = test_manual_enqueue(company)
    if enqueued:
        test_process_queue(company)
    test_sync_logs(company)
    test_contact_mappings(company)
    test_retry_failed(company)

    print(f"\n{BOLD}{GREEN}{'='*60}")
    print(f"  TEST COMPLETE")
    print(f"{'='*60}{RESET}\n")
