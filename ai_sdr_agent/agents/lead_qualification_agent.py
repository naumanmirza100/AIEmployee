"""
Lead Qualification & Scoring Agent
------------------------------------
Scores each lead 0–100 using a 5-category weighted model:

  Company Quality    (30 pts) — website, business presence, service clarity
  Contact Quality    (20 pts) — decision-maker identified, verified contact info
  Business Fit       (25 pts) — ICP industry/size match
  Engagement Signals (15 pts) — LinkedIn, buying signals, recent activity
  Data Completeness  (10 pts) — how complete the profile is

Score categories (fixed thresholds):
  90–100 → Hot Lead 🔥
  75–89  → High Potential Lead
  60–74  → Qualified Lead
  40–59  → Low Priority Lead
  <40    → Reject

Temperature (ICP-configurable):
  score >= hot_threshold  → hot
  score >= warm_threshold → warm
  else                    → cold
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior B2B sales operations expert. "
    "Score leads strictly on fit, data quality, and business potential. "
    "Return ONLY valid JSON — no markdown, no extra text."
)

# Fixed thresholds for score category labels (independent of ICP hot/warm)
SCORE_CATEGORY_THRESHOLDS = (
    (90, 'hot_lead'),
    (75, 'high_potential'),
    (60, 'qualified'),
    (40, 'low_priority'),
    (0,  'reject'),
)


def score_to_category(score: int) -> str:
    for threshold, label in SCORE_CATEGORY_THRESHOLDS:
        if score >= threshold:
            return label
    return 'reject'


def _get_field(obj, field: str, default=''):
    if hasattr(obj, field):
        return getattr(obj, field, default) or default
    return obj.get(field, default) or default


class LeadQualificationAgent:

    def __init__(self, company=None):
        self._key_ctx = None
        self.groq_client = None

        if company is not None:
            from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client
            self.groq_client, self._key_ctx = resolve_sdr_groq_client(company)
        else:
            logger.warning("LeadQualificationAgent initialised without a company — no LLM key resolved.")

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

    def qualify_lead(self, lead, icp_profile) -> dict:
        if self.groq_client:
            try:
                return self._ai_qualify(lead, icp_profile)
            except Exception as exc:
                from core.api_key_service import KeyServiceError
                if isinstance(exc, KeyServiceError):
                    raise
                logger.warning("AI qualification failed, falling back to rule-based: %s", exc)

        return self._rule_based_qualify(lead, icp_profile)

    # ------------------------------------------------------------------
    # Groq AI qualification
    # ------------------------------------------------------------------

    def _ai_qualify(self, lead, icp) -> dict:
        size_int = _get_field(lead, 'company_size', None)
        size_range = _get_field(lead, 'company_size_range', '')
        size_display = str(size_int) if size_int else (size_range or 'unknown')

        has_website = bool(_get_field(lead, 'company_website'))
        has_linkedin = bool(_get_field(lead, 'linkedin_url'))
        has_phone = bool(_get_field(lead, 'phone'))
        has_email = bool(_get_field(lead, 'email'))
        buying_signals = _get_field(lead, 'buying_signals', [])
        recent_news = _get_field(lead, 'recent_news', [])
        technologies = _get_field(lead, 'company_technologies', [])

        lead_summary = (
            f"Name: {_get_field(lead, 'full_name') or _get_field(lead, 'first_name')} | "
            f"Title: {_get_field(lead, 'job_title')} | "
            f"Seniority: {_get_field(lead, 'seniority_level') or 'unknown'} | "
            f"Company: {_get_field(lead, 'company_name')} | "
            f"Industry: {_get_field(lead, 'company_industry') or 'unknown'} | "
            f"Size: {size_display} employees | "
            f"Location: {_get_field(lead, 'company_location') or 'unknown'} | "
            f"Website: {'yes' if has_website else 'no'} | "
            f"LinkedIn: {'yes' if has_linkedin else 'no'} | "
            f"Email: {'yes' if has_email else 'no'} | "
            f"Phone: {'yes' if has_phone else 'no'} | "
            f"Technologies: {', '.join(technologies[:3]) if technologies else 'unknown'} | "
            f"Buying signals: {'; '.join(str(s) for s in buying_signals[:3]) if buying_signals else 'none'} | "
            f"Recent news: {'yes' if recent_news else 'no'}"
        )

        icp_summary = (
            f"Target industries: {', '.join(icp.industries) or 'any'} | "
            f"Target titles: {', '.join(icp.job_titles) or 'any'} | "
            f"Company size: {icp.company_size_min or 0}–{icp.company_size_max or 99999} employees | "
            f"Locations: {', '.join(icp.locations) or 'any'} | "
            f"Keywords: {', '.join(icp.keywords) or 'none'}"
        )

        prompt = f"""Score this B2B sales lead against our ICP using the weighted model below. Respond with ONLY a JSON object.

ICP Profile: {icp_summary}

Lead Data: {lead_summary}

Scoring model (total = 100 points):
1. company_quality (0-30): Does the company have a professional website (0-10)? Active business presence / real company (0-10)? Clear service offerings / known industry (0-10)?
2. contact_quality (0-20): Is this person a decision-maker (C-suite/VP/Director/Head) (0-10)? Do they have verified email and/or phone (0-10)?
3. business_fit (0-25): How well does the industry match ICP (0-15)? Does company size fit ICP range (0-10)?
4. engagement_signals (0-15): Active LinkedIn presence (0-5)? Has buying signals or recent news (0-5)? Uses relevant technologies (0-5)?
5. data_completeness (0-10): Is the profile complete — name, email, title, company, location all present (0-10)?

Score each category realistically. If a field is missing, penalise accordingly. If unknown, give partial credit.

Also determine:
- The recommended outreach strategy (1-2 sentences specific to this lead)
- 2-3 key strengths
- 1-2 main concerns

Return EXACTLY this JSON structure:
{{"score": <int 0-100>, "temperature": "<hot|warm|cold>", "breakdown": {{"company_quality": <0-30>, "contact_quality": <0-20>, "business_fit": <0-25>, "engagement_signals": <0-15>, "data_completeness": <0-10>}}, "reasoning": "<2-3 sentence summary of fit>", "key_strengths": ["<strength1>", "<strength2>"], "concerns": ["<concern1>"], "outreach_strategy": "<personalised outreach recommendation>"}}

Use hot if score >= {icp.hot_threshold}, warm if >= {icp.warm_threshold}, else cold.
Score this lead now:"""

        resp = self.groq_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
        record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))

        raw = resp.choices[0].message.content.strip()

        # Strip markdown fences
        if "```" in raw:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
            if m:
                raw = m.group(1).strip()

        if not raw.startswith('{'):
            m = re.search(r'\{[\s\S]*\}', raw)
            if m:
                raw = m.group(0)

        result = json.loads(raw)

        raw_score = result.get('score', 0)
        score = max(0, min(100, int(float(str(raw_score)))))
        temperature = self._score_to_temp(score, icp)

        # Validate breakdown sums (cap each dimension)
        bd = result.get('breakdown', {})
        breakdown = {
            'company_quality':    max(0, min(30, int(bd.get('company_quality', 0)))),
            'contact_quality':    max(0, min(20, int(bd.get('contact_quality', 0)))),
            'business_fit':       max(0, min(25, int(bd.get('business_fit', 0)))),
            'engagement_signals': max(0, min(15, int(bd.get('engagement_signals', 0)))),
            'data_completeness':  max(0, min(10, int(bd.get('data_completeness', 0)))),
        }
        # Recalculate score from breakdown to ensure consistency
        bd_sum = sum(breakdown.values())
        if bd_sum > 0 and abs(bd_sum - score) > 10:
            score = bd_sum

        return {
            'score': score,
            'temperature': temperature,
            'score_breakdown': breakdown,
            'qualification_reasoning': result.get('reasoning', ''),
            'key_strengths': result.get('key_strengths', []),
            'concerns': result.get('concerns', []),
            'outreach_strategy': result.get('outreach_strategy', ''),
        }

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_based_qualify(self, lead, icp) -> dict:
        from ai_sdr_agent.agents.lead_validator import is_decision_maker

        bd = {
            'company_quality': 0,
            'contact_quality': 0,
            'business_fit': 0,
            'engagement_signals': 0,
            'data_completeness': 0,
        }

        # ── Company Quality (30) ───────────────────────────────────────
        cq = 0
        if _get_field(lead, 'company_website'):
            cq += 10
        if _get_field(lead, 'company_name') and _get_field(lead, 'company_name') not in ('unknown', ''):
            cq += 10
        if _get_field(lead, 'company_industry'):
            cq += 10
        bd['company_quality'] = min(30, cq)

        # ── Contact Quality (20) ──────────────────────────────────────
        ctq = 0
        if is_decision_maker(_get_field(lead, 'job_title')):
            ctq += 10
        if _get_field(lead, 'email'):
            ctq += 6
        if _get_field(lead, 'phone'):
            ctq += 4
        bd['contact_quality'] = min(20, ctq)

        # ── Business Fit (25) ─────────────────────────────────────────
        bf = 0
        if icp.industries:
            lead_ind = _get_field(lead, 'company_industry').lower()
            for ind in icp.industries:
                if ind.lower() in lead_ind or lead_ind in ind.lower():
                    bf += 15
                    break
            if not bf and lead_ind:
                bf += 5
        else:
            bf += 10

        size_val = _get_field(lead, 'company_size', None)
        if size_val and isinstance(size_val, int):
            lo = icp.company_size_min or 0
            hi = icp.company_size_max or 999_999
            if lo <= size_val <= hi:
                bf += 10
            elif abs(size_val - lo) < lo * 0.5 or abs(size_val - hi) < hi * 0.5:
                bf += 5
        else:
            bf += 5
        bd['business_fit'] = min(25, bf)

        # ── Engagement Signals (15) ───────────────────────────────────
        es = 0
        if _get_field(lead, 'linkedin_url'):
            es += 5
        signals = _get_field(lead, 'buying_signals', [])
        if isinstance(signals, list) and signals:
            es += min(5, len(signals) * 2)
        news = _get_field(lead, 'recent_news', [])
        if isinstance(news, list) and news:
            es += 2
        techs = _get_field(lead, 'company_technologies', [])
        if isinstance(techs, list) and techs:
            es += 3
        bd['engagement_signals'] = min(15, es)

        # ── Data Completeness (10) ────────────────────────────────────
        dc = 0
        fields_check = [
            ('full_name', 2), ('email', 2), ('job_title', 2),
            ('company_name', 2), ('company_location', 1), ('phone', 1),
        ]
        for fname, pts in fields_check:
            if _get_field(lead, fname):
                dc += pts
        bd['data_completeness'] = min(10, dc)

        score = sum(bd.values())
        temperature = self._score_to_temp(score, icp)

        reasoning = (
            f"Rule-based score {score}/100. "
            f"Company: {bd['company_quality']}/30, Contact: {bd['contact_quality']}/20, "
            f"Business Fit: {bd['business_fit']}/25, Engagement: {bd['engagement_signals']}/15, "
            f"Completeness: {bd['data_completeness']}/10."
        )

        strengths, concerns = [], []
        if bd['business_fit'] >= 20:
            strengths.append("Strong ICP industry and size alignment")
        if is_decision_maker(_get_field(lead, 'job_title')):
            strengths.append("Decision-maker title identified")
        if _get_field(lead, 'linkedin_url'):
            strengths.append("LinkedIn profile available for research")
        if not _get_field(lead, 'email'):
            concerns.append("No verified email address")
        if bd['company_quality'] < 15:
            concerns.append("Limited company information available")

        outreach = ""
        cat = score_to_category(score)
        if cat in ('hot_lead', 'high_potential'):
            outreach = "Reach out immediately with a personalised email referencing their industry challenges."
        elif cat == 'qualified':
            outreach = "Add to a targeted nurture campaign with industry-specific content."
        elif cat == 'low_priority':
            outreach = "Include in broad awareness campaigns; revisit if more data becomes available."
        else:
            outreach = "Insufficient data or ICP fit — do not reach out."

        return {
            'score': score,
            'temperature': temperature,
            'score_breakdown': bd,
            'qualification_reasoning': reasoning,
            'key_strengths': strengths,
            'concerns': concerns,
            'outreach_strategy': outreach,
        }

    @staticmethod
    def _score_to_temp(score: int, icp) -> str:
        if score >= icp.hot_threshold:
            return 'hot'
        if score >= icp.warm_threshold:
            return 'warm'
        return 'cold'
