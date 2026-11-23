"""AI Data Analyst: questions answered from the company's own database (plan: MDS/01-Plan/week-45).

What is stored here, and what never is:
  * a source: how to reach the company's database (its password encrypted), or where its uploaded SQLite file is
    kept, and the list of its tables and columns (names, types, keys: never a value). For MongoDB (6 Nov 2026): its
    collections and the fields a sample of each showed, with their types;
  * each question: who asked, the answer, the SQL that ran, the result's column names and row count.
Never a row of the company's data: a result is shown once and run again when it is opened later (decided 3 Nov 2026).
"""
import uuid

from django.db import models

from core.crypto_utils import decrypt_secret, encrypt_secret


class DataSource(models.Model):
    KIND_POSTGRES = 'postgres'
    KIND_MYSQL = 'mysql'
    KIND_SQLITE = 'sqlite'
    KIND_MONGO = 'mongodb'
    KIND_MSSQL = 'mssql'
    KIND_CHOICES = [
        (KIND_POSTGRES, 'PostgreSQL'),
        (KIND_MYSQL, 'MySQL / MariaDB'),
        (KIND_MSSQL, 'Microsoft SQL Server'),
        (KIND_MONGO, 'MongoDB'),
        (KIND_SQLITE, 'SQLite file'),
    ]
    CONNECTION_KINDS = (KIND_POSTGRES, KIND_MYSQL, KIND_MSSQL, KIND_MONGO)

    STATUS_NEW = 'new'
    STATUS_LOADING = 'loading'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_NEW, 'Not tested yet'), (STATUS_LOADING, 'Loading the dump'), (STATUS_READY, 'Ready'),
                      (STATUS_FAILED, 'Could not connect')]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='data_sources')
    created_by = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='data_sources_created')
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)

    # A connection
    host = models.CharField(max_length=255, blank=True, default='')
    port = models.PositiveIntegerField(null=True, blank=True)
    database = models.CharField(max_length=255, blank=True, default='')
    username = models.CharField(max_length=255, blank=True, default='')
    password_encrypted = models.TextField(blank=True, default='')
    use_ssl = models.BooleanField(default=True)
    #: MongoDB: a mongodb+srv:// name, whose service record names the servers (MongoDB Atlas).
    use_srv = models.BooleanField(default=False)
    #: MongoDB: the connection options kept from its string (authSource, authMechanism, replicaSet), nothing else.
    #: SQL Server: {"trust_server_certificate": true} when its string says TrustServerCertificate=yes.
    options = models.JSONField(default=dict, blank=True)

    # An uploaded SQLite file: kept under LOCAL_STORAGE_ROOT/data_analyst, never served, deleted with the source. An
    # uploaded .sql dump is kept there only until it has been read into a SQLite copy (dumps.py), then deleted.
    file_path = models.CharField(max_length=500, blank=True, default='')
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_size = models.BigIntegerField(null=True, blank=True)
    #: A .sql dump read into the SQLite copy (7 Nov 2026): its dialect and name, the tables and rows read, the statements
    #: skipped, the problems met, and the keys the dump added by ALTER TABLE. Never a value of the data.
    load_report = models.JSONField(default=dict, blank=True)

    #: Whether the AI sees the first rows of a result to write its answer. Off: it writes only the SQL, and the
    #: answer is the table itself.
    send_rows_to_ai = models.BooleanField(default=True)
    #: Who may ask it: every dashboard login of the company, or only the ones listed (owners and admins always).
    everyone_may_ask = models.BooleanField(default=True)
    allowed_users = models.ManyToManyField('core.CompanyUser', blank=True, related_name='data_sources_allowed')
    #: What the company's data means, in its own words (22 Nov 2026): "revenue is invoices.total_usd of paid
    #: invoices", "an active customer ordered in the last 90 days". The agent reads it before it picks tables and
    #: writes a query. Most of the misses on the Meridian and Lumora test databases were meanings like these that the
    #: AI had to guess. Owners and admins write it; everyone who may ask sees it.
    company_notes = models.TextField(blank=True, default='')

    #: Tables and columns only: [{"name", "schema", "columns": [{"name", "type", "nullable", "pk"}], "fks": [...]}]
    tables = models.JSONField(default=list, blank=True)
    tables_read_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_NEW)
    last_error = models.TextField(blank=True, default='')
    last_checked_at = models.DateTimeField(null=True, blank=True)
    #: Whether the database user can write, as far as the test could tell (shown as a warning).
    user_can_write = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return f'{self.name} ({self.get_kind_display()})'

    def set_password(self, plaintext: str):
        self.password_encrypted = encrypt_secret(plaintext or '')

    def get_password(self) -> str:
        return decrypt_secret(self.password_encrypted)

    @property
    def is_connection(self) -> bool:
        return self.kind in self.CONNECTION_KINDS

    def may_ask(self, company_user) -> bool:
        from api.permissions import IsCompanyAdmin
        if company_user is None or company_user.company_id != self.company_id:
            return False
        if self.everyone_may_ask or getattr(company_user, 'role', None) in IsCompanyAdmin.ADMIN_ROLES:
            return True
        return self.allowed_users.filter(pk=company_user.pk).exists()


class DataQuestion(models.Model):
    STATUS_ANSWERED = 'answered'
    STATUS_FAILED = 'failed'
    STATUS_ASKED_BACK = 'asked_back'
    STATUS_CHOICES = [(STATUS_ANSWERED, 'Answered'), (STATUS_FAILED, 'Failed'), (STATUS_ASKED_BACK, 'Asked back')]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='data_questions')
    #: Removing a source removes its questions too (decided 3 Nov 2026: we keep none of a removed database).
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='questions')
    asked_by = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='data_questions')
    conversation = models.UUIDField(default=uuid.uuid4, db_index=True)

    question = models.TextField()
    answer = models.TextField(blank=True, default='')
    sql = models.TextField(blank=True, default='')
    #: The result's column names and size. Never its rows.
    columns = models.JSONField(default=list, blank=True)
    row_count = models.IntegerField(null=True, blank=True)
    truncated = models.BooleanField(default=False)
    #: Numbers in the answer not found in the rows the AI saw (shown under the answer).
    flagged = models.JSONField(default=list, blank=True)
    #: The chart the question asked for (14 Nov 2026): {"type": bar|line|pie, "x": label column, "y": number column,
    #: "title"}. Only its description: the screen draws it from the result's rows, which are never kept.
    chart = models.JSONField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ANSWERED)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    #: When its asker deleted the chat it is in (14 Nov 2026): gone from their chats and their history, kept in the
    #: company's History for owners and admins, so it stays a full record of what was asked.
    hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.question[:60]


class SavedQuestion(models.Model):
    """A question kept to run again: on a schedule, emailed to the people chosen, or only when a figure crosses a line
    (22 Nov 2026). It keeps the query that answered it and runs that again, read-only and without the AI, so the
    figures come the same way each time and a run costs nothing. The person checked the answer when they saved it."""

    SCHEDULE_OFF, SCHEDULE_DAILY, SCHEDULE_WEEKLY, SCHEDULE_MONTHLY = 'off', 'daily', 'weekly', 'monthly'
    SCHEDULE_CHOICES = [(SCHEDULE_OFF, 'Not scheduled'), (SCHEDULE_DAILY, 'Every day'),
                        (SCHEDULE_WEEKLY, 'Every week'), (SCHEDULE_MONTHLY, 'Every month')]
    ALERT_CHOICES = [('', 'Always send'), ('above', 'Only when above'), ('below', 'Only when below')]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='saved_data_questions')
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='saved_questions')
    created_by = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='saved_data_questions')
    title = models.CharField(max_length=120)
    question = models.TextField()
    sql = models.TextField()
    columns = models.JSONField(default=list, blank=True)

    schedule = models.CharField(max_length=10, choices=SCHEDULE_CHOICES, default=SCHEDULE_OFF)
    #: Monday is 0 (weekly); the day of the month, 1 to 28 (monthly); the hour on the company's clock.
    weekday = models.PositiveSmallIntegerField(default=0)
    month_day = models.PositiveSmallIntegerField(default=1)
    hour = models.PositiveSmallIntegerField(default=9)
    recipients = models.ManyToManyField('core.CompanyUser', blank=True, related_name='data_reports')
    #: "Only when": the first row's `alert_column` above or below `alert_value`; blank op sends every time.
    alert_column = models.CharField(max_length=120, blank=True, default='')
    alert_op = models.CharField(max_length=5, choices=ALERT_CHOICES, blank=True, default='')
    alert_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    #: 'sent' (emailed), 'quiet' (ran; the figure didn't cross the line), 'failed' (the query didn't run).
    last_status = models.CharField(max_length=10, blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    last_value = models.CharField(max_length=60, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'id']

    def __str__(self):
        return self.title
