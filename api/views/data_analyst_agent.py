"""AI Data Analyst API (plan: MDS/01-Plan/week-45/2026-11-03_Data-Analyst-Agent-Plan.md).

  GET    data-analyst/setup                  our server's address to allow, the kinds of database, the file limit
  GET    data-analyst/sources                the databases this login may ask (owners and admins: all)
  POST   data-analyst/sources                owner/admin: a connection (JSON: PostgreSQL, MySQL, or a MongoDB
                                             connection string) or a file (multipart): a SQLite database, or a .sql
                                             dump (MySQL, PostgreSQL, SQLite, SQL Server; .sql.gz too), which is read
                                             into a SQLite copy, in the background when it is big
  GET    data-analyst/sources/<id>           one source (never its password)
  PATCH  data-analyst/sources/<id>           owner/admin: change it
  DELETE data-analyst/sources/<id>           owner/admin: remove it, its file and its questions
  POST   data-analyst/sources/<id>/test      owner/admin: connect, read its tables, check the user can't write
  POST   data-analyst/ask                    {source, question, conversation?}: the answer, the SQL, the rows (not kept).
                                             A chat (conversation) stays on the database it started with, and is
                                             only its asker's (14 Nov 2026)
  GET    data-analyst/chats                  this login's chats, newest first: title, database, questions, last time
  DELETE data-analyst/chats/<conversation>   remove one of this login's chats (its questions)
  GET    data-analyst/questions              this login's questions (owners/admins: ?all=1 for everyone's)
  GET    data-analyst/questions/<id>         one, without rows
  POST   data-analyst/questions/<id>/run     its SQL run again now, read-only: the rows as of now
  GET    data-analyst/questions/<id>/csv     its SQL run again, streamed as a CSV (nothing kept)

Gated by the module middleware (prefix `data-analyst` -> data_analyst_agent).
"""
import csv
import io
import logging
import os
import re

from django.conf import settings
from django.db import transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyAdmin, IsCompanyUserOnly
from core.api_key_service import KeyServiceError
from data_analyst_agent import connectors, dumps, engine, mongo, mssql, sources as source_work
from data_analyst_agent.guards import Refused, check_query
from data_analyst_agent.models import DataQuestion, DataSource

logger = logging.getLogger(__name__)

MAX_QUESTION = 2000
SQLITE_HEADER = b'SQLite format 3\x00'
CSV_MAX_ROWS = 50_000


class AnalystThrottle(SimpleRateThrottle):
    """Per login: `analyst_llm` in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']."""
    scope = 'analyst_llm'

    def get_cache_key(self, request, view):
        ident = getattr(getattr(request, 'user', None), 'pk', None)
        return self.cache_format % {'scope': self.scope, 'ident': ident or self.get_ident(request)}


class AnalystConnectThrottle(AnalystThrottle):
    """Adding or testing a database makes our server connect to an address someone typed. Per login:
    `analyst_connect`, so it can't be used to probe other machines one port after another."""
    scope = 'analyst_connect'

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        return super().allow_request(request, view)


def _err(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'status': 'error', 'message': message}, status=code)


def _is_admin(request) -> bool:
    return getattr(request.user, 'role', None) in IsCompanyAdmin.ADMIN_ROLES


def _admins_only(request):
    if _is_admin(request):
        return None
    return _err('Only an owner or admin of your company can add, change or remove a database.',
                status.HTTP_403_FORBIDDEN)


def _max_file_bytes() -> int:
    return int(getattr(settings, 'DATA_ANALYST_MAX_FILE_MB', 500)) * 1024 * 1024


def _source_for(request, pk, *, manage=False):
    """The source `pk` of this company that this login may use (or manage), else (None, a refusal)."""
    source = DataSource.objects.filter(company_id=request.user.company_id, pk=pk).first()
    if source is None or not (source.may_ask(request.user) or _is_admin(request)):
        return None, _err('That database was not found.', status.HTTP_404_NOT_FOUND)
    if manage:
        refused = _admins_only(request)
        if refused:
            return None, refused
    return source, None


def _serialize(source: DataSource, request) -> dict:
    out = {
        'id': source.pk, 'name': source.name, 'kind': source.kind, 'kind_label': source.get_kind_display(),
        'status': source.status, 'last_error': source.last_error,
        'last_checked_at': source.last_checked_at.isoformat() if source.last_checked_at else None,
        'tables_count': len(source.tables or []),
        'tables_read_at': source.tables_read_at.isoformat() if source.tables_read_at else None,
        'user_can_write': source.user_can_write, 'send_rows_to_ai': source.send_rows_to_ai,
        'everyone_may_ask': source.everyone_may_ask,
        'created_at': source.created_at.isoformat() if source.created_at else None,
    }
    if source.is_connection:
        out.update({'host': source.host, 'port': source.port, 'database': source.database,
                    'username': source.username, 'use_ssl': source.use_ssl,
                    'has_password': bool(source.password_encrypted)})
        if source.kind == DataSource.KIND_MONGO:
            out['use_srv'] = source.use_srv
    else:
        out.update({'file_name': source.file_name, 'file_size': source.file_size})
        report = source.load_report or {}
        if report:
            out['load'] = {
                'dialect_label': report.get('dialect_label', ''), 'dump_name': report.get('dump_name', ''),
                'loading': source.status == DataSource.STATUS_LOADING,
                'tables': len(report.get('tables') or []), 'rows': report.get('rows'),
                'skipped': sum((report.get('skipped') or {}).values()), 'skipped_kinds': list(report.get('skipped') or {})[:4],
                'problems': (report.get('problems') or [])[:3], 'seconds': report.get('seconds'),
            }
    if _is_admin(request):
        out['allowed_user_ids'] = list(source.allowed_users.values_list('pk', flat=True))
        out['tables'] = [{'name': t['name'], 'schema': t.get('schema', ''), 'kind': t.get('kind', 'table'),
                          'columns': len(t.get('columns') or [])} for t in (source.tables or [])]
    return out


def _bool(value, default):
    if value is None or value == '':
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _apply_mongo_fields(source: DataSource, data, text):
    """MongoDB: a mongodb:// or mongodb+srv:// string first, then the fields sent. A database name typed beside the
    string wins over the string's (an app's string often has none, and its data is then in "test")."""
    if text:
        parsed = mongo.parse_uri(text)
        source.kind, source.use_srv, source.use_ssl = DataSource.KIND_MONGO, parsed['srv'], parsed['tls']
        source.host, source.port, source.options = parsed['host'], parsed['port'], parsed['options']
        source.database, source.username = parsed['database'], parsed['username']
        if parsed['password']:
            source.set_password(parsed['password'])
    for field in ('host', 'database', 'username'):
        if str(data.get(field) or '').strip():
            setattr(source, field, str(data.get(field)).strip()[:255])
    if str(data.get('port') or '').strip().isdigit():
        source.port = int(str(data.get('port')).strip())
    if str(data.get('password') or '').strip():
        source.set_password(str(data.get('password')))
    if 'use_ssl' in data and not text:
        source.use_ssl = _bool(data.get('use_ssl'), True)
    if not source.host:
        raise Refused('Paste the MongoDB connection string, e.g. '
                      'mongodb+srv://reader:password@cluster0.example.mongodb.net/your_db')
    if not source.username:
        raise Refused('The connection string needs a user (reader:password@...): a user that can only read.')


def _apply_sql_server_string(source: DataSource, text):
    """SQL Server's strings: ADO.NET (Azure portal: Server=tcp:...;Initial Catalog=...;User ID=...), ODBC, JDBC or a
    mssql:// URL."""
    parsed = mssql.parse_connection_string(text)
    source.kind, source.host, source.port = DataSource.KIND_MSSQL, parsed['host'], parsed['port']
    source.database, source.username = parsed['database'], parsed['username']
    source.use_ssl, source.options = parsed['use_ssl'], parsed['options']
    if parsed['password']:
        source.set_password(parsed['password'])


def _apply_connection_fields(source: DataSource, data):
    """Copy the connection fields sent, a pasted connection string first. A password left blank keeps the saved one."""
    text = str(data.get('connection_string') or '').strip()
    if text.lower().startswith(('mongodb://', 'mongodb+srv://')) or (not text and source.kind == DataSource.KIND_MONGO):
        _apply_mongo_fields(source, data, text)
        return
    if text and mssql.looks_like_sql_server(text):
        _apply_sql_server_string(source, text)
        text = ''
    if text:
        from sqlalchemy.engine import make_url
        try:
            url = make_url(text)
        except Exception:
            raise Refused('That connection string could not be read.')
        driver = url.drivername.split('+')[0].lower()
        kind = {'postgresql': 'postgres', 'postgres': 'postgres', 'mysql': 'mysql', 'mariadb': 'mysql'}.get(driver)
        if kind is None:
            raise Refused('A connection string must start with postgresql://, mysql://, mariadb://, mongodb:// or '
                          'mongodb+srv://, or be a SQL Server string (Server=...;Database=...;User ID=...).')
        source.kind, source.host, source.port = kind, url.host or '', url.port
        source.database, source.username = url.database or '', url.username or ''
        if url.password:
            source.set_password(url.password)
        # SSL is required only when the string asks for it; otherwise it is used when the server offers it. A string
        # without sslmode required it, and a server without SSL (RNAcentral's) was refused (3 Nov 2026).
        sslmode = str(url.query.get('sslmode') or url.query.get('ssl_mode') or '').lower()
        source.use_ssl = sslmode in ('require', 'required', 'verify-ca', 'verify-full', 'verify_ca', 'verify_identity')
    for field in ('host', 'database', 'username'):
        if field in data:
            setattr(source, field, str(data.get(field) or '').strip()[:255])
    if 'port' in data:
        port = str(data.get('port') or '').strip()
        source.port = int(port) if port.isdigit() else None
    if str(data.get('password') or '').strip():
        source.set_password(str(data.get('password')))
    if 'use_ssl' in data:
        source.use_ssl = _bool(data.get('use_ssl'), True)
    if source.kind not in DataSource.CONNECTION_KINDS:
        raise Refused('Choose PostgreSQL, MySQL / MariaDB, SQL Server or MongoDB.')
    if source.kind == DataSource.KIND_MSSQL:
        mssql.check_host(source.host)
    if not source.host or not source.database or not source.username:
        raise Refused('Give the host, the database name and the user.')


def _apply_shared_fields(source: DataSource, data):
    if 'name' in data:
        source.name = str(data.get('name') or '').strip()[:120]
    if 'send_rows_to_ai' in data:
        source.send_rows_to_ai = _bool(data.get('send_rows_to_ai'), True)
    if 'everyone_may_ask' in data:
        source.everyone_may_ask = _bool(data.get('everyone_may_ask'), True)


def _apply_allowed(source: DataSource, data):
    ids = data.getlist('allowed_user_ids') if hasattr(data, 'getlist') else data.get('allowed_user_ids')
    if ids is None:
        return
    from core.models import CompanyUser
    wanted = [int(i) for i in (ids if isinstance(ids, (list, tuple)) else [ids]) if str(i).isdigit()]
    source.allowed_users.set(CompanyUser.objects.filter(company_id=source.company_id, pk__in=wanted))


def _write_upload(upload, path):
    with open(path, 'wb') as out:
        for chunk in upload.chunks():
            out.write(chunk)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover (Windows)
        pass


def _save_upload(source: DataSource, upload):
    """A SQLite database is kept as it is. A .sql dump (or .sql.gz) is kept until it has been read into a SQLite copy:
    the source is "loading" until then."""
    if upload.size > _max_file_bytes():
        raise Refused(f'The file is larger than {_max_file_bytes() // (1024 * 1024)} MB.')
    head = upload.read(16)
    upload.seek(0)
    name = re.sub(r'[^\w.\- ]', '_', os.path.basename(upload.name or 'database.sqlite'))[:255]
    if head == SQLITE_HEADER:
        path = connectors.new_file_path(source.company_id)
        _write_upload(upload, path)
        source.file_path, source.file_size, source.file_name = path, upload.size, name
        return
    path = connectors.new_file_path(source.company_id, '.sql.gz' if head[:2] == dumps.GZIP_MAGIC else '.sql')
    _write_upload(upload, path)
    dialect = dumps.sniff(dumps.read_head(path))
    if dialect is None:
        connectors.remove_file(path)
        raise Refused('That is neither a SQLite database file nor a .sql dump with tables in it.')
    source.file_path, source.file_size, source.file_name = path, upload.size, name
    source.status = DataSource.STATUS_LOADING
    source.load_report = {'dialect': dialect, 'dialect_label': dumps.LABELS[dialect], 'dump_name': name,
                          'dump_size': upload.size}


def _remove_file(source: DataSource):
    if source.kind == DataSource.KIND_SQLITE and source.file_path:
        root = os.path.realpath(connectors.files_root())
        path = os.path.realpath(source.file_path)
        if path.startswith(root + os.sep) and os.path.isfile(path):
            os.remove(path)


_test = source_work.test_source


def _load_or_queue(source: DataSource):
    """Read an uploaded dump now when it is small, else in the background. (ok, message)."""
    if (source.file_size or 0) <= dumps.INLINE_BYTES:
        return source_work.load_dump(source)
    from data_analyst_agent.tasks import load_dump
    load_dump.delay(source.pk)
    return True, ('The dump is being read in the background; this page shows when it is ready. Big dumps take a few '
                  'minutes.')


# ---- endpoints ------------------------------------------------------------------------------------------------------

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def setup(request):
    return Response({'status': 'success', 'data': {
        'server_ip': getattr(settings, 'DATA_ANALYST_SERVER_IP', '') or '',
        'kinds': [{'value': v, 'label': label} for v, label in DataSource.KIND_CHOICES],
        'max_file_mb': _max_file_bytes() // (1024 * 1024),
        'can_manage': _is_admin(request),
    }})


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([AnalystConnectThrottle])
def sources(request):
    if request.method == 'GET':
        rows = DataSource.objects.filter(company_id=request.user.company_id).prefetch_related('allowed_users')
        for s in rows:
            source_work.settle_stale(s)
        visible = [s for s in rows if _is_admin(request) or s.may_ask(request.user)]
        return Response({'status': 'success', 'data': [_serialize(s, request) for s in visible]})
    refused = _admins_only(request)
    if refused:
        return refused
    data = request.data
    upload = request.FILES.get('file')
    source = DataSource(company_id=request.user.company_id, created_by=request.user)
    try:
        _apply_shared_fields(source, data)
        if upload is not None:
            source.kind = DataSource.KIND_SQLITE
            _save_upload(source, upload)
        else:
            source.kind = str(data.get('kind') or '').strip()
            _apply_connection_fields(source, data)
        if not source.name:
            source.name = (source.file_name or source.database or (source.host or '').split('.')[0] or 'Database')[:120]
    except Refused as exc:
        return _err(str(exc))
    with transaction.atomic():
        source.save()
        _apply_allowed(source, data)
    if source.status == DataSource.STATUS_LOADING:
        ok, message = _load_or_queue(source)
        source.refresh_from_db()
    else:
        ok, message = _test(source)
    return Response({'status': 'success', 'message': message, 'data': _serialize(source, request)},
                    status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def source_detail(request, source_id):
    source, refused = _source_for(request, source_id, manage=request.method != 'GET')
    if refused:
        return refused
    if request.method == 'GET':
        return Response({'status': 'success', 'data': _serialize(source, request)})
    if request.method == 'DELETE':
        questions = source.questions.count()
        _remove_file(source)
        source.delete()
        return Response({'status': 'success', 'message': f'Removed, with its {questions} question(s).'})
    data = request.data
    try:
        _apply_shared_fields(source, data)
        if source.is_connection and any(k in data for k in ('host', 'port', 'database', 'username', 'password',
                                                              'use_ssl', 'connection_string')):
            _apply_connection_fields(source, data)
            source.status = DataSource.STATUS_NEW
    except Refused as exc:
        return _err(str(exc))
    source.save()
    _apply_allowed(source, data)
    return Response({'status': 'success', 'data': _serialize(source, request)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([AnalystConnectThrottle])
def source_test(request, source_id):
    source, refused = _source_for(request, source_id, manage=True)
    if refused:
        return refused
    if source.status == DataSource.STATUS_LOADING:
        return _err('The dump is still being read. This page shows when it is ready.')
    ok, message = _test(source)
    return Response({'status': 'success' if ok else 'error', 'message': message,
                     'data': _serialize(source, request)}, status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([AnalystThrottle])
def ask(request):
    data = request.data if isinstance(request.data, dict) else {}
    question = str(data.get('question') or '').strip()
    if not question:
        return _err('Type a question.')
    if len(question) > MAX_QUESTION:
        return _err(f'Keep the question under {MAX_QUESTION} characters.')
    source, refused = _source_for(request, data.get('source') or 0)
    if refused:
        return refused
    if not source.may_ask(request.user):
        return _err('You may not ask this database. Ask an owner or admin of your company.', status.HTTP_403_FORBIDDEN)
    if source.status == DataSource.STATUS_LOADING:
        return _err('This database is still being read from its dump. Ask again when it is ready.')
    conversation = _conversation(data.get('conversation'))
    if conversation:
        # A chat is its asker's, and stays on the database it started with: its earlier turns are about that one,
        # and the screen offers another chat (or a new one) for another database.
        earlier = DataQuestion.objects.filter(conversation=conversation)
        if earlier.exclude(company_id=request.user.company_id, asked_by=request.user).exists():
            return _err('That chat was not found.', status.HTTP_404_NOT_FOUND)
        other = earlier.exclude(source=source).select_related('source').first()
        if other is not None:
            return _err(f'This chat is about {other.source.name}. Start a new chat to ask about {source.name}.',
                        status.HTTP_409_CONFLICT)
    try:
        result = engine.ask(request.user, source, question, conversation=conversation)
    except Refused as exc:
        return _err(str(exc))
    except KeyServiceError as exc:
        return Response({'status': 'error', 'code': exc.reason, 'message': exc.user_message},
                        status=status.HTTP_402_PAYMENT_REQUIRED)
    except Exception:
        logger.exception('data analyst ask failed')
        return _err('The question could not be answered just now. Please try again.',
                    status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({'status': 'success', 'data': result})


def _question_for(request, pk):
    record = (DataQuestion.objects.select_related('source', 'asked_by')
              .filter(company_id=request.user.company_id, pk=pk).first())
    if record is None or (record.asked_by_id != request.user.pk and not _is_admin(request)):
        return None, _err('That question was not found.', status.HTTP_404_NOT_FOUND)
    return record, None


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def questions(request):
    rows = DataQuestion.objects.select_related('source', 'asked_by').filter(company_id=request.user.company_id)
    if not (_is_admin(request) and request.query_params.get('all') == '1'):
        rows = rows.filter(asked_by=request.user)
    if str(request.query_params.get('source') or '').isdigit():
        rows = rows.filter(source_id=int(request.query_params['source']))
    if request.query_params.get('conversation'):
        conversation = _conversation(request.query_params['conversation'])
        rows = rows.filter(conversation=conversation) if conversation else rows.none()
    return Response({'status': 'success', 'data': [engine.serialize_question(q) for q in rows[:200]]})


def _conversation(value):
    """A chat's id as given, or None when it is not one (it is a UUID)."""
    value = str(value or '').strip()
    return value if re.fullmatch(r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}',
                                 value) else None


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def chats(request):
    """This login's chats, newest first (the chat list on the left): each with its first question as the title, the
    database it is about, how many questions, and when the last one was asked."""
    rows = (DataQuestion.objects.select_related('source')
            .filter(company_id=request.user.company_id, asked_by=request.user)
            .only('conversation', 'question', 'created_at', 'source__id', 'source__name', 'source__kind',
                  'source__status')
            .order_by('-created_at', '-id')[:3000])
    found = {}
    for q in rows:
        chat = found.get(q.conversation)
        if chat is None:
            chat = found[q.conversation] = {
                'id': str(q.conversation), 'last_at': q.created_at.isoformat(), 'questions': 0,
                'source': {'id': q.source_id, 'name': q.source.name, 'kind': q.source.kind,
                           'kind_label': q.source.get_kind_display(), 'status': q.source.status},
            }
        chat['questions'] += 1
        chat['title'] = q.question[:120]          # the rows come newest first: the last one seen is the first asked
    return Response({'status': 'success', 'data': list(found.values())[:300]})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def chat_detail(request, conversation):
    """Remove one of this login's chats: its questions, answers and SQL."""
    conversation = _conversation(conversation)
    rows = DataQuestion.objects.filter(company_id=request.user.company_id, asked_by=request.user,
                                       conversation=conversation) if conversation else DataQuestion.objects.none()
    removed = rows.count()
    if not removed:
        return _err('That chat was not found.', status.HTTP_404_NOT_FOUND)
    rows.delete()
    return Response({'status': 'success', 'message': 'The chat was removed.', 'data': {'removed': removed}})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def question_detail(request, question_id):
    record, refused = _question_for(request, question_id)
    if refused:
        return refused
    return Response({'status': 'success', 'data': engine.serialize_question(record)})


def _rerun(request, record, max_rows):
    if not record.sql:
        raise Refused('This question has no query to run.')
    if not record.source.may_ask(request.user):
        raise Refused('You may not ask this database any more.')
    checked = check_query(record.sql, record.source.kind, engine.collections(record.source))
    return connectors.run(record.source, checked, max_rows=max_rows)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def question_run(request, question_id):
    record, refused = _question_for(request, question_id)
    if refused:
        return refused
    try:
        result = _rerun(request, record, engine.ROWS_TO_SCREEN)
    except Refused as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f'The query could not be run: {connectors.friendly_error(exc)}')
    return Response({'status': 'success', 'data': {'columns': result['columns'], 'rows': result['rows'],
                                                   'more_rows': result['truncated'], 'as_of': timezone.now().isoformat()}})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def question_csv(request, question_id):
    record, refused = _question_for(request, question_id)
    if refused:
        return refused
    try:
        result = _rerun(request, record, CSV_MAX_ROWS)
    except Refused as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f'The query could not be run: {connectors.friendly_error(exc)}')

    def lines():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(result['columns'])
        for row in result['rows']:
            writer.writerow(['' if v is None else v for v in row])
            if buffer.tell() > 64_000:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        yield buffer.getvalue()

    response = StreamingHttpResponse(lines(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="question-{record.pk}.csv"'
    return response
