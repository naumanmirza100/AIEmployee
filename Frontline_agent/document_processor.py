"""
Document Processing Service for Frontline Agent
Handles document parsing and text extraction from various file formats
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Service for processing and extracting text from documents"""
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.doc': 'doc',
        '.txt': 'txt',
        '.md': 'md',
        '.html': 'html',
        '.htm': 'html',
    }
    
    # Max file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    @staticmethod
    def get_file_hash(file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def get_file_format(filename: str) -> str:
        """Get file format from filename"""
        ext = Path(filename).suffix.lower()
        return DocumentProcessor.SUPPORTED_EXTENSIONS.get(ext, 'other')
    
    @staticmethod
    def validate_file(file_path: str, file_size: int) -> Tuple[bool, Optional[str]]:
        """Validate file before processing"""
        if file_size > DocumentProcessor.MAX_FILE_SIZE:
            return False, f"File size exceeds maximum allowed size ({DocumentProcessor.MAX_FILE_SIZE / 1024 / 1024}MB)"
        
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        return True, None
    
    @staticmethod
    def extract_text(file_path: str, file_format: str) -> Tuple[bool, str, Optional[str]]:
        """
        Extract text from document based on file format.
        
        Returns:
            Tuple of (success, extracted_text, error_message)
        """
        try:
            if file_format == 'txt':
                return DocumentProcessor._extract_txt(file_path)
            elif file_format == 'md':
                return DocumentProcessor._extract_txt(file_path)  # Markdown is text
            elif file_format == 'html':
                return DocumentProcessor._extract_html(file_path)
            elif file_format == 'pdf':
                return DocumentProcessor._extract_pdf(file_path)
            elif file_format == 'docx':
                return DocumentProcessor._extract_docx(file_path)
            elif file_format == 'doc':
                return DocumentProcessor._extract_doc(file_path)
            else:
                return False, '', f"Unsupported file format: {file_format}"
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}", exc_info=True)
            return False, '', str(e)
    
    @staticmethod
    def _extract_txt(file_path: str) -> Tuple[bool, str, Optional[str]]:
        """Extract text from plain text file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return True, content, None
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                return True, content, None
            except Exception as e:
                return False, '', f"Failed to read text file: {str(e)}"
        except Exception as e:
            return False, '', f"Error reading text file: {str(e)}"
    
    @staticmethod
    def _extract_html(file_path: str) -> Tuple[bool, str, Optional[str]]:
        """Extract text from HTML file"""
        try:
            from bs4 import BeautifulSoup
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text()
                # Clean up whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
            return True, text, None
        except ImportError:
            # Fallback to basic extraction if BeautifulSoup not available
            return DocumentProcessor._extract_txt(file_path)
        except Exception as e:
            return False, '', f"Error extracting HTML: {str(e)}"
    
    @staticmethod
    def _extract_pdf(file_path: str) -> Tuple[bool, str, Optional[str]]:
        """Extract text from PDF file"""
        try:
            import PyPDF2
            text = ""
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return True, text.strip(), None
        except ImportError:
            return False, '', "PyPDF2 library not installed. Install with: pip install PyPDF2"
        except Exception as e:
            return False, '', f"Error extracting PDF: {str(e)}"
    
    @staticmethod
    def _extract_docx(file_path: str) -> Tuple[bool, str, Optional[str]]:
        """Extract text from DOCX file"""
        try:
            from docx import Document
            doc = Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return True, text, None
        except ImportError:
            return False, '', "python-docx library not installed. Install with: pip install python-docx"
        except Exception as e:
            return False, '', f"Error extracting DOCX: {str(e)}"
    
    @staticmethod
    def _extract_doc(file_path: str) -> Tuple[bool, str, Optional[str]]:
        """Extract text from DOC file (legacy Word format)"""
        # DOC files are more complex, may require additional libraries
        # For now, return error suggesting conversion to DOCX
        return False, '', "DOC format not directly supported. Please convert to DOCX format."
    
    @staticmethod
    def process_document(file_path: str, filename: str) -> Dict:
        """
        Process a document: validate, extract text, and return metadata.
        
        Returns:
            Dictionary with processing results
        """
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        # Validate file
        is_valid, error_msg = DocumentProcessor.validate_file(file_path, file_size)
        if not is_valid:
            return {
                'success': False,
                'error': error_msg,
                'file_hash': None,
                'file_format': None,
                'extracted_text': '',
            }
        
        # Get file format
        file_format = DocumentProcessor.get_file_format(filename)
        
        # Calculate file hash
        file_hash = DocumentProcessor.get_file_hash(file_path)
        
        # Extract text
        success, extracted_text, extract_error = DocumentProcessor.extract_text(file_path, file_format)
        
        if not success:
            return {
                'success': False,
                'error': extract_error or 'Failed to extract text',
                'file_hash': file_hash,
                'file_format': file_format,
                'extracted_text': '',
            }
        
        return {
            'success': True,
            'file_hash': file_hash,
            'file_format': file_format,
            'extracted_text': extracted_text,
            'file_size': file_size,
            'error': None,
        }

