# A company's own AI key was saved but never used: every agent starts on the
# 'managed' key preference, and resolve_for_call skips the company's key while
# that preference stands. Saving a key now sets the preference to 'byok'. This
# does the same for keys saved before: where an agent has an active key of the
# company's own and no active managed key, the preference could only have
# meant "free tokens", which nobody who had just added a key intended.
# Rows set to 'free' or 'none' were chosen by hand and are left alone.

from django.db import migrations
from django.db.models import Q


def use_saved_keys(apps, schema_editor):
    CompanyAPIKey = apps.get_model('core', 'CompanyAPIKey')
    AgentTokenQuota = apps.get_model('core', 'AgentTokenQuota')

    own = set(CompanyAPIKey.objects.filter(mode='byok', status='active').values_list('company_id', 'agent_name'))
    managed = set(CompanyAPIKey.objects.filter(mode='managed', status='active')
                  .values_list('company_id', 'agent_name'))
    ids = [quota_id for quota_id, company_id, agent_name in
           AgentTokenQuota.objects.filter(Q(preferred_pool='managed') | Q(preferred_pool='') | Q(preferred_pool__isnull=True))
           .values_list('id', 'company_id', 'agent_name')
           if (company_id, agent_name) in own and (company_id, agent_name) not in managed]
    if ids:
        AgentTokenQuota.objects.filter(id__in=ids).update(preferred_pool='byok')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0110_donotemail'),
    ]

    operations = [
        migrations.RunPython(use_saved_keys, migrations.RunPython.noop),
    ]
