"""HR items from the test report's "Later" list and the decisions (24 Nov 2026).

- The reviews list was back to front: the person saw the manager's unreleased assessment, their manager only released
  reviews.
- HR 6 (decision D21): the approver sees who else in the team is off then.
- Final 4: a time sent without an offset is read in the meeting's zone, as the Executive agent reads it.
"""
from datetime import date, timedelta, timezone as dt_timezone
from unittest import mock

from api.views import hr_agent as views
from hr_agent.models import Employee, HRMeeting, PerformanceReview, PerformanceReviewCycle

from .base import HRTestCase


class ReviewsTheRightWayRound(HRTestCase):

    def setUp(self):
        super().setUp()
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.admin_emp)
        self.una = self.login(self.company, 'una@test.local', 'Una Manager', 'manager')
        self.una_emp = self.employee(self.una, 'Una Manager')
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.una_emp)
        cycle = PerformanceReviewCycle.objects.create(company=self.company, name='H2', status='active',
                                                      period_start=date(2026, 7, 1), period_end=date(2026, 12, 31))
        self.review = PerformanceReview.objects.create(cycle=cycle, employee=self.member_emp, reviewer=self.una_emp,
                                                       manager_summary='Needs to speed up.', overall_rating=2)

    def reviews(self, actor):
        return self.call(views.list_employee_reviews, actor, method='get', employee_id=self.member_emp.id)

    def test_the_person_sees_their_review_but_not_the_unreleased_managers_part(self):
        code, body = self.reviews(self.member)
        self.assertEqual(code, 200, body)
        [row] = body['data']
        self.assertEqual((row['manager_summary'], row['overall_rating'], row['manager_part_hidden']), ('', None, True))
        PerformanceReview.objects.filter(pk=self.review.pk).update(visible_to_employee=True)
        [row] = self.reviews(self.member)[1]['data']
        self.assertEqual(row['manager_summary'], 'Needs to speed up.')

    def test_the_manager_sees_the_review_they_are_writing(self):
        [row] = self.reviews(self.una)[1]['data']
        self.assertEqual((row['manager_summary'], row['overall_rating']), ('Needs to speed up.', 2))

    def test_saving_the_self_review_does_not_hand_back_the_managers_part(self):
        code, body = self.call(views.update_perf_review, self.member, {'self_summary': 'A good half.'},
                               method='patch', review_id=self.review.id)
        self.assertEqual(code, 200, body)
        self.assertEqual((body['data']['self_summary'], body['data']['manager_summary']), ('A good half.', ''))


class WhoElseIsOff(HRTestCase):

    def test_the_approver_sees_the_others_in_the_team_off_then(self):
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.admin_emp)
        zara = self.employee(self.login(self.company, 'zara@test.local', 'Zara Z', 'company_user'), 'Zara Z')
        Employee.objects.filter(pk=zara.pk).update(manager=self.admin_emp)
        start = date.today() + timedelta(days=14)
        self.leave_request(self.member_emp, start_date=start, end_date=start + timedelta(days=1), approver=self.admin_emp)
        self.leave_request(zara, start_date=start + timedelta(days=1), end_date=start + timedelta(days=3),
                           status='approved')
        code, body = self.call(views.list_leave_requests, self.admin, method='get')
        self.assertEqual(code, 200, body)
        mine = next(r for r in body['data'] if r['employee_id'] == self.member_emp.id)
        self.assertEqual([o['employee_name'] for o in mine['others_off']], ['Zara Z'])
        self.assertNotIn('reason', mine['others_off'][0])


class ATimeWithoutAnOffset(HRTestCase):

    def test_it_is_read_in_the_meetings_zone(self):
        with mock.patch.object(views, 'ensure_free'), mock.patch.object(views, 'booking_guard'):
            code, body = self.call(views.create_hr_meeting, self.admin, {
                'title': 'Check-in', 'scheduled_at': '2026-12-02T15:15:00', 'timezone_name': 'Asia/Karachi'})
        self.assertIn(code, (200, 201), body)
        meeting = HRMeeting.objects.get(title='Check-in')
        self.assertEqual(meeting.scheduled_at.astimezone(dt_timezone.utc).strftime('%H:%M'), '10:15')
