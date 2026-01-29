import re
from typing import Any, Dict, List, Optional, Tuple

from recruitment_agent.log_service import LogService
from recruitment_agent.skill_equivalences import skill_matches_keyword, is_exact_match, is_related_match


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
        
        # Infer stack-based common skills (e.g., MERN stack → Backend business logic, CRUD, etc.)
        stack_related_skills = self._infer_stack_related_skills(all_skills, inferred_skills, parsed_cv)
        
        # Combine all skills for matching (explicit + inferred + stack-related)
        all_skills_for_matching = list(set(all_skills + inferred_skills + stack_related_skills))
        
        # Match against job keywords using inference-aware matching
        # Pass all skills as explicit_skills (stack-related are treated as additional skills)
        exact_matched, related_matched, missing = self._match_with_inference(all_skills_for_matching, [], normalized_keywords)
        
        # Combine exact and related for backward compatibility
        matched = exact_matched + related_matched
        
        # Evaluate overall fit using recruiter-style reasoning
        role_fit_score = candidate_insights.get("role_fit_score")
        total_exp_years = candidate_insights.get("total_experience_years")
        decision, confidence, confidence_breakdown = self._recruiter_decide(
            all_skills, inferred_skills, matched, missing, exact_matched, related_matched, role_fit_score, total_exp_years, parsed_cv, candidate_insights, enriched_data, job_keywords, interview_threshold, hold_threshold
        )
        priority = self._assign_priority(decision, confidence, total_exp_years, matched, inferred_skills, enriched_data)
        
        reasoning = self._build_recruiter_reasoning(
            decision, confidence, exact_matched, related_matched, inferred_skills, missing, role_fit_score, total_exp_years, parsed_cv, candidate_insights, enriched_data
        )
        
        # Calculate match percentage for ranking visibility
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        total_keywords = matched_count + missing_count
        match_percentage = int((matched_count / max(total_keywords, 1)) * 100) if total_keywords > 0 else 0

        result = {
            "decision": decision,
            "confidence_score": confidence,
            "confidence_breakdown": confidence_breakdown,
            "priority": priority,
            "matched_skills": matched or None,
            "exact_matched_skills": exact_matched or None,
            "related_matched_skills": related_matched or None,
            "inferred_skills": inferred_skills or None,
            "stack_related_skills": stack_related_skills or None,  # Stack-based inferred skills
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
        # Only infer if "MERN" is explicitly mentioned (not individual components)
        if "mern" in combined_text and "mern stack" in combined_text:
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
        # Only infer if explicitly mentioned as "full stack" role
        if ("full stack" in combined_text or "fullstack" in combined_text) and any(term in combined_text for term in ["developer", "engineer", "role", "position"]):
            if "frontend" not in seen:
                add_if_new("Frontend Development")
            if "backend" not in seen:
                add_if_new("Backend Development")
        
        # Database signals - only if they actually worked with databases (not just mentioned)
        # Look for action verbs indicating database work
        db_action_verbs = ["designed database", "created database", "managed database", "database design", "database schema", "database modeling"]
        if any(verb in combined_text for verb in db_action_verbs):
            if "database" not in seen and "database design" not in seen:
                add_if_new("Database Design")
        
        # Cloud/AWS signals
        if any(term in combined_text for term in ["aws", "cloud", "azure", "gcp", "deployment"]):
            if "cloud" not in seen:
                add_if_new("Cloud Infrastructure")
        
        # Teaching/Mentoring/Leadership → Communication skills
        # Only infer if there's strong evidence (not just mentions in job titles)
        leadership_strong_terms = ["mentored", "taught", "trained", "led team", "managed team", "presented to", "director of"]
        if any(term in combined_text for term in leadership_strong_terms):
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

    def _infer_stack_related_skills(
        self, explicit_skills: List[str], inferred_skills: List[str], parsed_cv: Dict[str, Any]
    ) -> List[str]:
        """
        Infer common skills that are typically associated with technology stacks.
        E.g., MERN stack developers typically know: Backend business logic, CRUD operations, Authentication, etc.
        """
        stack_related: List[str] = []
        seen = {s.lower() for s in (explicit_skills + inferred_skills)}
        
        def add_if_new(skill: str) -> None:
            key = skill.lower()
            if key not in seen:
                seen.add(key)
                stack_related.append(skill)
        
        # Collect all skills (explicit + inferred) for stack detection
        all_skills_lower = [s.lower() for s in (explicit_skills + inferred_skills)]
        combined_skills_text = " ".join(all_skills_lower)
        
        # Common full-stack skills (applies to most web development stacks)
        common_fullstack_skills = [
            "Backend business logic",
            "Database management",
            "CRUD operations",
            "Authentication",
            "Authorization",
            "Frontend–backend API integration",
            "Debugging",
            "Performance optimization",
            "Application deployment",
            "Clean code practices",
            "Scalable architecture"
        ]
        
        # MERN/MEAN/MEVN Stack - JavaScript-based full stack
        # Only infer if "MERN/MEAN/MEVN" is explicitly mentioned OR they have 3+ components
        has_mern_explicit = any(term in combined_skills_text for term in ["mern", "mean", "mevn"])
        mern_components = sum([
            "mongodb" in combined_skills_text or "mongo" in combined_skills_text,
            "express" in combined_skills_text or "express.js" in combined_skills_text,
            "react" in combined_skills_text or "angular" in combined_skills_text or "vue" in combined_skills_text,
            "node.js" in combined_skills_text or "nodejs" in combined_skills_text or "node" in combined_skills_text
        ])
        
        if has_mern_explicit or mern_components >= 3:  # Changed from 2 to 3
            for skill in common_fullstack_skills:
                add_if_new(skill)
            # JavaScript-specific
            if "es6" not in seen and "es2015" not in seen:
                add_if_new("ES6+")
        
        # Django Stack - Python-based full stack
        if "django" in combined_skills_text or "python" in combined_skills_text:
            # Check if they have Django + at least one other web component
            has_django = "django" in combined_skills_text
            has_python_web = any(term in combined_skills_text for term in ["flask", "fastapi", "python"])
            
            if has_django or (has_python_web and any(term in combined_skills_text for term in ["sql", "postgresql", "mysql", "database"])):
                for skill in common_fullstack_skills:
                    add_if_new(skill)
                # Python-specific
                if "orm" not in seen:
                    add_if_new("ORM")
                if "rest api" not in seen and "restful" not in seen:
                    add_if_new("REST API")
        
        # .NET Stack - C# based
        if any(term in combined_skills_text for term in [".net", "c#", "asp.net", "entity framework"]):
            for skill in common_fullstack_skills:
                add_if_new(skill)
            if "linq" not in seen:
                add_if_new("LINQ")
        
        # Spring Boot / Java Stack
        if any(term in combined_skills_text for term in ["spring", "spring boot", "java", "hibernate"]):
            for skill in common_fullstack_skills:
                add_if_new(skill)
            if "jpa" not in seen:
                add_if_new("JPA")
        
        # Laravel / PHP Stack
        if any(term in combined_skills_text for term in ["laravel", "php", "symfony"]):
            for skill in common_fullstack_skills:
                add_if_new(skill)
        
        # React / Frontend frameworks
        if any(term in combined_skills_text for term in ["react", "vue", "angular", "next.js"]):
            if "frontend–backend api integration" not in seen:
                add_if_new("Frontend–backend API integration")
            if "state management" not in seen:
                add_if_new("State Management")
        
        # Backend frameworks (Express, NestJS, etc.)
        if any(term in combined_skills_text for term in ["express", "nestjs", "koa", "fastapi", "flask"]):
            if "backend business logic" not in seen:
                add_if_new("Backend business logic")
            if "api design" not in seen:
                add_if_new("API Design")
            if "crud operations" not in seen:
                add_if_new("CRUD operations")
        
        # Database work - only if they have multiple database-related skills
        db_skills_count = sum([
            "mongodb" in combined_skills_text or "mongo" in combined_skills_text,
            "mysql" in combined_skills_text,
            "postgresql" in combined_skills_text or "postgres" in combined_skills_text,
            "sql" in combined_skills_text,
            "database" in combined_skills_text
        ])
        # Only infer if they have 2+ database skills (not just one mention)
        if db_skills_count >= 2:
            if "database management" not in seen:
                add_if_new("Database management")
            if "crud operations" not in seen:
                add_if_new("CRUD operations")
        
        return stack_related

    def _match_with_inference(
        self, explicit_skills: List[str], inferred_skills: List[str], job_keywords: List[str]
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Match job keywords against both explicit and inferred skills.
        Uses shared skill equivalences (e.g. Node.js ↔ JavaScript) and substring matching.
        Returns: (exact_matches, related_matches, missing)
        """
        if not job_keywords:
            return [], [], []
        
        all_skills = explicit_skills + inferred_skills
        skills_lower = [s.lower() for s in all_skills]
        
        exact_matched = []
        related_matched = []
        missing = []
        
        for kw in job_keywords:
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue
            
            # Check for exact match first
            has_exact = False
            has_related = False
            
            # IMPORTANT: Check exact match first, but ensure related matches are NOT added to exact
            for sk in skills_lower:
                # First check if it's an exact match (this function already excludes related matches)
                if is_exact_match(sk, kw_lower):
                    has_exact = True
                    break  # Found exact match, stop searching
                # Only check for related match if we haven't found exact yet
                elif not has_exact and is_related_match(sk, kw_lower):
                    has_related = True
                    # Don't break - continue checking in case there's an exact match later
                    # But if we find exact later, it will override this
            
            # Add to appropriate list - exact takes priority, then related, then missing
            if has_exact:
                exact_matched.append(kw)
            elif has_related:
                related_matched.append(kw)
            else:
                missing.append(kw)
        
        return exact_matched, related_matched, missing

    def _recruiter_decide(
        self,
        explicit_skills: List[str],
        inferred_skills: List[str],
        matched: List[str],
        missing: List[str],
        exact_matched: List[str],
        related_matched: List[str],
        role_fit_score: Optional[float],
        total_exp_years: Optional[float],
        parsed_cv: Dict[str, Any],
        candidate_insights: Dict[str, Any],
        enriched_data: Optional[Dict[str, Any]] = None,
        job_keywords: Optional[List[str]] = None,
        interview_threshold: Optional[int] = None,
        hold_threshold: Optional[int] = None,
    ) -> Tuple[str, int, Dict[str, Any]]:
        """
        Hiring decision based on SKILLS + EXPERIENCE only.
        No seniority, critical-skills penalty, or other extras.
        
        Factors:
        1. Base score (role_fit_score or match-based) - variable
        2. Skill evidence (explicit 2x, inferred 0.5x) - max 30
        3. Match quality (smooth curve with lower thresholds) - max 30
        4. Experience years - max 8
        
        Formula: Confidence Score = Base Score + Skill Evidence + Match Quality + Experience Boost
        
        Match Quality thresholds:
        - ≥80% match ratio → 30 points
        - ≥65% match ratio → 22 points
        - ≥50% match ratio → 12 points
        - ≥35% match ratio → 5 points
        - ≥20% match ratio → 2 points
        - ≥10% match ratio → 1 point
        - <10% match ratio → 0 points
        
        Note: Confidence score is always calculated, even for weak candidates.
        
        Returns: (decision, confidence_score, confidence_breakdown)
        """
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        exact_count = len(exact_matched) if exact_matched else 0
        related_count = len(related_matched) if related_matched else 0
        total_keywords = matched_count + missing_count
        match_ratio = matched_count / max(total_keywords, 1) if total_keywords > 0 else 0.0
        
        # BASE SCORE
        if role_fit_score is not None:
            base_score = role_fit_score
        elif matched_count == 0:
            base_score = 20
        elif match_ratio < 0.4:
            base_score = 30
        else:
            base_score = 40
        
        # SKILL EVIDENCE: Explicit 2x, inferred 0.5x, missing -0.2x (max 30)
        # Measures: How many skills the candidate has (matched + inferred - missing)
        # Purpose: Rewards candidates with more skills, penalizes missing required skills
        # Formula: (exact × 2) + (related × 2) + (inferred × 0.5) - (missing × 0.2)
        inferred_count = len(inferred_skills) if inferred_skills else 0
        skill_evidence_raw = (matched_count * 2) + (inferred_count * 0.5) - (missing_count * 0.2)
        # Cap at 30, floor at 0 (can't go negative)
        skill_evidence_score = max(0, min(30, int(skill_evidence_raw)))
        
        # Calculate exact and related match contributions to skill evidence
        exact_match_contribution = exact_count * 2
        related_match_contribution = related_count * 2  # Related matches also count as matched_count
        inferred_contribution = inferred_count * 0.5
        missing_penalty = missing_count * 0.2
        
        # MATCH QUALITY (max 30) - Add lower thresholds so even small matches get some points
        # Measures: What percentage of required skills are matched (match_ratio)
        # Purpose: Rewards candidates who match a higher percentage of job requirements
        # Example: 7/10 skills matched (70%) gets more points than 3/10 (30%)
        match_quality = 0
        if total_keywords > 0:
            if match_ratio >= 0.8:
                match_quality = 30
            elif match_ratio >= 0.65:
                match_quality = 22
            elif match_ratio >= 0.5:
                match_quality = 12
            elif match_ratio >= 0.35:
                match_quality = 5
            elif match_ratio >= 0.20:
                match_quality = 2  # 20-34% match gets 2 points
            elif match_ratio >= 0.10:
                match_quality = 1  # 10-19% match gets 1 point
            # Below 10% stays at 0
        
        # EXPERIENCE ONLY (max 8) - no seniority, no critical penalty
        exp_boost = 0
        if total_exp_years is not None:
            if total_exp_years >= 5:
                exp_boost = 8
            elif total_exp_years >= 3:
                exp_boost = 5
            elif total_exp_years >= 1:
                exp_boost = 2
        
        # Final score = skills + experience only
        final_score = int(base_score + skill_evidence_score + match_quality + exp_boost)
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
        
        # Build confidence score breakdown
        confidence_breakdown = {
            "base_score": base_score,
            "skill_evidence_score": skill_evidence_score,
            "match_quality_score": match_quality,
            "experience_boost": exp_boost,
            "matched_count": matched_count,
            "exact_matched_count": exact_count,
            "related_matched_count": related_count,
            "missing_count": missing_count,
            "inferred_count": len(inferred_skills) if inferred_skills else 0,
            "match_ratio": round(match_ratio * 100, 1) if total_keywords > 0 else 0.0,
            "total_keywords": total_keywords,
            # Skill evidence breakdown
            "exact_match_contribution": exact_match_contribution,
            "related_match_contribution": related_match_contribution,
            "inferred_contribution": inferred_contribution,
            "missing_penalty": missing_penalty,
            # Match quality explanation
            "match_quality_explanation": f"{matched_count}/{total_keywords} skills matched ({round(match_ratio * 100, 1)}%)" if total_keywords > 0 else "No job keywords",
        }
        
        return decision, final_score, confidence_breakdown

    def _assign_priority(
        self, decision: str, confidence: int, total_exp_years: Optional[float], matched: List[str], inferred_skills: List[str], enriched_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Priority from skills + experience only (no seniority).
        HIGH = INTERVIEW + confidence >= 75 + experience >= 3; else MEDIUM. HOLD/REJECT = LOW.
        """
        if decision == "INTERVIEW":
            if confidence >= 75 and total_exp_years is not None and total_exp_years >= 3:
                return "HIGH"
            return "MEDIUM"
        return "LOW"

    def _build_recruiter_reasoning(
        self,
        decision: str,
        confidence: int,
        exact_matched: List[str],
        related_matched: List[str],
        inferred_skills: List[str],
        missing: List[str],
        role_fit_score: Optional[float],
        total_exp_years: Optional[float],
        parsed_cv: Dict[str, Any],
        candidate_insights: Dict[str, Any],
        enriched_data: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Build clear, recruiter-style reasoning for the decision.
        Returns formatted list with proper sections and separators.
        """
        reasons = []
        
        # ========== DECISION SECTION ==========
        decision_emoji = "✅" if decision == "INTERVIEW" else "⏸️" if decision == "HOLD" else "❌"
        reasons.append(f"{decision_emoji} **Decision:** {decision}")
        reasons.append(f"**Confidence Score:** {confidence}/100")
        reasons.append("")  # Empty line separator
        
        # ========== CANDIDATE PROFILE SECTION ==========
        if enriched_data:
            if enriched_data.get("primary_role"):
                reasons.append(f"**Primary Role:** {enriched_data.get('primary_role')}")
            if enriched_data.get("seniority_level"):
                reasons.append(f"**Seniority Level:** {enriched_data.get('seniority_level')}")
            if enriched_data.get("primary_role") or enriched_data.get("seniority_level"):
                reasons.append("")  # Empty line separator
        
        # ========== SKILLS MATCH SECTION ==========
        matched = exact_matched + related_matched
        matched_count = len(matched) if matched else 0
        missing_count = len(missing) if missing else 0
        total_keywords = matched_count + missing_count
        
        if total_keywords > 0:
            match_percentage = int((matched_count / total_keywords) * 100)
            match_emoji = "🟢" if match_percentage >= 70 else "🟡" if match_percentage >= 50 else "🔴"
            reasons.append(f"{match_emoji} **Job Requirements Match:** {match_percentage}% ({matched_count}/{total_keywords} skills matched)")
            reasons.append("")
        
        # Matched skills - separate exact and related
        matched = exact_matched + related_matched
        if exact_matched or related_matched:
            # Exact matches
            if exact_matched:
                exact_display = exact_matched[:10]  # Show up to 10
                exact_text = ", ".join(exact_display)
                if len(exact_matched) > 10:
                    exact_text += f" (+{len(exact_matched) - 10} more)"
                reasons.append(f"✓ **Exact Matches:** {exact_text}")
            
            # Related matches
            if related_matched:
                related_display = related_matched[:10]  # Show up to 10
                related_text = ", ".join(related_display)
                if len(related_matched) > 10:
                    related_text += f" (+{len(related_matched) - 10} more)"
                reasons.append(f"🔗 **Related Matches:** {related_text}")
            
            reasons.append("")
        
        # Inferred skills - removed from display per user request
        # Skills are still used for matching and scoring, just not displayed
        
        # Missing skills
        if missing:
            if len(missing) <= 5:
                reasons.append(f"⚠️ **Missing Skills:** {', '.join(missing)}")
            else:
                missing_display = missing[:5]
                reasons.append(f"⚠️ **Missing Skills:** {', '.join(missing_display)} (+{len(missing) - 5} more)")
            reasons.append("")
        
        # ========== EXPERIENCE & SCORES SECTION ==========
        if total_exp_years is not None:
            reasons.append(f"📅 **Professional Experience:** ~{total_exp_years:.1f} years")
        
        if role_fit_score is not None:
            score_emoji = "🟢" if role_fit_score >= 70 else "🟡" if role_fit_score >= 50 else "🔴"
            reasons.append(f"{score_emoji} **Role Fit Score:** {int(role_fit_score)}")
        
        if total_exp_years is not None or role_fit_score is not None:
            reasons.append("")  # Empty line separator
        
        # ========== CRITICAL SKILLS SECTION ==========
        if enriched_data and enriched_data.get("critical_skills"):
            critical_skills = enriched_data.get("critical_skills", [])
            if isinstance(critical_skills, list) and critical_skills:
                all_candidate_skills = [s.lower() for s in (exact_matched + related_matched + inferred_skills)]
                missing_critical = []
                for crit_skill in critical_skills:
                    crit_lower = str(crit_skill).lower()
                    if not any(crit_lower in skill or skill in crit_lower for skill in all_candidate_skills):
                        missing_critical.append(crit_skill)
                if missing_critical:
                    reasons.append(f"🚨 **Missing Critical Skills:** {', '.join(missing_critical)}")
                    reasons.append("")
        
        # ========== STRENGTHS SECTION ==========
        strengths = []
        if inferred_skills:
            strengths.append(f"Strong skill inference ({len(inferred_skills)} inferred skills)")
        matched = exact_matched + related_matched
        if matched:
            exact_count = len(exact_matched)
            related_count = len(related_matched)
            if exact_count > 0 and related_count > 0:
                strengths.append(f"Good skills match ({exact_count} exact, {related_count} related)")
            elif exact_count > 0:
                strengths.append(f"Good skills match ({exact_count} exact matches)")
            else:
                strengths.append(f"Good skills match ({related_count} related matches)")
        if enriched_data and enriched_data.get("technical_depth_signals"):
            strengths.append("Strong technical depth indicators")
        if total_exp_years and total_exp_years >= 3:
            strengths.append(f"Solid experience ({total_exp_years:.1f} years)")
        
        if strengths:
            reasons.append("**Strengths:**")
            for strength in strengths:
                reasons.append(f"  • {strength}")
        
        return reasons

    # ------------------------
    # Logging
    # ------------------------
    def _log_step(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.log_service.log_event(event_name, metadata or {})

