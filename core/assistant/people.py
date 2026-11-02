"""The people of one company, as the Company Assistant finds them by name.

A person can be up to three rows: a dashboard login (`CompanyUser`), an employee login (`auth.User`, from the Users
page) and an HR record (`hr_agent.Employee`). The agents each know them by a different one: PM assigns tasks to the
employee login, the shared calendar books the employee login, HR keeps leave on the HR record, Frontline gives
tickets to the login's own user. One `Person` joins them, by the links between them and by email address, so a
question about "Sara" reaches every agent's rows for her.

`find` never guesses: two people who match equally well both come back, and the assistant asks which one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ME_WORDS = {'me', 'i', 'my', 'myself', 'mine', 'mera', 'meri', 'mujhe', 'main'}


@dataclass
class Person:
    key: str
    name: str
    email: str = ''
    #: auth.User ids this person acts as (tasks, calendar, tickets).
    user_ids: set = field(default_factory=set)
    company_user: object = None
    employee: object = None
    title: str = ''
    department: str = ''
    manager: str = ''
    role: str = ''

    def describe(self) -> str:
        """'Sara Malik (Designer, Product)': enough to tell two Saras apart."""
        extra = ', '.join(p for p in (self.title or self.role, self.department) if p)
        return f'{self.name} ({extra})' if extra else (f'{self.name} <{self.email}>' if self.email else self.name)

    def facts(self) -> dict:
        out = {'name': self.name}
        for key in ('title', 'department', 'manager', 'email'):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.role:
            out['dashboard_login_role'] = self.role
        return out


def _norm(text) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s@.-]', ' ', str(text or '').lower())).strip()


class Directory:
    """Everyone in `company`, built once per question."""

    def __init__(self, company, *, with_hr=True):
        self.company = company
        self.people: list[Person] = []
        self._by_email: dict[str, Person] = {}
        self._by_user: dict[int, Person] = {}
        self._by_login: dict[int, Person] = {}
        if with_hr:
            self._add_hr_records()
        self._add_logins()
        self._add_members()

    # ---- building ------------------------------------------------------------------------------------------

    def _join(self, *, email='', user_id=None, login_id=None) -> Person | None:
        if login_id and login_id in self._by_login:
            return self._by_login[login_id]
        if user_id and user_id in self._by_user:
            return self._by_user[user_id]
        email = (email or '').strip().lower()
        return self._by_email.get(email) if email else None

    def _index(self, person: Person):
        if person.email:
            self._by_email.setdefault(person.email.lower(), person)
        for uid in person.user_ids:
            self._by_user.setdefault(uid, person)
        if person.company_user is not None:
            self._by_login[person.company_user.pk] = person

    def _add_hr_records(self):
        try:
            from hr_agent.models import Employee
        except ImportError:  # pragma: no cover
            return
        rows = (Employee.objects.filter(company=self.company, anonymized_at__isnull=True)
                .exclude(employment_status__in=('terminated', 'offboarded'))
                .select_related('manager', 'department_obj'))
        for e in rows:
            person = Person(key=f'emp:{e.pk}', name=e.full_name.strip() or e.work_email, email=e.work_email or '',
                            employee=e, title=e.job_title or '',
                            department=(getattr(e.department_obj, 'name', '') or e.department or ''),
                            manager=e.manager.full_name if e.manager_id else '')
            if e.user_id:
                person.user_ids.add(e.user_id)
            self.people.append(person)
            self._index(person)

    def _add_logins(self):
        from core.models import CompanyUser
        from core.scheduling.identity import login_user_id_for_company_user
        for cu in CompanyUser.objects.filter(company=self.company, is_active=True):
            employee_link = None
            if self.people:
                employee_link = next((p for p in self.people
                                      if p.employee is not None and p.employee.company_user_id == cu.pk), None)
            person = employee_link or self._join(email=cu.email, login_id=cu.pk)
            if person is None:
                person = Person(key=f'cu:{cu.pk}', name=(cu.full_name or cu.email).strip(), email=cu.email or '')
                self.people.append(person)
            person.company_user = cu
            person.role = cu.get_role_display()
            for uid in (cu.login_user_id, login_user_id_for_company_user(cu)):
                if uid:
                    person.user_ids.add(uid)
            self._index(person)

    def _add_members(self):
        from core.tenancy import members_of
        for user in members_of(self.company):
            person = self._join(email=user.email, user_id=user.pk)
            if person is None:
                name = (user.get_full_name() or user.username).strip()
                person = Person(key=f'user:{user.pk}', name=name, email=user.email or '')
                self.people.append(person)
            person.user_ids.add(user.pk)
            self._index(person)

    # ---- finding -----------------------------------------------------------------------------------------

    def me(self, company_user) -> Person | None:
        return self._by_login.get(company_user.pk)

    def find(self, name, *, asker=None) -> list[Person]:
        """Everyone `name` may mean, best matches only. 'me' is the asker."""
        query = _norm(name)
        if not query:
            return []
        if query in ME_WORDS and asker is not None:
            mine = self.me(asker)
            return [mine] if mine else []
        exact = [p for p in self.people if _norm(p.name) == query or (p.email and p.email.lower() == query)]
        if exact:
            return exact
        words = query.split()
        starts = [p for p in self.people
                  if all(any(part.startswith(w) for part in _norm(p.name).split()) for w in words)]
        if starts:
            return starts
        return [p for p in self.people
                if query in _norm(p.name) or (p.email and query in p.email.lower().split('@')[0])]

    def by_user_id(self, user_id) -> Person | None:
        return self._by_user.get(user_id)

    def by_employee_id(self, employee_id) -> Person | None:
        return next((p for p in self.people if p.employee is not None and p.employee.pk == employee_id), None)
