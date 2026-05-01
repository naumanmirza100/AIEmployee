"""
Lead Qualification & Scoring Agent
------------------------------------
Scores each lead 0–100 against the company's ICP using Groq AI.

  ≥ hot_threshold  → "Hot"  (contact immediately)
  ≥ warm_threshold → "Warm" (add to nurture list)
  < warm_threshold → "Cold" (deprioritise)
"""

import json
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert B2B sales lead-qualification specialist. "
    "Score leads strictly from 0 to 100 based on ICP fit. "
    "Return ONLY valid JSON — no markdown, no extra text."
)


def _get_field(obj, field: str, default=''):
    """Works for both Django model instances and plain dicts."""
    if hasattr(obj, field):
        return getattr(obj, field, default) or default
    return obj.get(field, default) or default


class LeadQualificationAgent:
    """AI-powered lead scorer using Groq."""

    def __init__(self):
        groq_key = (
            getattr(settings, 'GROQ_API_KEY', None)
            or getattr(settings, 'GROQ_REC_API_KEY', None)
            or os.environ.get('GROQ_API_KEY', '')
            or os.environ.get('GROQ_REC_API_KEY', '')
        ).strip()

        self.groq_client = None
        if groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_key)
            except Exception as exc:
                logger.error("Groq init failed in LeadQualificationAgent: %s", exc)

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def qualify_lead(self, lead, icp_profile) -> dict:
        """
        Score a lead against an ICP profile.
        `lead` can be a Django model instance or a plain dict.
        Returns a dict with: score, temperature, score_breakdown, qualification_reasoning.
        """
        if self.groq_client:
            try:
                return self._ai_qualify(lead, icp_profile)
            except Exception as exc:
                logger.warning("AI qualification failed, falling back to rule-based: %s", exc)

        return self._rule_based_qualify(lead, icp_profile)

    # ------------------------------------------------------------------
    # Groq AI qualification
    # ------------------------------------------------------------------

    def _ai_qualify(self, lead, icp) -> dict:
        icp_data = {
            "industries": icp.industries,
            "job_titles": icp.job_titles,
            "company_size_min": icp.company_size_min,
            "company_size_max": icp.company_size_max,
            "locations": icp.locations,
            "keywords": icp.keywords,
            "hot_threshold": icp.hot_threshold,
            "warm_threshold": icp.warm_threshold,
        }

        lead_data = {
            "name": (
                _get_field(lead, 'display_name')
                or (f"{_get_field(lead, 'first_name')} {_get_field(lead, 'last_name')}").strip()
                or _get_field(lead, 'full_name')
            ),
            "job_title": _get_field(lead, 'job_title'),
            "seniority_level": _get_field(lead, 'seniority_level'),
            "company_name": _get_field(lead, 'company_name'),
            "company_industry": _get_field(lead, 'company_industry'),
            "company_size": _get_field(lead, 'company_size', None),
            "company_location": _get_field(lead, 'company_location'),
            "company_technologies": _get_field(lead, 'company_technologies', []),
            "buying_signals": _get_field(lead, 'buying_signals', []),
            "recent_news": _get_field(lead, 'recent_news', []),
        }

        # Compact ICP summary to reduce token usage
        icp_summary = (
            f"Industries: {', '.join(icp.industries) or 'any'} | "
            f"Titles: {', '.join(icp.job_titles) or 'any'} | "
            f"Size: {icp.company_size_min or 0}-{icp.company_size_max or 99999} | "
            f"Locations: {', '.join(icp.locations) or 'any'} | "
            f"Hot>={icp.hot_threshold} Warm>={icp.warm_threshold}"
        )
        lead_summary = (
            f"Name: {lead_data['name']} | Title: {lead_data['job_title']} | "
            f"Company: {lead_data['company_name']} | Industry: {lead_data['company_industry']} | "
            f"Size: {lead_data['company_size']} | Location: {lead_data['company_location']} | "
            f"Signals: {'; '.join(lead_data['buying_signals'][:2]) or 'none'}"
        )

        prompt = f"""Score this B2B lead vs ICP (0-100). Return JSON only.

ICP: {icp_summary}
Lead: {lead_summary}

Scoring: industry(0-30), job_title(0-30), company_size(0-20), location(0-10), buying_signals(0-10)

Return exactly this JSON:
{{
  "score": <integer 0-100>,
  "temperature": "<hot|warm|cold>",
  "breakdown": {{
    "industry": <0-30>,
    "job_title": <0-30>,
    "company_size": <0-20>,
    "location": <0-10>,
    "buying_signals": <0-10>
  }},
  "reasoning": "<2-3 concise sentences>",
  "key_strengths": ["<strength1>", "<strength2>"],
  "concerns": ["<concern1>"]
}}"""

        resp = self.groq_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=400,
        )

        raw = resp.choices[0].message.content.strip()

        # Strip markdown if present
        if "```" in raw:
            for part in raw.split("```"):
                if "{" in part:
                    raw = part.lstrip("json").strip()
                    break

        result = json.loads(raw)

        score = max(0, min(100, int(result.get('score', 0))))
        temperature = self._score_to_temp(score, icp)

        return {
            'score': score,
            'temperature': temperature,
            'score_breakdown': result.get('breakdown', {}),
            'qualification_reasoning': result.get('reasoning', ''),
            'key_strengths': result.get('key_strengths', []),
            'concerns': result.get('concerns', []),
        }

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _rule_based_qualify(self, lead, icp) -> dict:
        bd = {'industry': 0, 'job_title': 0, 'company_size': 0, 'location': 0, 'buying_signals': 0}

        # Industry (30 pts)
        if icp.industries:
            lead_ind = _get_field(lead, 'company_industry').lower()
            for ind in icp.industries:
                if ind.lower() in lead_ind or lead_ind in ind.lower():
                    bd['industry'] = 30
                    break
            if not bd['industry'] and lead_ind:
                bd['industry'] = 5
        else:
            bd['industry'] = 15

        # Job title (30 pts)
        if icp.job_titles:
            lead_title = _get_field(lead, 'job_title').lower()
            for t in icp.job_titles:
                t_lower = t.lower()
                if t_lower in lead_title or any(w in lead_title for w in t_lower.split()):
                    bd['job_title'] = 25
                    break
        else:
            bd['job_title'] = 15

        # Company size (20 pts)
        size_val = _get_field(lead, 'company_size', None)
        if size_val and isinstance(size_val, int):
            lo = icp.company_size_min or 0
            hi = icp.company_size_max or 999_999
            if lo <= size_val <= hi:
                bd['company_size'] = 20
            elif abs(size_val - lo) < lo * 0.5 or abs(size_val - hi) < hi * 0.5:
                bd['company_size'] = 10
        else:
            bd['company_size'] = 10

        # Location (10 pts)
        if icp.locations:
            loc = _get_field(lead, 'company_location').lower()
            for l in icp.locations:
                if l.lower() in loc or loc in l.lower():
                    bd['location'] = 10
                    break
        else:
            bd['location'] = 5

        # Buying signals (10 pts)
        signals = _get_field(lead, 'buying_signals', [])
        if isinstance(signals, list) and signals:
            bd['buying_signals'] = min(10, len(signals) * 4)

        score = sum(bd.values())
        return {
            'score': score,
            'temperature': self._score_to_temp(score, icp),
            'score_breakdown': bd,
            'qualification_reasoning': (
                f"Rule-based score {score}/100. "
                f"Industry: {bd['industry']}/30, Title: {bd['job_title']}/30, "
                f"Size: {bd['company_size']}/20, Location: {bd['location']}/10, "
                f"Signals: {bd['buying_signals']}/10."
            ),
            'key_strengths': [],
            'concerns': [],
        }

    @staticmethod
    def _score_to_temp(score: int, icp) -> str:
        if score >= icp.hot_threshold:
            return 'hot'
        if score >= icp.warm_threshold:
            return 'warm'
        return 'cold'
