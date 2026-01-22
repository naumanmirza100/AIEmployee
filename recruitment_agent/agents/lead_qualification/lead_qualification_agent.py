import re
from typing import Any, Dict, List, Optional, Tuple

from recruitment_agent.log_service import LogService


class LeadQualificationAgent:
    """
    Senior technical recruiter-style evaluation agent.
    Evaluates candidates using inference, context, and evidence-based reasoning.
    Does NOT rely on exact keyword matching.
    """

    def __init__(
        self,
        log_service: Optional[LogService] = None,
        sql_repository: Optional[Any] = None,  # Can be SQLRepository or DjangoRepository
    ) -> None:
        self.log_service = log_service or LogService()
        self.sql_repository = sql_repository

    def qualify(
        self,
        parsed_cv: Dict[str, Any],
        candidate_insights: Dict[str, Any],
        job_keywords: Optional[List[str]] = None,
        enriched_data: Optional[Dict[str, Any]] = None,
        interview_threshold: Optional[int] = None,
        hold_threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._log_step("qualification_start", {"has_keywords": bool(job_keywords), "has_enriched": bool(enriched_data)})

        normalized_keywords = self._normalize_keywords(job_keywords)
        
        # Use enriched normalized_skills if available, otherwise extract from CV
        if enriched_data and enriched_data.get("normalized_skills"):
            all_skills = enriched_data.get("normalized_skills", [])
        else:
            all_skills = self._extract_all_skills(parsed_cv, candidate_insights)
        
        # Still infer additional skills from context (enrichment may have missed some)
        inferred_skills = self._infer_skills_from_context(parsed_cv, candidate_insights, all_skills)
        
        # Merge enriched normalized skills with inferred
        if enriched_data and enriched_data.get("normalized_skills"):
            enriched_skills = enriched_data.get("normalized_skills", [])
            all_skills = list(set(all_skills + enriched_skills))
        
        # Match against job keywords using inference-aware matching
        matched, missing = self._match_with_inference(all_skills, inferred_skills, normalized_keywords)
        
        # Evaluate overall fit using recruiter-style reasoning
        role_fit_score = candidate_insights.get("role_fit_score")
        total_exp_years = candidate_insights.get("total_experience_years")
        decision, confidence = self._recruiter_decide(
            all_skills, inferred_skills, matched, missing, role_fit_score, total_exp_years, parsed_cv, candidate_insights, enriched_data, job_keywords, interview_threshold, hold_threshold
        )
        priority = self._assign_priority(decision, confidence, total_exp_years, matched, inferred_skills, enriched_data)
        
        reasoning = self._build_recruiter_reasoning(
            decision, confidence, matched, inferred_skills, missing, role_fit_score, total_exp_years, parsed_cv, candidate_insights, enriched_data
        )
        
        # Calculate match percentage for ranking visibility
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        total_keywords = matched_count + missing_count
        match_percentage = int((matched_count / max(total_keywords, 1)) * 100) if total_keywords > 0 else 0

        result = {
            "decision": decision,
            "confidence_score": confidence,
            "priority": priority,
            "matched_skills": matched or None,
            "inferred_skills": inferred_skills or None,
            "missing_skills": missing or None,
            "match_percentage": match_percentage,  # Job requirements se kitna match (0-100)
            "matched_count": matched_count,
            "total_keywords": total_keywords,
            "reasoning": reasoning,
        }

        record_id = candidate_insights.get("record_id") or parsed_cv.get("record_id")
        if self.sql_repository and record_id:
            self.sql_repository.store_qualification(record_id, result)

        self._log_step("qualification_complete", {"decision": decision, "priority": priority, "confidence": confidence})
        return result

    def qualify_multiple(
        self,
        cvs: List[Tuple[Dict[str, Any], Dict[str, Any]]],
        job_keywords: Optional[List[str]] = None,
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._log_step("batch_qualification_start", {"count": len(cvs), "has_keywords": bool(job_keywords), "top_n": top_n})
        results: List[Dict[str, Any]] = []
        for parsed_cv, insights in cvs:
            results.append(self.qualify(parsed_cv, insights, job_keywords))

        # Rank by SKILLS MATCH - job requirements se best match wale top par
        def skills_based_sort_key(r: Dict[str, Any]) -> Tuple[float, int, int, int]:
            matched = r.get("matched_skills") or []
            inferred = r.get("inferred_skills") or []
            missing = r.get("missing_skills") or []
            confidence = r.get("confidence_score") if r.get("confidence_score") is not None else 0
            
            matched_count = len(matched) if isinstance(matched, list) else 0
            missing_count = len(missing) if isinstance(missing, list) else 0
            total_keywords = matched_count + missing_count
            
            # PRIMARY: Match ratio (matched/total) - job requirements se kitna match
            # Higher ratio = better rank (e.g., 4/5 = 80% > 2/5 = 40%)
            match_ratio = matched_count / max(total_keywords, 1) if total_keywords > 0 else 0.0
            
            # SECONDARY: Matched skills count (zyada matched = better)
            # Tertiary: Inferred skills count (zyada inferred = better)
            inferred_count = len(inferred) if isinstance(inferred, list) else 0
            
            # Quaternary: Confidence score
            return (match_ratio, matched_count, inferred_count, confidence)
        
        results_sorted = sorted(results, key=skills_based_sort_key, reverse=True)
        for rank, item in enumerate(results_sorted, start=1):
            item["rank"] = rank
            record_id = item.get("record_id") or None
            if self.sql_repository and record_id:
                self.sql_repository.store_qualification(record_id, item, rank=rank)

        if top_n is not None:
            results_sorted = results_sorted[:top_n]

        self._log_step("batch_qualification_complete", {"count": len(results_sorted)})
        return results_sorted

    # ------------------------
    # Recruiter-style evaluation logic
    # ------------------------
    def _normalize_keywords(self, keywords: Optional[List[Any]]) -> List[str]:
        """Normalize job keywords for matching."""
        if not keywords:
            return []
        cleaned = []
        seen = set()
        for k in keywords:
            if k is None:
                continue
            val = str(k).strip()
            if not val:
                continue
            key = val.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(val)
        return cleaned

    def _extract_all_skills(self, parsed_cv: Dict[str, Any], candidate_insights: Dict[str, Any]) -> List[str]:
        """Extract all skills from explicit skills list."""
        skills_raw = parsed_cv.get("skills") or []
        normalized = []
        seen = set()
        for s in skills_raw:
            if not s:
                continue
            val = str(s).strip()
            if not val:
                continue
            key = val.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(val)
        return normalized

    def _infer_skills_from_context(
        self, parsed_cv: Dict[str, Any], candidate_insights: Dict[str, Any], explicit_skills: List[str]
    ) -> List[str]:
        """
        Infer skills from experience descriptions, roles, projects, and context.
        This is where recruiter-style reasoning happens.
        """
        inferred: List[str] = []
        seen = {s.lower() for s in explicit_skills}

        def add_if_new(skill: str) -> None:
            key = skill.lower()
            if key not in seen:
                seen.add(key)
                inferred.append(skill)

        # Collect all text evidence
        all_text_parts = []
        
        # From summary
        summary = str(parsed_cv.get("summary", "")).lower()
        all_text_parts.append(summary)
        
        # From experience descriptions
        for exp in parsed_cv.get("experience") or []:
            role = str(exp.get("role", "")).lower()
            desc = str(exp.get("description", "")).lower()
            company = str(exp.get("company", "")).lower()
            all_text_parts.extend([role, desc, company])
        
        # From education
        for edu in parsed_cv.get("education") or []:
            degree = str(edu.get("degree", "")).lower()
            institution = str(edu.get("institution", "")).lower()
            all_text_parts.extend([degree, institution])
        
        # From certifications
        for cert in parsed_cv.get("certifications") or []:
            name = str(cert.get("name", "")).lower()
            issuer = str(cert.get("issuer", "")).lower()
            all_text_parts.extend([name, issuer])
        
        combined_text = " ".join(all_text_parts)
        
        # Inference rules (recruiter-style)
        
        # MERN Stack → MongoDB, Express.js, React, Node.js
        if "mern" in combined_text:
            add_if_new("MongoDB")
            add_if_new("Express.js")
            add_if_new("React")
            add_if_new("Node.js")
        
        # React Native → React
        if "react native" in combined_text and "react" not in seen:
            add_if_new("React")
        
        # AI/LLM/Agentic signals → LLMs, NLP, Transformers
        ai_terms = ["ai engineer", "agentic", "llm", "large language model", "language model", "nlp", "natural language"]
        if any(term in combined_text for term in ai_terms):
            add_if_new("LLMs")
            add_if_new("NLP")
            if "transformer" in combined_text or "bert" in combined_text or "gpt" in combined_text:
                add_if_new("Transformers")
        
        # Backend/API work → Node.js, API design
        if any(term in combined_text for term in ["backend", "api", "rest", "graphql", "microservice"]):
            if "node" not in seen and "node.js" not in seen:
                add_if_new("Node.js")
            add_if_new("API Design")
        
        # Full Stack → implies both frontend and backend
        if "full stack" in combined_text or "fullstack" in combined_text:
            if "frontend" not in seen:
                add_if_new("Frontend Development")
            if "backend" not in seen:
                add_if_new("Backend Development")
        
        # Database signals
        if any(term in combined_text for term in ["database", "sql", "postgres", "mysql", "mongodb"]):
            if "database" not in seen:
                add_if_new("Database Design")
        
        # Cloud/AWS signals
        if any(term in combined_text for term in ["aws", "cloud", "azure", "gcp", "deployment"]):
            if "cloud" not in seen:
                add_if_new("Cloud Infrastructure")
        
        # Teaching/Mentoring/Leadership → Communication skills
        leadership_terms = ["teach", "mentor", "lead", "manage", "director", "present", "presentation", "train"]
        if any(term in combined_text for term in leadership_terms):
            add_if_new("Communication")
            add_if_new("Leadership")
        
        # Docker/Containerization
        if "docker" in combined_text or "container" in combined_text:
            add_if_new("Docker")
            add_if_new("Containerization")
        
        # CI/CD signals
        if any(term in combined_text for term in ["ci/cd", "jenkins", "github actions", "gitlab", "pipeline"]):
            add_if_new("CI/CD")
        
        return inferred

    def _match_with_inference(
        self, explicit_skills: List[str], inferred_skills: List[str], job_keywords: List[str]
    ) -> Tuple[List[str], List[str]]:
        """
        Match job keywords against both explicit and inferred skills.
        Uses fuzzy matching and synonym awareness.
        """
        if not job_keywords:
            return [], []
        
        all_skills = explicit_skills + inferred_skills
        skills_lower = {s.lower(): s for s in all_skills}
        
        # Skill equivalences (recruiter knowledge)
        equivalences = {
            "llm": ["llms", "large language model", "language model"],
            "node": ["node.js", "nodejs"],
            "react": ["react.js", "reactjs"],
            "express": ["express.js", "expressjs"],
            "api": ["rest api", "restful", "graphql"],
            "mongodb": ["mongo"],
            "postgresql": ["postgres"],
            "javascript": ["js", "ecmascript"],
            "typescript": ["ts"],
        }
        
        matched = []
        missing = []
        
        for kw in job_keywords:
            kw_lower = kw.lower()
            found = False
            
            # Direct match
            if kw_lower in skills_lower:
                matched.append(kw)
                found = True
            else:
                # Check equivalences
                for canonical, variants in equivalences.items():
                    if kw_lower == canonical or kw_lower in variants:
                        # Check if any variant exists in skills
                        for variant in [canonical] + variants:
                            if variant in skills_lower:
                                matched.append(kw)
                                found = True
                                break
                        if found:
                            break
                
                # Partial/substring match (recruiter-style)
                if not found:
                    for skill_key, skill_val in skills_lower.items():
                        if kw_lower in skill_key or skill_key in kw_lower:
                            matched.append(kw)
                            found = True
                            break
            
            if not found:
                missing.append(kw)
        
        return matched, missing

    def _recruiter_decide(
        self,
        explicit_skills: List[str],
        inferred_skills: List[str],
        matched: List[str],
        missing: List[str],
        role_fit_score: Optional[float],
        total_exp_years: Optional[float],
        parsed_cv: Dict[str, Any],
        candidate_insights: Dict[str, Any],
        enriched_data: Optional[Dict[str, Any]] = None,
        job_keywords: Optional[List[str]] = None,
        interview_threshold: Optional[int] = None,
        hold_threshold: Optional[int] = None,
    ) -> Tuple[str, int]:
        """
        Strict, recruiter-accurate hiring decision based on SKILLS matching.
        Prevents score inflation and ensures only qualified candidates pass.
        
        Decision factors (in order of importance):
        1. Base score (role_fit_score or match-based, not default 50)
        2. Skill evidence (explicit matches weighted 3x, inferred 1x) - 30 points max
        3. Match quality (smooth curve, not binary) - 30 points max
        4. Experience years (minimal) - 8 points max
        5. Seniority level (minimal) - 5 points max
        6. Critical skills penalty (if missing required skills)
        
        Gating: Candidates with < 3 matches or < 35% match ratio are auto-rejected.
        """
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        total_keywords = matched_count + missing_count
        match_ratio = matched_count / max(total_keywords, 1) if total_keywords > 0 else 0.0
        
        # GATING RULE: Stop resume spam - no interview without minimum relevance
        if matched_count < 3 or match_ratio < 0.35:
            return "REJECT", 0
        
        # BASE SCORE: Fix inflation - no default 50
        if role_fit_score is not None:
            base_score = role_fit_score  # Already normalized 0-100
        elif matched_count == 0:
            base_score = 20  # Unknown/weak = low start
        elif match_ratio < 0.4:
            base_score = 30  # Weak match starts low
        else:
            base_score = 40  # Only real matches get neutral base
        
        # SKILL EVIDENCE SCORE: Explicit > Inferred (weighted)
        # Explicit matches weighted 3x, inferred 1x
        skill_evidence_score = min(
            30,  # Reduced cap to avoid quantity bias
            (matched_count * 3) + (len(inferred_skills) * 1)
        )
        
        # MATCH QUALITY SCORE: Smooth curve, not binary
        match_quality = 0
        if total_keywords > 0:
            if match_ratio >= 0.8:
                match_quality = 30  # Excellent match
            elif match_ratio >= 0.65:
                match_quality = 22  # Strong match
            elif match_ratio >= 0.5:
                match_quality = 12  # Moderate match
            elif match_ratio >= 0.35:
                match_quality = 5   # Weak but acceptable
            else:
                match_quality = 0   # Too weak
        
        # Experience years boost (minimal)
        exp_boost = 0
        if total_exp_years is not None:
            if total_exp_years >= 5:
                exp_boost = 8
            elif total_exp_years >= 3:
                exp_boost = 5
            elif total_exp_years >= 1:
                exp_boost = 2
        
        # Seniority boost (minimal)
        seniority_boost = 0
        if enriched_data and enriched_data.get("seniority_level"):
            seniority = enriched_data.get("seniority_level", "").upper()
            if seniority in ["SENIOR", "LEAD", "MANAGER"]:
                seniority_boost = 5
            elif seniority in ["MID"]:
                seniority_boost = 3
            elif seniority in ["JUNIOR"]:
                seniority_boost = 1
        
        # CRITICAL SKILL PENALTY: Hard reality check
        # Check if job_keywords contains critical_skills info or use enriched_data
        critical_penalty = 0
        if enriched_data and enriched_data.get("critical_skills"):
            critical_skills = enriched_data.get("critical_skills", [])
            if isinstance(critical_skills, list) and critical_skills:
                # Count missing critical skills
                all_candidate_skills = [s.lower() for s in explicit_skills + inferred_skills]
                missing_critical = 0
                for crit_skill in critical_skills:
                    crit_lower = str(crit_skill).lower()
                    if not any(crit_lower in skill or skill in crit_lower for skill in all_candidate_skills):
                        missing_critical += 1
                
                # Apply penalty
                if missing_critical >= 2:
                    critical_penalty = -20
                elif missing_critical == 1:
                    critical_penalty = -10
        
        # Calculate final score - SKILLS FOCUSED
        final_score = int(
            base_score
            + skill_evidence_score
            + match_quality
            + exp_boost
            + seniority_boost
            + critical_penalty
        )
        final_score = max(0, min(100, final_score))
        
        # DECISION THRESHOLDS: Use custom thresholds if provided, otherwise use defaults
        interview_thresh = interview_threshold if interview_threshold is not None else 65
        hold_thresh = hold_threshold if hold_threshold is not None else 45
        
        if final_score >= interview_thresh:
            decision = "INTERVIEW"  # Strong candidates only
        elif final_score >= hold_thresh:
            decision = "HOLD"  # HOLD becomes meaningful
        else:
            decision = "REJECT"  # Weak candidates rejected
        
        return decision, final_score

    def _assign_priority(
        self, decision: str, confidence: int, total_exp_years: Optional[float], matched: List[str], inferred_skills: List[str], enriched_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Assign priority based on decision and confidence.
        Only INTERVIEW candidates get priority (HIGH or MEDIUM).
        HOLD and REJECT get None/LOW.
        """
        # Use enriched seniority_level if available
        seniority = None
        if enriched_data and enriched_data.get("seniority_level"):
            seniority = enriched_data.get("seniority_level", "").upper()
        
        if decision == "INTERVIEW":
            # HIGH: Score >= 75 AND (experience >= 3 years OR seniority is SENIOR/LEAD/MANAGER)
            if confidence >= 75 and (total_exp_years and total_exp_years >= 3 or seniority in ["SENIOR", "LEAD", "MANAGER"]):
                return "HIGH"
            # All other INTERVIEW candidates get MEDIUM
            return "MEDIUM"
        
        # HOLD and REJECT get LOW priority
        return "LOW"

    def _build_recruiter_reasoning(
        self,
        decision: str,
        confidence: int,
        matched: List[str],
        inferred_skills: List[str],
        missing: List[str],
        role_fit_score: Optional[float],
        total_exp_years: Optional[float],
        parsed_cv: Dict[str, Any],
        candidate_insights: Dict[str, Any],
        enriched_data: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build clear, recruiter-style reasoning for the decision."""
        reasons = []
        
        # Decision summary
        reasons.append(f"Decision: {decision} (Confidence: {confidence}/100)")
        
        # Use enriched data if available (minimal - focus on skills)
        if enriched_data:
            if enriched_data.get("primary_role"):
                reasons.append(f"Primary role: {enriched_data.get('primary_role')}")
            if enriched_data.get("seniority_level"):
                reasons.append(f"Seniority level: {enriched_data.get('seniority_level')}")
        
        # Skills match summary (job requirements correspondence)
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        total_keywords = matched_count + missing_count
        
        if total_keywords > 0:
            match_percentage = int((matched_count / total_keywords) * 100)
            reasons.append(f"Job Requirements Match: {match_percentage}% ({matched_count}/{total_keywords} skills matched)")
        
        if matched:
            reasons.append(f"Matched required skills: {', '.join(matched[:5])}" + (f" (+{len(matched)-5} more)" if len(matched) > 5 else ""))
        
        if inferred_skills:
            reasons.append(f"Inferred skills from experience/context: {', '.join(inferred_skills[:5])}" + (f" (+{len(inferred_skills)-5} more)" if len(inferred_skills) > 5 else ""))
        
        if total_exp_years is not None:
            reasons.append(f"Professional experience: ~{total_exp_years:.1f} years")
        
        # Role fit context
        if role_fit_score is not None:
            reasons.append(f"Overall role fit score: {role_fit_score}/100")
        
        # Missing skills (only if significant)
        if missing and len(missing) <= 3:
            reasons.append(f"Note: Missing {', '.join(missing)} - consider if critical for role")
        elif missing:
            reasons.append(f"Note: Several skills missing - review requirements")
        
        # Critical skills check (if applicable)
        if enriched_data and enriched_data.get("critical_skills"):
            critical_skills = enriched_data.get("critical_skills", [])
            if isinstance(critical_skills, list) and critical_skills:
                all_candidate_skills = [s.lower() for s in (matched + inferred_skills)]
                missing_critical = []
                for crit_skill in critical_skills:
                    crit_lower = str(crit_skill).lower()
                    if not any(crit_lower in skill or skill in crit_lower for skill in all_candidate_skills):
                        missing_critical.append(crit_skill)
                if missing_critical:
                    reasons.append(f"⚠️ Missing critical skills: {', '.join(missing_critical)}")
        
        # Strengths (skills-focused only)
        strengths = []
        if inferred_skills:
            strengths.append(f"Strong skill inference from experience ({len(inferred_skills)} inferred skills)")
        if matched:
            strengths.append(f"Good skills match ({len(matched)} matched)")
        if enriched_data and enriched_data.get("technical_depth_signals"):
            strengths.append("Strong technical depth indicators")
        
        if strengths:
            reasons.append("Strengths: " + "; ".join(strengths))
        
        return reasons

    # ------------------------
    # Logging
    # ------------------------
    def _log_step(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.log_service.log_event(event_name, metadata or {})

