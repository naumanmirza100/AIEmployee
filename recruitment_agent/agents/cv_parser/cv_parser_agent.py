import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pdfplumber
from docx import Document

try:
    import spacy
    SPACY_AVAILABLE = True
except (ImportError, TypeError, Exception):
    # Catch all exceptions during spacy import to handle compatibility issues
    # (e.g., pydantic compatibility issues with Python 3.12)
    SPACY_AVAILABLE = False
    spacy = None
    # Note: To use spaCy NER, install spaCy and download the model:
    # pip install spacy
    # python -m spacy download en_core_web_sm

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.log_service import LogService
from recruitment_agent.agents.cv_parser.prompts import CV_PARSING_SYSTEM_PROMPT


class CVParserAgent:
    """
    Autonomous CV parser that extracts structured candidate data.
    """

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        log_service: Optional[LogService] = None,
    ) -> None:
        self.groq_client = groq_client or GroqClient()
        self.log_service = log_service or LogService()
        self._nlp = None
        if SPACY_AVAILABLE and spacy is not None:
            try:
                # Try to load spaCy model, fallback to regex if not available
                self._nlp = spacy.load("en_core_web_sm")
                self._log_step("spacy_model_loaded", {"model": "en_core_web_sm"})
            except (OSError, Exception):
                # Model not installed or other error, will use regex fallback
                self._log_step("spacy_model_not_found", {"fallback": "regex"})
                self._nlp = None

    def parse_file(self, filepath: str) -> Dict[str, Any]:
        """
        Detect file type, extract text, and parse into structured JSON.
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
        except Exception as exc:  # pragma: no cover - propagated
            self._log_error("text_extraction_failed", exc, {"path": str(path)})
            raise

        return self.parse_text(text)

    def parse_text(self, text: str) -> Dict[str, Any]:
        """
        Parse raw text into structured CV JSON.
        """
        cleaned_text = self._clean_text(text)
        if not cleaned_text:
            self._log_step("empty_text_after_cleaning", {})
            raise ValueError("Provided text is empty after cleaning.")

        self._log_step("text_ready", {"length": len(cleaned_text)})
        
        # Extract email using NER before calling Groq
        ner_email = self._extract_email_with_ner(cleaned_text)
        if ner_email:
            self._log_step("email_extracted_with_ner", {"email": ner_email})
        
        parsed = self._call_groq(cleaned_text)
        
        # Use NER-extracted email if Groq didn't find one, or prefer NER if both found
        if ner_email:
            parsed["email"] = ner_email
        
        normalized = self._normalize_output(parsed)
        self._log_step("parse_complete", {"extracted_keys": list(normalized.keys())})
        return normalized

    def parse_multiple(self, cvs: List[str]) -> List[Dict[str, Any]]:
        """
        Parse multiple CVs provided as raw text strings.
        """
        results: List[Dict[str, Any]] = []
        self._log_step("batch_parse_start", {"count": len(cvs)})
        for idx, cv_text in enumerate(cvs):
            self._log_step("cv_processing_start", {"index": idx})
            try:
                parsed = self.parse_text(cv_text)
                results.append(parsed)
            except Exception as exc:  # pragma: no cover - propagate after logging
                self._log_error("cv_processing_failed", exc, {"index": idx})
                raise
            self._log_step("cv_processing_complete", {"index": idx})
        self._log_step("batch_parse_complete", {"count": len(results)})
        return results

    def _extract_text_from_pdf(self, path: Path) -> str:
        """
        Extract text from a PDF using pdfplumber.
        """
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
        """
        Extract text from a DOCX using python-docx.
        """
        self._log_step("docx_extraction_started", {"path": str(path)})
        doc = Document(path)
        paragraphs = [para.text for para in doc.paragraphs if para.text]
        combined = "\n".join(paragraphs)
        self._log_step("docx_extraction_complete", {"length": len(combined)})
        return combined

    def _call_groq(self, cleaned_text: str) -> Dict[str, Any]:
        """
        Send cleaned text to Groq for structured parsing.
        Handles API key expiration gracefully.
        """
        try:
            self._log_step(
                "groq_request",
                {"preview": cleaned_text[:400], "length": len(cleaned_text)},
            )
            response = self.groq_client.send_prompt(
                CV_PARSING_SYSTEM_PROMPT, cleaned_text
            )
            self._log_step(
                "groq_response_received", {"response_type": type(response).__name__}
            )
            if not isinstance(response, dict):
                raise GroqClientError("Groq response is not a JSON object.")
            return response
        except GroqClientError as exc:
            # Check if it's an auth error (API key expired)
            if exc.is_auth_error:
                self._log_error("groq_api_key_expired", exc)
                # Re-raise with clear message
                raise GroqClientError(
                    "Groq API key expired or invalid. CV parsing requires valid API key. "
                    "Please update GROQ_REC_API_KEY in environment variables.",
                    is_auth_error=True
                ) from exc
            # Re-raise other GroqClientErrors
            raise
        except Exception as exc:  # pragma: no cover - propagated
            self._log_error("groq_call_failed", exc)
            raise

    def _normalize_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure required keys exist and values are well-typed.
        """
        normalized: Dict[str, Any] = {
            "name": self._to_string_or_none(data.get("name")),
            "email": self._to_string_or_none(data.get("email")),
            "phone": self._to_string_or_none(data.get("phone")),
            "skills": self._normalize_skill_list(data.get("skills")),
            "experience": self._normalize_experience(data.get("experience")),
            "education": self._normalize_education(data.get("education")),
            "certifications": self._normalize_certifications(
                data.get("certifications")
            ),
            "summary": self._to_string_or_none(data.get("summary")),
        }
        return normalized

    def _normalize_skill_list(
        self, skills: Optional[Union[str, List[Any]]]
    ) -> Optional[List[str]]:
        if skills is None:
            return None
        if isinstance(skills, str):
            parts = re.split(r"[;,\n]+", skills)
            cleaned = [part.strip() for part in parts if part.strip()]
            return cleaned or None
        if isinstance(skills, list):
            cleaned_list = [str(item).strip() for item in skills if str(item).strip()]
            return cleaned_list or None
        return None

    def _normalize_experience(
        self, experience: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        if not experience:
            return None
        normalized_list: List[Dict[str, Any]] = []
        for item in experience:
            if not isinstance(item, dict):
                continue
            normalized_item = {
                "role": self._to_string_or_none(item.get("role")),
                "company": self._to_string_or_none(item.get("company")),
                "start_date": self._to_string_or_none(item.get("start_date")),
                "end_date": self._to_string_or_none(item.get("end_date")),
                "description": self._to_string_or_none(item.get("description")),
            }
            if any(normalized_item.values()):
                normalized_list.append(normalized_item)
        return normalized_list or None

    def _normalize_education(
        self, education: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        if not education:
            return None
        normalized_list: List[Dict[str, Any]] = []
        for item in education:
            if not isinstance(item, dict):
                continue
            normalized_item = {
                "degree": self._to_string_or_none(item.get("degree")),
                "institution": self._to_string_or_none(item.get("institution")),
                "graduation_year": self._to_string_or_none(item.get("graduation_year")),
            }
            if any(normalized_item.values()):
                normalized_list.append(normalized_item)
        return normalized_list or None

    def _normalize_certifications(
        self, certifications: Optional[Union[List[Any], str]]
    ) -> Optional[List[Dict[str, Any]]]:
        if certifications is None:
            return None
        normalized_list: List[Dict[str, Any]] = []

        if isinstance(certifications, str):
            items = [
                item.strip() for item in re.split(r"[;\n]+", certifications) if item.strip()
            ]
            for name in items:
                normalized_list.append({"name": name, "issuer": None, "year": None})
            return normalized_list or None

        if isinstance(certifications, list):
            for cert in certifications:
                if isinstance(cert, dict):
                    normalized_list.append(
                        {
                            "name": self._to_string_or_none(cert.get("name")),
                            "issuer": self._to_string_or_none(cert.get("issuer")),
                            "year": self._to_string_or_none(cert.get("year")),
                        }
                    )
                else:
                    cert_str = str(cert).strip()
                    if cert_str:
                        normalized_list.append(
                            {"name": cert_str, "issuer": None, "year": None}
                        )
            return normalized_list or None

        return None

    def _clean_text(self, text: str) -> str:
        """
        Normalize whitespace and remove non-informative characters.
        """
        cleaned = text.replace("\xa0", " ")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        cleaned = cleaned.strip()
        return cleaned

    def _extract_email_with_ner(self, text: str) -> Optional[str]:
        """
        Extract email address from text using NER (spaCy) with regex fallback.
        Returns the first valid email found, or None if none found.
        """
        # First, try regex pattern (fast and reliable for emails)
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        regex_emails = re.findall(email_pattern, text)
        
        if regex_emails:
            # Return the first valid email (usually the primary one)
            email = regex_emails[0].strip().lower()
            self._log_step("email_extracted_regex", {"email": email, "total_found": len(regex_emails)})
            return email
        
        # If regex didn't find anything, try spaCy NER
        if self._nlp is not None:
            try:
                doc = self._nlp(text)
                # Look for entities that might be emails
                for ent in doc.ents:
                    # Check if entity text matches email pattern
                    if re.match(email_pattern, ent.text):
                        email = ent.text.strip().lower()
                        self._log_step("email_extracted_spacy", {"email": email, "label": ent.label_})
                        return email
            except Exception as exc:
                self._log_error("spacy_ner_extraction_failed", exc)
        
        # No email found
        return None

    def _to_string_or_none(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        stringified = str(value).strip()
        return stringified if stringified else None

    def _log_step(
        self, event_name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.log_service.log_event(event_name, metadata or {})

    def _log_error(
        self, event_name: str, exc: Exception, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        error_meta = metadata or {}
        error_meta.update({"error": str(exc)})
        self.log_service.log_error(event_name, error_meta)


