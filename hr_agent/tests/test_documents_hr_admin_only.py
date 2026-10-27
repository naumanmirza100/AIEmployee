"""Only an HR admin uploads or deletes HR documents, and anyone else is told why.

Any dashboard login could upload a document (and choose who may read it) or delete any document, confidential ones
included (found 3 Oct 2026 while fixing CO-15; still true on 27 Oct). Refusals across HR said only "HR-admin role
required"; they now say who can, and how to become one.
"""
from django.core.files.uploadedfile import SimpleUploadedFile

from api.views import hr_agent as views
from hr_agent.models import HRDocument

from .base import HRTestCase


class DocumentsAreForHRAdminsTests(HRTestCase):

    def upload(self, actor):
        from rest_framework.test import force_authenticate
        request = self.factory.post('/', {'file': SimpleUploadedFile('policy.txt', b'Leave policy: 18 days a year.'),
                                          'confidentiality': 'hr_only'}, format='multipart')
        force_authenticate(request, user=actor)
        response = views.upload_hr_document(request)
        response.render()
        return response.status_code, response.data

    def test_a_member_cannot_upload_and_is_told_why(self):
        code, body = self.upload(self.member)
        self.assertEqual(code, 403)
        self.assertEqual(body['code'], 'hr_admin_only')
        self.assertIn('Only an HR admin can upload HR documents', body['message'])
        self.assertIn('Logins & roles', body['message'])
        self.assertFalse(HRDocument.objects.exists())

    def test_an_admin_can_upload(self):
        code, body = self.upload(self.admin)
        self.assertIn(code, (200, 201, 202), body)
        self.assertTrue(HRDocument.objects.filter(company=self.company).exists())

    def test_a_member_cannot_delete_a_confidential_document(self):
        doc = HRDocument.objects.create(company=self.company, title='Salaries', confidentiality='hr_only',
                                        document_type='payroll')
        code, body = self.call(views.delete_hr_document, self.member, method='post', document_id=doc.id)
        self.assertEqual(code, 403)
        self.assertIn('Only an HR admin can delete HR documents', body['message'])
        self.assertTrue(HRDocument.objects.filter(pk=doc.pk).exists())
        code, _ = self.call(views.delete_hr_document, self.admin, method='post', document_id=doc.id)
        self.assertEqual(code, 200)
        self.assertFalse(HRDocument.objects.filter(pk=doc.pk).exists())

    def test_other_hr_refusals_say_who_can(self):
        code, body = self.call(views.create_department, self.member, {'name': 'Design'})
        self.assertEqual(code, 403)
        self.assertIn("the company's owner, an admin, or a login with the HR admin role", body['message'])
