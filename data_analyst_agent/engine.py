"""A question answered from a company's database (plan: MDS/01-Plan/week-45/2026-11-03_Data-Analyst-Agent-Plan.md).

1. Choose the tables (an AI call, only for a database with many tables).
2. Write the SQL for that database's dialect (an AI call), from those tables' columns, types and keys.
3. Check it (guards.check_sql) and run it read-only (connectors.run). A refusal or a database error goes back to the
   AI once, with the reason, for a corrected query.
4. Write the answer from the result's first rows (an AI call), unless the source keeps rows from the AI; every number
   in it is checked against those rows (the Company Assistant's check).
5. Store the question, answer, SQL, column names and row count. Never a row.

MongoDB (6 Nov 2026): the same steps, with an aggregation {"collection", "pipeline"} in place of the SQL, written from
the collections' fields and checked by guards.check_pipeline.
"""
import json
import logging
import re
import time
from collections import namedtuple

from django.utils import timezone

from core.api_key_service import KeyServiceError
from core.assistant.engine import unchecked_numbers
from project_manager_agent.ai_agents.base_agent import BaseAgent

from . import connectors, mongo
from .guards import Refused, check_query
from .models import DataQuestion, DataSource

logger = logging.getLogger(__name__)

AGENT_KEY = 'data_analyst_agent'
TABLES_WITHOUT_CHOOSING = 30   # a database with more tables first has the question's tables chosen
TABLES_CHOSEN = 12
# The chosen tables and the ones they point at (their foreign keys), up to this many: the AI chose core_project and
# core_task but not auth_user, which both point at, and joined the project manager through the wrong table (16 Nov 2026).
TABLES_WITH_LINKS = 20
# The table list for choosing stays under about 6,000 tokens: fewer columns a table first, then names only. All 294
# tables of a real database with 25 columns each came to 11,536 tokens, more than a Groq key allows a minute (3 Nov 2026).
CHOOSE_LIST_CHARS = 20000
NOTES_IN_CHOICE_CHARS = 4000
ROWS_TO_AI = 100
ROWS_TO_SCREEN = 200
HISTORY_TURNS = 6
# The site's web server cuts a request at 60 seconds. A query stopped at the time limit isn't tried again, and another
# try is made only while it still fits: two 30-second queries came to 66 seconds and the screen got an error page.
ASK_SECONDS = 50
RETRY_SECONDS = 15      # a second try needs about 8 seconds to write and some time to run
QUERY_MIN_SECONDS = 5
QUERY_TRIES = 3         # a query and up to two corrected ones, while there is time (two until 17 Nov 2026)

_Fact = namedtuple('_Fact', 'text')
_THOUSANDS = re.compile(r'(?<=\d)[,  ](?=\d{3}(?!\d))')
DIALECT_NAMES = {'postgres': 'PostgreSQL', 'mysql': 'MySQL/MariaDB', 'sqlite': 'SQLite', 'mssql': 'Microsoft SQL Server',
                 'mongodb': 'MongoDB'}


class AnalystAI(BaseAgent):
    """The Data Analyst's AI calls: the company's key, counted under the agent's own name and quota."""

    def __init__(self, company_id):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = AGENT_KEY


def _json(raw) -> dict:
    text = (raw or '').strip().strip('`').removeprefix('json').strip()
    try:
        out = json.loads(text)
    except ValueError:
        match = re.search(r'\{.*\}', text, re.S)
        try:
            out = json.loads(match.group(0)) if match else {}
        except ValueError:
            out = {}
    return out if isinstance(out, dict) else {}


def _table_key(t) -> str:
    return f"{t['schema']}.{t['name']}" if t.get('schema') else t['name']


def _telling(cols) -> list:
    """A table's columns, the ones that say most about what it holds first: status-like ones (status, type ...), then
    the rest, then timestamps, then ids. The list for choosing tables shows only the first few: the leave requests
    showed "id, leave_type, start_date, end_date", hiding their status and days, and the balances were chosen for
    approved leave days (16 Nov 2026)."""
    def rank(c):
        name = str(c['name']).lower()
        if name == 'id' or name.endswith('_id'):
            return 3
        if name.endswith('_at') or name in ('created', 'updated', 'modified'):
            return 2
        return 0 if connectors._CHOICE_COLUMN.search(name) else 1
    return sorted(cols, key=rank)


def _table_text(t, full=True, columns=25, values=None, notes=None) -> str:
    view = ' (view)' if t.get('kind') == 'view' else ''
    if not full:
        names = ', '.join(c['name'] for c in _telling(t['columns'])[:columns])
        return f"- {_table_key(t)}{view} ({names})" if names else f"- {_table_key(t)}{view}"
    values, notes = values or {}, notes or {}

    def column(c):
        said = []
        if values.get(c['name']):
            said.append(f"values: {', '.join(repr(v) for v in values[c['name']])}")
        if notes.get(str(c['name']).lower()):
            said.append(f"note: {notes[str(c['name']).lower()]}")
        extra = f" ({'; '.join(said)})" if said else ''
        return f"{c['name']} {c['type']}{' PK' if c.get('pk') else ''}{extra}"
    cols = ', '.join(column(c) for c in t['columns'])
    fks = ''.join(f"; {', '.join(fk['columns'])} -> {fk['references']}" for fk in t.get('fks') or [])
    about = f"\n  Note on the table: {notes['']}" if notes.get('') else ''
    return f"- {_table_key(t)}{view}: {cols}{fks}{about}"


def _notes_text(notes, tables=None) -> str:
    """The database's own notes, one line each, for the table choice ("orders.total_amount: in the order's currency;
    convert with exchange_rates")."""
    names = {t['name'].lower() for t in tables} if tables is not None else None
    lines = [f"- {table}{'.' + column if column else ''}: {text}" for table, entry in (notes or {}).items()
             if names is None or table in names for column, text in entry.items()]
    text = '\n'.join(lines)[:NOTES_IN_CHOICE_CHARS]
    return f"The database's own notes on its tables and columns:\n{text}\n\n" if text else ''


def _history(conversation, source) -> str:
    if not conversation:
        return ''
    turns = list(DataQuestion.objects.filter(conversation=conversation, source=source)
                 .order_by('-created_at')[:HISTORY_TURNS])[::-1]
    lines = []
    for q in turns:
        lines.append(f'Question: {q.question[:400]}')
        if q.sql:
            lines.append(f'SQL: {q.sql[:800]}')
        if q.answer:
            lines.append(f'Answer: {q.answer[:400]}')
    return ('Conversation so far:\n' + '\n'.join(lines) + '\n\n') if lines else ''


_CHOOSE = """You pick the tables a question needs from a company's {dialect} database.

Tables (name and some columns):
{tables}

{notes}{history}Question: {question}

Return only JSON: {{"tables": ["name", ...]}} with at most {limit} names, spelled exactly as listed. Include the tables
needed to join, and the tables that hold the names of what the answer lists (people, companies, projects, products).
Choose generously, up to the limit: a table that may hold a figure the question needs (a salary, a price, hours, a
count) is better included than left out; the query is written from the tables chosen alone. When two tables could
hold what is asked (a record of each request and a running total, say), include both. To
count or add up what happened (approved leave days, orders, payments, tickets), the table with a row for each one is
the source; a table of running totals or balances only for a balance or what is left.
Amounts kept in several currencies (a currency column beside them) and asked in one: include the table of exchange
rates, and a view that already converts them if there is one. Include what the database's notes say a figure needs.
If none fits, return {{"tables": []}}."""

_SQL = """You write one read-only SQL query for a {dialect} database, to answer a question about a company's own data.

Today is {today}. The database: "{source_name}".

Tables (only these exist; columns with their types, PK marks the primary key, -> a foreign key; a note is the
database's own description of a column or table):
{tables}

{history}Question: {question}
{previous}
Rules:
- Exactly one SELECT (WITH allowed). Never change anything.
- Asked to change data (delete, update, add, cancel, fix records): write no query. Put in "ask_back": "I only read your
  database, so I can't change it." and leave "sql" empty.
- Return the figures the question is about as columns (a count, a total, an average, a share), named plainly, not
  only names. For "which ... the most / least / top", return the top 5 with their figures, in order, so the answer
  can say by how much.
- Use only the tables and columns listed, spelled exactly; quote names the way {dialect} needs when they have capitals,
  spaces or reserved words.
- Show what things are called, not only their ids: for companies, people, projects, campaigns, products and the like,
  join the table that holds the name and return it (an id may come alongside).
- A column listed with its values holds only those: filter with them exactly as spelled there.
- Count rows by the counted table's own id (COUNT(t.id)), also after a LEFT JOIN: COUNT of another column leaves out
  the rows where it is empty (COUNT(contact_id) misses the tickets without a contact), and COUNT(*) after a LEFT JOIN
  counts the empty row.
- Add no condition the question doesn't ask for (only active ones, only a period or a kind): when it doesn't say,
  count them all.
- The business's own name in the question (as in "Acme's revenue", or "our orders") means all of its data, not a
  filter on a store, brand or customer with that name, unless the question says so.
- Follow the notes on what a column means and how to work with it (its currency, what an empty value means, how to
  convert it). A note that some rows are usually left out is a default: when the question says what to leave out,
  leave out only that.
- Amounts beside a currency column are in that currency. For a total in one currency, convert each amount at the rate
  of its own date (the order's, the payment's) unless the question names another, with the exchange-rate table or a
  view that already converts: never add up different currencies, never leave the other currencies out, and never use
  one day's rate for all. A rate named like rate_to_usd turns the amount into USD by multiplying.
- A rate or price in force on a date, from a table with one row per date (exchange rates): take the latest date on or
  before it, for the same currency (or product), in a subquery right where the amount is converted, ordered by that
  date, newest first, first row only: amount * (SELECT r.rate FROM rates r WHERE r.currency = o.currency AND r.day <=
  the order's date ORDER BY r.day DESC, first row). A CTE can't see the order it would need. Dates can be missing
  (weekends, holidays), so joining on the same date drops the days without a row. From a table of periods (valid_from
  and valid_to): the period that covers the date, as its note says.
- Compare a timestamp with a date by its date part: as text, '2024-05-03 10:00:00' comes after '2024-05-03'.
- Take a thing's attribute from its own column when it has one: a customer's country is the customer's own country
  column, not an address's, unless the question names the address (billing, shipping).
- Join a table only on its key (its id, or a column marked ->). Joining on a column many rows share (a country, a
  date, a status) repeats every row once per match, and the totals multiply.
- Amounts kept with their sign (refunds or chargebacks as negative amounts, as a note or the values show): a net figure
  is their plain SUM over the rows that count. Subtracting them again adds them back.
- A total row beside the groups ("also give the grand total"): put the groups and the total row together with UNION
  ALL inside a subquery, and sort only outside it: SELECT * FROM (SELECT region, SUM(x) AS total FROM ... GROUP BY
  region UNION ALL SELECT 'Grand total', SUM(x) FROM ...) AS t ORDER BY CASE WHEN region = 'Grand total' THEN 1 ELSE 0
  END, total DESC. No ORDER BY inside the union or right after it.
- "First ever" (a first order, new customers): find each one's first over all the data, with no period condition in
  that step (MIN over every row), then keep those whose first falls in the period asked. A period condition inside the
  first step turns the first one in the period into the first ever.
- "Within N days of" something counts from its own day: another one on the same day is within 0 days.
- A table that points at itself (parent_id -> the same table) is a tree that can be several levels deep: to reach the
  top level, or everything under one, walk it with a recursive CTE (WITH RECURSIVE; in SQL Server a plain WITH). One
  join reaches only the next level.
- A list gets at most 200 rows ({limit_word}) unless the question asks for everything.
- Work dates out from today ("last month", "this year").
- When the tables can't answer it, or it is too unclear to write a query for, put one short sentence for the person in
  "ask_back" (what is missing, or what to make clear) and leave "sql" empty.
- Asked for a graph, chart, plot or any picture of the data: also describe it in "chart". "type": "bar" to compare
  groups, "line" for a change over time, "pie" for the parts of a whole (at most 8 parts); "x": the result column with
  the labels (for a line, the dates); "y": the result column with the figure; "title": a few words. The query must
  return those two columns: a bar chart at most 30 groups, largest first; a line in date order. Not asked for a
  picture: "chart": null.

Return only JSON: {{"sql": "...", "ask_back": "", "chart": null}}"""

_MONGO = """You write one read-only MongoDB aggregation, to answer a question about a company's own data.

Today is {today}.

Collections (only these exist; each with its fields and their types, read from a sample of its documents; a dotted name
is a nested field, array<...> a list; an objectId field other than _id usually holds the _id of a document in another
collection):
{tables}

{history}Question: {question}
{previous}
Rules:
- One aggregation on one collection: "collection" is its name, "pipeline" its stages. Join another collection with
  $lookup, its "from" one of the collections listed. Only stages that read: never $out or $merge, never JavaScript
  ($function, $accumulator, $where).
- Asked to change data (delete, update, add, cancel, fix records): write no query. Put in "ask_back": "I only read your
  database, so I can't change it." and leave "pipeline" empty.
- Return the figures the question is about as fields, named plainly (a count, a total, an average, a share), not only
  names. For "which ... the most / least / top", return the top 5 with their figures, in order, so the answer can say
  by how much.
- Use only the fields listed, spelled exactly. Leave _id out unless it is asked for ({{"$project": {{"_id": 0, ...}}}}).
- Show what things are called, not only their ids: $lookup the collection that holds the name and return it.
- A field listed with its values holds only those: match them exactly as spelled there.
- A field marked -> holds the _id of a document in that collection: join with $lookup from that collection,
  localField the field, foreignField _id. Don't join through a field that has no such mark to a collection it
  doesn't point at.
- Return one flat document per row, the figures as plain fields, no lists inside: for "per company and category",
  group by both together.
- Count documents with {{"$sum": 1}} (or $count): counting a field leaves out the documents where it is missing.
  To count different values ($addToSet, then $size), leave out the missing and null ones first.
- Add no condition the question doesn't ask for (only active ones, only a period or a kind): when it doesn't say,
  count them all.
- Write a date as {{"$date": "2026-10-01T00:00:00Z"}} and an ObjectId as {{"$oid": "..."}}.
- A list gets at most 200 documents ($limit 200) unless the question asks for everything.
- Work dates out from today ("last month", "this year").
- When the collections can't answer it, or it is too unclear to write a query for, put one short sentence for the
  person in "ask_back" (what is missing, or what to make clear) and leave "pipeline" empty.
- Asked for a graph, chart, plot or any picture of the data: also describe it in "chart". "type": "bar" to compare
  groups, "line" for a change over time, "pie" for the parts of a whole (at most 8 parts); "x": the result field with
  the labels (for a line, the dates); "y": the result field with the figure; "title": a few words. The pipeline must
  return those two fields: a bar chart at most 30 groups, largest first; a line in date order. Not asked for a
  picture: "chart": null.

Return only JSON: {{"collection": "...", "pipeline": [...], "ask_back": "", "chart": null}}"""

_ANSWER = """You answer a question from the result of a query that just ran on the company's own database.

Question: {question}

The query: {sql}

Result: {count}. Columns: {columns}
{rows}
{chart}
Write the answer plainly, in the language of the question:
- First one sentence that answers it, with the figure that answers it (the count, the total). Then, only if they
  help, up to five short bullets (the next ones, each with its own figure from the rows).
- Don't work out new numbers (differences, shares, sums of rows): give the figures as the rows have them.
- Use only the names, numbers and dates in the rows above. When the result was cut, don't add rows up yourself:
  say what the rows shown say, and that there are more.
- An empty result, or a total that came back empty: say nothing matched the query's conditions, naming the condition
  that matched nothing when one stands out. Never call it zero.
- Don't explain the SQL. Under 120 words. No heading."""


def _choose_list(tables) -> str:
    """The tables to choose from, each with as many of its columns as the size budget allows."""
    for columns in (25, 15, 10, 6, 4, 2, 0):
        text = '\n'.join(_table_text(t, full=False, columns=columns) for t in tables)
        if len(text) <= CHOOSE_LIST_CHARS:
            return text
    return text[:CHOOSE_LIST_CHARS]


_GENERIC_TOKENS = {'obj', 'ref', 'fk', 'key', 'pk'}


def _singular(word: str) -> str:
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith('s') and not word.endswith('ss') and len(word) > 3:
        return word[:-1]
    return word


def _tokens(name: str) -> list:
    """'hr_agent_employee' -> ['hr', 'agent', 'employee']; 'companyId' -> ['company', 'id']."""
    import re as _re
    spaced = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', str(name))
    return [t for t in _re.split(r'[^A-Za-z0-9]+', spaced.lower()) if t]


def _mongo_references(tables) -> list:
    """MongoDB has no foreign keys, so the AI guessed what a field pointed at: leave requests were joined straight to
    departments, and projects to themselves for their company (16 Nov 2026). A field named for a collection
    (employee_id, companyId, company, department_obj_id) is taken to hold the _id of a document in it, when one
    collection is named so; of several, the one whose name shares the most of the field's collection's name (the same
    app). Returns copies of the tables with those as their 'fks', for the prompt and for adding the tables pointed at."""
    by_last = {}          # every ending of a collection's name, singular: company_users -> "user", "companyuser"
    for t in tables:
        words = _tokens(t['name'])
        for size in range(1, len(words) + 1):
            key = _singular(''.join(words[-size:]))
            if t not in by_last.setdefault(key, []):
                by_last[key].append(t)
    out = []
    for t in tables:
        fks = list(t.get('fks') or [])
        for column in t.get('columns') or []:
            name, kind = str(column['name']), str(column.get('type') or '')
            if name == '_id' or '.' in name or not kind.startswith(('int', 'long', 'objectId', 'string', 'array<objectId')):
                continue
            words = _tokens(name)
            if words and words[-1] in ('id', 'ids'):
                words = words[:-1]
            elif kind != 'objectId':
                continue
            target = None
            words = [w for w in words if w not in _GENERIC_TOKENS]
            # The longest ending of the name first: company_user_id is core_companyuser, not auth_user.
            for size in range(len(words), 0, -1):
                key = _singular(''.join(words[-size:]))
                matches = [m for m in by_last.get(key, []) if m is not t]
                if not matches:
                    continue
                if len(matches) > 1:
                    # The same app first (the most of the name in common), then the closest name (the fewest words
                    # besides the match): user_id is auth_user rather than core_company_users.
                    mine = _tokens(t['name'])
                    shared = lambda m: sum(1 for a, b in zip(mine, _tokens(m['name'])) if a == b)
                    best = max(shared(m) for m in matches)
                    matches = [m for m in matches if shared(m) == best]
                    fewest = min(len(_tokens(m['name'])) for m in matches)
                    matches = [m for m in matches if len(_tokens(m['name'])) == fewest]
                if len(matches) == 1:
                    target = matches[0]
                break
            if target is not None:
                fks.append({'columns': [name], 'references': f"{target['name']}(_id)"})
        out.append({**t, 'fks': fks})
    return out


def _known_tables(source) -> list:
    tables = source.tables or []
    return _mongo_references(tables) if source.kind == DataSource.KIND_MONGO else tables


def _checked(source, tables) -> list:
    """MongoDB's links inferred from names, kept only where the data agrees (mongo.verify_references)."""
    if source.kind != DataSource.KIND_MONGO:
        return tables
    from . import mongo
    return mongo.verify_references(source, tables)


def _choose_tables(ai, source, question, history, notes=None) -> list:
    tables = _known_tables(source)
    if len(tables) <= TABLES_WITHOUT_CHOOSING:
        return _checked(source, tables)
    raw = ai._call_llm(prompt=_CHOOSE.format(dialect=DIALECT_NAMES[source.kind], history=history, question=question,
                                             tables=_choose_list(tables), limit=TABLES_CHOSEN,
                                             notes=_notes_text(notes)),
                       system_prompt='You choose tables. Output only one JSON object.', temperature=0,
                       max_tokens=600, json_mode=True)
    wanted = {str(n).strip().lower() for n in _json(raw).get('tables') or []}
    chosen = [t for t in tables if _table_key(t).lower() in wanted or t['name'].lower() in wanted]
    if not chosen:
        return _checked(source, tables[:TABLES_WITHOUT_CHOOSING])
    chosen = _checked(source, chosen[:TABLES_CHOSEN])
    linked = _with_references(tables, chosen)
    return chosen + _checked(source, linked[len(chosen):])


def _with_references(tables, chosen) -> list:
    """The chosen tables, then the tables they point at by foreign key, up to TABLES_WITH_LINKS: a join's other end
    is there even when the choice left it out."""
    by_name = {}
    for t in tables:
        by_name.setdefault(_table_key(t).lower(), t)
        by_name.setdefault(t['name'].lower(), t)
    out, seen = list(chosen), {id(t) for t in chosen}
    for t in chosen:
        for fk in t.get('fks') or []:
            target = by_name.get(str(fk.get('references') or '').split('(')[0].strip().lower())
            if target is not None and id(target) not in seen and len(out) < TABLES_WITH_LINKS:
                out.append(target)
                seen.add(id(target))
    return out


def _write_aggregation(ai, source, question, history, tables, previous='', values=None) -> dict:
    values = values or {}
    listed = '\n'.join(_table_text(t, values=values.get((t.get('schema') or '', t['name']))) for t in tables)
    prompt = _MONGO.format(today=timezone.localdate().isoformat(), history=history, question=question,
                           previous=previous, tables=listed or '(none)')
    out = _json(ai._call_llm(prompt=prompt, system_prompt='You write MongoDB aggregations. Output only one JSON object.',
                             temperature=0, max_tokens=1500, json_mode=True))
    ask_back = str(out.get('ask_back') or '').strip()[:500]
    collection, pipeline = str(out.get('collection') or '').strip(), out.get('pipeline')
    if ask_back and not pipeline:
        return {'sql': '', 'ask_back': ask_back}
    text = mongo.query_text(collection, pipeline) if collection and isinstance(pipeline, list) else ''
    return {'sql': text, 'ask_back': ask_back, 'chart': out.get('chart')}


def collections(source: DataSource) -> set:
    """A MongoDB source's collection names, as read (a query may only read and join these)."""
    return {t['name'] for t in source.tables or []} if source.kind == DataSource.KIND_MONGO else set()


def _write_sql(ai, source, question, history, tables, previous='', values=None, notes=None) -> dict:
    if source.kind == DataSource.KIND_MONGO:
        return _write_aggregation(ai, source, question, history, tables, previous, values)
    values, notes = values or {}, notes or {}
    listed = '\n'.join(_table_text(t, values=values.get((t.get('schema') or '', t['name'])),
                                   notes=notes.get(t['name'].lower())) for t in tables)
    prompt = _SQL.format(dialect=DIALECT_NAMES[source.kind], today=timezone.localdate().isoformat(),
                         source_name=str(source.name or '').replace('"', "'")[:120],
                         tables=listed or '(none)', history=history,
                         question=question, previous=previous,
                         limit_word='TOP 200' if source.kind == 'mssql' else 'LIMIT 200')
    out = _json(ai._call_llm(prompt=prompt, system_prompt='You write SQL. Output only one JSON object.',
                             temperature=0, max_tokens=1200, json_mode=True))
    return {'sql': str(out.get('sql') or '').strip(), 'ask_back': str(out.get('ask_back') or '').strip()[:500],
            'chart': out.get('chart')}


_UNION_SORT_ERRORS = ('order by term does not match any column in the result set',      # SQLite
                      'invalid union/intersect/except order by clause')                    # PostgreSQL
_COMPOUND = re.compile(r'\b(union|intersect|except)\b', re.I)
_ORDER_BY = re.compile(r'\border\s+by\b', re.I)


def _masked(sql: str) -> str:
    """The query with quoted text and everything inside parentheses blanked, so a keyword found in it is top-level."""
    out, depth, quote = [], 0, ''
    for ch in sql:
        if quote:
            out.append(' ')
            if ch == quote:
                quote = ''
            continue
        if ch in '\'"`':
            quote = ch
            out.append(' ')
        elif ch == '(':
            depth += 1
            out.append(' ')
        elif ch == ')':
            depth = max(0, depth - 1)
            out.append(' ')
        else:
            out.append(' ' if depth else ch)
    return ''.join(out)


def _sorted_outside(sql: str) -> str:
    """A UNION ALL sorted by an expression ("ORDER BY CASE WHEN region = 'Grand total' ..."), which SQLite and
    PostgreSQL refuse, as the same union in a subquery sorted outside it; '' when the query isn't one. The AI wrote it
    again after being shown the error (17 Nov 2026), so it is turned around here, without another AI call."""
    text = sql.strip().rstrip(';').strip()
    masked = _masked(text)
    orders = list(_ORDER_BY.finditer(masked))
    if not orders or not _COMPOUND.search(masked[:orders[-1].start()]):
        return ''
    head, tail = text[:orders[-1].start()].strip(), text[orders[-1].end():].strip()
    return f'SELECT * FROM ({head}) AS sorted_rows ORDER BY {tail}' if head and tail else ''


CHART_TYPES = ('bar', 'line', 'pie')


def _chart(spec, columns, rows):
    """The chart the AI described, when it fits the result: a known type, a label column and a number column that
    are both in the result, and numbers in the number column. Otherwise None: the answer and the table still show."""
    if not isinstance(spec, dict) or not rows:
        return None
    named = {str(c).lower(): c for c in columns}
    kind = str(spec.get('type') or '').strip().lower()
    y = spec.get('y')
    y = (y[0] if y else '') if isinstance(y, list) else y
    x, y = named.get(str(spec.get('x') or '').strip().lower()), named.get(str(y or '').strip().lower())
    if kind not in CHART_TYPES or x is None or y is None or x == y:
        return None
    at, numbers = list(columns).index(y), 0
    for row in rows[:ROWS_TO_SCREEN]:
        value = row[at]
        if value is None or value == '':
            continue
        try:
            float(str(value).replace(',', ''))
        except ValueError:
            return None
        numbers += 1
    if not numbers:
        return None
    return {'type': kind, 'x': x, 'y': y, 'title': str(spec.get('title') or '').strip()[:120] or f'{y} by {x}'}


def _write_answer(ai, question, sql, result, total, chart=None) -> str:
    shown = result['rows'][:ROWS_TO_AI]
    count = f'{total} row(s)' + (f', the first {len(shown)} shown below' if total > len(shown) else '')
    if result['truncated']:
        count = f'more than {len(result["rows"])} rows; the first {len(shown)} shown below'
    rows = '\n'.join(' | '.join('' if v is None else str(v)[:120] for v in row) for row in shown) or '(no rows)'
    # Asked for a picture, the answer said "I can't create graphs": it is told one is drawn under it.
    drawn = (f'A {chart["type"]} chart of {chart["y"]} by {chart["x"]} is drawn from these rows under your answer: '
             "mention it in a few words, and never say you can't draw one.\n") if chart else ''
    prompt = _ANSWER.format(question=question, sql=sql[:2000], count=count, columns=', '.join(result['columns']),
                            rows=f'Rows:\n{rows}', chart=drawn)
    return (ai._call_llm(prompt=prompt, system_prompt='You answer only from the rows given.', temperature=0.2,
                         max_tokens=700) or '').strip()


def ask(company_user, source: DataSource, question: str, conversation=None, ai=None) -> dict:
    """Answer `question` from `source`. Stores the question with its answer and SQL (no rows) and returns, for the
    screen only, up to ROWS_TO_SCREEN rows."""
    started = time.monotonic()
    question = str(question or '').strip()[:2000]
    ai = ai or AnalystAI(company_user.company_id)
    record = DataQuestion(company_id=company_user.company_id, source=source, asked_by=company_user, question=question)
    if conversation:
        record.conversation = conversation
    if not source.tables:
        raise Refused('Test this database first, so its tables are known.')
    history = _history(conversation, source)
    # What the database says about its own tables (comments, its dictionary table, how its periods end): read now,
    # never kept. They describe the structure, not a record, so they are read whether or not the AI may see rows.
    notes = connectors.notes(source, _known_tables(source))
    tables = _choose_tables(ai, source, question, history, notes)
    # The values of the chosen tables' status-like columns, so a filter is spelled as the data has it. Only when the
    # AI may see rows: these are values of the data. Read now, never kept.
    values = connectors.sample_values(source, tables) if source.send_rows_to_ai else {}
    attempt, result, sql, previous, too_long, limit = 0, None, '', '', False, connectors.QUERY_TIMEOUT
    while attempt < QUERY_TRIES:
        attempt += 1
        written = _write_sql(ai, source, question, history, tables, previous, values, notes)
        if written['ask_back'] and not written['sql']:
            record.status, record.answer = DataQuestion.STATUS_ASKED_BACK, written['ask_back']
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.save()
            return _reply(record, rows=[])
        try:
            sql = check_query(written['sql'], source.kind, collections(source))
            # The query gets what is left of the time, at most QUERY_TIMEOUT, so it ends before the site cuts it.
            left = int(ASK_SECONDS - (time.monotonic() - started))
            limit = min(connectors.QUERY_TIMEOUT, max(QUERY_MIN_SECONDS, left))
            try:
                result = connectors.run(source, sql, seconds=limit)
            except Exception as exc:
                turned = _sorted_outside(sql) if any(e in str(exc).lower() for e in _UNION_SORT_ERRORS) else ''
                if not turned:
                    raise
                sql = check_query(turned, source.kind, collections(source))
                result = connectors.run(source, sql, seconds=limit)
            break
        except Refused as exc:
            reason = str(exc)
        except KeyServiceError:
            raise
        except Exception as exc:          # the database's own error: a wrong column, a type, a timeout
            reason = connectors.friendly_error(exc)
            if connectors.timed_out(exc):
                too_long = True
        sql = written['sql']
        previous = f'\nYour last query was:\n{sql[:1500]}\nIt failed: {reason}\nWrite a corrected one.\n'
        logger.info('data analyst: query %s failed (%s): %s', attempt, source.kind, reason[:200])
        # Another try while there is time to write one and run it. It used to need a whole QUERY_TIMEOUT left, so a
        # question that took 10 seconds to reach its first query never got one, even for a query refused at once
        # (17 Nov 2026); the second query now gets the time that is left instead.
        if too_long or ASK_SECONDS - (time.monotonic() - started) < RETRY_SECONDS:
            break
    if result is None:
        record.status, record.sql, record.error = DataQuestion.STATUS_FAILED, sql, reason
        record.answer = (f'The query took longer than {limit} seconds, the most it could take here, so the database '
                         'stopped it. Ask about a smaller part, such as one period or one group.'
                         if too_long else f'The query could not be run: {reason}')
        record.duration_ms = int((time.monotonic() - started) * 1000)
        record.save()
        return _reply(record, rows=[])

    total = len(result['rows'])
    record.sql, record.columns, record.row_count, record.truncated = sql, result['columns'], total, result['truncated']
    record.chart = _chart(written.get('chart'), result['columns'], result['rows'])
    if source.send_rows_to_ai:
        record.answer = _write_answer(ai, question, sql, result, total, record.chart)
        seen = [_Fact(' '.join('' if v is None else str(v) for v in row)) for row in result['rows'][:ROWS_TO_AI]]
        seen.append(_Fact(f'{total} {len(result["columns"])}'))
        # "314,950" in the answer is 314950 in the rows: thousands separators don't make a figure new (3 Nov 2026).
        plain = _THOUSANDS.sub('', record.answer)
        record.flagged = unchecked_numbers(plain, seen, question, timezone.localdate())
    else:
        record.answer = ('No rows matched.' if not total else
                         f'{"More than " if result["truncated"] else ""}{total} row(s): see the '
                         f'{"chart and the " if record.chart else ""}table.')
    record.duration_ms = int((time.monotonic() - started) * 1000)
    record.save()
    return _reply(record, rows=result['rows'][:ROWS_TO_SCREEN], more=total > ROWS_TO_SCREEN or result['truncated'])


def _reply(record: DataQuestion, rows, more=False) -> dict:
    return {'id': record.pk, 'conversation': str(record.conversation), 'question': record.question,
            'answer': record.answer, 'sql': record.sql, 'columns': record.columns, 'rows': rows,
            'row_count': record.row_count, 'more_rows': bool(more or record.truncated), 'flagged': record.flagged,
            'status': record.status, 'error': record.error, 'duration_ms': record.duration_ms,
            'chart': record.chart or None,
            'query_kind': 'mongodb' if record.source.kind == DataSource.KIND_MONGO else 'sql',
            'created_at': record.created_at.isoformat() if record.created_at else None}


def serialize_question(record: DataQuestion) -> dict:
    """A stored question for the history: its answer and SQL, never rows (they are run again when opened)."""
    out = _reply(record, rows=[])
    out.update({'source': {'id': record.source_id, 'name': record.source.name},
                'asked_by': getattr(record.asked_by, 'full_name', '') or '',
                # Its asker deleted the chat: shown to owners and admins in History only.
                'hidden': record.hidden_at is not None})
    return out
