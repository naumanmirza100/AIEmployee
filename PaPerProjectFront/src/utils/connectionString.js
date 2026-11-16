// What a pasted database connection string holds, read on the screen as it is typed (16 Nov 2026): the kind, host,
// port, database, user, whether it has a password, encryption and the options kept. Nothing is sent or connected
// here; the server reads the string again when it is added (data_analyst_agent/mssql.py, mongo.py and SQLAlchemy's
// make_url), and this follows those readers so what is shown is what is saved.

export const KIND_LABELS = { postgres: 'PostgreSQL', mysql: 'MySQL / MariaDB', mssql: 'SQL Server', mongodb: 'MongoDB' };

// The port each kind listens on unless set otherwise, as the server's connectors.DEFAULT_PORTS.
export const DEFAULT_PORTS = { postgres: 5432, mysql: 3306, mssql: 1433, mongodb: 27017 };

// The ports people commonly meet for each kind, the default first. SQL Server and Azure SQL use 1433 (a named
// instance has its own port, which its administrator knows); MongoDB servers 27017 (Atlas: a mongodb+srv string).
export const PORT_OPTIONS = {
  postgres: [[5432, 'default'], [6543, 'Supabase pooler'], [25060, 'DigitalOcean']],
  mysql: [[3306, 'default'], [3307, 'second server'], [25060, 'DigitalOcean']],
  mssql: [[1433, 'default, also Azure SQL']],
  mongodb: [[27017, 'default']],
};

export const validPort = (value) => /^\d{1,5}$/.test(String(value ?? '').trim())
  && Number(value) >= 1 && Number(value) <= 65535;

const decode = (text) => {
  try { return decodeURIComponent(text || ''); } catch { return text || ''; }
};

// a=1&b=2 as {a: '1', b: '2'}; the keys lower-case unless keepCase (SQLAlchemy reads sslmode as written).
const query = (text, keepCase = false) => {
  const out = {};
  for (const part of String(text || '').split('&')) {
    if (!part) continue;
    const [key, ...rest] = part.split('=');
    const name = decode(key.replace(/\+/g, ' '));
    out[keepCase ? name : name.toLowerCase()] = decode(rest.join('=').replace(/\+/g, ' '));
  }
  return out;
};

// ---- SQL Server: ADO.NET (Azure portal), ODBC, JDBC or a URL, as mssql.parse_connection_string -------------------

const SQL_SERVER_KEYS = {
  server: 'server', datasource: 'server', address: 'server', addr: 'server', networkaddress: 'server',
  servername: 'server',
  database: 'database', initialcatalog: 'database', databasename: 'database',
  userid: 'username', uid: 'username', user: 'username', username: 'username',
  password: 'password', pwd: 'password',
  encrypt: 'encrypt', trustservercertificate: 'trust', portnumber: 'port', port: 'port',
};

export const looksLikeSqlServer = (text) => {
  const lowered = String(text || '').trim().toLowerCase();
  if (/^(jdbc:sqlserver|sqlserver|mssql|mssql\+pyodbc|mssql\+pymssql):\/\//.test(lowered)) return true;
  return /(?:^|;)\s*(?:server|data\s+source|address|addr|network\s+address)\s*=/.test(lowered);
};

// key=value;key={va;lue};key="value" as {normalised key: value}.
const pairs = (text) => {
  const out = {};
  let i = 0;
  const n = text.length;
  while (i < n) {
    const eq = text.indexOf('=', i);
    if (eq < 0) break;
    const key = text.slice(i, eq).replace(/\s+/g, '').toLowerCase();
    let j = eq + 1;
    while (j < n && text[j] === ' ') j += 1;
    if (j < n && '{"\''.includes(text[j])) {
      const close = { '{': '}', '"': '"', "'": "'" }[text[j]];
      let k = j + 1;
      let value = '';
      while (k < n) {
        if (text[k] === close && text[k + 1] === close) { value += close; k += 2; continue; }
        if (text[k] === close) break;
        value += text[k];
        k += 1;
      }
      out[key] = value;
      const end = text.indexOf(';', k);
      i = end < 0 ? n : end + 1;
    } else {
      const end = text.indexOf(';', j);
      out[key] = (end < 0 ? text.slice(j) : text.slice(j, end)).trim();
      i = end < 0 ? n : end + 1;
    }
  }
  return out;
};

// 'tcp:host,1433', 'host\\instance', 'host:1433' or '[::1],1433' as {host, port, instance}.
const sqlServerAddress = (value) => {
  const text = String(value || '').trim().replace(/^(?:tcp|np|lpc|admin):/i, '');
  let host = text;
  let port = '';
  if (text.includes(',')) {
    const at = text.lastIndexOf(',');
    host = text.slice(0, at);
    port = text.slice(at + 1);
  } else if ((text.match(/:/g) || []).length === 1 && !text.startsWith('[')) {
    [host, port] = text.split(':');
  }
  host = host.trim().replace(/^\[|\]$/g, '');
  let instance = '';
  if (host.includes('\\')) [host, instance] = host.split('\\', 2);
  port = port.trim();
  if (port && !/^\d+$/.test(port)) throw new Error(`"${port}" is not a port number.`);
  return { host, port: port ? Number(port) : null, instance };
};

const readSqlServer = (text) => {
  const lowered = text.toLowerCase();
  let fields = {};
  if (lowered.startsWith('jdbc:sqlserver://')) {
    const rest = text.slice('jdbc:sqlserver://'.length);
    const cut = rest.indexOf(';');
    const head = cut < 0 ? rest : rest.slice(0, cut);
    const address = sqlServerAddress((head.match(/:/g) || []).length === 1 ? head.replace(':', ',') : head);
    fields = pairs(cut < 0 ? '' : rest.slice(cut + 1));
    fields.server = address.port ? `${address.host},${address.port}` : address.host;
  } else if (/^(?:sqlserver|mssql(?:\+\w+)?):\/\//.test(lowered)) {
    const body = text.slice(text.indexOf('://') + 3);
    const cut = body.search(/[/?#]/);
    const netloc = cut < 0 ? body : body.slice(0, cut);
    const after = cut < 0 ? '' : body.slice(cut);
    const at = netloc.lastIndexOf('@');
    const userinfo = at < 0 ? '' : netloc.slice(0, at);
    const hostport = netloc.slice(at + 1);
    const colon = userinfo.indexOf(':');
    const path = after.startsWith('/') ? after.slice(1).split(/[?#]/)[0] : '';
    const q = after.includes('?') ? after.slice(after.indexOf('?') + 1).split('#')[0] : '';
    fields = {
      server: (hostport.match(/:/g) || []).length === 1 ? hostport.replace(':', ',') : hostport,
      database: decode(path),
      username: decode(colon < 0 ? userinfo : userinfo.slice(0, colon)),
      password: decode(colon < 0 ? '' : userinfo.slice(colon + 1)),
    };
    for (const [key, value] of Object.entries(query(q))) fields[key.replace(/\s+/g, '')] = value;
  } else {
    fields = pairs(text);
  }
  const found = {};
  for (const [key, value] of Object.entries(fields)) {
    const name = SQL_SERVER_KEYS[key];
    if (name && value != null) found[name] = value;
  }
  if (!found.server) throw new Error('The string has no server (Server=... or Data Source=...).');
  const address = sqlServerAddress(found.server);
  let { port } = address;
  if (!port && /^\d+$/.test(String(found.port || ''))) port = Number(found.port);
  const encrypt = String(found.encrypt ?? 'true').trim().toLowerCase();
  const trust = ['true', 'yes', '1', 'mandatory', 'strict'].includes(String(found.trust ?? 'false').trim().toLowerCase());
  return {
    kind: 'mssql', host: address.host, port, database: found.database || '', username: found.username || '',
    hasPassword: Boolean(found.password),
    ssl: ['false', 'no', '0', 'optional'].includes(encrypt) ? 'off' : 'required',
    options: trust ? ['TrustServerCertificate=True'] : [],
    problem: address.instance && !port
      ? `A named instance (${address.host}\\${address.instance}) needs its port: ask its administrator, and type it in Port.`
      : '',
  };
};

// ---- MongoDB, as mongo.parse_uri ----------------------------------------------------------------------------------

const MONGO_OPTIONS = { authsource: 'authSource', authmechanism: 'authMechanism', replicaset: 'replicaSet' };

const mongoHost = (item) => {
  const text = item.trim();
  let host = text;
  let port = '';
  if (text.startsWith('[')) {
    const close = text.indexOf(']');
    host = text.slice(1, close < 0 ? undefined : close);
    port = close < 0 ? '' : text.slice(close + 1).replace(/^:/, '');
  } else if ((text.match(/:/g) || []).length === 1) {
    [host, port] = text.split(':');
  }
  if (port && !/^\d+$/.test(port)) throw new Error(`"${text}" has a port that is not a number.`);
  return { host, port: port ? Number(port) : null };
};

const readMongo = (text) => {
  const scheme = text.slice(0, text.indexOf('://')).toLowerCase();
  const body = text.slice(text.indexOf('://') + 3);
  const cut = body.search(/[/?#]/);
  const netloc = cut < 0 ? body : body.slice(0, cut);
  const after = cut < 0 ? '' : body.slice(cut);
  const at = netloc.lastIndexOf('@');
  const userinfo = at < 0 ? '' : netloc.slice(0, at);
  const colon = userinfo.indexOf(':');
  const hosts = netloc.slice(at + 1).split(',').filter((h) => h.trim());
  if (!hosts.length) throw new Error('The string has no host.');
  const srv = scheme === 'mongodb+srv';
  if (srv && (hosts.length !== 1 || hosts[0].includes(':'))) throw new Error('A mongodb+srv:// string names one host, without a port.');
  const q = query(after.includes('?') ? after.slice(after.indexOf('?') + 1).split('#')[0] : '');
  const servers = hosts.map(mongoHost);
  const tls = String(q.tls || q.ssl || '').toLowerCase() === 'true';
  return {
    kind: 'mongodb', srv,
    host: servers.length === 1 ? servers[0].host : servers.map((s) => s.host).join(', '),
    port: servers.length === 1 ? servers[0].port : null,
    servers: servers.length > 1 ? servers : null,
    database: decode((after.startsWith('/') ? after.slice(1) : '').split(/[?#]/)[0]),
    username: decode(colon < 0 ? userinfo : userinfo.slice(0, colon)),
    hasPassword: colon >= 0 && colon < userinfo.length - 1,
    ssl: srv || tls ? 'required' : 'off',
    options: Object.entries(q).filter(([k]) => MONGO_OPTIONS[k]).map(([k, v]) => `${MONGO_OPTIONS[k]}=${v}`),
    problem: '',
  };
};

// ---- PostgreSQL and MySQL / MariaDB URLs, as SQLAlchemy's make_url ----------------------------------------------

const URL_PATTERN = /^([\w+]+):\/\/(?:([^:/]*)(?::([^@]*))?@)?(?:(?:\[([^/?]+)\]|([^/:?]+))?(?::([^/?]*))?)?(?:\/([^?]*))?(?:\?(.*))?$/s;
const URL_KINDS = { postgresql: 'postgres', postgres: 'postgres', mysql: 'mysql', mariadb: 'mysql' };

const readUrl = (text) => {
  const m = text.match(URL_PATTERN);
  if (!m) throw new Error('That connection string could not be read.');
  const [, name, user, password, ipv6, host, port, database, q] = m;
  const kind = URL_KINDS[name.split('+')[0].toLowerCase()];
  if (!kind) {
    throw new Error('A connection string starts with postgresql://, mysql://, mariadb://, mongodb:// or '
      + 'mongodb+srv://, or is a SQL Server string (Server=...;Database=...;User ID=...).');
  }
  if (port && !/^\d+$/.test(port)) throw new Error(`"${port}" is not a port number.`);
  const params = query(q, true);
  const sslmode = String(params.sslmode || params.ssl_mode || '').toLowerCase();
  const required = ['require', 'required', 'verify-ca', 'verify-full', 'verify_ca', 'verify_identity'].includes(sslmode);
  return {
    kind, host: host || ipv6 || '', port: port ? Number(port) : null, database: database || '',
    username: decode(user), hasPassword: Boolean(password),
    ssl: required ? 'required' : 'offered',
    options: sslmode ? [`${params.sslmode ? 'sslmode' : 'ssl_mode'}=${sslmode}`] : [],
    problem: '',
  };
};

/** The pieces of a connection string, or {error} when it can't be read; null for an empty string. */
export function readConnectionString(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  try {
    const lowered = text.toLowerCase();
    if (lowered.startsWith('mongodb://') || lowered.startsWith('mongodb+srv://')) return readMongo(text);
    if (looksLikeSqlServer(text)) return readSqlServer(text);
    return readUrl(text);
  } catch (e) {
    return { error: e.message || 'That connection string could not be read.' };
  }
}

/** True when a value typed in a Host box is a whole connection string. */
export const isConnectionString = (value) => {
  const text = String(value || '').trim();
  return /^[\w+]+:\/\/./.test(text) || /;/.test(text) && looksLikeSqlServer(text);
};
