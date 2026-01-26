import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.log_service import LogService
from recruitment_agent.agents.summarization.prompts import SUMMARIZATION_SYSTEM_PROMPT
from recruitment_agent.skill_equivalences import skill_matches_keyword, get_all_match_terms


class SummarizationAgent:
    """
    Generates concise summaries and insights from parsed CV JSON produced by CVParserAgent.
    Uses LLM for intelligent analysis and summarization.
    """

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        log_service: Optional[LogService] = None,
        use_llm: bool = True,
    ) -> None:
        self.groq_client = groq_client
        self.log_service = log_service or LogService()
        self.use_llm = use_llm
        if use_llm and not self.groq_client:
            try:
                self.groq_client = GroqClient()
            except Exception:
                self.use_llm = False
                self._log_step("llm_disabled", {"reason": "GroqClient initialization failed"})

    def summarize(self, parsed_cv: Dict[str, Any], job_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Produce a structured summary for a single parsed CV using LLM for intelligent analysis.
        Falls back to rule-based approach if LLM is unavailable.
        """
        self._log_step("summarize_start", {"has_keywords": bool(job_keywords), "use_llm": self.use_llm})
        try:
            validated = self._validate(parsed_cv)
            
            # Try LLM-based summarization first
            if self.use_llm and self.groq_client:
                try:
                    llm_result = self._llm_summarize(validated, job_keywords)
                    if llm_result:
                        # Validate and merge with manual calculations for accuracy
                        manual_exp = self._estimate_total_experience_years(validated.get("experience"))
                        # Use LLM's experience if reasonable, else use manual
                        if llm_result.get("total_experience_years") is None or (
                            manual_exp and abs(llm_result.get("total_experience_years", 0) - manual_exp) > 2
                        ):
                            llm_result["total_experience_years"] = manual_exp
                        
                        # Ensure role_fit_score is present and valid
                        # Also validate if LLM's score is reasonable based on match percentage
                        llm_score = llm_result.get("role_fit_score")
                        should_recalculate = False
                        
                        if llm_score is None or not isinstance(llm_score, (int, float)):
                            should_recalculate = True
                        elif job_keywords and len(job_keywords) > 0:
                            # Validate LLM score vs match % (using equivalences: Node.js ↔ JavaScript, etc.)
                            all_skills = [s.lower() for s in (validated.get("skills") or [])]
                            job_kw = [k.lower().strip() for k in job_keywords if k]
                            if job_kw:
                                matched_kw = sum(1 for kw in job_kw if any(skill_matches_keyword(sk, kw) for sk in all_skills))
                                match_percentage = (matched_kw / len(job_kw)) * 100
                                if match_percentage >= 70 and llm_score < 50:
                                    should_recalculate = True
                                elif match_percentage >= 50 and llm_score < 35:
                                    should_recalculate = True
                                elif match_percentage >= 30 and llm_score < 20:
                                    should_recalculate = True
                        
                        if should_recalculate:
                            # Recalculate using manual method
                            key_skills = self._extract_key_skills(validated.get("skills"))
                            all_skills = validated.get("skills") or []  # Use ALL skills for scoring, not just key_skills
                            achievements = self._extract_achievements(validated)
                            education_level = self._highest_degree(validated.get("education"))
                            llm_result["role_fit_score"] = self._compute_fit_score(
                                all_skills,  # Use ALL skills for accurate matching
                                achievements,
                                education_level,
                                llm_result.get("total_experience_years"),
                                job_keywords,
                                validated.get("experience"),
                                validated.get("certifications"),
                            )
                        
                        self._log_step("summarize_complete", {"role_fit_score": llm_result.get("role_fit_score"), "source": "llm"})
                        return llm_result
                except Exception as llm_exc:
                    self._log_error("llm_summarize_failed", llm_exc)
                    # Fall through to rule-based approach
            
            # Fallback to rule-based approach
            total_exp = self._estimate_total_experience_years(validated.get("experience"))
            key_skills = self._extract_key_skills(validated.get("skills"))
            all_skills = validated.get("skills") or []  # Use ALL skills for scoring, not just key_skills
            education_level = self._highest_degree(validated.get("education"))
            achievements = self._extract_achievements(validated)
            fit_score = self._compute_fit_score(
                all_skills,  # Use ALL skills for accurate matching
                achievements,
                education_level,
                total_exp,
                job_keywords,
                validated.get("experience"),
                validated.get("certifications"),
            )
            candidate_summary = self._build_candidate_summary(
                validated, key_skills, total_exp, education_level, achievements
            )

            result = {
                "candidate_summary": candidate_summary,
                "total_experience_years": total_exp,
                "key_skills": key_skills or None,
                "role_fit_score": fit_score,
                "notable_achievements": achievements or None,
                "education_level": education_level,
            }
            self._log_step("summarize_complete", {"role_fit_score": fit_score, "source": "rule_based"})
            return result
        except Exception as exc:  # pragma: no cover - propagate after logging
            self._log_error("summarize_failed", exc)
            raise

    def summarize_multiple(
        self,
        cvs: List[Dict[str, Any]],
        job_keywords: Optional[List[str]] = None,
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Produce summaries for multiple parsed CVs.
        """
        results: List[Dict[str, Any]] = []
        self._log_step(
            "batch_summarize_start",
            {"count": len(cvs), "has_keywords": bool(job_keywords), "top_n": top_n},
        )
        for idx, cv in enumerate(cvs):
            self._log_step("cv_summary_start", {"index": idx})
            try:
                results.append(self.summarize(cv, job_keywords=job_keywords))
            except Exception as exc:  # pragma: no cover
                self._log_error("cv_summary_failed", exc, {"index": idx})
                raise
            self._log_step("cv_summary_complete", {"index": idx})
        # Rank by role_fit_score (None treated as -1)
        results_sorted = sorted(
            results,
            key=lambda r: r.get("role_fit_score") if r.get("role_fit_score") is not None else -1,
            reverse=True,
        )
        for rank, item in enumerate(results_sorted, start=1):
            item["rank"] = rank
        if top_n is not None:
            results_sorted = results_sorted[:top_n]
        self._log_step("batch_summarize_complete", {"count": len(results_sorted)})
        return results_sorted

    def _llm_summarize(self, parsed_cv: Dict[str, Any], job_keywords: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Use LLM to generate intelligent summarization and insights.
        """
        try:
            # Prepare input data for LLM
            input_data = {
                "parsed_cv": parsed_cv,
                "job_keywords": job_keywords if job_keywords else None,
            }
            
            # Convert to JSON string for LLM
            input_text = json.dumps(input_data, indent=2, ensure_ascii=False)
            
            self._log_step("llm_summarize_request", {"length": len(input_text), "has_keywords": bool(job_keywords)})
            
            # Call LLM
            response = self.groq_client.send_prompt(SUMMARIZATION_SYSTEM_PROMPT, input_text)
            
            if not isinstance(response, dict):
                raise GroqClientError("LLM response is not a JSON object")
            
            # Validate required fields
            if "role_fit_score" not in response:
                raise ValueError("LLM response missing required field: role_fit_score")
            
            # Ensure role_fit_score is valid (0-100 integer)
            fit_score = response.get("role_fit_score")
            if not isinstance(fit_score, (int, float)):
                raise ValueError(f"Invalid role_fit_score type: {type(fit_score)}")
            response["role_fit_score"] = int(max(0, min(100, fit_score)))
            
            self._log_step("llm_summarize_response", {"role_fit_score": response.get("role_fit_score")})
            return response
            
        except Exception as exc:
            self._log_error("llm_summarize_error", exc)
            return None

    # --------------------
    # Core helpers
    # --------------------

    def _validate(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        required_keys = {"name", "email", "phone", "skills", "experience", "education", "certifications", "summary"}
        missing = required_keys - parsed.keys()
        if missing:
            raise ValueError(f"Parsed CV missing required keys: {sorted(missing)}")
        return parsed

    def _estimate_total_experience_years(self, experience: Any) -> Optional[float]:
        if not experience or not isinstance(experience, list):
            return None
        total_months = 0
        now = datetime.utcnow()
        for item in experience:
            if not isinstance(item, dict):
                continue
            start = self._parse_date(item.get("start_date"))
            end_raw = item.get("end_date")
            end = self._parse_date(end_raw) if end_raw and str(end_raw).lower() != "present" else now
            if start:
                end_date = end or start
                months = max(0, (end_date.year - start.year) * 12 + (end_date.month - start.month))
                total_months += months
        if total_months == 0:
            return None
        return round(total_months / 12.0, 2)

    def _parse_date(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        # Try formats: YYYY, MMM YYYY, Month YYYY
        for fmt in ("%b %Y", "%B %Y", "%Y-%m-%d", "%Y/%m/%d", "%Y"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt
            except ValueError:
                continue
        # If numeric year in text
        m = re.search(r"(20\\d{2}|19\\d{2})", text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y")
            except ValueError:
                return None
        return None

    def _extract_key_skills(self, skills: Any, limit: int = 10) -> List[str]:
        if not skills:
            return []
        if isinstance(skills, list):
            cleaned = [s.strip() for s in skills if str(s).strip()]
        else:
            cleaned = [str(skills).strip()] if str(skills).strip() else []
        deduped = []
        seen = set()
        for s in cleaned:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(s)
            if len(deduped) >= limit:
                break
        return deduped

    def _highest_degree(self, education: Any) -> Optional[str]:
        if not education or not isinstance(education, list):
            return None
        priorities = [
            ("phd", "PhD"),
            ("doctor", "Doctorate"),
            ("masters", "Master"),
            ("master", "Master"),
            ("msc", "Master"),
            ("ma", "Master"),
            ("mba", "MBA"),
            ("bachelor", "Bachelor"),
            ("bsc", "Bachelor"),
            ("bs", "Bachelor"),
        ]
        for item in education:
            degree_text = " ".join(str(item.get("degree", "")).lower().split())
            for key, label in priorities:
                if key in degree_text:
                    return label
        return None

    def _extract_achievements(self, parsed: Dict[str, Any]) -> List[str]:
        achievements: List[str] = []
        # Certifications
        certs = parsed.get("certifications") or []
        if isinstance(certs, list):
            for c in certs:
                if isinstance(c, dict):
                    name = c.get("name")
                    issuer = c.get("issuer")
                    year = c.get("year")
                    parts = [p for p in [name, issuer, year] if p]
                    if parts:
                        achievements.append(" | ".join(parts))
        # Experience descriptions
        exp = parsed.get("experience") or []
        if isinstance(exp, list):
            for item in exp:
                desc = item.get("description")
                if desc:
                    achievements.append(desc.strip())
        return achievements

    def _compute_fit_score(
        self,
        key_skills: List[str],  # ALL skills, not just key_skills subset
        achievements: List[str],
        education_level: Optional[str],
        total_experience_years: Optional[float],
        job_keywords: Optional[List[str]],
        experience: Any,
        certifications: Any,
    ) -> int:
        """
        role_fit_score (0-100): SKILLS + EXPERIENCE only.
        No education, seniority, or critical-skills.
        
        1. Skills Match: max 80 pts – job_keywords vs ALL skills, using equivalences
           (e.g. Node.js ↔ JavaScript). If no keywords: skill volume (8 pts/skill, max 80).
        2. Experience: max 8 pts – min(8, total_experience_years * 1.5).
        3. Experience Relevance: max 5 pts – keyword hits in roles/descriptions.
        """
        score = 0.0
        job_kw = [k.lower().strip() for k in job_keywords] if job_keywords else []
        job_kw = [k for k in job_kw if k]
        job_kw_set = set(job_kw)
        skills_lower = [s.lower() for s in key_skills]

        if job_kw_set:
            # Overlap using shared equivalences (Node.js ↔ JavaScript, etc.)
            matched_keywords = 0
            for kw in job_kw_set:
                if any(skill_matches_keyword(sk, kw) for sk in skills_lower):
                    matched_keywords += 1
            match_ratio = matched_keywords / len(job_kw_set)
            score += match_ratio * 80
        else:
            skill_count = len(key_skills)
            if skill_count >= 10:
                score += 80
            else:
                score += skill_count * 8.0

        # Experience only (max 8)
        if total_experience_years:
            score += min(8, total_experience_years * 1.5)

        # Experience relevance (max 5) – use equivalences (e.g. Node.js ↔ JavaScript)
        exp_hits = 0
        if job_kw_set and experience and isinstance(experience, list):
            for item in experience:
                if not isinstance(item, dict):
                    continue
                text = " ".join(
                    [
                        str(item.get("role", "")),
                        str(item.get("company", "")),
                        str(item.get("description", "")),
                    ]
                ).lower()
                for kw in job_kw_set:
                    terms = get_all_match_terms(kw)
                    if any(t in text for t in terms):
                        exp_hits += 1
            score += min(5, exp_hits * 1)

        return int(max(0, min(100, math.floor(score))))

    def _build_candidate_summary(
        self,
        parsed: Dict[str, Any],
        key_skills: List[str],
        total_exp: Optional[float],
        education_level: Optional[str],
        achievements: List[str],
    ) -> Optional[str]:
        fragments: List[str] = []

        # Existing summary / profile content
        if parsed.get("summary"):
            fragments.append(str(parsed["summary"]).strip())

        name = parsed.get("name")

        # Constructed professional highlight
        parts = []
        if name:
            parts.append(f"{name} is a professional")
        if total_exp:
            parts.append(f"with approximately {total_exp} years of experience")
        elif parsed.get("experience"):
            parts.append("with proven experience across multiple roles")
        if key_skills:
            parts.append(f"skilled in {', '.join(key_skills[:5])}")
        if education_level:
            parts.append(f"holding {education_level}-level education")

        constructed = " ".join(parts).strip()
        if constructed:
            fragments.append(constructed)

        # Add achievements in a concise way
        if achievements:
            fragments.append("Notable achievements include: " + "; ".join(achievements[:3]))

        if not fragments:
            return None

        summary_text = " ".join(fragments)
        sentences = re.split(r"(?<=[.!?])\s+", summary_text.strip())
        if len(sentences) < 3 and len(fragments) > 1:
            summary_text = ". ".join(fragments)
        return summary_text.strip()

    def _has_leadership_role(self, experience: Any) -> bool:
        if not experience or not isinstance(experience, list):
            return False
        leadership_terms = [
            "lead",
            "leader",
            "manager",
            "head",
            "director",
            "vp",
            "chief",
            "president",
            "chair",
        ]
        for item in experience:
            if not isinstance(item, dict):
                continue
            role_text = str(item.get("role", "")).lower()
            desc_text = str(item.get("description", "")).lower()
            if any(term in role_text for term in leadership_terms) or any(
                term in desc_text for term in leadership_terms
            ):
                return True
        return False

    # --------------------
    # Logging helpers
    # --------------------

    def _log_step(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.log_service.log_event(event_name, metadata or {})

    def _log_error(
        self, event_name: str, exc: Exception, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        error_meta = metadata or {}
        error_meta.update({"error": str(exc)})
        self.log_service.log_error(event_name, error_meta)

