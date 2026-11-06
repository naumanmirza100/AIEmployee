"""A .sql dump read into a private SQLite copy (7 Nov 2026), so it is asked exactly like an uploaded SQLite file.

The dump's statements are never run. It is read statement by statement, as text, and only two kinds are used:
  * CREATE TABLE: parsed (sqlglot, in the dump's dialect) into a plain SQLite table: each column with its declared type
    name (VARCHAR(255), DECIMAL(10,2), DATETIME), the primary key and the foreign keys. Nothing else of it is kept
    (engines, character sets, defaults, checks, indexes);
  * the rows: INSERT ... VALUES (mysqldump, phpMyAdmin, pg_dump --inserts, sqlite3 .dump, SQL Server scripts) and
    COPY ... FROM stdin (pg_dump's own format). Their values are read and inserted with parameters.
Keys added afterwards by ALTER TABLE (pg_dump, phpMyAdmin) are kept for the structure the AI sees (`with_keys`).
Everything else is skipped and counted: settings, locks, indexes, views, functions, triggers, grants, sequences.

Dialects: MySQL / MariaDB, PostgreSQL, SQLite and SQL Server (GO between batches), told apart from the dump's first
part. A .sql.gz is read as it is. Nothing is held in memory beyond one statement.
"""
import gzip
import io
import re
import sqlite3
import time
from collections import Counter

import sqlglot
from sqlglot import exp

from .guards import Refused

GZIP_MAGIC = b'\x1f\x8b'
HEAD_BYTES = 256 * 1024
INLINE_BYTES = 5 * 1024 * 1024     # a smaller dump loads while the upload waits; a bigger one in the background
BATCH = 2000                       # rows inserted at a time
MAX_PROBLEMS = 20
LABELS = {'mysql': 'MySQL / MariaDB', 'postgres': 'PostgreSQL', 'sqlite': 'SQLite', 'tsql': 'SQL Server'}


class _Unreadable(Exception):
    """The quick reading of a VALUES list met something it doesn't know (a function call, an expression)."""


# ---- the file -------------------------------------------------------------------------------------------------------

def _open_binary(path):
    with open(path, 'rb') as fh:
        magic = fh.read(2)
    return gzip.open(path, 'rb') if magic == GZIP_MAGIC else open(path, 'rb')


def open_text(path):
    return io.TextIOWrapper(_open_binary(path), encoding='utf-8', errors='replace', newline='')


def read_head(path) -> str:
    try:
        with _open_binary(path) as fh:
            return fh.read(HEAD_BYTES).decode('utf-8', 'replace')
    except (OSError, EOFError):
        return ''


_HAS_TABLES = re.compile(r'\bCREATE\s+(?:TEMPORARY\s+|UNLOGGED\s+)?TABLE\b|\bINSERT\s+(?:\w+\s+)*INTO\b'
                         r'|\bCOPY\s+\S+[^;]*\bFROM\s+stdin\b', re.I)


def sniff(head: str):
    """The dump's dialect ('mysql', 'postgres', 'sqlite', 'tsql'), or None when it holds no tables or rows."""
    if not head or '\x00' in head[:4096] or not _HAS_TABLES.search(head):
        return None
    upper = head.upper()
    if ('POSTGRESQL DATABASE DUMP' in upper or re.search(r'FROM\s+stdin;', head, re.I) or 'SET SEARCH_PATH' in upper
            or 'PG_CATALOG.' in upper):
        return 'postgres'
    if re.search(r'^\s*GO\s*$', head, re.M) or 'SET ANSI_NULLS' in upper or '[DBO].' in upper:
        return 'tsql'
    if ('MYSQL DUMP' in upper or 'MARIADB DUMP' in upper or 'PHPMYADMIN' in upper or 'ENGINE=' in upper
            or '/*!' in head or '`' in head):
        return 'mysql'
    if 'PRAGMA FOREIGN_KEYS' in upper or 'BEGIN TRANSACTION;' in upper:
        return 'sqlite'
    return 'postgres' if '"' in head else 'mysql'


# ---- statements -----------------------------------------------------------------------------------------------------

_COPY = re.compile(r'^COPY\s+(?P<table>.+?)\s*(?:\((?P<cols>[^)]*)\))?\s+FROM\s+stdin\b', re.I | re.S)
#: SQL Server scripts put no semicolons between the statements of a GO batch: a line starting one of these ends the last.
_TSQL_STARTS = re.compile(r'\s*(INSERT|CREATE|ALTER|SET|DROP|USE|PRINT|EXEC|EXECUTE|DECLARE|IF|BEGIN|END|GRANT|DELETE|'
                          r'UPDATE|TRUNCATE|DBCC)\b', re.I)


def _scanner(dialect, delimiter=';'):
    opens = ["'", '"']
    if dialect in ('mysql', 'sqlite'):
        opens.append('`')
    if dialect in ('sqlite', 'tsql'):
        opens.append(r'\[')
    dollar = [r'\$[A-Za-z_][A-Za-z_0-9]*\$', r'\$\$'] if dialect == 'postgres' else []
    return re.compile('|'.join(opens + ['--', r'/\*', re.escape(delimiter)] + dollar))


_DELIMITER = re.compile(r'\s*DELIMITER\s+(\S+)\s*$', re.I)


def _find_close(line, i, state):
    """Where the quoted text open in `state` ends on this line (just after it), or -1 when it goes on."""
    if state.startswith('$'):
        k = line.find(state, i)
        return -1 if k < 0 else k + len(state)
    quote, backslash, n = state[-1], state.startswith('\\'), len(line)
    while True:
        k = line.find(quote, i)
        if backslash:
            b = line.find('\\', i)
            if 0 <= b and (k < 0 or b < k):
                i = b + 2                       # the next character is escaped
                if i >= n:
                    return -1
                continue
        if k < 0:
            return -1
        if k + 1 < n and line[k + 1] == quote:  # doubled: still inside
            i = k + 2
            continue
        return k + 1


def statements(lines, dialect):
    """('sql', text) for each statement, comments left out; after a COPY ... FROM stdin, ('row', line) for each of its
    data lines, then ('copy_end', None)."""
    delimiter = ';'
    normal = _scanner(dialect)
    backslash_strings = dialect == 'mysql'
    buf, state, copying = [], None, False
    for line in lines:
        if state is None and not copying and not ''.join(buf).strip():
            # A psql meta-command (\restrict, \connect: pg_dump 17.6 writes them) is not SQL: the line is dropped.
            if dialect == 'postgres' and line.lstrip().startswith('\\'):
                continue
            # MySQL's DELIMITER ;; keeps a procedure's or trigger's body, semicolons and all, one statement.
            change = _DELIMITER.match(line) if dialect == 'mysql' else None
            if change:
                delimiter = change.group(1)
                normal = _scanner(dialect, delimiter)
                continue
        if copying:
            data = line.rstrip('\r\n')
            if data == '\\.':
                copying = False
                yield 'copy_end', None
            else:
                yield 'row', data
            continue
        if dialect == 'tsql' and state is None and (line.strip().upper() == 'GO' or _TSQL_STARTS.match(line)):
            text = ''.join(buf).strip()
            buf = []
            if text:
                yield 'sql', text
            if line.strip().upper() == 'GO':
                continue
        i, n = 0, len(line)
        while i < n:
            if state == '*':
                end = line.find('*/', i)
                if end < 0:
                    break
                i, state = end + 2, None
                continue
            if state is not None:
                j = _find_close(line, i, state)
                if j < 0:
                    buf.append(line[i:])
                    break
                buf.append(line[i:j])
                i, state = j, None
                continue
            m = normal.search(line, i)
            if not m:
                buf.append(line[i:])
                break
            token, start = m.group(0), m.start()
            if token == '--':
                buf.append(line[i:start])
                buf.append('\n')
                break
            if token == '/*':
                buf.append(line[i:start])
                buf.append(' ')
                i, state = m.end(), '*'
                continue
            if token == delimiter:
                buf.append(line[i:start])
                text = ''.join(buf).strip()
                buf, i = [], m.end()
                if text:
                    yield 'sql', text
                    if dialect == 'postgres' and _COPY.match(text):
                        copying = True
                        break
                continue
            buf.append(line[i:m.end()])
            if token == "'":
                e_string = (dialect == 'postgres' and start > 0 and line[start - 1] in 'eE'
                            and (start < 2 or not (line[start - 2].isalnum() or line[start - 2] == '_')))
                state = "\\'" if backslash_strings or e_string else "'"
            elif token == '[':
                state = ']'
            elif token == '"' and backslash_strings:
                state = '\\"'
            else:
                state = token                   # " ` or a $tag$
            i = m.end()
    text = ''.join(buf).strip()
    if text and not copying:
        yield 'sql', text


# ---- names ----------------------------------------------------------------------------------------------------------

_NAME_PART = re.compile(r'`([^`]+)`|"((?:[^"]|"")+)"|\[([^\]]+)\]|([^\s.`"\[(),]+)')


def _split_name(text):
    """'`shop`.`orders`', 'public.orders', '[dbo].[Orders]' as (schema, name)."""
    parts = [next(g for g in m.groups() if g is not None).replace('""', '"') for m in _NAME_PART.finditer(text or '')]
    if not parts:
        return '', ''
    return (parts[-2] if len(parts) > 1 else ''), parts[-1]


def _sqlite_name(schema, name):
    if schema and schema.lower() not in ('public', 'dbo', 'main'):
        return f'{schema}_{name}'
    return name


def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


def _columns_list(text):
    """'`a`, `b`' or '[Id] ASC, [Day] DESC' as ['a', 'b'] / ['Id', 'Day']."""
    names = []
    for part in (text or '').split(','):
        part = re.sub(r'\s+(?:ASC|DESC)\s*$', '', part.strip(), flags=re.I)
        if part:
            names.append(_split_name(part)[1])
    return names


# ---- CREATE TABLE ---------------------------------------------------------------------------------------------------

def _ident(node):
    if isinstance(node, exp.Identifier):
        return node.name
    found = node.find(exp.Identifier)
    return found.name if found else node.sql()


def _type_name(kind):
    """The declared type as SQLite keeps it: its name and its numbers (VARCHAR(255), DECIMAL(10,2)), never words it
    can't read (CHARACTER SET, enum values)."""
    if kind is None:
        return ''
    name = kind.this.name if isinstance(kind.this, exp.DataType.Type) else 'TEXT'
    if name in ('USERDEFINED', 'UNKNOWN'):
        return 'TEXT'
    numbers = [p.sql() for p in kind.expressions if re.fullmatch(r'\d+', p.sql() or '')]
    return f"{name}({','.join(numbers)})" if numbers else name


def _reference(ref):
    target = ref.this
    if isinstance(target, exp.Schema):
        table = target.this
        return _sqlite_name(table.args.get('db') and table.args['db'].name or '', table.name), \
            [_ident(e) for e in target.expressions]
    return _sqlite_name(target.args.get('db') and target.args['db'].name or '', target.name), []


def parse_create(text, dialect):
    """(schema, name, [(column, type)], primary key columns, [(columns, table, columns)]) of a CREATE TABLE."""
    try:
        tree = sqlglot.parse_one(text, read=dialect)
    except Exception:
        tree = None
    if isinstance(tree, exp.Create) and isinstance(tree.this, exp.Schema):
        table = tree.this.this
        schema = table.args.get('db').name if table.args.get('db') else ''
        columns, pk, fks = [], [], []
        for item in tree.this.expressions:
            if isinstance(item, exp.ColumnDef):
                columns.append((item.name, _type_name(item.args.get('kind'))))
                for constraint in item.args.get('constraints') or []:
                    kind = constraint.args.get('kind')
                    if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                        pk.append(item.name)
                    elif isinstance(kind, exp.Reference):
                        fks.append(([item.name], *_reference(kind)))
                continue
            for part in (item.expressions if isinstance(item, exp.Constraint) else [item]):
                if isinstance(part, exp.PrimaryKey):
                    pk.extend(_ident(e) for e in part.expressions)
                elif isinstance(part, exp.ForeignKey) and part.args.get('reference'):
                    fks.append(([_ident(e) for e in part.expressions], *_reference(part.args['reference'])))
        if columns:
            if not pk:      # SQL Server's PRIMARY KEY CLUSTERED (...) and the like, which sqlglot passes over
                key = re.search(r'PRIMARY\s+KEY\s+(?:CLUSTERED\s+|NONCLUSTERED\s+)?\(([^)]*)\)', text, re.I)
                if key:
                    pk = _columns_list(key.group(1))
            return schema, table.name, columns, pk, fks
    return _parse_create_by_hand(text)


_CREATE_HEAD = re.compile(r'^CREATE\s+(?:TEMPORARY\s+|UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>.+?)\s*\(',
                          re.I | re.S)


def _top_level_parts(body):
    parts, depth, start, quote = [], 0, 0, None
    for i, ch in enumerate(body):
        if quote:
            if ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_create_by_hand(text):
    """When sqlglot can't read a CREATE TABLE: its columns and keys from the text, line by line."""
    head = _CREATE_HEAD.match(text)
    if not head:
        raise ValueError('not a CREATE TABLE')
    schema, name = _split_name(head.group('name'))
    body = text[head.end():text.rfind(')')]
    columns, pk, fks = [], [], []
    for part in _top_level_parts(body):
        upper = part.upper()
        key = re.match(r'(?:CONSTRAINT\s+\S+\s+)?(PRIMARY\s+KEY|FOREIGN\s+KEY)\s*\(([^)]*)\)(.*)', part, re.I | re.S)
        if key:
            cols = _columns_list(key.group(2))
            if key.group(1).upper().startswith('PRIMARY'):
                pk.extend(cols)
            else:
                ref = re.search(r'REFERENCES\s+(\S+?)\s*\(([^)]*)\)', key.group(3), re.I)
                if ref:
                    fks.append((cols, _sqlite_name(*_split_name(ref.group(1))), _columns_list(ref.group(2))))
            continue
        if re.match(r'(KEY|INDEX|UNIQUE|CHECK|CONSTRAINT|FULLTEXT|SPATIAL|EXCLUDE|LIKE)\b', upper):
            continue
        m = _NAME_PART.match(part)
        if not m:
            continue
        column = next(g for g in m.groups() if g is not None)
        typed = re.match(r'\s*([A-Za-z][A-Za-z0-9_ ]*?)\s*(\(\s*\d+(?:\s*,\s*\d+)?\s*\))?(?:\s|$|\[)', part[m.end():])
        columns.append((column, (typed.group(1).upper() + (typed.group(2) or '').replace(' ', '')) if typed else ''))
        if re.search(r'\bPRIMARY\s+KEY\b', upper):
            pk.append(column)
    if not columns:
        raise ValueError('no columns')
    return schema, name, columns, pk, fks


# ---- values ---------------------------------------------------------------------------------------------------------

_INSERT = re.compile(
    r'^(?:INSERT|REPLACE)\s+(?:(?:LOW_PRIORITY|DELAYED|HIGH_PRIORITY|IGNORE)\s+)*(?:OR\s+\w+\s+)?(?:INTO\s+)?'
    r'(?P<table>(?:`[^`]+`|"(?:[^"]|"")+"|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:`[^`]+`|"(?:[^"]|"")+"|\[[^\]]+\]|[\w$]+))*)'
    r'\s*(?:\((?P<cols>[^)]*)\))?\s*VALUES\s*', re.I | re.S)
_NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)')
_WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
_SPACE = re.compile(r'\s*')
_BACKSLASH_STRING = re.compile(r"'((?:[^'\\]|\\.|'')*)'", re.S)
_PLAIN_STRING = re.compile(r"'((?:[^']|'')*)'", re.S)
_CAST = re.compile(r'(?:\s*::\s*[A-Za-z_][\w ."]*(?:\([^)]*\))?(?:\[\])*)+')
_MYSQL_ESCAPES = {'0': '\x00', 'b': '\b', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a'}
_PG_ESCAPES = {'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t', 'v': '\v'}


def _mysql_unescape(text):
    def one(m):
        ch = m.group(1)
        if ch in '%_':
            return '\\' + ch
        return _MYSQL_ESCAPES.get(ch, ch)
    return re.sub(r'\\(.)', one, text.replace("''", "'"), flags=re.S)


def _pg_unescape(text):
    """E'...' strings and COPY's text format: \\n, \\t, octal \\101, hex \\x41, unicode \\u0041."""
    def one(m):
        seq = m.group(1)
        if seq[0] in _PG_ESCAPES:
            return _PG_ESCAPES[seq[0]]
        if seq[0] in '01234567':
            return chr(int(seq, 8) & 0xFF)
        if seq[0] == 'x':
            return chr(int(seq[1:], 16))
        if seq[0] in 'uU':
            return chr(int(seq[1:], 16))
        return seq
    return re.sub(r'\\([0-7]{1,3}|x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)', one, text, flags=re.S)


def _number(text):
    if re.fullmatch(r'[-+]?\d+', text):
        value = int(text)
        return value if -2 ** 63 <= value < 2 ** 63 else text
    return float(text)


class _ValueReader:
    """Reads the tuples after VALUES quickly, for the literals dumps write. Anything else raises _Unreadable."""

    def __init__(self, text, dialect):
        self.text, self.dialect = text, dialect

    def tuples(self, i):
        text, n = self.text, len(self.text)
        while True:
            i = _SPACE.match(text, i).end()
            if i >= n:
                return
            if text[i] == ',':
                i += 1
                continue
            if text[i] != '(':
                return                      # ON DUPLICATE KEY UPDATE, RETURNING ... after the rows
            i += 1
            row = []
            while True:
                i = _SPACE.match(text, i).end()
                value, i = self.value(i)
                row.append(value)
                i = _SPACE.match(text, i).end()
                if i < n and text[i] == ',':
                    i += 1
                    continue
                if i < n and text[i] == ')':
                    i += 1
                    break
                raise _Unreadable()
            yield row

    def _string(self, i, backslash):
        m = (_BACKSLASH_STRING if backslash else _PLAIN_STRING).match(self.text, i)
        if not m:
            raise _Unreadable()
        raw = m.group(1)
        if backslash:
            value = _mysql_unescape(raw) if self.dialect == 'mysql' else _pg_unescape(raw.replace("''", "'"))
        else:
            value = raw.replace("''", "'")
        return value, self._skip_cast(m.end())

    def _skip_cast(self, i):
        m = _CAST.match(self.text, i) if self.dialect == 'postgres' else None
        return m.end() if m and m.end() > i else i

    def value(self, i):
        text = self.text
        if i >= len(text):
            raise _Unreadable()
        ch = text[i]
        if ch == "'":
            return self._string(i, self.dialect == 'mysql')
        if ch in 'eE' and text[i + 1:i + 2] == "'" and self.dialect == 'postgres':
            return self._string(i + 1, True)
        if ch in 'nN' and text[i + 1:i + 2] == "'":
            return self._string(i + 1, self.dialect == 'mysql')
        if ch in 'xX' and text[i + 1:i + 2] == "'":
            m = re.compile(r"'([0-9A-Fa-f]*)'").match(text, i + 1)
            if not m:
                raise _Unreadable()
            return bytes.fromhex(m.group(1)), m.end()
        if ch == '0' and text[i + 1:i + 2] in ('x', 'X') and self.dialect != 'postgres':
            m = re.compile(r'0[xX]([0-9A-Fa-f]*)').match(text, i)
            digits = m.group(1)
            return bytes.fromhex(digits if len(digits) % 2 == 0 else '0' + digits), m.end()
        if ch.isdigit() or ch in '+-.':
            m = _NUMBER.match(text, i)
            if not m:
                raise _Unreadable()
            return _number(m.group(0)), self._skip_cast(m.end())
        if ch == '_' or ch.isalpha():
            m = _WORD.match(text, i)
            word, end = m.group(0), m.end()
            upper = word.upper()
            if upper == 'NULL' or upper == 'DEFAULT':
                return None, self._skip_cast(end)
            if upper == 'TRUE':
                return 1, self._skip_cast(end)
            if upper == 'FALSE':
                return 0, self._skip_cast(end)
            if word.startswith('_'):        # a character set before a string: _utf8mb4'..', _binary '..'
                j = _SPACE.match(text, end).end()
                if text[j:j + 1] == "'":
                    value, k = self._string(j, self.dialect == 'mysql')
                    return (value.encode('latin-1', 'replace') if upper == '_BINARY' else value), k
        raise _Unreadable()


def _literal(node):
    """A sqlglot value as Python, for a VALUES list the quick reader couldn't read."""
    if isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.Boolean):
        return 1 if node.this else 0
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else _number(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal) and not node.this.is_string:
        value = _number(node.this.this)
        return -value if not isinstance(value, str) else '-' + value
    if isinstance(node, (exp.Cast, exp.TryCast)):
        return _literal(node.this)
    if isinstance(node, exp.HexString):
        return bytes.fromhex(node.this if len(node.this) % 2 == 0 else '0' + node.this)
    return node.sql()


def parse_insert(text, dialect):
    """(schema, name, [columns] or None, [rows]) of an INSERT ... VALUES."""
    head = _INSERT.match(text)
    if head:
        schema, name = _split_name(head.group('table'))
        columns = _columns_list(head.group('cols')) if head.group('cols') else None
        try:
            return schema, name, columns, list(_ValueReader(text, dialect).tuples(head.end()))
        except _Unreadable:
            pass
    tree = sqlglot.parse_one(text, read=dialect)
    if not isinstance(tree, exp.Insert):
        raise ValueError('not an INSERT')
    target = tree.this
    table = target.this if isinstance(target, exp.Schema) else target
    columns = [_ident(e) for e in target.expressions] if isinstance(target, exp.Schema) else None
    values = tree.expression
    if not isinstance(values, exp.Values):
        raise ValueError('an INSERT ... SELECT')
    rows = [[_literal(v) for v in (row.expressions if isinstance(row, exp.Tuple) else [row])]
            for row in values.expressions]
    schema = table.args.get('db').name if table.args.get('db') else ''
    return schema, table.name, columns, rows


_TRUE, _FALSE = {'t', 'true', 'y', 'yes', '1', 'on'}, {'f', 'false', 'n', 'no', '0', 'off'}


def _typed(rows, types):
    """Values as their declared types say: a boolean's t/f as 1/0, a bytea's \\x... text as bytes (pg's COPY writes both
    as text). Nothing else is changed."""
    bools = [n for n, t in enumerate(types) if t.startswith('BOOL')]
    binary = [n for n, t in enumerate(types) if t in ('VARBINARY', 'BINARY', 'BLOB', 'BYTEA') or t.startswith('VARBINARY')]
    if not bools and not binary:
        return rows
    out = []
    for row in rows:
        row = list(row)
        for n in bools:
            if n < len(row) and isinstance(row[n], str):
                word = row[n].strip().lower()
                row[n] = 1 if word in _TRUE else 0 if word in _FALSE else row[n]
        for n in binary:
            if n < len(row) and isinstance(row[n], str) and row[n].startswith('\\x'):
                try:
                    row[n] = bytes.fromhex(row[n][2:])
                except ValueError:
                    pass
        out.append(row)
    return out


def copy_row(line):
    """One line of COPY's text format: fields split by tabs, \\N for NULL, backslash escapes."""
    return [None if field == '\\N' else _pg_unescape(field) for field in line.split('\t')]


# ---- loading --------------------------------------------------------------------------------------------------------

class _Loader:
    def __init__(self, conn, dialect):
        self.conn, self.dialect = conn, dialect
        self.tables = {}               # lower-case SQLite name -> {"name", "columns": [names], "rows": n}
        self.keys = {}                 # SQLite name -> {"pk": [...], "fks": [{"columns", "references"}]}
        self.skipped, self.problems = Counter(), []

    def problem(self, message):
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(message[:300])

    def create(self, schema, name, columns, pk, fks):
        sqlite_name = _sqlite_name(schema, name)
        if sqlite_name.lower() in self.tables:
            return
        parts = [f'{_q(c)} {t}'.rstrip() for c, t in columns]
        if pk:
            parts.append(f'PRIMARY KEY ({", ".join(_q(c) for c in pk)})')
        for cols, ref_table, ref_cols in fks:
            parts.append(f'FOREIGN KEY ({", ".join(_q(c) for c in cols)}) REFERENCES {_q(ref_table)}'
                         + (f' ({", ".join(_q(c) for c in ref_cols)})' if ref_cols else ''))
        self.conn.execute(f'CREATE TABLE {_q(sqlite_name)} ({", ".join(parts)})')
        self.tables[sqlite_name.lower()] = {'name': sqlite_name, 'columns': [c for c, _t in columns], 'rows': 0,
                                            'types': {c: (t or '').upper() for c, t in columns}}

    def table_for(self, schema, name, width, columns=None):
        sqlite_name = _sqlite_name(schema, name)
        table = self.tables.get(sqlite_name.lower())
        if table is None:
            cols = columns or [f'column_{n + 1}' for n in range(width)]
            self.create(schema, name, [(c, '') for c in cols], [], [])
            self.problem(f'Rows for "{sqlite_name}" came without its CREATE TABLE; its columns have no types.')
            table = self.tables[sqlite_name.lower()]
        return table

    def insert(self, table, columns, rows):
        columns = columns or table['columns']
        rows = _typed(rows, [table.get('types', {}).get(c, '') for c in columns])
        good = [r for r in rows if len(r) == len(columns)]
        if len(good) < len(rows):
            self.problem(f'{len(rows) - len(good)} row(s) of "{table["name"]}" had the wrong number of values.')
        for start in range(0, len(good), BATCH):
            chunk = good[start:start + BATCH]
            try:
                self.conn.executemany(f'INSERT OR IGNORE INTO {_q(table["name"])} ({", ".join(_q(c) for c in columns)}) '
                                      f'VALUES ({", ".join("?" * len(columns))})', chunk)
                table['rows'] += len(chunk)
            except sqlite3.Error as exc:
                self.problem(f'Rows of "{table["name"]}" were refused: {exc}')
                return

    def alter(self, text):
        m = re.match(r'^ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(?P<table>(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[\w$.]+)+)'
                     r'\s+(?P<rest>.*)$', text, re.I | re.S)
        if not m or not re.search(r'PRIMARY\s+KEY|FOREIGN\s+KEY', m.group('rest'), re.I):
            self.skipped['ALTER TABLE'] += 1
            return
        name = _sqlite_name(*_split_name(m.group('table')))
        keys = self.keys.setdefault(name, {'pk': [], 'fks': []})
        for pk in re.finditer(r'PRIMARY\s+KEY\s*\(([^)]*)\)', m.group('rest'), re.I):
            keys['pk'] = _columns_list(pk.group(1))
        for fk in re.finditer(r'FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+(\S+?)\s*\(([^)]*)\)', m.group('rest'), re.I):
            keys['fks'].append({'columns': _columns_list(fk.group(1)),
                                'references': f'{_sqlite_name(*_split_name(fk.group(2)))}({", ".join(_columns_list(fk.group(3)))})'})

    def statement(self, text):
        upper = text[:120].upper()
        if re.match(r'CREATE\s+(?:TEMPORARY\s+|UNLOGGED\s+)?TABLE\b', upper) and ' AS SELECT' not in upper:
            try:
                self.create(*parse_create(text, self.dialect))
            except Exception as exc:
                self.problem(f'A CREATE TABLE could not be read: {str(exc)[:150]} ({text[:80]}...)')
            return
        if re.match(r'(?:INSERT|REPLACE)\b', upper):
            try:
                schema, name, columns, rows = parse_insert(text, self.dialect)
            except Exception as exc:
                self.problem(f'An INSERT could not be read: {str(exc)[:150]} ({text[:80]}...)')
                return
            if rows:
                self.insert(self.table_for(schema, name, len(rows[0]), columns), columns, rows)
            return
        if upper.startswith('ALTER TABLE'):
            self.alter(text)
            return
        words = re.findall(r'[A-Z_]+', upper)[:2]
        label = ' '.join(words) if words and words[0] in ('CREATE', 'ALTER', 'DROP') else (words[0] if words else '?')
        self.skipped[label] += 1


def load(path, out_path, dialect, deadline=None) -> dict:
    """Read the dump at `path` into a new SQLite file at `out_path`. Returns what was read and what was skipped."""
    started = time.monotonic()
    conn = sqlite3.connect(out_path)
    conn.execute('PRAGMA journal_mode=OFF')
    conn.execute('PRAGMA synchronous=OFF')
    loader = _Loader(conn, dialect)
    copy_table, copy_columns, copy_rows = None, None, []
    try:
        with open_text(path) as lines:
            for count, (kind, value) in enumerate(statements(lines, dialect)):
                if deadline and count % 500 == 0 and time.monotonic() > deadline:
                    raise Refused('Loading stopped: the dump took too long to read. Upload a smaller one, or only the '
                                  'tables to ask about.')
                if kind == 'row':
                    if copy_table is not None:
                        copy_rows.append(copy_row(value))
                        if len(copy_rows) >= BATCH:
                            loader.insert(copy_table, copy_columns, copy_rows)
                            copy_rows = []
                    continue
                if kind == 'copy_end':
                    if copy_table is not None and copy_rows:
                        loader.insert(copy_table, copy_columns, copy_rows)
                    copy_table, copy_columns, copy_rows = None, None, []
                    continue
                copy = _COPY.match(value) if dialect == 'postgres' else None
                if copy:
                    columns = _columns_list(copy.group('cols')) if copy.group('cols') else None
                    schema, name = _split_name(copy.group('table'))
                    copy_table = loader.table_for(schema, name, len(columns or []) or 1, columns)
                    copy_columns, copy_rows = columns, []
                    continue
                loader.statement(value)
        conn.commit()
    finally:
        conn.close()
    tables = sorted(loader.tables.values(), key=lambda t: t['name'].lower())
    return {
        'dialect': dialect, 'dialect_label': LABELS.get(dialect, dialect),
        'tables': [{'name': t['name'], 'rows': t['rows']} for t in tables],
        'rows': sum(t['rows'] for t in tables),
        'skipped': dict(loader.skipped.most_common()),
        'problems': loader.problems,
        'keys': loader.keys,
        'seconds': round(time.monotonic() - started, 1),
    }


def with_keys(tables, report) -> list:
    """The structure read from the SQLite copy, with the keys the dump added later by ALTER TABLE."""
    keys = (report or {}).get('keys') or {}
    if not keys:
        return tables
    by_name = {k.lower(): v for k, v in keys.items()}
    for table in tables:
        extra = by_name.get(table['name'].lower())
        if not extra:
            continue
        for column in table.get('columns') or []:
            if column['name'] in (extra.get('pk') or []):
                column['pk'] = True
        known = {fk['references'] for fk in table.get('fks') or []}
        table['fks'] = (table.get('fks') or []) + [fk for fk in extra.get('fks') or [] if fk['references'] not in known]
    return tables
