"""One tenant must never reach another's data (FL-SEC-1, -2, -4, -15, FL-GAP-2)."""
from api.views import frontline_agent as views
from Frontline_agent.models import (
    FrontlineWorkflow, KBFeedback, NotificationTemplate, Ticket, TicketLink,
)

from .base import FrontlineTestCase


class WorkflowStepScopeTests(FrontlineTestCase):
    """The step executor takes ids from caller-supplied execution context."""

    def run_step(self, step, context, workflow=None):
        workflow = workflow or FrontlineWorkflow.objects.create(
            company=self.company, name='wf', steps=[step], is_active=True)
        return views._run_single_step(step, 0, '0', workflow, context, False)

    def test_update_ticket_step_cannot_touch_another_company(self):
        """FL-SEC-1."""
        ok, result, _ = self.run_step(
            {'type': 'update_ticket', 'status': 'closed', 'resolution': 'owned'},
            {'ticket_id': self.rival_ticket.id})
        self.assertFalse(ok)
        self.assertEqual(result.get('error'), 'Ticket not found')
        self.rival_ticket.refresh_from_db()
        self.assertNotEqual(self.rival_ticket.status, 'closed')
        self.assertNotEqual(self.rival_ticket.resolution or '', 'owned')

    def test_update_ticket_step_works_on_own_company(self):
        ok, result, _ = self.run_step(
            {'type': 'update_ticket', 'status': 'open'},
            {'ticket_id': self.ticket.id})
        self.assertTrue(ok, result)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')

    def test_send_email_step_cannot_read_another_companys_template(self):
        """FL-SEC-2."""
        theirs = NotificationTemplate.objects.create(
            company=self.rival, name='Theirs', subject='Secret subject',
            body='Secret body', channel='email')
        ok, result, _ = self.run_step(
            {'type': 'send_email', 'template_id': theirs.id,
             'recipient_email': 'attacker@evil.test'},
            {})
        self.assertFalse(ok)
        self.assertEqual(result.get('error'), 'Template not found')


class CreatorScopedEndpointTests(FrontlineTestCase):
    """Endpoints that used to filter on the creator only (FL-SEC-4)."""

    def setUp(self):
        super().setUp()
        # A rival ticket that shares our creator, which is what the shadow-user
        # collision used to produce.
        self.shared_creator_ticket = self.make_ticket(
            title='Rival ticket, our creator', company=self.rival,
            created_by=self.admin_user, category='knowledge_gap',
            assigned_to=self.admin_user)

    def test_ticket_tasks_list_is_company_scoped(self):
        code, body = self.call(views.list_ticket_tasks, self.admin, method='get')
        self.assertEqual(code, 200, body)
        titles = {row['title'] for row in body['data']}
        self.assertNotIn('Rival ticket, our creator', titles)

    def test_aging_list_is_company_scoped(self):
        Ticket.objects.filter(pk=self.shared_creator_ticket.pk).update(
            sla_due_at=self.now())
        code, body = self.call(views.list_tickets_aging, self.admin, method='get')
        self.assertEqual(code, 200, body)
        ids = {row['id'] for row in body['data']['breached'] + body['data']['at_risk']}
        self.assertNotIn(self.shared_creator_ticket.id, ids)

    def test_dashboard_counts_are_company_scoped(self):
        code, body = self.call(views.frontline_dashboard, self.admin, method='get')
        self.assertEqual(code, 200, body)
        titles = {t['title'] for t in body['data'].get('recent_tickets', [])}
        self.assertNotIn('Rival ticket, our creator', titles)

    def test_update_ticket_task_cannot_reach_another_company(self):
        code, _ = self.call(views.update_ticket_task, self.admin, {'status': 'resolved'},
                            method='patch', ticket_id=self.shared_creator_ticket.id)
        self.assertEqual(code, 404)
        self.shared_creator_ticket.refresh_from_db()
        self.assertNotEqual(self.shared_creator_ticket.status, 'resolved')

    def test_analytics_is_company_scoped(self):
        data = views._compute_frontline_analytics_data(self.admin)
        counted = sum(data['tickets_by_status_obj'].values())
        ours = Ticket.objects.filter(company=self.company, created_by=self.admin_user).count()
        self.assertEqual(counted, ours)
        # The rival ticket that shares our creator must not be in there.
        self.assertLess(counted, Ticket.objects.filter(created_by=self.admin_user).count())


class TicketLinkScopeTests(FrontlineTestCase):
    """FL-SEC-15 — the far side of a link must be ours too."""

    def test_link_to_another_companys_ticket_is_not_returned(self):
        TicketLink.objects.create(
            from_ticket=self.ticket, to_ticket=self.rival_ticket, relation='related')
        code, body = self.call(views.list_ticket_links, self.admin, method='get',
                               ticket_id=self.ticket.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data'], [])


class KBCoverageScopeTests(FrontlineTestCase):
    """FL-GAP-2 — the thumbs-down half of the report was silently always zero,
    and the obvious fix would have aggregated every tenant's feedback."""

    def test_thumbs_down_counts_only_this_company(self):
        KBFeedback.objects.create(company_user=self.admin, question='how do i export',
                                  helpful=False)
        KBFeedback.objects.create(company_user=self.rival_admin, question='how do i export',
                                  helpful=False)
        code, body = self.call(views.kb_coverage_report, self.admin, method='get')
        self.assertEqual(code, 200, body)
        # Counted at all — it used to raise FieldError and be swallowed, so
        # this half of the report was always zero.
        self.assertEqual(body['data']['total_thumbs_down'], 1, body['data'])
        rows = {r['question']: r for r in body['data']['items']}
        self.assertEqual(rows['how do i export']['thumbs_down_count'], 1)
