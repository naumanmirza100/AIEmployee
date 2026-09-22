"""The things that must move together when a ticket changes
(FL-DATA-11, -12, -13, -14, -15)."""
from datetime import timedelta

from api.views import frontline_agent as views
from Frontline_agent.models import Ticket, TicketSatisfaction
from Frontline_agent.ticket_state import apply_status_change, resume_sla

from .base import FrontlineTestCase


class ResolvedAtTests(FrontlineTestCase):
    """FL-DATA-11 — it used to be stamped by one endpoint, and only when a
    resolution came with it."""

    def test_closing_from_the_grid_stamps_resolved_at(self):
        code, body = self.call(views.update_ticket, self.admin, {'status': 'closed'},
                               method='patch', ticket_id=self.ticket.id)
        self.assertEqual(code, 200, body)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.resolved_at)

    def test_bulk_close_stamps_resolved_at(self):
        code, body = self.call(views.bulk_update_tickets, self.admin,
                               {'ids': [self.ticket.id], 'status': 'resolved'})
        self.assertEqual(code, 200, body)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.resolved_at)

    def test_reopening_clears_resolved_at(self):
        apply_status_change(self.ticket, 'resolved')
        self.ticket.save()
        self.assertIsNotNone(self.ticket.resolved_at)
        changed = apply_status_change(self.ticket, 'open')
        self.assertIn('resolved_at', changed)
        self.assertIsNone(self.ticket.resolved_at)

    def test_unchanged_status_reports_no_changes(self):
        self.assertEqual(apply_status_change(self.ticket, self.ticket.status), [])


class HandoffLifecycleTests(FrontlineTestCase):
    """FL-DATA-15 — resolve_handoff existed but nothing called it."""

    def test_closing_a_ticket_releases_the_handoff(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            handoff_status='accepted', handoff_accepted_by=self.admin_user)
        self.ticket.refresh_from_db()
        code, body = self.call(views.update_ticket, self.admin, {'status': 'closed'},
                               method='patch', ticket_id=self.ticket.id)
        self.assertEqual(code, 200, body)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.handoff_status, 'resolved')

    def test_an_open_ticket_keeps_its_handoff(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(handoff_status='accepted')
        self.ticket.refresh_from_db()
        self.call(views.update_ticket, self.admin, {'priority': 'high'},
                  method='patch', ticket_id=self.ticket.id)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.handoff_status, 'accepted')


class SlaResumeTests(FrontlineTestCase):
    """FL-DATA-12 — one guarded resume, and the deadline moves with it."""

    def setUp(self):
        super().setUp()
        self.paused_at = self.now() - timedelta(hours=2)
        self.due_at = self.now() + timedelta(hours=1)
        Ticket.objects.filter(pk=self.ticket.pk).update(
            sla_paused_at=self.paused_at, sla_due_at=self.due_at,
            sla_paused_accumulated_seconds=0)
        self.ticket.refresh_from_db()

    def test_resume_credits_time_and_moves_the_deadline(self):
        credited = resume_sla(self.ticket)
        self.assertIsNotNone(credited)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.sla_paused_at)
        self.assertGreater(self.ticket.sla_paused_accumulated_seconds, 7000)  # ~2h
        self.assertGreater(self.ticket.sla_due_at, self.due_at)

    def test_a_second_resume_credits_nothing(self):
        first = resume_sla(self.ticket)
        self.ticket.refresh_from_db()
        after_first = (self.ticket.sla_paused_accumulated_seconds, self.ticket.sla_due_at)

        stale = Ticket.objects.get(pk=self.ticket.pk)
        stale.sla_paused_at = self.paused_at  # what a racing request still held
        self.assertIsNone(resume_sla(stale))

        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.sla_paused_accumulated_seconds, self.ticket.sla_due_at), after_first)
        self.assertIsNotNone(first)


class SnoozeWakeTests(FrontlineTestCase):
    """FL-DATA-13 — waking a ticket must restart its inactivity clock."""

    def test_waking_stamps_updated_at(self):
        from Frontline_agent.tasks import wake_snoozed_tickets
        long_ago = self.now() - timedelta(days=30)
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status='resolved', snoozed_until=self.now() - timedelta(minutes=1),
            updated_at=long_ago)

        wake_snoozed_tickets()

        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.snoozed_until)
        self.assertGreater(self.ticket.updated_at, long_ago)

    def test_a_woken_ticket_is_not_auto_closed_immediately(self):
        from Frontline_agent.tasks import auto_close_inactive_tickets, wake_snoozed_tickets
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status='resolved', snoozed_until=self.now() - timedelta(minutes=1),
            updated_at=self.now() - timedelta(days=30))

        wake_snoozed_tickets()
        auto_close_inactive_tickets()

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'resolved')


class SatisfactionSurveyTests(FrontlineTestCase):
    """FL-DATA-14 — surveys were created by one endpoint that most closes
    never touch."""

    def test_closing_a_ticket_creates_a_survey(self):
        code, body = self.call(views.update_ticket, self.admin, {'status': 'resolved'},
                               method='patch', ticket_id=self.ticket.id)
        self.assertEqual(code, 200, body)
        self.assertTrue(TicketSatisfaction.objects.filter(ticket=self.ticket).exists())

    def test_a_second_close_does_not_raise_or_duplicate(self):
        from Frontline_agent.satisfaction import ensure_satisfaction_survey
        first = ensure_satisfaction_survey(self.ticket)
        second = ensure_satisfaction_survey(self.ticket)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TicketSatisfaction.objects.filter(ticket=self.ticket).count(), 1)

    def test_an_unsent_survey_is_retried(self):
        from django.core import mail
        from Frontline_agent.satisfaction import ensure_satisfaction_survey
        survey = TicketSatisfaction.objects.create(ticket=self.ticket, token='tok-123')
        self.assertIsNone(survey.sent_at)

        mail.outbox = []
        ensure_satisfaction_survey(self.ticket)

        survey.refresh_from_db()
        self.assertIsNotNone(survey.sent_at)
        self.assertEqual(len(mail.outbox), 1)
