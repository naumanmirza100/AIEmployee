"""A person's own Google or Outlook calendar (core/personal_calendars.py, 24 Nov 2026).

Its busy times count in every agent's clash check; the agents' bookings go into it and follow the booking. Nothing
here reaches Google or Microsoft: a stand-in calendar plays the provider, and the two clients are fed recorded
answers.
"""
import base64
from datetime import datetime, time, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_integrations, personal_calendar as views
from core import personal_calendars as pc
from core.models import CalendarBlock, Company, CompanyUser, PersonalCalendar, PersonalCalendarEvent, UserProfile
from core.scheduling import ScheduleConflict, ensure_free
from core.scheduling.conflicts import find_conflicts

UTC = ZoneInfo('UTC')
GOOGLE = dict(GOOGLE_CLIENT_ID='gid', GOOGLE_CLIENT_SECRET='gsecret',
              GOOGLE_OAUTH_REDIRECT_URI='http://api.test/api/company/integrations/google-calendar/callback',
              MICROSOFT_CLIENT_ID='', MICROSOFT_CLIENT_SECRET='', MICROSOFT_OAUTH_REDIRECT_URI='')
BOTH = {**GOOGLE, 'MICROSOFT_CLIENT_ID': 'mid', 'MICROSOFT_CLIENT_SECRET': 'msecret',
        'MICROSOFT_OAUTH_REDIRECT_URI': 'http://api.test/api/me/calendar/microsoft/callback'}


class FakeCalendar:
    """The provider's side: some busy events of the person's own, plus whatever we write."""

    def __init__(self, busy=()):
        self.own, self.ours, self.calls, self.n = list(busy), {}, [], 0

    def busy(self, start, end):
        return self.own + [(eid, b['starts_at'], b['ends_at']) for eid, b in self.ours.items()]

    def create(self, booking):
        self.n += 1
        eid = f'ours-{self.n}'
        self.ours[eid] = booking
        self.calls.append(('create', eid))
        return eid

    def update(self, eid, booking):
        if eid not in self.ours:
            return False
        self.ours[eid] = booking
        self.calls.append(('update', eid))
        return True

    def delete(self, eid):
        self.ours.pop(eid, None)
        self.calls.append(('delete', eid))


@override_settings(**GOOGLE)
class CalendarTestCase(TestCase):
    factory = APIRequestFactory()

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.rae_login = CompanyUser.objects.create(company=self.company, email='rae@test.local', full_name='Rae Rep',
                                                    role='admin', password_hash='x', is_active=True)
        self.rae = self.employee('rae')
        self.dee_login = CompanyUser.objects.create(company=self.company, email='dee@test.local', full_name='Dee',
                                                    role='manager', password_hash='x', is_active=True)
        self.day = timezone.now().date() + timedelta(days=7)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)
        self.fake = FakeCalendar()
        patcher = mock.patch.object(pc, '_client', lambda cal: self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def employee(self, username):
        user = get_user_model().objects.create_user(username, email=f'{username}@test.local', password='x',
                                                    first_name=username.title())
        UserProfile.objects.update_or_create(user=user, defaults={'company': self.company, 'role': 'team_member'})
        return get_user_model().objects.get(pk=user.pk)

    def at(self, hour, minute=0, day=None):
        return datetime.combine(day or self.day, time(hour, minute), tzinfo=UTC)

    def call(self, view, who, method='get', data=None, path='/x'):
        request = getattr(self.factory, method)(path, data or {}, format='json')
        force_authenticate(request, user=who)
        response = view(request)
        return response.status_code, response.data

    def connected(self, user=None, provider='google'):
        user = user or self.rae
        return PersonalCalendar.objects.create(user=user, company=self.company, provider=provider,
                                               account_email='rae@gmail.example', refresh_token=pc._seal('r1'))

    def booking(self, user=None, source='pm', source_id=1, hour=14, title='Roadmap review', private=False,
                response='accepted'):
        return CalendarBlock.objects.create(company=self.company, user=user or self.rae, source=source,
                                            source_id=source_id, role='participant', response=response, title=title,
                                            starts_at=self.at(hour), ends_at=self.at(hour + 1), is_private=private)


class Connecting(CalendarTestCase):

    def test_a_dashboard_login_connects_its_employee_logins_calendar(self):
        code, body = self.call(views.company_my_calendar_connect, self.rae_login, 'post', {'provider': 'google'})
        self.assertEqual(code, 200, body)
        url = urlparse(body['data']['authUrl'])
        self.assertEqual(url.netloc, 'accounts.google.com')
        query = parse_qs(url.query)
        self.assertEqual(query['redirect_uri'], [GOOGLE['GOOGLE_OAUTH_REDIRECT_URI']])   # no new Google setup
        state = pc.read_state(query['state'][0])
        self.assertEqual((state['user_id'], state['company_id']), (self.rae.id, self.company.id))
        self.assertEqual(state['return_to'], '/company/profile/integrations')

        self.fake.own = [('dentist', self.at(11), self.at(12))]
        with mock.patch.object(pc, '_exchange', return_value=('refresh-1', 'access', 'rae@gmail.example')):
            request = self.factory.get('/cb', {'code': 'abc', 'state': query['state'][0]})
            response = company_integrations.google_calendar_callback(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/company/profile/integrations?mycal=connected', response['Location'])
        cal = PersonalCalendar.objects.get(user=self.rae)
        self.assertEqual((cal.provider, cal.account_email), ('google', 'rae@gmail.example'))
        self.assertNotIn('refresh-1', cal.refresh_token)                                   # sealed
        self.assertEqual(pc._token_of(cal), 'refresh-1')
        self.assertTrue(CalendarBlock.objects.filter(user=self.rae, source='personal').exists())   # synced at once

    def test_the_company_calendars_own_connect_is_untouched(self):
        signed = signing.dumps({'company_id': self.company.id, 'return_to': ''}, salt=company_integrations.STATE_SALT)
        state = base64.urlsafe_b64encode(signed.encode()).decode().rstrip('=')
        self.assertIsNone(pc.read_state(state))
        with mock.patch('requests.post') as post:
            post.return_value.status_code, post.return_value.json.return_value = 400, {'error': 'bad'}
            response = company_integrations.google_calendar_callback(self.factory.get('/cb', {'code': 'x', 'state': state}))
        self.assertIn('gcal_error=bad', response['Location'])
        self.assertFalse(PersonalCalendar.objects.exists())

    def test_a_login_that_is_nobodys_calendar_is_told_why(self):
        code, body = self.call(views.company_my_calendar, self.dee_login)
        self.assertEqual(code, 200)
        self.assertFalse(body['data']['linked'])
        self.assertIn('link your login to your employee record', body['data']['notLinkedReason'])
        code, body = self.call(views.company_my_calendar_connect, self.dee_login, 'post', {'provider': 'google'})
        self.assertEqual(code, 400)

    def test_outlook_is_offered_only_once_it_is_set_up(self):
        code, body = self.call(views.my_calendar_connect, self.rae, 'post', {'provider': 'microsoft'})
        self.assertEqual(code, 400)
        self.assertIn('not set up on this server', body['message'])
        with override_settings(**BOTH):
            code, body = self.call(views.my_calendar_connect, self.rae, 'post', {'provider': 'microsoft'})
            self.assertEqual(code, 200, body)
            url = urlparse(body['data']['authUrl'])
            self.assertEqual(url.netloc, 'login.microsoftonline.com')
            self.assertIn('Calendars.ReadWrite', parse_qs(url.query)['scope'][0])
            self.assertEqual(pc.read_state(parse_qs(url.query)['state'][0])['return_to'], '/me/meetings')
            with mock.patch.object(pc, '_exchange', return_value=('m-refresh', 'a', 'rae@outlook.example')):
                request = self.factory.get('/cb', {'code': 'c', 'state': parse_qs(url.query)['state'][0]})
                response = views.microsoft_callback(request)
            self.assertIn('/me/meetings?mycal=connected', response['Location'])
            self.assertEqual(PersonalCalendar.objects.get(user=self.rae).provider, 'microsoft')

    def test_a_state_for_google_is_not_taken_by_the_outlook_callback(self):
        state = pc.make_state(user_id=self.rae.id, company_id=self.company.id, provider='google', return_to='/me/meetings')
        response = views.microsoft_callback(self.factory.get('/cb', {'code': 'c', 'state': state}))
        self.assertIn('mycal_error=', response['Location'])
        self.assertFalse(PersonalCalendar.objects.exists())

    def test_connecting_another_account_takes_our_meetings_out_of_the_old_one(self):
        cal = self.connected()
        self.booking()
        pc.sync(cal)
        self.assertEqual(len(self.fake.ours), 1)
        state = pc.make_state(user_id=self.rae.id, company_id=self.company.id, provider='google', return_to='/me/meetings')
        with mock.patch.object(pc, '_exchange', return_value=('r2', 'a', 'other@gmail.example')):
            pc.finish_connect(pc.read_state(state), 'code')
        self.assertIn(('delete', 'ours-1'), self.fake.calls)
        self.assertEqual(PersonalCalendar.objects.get(user=self.rae).account_email, 'other@gmail.example')


class BusyTimes(CalendarTestCase):

    def test_own_busy_times_count_in_every_clash_check_without_their_titles(self):
        cal = self.connected()
        self.fake.own = [('dentist', self.at(11), self.at(12))]
        self.assertEqual(pc.sync(cal)['busy'], 1)
        block = CalendarBlock.objects.get(user=self.rae, source='personal')
        self.assertEqual((block.title, block.is_private), ('Busy', True))
        clashes = find_conflicts([self.rae.id], self.at(11, 30), self.at(12, 30), reveal_private=True,
                                 viewer_source='hr')
        self.assertEqual([c.source for c in clashes], ['personal'])
        self.assertIsNone(clashes[0].title)
        self.assertIn('(own calendar)', clashes[0].describe())
        with self.assertRaises(ScheduleConflict):
            ensure_free([self.rae.id], self.at(11), 30)
        ensure_free([self.rae.id], self.at(12), 30)                       # after it, free

    def test_each_sync_replaces_them_and_our_own_events_are_not_read_back(self):
        cal = self.connected()
        self.booking(hour=15)
        self.fake.own = [('a', self.at(9), self.at(10)), ('b', self.at(11), self.at(12))]
        pc.sync(cal)
        self.assertEqual(CalendarBlock.objects.filter(user=self.rae, source='personal').count(), 2)   # not 3
        self.fake.own = [('b', self.at(11), self.at(12))]
        pc.sync(cal)
        self.assertEqual(list(CalendarBlock.objects.filter(user=self.rae, source='personal')
                              .values_list('starts_at', flat=True)), [self.at(11)])

    def test_turned_off_they_go(self):
        cal = self.connected()
        self.fake.own = [('a', self.at(9), self.at(10))]
        pc.sync(cal)
        code, body = self.call(views.my_calendar, self.rae, 'patch', {'readBusy': False})
        self.assertEqual(code, 200, body)
        self.assertFalse(body['data']['readBusy'])
        self.assertFalse(CalendarBlock.objects.filter(source='personal').exists())

    def test_a_revoked_connection_clears_them_and_says_so(self):
        cal = self.connected()
        self.fake.own = [('a', self.at(9), self.at(10))]
        pc.sync(cal)
        self.fake.busy = mock.Mock(side_effect=pc._Revoked(pc.REVOKED.format(provider='Google Calendar')))
        self.assertEqual(pc.sync(cal), {'error': 'revoked'})
        cal.refresh_from_db()
        self.assertIn('Connect it again', cal.last_error)
        self.assertIsNone(cal.sync_started_at)
        self.assertFalse(CalendarBlock.objects.filter(source='personal').exists())

    def test_two_syncs_never_run_at_once(self):
        cal = self.connected()
        PersonalCalendar.objects.filter(pk=cal.pk).update(sync_started_at=timezone.now())
        self.assertEqual(pc.sync(cal), {'skipped': 'already syncing'})
        PersonalCalendar.objects.filter(pk=cal.pk).update(sync_started_at=timezone.now() - timedelta(minutes=30))
        self.assertNotIn('skipped', pc.sync(cal))                       # a dead one is taken over

    def test_they_are_not_listed_as_meetings_a_leave_or_holiday_lands_on(self):
        from api.views.hr_agent import _booked_on
        cal = self.connected()
        self.fake.own = [('a', self.at(9), self.at(10))]
        pc.sync(cal)
        self.booking(hour=14)
        self.assertEqual([b['source'] for b in _booked_on(self.company, self.day)], ['pm'])


class Bookings(CalendarTestCase):

    def test_the_agents_bookings_go_in_and_follow_the_booking(self):
        cal = self.connected()
        block = self.booking(title='Roadmap review')
        self.assertEqual(pc.sync(cal)['added'], 1)
        event = PersonalCalendarEvent.objects.get(calendar=cal)
        self.assertEqual((event.block_source, event.block_source_id), ('pm', 1))
        self.assertEqual(self.fake.ours[event.external_id]['title'], 'Roadmap review')
        pc.sync(cal)
        self.assertEqual([c[0] for c in self.fake.calls], ['create'])       # nothing changed: nothing written

        block.starts_at, block.ends_at = self.at(16), self.at(17)
        block.save()
        self.assertEqual(pc.sync(cal)['moved'], 1)
        self.assertEqual(self.fake.ours[event.external_id]['starts_at'], self.at(16))

        block.delete()                                                     # cancelled
        self.assertEqual(pc.sync(cal)['removed'], 1)
        self.assertEqual(self.fake.ours, {})
        self.assertFalse(PersonalCalendarEvent.objects.exists())

    def test_a_private_bookings_title_stays_here_and_an_invitation_says_so(self):
        cal = self.connected()
        self.booking(source='hr', title='Exit interview: Sana', private=True)
        self.booking(source='exec', source_id=2, hour=16, title='Board prep', response='pending')
        pc.sync(cal)
        titles = sorted(b['title'] for b in self.fake.ours.values())
        self.assertEqual(titles, ['HR meeting (details in PayPerProject)', 'Invited: Board prep'])

    def test_leave_and_ended_meetings_are_not_written(self):
        cal = self.connected()
        CalendarBlock.objects.create(company=self.company, user=self.rae, source='leave', source_id=5,
                                     starts_at=self.at(0), ends_at=self.at(23), response='on_leave')
        CalendarBlock.objects.create(company=self.company, user=self.rae, source='pm', source_id=6,
                                     starts_at=timezone.now() - timedelta(hours=3),
                                     ends_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(pc.sync(cal)['added'], 0)

    def test_a_deleted_event_of_a_moved_meeting_is_put_back(self):
        cal = self.connected()
        block = self.booking()
        pc.sync(cal)
        self.fake.ours.clear()                                             # the person deleted it there
        block.starts_at, block.ends_at = self.at(9), self.at(10)
        block.save()
        pc.sync(cal)
        self.assertEqual(len(self.fake.ours), 1)
        self.assertEqual(PersonalCalendarEvent.objects.get().external_id, list(self.fake.ours)[0])

    def test_disconnecting_takes_them_out_and_ends_the_busy_times(self):
        cal = self.connected()
        self.booking()
        self.fake.own = [('a', self.at(9), self.at(10))]
        pc.sync(cal)
        code, body = self.call(views.my_calendar, self.rae, 'delete')
        self.assertEqual(code, 200, body)
        self.assertFalse(body['data']['connected'])
        self.assertEqual(self.fake.ours, {})
        self.assertFalse(CalendarBlock.objects.filter(source='personal').exists())
        self.assertFalse(PersonalCalendar.objects.exists())
        self.assertTrue(CalendarBlock.objects.filter(source='pm').exists())       # the booking itself stays

    def test_the_card_counts_both_ways_and_sync_now_runs_it(self):
        cal = self.connected()
        self.booking()
        self.fake.own = [('a', self.at(9), self.at(10))]
        code, body = self.call(views.company_my_calendar_sync, self.rae_login, 'post')
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual((data['busyCount'], data['pushedCount'], data['providerLabel']), (1, 1, 'Google Calendar'))
        self.assertTrue(data['lastSyncedAt'])
        cal.refresh_from_db()
        self.assertEqual(cal.last_error, '')


class Response:
    def __init__(self, status_code, body):
        self.status_code, self.body = status_code, body

    def json(self):
        return self.body


class FakeHTTP:
    """Answers in turn, recording what was asked."""

    def __init__(self, token, pages):
        self.token, self.pages, self.asked = token, list(pages), []

    def post(self, url, data=None, timeout=None):
        self.asked.append(('POST', url, data))
        return Response(200, self.token)

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.asked.append((method, url, params, headers))
        return self.pages.pop(0)


def _when(text):
    return {'dateTime': text}


@override_settings(**BOTH)
class Providers(CalendarTestCase):
    """The two clients read the providers' answers as the providers write them."""

    def test_google_skips_free_cancelled_declined_and_our_own_and_reads_whole_days(self):
        cal = self.connected()
        items = [
            {'id': 'a', 'start': _when('2026-12-01T10:00:00+05:00'), 'end': _when('2026-12-01T11:00:00+05:00')},
            {'id': 'free', 'transparency': 'transparent', 'start': _when('2026-12-01T12:00:00Z'),
             'end': _when('2026-12-01T13:00:00Z')},
            {'id': 'gone', 'status': 'cancelled', 'start': _when('2026-12-01T12:00:00Z'), 'end': _when('2026-12-01T13:00:00Z')},
            {'id': 'no', 'attendees': [{'self': True, 'responseStatus': 'declined'}],
             'start': _when('2026-12-01T12:00:00Z'), 'end': _when('2026-12-01T13:00:00Z')},
            {'id': 'ours', 'extendedProperties': {'private': {pc.GOOGLE_MARK: 'pm:1'}},
             'start': _when('2026-12-01T12:00:00Z'), 'end': _when('2026-12-01T13:00:00Z')},
            {'id': 'day', 'start': {'date': '2026-12-02'}, 'end': {'date': '2026-12-03'}},
        ]
        client = pc._Google(cal)
        client.http = FakeHTTP({'access_token': 'acc'}, [Response(200, {'timeZone': 'Asia/Karachi', 'items': items})])
        got = client.busy(self.at(0), self.at(0) + timedelta(days=30))
        self.assertEqual(got, [
            ('a', datetime(2026, 12, 1, 5, 0, tzinfo=UTC), datetime(2026, 12, 1, 6, 0, tzinfo=UTC)),
            ('day', datetime(2026, 12, 1, 19, 0, tzinfo=UTC), datetime(2026, 12, 2, 19, 0, tzinfo=UTC)),
        ])
        self.assertEqual(client.http.asked[0][2]['grant_type'], 'refresh_token')
        self.assertEqual(client.http.asked[1][3]['Authorization'], 'Bearer acc')

    def test_outlook_reads_utc_pages_and_keeps_a_rolled_refresh_token(self):
        cal = self.connected(provider='microsoft')
        first = {'value': [
            {'id': 'm1', 'start': {'dateTime': '2026-12-01T05:00:00.0000000', 'timeZone': 'UTC'},
             'end': {'dateTime': '2026-12-01T06:00:00.0000000', 'timeZone': 'UTC'}, 'showAs': 'busy'},
            {'id': 'free', 'showAs': 'free', 'start': _when('2026-12-01T07:00:00'), 'end': _when('2026-12-01T08:00:00')},
            {'id': 'x', 'isCancelled': True, 'start': _when('2026-12-01T07:00:00'), 'end': _when('2026-12-01T08:00:00')},
            {'id': 'ours', 'transactionId': pc.MS_MARK + 'abc', 'start': _when('2026-12-01T07:00:00'),
             'end': _when('2026-12-01T08:00:00')},
            {'id': 'dec', 'responseStatus': {'response': 'declined'}, 'start': _when('2026-12-01T07:00:00'),
             'end': _when('2026-12-01T08:00:00')},
        ], '@odata.nextLink': 'https://graph.microsoft.com/v1.0/me/calendarView?$skip=100'}
        second = {'value': [{'id': 'm2', 'start': _when('2026-12-03T09:30:00.0000000'),
                             'end': _when('2026-12-03T10:00:00.0000000'), 'showAs': 'tentative'}]}
        client = pc._Microsoft(cal)
        client.http = FakeHTTP({'access_token': 'acc', 'refresh_token': 'r2'}, [Response(200, first), Response(200, second)])
        got = client.busy(self.at(0), self.at(0) + timedelta(days=30))
        self.assertEqual([g[0] for g in got], ['m1', 'm2'])
        self.assertEqual(got[0][1], datetime(2026, 12, 1, 5, 0, tzinfo=UTC))
        self.assertEqual(client.http.asked[1][3]['Prefer'], 'outlook.timezone="UTC"')
        self.assertIsNone(client.http.asked[2][2])                         # the next page's link carries its query
        cal.refresh_from_db()
        self.assertEqual(pc._token_of(cal), 'r2')

    def test_a_401_or_a_refused_refresh_is_a_revoked_connection(self):
        cal = self.connected()
        client = pc._Google(cal)
        client.http = FakeHTTP({'access_token': 'acc'}, [Response(401, {})])
        with self.assertRaises(pc._Revoked):
            client.busy(self.at(0), self.at(1))
        client = pc._Google(cal)
        client.http = FakeHTTP({'error': 'invalid_grant'}, [])
        client.http.post = lambda url, data=None, timeout=None: Response(400, {'error': 'invalid_grant'})
        with self.assertRaises(pc._Revoked):
            client.access()


class Schedule(TestCase):

    def test_it_runs_every_fifteen_minutes(self):
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['sync-personal-calendars']
        self.assertEqual((entry['task'], entry['schedule']), ('core.tasks.sync_personal_calendars', 900.0))
        from core.tasks import sync_personal_calendars
        self.assertEqual(sync_personal_calendars(), {'calendars': 0, 'failed': 0})
