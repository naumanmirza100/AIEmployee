"""MongoDB for the AI Data Analyst (6 Nov 2026): a connection string in, questions answered by one read-only aggregation.

MongoDB has no SQL, so the AI writes one aggregation, {"collection": "...", "pipeline": [...]}, and the three layers
that guard SQL guard it too:
  1. guards.check_pipeline: only stages that read; nothing anywhere that writes ($out, $merge) or runs JavaScript
     ($function, $accumulator, $where, $code); joins only to collections of the same database;
  2. here: the only call ever made with the AI's query is aggregate(), with a time limit (maxTimeMS), reading from a
     secondary when the database has one; nothing in this module writes;
  3. the company is asked for a user with the read role only, and the test says when the user could write
     (connectionStatus lists its privileges).

Addresses: every host of a mongodb:// string, and every host the service record of a mongodb+srv:// name points to,
must be public (guards.resolve_public), as for SQL. A single host is connected to directly, so no other member is
discovered. A replica set's members are named by its own servers; once connected, every member must be public too, or
the connection is closed before anything is asked.

Structure: the collections' names, and from a sample of each, its fields (dotted for nested ones) and their types.
No value is kept.
"""
import datetime
import json
import time
import uuid
from urllib.parse import parse_qs, unquote, urlsplit

from .guards import Refused, resolve_public

CONNECT_TIMEOUT = 10          # seconds
SAMPLE_SIZE = 40              # documents read from each collection to learn its fields
SAMPLE_TIMEOUT_MS = 5000
READ_BUDGET = 35              # seconds for reading every collection; the site cuts a request at 60
MAX_DEPTH = 3                 # nested levels named in the structure (a.b.c)
MAX_CELL = 500                # characters of a list or a nested value shown in a cell
DEFAULT_PORT = 27017
SYSTEM_DATABASES = {'admin', 'local', 'config'}
#: URI options kept from a connection string, under pymongo's spelling. Everything else (w, retryWrites, appName...) is
#: about writing or naming and is dropped.
OPTIONS = {'authsource': 'authSource', 'authmechanism': 'authMechanism', 'replicaset': 'replicaSet'}
#: A user holding any of these could change data.
WRITE_ACTIONS = {'insert', 'update', 'remove', 'createCollection', 'dropCollection', 'dropDatabase', 'createIndex',
                 'dropIndex', 'renameCollectionSameDB', 'bypassDocumentValidation', 'collMod'}


# ---- the connection string ------------------------------------------------------------------------------------------

def _split_host(item: str):
    """'host', 'host:27018' or '[::1]:27018' as (host, port or None)."""
    item = item.strip()
    if item.startswith('['):
        host, _, rest = item[1:].partition(']')
        port = rest.lstrip(':')
    elif item.count(':') == 1:
        host, port = item.split(':')
    else:
        host, port = item, ''
    if port and not port.isdigit():
        raise Refused(f'"{item}" has a port that is not a number.')
    return host, (int(port) if port else None)


def parse_uri(text: str) -> dict:
    """A mongodb:// or mongodb+srv:// string as the source's fields. Nothing is looked up or connected here."""
    text = str(text or '').strip()
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ('mongodb', 'mongodb+srv'):
        raise Refused('A MongoDB connection string starts with mongodb:// or mongodb+srv://.')
    userinfo, at, hostlist = parts.netloc.rpartition('@')
    if not at:
        hostlist, userinfo = parts.netloc, ''
    username, _, password = userinfo.partition(':')
    hosts = [h for h in hostlist.split(',') if h.strip()]
    if not hosts:
        raise Refused('The connection string has no host.')
    srv = scheme == 'mongodb+srv'
    if srv and (len(hosts) != 1 or ':' in hosts[0]):
        raise Refused('A mongodb+srv:// string names one host, without a port.')
    query = {k.lower(): v[-1] for k, v in parse_qs(parts.query).items()}
    tls_word = (query.get('tls') or query.get('ssl') or '').lower()
    if len(hosts) == 1:
        host, port = _split_host(hosts[0])
    else:
        for item in hosts:
            _split_host(item)               # each must be readable
        host, port = ','.join(h.strip() for h in hosts), None
    return {
        'srv': srv, 'host': host[:255], 'port': port,
        'database': unquote(parts.path.lstrip('/'))[:255],
        'username': unquote(username)[:255], 'password': unquote(password),
        'options': {OPTIONS[k]: v[:100] for k, v in query.items() if k in OPTIONS},
        # A +srv name is always encrypted (Atlas); a plain string only when it says so.
        'tls': srv or tls_word == 'true',
    }


# ---- connecting -----------------------------------------------------------------------------------------------------

def _hosts(source):
    """[(host, port)] of a mongodb:// source."""
    out = []
    for item in [h for h in (source.host or '').split(',') if h.strip()]:
        host, port = _split_host(item)
        out.append((host, port or source.port or DEFAULT_PORT))
    if not out:
        raise Refused("Give the MongoDB server's host name.")
    return out


def srv_targets(host: str) -> list:
    """The (host, port) pairs the service record of a mongodb+srv:// name points to, each checked public."""
    import dns.exception
    import dns.resolver
    try:
        answers = dns.resolver.resolve(f'_mongodb._tcp.{host}', 'SRV', lifetime=CONNECT_TIMEOUT)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        raise Refused(f'"{host}" has no MongoDB service record. Check the host, or use a mongodb:// string.')
    except dns.exception.Timeout:
        raise Refused(f'"{host}" could not be looked up in time. Try again.')
    targets = [(str(r.target).rstrip('.'), int(r.port)) for r in answers]
    if not targets:
        raise Refused(f'"{host}" has no MongoDB service record.')
    for target, port in targets:
        resolve_public(target, port)
    return targets


def _check_members(client):
    """Every server the client found must be public (a replica set's members are named by its own servers)."""
    for host, port in list(client.topology_description.server_descriptions()):
        resolve_public(host, port)


def _client(source):
    """A client for one question, every address checked. Closed by the caller."""
    from pymongo import MongoClient
    from . import connectors
    settings = dict(
        username=source.username or None, password=source.get_password() or None,
        serverSelectionTimeoutMS=CONNECT_TIMEOUT * 1000, connectTimeoutMS=CONNECT_TIMEOUT * 1000,
        socketTimeoutMS=(connectors.QUERY_TIMEOUT + 10) * 1000, readPreference='secondaryPreferred',
        retryWrites=False, appname='PayPerProject Data Analyst', tz_aware=True, uuidRepresentation='standard',
        maxPoolSize=2, **{k: v for k, v in (source.options or {}).items() if k in OPTIONS.values()})
    if source.use_srv:
        srv_targets(source.host)
        return MongoClient(f'mongodb+srv://{source.host}/', tls=True, **settings)
    hosts = _hosts(source)
    checked = [(host, port, resolve_public(host, port)) for host, port in hosts]
    if len(checked) == 1:
        host, port, address = checked[0]
        # Without encryption the checked address itself is used, so the name can't point elsewhere in between; with
        # it, the name (its certificate is for the name). Either way only this server: nothing else is discovered.
        target = host if source.use_ssl else (f'[{address}]' if ':' in address else address)
        return MongoClient(host=target, port=port, tls=bool(source.use_ssl), directConnection=True, **settings)
    return MongoClient(host=[f'{h}:{p}' for h, p, _a in checked], tls=bool(source.use_ssl), **settings)


def _database(client, source):
    """The source's database. With none named, the only one this user can see is taken (and remembered)."""
    _check_members_after_connect(client)
    if source.database:
        return client[source.database]
    names = [n for n in client.list_database_names() if n not in SYSTEM_DATABASES]
    if len(names) == 1:
        source.database = names[0]
        return client[names[0]]
    if not names:
        raise Refused('This user can see no database. Give it the read role on the one to ask.')
    raise Refused(f'Name the database to read: this user can see {", ".join(sorted(names)[:15])}. Add it after the '
                  'host in the connection string (…mongodb.net/your_db) or in "Database name".')


def database_names(source) -> list:
    """The databases this user can see (not admin, local or config), to name back when the one asked for is empty."""
    client = _client(source)
    try:
        _check_members_after_connect(client)
        return sorted(n for n in client.list_database_names() if n not in SYSTEM_DATABASES)
    except Exception:
        return []
    finally:
        client.close()


def _check_members_after_connect(client):
    client.admin.command('ping')       # connects (and discovers the members of a replica set)
    _check_members(client)


# ---- the structure --------------------------------------------------------------------------------------------------

def _type_name(value) -> str:
    from bson import Binary, Decimal128, Int64, ObjectId
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, Int64):
        return 'long'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'double'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, datetime.datetime):
        return 'date'
    if isinstance(value, ObjectId):
        return 'objectId'
    if isinstance(value, Decimal128):
        return 'decimal'
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, uuid.UUID):
        return 'uuid'
    if isinstance(value, (bytes, Binary)):
        return 'binData'
    return type(value).__name__


def fields_of(docs, max_columns=150) -> list:
    """The fields of sampled documents: [{"name", "type", "pk", "nullable"}], nested ones dotted (a.b), first seen first.
    Lists are 'array<type>', and the fields of documents inside a list are named through it, as MongoDB queries them
    (items.qty)."""
    found = {}       # name -> {"types": set, "docs": set of document numbers}

    def note(name, kind, number):
        entry = found.setdefault(name, {'types': [], 'docs': set()})
        if kind not in entry['types']:
            entry['types'].append(kind)
        entry['docs'].add(number)

    def visit(name, value, depth, number):
        if isinstance(value, list):
            inner = []
            for item in value[:20]:
                kind = _type_name(item)
                if kind not in inner:
                    inner.append(kind)
            note(name, f"array<{'|'.join(inner[:3])}>" if inner else 'array', number)
            for item in value[:20]:
                if isinstance(item, dict) and depth < MAX_DEPTH:
                    for key, sub in item.items():
                        visit(f'{name}.{key}', sub, depth + 1, number)
            return
        note(name, _type_name(value), number)
        if isinstance(value, dict) and depth < MAX_DEPTH:
            for key, sub in value.items():
                visit(f'{name}.{key}', sub, depth + 1, number)

    for number, doc in enumerate(docs):
        for key, value in doc.items():
            visit(str(key), value, 1, number)
    columns = []
    for name, entry in found.items():
        types = [t for t in entry['types'] if t != 'null'] or ['null']
        if any(t.startswith('array<') for t in types):
            types = [t for t in types if t != 'array']          # an empty list says nothing about its items
        columns.append({'name': name, 'type': '|'.join(types[:3]), 'pk': name == '_id',
                        'nullable': 'null' in entry['types'] or len(entry['docs']) < len(docs)})
        if len(columns) >= max_columns:
            break
    return columns


def _list_collections(db) -> list:
    """The database's collections and views, unfiltered: system.* is left out by the caller. Atlas's free clusters
    (M0) refused a {"$not": {"$regex": ...}} filter here ("can't get regex from filter doc not a regex", 7 Nov 2026),
    and an older server may not know authorizedCollections, so the plainest form is the fallback."""
    from pymongo.errors import OperationFailure
    try:
        return list(db.list_collections(authorizedCollections=True, nameOnly=True))
    except OperationFailure:
        return [{'name': name, 'type': 'collection'} for name in db.list_collection_names()]


def _sample(collection) -> list:
    try:
        return list(collection.aggregate([{'$sample': {'size': SAMPLE_SIZE}}], maxTimeMS=SAMPLE_TIMEOUT_MS))
    except Exception:
        return list(collection.find({}, limit=SAMPLE_SIZE, max_time_ms=SAMPLE_TIMEOUT_MS))


def read_tables(source) -> list:
    """Collections and views with the fields a sample of each shows: never a value. A collection left when the time is
    up is listed by name only."""
    from . import connectors
    client = _client(source)
    started = time.monotonic()
    try:
        db = _database(client, source)
        listed = [c for c in _list_collections(db) if not str(c.get('name', '')).startswith('system.')]
        out = []
        for item in sorted(listed, key=lambda c: c['name'])[:connectors.MAX_TABLES]:
            name = item['name']
            kind = 'view' if item.get('type') == 'view' else 'collection'
            columns = []
            if time.monotonic() - started < READ_BUDGET:
                try:
                    columns = fields_of(_sample(db[name]), connectors.MAX_COLUMNS)
                except Exception:
                    columns = []
            out.append({'name': name, 'schema': '', 'kind': kind, 'columns': columns, 'fks': []})
        return out
    finally:
        client.close()


def can_write(source):
    """Whether the user could change data, from the privileges MongoDB lists for it; None when it can't be told."""
    client = _client(source)
    try:
        db = _database(client, source)
        status = db.command({'connectionStatus': 1, 'showPrivileges': True})
        info = status.get('authInfo') or {}
        if not info.get('authenticatedUsers'):
            return None
        actions = {a for p in info.get('authenticatedUserPrivileges') or [] for a in p.get('actions') or []}
        return bool(actions & WRITE_ACTIONS)
    except Refused:
        raise
    except Exception:
        return None
    finally:
        client.close()


# ---- running a question ---------------------------------------------------------------------------------------------

def _cell(value):
    """A value the screen and the AI can read."""
    from bson import Decimal128, ObjectId, json_util
    from . import connectors
    if isinstance(value, (ObjectId, Decimal128, uuid.UUID)):
        return str(value)
    if isinstance(value, list) and not any(isinstance(v, (list, dict)) for v in value):
        text = ', '.join('' if v is None else str(_cell(v)) for v in value)     # tags, ids: plain words
        return text if len(text) <= MAX_CELL else text[:MAX_CELL] + '…'
    if isinstance(value, (list, dict)):
        text = json_util.dumps(value, json_options=json_util.RELAXED_JSON_OPTIONS, ensure_ascii=False)
        return text if len(text) <= MAX_CELL else text[:MAX_CELL] + '…'
    return connectors._value(value)


def to_rows(docs, max_columns=100):
    """Documents as columns and rows: nested documents spread into dotted columns (two levels: _id.city), lists kept
    as text, columns in the order first seen."""
    def flat(doc, prefix='', depth=1):
        for key, value in doc.items():
            name = f'{prefix}{key}'
            if isinstance(value, dict) and value and depth < 3:
                yield from flat(value, f'{name}.', depth + 1)
            else:
                yield name, value

    flattened = [dict(flat(doc)) for doc in docs]
    columns = []
    for doc in flattened:
        for name in doc:
            if name not in columns and len(columns) < max_columns:
                columns.append(name)
    rows = [[_cell(doc.get(name)) for name in columns] for doc in flattened]
    return columns, rows


def run(source, text: str, max_rows: int) -> dict:
    """Run one already-checked aggregation. {"columns", "rows", "truncated", "duration_ms"} as for SQL."""
    from bson import json_util
    from . import connectors
    query = json_util.loads(text)
    client = _client(source)
    started = time.monotonic()
    docs = []
    try:
        db = _database(client, source)
        # maxTimeMS 0 would mean no limit at all to MongoDB: never less than 1 ms.
        limit_ms = max(1, int(connectors.QUERY_TIMEOUT * 1000))
        cursor = db[query['collection']].aggregate(query['pipeline'], maxTimeMS=limit_ms,
                                                   batchSize=min(max_rows + 1, 1000))
        try:
            for doc in cursor:
                docs.append(doc)
                if len(docs) > max_rows:
                    break
        finally:
            cursor.close()
    finally:
        client.close()
    columns, rows = to_rows(docs[:max_rows])
    return {'columns': columns, 'rows': rows, 'truncated': len(docs) > max_rows,
            'duration_ms': int((time.monotonic() - started) * 1000)}


def query_text(collection, pipeline) -> str:
    """How an aggregation is kept and shown: its collection and stages as JSON."""
    return json.dumps({'collection': collection, 'pipeline': pipeline}, indent=2, ensure_ascii=False)
