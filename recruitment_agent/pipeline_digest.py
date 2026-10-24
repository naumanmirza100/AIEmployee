"""Once a day, each recruiter hears what in their pipeline is waiting on them.

Nothing told a recruiter that a candidate had sat on hold for days, that an online interview tomorrow had no meeting
link, or that an interview was over with no outcome recorded. Now one bell item a day per recruiter says so, worked out
with three grouped queries across every company and sent by Celery beat, not from a web request.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

KIND = 'recruitment_pipeline_digest'
ON_HOLD_DAYS = 3            # on hold longer than this, a candidate is waiting for a decision
ON_HOLD_UNTIL_DAYS = 30     # older holds are taken as deliberate, not forgotten
OUTCOME_WINDOW_DAYS = 14    # interviews over in the last fortnight with no outcome

# What each count says, in the order it is told; the first one present decides where the bell item opens.
LINES = (
    ('no_link', '{n} online interview{s} in the next 24 hours with no meeting link', '/recruitment/interviews'),
    ('no_outcome', '{n} interview{s} done with no outcome recorded', '/recruitment/interviews'),
    ('on_hold', '{n} candidate{s} on hold for over %d days' % ON_HOLD_DAYS, '/recruitment/candidates'),
)


def pipeline_items(now=None):
    """{company_user_id: {'on_hold': n, 'no_link': n, 'no_outcome': n}} for each recruiter with anything waiting."""
    from recruitment_agent.models import CVRecord, Interview

    now = now or timezone.now()
    on_hold = (CVRecord.objects
               .filter(qualification_decision='HOLD', created_at__lt=now - timedelta(days=ON_HOLD_DAYS),
                       created_at__gte=now - timedelta(days=ON_HOLD_UNTIL_DAYS),
                       job_description__company_user__isnull=False, interviews__isnull=True)
               .order_by().values('job_description__company_user_id').annotate(n=Count('id', distinct=True)))
    no_link = (Interview.objects
               .filter(status='SCHEDULED', interview_type='ONLINE', company_user__isnull=False,
                       scheduled_datetime__gte=now, scheduled_datetime__lt=now + timedelta(hours=24))
               .filter(Q(meeting_link__isnull=True) | Q(meeting_link=''))
               .order_by().values('company_user_id').annotate(n=Count('id')))
    no_outcome = (Interview.objects
                  .filter(status__in=('SCHEDULED', 'COMPLETED'), company_user__isnull=False,
                          scheduled_datetime__lt=now - timedelta(hours=1),
                          scheduled_datetime__gte=now - timedelta(days=OUTCOME_WINDOW_DAYS))
                  .filter(Q(outcome__isnull=True) | Q(outcome=''))
                  .order_by().values('company_user_id').annotate(n=Count('id')))

    items = {}
    for key, rows, owner in (('on_hold', on_hold, 'job_description__company_user_id'),
                             ('no_link', no_link, 'company_user_id'),
                             ('no_outcome', no_outcome, 'company_user_id')):
        for row in rows:
            items.setdefault(row[owner], {})[key] = row['n']
    return items


def digest(found):
    """The title, message and link of one recruiter's bell item."""
    lines, link = [], None
    for key, text, opens in LINES:
        n = found.get(key)
        if n:
            lines.append(text.format(n=n, s='' if n == 1 else 's'))
            link = link or opens
    return 'Waiting on you in Recruitment', ' · '.join(lines) + '.', link


def send_pipeline_digests(now=None):
    """Tell each recruiter with something waiting, at most once a day. Returns how many were told."""
    from core.models import CompanyUser
    from core.modules import active_company_ids
    from core.notification_utils import notify_company_users
    from project_manager_agent.models import PMNotification

    now = now or timezone.now()
    items = pipeline_items(now)
    if not items:
        return 0
    told_today = set(PMNotification.objects.filter(
        company_user_id__in=list(items), data__kind=KIND, created_at__gte=now - timedelta(hours=20),
    ).values_list('company_user_id', flat=True))
    recruiters = CompanyUser.objects.filter(
        id__in=[i for i in items if i not in told_today], is_active=True,
        company_id__in=active_company_ids('recruitment_agent'))
    told = 0
    for recruiter in recruiters:
        title, message, link = digest(items[recruiter.id])
        told += notify_company_users([recruiter], title=title, message=message, link=link, kind=KIND)
    return told
