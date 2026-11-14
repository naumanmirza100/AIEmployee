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
# The table list for choosing stays under about 6,000 tokens: fewer columns a table first, then names only. All 294
# tables of a real database with 25 columns each came to 11,536 tokens, more than a Groq key allows a minute (3 Nov 2026).
CHOOSE_LIST_CHARS = 20000
ROWS_TO_AI = 100
ROWS_TO_SCREEN = 200
HISTORY_TURNS = 6
# The site's web server cuts a request at 60 seconds. A query stopped at the time limit isn't tried again, and another
# try is made only while it still fits: two 30-second queries came to 66 seconds and the screen got an error page.
ASK_SECONDS = 50

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


def _table_text(t, full=True, columns=25) -> str:
    if not full:
        names = ', '.join(c['name'] for c in t['columns'][:columns])
        return f"- {_table_key(t)} ({names})" if names else f"- {_table_key(t)}"
    cols = ', '.join(f"{c['name']} {c['type']}{' PK' if c.get('pk') else ''}" for c in t['columns'])
    fks = ''.join(f"; {', '.join(fk['columns'])} -> {fk['references']}" for fk in t.get('fks') or [])
    return f"- {_table_key(t)}{' (view)' if t.get('kind') == 'view' else ''}: {cols}{fks}"


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

{history}Question: {question}

Return only JSON: {{"tables": ["name", ...]}} with at most {limit} names, spelled exactly as listed. Include the tables
needed to join. If none fits, return {{"tables": []}}."""

_SQL = """You write one read-only SQL query for a {dialect} database, to answer a question about a company's own data.

Today is {today}.

Tables (only these exist; columns with their types, PK marks the primary key, -> a foreign key):
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
- An empty result: say nothing matched.
- Don't explain the SQL. Under 120 words. No heading."""


def _choose_list(tables) -> str:
    """The tables to choose from, each with as many of its columns as the size budget allows."""
    for columns in (25, 15, 10, 6, 4, 2, 0):
        text = '\n'.join(_table_text(t, full=False, columns=columns) for t in tables)
        if len(text) <= CHOOSE_LIST_CHARS:
            return text
    return text[:CHOOSE_LIST_CHARS]


def _choose_tables(ai, source, question, history) -> list:
    tables = source.tables or []
    if len(tables) <= TABLES_WITHOUT_CHOOSING:
        return tables
    raw = ai._call_llm(prompt=_CHOOSE.format(dialect=DIALECT_NAMES[source.kind], history=history, question=question,
                                             tables=_choose_list(tables), limit=TABLES_CHOSEN),
                       system_prompt='You choose tables. Output only one JSON object.', temperature=0,
                       max_tokens=600, json_mode=True)
    wanted = {str(n).strip().lower() for n in _json(raw).get('tables') or []}
    chosen = [t for t in tables if _table_key(t).lower() in wanted or t['name'].lower() in wanted]
    return chosen[:TABLES_CHOSEN] or tables[:TABLES_WITHOUT_CHOOSING]


def _write_aggregation(ai, source, question, history, tables, previous='') -> dict:
    prompt = _MONGO.format(today=timezone.localdate().isoformat(), history=history, question=question,
                           previous=previous, tables='\n'.join(_table_text(t) for t in tables) or '(none)')
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


def _write_sql(ai, source, question, history, tables, previous='') -> dict:
    if source.kind == DataSource.KIND_MONGO:
        return _write_aggregation(ai, source, question, history, tables, previous)
    prompt = _SQL.format(dialect=DIALECT_NAMES[source.kind], today=timezone.localdate().isoformat(),
                         tables='\n'.join(_table_text(t) for t in tables) or '(none)', history=history,
                         question=question, previous=previous,
                         limit_word='TOP 200' if source.kind == 'mssql' else 'LIMIT 200')
    out = _json(ai._call_llm(prompt=prompt, system_prompt='You write SQL. Output only one JSON object.',
                             temperature=0, max_tokens=1200, json_mode=True))
    return {'sql': str(out.get('sql') or '').strip(), 'ask_back': str(out.get('ask_back') or '').strip()[:500],
            'chart': out.get('chart')}


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
    tables = _choose_tables(ai, source, question, history)
    attempt, result, sql, previous, too_long = 0, None, '', '', False
    while attempt < 2:
        attempt += 1
        written = _write_sql(ai, source, question, history, tables, previous)
        if written['ask_back'] and not written['sql']:
            record.status, record.answer = DataQuestion.STATUS_ASKED_BACK, written['ask_back']
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.save()
            return _reply(record, rows=[])
        try:
            sql = check_query(written['sql'], source.kind, collections(source))
            result = connectors.run(source, sql)
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
        if too_long or time.monotonic() - started + connectors.QUERY_TIMEOUT + 10 > ASK_SECONDS:
            break
    if result is None:
        record.status, record.sql, record.error = DataQuestion.STATUS_FAILED, sql, reason
        record.answer = (f'The query took longer than {connectors.QUERY_TIMEOUT} seconds, the most a question may take, '
                         'so the database stopped it. Ask about a smaller part, such as one period or one group.'
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
