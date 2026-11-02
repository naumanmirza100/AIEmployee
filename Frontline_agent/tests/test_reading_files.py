"""Web pages and scanned PDFs are read as their words (2 Nov 2026).

The server had neither BeautifulSoup nor the OCR tools: an uploaded web page was stored tags, styles and scripts
and all, and a scanned PDF was stored as nothing, though the documents page and the manual offer both. The
libraries are in requirements.txt now, and Tesseract and Poppler in the Dockerfile. The OCR test runs where
Tesseract is installed: in the image, which is where the tests run before a deploy.
"""
import shutil
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

from Frontline_agent.document_processor import DocumentProcessor

ROOT = Path(__file__).resolve().parents[2]


class ReadingFilesTests(SimpleTestCase):

    def write(self, name, data):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        path = folder / name
        path.write_bytes(data)
        return str(path)

    def test_a_web_page_is_read_without_its_tags_styles_and_scripts(self):
        path = self.write('hours.html', b'<!DOCTYPE html><html><head><style>h1{color:red}</style>'
                                        b'<script>alert("x")</script></head><body><h1>Support hours</h1>'
                                        b'<p>We answer from 9 to 6, Monday to Friday.</p></body></html>')
        ok, text, error = DocumentProcessor.extract_text(path, 'html')
        self.assertTrue(ok, error)
        self.assertIn('Support hours', text)
        self.assertIn('We answer from 9 to 6', text)
        for leftover in ('<h1>', 'alert', 'color:red'):
            self.assertNotIn(leftover, text)

    def test_the_server_installs_what_reading_needs(self):
        requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
        for package in ('beautifulsoup4', 'pdf2image', 'pytesseract'):
            self.assertIn(package, requirements)
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        for package in ('tesseract-ocr', 'poppler-utils'):
            self.assertIn(package, dockerfile)

    @skipUnless(shutil.which('tesseract') and shutil.which('pdftoppm'), 'Tesseract and Poppler are in the image only')
    def test_a_scanned_pdf_is_read_by_ocr(self):
        from PIL import Image, ImageDraw, ImageFont
        page = Image.new('RGB', (1700, 2200), 'white')
        draw = ImageDraw.Draw(page)
        font = ImageFont.load_default(size=56)
        for i, line in enumerate(('Booking reminders stopped on Friday.', 'Patients get no SMS or email.',
                                  'Please call the clinic before noon.')):
            draw.text((120, 200 + i * 110), line, fill='black', font=font)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        path = folder / 'scan.pdf'
        page.save(path, 'PDF', resolution=200)
        ok, text, error = DocumentProcessor.extract_text(str(path), 'pdf')
        self.assertTrue(ok, error)
        self.assertIn('reminders', text.lower())
        self.assertIn('clinic', text.lower())
