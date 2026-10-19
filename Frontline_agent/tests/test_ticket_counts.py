"""The top cards and the analytics count the tickets the list shows.

The list shows the tickets a login raised or was given; the cards and the
analytics counted only the ones it raised. A support lead given every ticket
saw a full list under cards that read 0.
"""
from api.views import frontline_agent as views

from .base import FrontlineTestCase


class TicketCountsTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.given = self.make_ticket(title='Given to Mo', assigned_to=self.member_user, status='open')
        self.rival_given = self.make_ticket(title='Rival, given to Mo', company=self.rival,
                                            created_by=self.rival_user, assigned_to=self.member_user)

    def stats(self, actor):
        code, body = self.call(views.frontline_dashboard, actor, method='get')
        self.assertEqual(code, 200, body)
        return body['data']['stats'], {t['title'] for t in body['data']['recent_tickets']}

    def listed(self, actor):
        code, body = self.call(views.list_tickets, actor, method='get')
        self.assertEqual(code, 200, body)
        rows = body['data'] if isinstance(body['data'], list) else body['data'].get('tickets', body['data'].get('results', []))
        return {row['title'] for row in rows}

    def test_a_ticket_given_to_someone_counts_on_their_cards(self):
        stats, recent = self.stats(self.member)
        self.assertEqual((stats['total_tickets'], stats['open_tickets']), (1, 1))
        self.assertEqual(recent, {'Given to Mo'})
        self.assertEqual(recent, self.listed(self.member))

    def test_and_in_their_analytics(self):
        data = views._compute_frontline_analytics_data(self.member)
        self.assertEqual(sum(data['tickets_by_status_obj'].values()), 1)

    def test_the_one_who_raised_it_still_counts_it(self):
        stats, recent = self.stats(self.admin)
        self.assertEqual(stats['total_tickets'], 2)
        self.assertEqual(recent, {'Printer on fire', 'Given to Mo'})
