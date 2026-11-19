"""Opening a company's database for one question, read-only, and reading its tables.

Every connection is opened for one question and closed straight after (no pool). Read-only is the second of three
layers (guards.check_sql comes first; the company's read-only user is the third):
  * PostgreSQL: default_transaction_read_only and statement_timeout, set as the connection opens;
  * MySQL/MariaDB: SET SESSION TRANSACTION READ ONLY and an execution time limit, LOCAL INFILE off;
  * SQL Server: ApplicationIntent=ReadOnly and a query time limit (mssql.py);
  * SQLite: the file opened read-only and immutable, interrupted after the time limit, extensions never loaded.
Whatever happens, the transaction is rolled back. MongoDB has its own module (mongo.py): only aggregate(), with a
time limit.
"""
import datetime
import decimal
import json
import logging
import os
import re
import sqlite3
import time
import uuid

from django.conf import settings
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from .guards import Refused, resolve_public
from .models import DataSource

logger = logging.getLogger(__name__)

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


def new_file_path(company_id, suffix='.sqlite') -> str:
    folder = os.path.join(files_root(), str(int(company_id)))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f'{uuid.uuid4().hex}{suffix}')


def safe_path(path) -> str:
    """`path`, only if it is a file inside our folder (a path is never taken from anyone)."""
    root = os.path.realpath(files_root())
    real = os.path.realpath(path or '')
    if not real.startswith(root + os.sep) or not os.path.isfile(real):
        raise Refused('The uploaded file is missing. Upload it again.')
    return real


def remove_file(path):
    """Delete a file of ours (inside our folder only); nothing when it is already gone."""
    try:
        os.remove(safe_path(path))
    except (Refused, OSError):
        pass


def _safe_file(source: DataSource) -> str:
    """The source's file, only if it lies inside our folder."""
    return safe_path(source.file_path)


def _engine(source: DataSource, seconds=None):
    """seconds: the time limit for each statement, QUERY_TIMEOUT unless less is left (a second try, 17 Nov 2026)."""
    limit = seconds or QUERY_TIMEOUT
    if source.kind == DataSource.KIND_SQLITE:
        path = _safe_file(source)

        def connect():
            conn = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True, check_same_thread=False,
                                   timeout=CONNECT_TIMEOUT)
            started = time.monotonic()
            # Stops a query that runs past the limit (returning non-zero interrupts it).
            conn.set_progress_handler(lambda: int(time.monotonic() - started > limit), 10_000)
            return conn
        return create_engine('sqlite+pysqlite://', creator=connect, poolclass=NullPool)

    address = resolve_public(source.host, source.port or _default_port(source.kind))
    if source.kind == DataSource.KIND_POSTGRES:
        url = URL.create('postgresql+psycopg', username=source.username or None, password=source.get_password() or None,
                         host=source.host, port=source.port or 5432, database=source.database or None)
        args = {'hostaddr': address, 'connect_timeout': CONNECT_TIMEOUT,
                'sslmode': 'require' if source.use_ssl else 'prefer',
                'options': f'-c default_transaction_read_only=on -c statement_timeout={int(limit * 1000)}'}
        return create_engine(url, connect_args=args, poolclass=NullPool)
    if source.kind == DataSource.KIND_MSSQL:
        from . import mssql
        # Every address of the name was checked above; the connection uses the name, which SQL Server's certificate
        # and Azure SQL's gateway both need.
        url = URL.create('mssql+pyodbc', query={'odbc_connect': mssql.odbc_connection_string(source)})
        engine = create_engine(url, connect_args={'timeout': CONNECT_TIMEOUT}, poolclass=NullPool)

        @event.listens_for(engine, 'connect')
        def _query_time_limit(dbapi_connection, _record):
            dbapi_connection.timeout = int(limit)      # seconds; pyodbc stops a statement that runs longer

        return engine
    if source.kind == DataSource.KIND_MYSQL:
        url = URL.create('mysql+mysqldb', username=source.username or None, password=source.get_password() or None,
                         host=address, port=source.port or 3306, database=source.database or None)
        args = {'connect_timeout': CONNECT_TIMEOUT, 'read_timeout': int(limit) + 10, 'local_infile': False,
                'charset': 'utf8mb4', 'init_command': 'SET SESSION TRANSACTION READ ONLY'}
        if source.use_ssl:
            args['ssl_mode'] = 'REQUIRED'
        return create_engine(url, connect_args=args, poolclass=NullPool)
    raise Refused('This kind of database is not supported yet.')


#: The port each kind of server listens on unless set otherwise. The screen offers the same ones (16 Nov 2026).
DEFAULT_PORTS = {DataSource.KIND_POSTGRES: 5432, DataSource.KIND_MYSQL: 3306, DataSource.KIND_MSSQL: 1433,
                 DataSource.KIND_MONGO: 27017}


def default_port(kind) -> int:
    return DEFAULT_PORTS.get(kind, 0)


_default_port = default_port


def _limit_mysql_time(conn, seconds=None):
    """MySQL's limit is max_execution_time (ms), MariaDB's max_statement_time (s); each refuses the other's."""
    limit = seconds or QUERY_TIMEOUT
    for statement in (f'SET SESSION max_execution_time = {int(limit * 1000)}',
                      f'SET SESSION max_statement_time = {int(limit)}'):
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
    if 'SQL Server' in message:
        from . import mssql
        message = mssql.clean_error(' '.join(text))[:400]
    if exc.__class__.__name__ == 'OperationFailure':
        message = message.split(', full error:')[0]
    lowered = ' '.join(text).lower()
    if 'does not support ssl' in lowered or 'ssl connection is required' in lowered and 'not' in lowered:
        message += ' (This server has no encrypted connection: untick "Require an encrypted connection".)'
    elif ('password authentication failed' in lowered or 'access denied' in lowered or 'bad auth' in lowered
          or 'authentication failed' in lowered or 'login failed' in lowered):
        message += ' (Check the user and password.)'
    elif 'certificate' in lowered and ('not trusted' in lowered or 'verify failed' in lowered):
        message += (" (The server's certificate is not trusted. For your own server with a self-signed certificate, "
                    'add TrustServerCertificate=yes to the connection string.)')
    elif 'cannot open database' in lowered:
        message += ' (Check the database name, and that this user may use it.)'
    elif 'login timeout expired' in lowered or 'tcp provider' in lowered or 'network-related' in lowered:
        message += (" (Our server couldn't reach it: allow our address in the database's firewall; in Azure SQL, under "
                    "the server's Networking.)")
    elif 'not authorized' in lowered:
        message += ' (This user may not read it: give it the read role on the database.)'
    elif 'timeout' in lowered and 'connect' in lowered:
        message += " (Our server couldn't reach it: allow our address in the database's firewall.)"
    return message


_TIMED_OUT = ('statement timeout', 'max_statement_time', 'maximum statement execution time', 'execution was interrupted',
              'lost connection to mysql server during query', 'exceeded time limit', 'maxtimemsexpired',
              'query timeout expired')


def timed_out(exc) -> bool:
    """The database stopped the query at our time limit (PostgreSQL, MySQL, MariaDB, MongoDB's maxTimeMS, or SQLite's
    progress check)."""
    if exc.__class__.__name__ == 'ExecutionTimeout':
        return True
    text = str(getattr(exc, 'orig', None) or exc).lower()
    return any(words in text for words in _TIMED_OUT) or text.strip() == 'interrupted'


def run(source: DataSource, sql: str, max_rows: int = MAX_ROWS, seconds=None) -> dict:
    """Run one already-checked query read-only. {"columns", "rows", "truncated", "duration_ms"}. seconds: its time
    limit when less than QUERY_TIMEOUT is left."""
    if source.kind == DataSource.KIND_MONGO:
        from . import mongo
        return mongo.run(source, sql, max_rows, seconds)
    engine = _engine(source, seconds)
    started = time.monotonic()
    try:
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_MYSQL:
                _limit_mysql_time(conn, seconds)
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


# ---- The values of a few short columns, for writing a query (16 Nov 2026) --------------------------------------
#
# Asked for tickets "status new, open or in progress", the AI wrote status = 'in progress' for a column that holds
# 'in_progress', and three tickets were missed. So before writing a query, the values of the chosen tables' short
# status-like columns are read from their first rows and named to the AI. Read when a question is asked, never kept,
# and only when the source lets the AI see rows. A column with more values than SAMPLE_VALUES is not a list of
# choices and is left out.
SAMPLE_SCAN_ROWS = 5000
SAMPLE_VALUES = 12
SAMPLE_TABLES = 15
SAMPLE_VALUE_CHARS = 40
_CHOICE_COLUMN = re.compile(r'(^|_)(status|state|type|kind|category|priority|stage|level|role|source|channel|mode|'
                            r'frequency|period|currency|response|outcome|tier|interval|direction|gender)$', re.I)
_TEXT_TYPE = re.compile(r'char|text|string|enum|varchar|clob', re.I)


def _quote(kind, name) -> str:
    if kind == DataSource.KIND_MYSQL:
        return '`' + str(name).replace('`', '``') + '`'
    if kind == DataSource.KIND_MSSQL:
        return '[' + str(name).replace(']', ']]') + ']'
    return '"' + str(name).replace('"', '""') + '"'


def row_counts(source: DataSource, tables, seconds=5) -> dict:
    """{table name: its number of rows} for these tables, on one connection; a table that can't be counted in time is
    left out. Used to tell a count that a join repeated (engine._too_many, 19 Nov 2026); never shown or kept."""
    found = {}
    if source.kind == DataSource.KIND_MONGO or not tables:
        return found
    try:
        engine = _engine(source, seconds)
    except Exception as exc:
        logger.info('row_counts: no connection: %s', str(exc)[:200])
        return found
    try:
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_MYSQL:
                _limit_mysql_time(conn, seconds)
            for t in tables[:8]:
                name = (_quote(source.kind, t['schema']) + '.' if t.get('schema') else '') + _quote(source.kind, t['name'])
                try:
                    found[t['name']] = int(conn.execution_options(no_parameters=True)
                                           .exec_driver_sql(f'SELECT COUNT(*) FROM {name}').scalar() or 0)
                except Exception:
                    conn.rollback()
    except Exception as exc:
        logger.info('row_counts failed: %s', str(exc)[:200])
    finally:
        engine.dispose()
    return found


def choice_columns(table) -> list:
    """The table's short text columns whose names say they hold one of a few choices (status, type, priority ...)."""
    return [c['name'] for c in table.get('columns') or []
            if _CHOICE_COLUMN.search(c['name']) and _TEXT_TYPE.search(str(c.get('type') or ''))]


# What a value looks like (19 Nov 2026). A test database kept its exchange-rate months as '2025-04-01'; the AI, never
# shown one, compared them with '2025-04' and took the previous month's rate, or matched nothing at all. Date-like
# text columns (month, issued_at, valid_to) and JSON ones (tags, properties, stage_history) now come with one example
# value, read with the choices and on the same terms (only when the AI may see rows; never kept).
EXAMPLE_ROWS = 50
EXAMPLE_CHARS = 160
_DATE_NAME = re.compile(r'(^|_)(month|date|day|week|year|period|time|timestamp|datetime|ts|dt|start|end|from|until)$'
                        r'|_(at|on)$|^(created|updated|modified)$|(valid|effective|date)_to$', re.I)
_JSON_NAME = re.compile(r'json|properties|metadata|payload|attributes|tags|history|settings|config|features|details|'
                        r'extra', re.I)


class Samples(dict):
    """sample_values' result: {(schema, table): {column: [values]}} for the choice columns, and in .examples
    {(schema, table): {column: one value}} for the date-like and JSON text columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.examples = {}


def example_columns(table) -> list:
    """The table's text columns whose values' form matters to a query: dates kept as text, and JSON."""
    choices, out = set(choice_columns(table)), []
    for c in table.get('columns') or []:
        name, kind = str(c['name']), str(c.get('type') or '')
        if name in choices:
            continue
        if 'json' in kind.lower() or ((not kind or _TEXT_TYPE.search(kind))
                                      and (_DATE_NAME.search(name) or _JSON_NAME.search(name))):
            out.append(name)
    return out


def _example(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, default=str)
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= EXAMPLE_CHARS else text[:EXAMPLE_CHARS] + '…'


def sample_values(source: DataSource, tables) -> dict:
    """{(schema, table): {column: [values]}} for the tables' choice columns, read from their first SAMPLE_SCAN_ROWS
    rows on one connection, and one example of each date-like or JSON text column (Samples.examples). Anything that
    fails is left out: the query is written without it."""
    if source.kind == DataSource.KIND_MONGO:
        from . import mongo
        return mongo.sample_values(source, tables)
    wanted = [(t, choice_columns(t), example_columns(t)) for t in tables if t.get('kind', 'table') in ('table', 'view')]
    wanted = [w for w in wanted if w[1] or w[2]][:SAMPLE_TABLES]
    found = Samples()
    if not wanted:
        return found
    engine = _engine(source)
    try:
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_MYSQL:
                _limit_mysql_time(conn)

            def first_rows(table, cols, count):
                name = (_quote(source.kind, table['schema']) + '.' if table.get('schema') else '') + \
                    _quote(source.kind, table['name'])
                listed = ', '.join(_quote(source.kind, c) for c in cols)
                sql = (f'SELECT TOP {count} {listed} FROM {name}' if source.kind == DataSource.KIND_MSSQL
                       else f'SELECT {listed} FROM {name} LIMIT {count}')
                try:
                    return conn.execution_options(no_parameters=True).exec_driver_sql(sql).fetchall()
                except Exception:
                    conn.rollback()
                    return None

            for table, cols, shown in wanted:
                key = (table.get('schema') or '', table['name'])
                if shown:
                    rows = first_rows(table, shown, EXAMPLE_ROWS) or []
                    examples = {}
                    for i, col in enumerate(shown):
                        value = next((r[i] for r in rows if r[i] is not None and r[i] != ''), None)
                        if value is not None:
                            examples[col] = _example(value)
                    if examples:
                        found.examples[key] = examples
                if not cols:
                    continue
                rows = first_rows(table, cols, SAMPLE_SCAN_ROWS)
                if rows is None:
                    continue
                values = {}
                for i, col in enumerate(cols):
                    seen = []
                    for row in rows:
                        v = row[i]
                        if v is None or v == '':
                            continue
                        v = str(v)
                        if len(v) > SAMPLE_VALUE_CHARS:
                            seen = None
                            break
                        if v not in seen:
                            seen.append(v)
                            if len(seen) > SAMPLE_VALUES:
                                seen = None
                                break
                    if seen:
                        values[col] = sorted(seen)
                if values:
                    found[(table.get('schema') or '', table['name'])] = values
            conn.rollback()
    except Exception:
        logger.info('data analyst: values not sampled for source %s', source.pk, exc_info=True)
    finally:
        engine.dispose()
    return found


# ---- what the database says about its own tables (17 Nov 2026) ----------------------------------------------------
# A test database's own data dictionary said "total_amount is in the order's currency: convert with exchange_rates
# (the latest rate_date on or before the order date)", "NULL customer_id is a guest checkout", "negative payments are
# refunds"; the AI never saw it and added up ten currencies. Column comments (PostgreSQL, MySQL / MariaDB, SQL Server)
# and a dictionary table the database keeps (table_name, column_name, description) are now its notes. Periods
# (valid_from / valid_to) are read for whether valid_to is the last day or the day the next one starts: "order_ts <
# valid_to" left out the orders on a tier's last day. Read when a question is asked, never kept.
NOTE_CHARS = 300
NOTES_MAX = 800
PERIOD_TABLES = 8
_DICT_TABLE = {'table_name', 'tablename', 'table', 'tbl', 'entity', 'entity_name'}
_DICT_COLUMN = {'column_name', 'columnname', 'column', 'field', 'field_name', 'attribute', 'col', 'col_name'}
_DICT_TEXT = {'description', 'descr', 'comment', 'comments', 'notes', 'note', 'definition', 'meaning', 'explanation',
              'details', 'remarks'}
_PERIOD_ENDS = (('valid_from', 'valid_to'), ('effective_from', 'effective_to'), ('date_from', 'date_to'),
                ('start_date', 'end_date'), ('starts_on', 'ends_on'), ('from_date', 'to_date'))
_MIDNIGHT = re.compile(r'^[ T]00:00(:00(\.0+)?)?$')
_COMMENT_QUERIES = {
    DataSource.KIND_MYSQL: (
        "SELECT table_name, '', table_comment FROM information_schema.tables WHERE table_schema = DATABASE() "
        "AND table_comment <> '' AND table_type = 'BASE TABLE'",
        "SELECT table_name, column_name, column_comment FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND column_comment <> ''",
    ),
    DataSource.KIND_POSTGRES: (
        "SELECT c.relname, COALESCE(a.attname, ''), d.description FROM pg_catalog.pg_description d "
        "JOIN pg_catalog.pg_class c ON c.oid = d.objoid JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid AND d.objsubid > 0 "
        "WHERE d.classoid = 'pg_catalog.pg_class'::regclass AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND n.nspname NOT LIKE 'pg\\_%'",
    ),
    DataSource.KIND_MSSQL: (
        "SELECT t.name, COALESCE(c.name, ''), CAST(ep.value AS nvarchar(1000)) FROM sys.extended_properties ep "
        "JOIN sys.objects t ON t.object_id = ep.major_id LEFT JOIN sys.columns c ON c.object_id = ep.major_id "
        "AND c.column_id = ep.minor_id AND ep.minor_id > 0 WHERE ep.class = 1 AND ep.name = 'MS_Description'",
    ),
}


def dictionary_table(tables):
    """(table, its table-name column, its column-name column or None, its description column) for a table the database
    keeps to describe its own tables and columns; None when it has none."""
    for t in tables:
        if t.get('kind', 'table') not in ('table', 'view'):
            continue
        names = {str(c['name']).lower(): c['name'] for c in t.get('columns') or []}
        table_col = next((names[n] for n in names if n in _DICT_TABLE), None)
        text_col = next((names[n] for n in names if n in _DICT_TEXT), None)
        if table_col and text_col:
            return t, table_col, next((names[n] for n in names if n in _DICT_COLUMN), None), text_col
    return None


def _day(value):
    """A date from a date, a midnight timestamp or 'YYYY-MM-DD...' text; None for anything else (a time of day)."""
    if isinstance(value, datetime.datetime):
        return value.date() if value.time() == datetime.time(0) else None
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()
    if len(text) > 10 and not _MIDNIGHT.match(text[10:]):
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def period_pairs(table) -> list:
    """[(start column, end column)] of a table of periods (valid_from / valid_to and the like)."""
    names = {str(c['name']).lower(): c['name'] for c in table.get('columns') or []}
    return [(names[a], names[b]) for a, b in _PERIOD_ENDS if a in names and b in names]


def _period_note(rows, start, end) -> str:
    """How a table's periods end, from its rows [(key, start, end)]: the next period of the same key starting the day
    after the end (the end is the last day) or on it (the end is not part of the period). '' when the rows don't say."""
    by_key = {}
    for key, begins, ends in rows:
        if key is not None:
            by_key.setdefault(key, []).append((_day(begins), ends, _day(ends)))
    after = on = 0
    for periods in by_key.values():
        periods.sort(key=lambda p: (p[0] is None, p[0] or datetime.date.min))
        for (_b, _raw, ends), (begins, _r2, _e2) in zip(periods, periods[1:]):
            if ends is None or begins is None:
                continue
            if begins == ends + datetime.timedelta(days=1):
                after += 1
            elif begins == ends:
                on += 1
    total = after + on
    if total < 5:
        return ''
    if after >= 0.8 * total:
        return (f'{end} is the period\'s last day (the next period starts the day after): a date d is in it when '
                f'{start} <= d <= {end}')
    if on >= 0.8 * total:
        return (f'{end} is the day the next period starts, not part of this one: a date d is in it when '
                f'{start} <= d < {end}')
    return ''


def notes(source: DataSource, tables) -> dict:
    """{table name (lower case): {'': the table's note, column (lower case): its note}}: the column comments, the
    database's own dictionary table, and how its periods end. One connection; anything that fails is left out."""
    if source.kind == DataSource.KIND_MONGO:
        return {}
    found = {}

    def add(table, column, text):
        # A note filed under no table is about the whole database, as one filed under '*' (19 Nov 2026).
        table = str(table or '').strip() or '*'
        text = ' '.join(str(text or '').split())[:NOTE_CHARS]
        if not text or sum(len(v) for v in found.values()) >= NOTES_MAX:
            return
        entry = found.setdefault(str(table).lower(), {})
        key = str(column or '').lower()
        if text not in entry.get(key, ''):
            entry[key] = f"{entry[key]}; {text}" if entry.get(key) else text

    def name_of(t):
        return (_quote(source.kind, t['schema']) + '.' if t.get('schema') else '') + _quote(source.kind, t['name'])

    def first_rows(t, columns):
        listed = ', '.join(_quote(source.kind, c) for c in columns)
        return (f'SELECT TOP {SAMPLE_SCAN_ROWS} {listed} FROM {name_of(t)}' if source.kind == DataSource.KIND_MSSQL
                else f'SELECT {listed} FROM {name_of(t)} LIMIT {SAMPLE_SCAN_ROWS}')

    dictionary = dictionary_table(tables)
    periods = [(t, pair) for t in tables if t.get('kind', 'table') == 'table'
               for pair in period_pairs(t)][:PERIOD_TABLES]
    queries = _COMMENT_QUERIES.get(source.kind, ())
    if not (dictionary or periods or queries):
        return {}
    engine = None
    try:
        engine = _engine(source)
        with engine.connect() as conn:
            if source.kind == DataSource.KIND_MYSQL:
                _limit_mysql_time(conn)

            def read(sql):
                try:
                    return conn.execution_options(no_parameters=True).exec_driver_sql(sql).fetchall()
                except Exception:
                    conn.rollback()
                    return []

            for sql in queries:
                for table, column, text in read(sql):
                    add(table, column, text)
            if dictionary:
                t, table_col, column_col, text_col = dictionary
                for row in read(first_rows(t, [c for c in (table_col, column_col, text_col) if c])):
                    add(row[0], row[1] if column_col else '', row[-1])
            for t, (start, end) in periods:
                keys = [c for fk in t.get('fks') or [] for c in fk.get('columns') or [] if c not in (start, end)]
                best = ''
                for key in keys[:3]:
                    best = _period_note(read(first_rows(t, [key, start, end])), start, end)
                    if best:
                        break
                if best:
                    add(t['name'], end, best)
            conn.rollback()
    except Exception:
        logger.info('data analyst: notes not read for source %s', source.pk, exc_info=True)
    finally:
        if engine is not None:
            engine.dispose()
    return found


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
            if source.kind == DataSource.KIND_MSSQL:
                from . import mssql
                try:
                    return mssql.read_tables(raw, _table_entry, MAX_TABLES)
                finally:
                    raw.rollback()
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
            if source.kind == DataSource.KIND_MSSQL:
                from . import mssql
                row = conn.execution_options(no_parameters=True).exec_driver_sql(mssql.CAN_WRITE_SQL).first()
                conn.rollback()
                return bool(row[0]) if row and row[0] is not None else None
            grants = ' '.join(str(r[0]).upper() for r in conn.exec_driver_sql('SHOW GRANTS'))
            conn.rollback()
            return any(word in grants for word in ('ALL PRIVILEGES', 'INSERT', 'UPDATE', 'DELETE'))
    except Exception:
        return None
    finally:
        engine.dispose()
