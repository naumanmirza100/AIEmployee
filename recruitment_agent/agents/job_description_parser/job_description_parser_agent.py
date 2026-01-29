import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.log_service import LogService
from recruitment_agent.agents.job_description_parser.prompts import JOB_DESCRIPTION_PARSING_SYSTEM_PROMPT


class JobDescriptionParserAgent:
    """
    Agent that extracts keywords, skills, and requirements from job descriptions.
    Uses LLM to intelligently parse job descriptions and extract structured data.
    """

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        log_service: Optional[LogService] = None,
    ) -> None:
        self.groq_client = groq_client or GroqClient()
        self.log_service = log_service or LogService()

    def parse_file(self, filepath: str) -> Dict[str, Any]:
        """
        Parse job description from a file (PDF, DOCX, TXT).
        
        Args:
            filepath: Path to job description file
            
        Returns:
            Dictionary with extracted job keywords and requirements
        """
        path = Path(filepath)
        if not path.exists():
            self._log_step("file_not_found", {"path": str(path)})
            raise FileNotFoundError(f"File not found: {path}")

        ext = path.suffix.lower()
        self._log_step("file_detected", {"path": str(path), "extension": ext})

        try:
            if ext == ".pdf":
                text = self._extract_text_from_pdf(path)
            elif ext == ".docx":
                text = self._extract_text_from_docx(path)
            elif ext == ".txt":
                text = path.read_text(encoding="utf-8", errors="ignore")
            else:
                raise ValueError(f"Unsupported file type: {ext}")
        except Exception as exc:
            self._log_error("text_extraction_failed", exc, {"path": str(path)})
            raise

        return self.parse_text(text)

    def parse_text(self, job_description: str) -> Dict[str, Any]:
        """
        Parse job description text and extract keywords.
        
        Args:
            job_description: Raw job description text
            
        Returns:
            Dictionary with extracted keywords and requirements
        """
        cleaned_text = self._clean_text(job_description)
        if not cleaned_text:
            self._log_step("empty_text_after_cleaning", {})
            raise ValueError("Provided job description text is empty after cleaning.")

        self._log_step("parsing_start", {"length": len(cleaned_text)})
        parsed = self._call_groq(cleaned_text)
        normalized = self._normalize_output(parsed)
        
        # Ensure keywords array is populated with all technical terms
        if not normalized.get("keywords") or len(normalized.get("keywords", [])) == 0:
            normalized["keywords"] = self._combine_keywords(normalized)
        
        self._log_step("parsing_complete", {
            "keywords_count": len(normalized.get("keywords", [])),
            "required_skills_count": len(normalized.get("required_skills", []))
        })
        return normalized

    def get_keywords(self, job_description: str) -> List[str]:
        """
        Quick method to get just the keywords array for matching.
        
        Args:
            job_description: Job description text
            
        Returns:
            List of keywords for candidate matching
        """
        parsed = self.parse_text(job_description)
        return parsed.get("keywords", [])

    def _extract_text_from_pdf(self, path: Path) -> str:
        """Extract text from PDF file."""
        import pdfplumber
        self._log_step("pdf_extraction_started", {"path": str(path)})
        texts: List[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    texts.append(page_text)
        combined = "\n".join(texts)
        self._log_step("pdf_extraction_complete", {"length": len(combined)})
        return combined

    def _extract_text_from_docx(self, path: Path) -> str:
        """Extract text from DOCX file."""
        from docx import Document
        self._log_step("docx_extraction_started", {"path": str(path)})
        doc = Document(path)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        combined = "\n".join(paragraphs)
        self._log_step("docx_extraction_complete", {"length": len(combined)})
        return combined

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        # Remove excessive whitespace
        cleaned = " ".join(text.split())
        return cleaned.strip()

    def _call_groq(self, text: str) -> Dict[str, Any]:
        """Call Groq LLM to parse job description."""
        try:
            result = self.groq_client.send_prompt(JOB_DESCRIPTION_PARSING_SYSTEM_PROMPT, text)
            return result
        except GroqClientError as exc:
            # Check if it's an auth error (API key expired)
            if exc.is_auth_error:
                self._log_error("groq_api_key_expired", exc)
                raise GroqClientError(
                    "Groq API key expired or invalid. Job description parsing requires valid API key. "
                    "Please update GROQ_REC_API_KEY in environment variables.",
                    is_auth_error=True
                ) from exc
            self._log_error("groq_parsing_failed", exc)
            raise

    def _normalize_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate extracted data."""
        normalized: Dict[str, Any] = {
            "job_title": self._to_string_or_none(data.get("job_title")),
            "required_skills": self._normalize_list(data.get("required_skills")),
            "preferred_skills": self._normalize_list(data.get("preferred_skills")),
            "technologies": self._normalize_list(data.get("technologies")),
            "programming_languages": self._normalize_list(data.get("programming_languages")),
            "frameworks": self._normalize_list(data.get("frameworks")),
            "tools": self._normalize_list(data.get("tools")),
            "cloud_platforms": self._normalize_list(data.get("cloud_platforms")),
            "databases": self._normalize_list(data.get("databases")),
            "experience_years": self._to_number_or_none(data.get("experience_years")),
            "education_requirements": self._normalize_list(data.get("education_requirements")),
            "certifications": self._normalize_list(data.get("certifications")),
            "soft_skills": self._normalize_list(data.get("soft_skills")),
            "keywords": self._normalize_list(data.get("keywords")),
        }
        return normalized

    def _normalize_list(self, value: Any) -> List[str]:
        """Normalize list values."""
        if not value:
            return []
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if item and str(item).strip()]
            # Remove duplicates while preserving order
            seen = set()
            result = []
            for item in cleaned:
                item_lower = item.lower()
                if item_lower not in seen:
                    seen.add(item_lower)
                    result.append(item)
            return result
        return []

    def _to_string_or_none(self, value: Any) -> Optional[str]:
        """Convert value to string or None."""
        if not value:
            return None
        result = str(value).strip()
        return result if result else None

    def _to_number_or_none(self, value: Any) -> Optional[float]:
        """Convert value to number or None."""
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)):
                return float(value)
            result = float(str(value).strip())
            return result if result >= 0 else None
        except (ValueError, TypeError):
            return None

    def _combine_keywords(self, parsed_data: Dict[str, Any]) -> List[str]:
        """Combine all technical terms into keywords array."""
        keywords = []
        keyword_fields = [
            "required_skills",
            "preferred_skills",
            "technologies",
            "programming_languages",
            "frameworks",
            "tools",
            "cloud_platforms",
            "databases",
        ]
        
        seen = set()
        for field in keyword_fields:
            items = parsed_data.get(field, [])
            for item in items:
                item_lower = item.lower()
                if item_lower not in seen:
                    seen.add(item_lower)
                    keywords.append(item)
        
        return keywords

    def _log_step(self, event_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log a step in the parsing process."""
        self.log_service.log_event(event_name, metadata or {})

    def _log_error(self, event_name: str, exc: Exception, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log an error."""
        error_data = {"error": str(exc), "type": type(exc).__name__}
        if metadata:
            error_data.update(metadata)
        self.log_service.log_error(event_name, error_data)

