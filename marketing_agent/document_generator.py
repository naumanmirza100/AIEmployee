"""
Document Generator - Converts marketing documents to various file formats
Supports: PDF, DOCX, PPTX
"""

import io
import re
from typing import Optional
from django.http import HttpResponse
from marketing_agent.models import MarketingDocument

try:
    from docx import Document as DocxDocument
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import black, HexColor
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class DocumentGenerator:
    """Generate documents in various formats"""
    
    @staticmethod
    def generate_docx(document: MarketingDocument) -> HttpResponse:
        """Generate DOCX file from marketing document"""
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx is not installed. Run: pip install python-docx")
        
        doc = DocxDocument()
        
        # Add title
        title = doc.add_heading(document.title, 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add metadata
        doc.add_paragraph(f"Document Type: {document.get_document_type_display()}")
        doc.add_paragraph(f"Status: {document.get_status_display()}")
        doc.add_paragraph(f"Created: {document.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if document.campaign:
            doc.add_paragraph(f"Campaign: {document.campaign.name}")
        doc.add_paragraph("")  # Empty line
        
        # Parse and add content
        content = document.content
        DocumentGenerator._add_content_to_docx(doc, content)
        
        # Create response
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{document.title.replace(" ", "_")}.docx"'
        
        doc.save(response)
        return response
    
    @staticmethod
    def _add_content_to_docx(doc: DocxDocument, content: str):
        """Add formatted content to DOCX document"""
        lines = content.split('\n')
        in_list = False
        
        for line in lines:
            line = line.strip()
            if not line:
                if in_list:
                    in_list = False
                continue
            
            # Headers
            if line.startswith('# '):
                doc.add_heading(line[2:], level=1)
                in_list = False
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
                in_list = False
            elif line.startswith('### '):
                doc.add_heading(line[4:], level=3)
                in_list = False
            # Lists
            elif line.startswith('- ') or line.startswith('* '):
                if not in_list:
                    p = doc.add_paragraph(line[2:], style='List Bullet')
                    in_list = True
                else:
                    doc.add_paragraph(line[2:], style='List Bullet')
            elif re.match(r'^\d+\.\s', line):
                if not in_list:
                    p = doc.add_paragraph(re.sub(r'^\d+\.\s', '', line), style='List Number')
                    in_list = True
                else:
                    doc.add_paragraph(re.sub(r'^\d+\.\s', '', line), style='List Number')
            # Regular paragraph
            else:
                if in_list:
                    in_list = False
                # Handle bold
                para = doc.add_paragraph()
                DocumentGenerator._add_formatted_text(para, line)
    
    @staticmethod
    def _add_formatted_text(para, text: str):
        """Add text with formatting (bold, etc.)"""
        # Simple bold handling
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                para.add_run(part[2:-2]).bold = True
            else:
                para.add_run(part)
    
    @staticmethod
    def generate_pdf(document: MarketingDocument) -> HttpResponse:
        """Generate PDF file from marketing document"""
        if not PDF_AVAILABLE:
            raise ImportError("reportlab is not installed. Run: pip install reportlab")
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=black,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        # Add title
        elements.append(Paragraph(document.title, title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Add metadata
        meta_style = ParagraphStyle(
            'Meta',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#646464')
        )
        elements.append(Paragraph(f"<b>Document Type:</b> {document.get_document_type_display()}", meta_style))
        elements.append(Paragraph(f"<b>Status:</b> {document.get_status_display()}", meta_style))
        elements.append(Paragraph(f"<b>Created:</b> {document.created_at.strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
        if document.campaign:
            elements.append(Paragraph(f"<b>Campaign:</b> {document.campaign.name}", meta_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Parse and add content
        content = document.content
        DocumentGenerator._add_content_to_pdf(elements, content, styles)
        
        # Build PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer and write it to the response
        pdf = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{document.title.replace(" ", "_")}.pdf"'
        return response
    
    @staticmethod
    def _add_content_to_pdf(elements, content: str, styles):
        """Add formatted content to PDF"""
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                elements.append(Spacer(1, 0.1*inch))
                continue
            
            # Headers
            if line.startswith('# '):
                elements.append(Paragraph(line[2:], styles['Heading1']))
                elements.append(Spacer(1, 0.2*inch))
            elif line.startswith('## '):
                elements.append(Paragraph(line[3:], styles['Heading2']))
                elements.append(Spacer(1, 0.15*inch))
            elif line.startswith('### '):
                elements.append(Paragraph(line[4:], styles['Heading3']))
                elements.append(Spacer(1, 0.1*inch))
            # Lists
            elif line.startswith('- ') or line.startswith('* '):
                para = Paragraph(f"• {line[2:]}", styles['Normal'])
                elements.append(para)
                elements.append(Spacer(1, 0.05*inch))
            elif re.match(r'^\d+\.\s', line):
                para = Paragraph(line, styles['Normal'])
                elements.append(para)
                elements.append(Spacer(1, 0.05*inch))
            # Horizontal rule
            elif line.startswith('---') or line.startswith('==='):
                elements.append(Spacer(1, 0.2*inch))
            # Regular paragraph
            else:
                # Handle bold
                formatted_line = line.replace('**', '<b>', 1).replace('**', '</b>', 1)
                para = Paragraph(formatted_line, styles['Normal'])
                elements.append(para)
                elements.append(Spacer(1, 0.1*inch))
    
    @staticmethod
    def generate_pptx(document: MarketingDocument) -> HttpResponse:
        """Generate PPTX file from marketing document (for presentations)"""
        if not PPTX_AVAILABLE:
            raise ImportError("python-pptx is not installed. Run: pip install python-pptx")
        
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        
        content = document.content
        
        # Split content into slides
        slides_content = DocumentGenerator._parse_presentation_slides(content)
        
        if not slides_content:
            # If no slides found, create a single slide with all content
            slide = prs.slides.add_slide(prs.slide_layouts[5])  # Blank layout
            DocumentGenerator._add_text_to_slide(slide, document.title, is_title=True)
            DocumentGenerator._add_text_to_slide(slide, content, is_title=False)
        else:
            # Create slides from parsed content
            for i, slide_content in enumerate(slides_content):
                slide = prs.slides.add_slide(prs.slide_layouts[5])  # Blank layout
                
                # Extract title and content
                title, body = DocumentGenerator._extract_slide_title_body(slide_content)
                
                if title:
                    DocumentGenerator._add_text_to_slide(slide, title, is_title=True)
                if body:
                    DocumentGenerator._add_text_to_slide(slide, body, is_title=False)
        
        # Create response
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
        response['Content-Disposition'] = f'attachment; filename="{document.title.replace(" ", "_")}.pptx"'
        
        prs.save(response)
        return response
    
    @staticmethod
    def _parse_presentation_slides(content: str) -> list:
        """Parse presentation content into individual slides"""
        # Split by slide markers
        slides = re.split(r'(?:^|\n)#\s*Slide\s+\d+:|(?:^|\n)Slide\s+\d+:|(?:^|\n)##\s*Slide\s+\d+:', content, flags=re.IGNORECASE | re.MULTILINE)
        
        # Filter out empty slides
        return [slide.strip() for slide in slides if slide.strip()]
    
    @staticmethod
    def _extract_slide_title_body(slide_content: str) -> tuple:
        """Extract title and body from slide content"""
        lines = slide_content.split('\n')
        title = None
        body_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # First non-empty line is usually the title
            if not title and line and not line.startswith('-') and not line.startswith('*'):
                if len(line) < 100:  # Reasonable title length
                    title = line
                    continue
            
            body_lines.append(line)
        
        body = '\n'.join(body_lines)
        return title, body
    
    @staticmethod
    def _add_text_to_slide(slide, text: str, is_title: bool = False):
        """Add text to a slide"""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        
        # Get slide dimensions
        left = Inches(0.5)
        top = Inches(1) if is_title else Inches(2)
        width = Inches(9)
        height = Inches(5) if is_title else Inches(4.5)
        
        textbox = slide.shapes.add_textbox(left, top, width, height)
        text_frame = textbox.text_frame
        text_frame.word_wrap = True
        
        # Clear default paragraph
        text_frame.clear()
        
        # Add text
        p = text_frame.paragraphs[0]
        p.text = text[:500]  # Limit text length
        p.font.size = Pt(44) if is_title else Pt(18)
        p.font.bold = is_title
        p.alignment = PP_ALIGN.LEFT
        
        # Split long text into multiple paragraphs
        if len(text) > 500:
            remaining = text[500:]
            for chunk in [remaining[i:i+200] for i in range(0, len(remaining), 200)]:
                p = text_frame.add_paragraph()
                p.text = chunk
                p.font.size = Pt(18)
                p.alignment = PP_ALIGN.LEFT
    
    @staticmethod
    def get_available_formats(document_type: str) -> list:
        """Get available download formats for a document type"""
        formats = []
        
        if PDF_AVAILABLE:
            formats.append(('pdf', 'PDF'))
        
        if DOCX_AVAILABLE:
            formats.append(('docx', 'Word (DOCX)'))
        
        # PPTX only for presentations
        if document_type == 'presentation' and PPTX_AVAILABLE:
            formats.append(('pptx', 'PowerPoint (PPTX)'))
        
        return formats

