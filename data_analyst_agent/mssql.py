"""Microsoft SQL Server for the AI Data Analyst (12 Nov 2026): the connection strings people paste, the ODBC connection
our server opens, and reading the tables. Questions are SQL in SQL Server's dialect (TOP, [names]), checked by
guards.check_sql like every SQL database.

Read-only, in three layers as for the others:
  1. guards.check_sql (T-SQL): one SELECT; no EXEC, INTO, OPENROWSET/OPENQUERY/OPENDATASOURCE, file-reading functions
     or four-part names (a linked server);
  2. the connection: ApplicationIntent=ReadOnly, a query time limit, and every transaction rolled back;
  3. the company is asked for a user in db_datareader only, and the test says when the user could write.

Addresses: every address the host name resolves to must be public (guards.resolve_public). The connection uses the
name, as SQL Server's certificate and Azure's gateway need it; the name is checked again on every connection.
The driver is Microsoft's ODBC Driver 18, already in the server image (msodbcsql18, for DB_ENGINE=mssql).
"""
import re
from urllib.parse import parse_qs, unquote, urlsplit

from .guards import Refused

DRIVER = 'ODBC Driver 18 for SQL Server'
DEFAULT_PORT = 1433
_HOST = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$')
_TRUE = {'true', 'yes', '1', 'mandatory', 'strict'}
_FALSE = {'false', 'no', '0', 'optional'}
#: Keys of an ADO.NET / ODBC / JDBC connection string, lower-case, without spaces, as the field they fill.
_KEYS = {
    'server': 'server', 'datasource': 'server', 'address': 'server', 'addr': 'server', 'networkaddress': 'server',
    'servername': 'server',
    'database': 'database', 'initialcatalog': 'database', 'databasename': 'database',
    'userid': 'username', 'uid': 'username', 'user': 'username', 'username': 'username',
    'password': 'password', 'pwd': 'password',
    'encrypt': 'encrypt', 'trustservercertificate': 'trust', 'portnumber': 'port', 'port': 'port',
}


def looks_like_sql_server(text: str) -> bool:
    lowered = (text or '').strip().lower()
    if lowered.startswith(('jdbc:sqlserver://', 'sqlserver://', 'mssql://', 'mssql+pyodbc://', 'mssql+pymssql://')):
        return True
    return bool(re.search(r'(?:^|;)\s*(?:server|data\s+source|address|addr|network\s+address)\s*=', lowered))


def _pairs(text):
    """key=value;key={va;lue};key="value" as {normalised key: value}."""
    out, i, n = {}, 0, len(text)
    while i < n:
        eq = text.find('=', i)
        if eq < 0:
            break
        key = re.sub(r'\s+', '', text[i:eq]).lower()
        j = eq + 1
        while j < n and text[j] == ' ':
            j += 1
        if j < n and text[j] in '{"\'':
            close = {'{': '}', '"': '"', "'": "'"}[text[j]]
            k, value = j + 1, []
            while k < n:
                if text[k] == close and text[k + 1:k + 2] == close:      # doubled: one of it
                    value.append(close)
                    k += 2
                    continue
                if text[k] == close:
                    break
                value.append(text[k])
                k += 1
            out[key] = ''.join(value)
            end = text.find(';', k)
            i = n if end < 0 else end + 1
        else:
            end = text.find(';', j)
            out[key] = (text[j:] if end < 0 else text[j:end]).strip()
            i = n if end < 0 else end + 1
    return out


def _server(value: str):
    """'tcp:host,1433', 'host\\instance', 'host:1433' or '[::1],1433' as (host, port or None)."""
    value = re.sub(r'^(?:tcp|np|lpc|admin):', '', (value or '').strip(), flags=re.I)
    host, port = value, None
    if ',' in value:
        host, port = value.rsplit(',', 1)
    elif value.count(':') == 1 and not value.startswith('['):
        host, port = value.split(':')
    host = host.strip().strip('[]')
    if '\\' in host:
        host, _instance = host.split('\\', 1)
        if not port:
            raise Refused('A named instance (server\\instance) needs its port here, e.g. server,1433: our server cannot '
                          'ask SQL Server Browser for it.')
    port = str(port or '').strip()
    if port and not port.isdigit():
        raise Refused(f'"{port}" is not a port number.')
    return host, (int(port) if port else None)


def parse_connection_string(text: str) -> dict:
    """An ADO.NET (Azure portal), ODBC, JDBC or URL connection string as the source's fields. Nothing is connected."""
    text = (text or '').strip()
    lowered = text.lower()
    fields = {}
    if lowered.startswith('jdbc:sqlserver://'):
        rest = text[len('jdbc:sqlserver://'):]
        head, _, tail = rest.partition(';')
        host, port = _server(head.replace(':', ',', 1) if head.count(':') == 1 else head)
        fields.update(_pairs(tail))
        fields['server'] = f'{host},{port}' if port else host
    elif re.match(r'^(?:sqlserver|mssql(?:\+\w+)?)://', lowered):
        url = urlsplit(text)
        user, _, password = url.netloc.rpartition('@')[0].partition(':') if '@' in url.netloc else ('', '', '')
        hostport = url.netloc.rpartition('@')[2]
        fields.update({'server': hostport.replace(':', ',') if hostport.count(':') == 1 else hostport,
                       'database': unquote(url.path.lstrip('/')), 'username': unquote(user),
                       'password': unquote(password)})
        fields.update({re.sub(r'\s+', '', k).lower(): v[-1] for k, v in parse_qs(url.query).items()})
    else:
        fields = _pairs(text)
    found = {}
    for key, value in fields.items():
        name = _KEYS.get(key)
        if name and value is not None:
            found[name] = value
    if not found.get('server'):
        raise Refused('The connection string has no server (Server=... or Data Source=...).')
    host, port = _server(found['server'])
    if found.get('port') and not port:
        port = int(found['port']) if str(found['port']).isdigit() else None
    encrypt = str(found.get('encrypt', 'true')).strip().lower()
    trust = str(found.get('trust', 'false')).strip().lower()
    return {
        'host': host[:255], 'port': port, 'database': (found.get('database') or '')[:255],
        'username': (found.get('username') or '')[:255], 'password': found.get('password') or '',
        # ODBC Driver 18 encrypts unless told not to; a string saying Encrypt=False keeps it off.
        'use_ssl': encrypt not in _FALSE,
        'options': {'trust_server_certificate': True} if trust in _TRUE else {},
    }


def check_host(host: str) -> str:
    """A host name or address to put in the ODBC string: nothing that could add a keyword (;, {, =)."""
    host = (host or '').strip()
    if not _HOST.match(host):
        raise Refused(f'"{host}" is not a host name. Give the server\'s name or address only.')
    return host


def _odbc_value(value) -> str:
    """A value in an ODBC connection string, braced so ; and = in it are plain characters."""
    return '{' + str(value or '').replace('}', '}}') + '}'


def odbc_connection_string(source) -> str:
    """The ODBC string for one connection. The host is checked (check_host), every other value braced. The login time
    limit is pyodbc's `timeout`, not a keyword here."""
    options = source.options or {}
    parts = [
        f'DRIVER={{{DRIVER}}}',
        f'SERVER=tcp:{check_host(source.host)},{int(source.port or DEFAULT_PORT)}',
        f'DATABASE={_odbc_value(source.database)}',
        f'UID={_odbc_value(source.username)}',
        f'PWD={_odbc_value(source.get_password())}',
        f'Encrypt={"yes" if source.use_ssl else "no"}',
        f'TrustServerCertificate={"yes" if options.get("trust_server_certificate") else "no"}',
        'ApplicationIntent=ReadOnly',
    ]
    return ';'.join(parts) + ';'


# ---- the structure: INFORMATION_SCHEMA in capitals (a case-sensitive database collation needs them) --------------

TABLES_SQL = ("SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
              "WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA') ORDER BY TABLE_SCHEMA, TABLE_NAME")
COLUMNS_SQL = ("SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
               "WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA') ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION")
PRIMARY_KEYS_SQL = (
    "SELECT KCU.TABLE_SCHEMA, KCU.TABLE_NAME, KCU.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC "
    "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KCU ON KCU.CONSTRAINT_NAME = TC.CONSTRAINT_NAME "
    "AND KCU.TABLE_SCHEMA = TC.TABLE_SCHEMA AND KCU.TABLE_NAME = TC.TABLE_NAME "
    "WHERE TC.CONSTRAINT_TYPE = 'PRIMARY KEY'")
# INFORMATION_SCHEMA has no referenced column for a foreign key in SQL Server: the catalog views do.
FOREIGN_KEYS_SQL = (
    "SELECT OBJECT_SCHEMA_NAME(FKC.PARENT_OBJECT_ID), OBJECT_NAME(FKC.PARENT_OBJECT_ID), PC.NAME, "
    "OBJECT_NAME(FKC.REFERENCED_OBJECT_ID), RC.NAME FROM SYS.FOREIGN_KEY_COLUMNS FKC "
    "JOIN SYS.COLUMNS PC ON PC.OBJECT_ID = FKC.PARENT_OBJECT_ID AND PC.COLUMN_ID = FKC.PARENT_COLUMN_ID "
    "JOIN SYS.COLUMNS RC ON RC.OBJECT_ID = FKC.REFERENCED_OBJECT_ID AND RC.COLUMN_ID = FKC.REFERENCED_COLUMN_ID")
# Could the user change data? Roles, database-wide rights, or a right on any one table.
CAN_WRITE_SQL = (
    "SELECT CASE WHEN IS_SRVROLEMEMBER('sysadmin') = 1 OR IS_ROLEMEMBER('db_owner') = 1 "
    "OR IS_ROLEMEMBER('db_datawriter') = 1 OR IS_ROLEMEMBER('db_ddladmin') = 1 "
    "OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT') = 1 OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'UPDATE') = 1 "
    "OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'DELETE') = 1 OR HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER') = 1 "
    "OR EXISTS (SELECT 1 FROM SYS.TABLES T WHERE HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(T.SCHEMA_ID)) + '.' + "
    "QUOTENAME(T.NAME), 'OBJECT', 'INSERT') = 1 OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(T.SCHEMA_ID)) + '.' + "
    "QUOTENAME(T.NAME), 'OBJECT', 'UPDATE') = 1 OR HAS_PERMS_BY_NAME(QUOTENAME(SCHEMA_NAME(T.SCHEMA_ID)) + '.' + "
    "QUOTENAME(T.NAME), 'OBJECT', 'DELETE') = 1) THEN 1 ELSE 0 END")


def read_tables(conn, table_entry, max_tables) -> list:
    """Tables and views, their columns, types, primary keys and foreign keys, from one connection."""
    def rows(sql):
        try:
            return list(conn.execution_options(no_parameters=True).exec_driver_sql(sql))
        except Exception:
            return []

    tables = rows(TABLES_SQL)
    tables.sort(key=lambda t: (t[0] != 'dbo', t[0], t[1]))
    tables = tables[:max_tables]
    wanted = {(t[0], t[1]) for t in tables}
    columns = {}
    for schema, table, column, data_type, nullable in rows(COLUMNS_SQL):
        if (schema, table) in wanted:
            columns.setdefault((schema, table), []).append({'name': column, 'type': data_type,
                                                            'nullable': str(nullable).upper() == 'YES'})
    pks = {}
    for schema, table, column in rows(PRIMARY_KEYS_SQL):
        pks.setdefault((schema, table), set()).add(column)
    fks = {}
    for schema, table, column, ref_table, ref_column in rows(FOREIGN_KEYS_SQL):
        fks.setdefault((schema, table), []).append({'constrained_columns': [column], 'referred_table': ref_table,
                                                    'referred_columns': [ref_column]})
    out = []
    for schema, table, table_type in tables:
        cols = [dict(c, pk=c['name'] in pks.get((schema, table), set())) for c in columns.get((schema, table), [])]
        if not cols:
            continue
        kind = 'view' if 'VIEW' in str(table_type).upper() else 'table'
        out.append(table_entry(table, schema, 'dbo', kind, cols, pks.get((schema, table), set()),
                               fks.get((schema, table))))
    return out


def clean_error(text: str) -> str:
    """pyodbc's "('28000', "[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed ... (18456)
    (SQLDriverConnect)")" as the database's own sentence."""
    found = re.findall(r'\]\s*([^\[\]]+?)\s*(?:\(\d+\)\s*)?(?:\(SQL\w+\))?\s*(?:;|"\)|\'\)|$)', text or '')
    found = [f.strip().rstrip('.').strip() for f in found if f.strip().rstrip('.').strip()]
    return (found[-1] + '.') if found else (text or '').strip()
