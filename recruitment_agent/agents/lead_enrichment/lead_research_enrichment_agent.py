from typing import Any, Dict, List, Optional, Tuple

from recruitment_agent.log_service import LogService


class LeadResearchEnrichmentAgent:
    """
    Enriches parsed CV data and existing candidate insights.
    - Normalizes skills/job titles
    - Infers primary role and seniority
    - Buckets experience
    - Extracts leadership/technical signals
    - Flags missing critical fields
    - With an AI client: the candidate's public GitHub (when the apply form gave it) and an AI research profile
      (headline, strengths, gaps, what to verify), in `research.py`. It was word rules only.
    """

    def __init__(
        self,
        log_service: Optional[LogService] = None,
        sql_repository: Optional[Any] = None,  # Can be SQLRepository or DjangoRepository
        groq_client: Optional[Any] = None,
    ) -> None:
        self.log_service = log_service or LogService()
        self.sql_repository = sql_repository
        self.groq_client = groq_client

    def enrich(self, parsed_cv: Dict[str, Any], candidate_insights: Dict[str, Any], *, application=None,
               job=None, job_keywords=None) -> Dict[str, Any]:
        self._log_step("enrichment_start", {"has_insights": bool(candidate_insights)})

        normalized_skills = self._normalize_skills(parsed_cv.get("skills") or [])
        role_from_exp = self._infer_role_from_experience(parsed_cv.get("experience") or [])
        role_from_skills = self._infer_role_from_skills(normalized_skills)
        primary_role = role_from_exp or role_from_skills

        total_exp_years = candidate_insights.get("total_experience_years")
        seniority = self._infer_seniority(parsed_cv.get("experience") or [], total_exp_years)
        exp_bucket = self._bucket_experience(total_exp_years)

        leadership_signals = self._extract_leadership(parsed_cv.get("experience") or [])
        technical_signals = self._extract_technical_signals(normalized_skills, parsed_cv)

        completeness_score, missing_fields = self._compute_completeness(parsed_cv)

        enriched = {
            "normalized_skills": normalized_skills or None,
            "primary_role": primary_role,
            "seniority_level": seniority,
            "years_experience_bucket": exp_bucket,
            "leadership_signals": leadership_signals or None,
            "technical_depth_signals": technical_signals or None,
            "profile_completeness_score": completeness_score,
            "missing_critical_fields": missing_fields or None,
        }
        if self.groq_client is not None:
            from recruitment_agent.agents.lead_enrichment import research
            github = research.github_facts(getattr(application, 'github_url', None)) if application is not None else None
            enriched["github"] = github
            enriched["research"] = research.profile(
                self.groq_client, parsed_cv=parsed_cv, summary=candidate_insights,
                job_title=getattr(job, 'title', ''), job_keywords=job_keywords, application=application,
                github=github)

        record_id = candidate_insights.get("record_id") or parsed_cv.get("record_id")
        if self.sql_repository and record_id:
            self.sql_repository.store_enrichment(record_id, enriched)

        self._log_step("enrichment_complete", {"primary_role": primary_role, "seniority": seniority})
        return enriched

    def enrich_multiple(
        self, items: List[Tuple[Dict[str, Any], Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        self._log_step("batch_enrichment_start", {"count": len(items)})
        results: List[Dict[str, Any]] = []
        for parsed_cv, insights in items:
            results.append(self.enrich(parsed_cv, insights))
        self._log_step("batch_enrichment_complete", {"count": len(results)})
        return results

    # -----------------------
    # Inference helpers
    # -----------------------
    def _normalize_skills(self, skills: List[Any]) -> List[str]:
        mapping = {
            "next js": "Next.js",
            "nextjs": "Next.js",
            "node js": "Node.js",
            "nodejs": "Node.js",
            "reactjs": "React",
            "react js": "React",
            "github": "GitHub",
            "git hub": "GitHub",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "c sharp": "C#",
            "csharp": "C#",
            "c plus plus": "C++",
            "docker": "Docker",
            "k8s": "Kubernetes",
            "kubernetes": "Kubernetes",
            "sql": "SQL",
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "aws": "AWS",
            "gcp": "GCP",
            "azure": "Azure",
        }
        cleaned = []
        seen = set()
        for s in skills:
            if s is None:
                continue
            norm = str(s).strip()
            if not norm:
                continue
            key = norm.lower()
            norm_val = mapping.get(key, mapping.get(key.replace(" ", ""), norm))
            if norm_val.lower() not in seen:
                seen.add(norm_val.lower())
                cleaned.append(norm_val)
        return cleaned

    def _infer_role_from_experience(self, experience: List[Dict[str, Any]]) -> Optional[str]:
        role_keywords = {
            "backend": ["backend", "back-end", "api"],
            "frontend": ["frontend", "front-end", "ui"],
            "full stack": ["full stack", "full-stack"],
            "mobile": ["mobile", "android", "ios", "react native"],
            "data": ["data engineer", "data scientist", "ml", "machine learning"],
            "devops": ["devops", "sre", "site reliability"],
            "security": ["security", "infosec", "cyber"],
        }
        for item in experience:
            role = (item.get("role") or "").lower()
            for label, keys in role_keywords.items():
                if any(k in role for k in keys):
                    return f"{label.title()} Engineer"
        return None

    def _infer_role_from_skills(self, skills: List[str]) -> Optional[str]:
        sk_lower = [s.lower() for s in skills]
        if any("react" in s or "next.js" in s for s in sk_lower):
            if any("node" in s for s in sk_lower):
                return "Full Stack Developer"
            return "Frontend Developer"
        if any("node" in s or "django" in s or "fastapi" in s for s in sk_lower):
            return "Backend Engineer"
        if any("aws" in s or "kubernetes" in s or "docker" in s for s in sk_lower):
            return "DevOps / Cloud Engineer"
        return None

    def _infer_seniority(self, experience: List[Dict[str, Any]], total_years: Optional[float]) -> str:
        roles_text = " ".join([(r.get("role") or "") for r in experience]).lower()
        if any(x in roles_text for x in ["director", "head", "vp", "chief"]):
            return "Manager"
        if any(x in roles_text for x in ["lead", "principal"]):
            return "Lead"
        if any(x in roles_text for x in ["senior", "sr"]):
            return "Senior"
        if any(x in roles_text for x in ["intern", "trainee"]):
            return "Intern"
        if total_years is None:
            return "Unknown"
        if total_years < 1:
            return "Intern"
        if total_years < 3:
            return "Junior"
        if total_years < 5:
            return "Mid"
        if total_years < 8:
            return "Senior"
        return "Lead"

    def _bucket_experience(self, total_years: Optional[float]) -> Optional[str]:
        if total_years is None:
            return None
        if total_years < 1:
            return "0-1"
        if total_years < 3:
            return "1-3"
        if total_years < 5:
            return "3-5"
        if total_years < 8:
            return "5-8"
        return "8+"

    def _extract_leadership(self, experience: List[Dict[str, Any]]) -> List[str]:
        terms = ["lead", "leader", "manager", "head", "director", "vp", "chief", "president", "chair"]
        signals = []
        for item in experience:
            role = (item.get("role") or "").lower()
            desc = (item.get("description") or "").lower()
            if any(t in role for t in terms) or any(t in desc for t in terms):
                signals.append(item.get("role") or "Leadership signal")
        return signals

    def _extract_technical_signals(self, skills: List[str], parsed_cv: Dict[str, Any]) -> List[str]:
        signals = []
        tech_keywords = ["kubernetes", "docker", "aws", "gcp", "azure", "distributed", "microservices", "architecture"]
        skills_lower = [s.lower() for s in skills]
        for kw in tech_keywords:
            if any(kw in s for s in skills_lower):
                signals.append(kw.title() if kw.islower() else kw)
        certs = parsed_cv.get("certifications") or []
        for c in certs:
            if isinstance(c, dict) and c.get("name"):
                signals.append(c["name"])
        return list(dict.fromkeys(signals))  # dedupe

    def _compute_completeness(self, parsed_cv: Dict[str, Any]) -> (int, List[str]):
        required = ["name", "email", "skills", "experience", "education", "certifications"]
        missing = []
        present = 0
        for key in required:
            val = parsed_cv.get(key)
            if val:
                present += 1
            else:
                missing.append(key)
        score = int((present / len(required)) * 100)
        return score, missing

    # -----------------------
    # Logging
    # -----------------------
    def _log_step(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.log_service.log_event(event_name, metadata or {})

