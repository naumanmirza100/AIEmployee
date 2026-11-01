with open('ai_sdr_agent/tasks.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = """        # Dual-write to relational history models if available
        try:
            from ai_sdr_agent.models import SDREnrichmentRun, SDREnrichmentAttempt
            db_run = SDREnrichmentRun.objects.create(
                lead=lead,
                company_user=company_user,
                run_id=res.get('run_id', ''),
                status=res.get('enrichment_status', 'completed'),
                providers_called=res.get('summary', {}).get('providers_called', []),
                fields_updated=list(res.get('changes', {}).keys()),
                changes=res.get('changes', {}),
                conflicts_count=len(res.get('contract', {}).get('conflicts', [])),
            )
            for att in res.get('contract', {}).get('provider_attempts', []):
                SDREnrichmentAttempt.objects.create(
                    run=db_run,
                    lead=lead,
                    provider=att.get('provider', ''),
                    target_field=att.get('target_field', ''),
                    status=att.get('status', ''),
                    latency_ms=att.get('latency_ms', 0),
                    error_message=att.get('message') or '',
                )
        except Exception as db_exc:
            logger.debug("Relational persistence skipped for enrichment run: %s", db_exc)

        return res"""

replacement = "        return res"

if target in text:
    text = text.replace(target, replacement, 1)
    print("Cleaned tasks.py (LF)")
else:
    target_crlf = target.replace('\n', '\r\n')
    replacement_crlf = replacement.replace('\n', '\r\n')
    if target_crlf in text:
        text = text.replace(target_crlf, replacement_crlf, 1)
        print("Cleaned tasks.py (CRLF)")
    else:
        print("target not found")

with open('ai_sdr_agent/tasks.py', 'w', encoding='utf-8') as f:
    f.write(text)
