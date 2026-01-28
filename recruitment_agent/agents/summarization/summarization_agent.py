import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.log_service import LogService
from recruitment_agent.agents.summarization.prompts import SUMMARIZATION_SYSTEM_PROMPT
from recruitment_agent.skill_equivalences import skill_matches_keyword, get_all_match_terms, is_exact_match, is_related_match


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
        LLM is PRIMARY - rule-based is only used as last resort fallback.
        Includes score validation to ensure accuracy.
        """
        self._log_step("summarize_start", {"has_keywords": bool(job_keywords), "use_llm": self.use_llm})
        try:
            validated = self._validate(parsed_cv)
            
            # PRIMARY: Try LLM-based summarization first
            if self.use_llm and self.groq_client:
                try:
                    llm_result = self._llm_summarize(validated, job_keywords)
                    if llm_result:
                        # Validate and correct scores for accuracy
                        manual_exp = self._estimate_total_experience_years(validated.get("experience"))
                        # Use manual experience calculation (more accurate)
                        if manual_exp is not None:
                            llm_result["total_experience_years"] = manual_exp
                        
                        # Validate and correct role_fit_score if needed
                        llm_score = llm_result.get("role_fit_score")
                        should_recalculate = False
                        
                        if llm_score is None or not isinstance(llm_score, (int, float)):
                            should_recalculate = True
                        elif job_keywords and len(job_keywords) > 0:
                            # Validate LLM score against actual weighted skill match percentage
                            all_skills = [s.lower() for s in (validated.get("skills") or [])]
                            job_kw = [k.lower().strip() for k in job_keywords if k]
                            if job_kw:
                                # Calculate weighted matches (exact*1.0 + related*0.5 - missing*0.2) - same as _compute_fit_score
                                # Note: Validation doesn't have missing count, so we approximate without negative scoring
                                exact_matches = 0
                                related_matches = 0
                                
                                for kw in job_kw:
                                    has_exact = False
                                    has_related = False
                                    
                                    # IMPORTANT: Check exact match first, but ensure related matches are NOT added to exact
                                    for sk in all_skills:
                                        # First check if it's an exact match (this function already excludes related matches)
                                        if is_exact_match(sk, kw):
                                            has_exact = True
                                            break  # Found exact match, stop searching
                                        # Only check for related match if we haven't found exact yet
                                        elif not has_exact and is_related_match(sk, kw):
                                            has_related = True
                                            # Don't break - continue checking in case there's an exact match later
                                    
                                    # Count matches - exact takes priority, then related
                                    if has_exact:
                                        exact_matches += 1
                                    elif has_related:
                                        related_matches += 1
                                
                                # Calculate weighted match percentage (normalized by total*1.0)
                                weighted_matches = (exact_matches * 1.0) + (related_matches * 0.5)
                                weighted_match_percentage = (weighted_matches / (len(job_kw) * 1.0)) * 100 if len(job_kw) > 0 else 0
                                
                                # Validate score matches weighted match percentage (with tolerance)
                                # Map weighted percentage to expected score range (same as _compute_fit_score)
                                if weighted_match_percentage >= 90:
                                    expected_max_score = 85
                                elif weighted_match_percentage >= 75:
                                    expected_max_score = 79
                                elif weighted_match_percentage >= 60:
                                    expected_max_score = 69
                                elif weighted_match_percentage >= 50:
                                    expected_max_score = 54
                                elif weighted_match_percentage >= 30:
                                    expected_max_score = 39
                                elif weighted_match_percentage >= 15:
                                    expected_max_score = 24
                                else:
                                    # For <15%, calculate: ratio * (10/0.15) = ratio * 66.67
                                    expected_max_score = int(weighted_match_percentage * (10 / 0.15))
                                
                                # Be strict: LLM score should not exceed expected max by much
                                # Allow 10% tolerance above, but be very strict for low matches
                                if weighted_match_percentage < 10 and llm_score > 10:
                                    should_recalculate = True  # Very low match (<10%) should never give >10 score
                                    self._log_step("validation_triggered", {
                                        "reason": "very_low_match_high_score",
                                        "weighted_match_percentage": weighted_match_percentage,
                                        "llm_score": llm_score,
                                        "expected_max": expected_max_score
                                    })
                                elif weighted_match_percentage < 20 and llm_score > 20:
                                    should_recalculate = True  # Low match (<20%) should never give >20 score
                                    self._log_step("validation_triggered", {
                                        "reason": "low_match_high_score",
                                        "weighted_match_percentage": weighted_match_percentage,
                                        "llm_score": llm_score,
                                        "expected_max": expected_max_score
                                    })
                                elif weighted_match_percentage < 30 and llm_score > 35:
                                    should_recalculate = True  # Low match (<30%) should never give >35 score
                                    self._log_step("validation_triggered", {
                                        "reason": "moderate_match_high_score",
                                        "weighted_match_percentage": weighted_match_percentage,
                                        "llm_score": llm_score,
                                        "expected_max": expected_max_score
                                    })
                                elif llm_score > expected_max_score * 1.2:  # Don't allow more than 20% above expected
                                    should_recalculate = True
                                    self._log_step("validation_triggered", {
                                        "reason": "score_exceeds_expected",
                                        "weighted_match_percentage": weighted_match_percentage,
                                        "llm_score": llm_score,
                                        "expected_max": expected_max_score
                                    })
                        
                        if should_recalculate:
                            # Recalculate using improved manual method for accuracy
                            key_skills = self._extract_key_skills(validated.get("skills"))
                            all_skills = validated.get("skills") or []  # Use ALL skills for scoring
                            achievements = self._extract_achievements(validated)
                            education_level = self._highest_degree(validated.get("education"))
                            corrected_score, score_metrics = self._compute_fit_score(
                                all_skills,  # Use ALL skills for accurate matching
                                achievements,
                                education_level,
                                llm_result.get("total_experience_years"),
                                job_keywords,
                                validated.get("experience"),
                                validated.get("certifications"),
                                validated.get("education"),
                            )
                            llm_result["role_fit_score"] = corrected_score
                            llm_result["score_breakdown"] = score_metrics
                            # Mark as hybrid (LLM with validated/corrected score)
                            llm_result["summarization_source"] = "llm_validated"
                            self._log_step("score_corrected", {
                                "original_score": llm_score,
                                "corrected_score": corrected_score,
                                "weighted_match_percentage": weighted_match_percentage if 'weighted_match_percentage' in locals() else None,
                                "exact_matches": exact_matches if 'exact_matches' in locals() else None,
                                "related_matches": related_matches if 'related_matches' in locals() else None,
                            })
                        else:
                            # Pure LLM result (validated as accurate)
                            llm_result["summarization_source"] = "llm"
                        
                        self._log_step("summarize_complete", {
                            "role_fit_score": llm_result.get("role_fit_score"), 
                            "source": llm_result.get("summarization_source", "llm")
                        })
                        return llm_result
                except Exception as llm_exc:
                    # Check if it's an auth error (API key expired)
                    from recruitment_agent.core import GroqClientError
                    import time
                    
                    if isinstance(llm_exc, GroqClientError):
                        if llm_exc.is_auth_error:
                            self._log_error("llm_api_key_expired", llm_exc)
                            # Disable LLM for future calls in this session
                            self.use_llm = False
                            # Fall through to rule-based fallback
                        elif llm_exc.is_rate_limit:
                            # Rate limit error - try retry with exponential backoff
                            self._log_error("llm_rate_limit", llm_exc)
                            
                            # Try retry up to 3 times with exponential backoff
                            max_retries = 3
                            retry_delays = [2, 5, 10]  # Wait 2s, 5s, 10s
                            
                            for retry_attempt in range(max_retries):
                                wait_time = retry_delays[retry_attempt]
                                self._log_step("llm_rate_limit_retry", {
                                    "attempt": retry_attempt + 1,
                                    "wait_seconds": wait_time
                                })
                                
                                time.sleep(wait_time)
                                
                                try:
                                    # Retry the LLM call
                                    llm_result = self._llm_summarize(validated, job_keywords)
                                    if llm_result:
                                        # Success after retry - process normally
                                        manual_exp = self._estimate_total_experience_years(validated.get("experience"))
                                        if manual_exp is not None:
                                            llm_result["total_experience_years"] = manual_exp
                                        
                                        # Validate and correct role_fit_score if needed (same logic as above)
                                        llm_score = llm_result.get("role_fit_score")
                                        should_recalculate = False
                                        
                                        if llm_score is None or not isinstance(llm_score, (int, float)):
                                            should_recalculate = True
                                        elif job_keywords and len(job_keywords) > 0:
                                            # Use same weighted validation as above
                                            all_skills = [s.lower() for s in (validated.get("skills") or [])]
                                            job_kw = [k.lower().strip() for k in job_keywords if k]
                                            if job_kw:
                                                # Calculate weighted matches (exact*2.0 + related*1.0)
                                                exact_matches = 0
                                                related_matches = 0
                                                
                                                for kw in job_kw:
                                                    has_exact = False
                                                    has_related = False
                                                    
                                                    for sk in all_skills:
                                                        if is_exact_match(sk, kw):
                                                            has_exact = True
                                                            break
                                                        elif is_related_match(sk, kw):
                                                            has_related = True
                                                    
                                                    if has_exact:
                                                        exact_matches += 1
                                                    elif has_related:
                                                        related_matches += 1
                                                
                                                weighted_matches = (exact_matches * 1.0) + (related_matches * 0.5)
                                                weighted_match_percentage = (weighted_matches / (len(job_kw) * 1.0)) * 100 if len(job_kw) > 0 else 0
                                                
                                                # Map weighted percentage to expected score range (same as _compute_fit_score)
                                                if weighted_match_percentage >= 90:
                                                    expected_max_score = 85
                                                elif weighted_match_percentage >= 75:
                                                    expected_max_score = 79
                                                elif weighted_match_percentage >= 60:
                                                    expected_max_score = 69
                                                elif weighted_match_percentage >= 50:
                                                    expected_max_score = 54
                                                elif weighted_match_percentage >= 30:
                                                    expected_max_score = 39
                                                elif weighted_match_percentage >= 15:
                                                    expected_max_score = 24
                                                else:
                                                    expected_max_score = int(weighted_match_percentage * (10 / 0.15))
                                                
                                                # Be strict: LLM score should not exceed expected max by much
                                                if weighted_match_percentage < 10 and llm_score > 10:
                                                    should_recalculate = True
                                                elif weighted_match_percentage < 20 and llm_score > 20:
                                                    should_recalculate = True
                                                elif weighted_match_percentage < 30 and llm_score > 35:
                                                    should_recalculate = True
                                                elif llm_score > expected_max_score * 1.2:
                                                    should_recalculate = True
                                        
                                        if should_recalculate:
                                            key_skills = self._extract_key_skills(validated.get("skills"))
                                            all_skills = validated.get("skills") or []
                                            achievements = self._extract_achievements(validated)
                                            education_level = self._highest_degree(validated.get("education"))
                                            corrected_score, score_metrics = self._compute_fit_score(
                                                all_skills,
                                                achievements,
                                                education_level,
                                                llm_result.get("total_experience_years"),
                                                job_keywords,
                                                validated.get("experience"),
                                                validated.get("certifications"),
                                                validated.get("education"),
                                            )
                                            llm_result["role_fit_score"] = corrected_score
                                            llm_result["score_breakdown"] = score_metrics
                                            llm_result["summarization_source"] = "llm_validated"
                                        else:
                                            llm_result["summarization_source"] = "llm"
                                        
                                        self._log_step("llm_rate_limit_retry_success", {
                                            "attempt": retry_attempt + 1
                                        })
                                        self._log_step("summarize_complete", {
                                            "role_fit_score": llm_result.get("role_fit_score"), 
                                            "source": llm_result.get("summarization_source", "llm")
                                        })
                                        return llm_result
                                except GroqClientError as retry_exc:
                                    if retry_exc.is_rate_limit:
                                        # Still rate limited - continue to next retry
                                        continue
                                    else:
                                        # Different error - break and fall through
                                        break
                                except Exception as retry_exc:
                                    # Other error during retry - break and fall through
                                    self._log_error("llm_retry_error", retry_exc)
                                    break
                            
                            # All retries failed - fall through to rule-based fallback
                            self._log_error("llm_rate_limit_exhausted", {"max_retries": max_retries})
                        elif llm_exc.is_request_too_large:
                            # Request too large - try minimal approach first
                            self._log_error("llm_request_too_large", llm_exc)
                            self._log_step("llm_trying_minimal_approach", {})
                            
                            try:
                                # Try minimal LLM approach (only essential data)
                                minimal_result = self._llm_summarize_minimal(validated, job_keywords)
                                if minimal_result:
                                    # Validate minimal LLM result (same validation as regular LLM)
                                    minimal_score = minimal_result.get("role_fit_score")
                                    should_recalculate_minimal = False
                                    
                                    if minimal_score is None or not isinstance(minimal_score, (int, float)):
                                        should_recalculate_minimal = True
                                    elif job_keywords and len(job_keywords) > 0:
                                        # Calculate weighted matches for validation
                                        all_skills = [s.lower() for s in (validated.get("skills") or [])]
                                        job_kw = [k.lower().strip() for k in job_keywords if k]
                                        if job_kw:
                                            exact_matches = 0
                                            related_matches = 0
                                            
                                            for kw in job_kw:
                                                has_exact = False
                                                has_related = False
                                                
                                                for sk in all_skills:
                                                    if is_exact_match(sk, kw):
                                                        has_exact = True
                                                        break
                                                    elif is_related_match(sk, kw):
                                                        has_related = True
                                                
                                                if has_exact:
                                                    exact_matches += 1
                                                elif has_related:
                                                    related_matches += 1
                                            
                                            weighted_matches = (exact_matches * 1.0) + (related_matches * 0.5)
                                            weighted_match_percentage = (weighted_matches / (len(job_kw) * 1.0)) * 100 if len(job_kw) > 0 else 0
                                            
                                            # Map weighted percentage to expected score range
                                            if weighted_match_percentage >= 90:
                                                expected_max_score = 85
                                            elif weighted_match_percentage >= 75:
                                                expected_max_score = 79
                                            elif weighted_match_percentage >= 60:
                                                expected_max_score = 69
                                            elif weighted_match_percentage >= 50:
                                                expected_max_score = 54
                                            elif weighted_match_percentage >= 30:
                                                expected_max_score = 39
                                            elif weighted_match_percentage >= 15:
                                                expected_max_score = 24
                                            else:
                                                expected_max_score = int(weighted_match_percentage * (10 / 0.15))
                                            
                                            # Strict validation for minimal LLM results
                                            if weighted_match_percentage < 10 and minimal_score > 10:
                                                should_recalculate_minimal = True
                                                self._log_step("minimal_validation_triggered", {
                                                    "reason": "very_low_match_high_score",
                                                    "weighted_match_percentage": weighted_match_percentage,
                                                    "minimal_score": minimal_score,
                                                    "expected_max": expected_max_score
                                                })
                                            elif weighted_match_percentage < 20 and minimal_score > 20:
                                                should_recalculate_minimal = True
                                                self._log_step("minimal_validation_triggered", {
                                                    "reason": "low_match_high_score",
                                                    "weighted_match_percentage": weighted_match_percentage,
                                                    "minimal_score": minimal_score,
                                                    "expected_max": expected_max_score
                                                })
                                            elif weighted_match_percentage < 30 and minimal_score > 35:
                                                should_recalculate_minimal = True
                                                self._log_step("minimal_validation_triggered", {
                                                    "reason": "moderate_match_high_score",
                                                    "weighted_match_percentage": weighted_match_percentage,
                                                    "minimal_score": minimal_score,
                                                    "expected_max": expected_max_score
                                                })
                                            elif minimal_score > expected_max_score * 1.2:
                                                should_recalculate_minimal = True
                                                self._log_step("minimal_validation_triggered", {
                                                    "reason": "score_exceeds_expected",
                                                    "weighted_match_percentage": weighted_match_percentage,
                                                    "minimal_score": minimal_score,
                                                    "expected_max": expected_max_score
                                                })
                                    
                                    if should_recalculate_minimal:
                                        # Recalculate using rule-based method
                                        key_skills = self._extract_key_skills(validated.get("skills"))
                                        all_skills = validated.get("skills") or []
                                        achievements = self._extract_achievements(validated)
                                        education_level = self._highest_degree(validated.get("education"))
                                        corrected_score, score_metrics = self._compute_fit_score(
                                            all_skills,
                                            achievements,
                                            education_level,
                                            minimal_result.get("total_experience_years"),
                                            job_keywords,
                                            validated.get("experience"),
                                            validated.get("certifications"),
                                            validated.get("education"),
                                        )
                                        minimal_result["role_fit_score"] = corrected_score
                                        minimal_result["score_breakdown"] = score_metrics
                                        minimal_result["summarization_source"] = "llm_minimal_validated"
                                        self._log_step("minimal_score_corrected", {
                                            "original_score": minimal_score,
                                            "corrected_score": corrected_score,
                                            "weighted_match_percentage": weighted_match_percentage if 'weighted_match_percentage' in locals() else None,
                                        })
                                    
                                    self._log_step("llm_minimal_success", {
                                        "role_fit_score": minimal_result.get("role_fit_score")
                                    })
                                    self._log_step("summarize_complete", {
                                        "role_fit_score": minimal_result.get("role_fit_score"), 
                                        "source": minimal_result.get("summarization_source", "llm_minimal")
                                    })
                                    return minimal_result
                            except Exception as minimal_exc:
                                self._log_error("llm_minimal_failed", minimal_exc)
                                # Fall through to rule-based fallback
                        else:
                            # Other GroqClientError
                            self._log_error("llm_summarize_failed", llm_exc)
                    else:
                        # Non-GroqClientError exception
                        self._log_error("llm_summarize_failed", llm_exc)
                    # Fall through to rule-based fallback
            
            # FALLBACK: Rule-based approach (only used if LLM fails or unavailable)
            total_exp = self._estimate_total_experience_years(validated.get("experience"))
            key_skills = self._extract_key_skills(validated.get("skills"))
            all_skills = validated.get("skills") or []  # Use ALL skills for scoring
            education_level = self._highest_degree(validated.get("education"))
            achievements = self._extract_achievements(validated)
            fit_score, score_metrics = self._compute_fit_score(
                all_skills,  # Use ALL skills for accurate matching
                achievements,
                education_level,
                total_exp,
                job_keywords,
                validated.get("experience"),
                validated.get("certifications"),
                validated.get("education"),
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
                "summarization_source": "rule_based_fallback",
                "score_breakdown": score_metrics,
            }
            self._log_step("summarize_complete", {
                "role_fit_score": fit_score, 
                "source": "rule_based_fallback"
            })
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
        PRIMARY method - full LLM analysis with score validation.
        Automatically reduces input size if too large.
        """
        try:
            # Prepare input data for LLM (with size reduction if needed)
            reduced_cv = self._reduce_cv_size(parsed_cv)
            input_data = {
                "parsed_cv": reduced_cv,
                "job_keywords": job_keywords if job_keywords else None,
            }
            
            # Convert to JSON string for LLM
            input_text = json.dumps(input_data, indent=2, ensure_ascii=False)
            
            self._log_step("llm_summarize_request", {"length": len(input_text), "has_keywords": bool(job_keywords)})
            
            # Call LLM with full prompt
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
            # Re-raise GroqClientError to check for auth errors in caller
            from recruitment_agent.core import GroqClientError
            if isinstance(exc, GroqClientError):
                raise
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
        """
        Calculate total experience years based on actual work duration.
        
        Priority:
        1. If duration is explicitly mentioned in description (e.g., "3 months", "6 months"), use that
        2. If not, estimate based on project type and complexity from description
        3. If no description, fall back to date range calculation (but only if dates are close together)
        
        This prevents overestimating experience when someone worked on small projects spread over years.
        """
        if not experience or not isinstance(experience, list):
            return None
        
        import re
        total_months = 0
        
        for item in experience:
            if not isinstance(item, dict):
                continue
            
            description = str(item.get("description", "")).lower()
            role = str(item.get("role", "")).lower()
            company = str(item.get("company", "")).lower()
            
            # PRIORITY 1: Check if duration is explicitly mentioned in description
            duration_months = self._extract_duration_from_text(description + " " + role + " " + company)
            
            if duration_months is not None:
                # Use explicit duration
                total_months += duration_months
                continue
            
            # PRIORITY 2: Estimate based on project type and complexity
            estimated_months = self._estimate_project_duration(description, role)
            
            if estimated_months is not None:
                total_months += estimated_months
                continue
            
            # PRIORITY 3: Fall back to date range, but only if dates are close (within 2 years)
            # This handles full-time jobs where dates are meaningful
            start = self._parse_date(item.get("start_date"))
            end_raw = item.get("end_date")
            now = datetime.utcnow()
            end = self._parse_date(end_raw) if end_raw and str(end_raw).lower() != "present" else now
            
            if start and end:
                date_months = max(0, (end.year - start.year) * 12 + (end.month - start.month))
                # Only use date range if it's reasonable (not a huge gap)
                # If date range is > 24 months, it's likely a gap - estimate conservatively
                if date_months <= 24:
                    total_months += date_months
                else:
                    # Large gap - estimate based on role type (likely part-time/freelance)
                    estimated = self._estimate_from_role_type(role, description, date_months)
                    total_months += estimated
        
        if total_months == 0:
            return None
        return round(total_months / 12.0, 2)
    
    def _reduce_cv_size(self, parsed_cv: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reduce CV data size to avoid exceeding token limits.
        Truncates long descriptions, limits skills, and shortens text fields.
        """
        reduced = parsed_cv.copy()
        
        # Limit skills to top 30 most relevant
        if isinstance(reduced.get("skills"), list):
            reduced["skills"] = reduced["skills"][:30]
        
        # Truncate experience descriptions (max 500 chars each)
        if isinstance(reduced.get("experience"), list):
            for exp in reduced["experience"]:
                if isinstance(exp, dict) and exp.get("description"):
                    desc = str(exp["description"])
                    if len(desc) > 500:
                        exp["description"] = desc[:497] + "..."
        
        # Truncate summary (max 300 chars)
        if reduced.get("summary"):
            summary = str(reduced["summary"])
            if len(summary) > 300:
                reduced["summary"] = summary[:297] + "..."
        
        # Limit certifications (max 10)
        if isinstance(reduced.get("certifications"), list):
            reduced["certifications"] = reduced["certifications"][:10]
        
        # Limit education entries (max 5)
        if isinstance(reduced.get("education"), list):
            reduced["education"] = reduced["education"][:5]
        
        # Limit experience entries (max 10)
        if isinstance(reduced.get("experience"), list):
            reduced["experience"] = reduced["experience"][:10]
        
        return reduced
    
    def _extract_duration_from_text(self, text: str) -> Optional[float]:
        """Extract explicit duration mentioned in text (e.g., '3 months', '6 months', '1 year')."""
        import re
        if not text:
            return None
        
        # Patterns for duration extraction
        patterns = [
            (r'(\d+)\s*(?:month|months|mo|mos)', 1),  # "3 months", "6 months"
            (r'(\d+)\s*(?:year|years|yr|yrs|y)', 12),  # "1 year", "2 years"
            (r'(\d+)\s*(?:week|weeks|wk|wks)', 0.25),  # "4 weeks" = 1 month
            (r'(\d+)\s*(?:day|days|d)', 0.033),  # "30 days" = 1 month
        ]
        
        for pattern, multiplier in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Take the largest duration mentioned (most likely the actual project duration)
                durations = [float(match) * multiplier for match in matches]
                return max(durations)
        
        return None
    
    def _estimate_project_duration(self, description: str, role: str) -> Optional[float]:
        """
        Estimate project duration based on project type and complexity.
        
        Returns estimated months, or None if cannot estimate.
        """
        if not description and not role:
            return None
        
        text = (description + " " + role).lower()
        
        # Keywords indicating project types and typical durations
        # Small projects / tasks
        small_project_keywords = [
            'bug fix', 'small fix', 'minor update', 'quick task', 'small task',
            'simple', 'basic', 'small project', 'mini project', 'side project',
            'personal project', 'hobby project', 'learning project'
        ]
        
        # Medium projects
        medium_project_keywords = [
            'feature', 'module', 'component', 'api', 'service', 'application',
            'website', 'web app', 'mobile app', 'dashboard', 'portal'
        ]
        
        # Large projects
        large_project_keywords = [
            'enterprise', 'platform', 'system', 'architecture', 'infrastructure',
            'migration', 'refactoring', 'rebuild', 'redesign', 'full stack',
            'microservices', 'distributed', 'scalable', 'production'
        ]
        
        # Check for small projects (typically 1-3 months)
        if any(keyword in text for keyword in small_project_keywords):
            # Small projects: 1-3 months average
            return 2.0
        
        # Check for large/complex projects (typically 6-12+ months)
        if any(keyword in text for keyword in large_project_keywords):
            # Large projects: 6-12 months average
            return 9.0
        
        # Check for medium projects (typically 3-6 months)
        if any(keyword in text for keyword in medium_project_keywords):
            # Medium projects: 3-6 months average
            return 4.5
        
        # If description mentions specific technologies that indicate complexity
        # Full-stack or complex tech stack suggests longer duration
        complex_tech_keywords = [
            'react', 'angular', 'vue', 'node', 'django', 'flask', 'spring',
            'microservices', 'kubernetes', 'docker', 'aws', 'azure', 'gcp',
            'database', 'backend', 'frontend', 'full stack'
        ]
        
        if any(keyword in text for keyword in complex_tech_keywords):
            # Has complex tech - likely a medium project
            return 4.5
        
        # If role suggests full-time employment (not project-based)
        full_time_keywords = [
            'software engineer', 'developer', 'engineer', 'programmer',
            'senior', 'lead', 'manager', 'architect', 'consultant'
        ]
        
        if any(keyword in text for keyword in full_time_keywords):
            # Likely full-time role - return None to use date range instead
            return None
        
        # Default: if we can't determine, assume small project (conservative estimate)
        return 2.0
    
    def _estimate_from_role_type(self, role: str, description: str, date_range_months: int) -> float:
        """
        Estimate actual work months when date range is large (likely gaps between projects).
        
        If someone worked on projects in 2021, 2023, 2025, the date range might be 4 years,
        but actual work might only be 6 months total.
        """
        text = (role + " " + description).lower()
        
        # If it's clearly a full-time role, use a portion of the date range
        full_time_indicators = [
            'full time', 'full-time', 'ft', 'permanent', 'employee',
            'software engineer', 'senior', 'lead', 'manager'
        ]
        
        if any(indicator in text for indicator in full_time_indicators):
            # Full-time role - use 80% of date range (accounting for some gaps)
            return date_range_months * 0.8
        
        # Project-based / freelance / contract
        # Estimate conservatively: assume 20-30% of date range is actual work
        return date_range_months * 0.25

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
    
    def _reduce_cv_size(self, parsed_cv: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reduce CV data size to avoid exceeding token limits.
        Truncates long descriptions, limits skills, and shortens text fields.
        """
        reduced = parsed_cv.copy()
        
        # Limit skills to top 30 most relevant
        if isinstance(reduced.get("skills"), list):
            reduced["skills"] = reduced["skills"][:30]
        
        # Truncate experience descriptions (max 500 chars each)
        if isinstance(reduced.get("experience"), list):
            for exp in reduced["experience"]:
                if isinstance(exp, dict) and exp.get("description"):
                    desc = str(exp["description"])
                    if len(desc) > 500:
                        exp["description"] = desc[:497] + "..."
        
        # Truncate summary (max 300 chars)
        if reduced.get("summary"):
            summary = str(reduced["summary"])
            if len(summary) > 300:
                reduced["summary"] = summary[:297] + "..."
        
        # Limit certifications (max 10)
        if isinstance(reduced.get("certifications"), list):
            reduced["certifications"] = reduced["certifications"][:10]
        
        # Limit education entries (max 5)
        if isinstance(reduced.get("education"), list):
            reduced["education"] = reduced["education"][:5]
        
        # Limit experience entries (max 10)
        if isinstance(reduced.get("experience"), list):
            reduced["experience"] = reduced["experience"][:10]
        
        return reduced
    
    def _create_minimal_cv_for_llm(self, parsed_cv: Dict[str, Any], job_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Create a MINIMAL CV representation with ONLY essential data for LLM scoring.
        This is used when even reduced CV is too large.
        
        Strategy: Only send what's absolutely needed for role_fit_score calculation:
        - Skills (for matching)
        - Brief experience summary (role titles + dates only, no descriptions)
        - Job keywords
        - Name (for summary generation)
        
        Everything else (experience calculation, achievements, education) is done rule-based.
        """
        minimal = {
            "name": parsed_cv.get("name"),
            "skills": parsed_cv.get("skills", [])[:50],  # Top 50 skills max
            "experience": []
        }
        
        # Create minimal experience entries (role + dates only, no descriptions)
        if isinstance(parsed_cv.get("experience"), list):
            for exp in parsed_cv.get("experience", [])[:10]:  # Max 10 entries
                if isinstance(exp, dict):
                    minimal_exp = {
                        "role": exp.get("role"),
                        "company": exp.get("company"),
                        "start_date": exp.get("start_date"),
                        "end_date": exp.get("end_date"),
                        # NO description - saves massive tokens
                    }
                    minimal["experience"].append(minimal_exp)
        
        return minimal
    
    def _llm_summarize_minimal(self, parsed_cv: Dict[str, Any], job_keywords: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        LLM summarization using MINIMAL data - only essential fields for scoring.
        Used as fallback when regular _llm_summarize fails due to size.
        """
        try:
            # Create minimal CV representation
            minimal_cv = self._create_minimal_cv_for_llm(parsed_cv, job_keywords)
            
            # Create a simplified prompt that only asks for scoring
            minimal_prompt = """You are an expert AI recruitment assistant. Analyze the candidate's skills and calculate a role fit score.

CRITICAL: Only return JSON with this exact schema:
{
  "role_fit_score": number,  # 0-100 score (REQUIRED)
  "candidate_summary": string | null  # Brief 2-3 sentence summary (optional)
}

CALCULATION RULES - EXACT vs RELATED vs MISSING MATCHES:
1. For EACH job keyword, check candidate's skills:
   - EXACT match (keyword exactly matches skill): Count as 1.0
   - RELATED match (related through technology stack, e.g., C# = .NET): Count as 0.5 (half of exact match)
   - MISSING skill (neither exact nor related match): Subtract 0.2 (1/5th of exact match)
2. Calculate weighted matches: (exact_matches × 1.0) + (related_matches × 0.5) - (missing_matches × 0.2)
3. Calculate weighted_match_percentage = (weighted_matches / (total_keywords × 1.0)) × 100
4. Missing skills reduce the score, so candidates with many missing skills will have lower scores
5. Base score from weighted percentage (70% weight - 0-70 points):
   - >= 90% weighted match → 54-70
   - >= 75% weighted match → 42-53
   - >= 60% weighted match → 28-41
   - >= 45% weighted match → 14-27
   - >= 30% weighted match → 5-13
   - < 30% weighted match → 0-5 (use formula: percentage × (5/0.15))
6. Add experience relevance (10% weight - 0-10 points):
   - If 5+ keywords in experience → +10
   - If 3+ keywords in experience → +7
   - If 1+ keyword in experience → +3
7. Add experience years (8% weight - 0-8 points):
   - If >= 5 years → +8
   - If >= 3 years → +5
   - If >= 1 year → +2
   - If >= 0.5 years → +1
8. Add education relevance (5% weight - 0-5 points):
   - If CS/IT degree → +5
   - If related degree (Engineering, Math) → +3
   - If other degree → +1
9. Add certification relevance (5% weight - 0-5 points):
   - If 2+ relevant certs → +5
   - If 1 relevant cert → +4
   - If any certs → +2
10. Add job stability (2% weight - 0-2 points):
   - If avg tenure >= 2 years → +2
   - If avg tenure >= 1 year → +1
   - If avg tenure < 1 year → +0
11. Final score formula: Skills (0-70) + Experience Relevance (0-10) + Experience Years (0-8) + Education (0-5) + Certifications (0-5) + Job Stability (0-2) = Total
12. Return integer 0-100

IMPORTANT: Low match percentages MUST give low scores!
- 8% match = ~5 points, NOT 85!
- 20% match = ~13 points, NOT 85!
- Only 90%+ matches should give 80-85 points

Return ONLY JSON, no other text."""
            
            input_data = {
                "skills": minimal_cv.get("skills", []),
                "experience_roles": [exp.get("role", "") for exp in minimal_cv.get("experience", []) if exp.get("role")],
                "job_keywords": job_keywords if job_keywords else [],
            }
            
            input_text = json.dumps(input_data, ensure_ascii=False)
            
            self._log_step("llm_summarize_minimal_request", {"length": len(input_text)})
            
            # Call LLM with minimal prompt
            response = self.groq_client.send_prompt(minimal_prompt, input_text)
            
            if not isinstance(response, dict):
                raise GroqClientError("LLM response is not a JSON object")
            
            # Validate role_fit_score
            fit_score = response.get("role_fit_score")
            if not isinstance(fit_score, (int, float)):
                raise ValueError(f"Invalid role_fit_score type: {type(fit_score)}")
            response["role_fit_score"] = int(max(0, min(100, fit_score)))
            
            # Fill in other fields with rule-based calculations (since LLM only did scoring)
            response["total_experience_years"] = self._estimate_total_experience_years(parsed_cv.get("experience"))
            response["key_skills"] = self._extract_key_skills(parsed_cv.get("skills"))
            response["notable_achievements"] = self._extract_achievements(parsed_cv)
            response["education_level"] = self._highest_degree(parsed_cv.get("education"))
            
            # Use LLM summary if provided, otherwise generate rule-based
            if not response.get("candidate_summary"):
                response["candidate_summary"] = self._build_candidate_summary(
                    parsed_cv,
                    response.get("key_skills", []),
                    response.get("total_experience_years"),
                    response.get("education_level"),
                    response.get("notable_achievements", [])
                )
            
            response["summarization_source"] = "llm_minimal"
            self._log_step("llm_summarize_minimal_response", {"role_fit_score": response.get("role_fit_score")})
            return response
            
        except Exception as exc:
            self._log_error("llm_summarize_minimal_error", exc)
            from recruitment_agent.core import GroqClientError
            if isinstance(exc, GroqClientError):
                raise
            return None
    
    def _compute_fit_score(
        self,
        key_skills: List[str],  # ALL skills, not just key_skills subset
        achievements: List[str],
        education_level: Optional[str],
        total_experience_years: Optional[float],
        job_keywords: Optional[List[str]],
        experience: Any,
        certifications: Any,
        education: Any = None,
    ) -> tuple[int, Dict[str, Any]]:
        """
        IMPROVED role_fit_score (0-100): More accurate scoring algorithm with additional metrics.
        
        Weight Distribution:
        1. Skills Match: 70% (0-70 points)
        2. Experience Relevance: 10% (0-10 points)
        3. Experience Years: 8% (0-8 points)
        4. Education Relevance: 5% (0-5 points)
        5. Certification Relevance: 5% (0-5 points)
        6. Job Stability: 2% (0-2 points)
        
        Formula: Role Fit Score = Skills Match + Exp Relevance + Exp Years + Education + Certifications + Job Stability
        
        Returns: (score, metrics_dict) where metrics_dict contains breakdown of each component
        """
        score = 0.0
        metrics = {
            "skills_match_score": 0,
            "experience_relevance_score": 0,
            "experience_years_score": 0,
            "education_relevance_score": 0,
            "certification_relevance_score": 0,
            "job_stability_score": 0,
        }
        
        job_kw = [k.lower().strip() for k in job_keywords] if job_keywords else []
        job_kw = [k for k in job_kw if k]
        job_kw_set = set(job_kw)
        skills_lower = [s.lower() for s in key_skills]

        if job_kw_set:
            # PRIMARY: Skills Match (70 points max) - 70% weight
            exact_matches = 0
            related_matches = 0
            missing_matches = 0
            
            for kw in job_kw_set:
                has_exact = False
                has_related = False
                
                # IMPORTANT: Check exact match first, but ensure related matches are NOT added to exact
                for sk in skills_lower:
                    if is_exact_match(sk, kw):
                        has_exact = True
                        break
                    elif not has_exact and is_related_match(sk, kw):
                        has_related = True
                
                if has_exact:
                    exact_matches += 1
                elif has_related:
                    related_matches += 1
                else:
                    missing_matches += 1
            
            total_keywords = len(job_kw_set)
            weighted_matches = (exact_matches * 1.0) + (related_matches * 0.5) - (missing_matches * 0.2)
            weighted_match_ratio = weighted_matches / (total_keywords * 1.0) if total_keywords > 0 else 0.0
            weighted_match_ratio = max(0.0, min(1.0, weighted_match_ratio))
            
            # Convert to 0-70 points (70% weight)
            if weighted_match_ratio >= 0.90:
                skills_score = 70
            elif weighted_match_ratio >= 0.75:
                skills_score = 54 + int((weighted_match_ratio - 0.75) * 107)  # 54-70 range
            elif weighted_match_ratio >= 0.60:
                skills_score = 42 + int((weighted_match_ratio - 0.60) * 80)  # 42-53 range
            elif weighted_match_ratio >= 0.45:
                skills_score = 28 + int((weighted_match_ratio - 0.45) * 93)  # 28-41 range
            elif weighted_match_ratio >= 0.30:
                skills_score = 14 + int((weighted_match_ratio - 0.30) * 93)  # 14-27 range
            elif weighted_match_ratio >= 0.15:
                skills_score = 5 + int((weighted_match_ratio - 0.15) * 60)  # 5-13 range
            else:
                skills_score = int(weighted_match_ratio * (5 / 0.15))  # 0-5 range
            
            score += skills_score
            metrics["skills_match_score"] = skills_score
            metrics["exact_matches_count"] = exact_matches
            metrics["related_matches_count"] = related_matches
            metrics["missing_matches_count"] = missing_matches
            metrics["missing_penalty"] = missing_matches * 0.2  # Penalty per missing skill
            metrics["weighted_matches"] = weighted_matches
            metrics["weighted_match_ratio"] = weighted_match_ratio
            
            # SECONDARY: Experience Relevance (10 points max) - 10% weight
            exp_keywords_found = set()
            if experience and isinstance(experience, list):
                # Build a comprehensive text from all experience entries
                all_exp_text = []
                for item in experience:
                    if not isinstance(item, dict):
                        continue
                    exp_text = " ".join([
                        str(item.get("role", "")),
                        str(item.get("company", "")),
                        str(item.get("description", "")),
                    ]).lower()
                    all_exp_text.append(exp_text)
                
                combined_exp_text = " ".join(all_exp_text)
                
                # Check each job keyword against experience text
                for kw in job_kw_set:
                    kw_lower = kw.lower().strip()
                    if not kw_lower:
                        continue
                    
                    # Get all match terms for this keyword (includes equivalents)
                    terms = get_all_match_terms(kw_lower)
                    # Also add the keyword itself
                    terms.add(kw_lower)
                    
                    # Check if any term appears in experience text
                    if any(term in combined_exp_text for term in terms):
                        exp_keywords_found.add(kw)
            
            exp_match_count = len(exp_keywords_found)
            if exp_match_count >= 5:
                exp_relevance_score = 10
            elif exp_match_count >= 3:
                exp_relevance_score = 7
            elif exp_match_count >= 1:
                exp_relevance_score = 3
            else:
                exp_relevance_score = 0
            
            score += exp_relevance_score
            metrics["experience_relevance_score"] = exp_relevance_score
            
            # TERTIARY: Experience Years (8 points max) - 8% weight
            exp_years_score = 0
            if total_experience_years:
                if total_experience_years >= 5:
                    exp_years_score = 8
                elif total_experience_years >= 3:
                    exp_years_score = 5
                elif total_experience_years >= 1:
                    exp_years_score = 2
                elif total_experience_years >= 0.5:
                    exp_years_score = 1
            
            score += exp_years_score
            metrics["experience_years_score"] = exp_years_score
            
            # FOURTH: Education Relevance (5 points max) - 5% weight
            education_score = self._calculate_education_relevance(education, education_level)
            # Scale down from 10 to 5 points
            education_score = min(5, int(education_score / 2))
            score += education_score
            metrics["education_relevance_score"] = education_score
            
            # FIFTH: Certification Relevance (5 points max) - 5% weight
            cert_score = self._calculate_certification_relevance(certifications, job_keywords)
            # Scale down from 10 to 5 points
            cert_score = min(5, int(cert_score / 2))
            score += cert_score
            metrics["certification_relevance_score"] = cert_score
            
            # SIXTH: Job Stability (2 points max) - 2% weight
            stability_score = self._calculate_job_stability(experience)
            # Scale down from 5 to 2 points
            stability_score = min(2, int(stability_score / 2.5))
            score += stability_score
            metrics["job_stability_score"] = stability_score
        else:
            # No job keywords - evaluate based on skill depth (fallback)
            skill_count = len(key_skills)
            if skill_count >= 15:
                score += 85
            elif skill_count >= 10:
                score += 70
            elif skill_count >= 7:
                score += 55
            elif skill_count >= 5:
                score += 40
            elif skill_count >= 3:
                score += 25
            else:
                score += skill_count * 8.0
            
            if total_experience_years:
                score += min(10, total_experience_years * 1.5)
            
            # Still calculate metrics even without job keywords
            education_score = self._calculate_education_relevance(education, education_level)
            cert_score = self._calculate_certification_relevance(certifications, None)
            stability_score = self._calculate_job_stability(experience)
            # Scale down to match new weights
            metrics["education_relevance_score"] = min(5, int(education_score / 2))
            metrics["certification_relevance_score"] = min(5, int(cert_score / 2))
            metrics["job_stability_score"] = min(2, int(stability_score / 2.5))
            # Set defaults for missing skills breakdown (no job keywords)
            metrics["exact_matches_count"] = 0
            metrics["related_matches_count"] = 0
            metrics["missing_matches_count"] = 0
            metrics["missing_penalty"] = 0
            metrics["weighted_matches"] = 0
            metrics["weighted_match_ratio"] = 0

        final_score = int(max(0, min(100, math.floor(score))))
        return final_score, metrics

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

    def _calculate_education_relevance(self, education: Any, education_level: Optional[str]) -> int:
        """
        Calculate education relevance score (0-10 points).
        Relevant CS/IT degrees get full points, related degrees get partial.
        """
        # Check both education_level and education array
        education_text = ""
        
        if education_level:
            education_text += " " + str(education_level).lower()
        
        if education and isinstance(education, list):
            for edu_item in education:
                if isinstance(edu_item, dict):
                    degree = edu_item.get("degree", "")
                    institution = edu_item.get("institution", "")
                    if degree:
                        education_text += " " + str(degree).lower()
                    if institution:
                        education_text += " " + str(institution).lower()
        
        if not education_text.strip():
            return 0
        
        education_lower = education_text.lower()
        
        # Highly relevant degrees (CS, IT, Software Engineering)
        relevant_degrees = [
            "computer science", "cs", "information technology", "it", 
            "software engineering", "computer engineering", "ce",
            "information systems", "is", "computing", "software", "programming",
            "computer", "computing science", "cs degree", "bsc cs", "ms cs", "mcs"
        ]
        
        # Related degrees (Engineering, Math, Physics)
        related_degrees = [
            "engineering", "electrical engineering", "ee", "mechanical engineering",
            "math", "mathematics", "physics", "statistics", "bachelor", "master",
            "bsc", "msc", "mtech", "btech"
        ]
        
        if any(deg in education_lower for deg in relevant_degrees):
            return 10
        elif any(deg in education_lower for deg in related_degrees):
            return 5
        else:
            return 2  # Other degree
    
    def _calculate_certification_relevance(self, certifications: Any, job_keywords: Optional[List[str]]) -> int:
        """
        Calculate certification relevance score (0-10 points).
        Highly relevant certs (AWS, Azure, GCP, tech-specific) get full points.
        """
        if not certifications or not isinstance(certifications, list):
            return 0
        
        if not job_keywords:
            # Without job keywords, just check if they have any certifications
            return 5 if len(certifications) > 0 else 0
        
        job_kw_lower = [kw.lower() for kw in job_keywords]
        
        # Highly relevant certifications
        highly_relevant = [
            "aws", "amazon web services", "azure", "microsoft azure", "gcp", "google cloud",
            "kubernetes", "docker", "terraform", "jenkins", "gitlab", "github",
            "oracle", "microsoft", "cisco", "red hat", "vmware"
        ]
        
        # Check each certification
        relevant_count = 0
        for cert in certifications:
            if not isinstance(cert, dict):
                continue
            
            cert_name = str(cert.get("name", "")).lower()
            cert_issuer = str(cert.get("issuer", "")).lower()
            cert_text = f"{cert_name} {cert_issuer}"
            
            # Check if cert matches job keywords
            for kw in job_kw_lower:
                if kw in cert_text or cert_text in kw:
                    relevant_count += 1
                    break
            
            # Check if cert is highly relevant
            if any(rel in cert_text for rel in highly_relevant):
                relevant_count += 1
        
        if relevant_count >= 2:
            return 10
        elif relevant_count >= 1:
            return 7
        elif len(certifications) > 0:
            return 3
        else:
            return 0
    
    def _calculate_job_stability(self, experience: Any) -> int:
        """
        Calculate job stability score (0-5 points) based on average tenure.
        High stability (>2 years avg) = 5, Moderate (1-2 years) = 3, Low (<1 year) = 1
        """
        if not experience or not isinstance(experience, list):
            return 0
        
        tenures = []
        for item in experience:
            if not isinstance(item, dict):
                continue
            
            start_date = item.get("start_date")
            end_date = item.get("end_date")
            
            # Try to extract dates from description if not in date fields
            if not start_date and not end_date:
                description = str(item.get("description", "")).lower()
                # Look for duration mentions like "2 years", "6 months", etc.
                import re
                duration_match = re.search(r'(\d+)\s*(year|years|yr|yrs|month|months|mo|mos)', description)
                if duration_match:
                    value = int(duration_match.group(1))
                    unit = duration_match.group(2).lower()
                    if 'year' in unit or 'yr' in unit:
                        tenures.append(float(value))
                    elif 'month' in unit or 'mo' in unit:
                        tenures.append(value / 12.0)
                    continue
            
            if not start_date:
                continue
            
            try:
                # Parse dates (handle various formats)
                start = self._parse_date(start_date)
                if not start:
                    continue
                
                if end_date and str(end_date).lower() not in ["present", "current", "now", "ongoing"]:
                    end = self._parse_date(end_date)
                    if end and end > start:
                        tenure_months = (end.year - start.year) * 12 + (end.month - start.month)
                        # Ensure minimum 1 month
                        if tenure_months < 1:
                            tenure_months = 1
                        tenures.append(tenure_months / 12.0)  # Convert to years
                else:
                    # Current job - use current date
                    from datetime import datetime
                    end = datetime.now()
                    tenure_months = (end.year - start.year) * 12 + (end.month - start.month)
                    # Ensure minimum 1 month
                    if tenure_months < 1:
                        tenure_months = 1
                    tenures.append(tenure_months / 12.0)
            except Exception:
                continue
        
        if not tenures:
            # If no dates found, but has experience entries, give minimal score
            if len(experience) > 0:
                return 1
            return 0
        
        avg_tenure = sum(tenures) / len(tenures)
        
        if avg_tenure >= 2.0:
            return 5
        elif avg_tenure >= 1.0:
            return 3
        else:
            return 1
    
    def _parse_date(self, date_str: str):
        """Parse date string to datetime object, handling various formats."""
        if not date_str:
            return None
        
        from datetime import datetime
        
        date_str = str(date_str).strip()
        
        # Common formats
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%Y",
            "%Y-%m",
            "%Y",
            "%B %Y",
            "%b %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None
    
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

