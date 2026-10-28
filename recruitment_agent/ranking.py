"""A candidate's rank: their place among the job's candidates by score, worked out when asked (CO-104).

Rank used to be written once, when a CV was processed: the place within one upload (every upload had its own
number 1) or, for public applicants, the order they applied in. The list sorted by it highest number first, and the
assistant called the first record by it "the best candidate".
"""
from django.db.models import F

from recruitment_agent.models import CVRecord

# Highest score first, then the AI's confidence, then the earlier application; a CV not scored yet comes last.
BEST_FIRST = (F('role_fit_score').desc(nulls_last=True), F('qualification_confidence').desc(nulls_last=True),
              'created_at', 'id')


def ranks_for(cv_records) -> dict:
    """{cv id: rank within its job} for these CVs. A CV with no job has no rank."""
    job_ids = {cv.job_description_id for cv in cv_records if cv.job_description_id}
    ranks, place = {}, {}
    for cv_id, job_id in (CVRecord.objects.filter(job_description_id__in=job_ids).order_by(*BEST_FIRST)
                          .values_list('id', 'job_description_id')):
        place[job_id] = place.get(job_id, 0) + 1
        ranks[cv_id] = place[job_id]
    return ranks
