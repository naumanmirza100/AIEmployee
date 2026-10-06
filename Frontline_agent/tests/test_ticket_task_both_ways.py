"""A ticket and its project task keep each other informed.

The link worked one way: the ticket heard when the task was done. Closing,
reopening or raising the urgency of the ticket told the task's assignee
nothing, and deleting the task (or its whole project) silently removed the
link from the ticket, with no note and no alert.
"""
from core.models import Notification, Project, Task, TaskComment
from Frontline_agent.models import Ticket, TicketNote
from project_manager_agent.models import PMNotification

from . import test_ticket_tasks as base       # the module, so its own tests are not collected here too


class BothWaysTests(base.TicketToTaskTests):
    locals().update({name: None for name in dir(base.TicketToTaskTests) if name.startswith('test_')})

    def setUp(self):
        super().setUp()
        self.ticket.priority = 'medium'
        self.ticket.status = 'open'
        self.ticket.save()
        self.task = Task.objects.get(pk=self.create()[1]['data']['id'])
        self.ticket.refresh_from_db()
        Notification.objects.all().delete()
        PMNotification.objects.all().delete()

    def change(self, **fields):
        ticket = Ticket.objects.get(pk=self.ticket.pk)        # a fresh copy, as a view would load it
        for name, value in fields.items():
            setattr(ticket, name, value)
        ticket.save()

    def comments(self):
        return list(TaskComment.objects.filter(task=self.task).order_by('id').values_list('comment_text', flat=True))

    def told(self):
        return list(Notification.objects.filter(user=self.dev).order_by('id').values_list('message', flat=True))

    # ---- the ticket tells the task --------------------------------------------

    def test_closing_the_ticket_is_written_on_the_task_and_its_assignee_is_told(self):
        self.change(status='resolved')
        expected = f'Frontline ticket #{self.ticket.id} was resolved. Check whether this task is still needed.'
        self.assertEqual(self.comments(), [expected])
        self.assertEqual(self.told(), [expected])
        note = Notification.objects.get(user=self.dev)
        self.assertEqual((note.action_url, note.title), ('/me/tasks', f'News on your task: {self.task.title}'))

    def test_reopening_it_is_too(self):
        self.change(status='closed')
        self.change(status='open')
        self.assertEqual(len(self.comments()), 2)
        self.assertIn('was reopened', self.comments()[1])

    def test_so_is_making_it_urgent(self):
        self.change(priority='urgent')
        self.assertEqual(self.comments(), [f'Frontline ticket #{self.ticket.id} is now urgent.'])

    def test_saving_the_ticket_without_such_a_change_says_nothing(self):
        self.change(title='Export is broken (again)')
        self.change(status='in_progress')
        self.change(priority='high')
        self.change(status='resolved')
        self.change(status='closed')                          # resolved to closed: still closed
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(len(self.told()), 1)

    def test_nobody_is_alerted_about_a_task_that_is_already_done(self):
        Task.objects.filter(pk=self.task.pk).update(status='done')
        self.change(status='closed')
        self.assertEqual(len(self.comments()), 1)             # still written on the task
        self.assertEqual(self.told(), [])

    def test_a_ticket_with_no_task_says_nothing(self):
        other = Ticket.objects.create(title='Other', description='x', company=self.company,
                                      created_by=self.admin_user, status='open')
        other.status = 'closed'
        other.save()
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.told(), [])

    # ---- the task tells the ticket --------------------------------------------

    def test_deleting_the_task_leaves_a_note_and_tells_the_owner(self):
        self.task.delete()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.pm_task_id)
        note = TicketNote.objects.filter(ticket=self.ticket).order_by('-id').first()
        self.assertIn('was deleted', note.body)
        self.assertIn(self.task.title, note.body)
        [alert] = PMNotification.objects.filter(company_user=self.admin)
        self.assertEqual(alert.title, f'The task for ticket #{self.ticket.id} was deleted')

    def test_deleting_the_whole_project_does_the_same(self):
        Project.objects.filter(pk=self.project.pk).first().delete()
        self.assertTrue(TicketNote.objects.filter(ticket=self.ticket, body__contains='was deleted').exists())
        self.assertEqual(PMNotification.objects.filter(company_user=self.admin).count(), 1)

    def test_a_closed_ticket_keeps_the_note_but_alerts_nobody(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(status='closed')
        self.task.delete()
        self.assertTrue(TicketNote.objects.filter(ticket=self.ticket, body__contains='was deleted').exists())
        self.assertEqual(PMNotification.objects.filter(company_user=self.admin).count(), 0)

    def test_a_ticket_owned_by_nobody_real_tells_whoever_created_it(self):
        # The chat widget files tickets under a system account with no dashboard login.
        from django.contrib.auth import get_user_model
        bot = get_user_model().objects.create(username='frontline_handoff_bot')
        Ticket.objects.filter(pk=self.ticket.pk).update(assigned_to=bot, created_by=self.admin_user)
        self.task.delete()
        self.assertEqual(PMNotification.objects.filter(company_user=self.admin).count(), 1)

    def test_deleting_a_task_no_ticket_knows_about_does_nothing(self):
        other = Task.objects.create(project=self.project, title='Unrelated')
        before = TicketNote.objects.count()
        other.delete()
        self.assertEqual(TicketNote.objects.count(), before)
