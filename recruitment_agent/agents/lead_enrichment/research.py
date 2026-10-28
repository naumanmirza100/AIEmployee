"""Research on a candidate, beyond the CV's own words (docx item 3, "Lead Research & Enrichment").

Enrichment was word rules over the CV: no research, no AI, and the LinkedIn and GitHub links an applicant typed
into the apply form were never looked at. Now:

  * `github_facts(url)`: the candidate's public GitHub (account age, public repositories, the languages they use,
    their most recent and most starred work), read from GitHub's public API when the applicant gave a profile link.
  * `profile(...)`: the AI reads the CV, the screening summary, the apply form (cover letter, links) and those GitHub
    facts, and writes a short profile: a headline, strengths, gaps against the job, what to check in the interview,
    and its own view of seniority. It says what it was based on; it does not invent employers or numbers.

Both are optional: no link, no GitHub; an AI failure leaves the rule-based enrichment as it was. Running out of
tokens or having no key stops the run, as everywhere else.
"""
import json
import logging
import re
from datetime import datetime, timezone as dt_timezone

logger = logging.getLogger(__name__)

GITHUB_API = 'https://api.github.com'
_LOGIN = re.compile(r'github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/?(?:[?#].*)?$', re.I)


def github_login(url):
    """The login in a profile link such as https://github.com/cara-khan, or None (a repository link is not a profile)."""
    match = _LOGIN.search((url or '').strip())
    return match.group(1) if match else None


def _get(path, timeout):
    from urllib.request import Request, urlopen
    request = Request(f'{GITHUB_API}{path}', headers={'Accept': 'application/vnd.github+json',
                                                      'User-Agent': 'PayPerProject-Recruitment'})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def github_facts(url, timeout=6):
    """Public facts from a GitHub profile link, or None when there is no profile link or GitHub does not answer."""
    login = github_login(url)
    if not login:
        return None
    try:
        user = _get(f'/users/{login}', timeout)
        repos = _get(f'/users/{login}/repos?sort=updated&per_page=30&type=owner', timeout)
    except Exception as exc:
        logger.info('GitHub profile %s could not be read: %s', login, exc)
        return None
    own = [r for r in repos if isinstance(r, dict) and not r.get('fork')]
    languages = {}
    for repo in own:
        if repo.get('language'):
            languages[repo['language']] = languages.get(repo['language'], 0) + 1
    created = user.get('created_at')
    years = None
    if created:
        try:
            since = datetime.fromisoformat(created.replace('Z', '+00:00'))
            years = round((datetime.now(dt_timezone.utc) - since).days / 365.25, 1)
        except ValueError:
            pass

    def brief(repo):
        return {'name': repo.get('name'), 'description': (repo.get('description') or '')[:160],
                'language': repo.get('language'), 'stars': repo.get('stargazers_count', 0),
                'updated': (repo.get('pushed_at') or '')[:10]}

    return {
        'login': login, 'url': f'https://github.com/{login}', 'name': user.get('name') or '',
        'account_years': years, 'public_repos': user.get('public_repos', 0), 'followers': user.get('followers', 0),
        'own_repos_read': len(own),
        'top_languages': [lang for lang, _ in sorted(languages.items(), key=lambda kv: -kv[1])[:5]],
        'recent': [brief(r) for r in own[:5]],
        'most_starred': [brief(r) for r in sorted(own, key=lambda r: -(r.get('stargazers_count') or 0))[:3]
                         if (r.get('stargazers_count') or 0) > 0],
    }


SYSTEM = """You research a job candidate for a recruiter, from what is given below only.
Reply with ONLY a JSON object:
{"headline": one sentence on who this candidate is,
 "seniority": "Junior" | "Mid" | "Senior" | "Lead" | "Unclear",
 "strengths": up to 4 short points, each tied to evidence in the material,
 "gaps": up to 4 short points: what the job asks for that the material does not show,
 "verify": up to 4 things to check in the interview (claims, gaps in dates, links that do not match the CV),
 "based_on": the sources you used, from "CV", "apply form", "GitHub"}
Never invent employers, dates, numbers or skills. If something is unknown, say so in "gaps" or "verify".
For years of experience use "experience_from_cv_dates" as given; if the CV's own words claim a different number, say
so in "verify"."""


def profile(client, *, parsed_cv, summary, job_title, job_keywords, application=None, github=None):
    """The AI's research profile, or None when the AI could not give one (the rule-based enrichment stands)."""
    from core.api_key_service import KeyServiceError
    form = {}
    if application is not None:
        form = {k: getattr(application, k, None) for k in ('current_location', 'education', 'previous_company',
                                                          'linkedin_url', 'github_url', 'other_links')}
        form['cover_letter'] = (getattr(application, 'cover_letter', '') or '')[:1500]
    material = {
        'job': {'title': job_title, 'keywords': (job_keywords or [])[:25]},
        'cv': {k: parsed_cv.get(k) for k in ('summary', 'skills', 'experience', 'education', 'certifications')},
        'screening_summary': {k: (summary or {}).get(k) for k in ('candidate_summary', 'total_experience_years',
                                                                  'key_skills', 'education_level')},
        'apply_form': {k: v for k, v in form.items() if v},
        'github': github,
    }
    from recruitment_agent.experience import about_years
    if (summary or {}).get('total_experience_years') is not None:
        material['experience_from_cv_dates'] = about_years(summary['total_experience_years'])
    try:
        reply = client.send_prompt(SYSTEM, json.dumps(material, default=str)[:12000])
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.warning('Candidate research by the AI failed: %s', exc)
        return None
    if not isinstance(reply, dict):
        return None

    def points(key):
        value = reply.get(key)
        return [str(x)[:220] for x in value][:4] if isinstance(value, list) else []

    seniority = reply.get('seniority') if reply.get('seniority') in ('Junior', 'Mid', 'Senior', 'Lead', 'Unclear') else 'Unclear'
    return {'headline': str(reply.get('headline') or '')[:300], 'seniority': seniority,
            'strengths': points('strengths'), 'gaps': points('gaps'), 'verify': points('verify'),
            'based_on': points('based_on')}
