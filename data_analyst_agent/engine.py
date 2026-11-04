"""A question answered from a company's database (plan: MDS/01-Plan/week-45/2026-11-03_Data-Analyst-Agent-Plan.md).

1. Choose the tables (an AI call, only for a database with many tables).
2. Write the SQL for that database's dialect (an AI call), from those tables' columns, types and keys.
3. Check it (guards.check_sql) and run it read-only (connectors.run). A refusal or a database error goes back to the
   AI once, with the reason, for a corrected query.
4. Write the answer from the result's first rows (an AI call), unless the source keeps rows from the AI; every number
   in it is checked against those rows (the Company Assistant's check).
5. Store the question, answer, SQL, column names and row count. Never a row.
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

from . import connectors
from .guards import Refused, check_sql
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
DIALECT_NAMES = {'postgres': 'PostgreSQL', 'mysql': 'MySQL/MariaDB', 'sqlite': 'SQLite', 'mssql': 'Microsoft SQL Server'}


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

Return only JSON: {{"sql": "...", "ask_back": ""}}"""

_ANSWER = """You answer a question from the result of a query that just ran on the company's own database.

Question: {question}

The query: {sql}

Result: {count}. Columns: {columns}
{rows}

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


def _write_sql(ai, source, question, history, tables, previous='') -> dict:
    prompt = _SQL.format(dialect=DIALECT_NAMES[source.kind], today=timezone.localdate().isoformat(),
                         tables='\n'.join(_table_text(t) for t in tables) or '(none)', history=history,
                         question=question, previous=previous,
                         limit_word='TOP 200' if source.kind == 'mssql' else 'LIMIT 200')
    out = _json(ai._call_llm(prompt=prompt, system_prompt='You write SQL. Output only one JSON object.',
                             temperature=0, max_tokens=1200, json_mode=True))
    return {'sql': str(out.get('sql') or '').strip(), 'ask_back': str(out.get('ask_back') or '').strip()[:500]}


def _write_answer(ai, question, sql, result, total) -> str:
    shown = result['rows'][:ROWS_TO_AI]
    count = f'{total} row(s)' + (f', the first {len(shown)} shown below' if total > len(shown) else '')
    if result['truncated']:
        count = f'more than {len(result["rows"])} rows; the first {len(shown)} shown below'
    rows = '\n'.join(' | '.join('' if v is None else str(v)[:120] for v in row) for row in shown) or '(no rows)'
    prompt = _ANSWER.format(question=question, sql=sql[:2000], count=count, columns=', '.join(result['columns']),
                            rows=f'Rows:\n{rows}')
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
            sql = check_sql(written['sql'], source.kind)
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
    if source.send_rows_to_ai:
        record.answer = _write_answer(ai, question, sql, result, total)
        seen = [_Fact(' '.join('' if v is None else str(v) for v in row)) for row in result['rows'][:ROWS_TO_AI]]
        seen.append(_Fact(f'{total} {len(result["columns"])}'))
        # "314,950" in the answer is 314950 in the rows: thousands separators don't make a figure new (3 Nov 2026).
        plain = _THOUSANDS.sub('', record.answer)
        record.flagged = unchecked_numbers(plain, seen, question, timezone.localdate())
    else:
        record.answer = ('No rows matched.' if not total else
                         f'{"More than " if result["truncated"] else ""}{total} row(s): see the table.')
    record.duration_ms = int((time.monotonic() - started) * 1000)
    record.save()
    return _reply(record, rows=result['rows'][:ROWS_TO_SCREEN], more=total > ROWS_TO_SCREEN or result['truncated'])


def _reply(record: DataQuestion, rows, more=False) -> dict:
    return {'id': record.pk, 'conversation': str(record.conversation), 'question': record.question,
            'answer': record.answer, 'sql': record.sql, 'columns': record.columns, 'rows': rows,
            'row_count': record.row_count, 'more_rows': bool(more or record.truncated), 'flagged': record.flagged,
            'status': record.status, 'error': record.error, 'duration_ms': record.duration_ms,
            'created_at': record.created_at.isoformat() if record.created_at else None}


def serialize_question(record: DataQuestion) -> dict:
    """A stored question for the history: its answer and SQL, never rows (they are run again when opened)."""
    out = _reply(record, rows=[])
    out.update({'source': {'id': record.source_id, 'name': record.source.name},
                'asked_by': getattr(record.asked_by, 'full_name', '') or ''})
    return out
