"""The two checks every question passes before it touches a company's database.

1. Addresses (`resolve_public`): the host a company types is resolved first, and refused if it points anywhere that is
   not the public internet: a private, loopback, link-local or reserved address, or this server's own. Someone could
   otherwise type `db`, `redis` or `127.0.0.1` and read *our* database or queue through the agent. The connection then
   goes to the address that was checked, so a name can't point elsewhere between the check and the connection.
2. SQL (`check_sql`): the AI's query is parsed in the database's own dialect and must be exactly one SELECT (WITH,
   UNION and the like allowed), with nothing anywhere inside it that writes, changes structure, locks, or reaches
   outside the query (files, other servers, sleeping, sequences).

They are the first of three layers: the session is also read-only (connectors.py), and the company is asked for a
read-only database user.
"""
import ipaddress
import socket

import sqlglot
from django.conf import settings
from sqlglot import exp


class Refused(Exception):
    """Said to the person as it is: what was refused, and why."""


# ---- 1. addresses ---------------------------------------------------------------------------------------------------

def _own_addresses() -> set:
    raw = getattr(settings, 'DATA_ANALYST_SERVER_IP', '') or ''
    extra = getattr(settings, 'DATA_ANALYST_BLOCKED_IPS', '') or ''
    return {a.strip() for a in f'{raw},{extra}'.split(',') if a.strip()}


def resolve_public(host: str, port: int) -> str:
    """The public address `host` resolves to (IPv4 first), or Refused."""
    host = str(host or '').strip()
    if not host:
        raise Refused("Give the database's host name or address.")
    if not 0 < int(port or 0) < 65536:
        raise Refused('The port must be a number from 1 to 65535.')
    try:
        infos = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise Refused(f'"{host}" could not be found. Check the host name.')
    addresses = sorted({info[4][0].split('%')[0] for info in infos}, key=lambda a: (':' in a, a))
    if not addresses:
        raise Refused(f'"{host}" could not be found. Check the host name.')
    own = _own_addresses()
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or address in own:
            raise Refused(f'"{host}" points to {address}, which is not a public address. The database must be reachable '
                          'on the internet, with access allowed for our server only.')
    return addresses[0]


# ---- 2. SQL ---------------------------------------------------------------------------------------------------------

DIALECTS = {'postgres': 'postgres', 'mysql': 'mysql', 'sqlite': 'sqlite', 'mssql': 'tsql'}

#: Statements and clauses that never belong in a question's query, wherever they appear (a WITH can hold a DELETE).
_FORBIDDEN = tuple(getattr(exp, name) for name in (
    'Insert', 'Update', 'Delete', 'Merge', 'Create', 'Drop', 'Alter', 'TruncateTable', 'Command', 'Into', 'Lock',
    'Transaction', 'Commit', 'Rollback', 'Use', 'Copy', 'LoadData', 'Grant', 'Set', 'Pragma', 'Attach', 'Detach',
    'Analyze', 'Kill', 'Cache', 'Uncache', 'Refresh') if hasattr(exp, name))

#: Functions that read files, reach other servers, run commands, wait, take locks or change sequences.
_FORBIDDEN_FUNCTIONS = {
    'pg_sleep', 'pg_sleep_for', 'pg_sleep_until', 'pg_read_file', 'pg_read_binary_file', 'pg_ls_dir', 'pg_stat_file',
    'pg_ls_logdir', 'pg_ls_waldir', 'lo_import', 'lo_export', 'lo_get', 'lo_put', 'lo_unlink', 'lo_open', 'lo_create',
    'dblink', 'dblink_exec', 'dblink_connect', 'dblink_send_query', 'pg_terminate_backend', 'pg_cancel_backend',
    'pg_reload_conf', 'pg_rotate_logfile', 'set_config', 'nextval', 'setval', 'pg_advisory_lock',
    'pg_advisory_xact_lock', 'pg_try_advisory_lock', 'query_to_xml', 'query_to_json', 'pg_logical_emit_message',
    'sleep', 'benchmark', 'load_file', 'get_lock', 'release_lock', 'master_pos_wait', 'source_pos_wait', 'sys_exec',
    'sys_eval', 'xp_cmdshell', 'openrowset', 'opendatasource', 'openquery', 'openxml',
    'load_extension', 'readfile', 'writefile', 'edit', 'fts3_tokenizer',
}


def _function_name(node) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name or '').lower()
    try:
        return str(node.sql_name() or '').lower()
    except Exception:  # pragma: no cover
        return ''


def check_sql(sql: str, kind: str) -> str:
    """`sql` cleaned of a trailing semicolon, if it is one read-only SELECT for this kind of database; else Refused."""
    text = str(sql or '').strip()
    while text.endswith(';'):
        text = text[:-1].rstrip()
    if not text:
        raise Refused('There was no query to run.')
    dialect = DIALECTS.get(kind, kind)
    try:
        statements = [s for s in sqlglot.parse(text, read=dialect) if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise Refused(f'The query could not be read: {str(exc).splitlines()[0][:200]}')
    if len(statements) != 1:
        raise Refused('Only one query is run at a time.')
    root = statements[0]
    if not isinstance(root, (exp.Select, exp.SetOperation, exp.Subquery)):
        raise Refused('Only queries that read (SELECT) are run.')
    for node in root.walk():
        if isinstance(node, _FORBIDDEN):
            raise Refused(f'Only reading is allowed: the query contains {node.key.upper()}.')
        if isinstance(node, (exp.Func, exp.Anonymous)) and _function_name(node) in _FORBIDDEN_FUNCTIONS:
            raise Refused(f'The function {_function_name(node)}() is not allowed.')
    return text
