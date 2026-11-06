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
    KIND_CHOICES = [
        (KIND_POSTGRES, 'PostgreSQL'),
        (KIND_MYSQL, 'MySQL / MariaDB'),
        (KIND_MONGO, 'MongoDB'),
        (KIND_SQLITE, 'SQLite file'),
    ]
    CONNECTION_KINDS = (KIND_POSTGRES, KIND_MYSQL, KIND_MONGO)

    STATUS_NEW = 'new'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [(STATUS_NEW, 'Not tested yet'), (STATUS_READY, 'Ready'), (STATUS_FAILED, 'Could not connect')]

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
    options = models.JSONField(default=dict, blank=True)

    # An uploaded SQLite file: kept under LOCAL_STORAGE_ROOT/data_analyst, never served, deleted with the source
    file_path = models.CharField(max_length=500, blank=True, default='')
    file_name = models.CharField(max_length=255, blank=True, default='')
    file_size = models.BigIntegerField(null=True, blank=True)

    #: Whether the AI sees the first rows of a result to write its answer. Off: it writes only the SQL, and the
    #: answer is the table itself.
    send_rows_to_ai = models.BooleanField(default=True)
    #: Who may ask it: every dashboard login of the company, or only the ones listed (owners and admins always).
    everyone_may_ask = models.BooleanField(default=True)
    allowed_users = models.ManyToManyField('core.CompanyUser', blank=True, related_name='data_sources_allowed')

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
    duration_ms = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ANSWERED)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.question[:60]
