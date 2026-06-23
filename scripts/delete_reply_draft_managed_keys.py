from core.models import CompanyAPIKey, KeyRequest

def clean_agent(agent):
    print(f"\n--- {agent} ---")
    keys = CompanyAPIKey.objects.filter(agent_name=agent, mode='managed')
    key_ids = list(keys.values_list('id', flat=True))
    if key_ids:
        nulled = KeyRequest.objects.filter(linked_key_id__in=key_ids).update(linked_key_id=None)
        print(f"  Nulled linked_key_id on {nulled} KeyRequest(s).")
    count = keys.count()
    print(f"  Keys found: {count}")
    for k in keys:
        print(f"  Deleting key id={k.id} company={k.company.name} status={k.status}")
    if count:
        keys.delete()
        print(f"  Deleted {count} managed key(s).")
    reqs = KeyRequest.objects.filter(agent_name=agent)
    req_count = reqs.count()
    print(f"  Requests found: {req_count}")
    for r in reqs:
        print(f"  Deleting KeyRequest id={r.id} status={r.status}")
    if req_count:
        reqs.delete()
        print(f"  Deleted {req_count} KeyRequest(s).")

clean_agent('reply_draft_agent')
clean_agent('marketing_agent')
print("\nDone.")
