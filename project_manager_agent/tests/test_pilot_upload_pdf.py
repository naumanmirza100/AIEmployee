"""A PDF uploaded to Project Pilot is read.

The upload is saved to disk and read again in a background job, through a
small wrapper that stands in for the uploaded file. The wrapper could only
seek from the start of the file. The PDF reader seeks from the end and asks
where it is, so every PDF failed with "Failed to extract text from file",
while text files, which need neither, worked.
"""
import io
import os
import tempfile
from unittest import skipUnless

from django.test import SimpleTestCase

from api.views import pm_agent
from project_manager_agent.tasks import _DiskFileWrapper


def a_pdf_saying(text):
    """The smallest PDF that holds one line of text."""
    stream = f'BT /F1 18 Tf 72 720 Td ({text}) Tj ET'.encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out, offsets = bytearray(b'%PDF-1.4\n'), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
    table = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    for offset in offsets:
        out += b'%010d 00000 n \n' % offset
    out += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, table)
    return bytes(out)


class UploadedPdfTests(SimpleTestCase):

    def on_disk(self, name, content):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, name)
        with open(path, 'wb') as handle:
            handle.write(content)
        self.addCleanup(lambda: (os.remove(path), os.rmdir(folder)))
        return path

    def read_as_the_job_does(self, name, content):
        path = self.on_disk(name, content)
        with open(path, 'rb') as handle:
            return pm_agent._extract_text_from_file(_DiskFileWrapper(handle, name, os.path.getsize(path)))

    @skipUnless(pm_agent.PDF_AVAILABLE, 'PyPDF2 is not installed')
    def test_the_job_reads_a_pdf(self):
        text = self.read_as_the_job_does('brief.pdf', a_pdf_saying('Ordering app for Zaiqa Foods'))
        self.assertIn('Ordering app for Zaiqa Foods', text)

    def test_the_job_still_reads_a_text_file(self):
        self.assertEqual(self.read_as_the_job_does('plan.txt', b'Build the checkout page'), 'Build the checkout page')

    def test_the_wrapper_moves_like_a_file(self):
        wrapper = _DiskFileWrapper(io.BytesIO(b'0123456789'), 'x.pdf', 10)
        wrapper.seek(-3, os.SEEK_END)
        self.assertEqual((wrapper.tell(), wrapper.read()), (7, b'789'))
        wrapper.seek(2)
        self.assertEqual(wrapper.read(3), b'234')

    @skipUnless(pm_agent.PDF_AVAILABLE, 'PyPDF2 is not installed')
    def test_a_file_that_only_claims_to_be_a_pdf_is_still_refused(self):
        with self.assertRaisesMessage(ValueError, 'does not match .pdf format'):
            self.read_as_the_job_does('brief.pdf', b'just some words')
