"""Opening a company's database for one question, read-only, and reading its tables.

Every connection is opened for one question and closed straight after (no pool). Read-only is the second of three
layers (guards.check_sql comes first; the company's read-only user is the third):
  * PostgreSQL: default_transaction_read_only and statement_timeout, set as the connection opens;
  * MySQL/MariaDB: SET SESSION TRANSACTION READ ONLY and an execution time limit, LOCAL INFILE off;
  * SQLite: the file opened read-only and immutable, interrupted after the time limit, extensions never loaded.
Whatever happens, the transaction is rolled back. MongoDB has its own module (mongo.py): only aggregate(), with a
time limit.
"""
import datetime
import decimal
import os
import sqlite3
import time
import uuid

from django.conf import settings
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from .guards import Refused, resolve_public
from .models import DataSource

CONNECT_TIMEOUT = 10      # seconds
QUERY_TIMEOUT = 30        # seconds
MAX_ROWS = 1000           # rows fetched from a result; more are counted as "more"
MAX_TABLES = 400
MAX_COLUMNS = 150

_SYSTEM_SCHEMAS = {'information_schema', 'pg_catalog', 'pg_toast', 'mysql', 'performance_schema', 'sys'}


def files_root():
    """Where uploaded SQLite files are kept: never served, shared by the web and worker containers."""
    root = os.path.join(str(settings.LOCAL_STORAGE_ROOT), 'data_analyst')
    os.makedirs(root, exist_ok=True)
    return root


def new_file_path(company_id) -> str:
    folder = os.path.join(files_root(), str(int(company_id)))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f'{uuid.uuid4().hex}.sqlite')


def _safe_file(source: DataSource) -> str:
    """The source's file, only if it lies inside our folder (a path is never taken from anyone)."""
    root = os.path.realpath(files_root())
    path = os.path.realpath(source.file_path or '')
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        raise Refused('The uploaded file is missing. Upload it again.')
    return path


def _engine(source: DataSource):
    if source.kind == DataSource.KIND_SQLITE:
        path = _safe_file(source)

        def connect():
            conn = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True, check_same_thread=False,
                                   timeout=CONNECT_TIMEOUT)
            started = time.monotonic()
            # Stops a query that runs past the limit (returning non-zero interrupts it).
            conn.set_progress_handler(lambda: int(time.monotonic() - started > QUERY_TIMEOUT), 10_000)
            return conn
        return create_engine('sqlite+pysqlite://', creator=connect, poolclass=NullPool)

    address = resolve_public(source.host, source.port or _default_port(source.kind))
    if source.kind == DataSource.KIND_POSTGRES:
        url = URL.create('postgresql+psycopg', username=source.username or None, password=source.get_password() or None,
                         host=source.host, port=source.port or 5432, database=source.database or None)
        args = {'hostaddr': address, 'connect_timeout': CONNECT_TIMEOUT,
                'sslmode': 'require' if source.use_ssl else 'prefer',
                'options': f'-c default_transaction_read_only=on -c statement_timeout={QUERY_TIMEOUT * 1000}'}
        return create_engine(url, connect_args=args, poolclass=NullPool)
    if source.kind == DataSource.KIND_MYSQL:
        url = URL.create('mysql+mysqldb', username=source.username or None, password=source.get_password() or None,
                         host=address, port=source.port or 3306, database=source.database or None)
        args = {'connect_timeout': CONNECT_TIMEOUT, 'read_timeout': QUERY_TIMEOUT + 10, 'local_infile': False,
                'charset': 'utf8mb4', 'init_command': 'SET SESSION TRANSACTION READ ONLY'}
        if source.use_ssl:
            args['ssl_mode'] = 'REQUIRED'
        return create_engine(url, connect_args=args, poolclass=NullPool)
    raise Refused('This kind of database is not supported yet.')


def _default_port(kind) -> int:
    return {DataSource.KIND_POSTGRES: 5432, DataSource.KIND_MYSQL: 3306}.get(kind, 0)


def _limit_mysql_time(conn):
    """MySQL's limit is max_execution_time (ms), MariaDB's max_statement_time (s); each refuses the other's."""
    for statement in (f'SET SESSION max_execution_time = {QUERY_TIMEOUT * 1000}',
                      f'SET SESSION max_statement_time = {QUERY_TIMEOUT}'):
        try:
            conn.exec_driver_sql(statement)
        except Exception:
            pass


def _value(v):
    """A value the screen and the AI can read: dates and decimals as text, bytes described, never raw."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f'<{len(bytes(v))} bytes>'
    return str(v)


def friendly_error(exc) -> str:
    """The database's own words, first line, without the driver's long tail, with what to do where it's clear."""
    if exc.__class__.__name__ in ('ServerSelectionTimeoutError', 'AutoReconnect', 'NetworkTimeout'):
        # MongoDB's own message lists every server it tried, with the whole topology: too long, and the same advice.
        return ("Could not reach the MongoDB server in time. (Allow our server's address in the database's firewall: "
                'in MongoDB Atlas, under Network Access.)')
    text = str(getattr(exc, 'orig', None) or exc).strip().splitlines()
    message = (text[0] if text else exc.__class__.__name__)[:400]
    if exc.__class__.__name__ == 'OperationFailure':
        message = message.split(', full error:')[0]
    lowered = ' '.join(text).lower()
    if 'does not support ssl' in lowered or 'ssl connection is required' in lowered and 'not' in lowered:
        message += ' (This server has no encrypted connection: untick "Require an encrypted connection".)'
    elif ('password authentication failed' in lowered or 'access denied' in lowered or 'bad auth' in lowered
          or 'authentication failed' in lowered):
        message += ' (Check the user and password.)'
    elif 'not authorized' in lowered:
        message += ' (This user may not read it: give it the read role on the database.)'
    elif 'timeout' in lowered and 'connect' in lowered:
        message += " (Our server couldn't reach it: allow our address in the database's firewall.)"
    return message


_TIMED_OUT = ('statement timeout', 'max_statement_time', 'maximum statement execution time', 'execution was interrupted',
              'lost connection to mysql server during query', 'exceeded time limit', 'maxtimemsexpired')


def timed_out(exc) -> bool:
    """The database stopped the query at our time limit (PostgreSQL, MySQL, MariaDB, MongoDB's maxTimeMS, or SQLite's
    progress check)."""
    if exc.__class__.__name__ == 'ExecutionTimeout':
        return True
    text = str(getattr(exc, 'orig', None) or exc).lower()
    return any(words in text for words in _TIMED_OUT) or text.strip() == 'interrupted'


def run(source: DataSource, sql: str, max_rows: int = MAX_ROWS) -> dict:
    """Run one already-checked query read-only. {"columns", "rows", "truncated", "duration_ms"}."""
    if source.kind == DataSource.KIND_MONGO:
        from . import mongo
        return mongo.run(source, sql, max_rows)
    engine = _engine(source)
    started = time.monotonic()
    try:
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_MYSQL:
                _limit_mysql_time(conn)
            try:
                result = conn.execution_options(no_parameters=True).exec_driver_sql(sql)
                columns = list(result.keys())
                fetched = result.fetchmany(max_rows + 1) if result.returns_rows else []
            finally:
                conn.rollback()
    finally:
        engine.dispose()
    rows = [[_value(v) for v in row] for row in fetched[:max_rows]]
    return {'columns': columns, 'rows': rows, 'truncated': len(fetched) > max_rows,
            'duration_ms': int((time.monotonic() - started) * 1000)}


def _table_entry(name, schema, default, kind, columns, pk, fks) -> dict:
    return {'name': name, 'schema': schema if schema and schema != default else '', 'kind': kind,
            'columns': [{'name': c['name'], 'type': str(c.get('type')), 'pk': c['name'] in pk,
                         'nullable': bool(c.get('nullable', True))} for c in (columns or [])[:MAX_COLUMNS]],
            'fks': [{'columns': fk.get('constrained_columns') or [],
                     'references': f"{fk.get('referred_table')}({', '.join(fk.get('referred_columns') or [])})"}
                    for fk in (fks or [])] if kind == 'table' else []}


_INFO_QUERIES = {
    # Only tables and views the user can read appear in information_schema: exactly the ones worth knowing.
    DataSource.KIND_POSTGRES: {
        'schema_filter': "table_schema NOT IN ('pg_catalog', 'information_schema') AND table_schema NOT LIKE 'pg\\_%'",
        'default_schema': 'public',
    },
    DataSource.KIND_MYSQL: {
        'schema_filter': 'table_schema = DATABASE()',
        'default_schema': None,
    },
}


def _read_information_schema(conn, kind) -> list:
    """Tables, columns and keys from information_schema, one query each (PostgreSQL, MySQL/MariaDB).

    SQLAlchemy's PostgreSQL reading joins pg_collation, which a locked-down read-only user may not read: every table
    failed on RNAcentral's public reader (3 Nov 2026). Table by table was also slow: Rfam's 64 tables took 25 s."""
    q = _INFO_QUERIES[kind]
    where = q['schema_filter']

    def rows(sql):
        try:   # no_parameters: a % in LIKE must not be read as a placeholder
            return list(conn.execution_options(no_parameters=True).exec_driver_sql(sql))
        except Exception:
            return []

    tables = rows(f'SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE {where} '
                  'ORDER BY table_schema, table_name')
    default = q['default_schema'] or (tables[0][0] if tables else None)
    tables.sort(key=lambda t: (t[0] != default, t[0], t[1]))
    tables = tables[:MAX_TABLES]
    wanted = {(t[0], t[1]) for t in tables}
    columns = {}
    for schema, table, column, data_type, nullable in rows(
            f'SELECT table_schema, table_name, column_name, data_type, is_nullable FROM information_schema.columns '
            f'WHERE {where} ORDER BY table_schema, table_name, ordinal_position'):
        if (schema, table) in wanted:
            columns.setdefault((schema, table), []).append({'name': column, 'type': data_type,
                                                            'nullable': str(nullable).upper() == 'YES'})
    pks = {}
    for schema, table, column in rows(
            'SELECT kcu.table_schema, kcu.table_name, kcu.column_name FROM information_schema.table_constraints tc '
            'JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name '
            'AND kcu.table_schema = tc.table_schema AND kcu.table_name = tc.table_name '
            f"WHERE tc.constraint_type = 'PRIMARY KEY' AND {where.replace('table_schema', 'tc.table_schema')}"):
        pks.setdefault((schema, table), set()).add(column)
    fks = {}
    if kind == DataSource.KIND_MYSQL:
        fk_rows = rows('SELECT table_schema, table_name, column_name, referenced_table_name, referenced_column_name '
                       f'FROM information_schema.key_column_usage WHERE {where} AND referenced_table_name IS NOT NULL')
    else:
        fk_rows = rows('SELECT kcu.table_schema, kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name '
                       'FROM information_schema.table_constraints tc '
                       'JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name '
                       'AND kcu.table_schema = tc.table_schema '
                       'JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name '
                       'AND ccu.constraint_schema = tc.constraint_schema '
                       f"WHERE tc.constraint_type = 'FOREIGN KEY' AND {where.replace('table_schema', 'tc.table_schema')}")
    for schema, table, column, ref_table, ref_column in fk_rows:
        fks.setdefault((schema, table), []).append({'constrained_columns': [column], 'referred_table': ref_table,
                                                    'referred_columns': [ref_column]})
    out = []
    for schema, table, table_type in tables:
        cols = [dict(c, pk=c['name'] in pks.get((schema, table), set())) for c in columns.get((schema, table), [])]
        if not cols:
            continue
        kind_of = 'view' if 'VIEW' in str(table_type).upper() else 'table'
        out.append(_table_entry(table, schema, default, kind_of, cols, {c['name'] for c in cols if c['pk']},
                                fks.get((schema, table))))
    return out


def read_tables(source: DataSource) -> list:
    """Tables and views with their columns, types and keys: never a value. PostgreSQL reads with each statement on
    its own, so one refused statement can't abort the rest; the session stays read-only."""
    if source.kind == DataSource.KIND_MONGO:
        from . import mongo
        return mongo.read_tables(source)
    engine = _engine(source)
    try:
        with engine.connect() as raw:
            if source.kind in _INFO_QUERIES:
                conn = raw.execution_options(isolation_level='AUTOCOMMIT') if source.kind == DataSource.KIND_POSTGRES \
                    else raw
                return _read_information_schema(conn, source.kind)
            insp = inspect(raw)
            out = []
            names = [(n, 'table') for n in insp.get_table_names()] + [(n, 'view') for n in insp.get_view_names()]
            for name, kind in names[:MAX_TABLES]:
                try:
                    pk = set((insp.get_pk_constraint(name) or {}).get('constrained_columns') or [])
                    out.append(_table_entry(name, '', '', kind, insp.get_columns(name), pk,
                                            insp.get_foreign_keys(name) if kind == 'table' else []))
                except Exception:
                    continue
            return out
    finally:
        engine.dispose()


def can_write(source: DataSource):
    """Whether the database user could change data, as far as can be told; None when it can't be told."""
    if source.kind == DataSource.KIND_SQLITE:
        return False            # opened read-only and immutable
    if source.kind == DataSource.KIND_MONGO:
        from . import mongo
        try:
            return mongo.can_write(source)
        except Exception:
            return None
    engine = _engine(source)
    try:
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_POSTGRES:
                row = conn.exec_driver_sql(
                    "SELECT bool_or(has_table_privilege(c.oid, 'INSERT') OR has_table_privilege(c.oid, 'UPDATE') "
                    "OR has_table_privilege(c.oid, 'DELETE')) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')").first()
                conn.rollback()
                return bool(row[0]) if row and row[0] is not None else False
            grants = ' '.join(str(r[0]).upper() for r in conn.exec_driver_sql('SHOW GRANTS'))
            conn.rollback()
            return any(word in grants for word in ('ALL PRIVILEGES', 'INSERT', 'UPDATE', 'DELETE'))
    except Exception:
        return None
    finally:
        engine.dispose()
