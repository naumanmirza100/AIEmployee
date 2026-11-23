import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, CalendarClock, CheckCircle2, Database, Download, FileUp, Loader2, Lock, MessageCircle, Play, Plus,
  RefreshCw, Send, ShieldCheck, Trash2, Upload,
} from 'lucide-react';

import AgentLocked from '@/components/common/AgentLocked';
import { renderChart } from '@/components/common/ChartRenderer';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import ChatShell from '@/components/shared/ChatShell';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import * as analyst from '@/services/dataAnalystService';
import { getAgentNavItems } from '@/utils/agentNavItems';
import {
  DEFAULT_PORTS, KIND_LABELS, PORT_OPTIONS, isConnectionString, readConnectionString, validPort,
} from '@/utils/connectionString';

/**
 * /data-analyst: the AI Data Analyst. Questions in plain words, answered read-only from the company's own database
 * (PostgreSQL, MySQL / MariaDB, Microsoft SQL Server, MongoDB, or an uploaded SQLite file). Only the question, its answer and its query
 * are kept; the rows come with the answer and are run again when a question is reopened (plan: MDS/01-Plan/week-45).
 * MongoDB (6 Nov 2026): a connection string; the AI writes one read-only aggregation instead of SQL.
 * A .sql dump (7 Nov 2026): uploaded like a SQLite file and read into a SQLite copy on the server (in the background
 * when it is big; the Databases tab checks back until it is ready).
 * Chats (14 Nov 2026): laid out like the PM agent's (components/shared/ChatShell), every chat on the left; a chat stays
 * on the database it started with.
 */
const TABS = [
  { key: 'ask', label: 'Chats' },
  { key: 'databases', label: 'Databases' },
  { key: 'saved', label: 'Saved reports' },
  { key: 'history', label: 'History' },
];

const panel = 'rounded-xl border border-border bg-[var(--panel-2)]';
const field = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-violet-400';

// A database file over the size the server takes is said plainly before it is sent. Sent anyway, the refusal reached
// the screen as "Failed to connect to server" (18 Nov 2026: a 125.6 MB file while the web server took 50 MB).
const tooBig = (file, setup) => {
  const most = Number(setup?.max_file_mb) || 500;
  return file && file.size > most * 1048576
    ? `${file.name} is ${(file.size / 1048576).toFixed(1)} MB; a database file may be up to ${most} MB. For a bigger database, connect to it instead (PostgreSQL, MySQL / MariaDB, SQL Server or MongoDB).`
    : '';
};
const uploadFailed = (e) => (e?.isNetworkError
  ? 'The file did not reach our server. Check the connection and try again: a large file can take a few minutes to send.'
  : e?.message || 'The file could not be added.');

function ResultTable({ columns, rows, more }) {
  if (!columns?.length) return null;
  return (
    <div className="mt-3">
      <div className="max-h-80 overflow-auto rounded-lg border border-border">
        <table className="min-w-full text-xs">
          <thead className="sticky top-0 bg-[var(--panel-2)]">
            <tr>{columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 text-left font-semibold text-muted-foreground">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-border">
                {row.map((v, j) => <td key={j} className="whitespace-nowrap px-3 py-1.5 text-foreground">{v === null ? '—' : String(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {rows.length} row(s) shown{more ? '; there are more: download the CSV for all of them' : ''}.
      </p>
    </div>
  );
}

// A chart asked for in a question (14 Nov 2026): the server keeps only its description ({ type, x, y, title }); it is
// drawn here from the result's rows with the agents' shared renderer. Bars: at most CHART_BARS; a pie: at most
// PIE_PARTS, the smallest together as "Other". The same label twice is added up.
const CHART_BARS = 30;
const PIE_PARTS = 8;

function AnalystChart({ chart, columns, rows }) {
  const xi = (columns || []).indexOf(chart.x);
  const yi = (columns || []).indexOf(chart.y);
  if (xi < 0 || yi < 0 || !rows?.length) return null;
  const points = [];
  rows.forEach((row) => {
    const raw = row[yi];
    const value = Number(String(raw ?? '').replace(/,/g, ''));
    if (raw === null || raw === '' || Number.isNaN(value)) return;
    points.push({ label: row[xi] === null ? '—' : String(row[xi]), value });
  });
  if (!points.length) return null;
  let data;
  let note = '';
  if (chart.type === 'line') {
    data = points;
  } else {
    const sums = new Map();
    points.forEach(({ label, value }) => sums.set(label, (sums.get(label) || 0) + value));
    let entries = [...sums.entries()];
    if (chart.type === 'pie' && entries.length > PIE_PARTS) {
      entries.sort((a, b) => b[1] - a[1]);
      const rest = entries.slice(PIE_PARTS - 1).reduce((total, [, v]) => total + v, 0);
      note = `The ${entries.length - (PIE_PARTS - 1)} smallest are shown together as "Other".`;
      entries = [...entries.slice(0, PIE_PARTS - 1), ['Other', rest]];
    } else if (entries.length > CHART_BARS) {
      note = `The first ${CHART_BARS} of ${entries.length} are shown; the table has them all.`;
      entries = entries.slice(0, CHART_BARS);
    }
    // An object, not a list: the renderer then keeps the labels exactly as the database has them.
    data = Object.fromEntries(entries.map(([label, v]) => [label, Math.round(v * 100) / 100]));
  }
  return (
    <div className="mt-3 rounded-lg border border-border bg-background/40 p-3" data-testid="analyst-chart">
      {renderChart({ type: chart.type, title: chart.title, data })}
      {note && <p className="mt-1 text-[11px] text-muted-foreground">{note}</p>}
    </div>
  );
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/**
 * Save an answered question as a report, or change one (22 Nov 2026): how often it runs, who gets it, and "only
 * when" a figure is above or below a value. It runs its own query again, read-only and without the AI.
 */
function SaveReportDialog({ open, onClose, item, saved, onSaved }) {
  const [logins, setLogins] = useState([]);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const me = getCompanyUser();
  const columns = saved?.columns || item?.columns || [];
  useEffect(() => {
    if (!open) return;
    setError('');
    setForm(saved ? {
      title: saved.title, schedule: saved.schedule, weekday: saved.weekday, month_day: saved.month_day, hour: saved.hour,
      recipient_ids: saved.recipients.map((r) => r.id), alert_op: saved.alert_op || '',
      alert_column: saved.alert_column || columns[0] || '', alert_value: saved.alert_value ?? '',
    } : {
      title: (item?.question || '').slice(0, 120), schedule: 'weekly', weekday: 0, month_day: 1, hour: 9,
      recipient_ids: me?.id ? [me.id] : [], alert_op: '', alert_column: columns[0] || '', alert_value: '',
    });
    analyst.listLogins().then((r) => setLogins((r?.data?.logins || []).filter((l) => l.is_active !== false))).catch(() => {});
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open || !form) return null;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggle = (id) => set('recipient_ids', form.recipient_ids.includes(id)
    ? form.recipient_ids.filter((x) => x !== id) : [...form.recipient_ids, id]);
  const save = async () => {
    setBusy(true); setError('');
    const fields = { ...form, alert_value: form.alert_op ? form.alert_value : null };
    try {
      const r = saved ? await analyst.updateSaved(saved.id, fields) : await analyst.saveQuestion(item.id, fields);
      onSaved?.(r?.data); onClose();
    } catch (e) { setError(e?.message || 'It could not be saved.'); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{saved ? 'Change the saved report' : 'Save as a report'}</DialogTitle>
          <DialogDescription>
            It runs this question's query again, read-only and without the AI, and emails the table.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <label className="block">Name
            <input className={field} value={form.title} maxLength={120} onChange={(e) => set('title', e.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <label className="flex-1 min-w-[140px]">How often
              <select className={field} value={form.schedule} onChange={(e) => set('schedule', e.target.value)}>
                <option value="off">Only when I run it</option>
                <option value="daily">Every day</option>
                <option value="weekly">Every week</option>
                <option value="monthly">Every month</option>
              </select>
            </label>
            {form.schedule === 'weekly' && (
              <label className="flex-1 min-w-[120px]">On
                <select className={field} value={form.weekday} onChange={(e) => set('weekday', Number(e.target.value))}>
                  {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </label>
            )}
            {form.schedule === 'monthly' && (
              <label className="flex-1 min-w-[100px]">On day
                <select className={field} value={form.month_day} onChange={(e) => set('month_day', Number(e.target.value))}>
                  {Array.from({ length: 28 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
                </select>
              </label>
            )}
            {form.schedule !== 'off' && (
              <label className="w-36">At (company time)
                <select className={field} value={form.hour} onChange={(e) => set('hour', Number(e.target.value))}>
                  {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{`${String(h).padStart(2, '0')}:00`}</option>)}
                </select>
              </label>
            )}
          </div>
          <div>
            <p>Send it</p>
            <div className="flex flex-wrap items-center gap-2">
              <select className={`${field} w-auto`} value={form.alert_op} onChange={(e) => set('alert_op', e.target.value)}>
                <option value="">every time</option>
                <option value="above">only when a figure is above</option>
                <option value="below">only when a figure is below</option>
              </select>
              {form.alert_op && (
                <>
                  <input className={`${field} w-28`} inputMode="decimal" value={form.alert_value}
                    onChange={(e) => set('alert_value', e.target.value)} placeholder="10" />
                </>
              )}
            </div>
            {form.alert_op && (
              <label className="mt-2 block">The figure to watch
                <select className={field} value={form.alert_column} onChange={(e) => set('alert_column', e.target.value)}>
                  {columns.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <span className="mt-1 block text-[11px] text-muted-foreground">Read from the first row of the result.</span>
              </label>
            )}
          </div>
          <div>
            <p>To</p>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border p-2">
              {logins.length === 0 && <p className="text-xs text-muted-foreground">Loading…</p>}
              {logins.map((l) => (
                <label key={l.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.recipient_ids.includes(l.id)} onChange={() => toggle(l.id)} />
                  <span>{l.full_name || l.email}</span><span className="text-xs text-muted-foreground">{l.email}</span>
                </label>
              ))}
            </div>
          </div>
          {error && <p className="text-red-300">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !form.title.trim()}>
            {busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <CalendarClock className="mr-1 h-3.5 w-3.5" />} Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Answer({ item, onRun, onCsv }) {
  const [busy, setBusy] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedNote, setSavedNote] = useState('');
  const run = async () => { setBusy('run'); try { await onRun(item); } finally { setBusy(''); } };
  const csv = async () => { setBusy('csv'); try { await onCsv(item); } finally { setBusy(''); } };
  const failed = item.status === 'failed';
  return (
    <div data-testid="analyst-answer" className={`${panel} p-4 ${failed ? 'border-red-500/40' : ''}`}>
      <p className={`whitespace-pre-wrap text-sm ${failed ? 'text-red-300' : 'text-foreground'}`}>{item.answer}</p>
      {item.flagged?.length > 0 && (
        <p className="mt-2 flex items-center gap-1 text-xs text-amber-300">
          <AlertTriangle className="h-3.5 w-3.5" /> Some figures ({item.flagged.slice(0, 5).join(', ')}) are not in the rows the answer was written from; check them in the table.
        </p>
      )}
      {item.chart && item.rows ? <AnalystChart chart={item.chart} columns={item.columns} rows={item.rows} /> : null}
      {item.rows ? <ResultTable columns={item.columns} rows={item.rows} more={item.more_rows} /> : null}
      {item.as_of && <p className="text-[11px] text-muted-foreground">Run again: as of {new Date(item.as_of).toLocaleString()}.</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {item.sql && !item.rows && item.status === 'answered' && (
          <Button size="sm" variant="outline" onClick={run} disabled={!!busy}>
            {busy === 'run' ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1 h-3.5 w-3.5" />} {item.chart ? 'Show the chart and table' : 'Show the table'}
          </Button>
        )}
        {item.sql && item.status === 'answered' && (
          <Button size="sm" variant="outline" onClick={csv} disabled={!!busy}>
            {busy === 'csv' ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1 h-3.5 w-3.5" />} Download CSV
          </Button>
        )}
        {item.sql && item.status === 'answered' && item.id && (
          <Button size="sm" variant="outline" onClick={() => setSaving(true)} data-testid="analyst-save-report">
            <CalendarClock className="mr-1 h-3.5 w-3.5" /> Save or schedule
          </Button>
        )}
        {item.duration_ms != null && <span className="text-[11px] text-muted-foreground">{(item.duration_ms / 1000).toFixed(1)} s</span>}
      </div>
      {savedNote && <p className="mt-2 text-xs text-emerald-300">{savedNote}</p>}
      <SaveReportDialog open={saving} onClose={() => setSaving(false)} item={item}
        onSaved={(s) => setSavedNote(`Saved as "${s?.title}": ${s?.when}. It's under Saved reports.`)} />
      {item.sql && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-violet-300">{item.query_kind === 'mongodb' ? 'The MongoDB query that ran' : 'The SQL that ran'}</summary>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-background p-3 text-xs text-foreground">{item.sql}</pre>
        </details>
      )}
    </div>
  );
}

/**
 * The chats (14 Nov 2026), laid out like the PM agent's: every chat on the left, whichever database it is about; the
 * database is chosen above the composer. A chat stays on its database once it has started (the server refuses
 * another one in it): picking another database offers the last chat on that one, or a new chat. Owners and admins
 * can add a database file (SQLite, or a .sql dump) from here too.
 */
function AskTab({ setup, sources, reload }) {
  const usable = useMemo(() => sources.filter((s) => s.status === 'ready'), [sources]);
  const byId = useMemo(() => new Map(sources.map((s) => [String(s.id), s])), [sources]);
  const [chats, setChats] = useState([]);
  const [loadingChats, setLoadingChats] = useState(true);
  const [chatId, setChatId] = useState(null);
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [newSourceId, setNewSourceId] = useState(() => String(usable[0]?.id || ''));
  const [switching, setSwitching] = useState(null);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const fileRef = useRef(null);
  const bottom = useRef(null);
  const opening = useRef(null);

  const chat = chats.find((c) => c.id === chatId) || null;
  const sourceId = chat ? String(chat.source.id) : newSourceId;
  const source = byId.get(sourceId) || (chat ? chat.source : null);
  const locked = !!chatId;

  const loadChats = useCallback(async () => {
    try {
      const res = await analyst.listChats();
      setChats(res?.data || []);
    } catch { /* the list is a convenience */ } finally {
      setLoadingChats(false);
    }
  }, []);
  useEffect(() => { loadChats(); }, [loadChats]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [items]);
  // A new chat's database must be one that can be asked; after a removal, fall back to the first.
  useEffect(() => {
    if (!usable.some((s) => String(s.id) === newSourceId)) setNewSourceId(String(usable[0]?.id || ''));
  }, [usable, newSourceId]);
  // A dump being read in the background: look again until it is ready, so it appears in the list.
  const loading = sources.some((s) => s.status === 'loading');
  useEffect(() => {
    if (!loading) return undefined;
    const timer = setTimeout(reload, 5000);
    return () => clearTimeout(timer);
  }, [loading, sources, reload]);

  const newChat = (id) => {
    opening.current = null;
    setChatId(null); setItems([]); setSwitching(null); setError(''); setNote('');
    if (id) setNewSourceId(String(id));
  };
  const openChat = async (c) => {
    opening.current = c.id;
    setChatId(c.id); setItems([]); setSwitching(null); setError(''); setNote(''); setLoadingItems(true);
    try {
      const res = await analyst.listQuestions({ conversation: c.id });
      if (opening.current === c.id) setItems([...(res?.data || [])].reverse().map((q) => ({ ...q, rows: null })));
    } catch (e) {
      if (opening.current === c.id) setError(e?.message || 'The chat could not be opened.');
    } finally {
      if (opening.current === c.id) setLoadingItems(false);
    }
  };
  const removeChat = async (c) => {
    if (!window.confirm(`Delete the chat "${c.title}"? It leaves your list; owners and admins still see its questions in History.`)) return;
    try {
      await analyst.deleteChat(c.id);
      if (c.id === chatId) newChat();
      loadChats();
    } catch (e) { setError(e?.message || 'The chat could not be deleted.'); }
  };

  // Another database in a chat that has started: this chat stays as it is; offer the last chat on that database
  // (the list is newest first), or a new one.
  const pickSource = (value) => {
    setError('');
    if (!locked) { setNewSourceId(value); return; }
    if (value === sourceId) { setSwitching(null); return; }
    setSwitching({ source: byId.get(value), chat: chats.find((c) => String(c.source.id) === value) || null });
  };

  const runAgain = async (item) => {
    try {
      const res = await analyst.runAgain(item.id);
      setItems((all) => all.map((x) => (x.id === item.id ? { ...x, ...res.data, rows: res.data.rows, more_rows: res.data.more_rows } : x)));
    } catch (e) { setError(e?.message || 'The query could not be run again.'); }
  };
  const csv = async (item) => {
    try { await analyst.downloadCsv(item.id); } catch (e) { setError(e?.message || 'The CSV could not be made.'); }
  };

  const submit = async (event) => {
    event?.preventDefault();
    const q = question.trim();
    if (!q || !sourceId || busy) return;
    if (source && source.status && source.status !== 'ready') {
      setError(`${source.name} can't be asked right now (${source.status === 'loading' ? 'it is still being read' : 'it could not be reached'}).`);
      return;
    }
    setBusy(true); setError(''); setNote(''); setSwitching(null);
    setItems((all) => [...all, { pending: true, question: q }]);
    setQuestion('');
    try {
      const res = await analyst.ask(Number(sourceId), q, chatId);
      setItems((all) => [...all.filter((x) => !x.pending), res.data]);
      if (!chatId) { opening.current = res.data.conversation; setChatId(res.data.conversation); }
      loadChats();
    } catch (e) {
      setItems((all) => all.filter((x) => !x.pending));
      setQuestion(q);
      setError(e?.message || 'The question could not be answered just now.');
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file) => {
    if (!file) return;
    if (tooBig(file, setup)) {
      setError(tooBig(file, setup)); setNote('');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setUploading(true); setError(''); setNote('');
    try {
      const name = file.name.replace(/\.(sql\.gz|sqlite3|sqlite|db3|db|sql|gz)$/i, '') || file.name;
      const res = await analyst.uploadSqlite(file, { name, send_rows_to_ai: true, everyone_may_ask: true });
      const added = res?.data;
      await reload();
      if (added?.status === 'ready') {
        newChat(added.id);
        setNote(`${added.name} is added. Ask your first question about it below.`);
      } else if (added?.status === 'loading') {
        newChat();
        setNote(`${added.name} is being read from its dump. It can be picked here when it is ready; the Databases tab shows how far it is.`);
      } else {
        setError(added?.last_error || res?.message || 'The file could not be read.');
      }
    } catch (e) {
      setError(uploadFailed(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const listed = chats.map((c) => ({
    id: c.id, title: c.title, updatedAt: c.last_at,
    detail: `${c.source.name}${c.questions > 1 ? ` · ${c.questions} questions` : ''}`, raw: c,
  }));
  const options = locked && chat && !usable.some((s) => String(s.id) === sourceId) ? [chat.source, ...usable] : usable;
  const nothingToAsk = !usable.length && !locked;

  const composer = (
    <div className="mx-3 my-3 rounded-xl border border-border px-3 py-3 sm:mx-4">
      {switching && (
        <div data-testid="analyst-switch" className="mb-2 rounded-lg border border-violet-500/30 bg-violet-500/10 p-2.5 text-xs text-foreground">
          <p>This chat stays on <b>{source?.name}</b>. To ask <b>{switching.source?.name}</b>:</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {switching.chat && (
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openChat(switching.chat)} data-testid="analyst-switch-open">
                Open your last chat on it
              </Button>
            )}
            <Button size="sm" className="h-7 text-xs" onClick={() => newChat(switching.source?.id)} data-testid="analyst-switch-new">
              <Plus className="mr-1 h-3.5 w-3.5" /> New chat on {switching.source?.name}
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setSwitching(null)}>Stay here</Button>
          </div>
        </div>
      )}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5"
          title={locked ? `This chat is about ${source?.name || 'this database'}. Pick another database to open your last chat on it or start a new one.` : 'The database this chat asks'}>
          {locked ? <Lock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <Database className="h-3.5 w-3.5 shrink-0 text-violet-300" />}
          <select id="analyst-source" aria-label="Database" data-testid="analyst-source-select" value={sourceId}
            onChange={(e) => pickSource(e.target.value)} disabled={busy || !options.length}
            className={`h-8 w-full min-w-0 flex-1 rounded-md border border-border px-2 text-xs text-foreground outline-none focus:border-violet-400 ${locked ? 'bg-muted/40' : 'bg-background'}`}>
            {!options.length && <option value="">No database yet</option>}
            {options.map((s) => <option key={s.id} value={String(s.id)}>{s.name} ({s.kind_label})</option>)}
          </select>
        </div>
        {setup?.can_manage && (
          <>
            <input ref={fileRef} type="file" className="hidden" accept=".db,.sqlite,.sqlite3,.db3,.sql,.gz"
              onChange={(e) => upload(e.target.files?.[0])} data-testid="analyst-chat-file" />
            <Button type="button" size="sm" variant="outline" className="h-8 shrink-0 text-xs" disabled={uploading || busy}
              onClick={() => fileRef.current?.click()}
              title={`Add a database file: a SQLite file, or a .sql dump from MySQL, PostgreSQL, SQLite or SQL Server (up to ${setup?.max_file_mb || 500} MB)`}>
              {uploading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Upload className="mr-1 h-3.5 w-3.5" />}
              Add database file
            </Button>
          </>
        )}
      </div>
      <form onSubmit={submit} className="flex items-start gap-2">
        <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={2000} rows={1}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(e); } }}
          placeholder={source ? `Ask about ${source.name}, e.g. How many orders did we have last month, by city?` : 'Add a database first'}
          aria-label="Question" data-testid="analyst-question" disabled={busy || nothingToAsk}
          className="min-h-[40px] flex-1 resize-none text-sm" />
        <Button type="submit" size="icon" className="h-[40px] w-10 shrink-0" disabled={busy || !question.trim() || nothingToAsk} title="Ask">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
      {error && <p className="mt-2 text-xs text-red-300" data-testid="analyst-error">{error}</p>}
      {note && <p className="mt-2 text-xs text-emerald-300" data-testid="analyst-note">{note}</p>}
    </div>
  );

  return (
    <ChatShell
      icon={Database} title="AI Data Analyst" badge="Read-only"
      description="Answers come from your database, read-only. Only each question, its answer and its query are kept."
      chats={listed} selectedId={chatId} loadingChats={loadingChats} testId="analyst-chats"
      onSelect={(c) => openChat(c.raw)} onNew={() => newChat()} onDelete={(c) => removeChat(c.raw)}
      emptyChatsText="No chats yet. Pick a database below and ask a question."
      composer={composer}
    >
      {nothingToAsk && (
        <div className="mx-auto mt-6 max-w-md text-center">
          <Database className="mx-auto mb-3 h-10 w-10 text-violet-400" />
          <h3 className="text-lg font-semibold text-foreground">No database to ask yet</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {setup?.can_manage
              ? 'Add a database file below, or a PostgreSQL, MySQL, SQL Server or MongoDB connection under Databases.'
              : 'An owner or admin adds one under Databases: a PostgreSQL, MySQL, SQL Server or MongoDB connection, a SQLite file, or a .sql dump.'}
          </p>
        </div>
      )}
      {!nothingToAsk && !locked && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-10 text-center text-muted-foreground">
          <MessageCircle className="mb-3 h-10 w-10 opacity-50" />
          <p className="font-medium text-foreground">New chat{source ? ` on ${source.name}` : ''}</p>
          <p className="mt-1 max-w-md text-sm">Ask about your data in plain words, e.g. "How many orders did we have last month, by city?" Follow-up questions in the same chat build on the earlier ones.</p>
        </div>
      )}
      {loadingItems && <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>}
      {items.map((item, i) => (
        <div key={item.id || `p${i}`} className="space-y-2">
          <div className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-violet-600 px-4 py-2 text-sm text-white">{item.question}</div></div>
          {item.pending
            ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Writing and running the query…</div>
            : <Answer item={item} onRun={runAgain} onCsv={csv} />}
        </div>
      ))}
      <div ref={bottom} />
    </ChatShell>
  );
}

const READ_ONLY_USER = {
  postgres: "CREATE USER pp_reader WITH PASSWORD 'a long password';\nGRANT CONNECT ON DATABASE your_db TO pp_reader;\nGRANT USAGE ON SCHEMA public TO pp_reader;\nGRANT SELECT ON ALL TABLES IN SCHEMA public TO pp_reader;\nALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pp_reader;",
  mysql: "CREATE USER 'pp_reader'@'%' IDENTIFIED BY 'a long password';\nGRANT SELECT ON your_db.* TO 'pp_reader'@'%';",
  mssql: "CREATE LOGIN pp_reader WITH PASSWORD = 'a long password';\nUSE your_db;\nCREATE USER pp_reader FOR LOGIN pp_reader;\nALTER ROLE db_datareader ADD MEMBER pp_reader;\n-- Azure SQL: CREATE USER pp_reader WITH PASSWORD = '...'; in the database, then the same ALTER ROLE.\n-- Azure SQL firewall: the server's Networking page, add our address.",
  mongodb: "MongoDB Atlas: Database Access > Add New Database User > Built-in Role: Only read any database.\nYour own server (mongosh):\nuse admin\ndb.createUser({ user: 'pp_reader', pwd: 'a long password', roles: [{ role: 'read', db: 'your_db' }] })",
};

const KINDS = [['postgres', 'PostgreSQL'], ['mysql', 'MySQL / MariaDB'], ['mssql', 'SQL Server'], ['mongodb', 'MongoDB'], ['sqlite', 'File: SQLite or .sql']];
const STRING_PLACEHOLDER = {
  postgres: 'postgresql://user:password@host:5432/database?sslmode=require',
  mysql: 'mysql://user:password@host:3306/database',
  mssql: 'Server=tcp:yourserver.database.windows.net,1433;Database=your_db;User ID=pp_reader;Password=...;Encrypt=True;',
};
const PORT_PLACEHOLDER = { postgres: 'Port (5432)', mysql: 'Port (3306)', mssql: 'Port (1433)' };

// A port box with the kind's common ports to pick (the default first); any other port can be typed.
function PortPicker({ kind, value, onChange }) {
  const options = PORT_OPTIONS[kind] || [];
  return (
    <div className="space-y-1.5">
      <input className={field} inputMode="numeric" placeholder={PORT_PLACEHOLDER[kind] || 'Port'} value={value}
        onChange={(e) => onChange(e.target.value.replace(/\s/g, ''))} aria-label="Port" data-testid="analyst-port" />
      <div className="flex flex-wrap gap-1.5">
        {options.map(([port, label]) => (
          <button key={port} type="button" onClick={() => onChange(String(port))} data-testid="analyst-port-option"
            className={`rounded-full border px-2 py-0.5 text-[11px] ${String(port) === String(value).trim() ? 'border-violet-400 bg-violet-500/20 text-violet-100' : 'border-border text-muted-foreground hover:border-violet-400'}`}>
            {port} · {label}
          </button>
        ))}
      </div>
      {String(value).trim() !== '' && !validPort(value) && <p className="text-xs text-red-300">A port is a number from 1 to 65535.</p>}
    </div>
  );
}

const SSL_TEXT = {
  required: 'Required',
  offered: 'Used when the server offers it (add ?sslmode=require to insist)',
  off: 'Off',
};

// What a pasted connection string holds, shown as it is typed: the port can be changed, and what the string lacks
// (a password, the database, the user) can be given here.
function StringReading({ reading, port, onPort, portTouched, form, set }) {
  if (!reading) return null;
  if (reading.error) return <p className="text-xs text-amber-300" data-testid="analyst-string-reading">{reading.error}</p>;
  const { kind } = reading;
  const row = 'grid grid-cols-[88px_minmax(0,1fr)] items-start gap-x-3';
  const label = 'pt-0.5 text-xs text-muted-foreground';
  let portNote = '';
  if (reading.port && portTouched && String(reading.port) !== String(port).trim()) portNote = `The string says ${reading.port}; this one is used.`;
  else if (reading.port && !portTouched) portNote = 'From the string.';
  else if (!reading.port && !portTouched && !reading.problem) portNote = `Not in the string: ${KIND_LABELS[kind]}'s default.`;
  return (
    <div className="space-y-2 rounded-lg border border-border bg-background/40 p-3 text-sm text-foreground" data-testid="analyst-string-reading">
      <p className="text-xs font-semibold text-muted-foreground">Read from the string: {KIND_LABELS[kind]}</p>
      <div className={row}><span className={label}>Host</span><span className="break-all">{reading.host}</span></div>
      <div className={row}>
        <span className={label}>Port</span>
        {reading.srv ? <span className="text-muted-foreground">Set by the cluster's DNS record (a mongodb+srv string has no port)</span>
          : reading.servers ? (
            <span className="break-all">{reading.servers.map((s) => `${s.host}:${s.port || DEFAULT_PORTS.mongodb}`).join(', ')}
              <span className="block text-xs text-muted-foreground">Several servers: each with its own port, {DEFAULT_PORTS.mongodb} where the string gives none.</span></span>
          ) : (
            <div className="space-y-1">
              <PortPicker kind={kind} value={port} onChange={onPort} />
              {portNote && <p className="text-xs text-muted-foreground" data-testid="analyst-port-note">{portNote}</p>}
            </div>
          )}
      </div>
      <div className={row}>
        <span className={label}>Database</span>
        {reading.database ? <span className="break-all">{reading.database}</span>
          : kind === 'mongodb' ? <span className="text-muted-foreground">Not in the string: give it below, or the only one the user can see is used.</span>
            : <input className={field} placeholder="Not in the string: the database name" value={form.database} onChange={set('database')} aria-label="Database" />}
      </div>
      <div className={row}>
        <span className={label}>User</span>
        {reading.username ? <span className="break-all">{reading.username}</span>
          : <input className={field} placeholder="Not in the string: the user (read-only)" value={form.username} onChange={set('username')} aria-label="User" />}
      </div>
      <div className={row}>
        <span className={label}>Password</span>
        {reading.hasPassword ? <span className="text-muted-foreground">In the string (not shown)</span>
          : <input className={field} type="password" placeholder="Not in the string: the password" value={form.password} onChange={set('password')} aria-label="Password" autoComplete="new-password" />}
      </div>
      <div className={row}>
        <span className={label}>Encryption</span>
        <span>{reading.srv ? 'Required (a mongodb+srv string always is)' : SSL_TEXT[reading.ssl]}</span>
      </div>
      {reading.options.length > 0 && (
        <div className={row}><span className={label}>Options</span><span className="break-all">{reading.options.join(', ')}</span></div>
      )}
      {reading.problem && <p className="text-xs text-amber-300">{reading.problem}</p>}
    </div>
  );
}

function AddDatabase({ setup, logins, onAdded }) {
  const [mode, setMode] = useState('postgres');
  const [form, setForm] = useState({ name: '', host: '', port: String(DEFAULT_PORTS.postgres), database: '', username: '', password: '', use_ssl: true, connection_string: '' });
  const [useString, setUseString] = useState(false);
  // A port typed or picked for a pasted string (null: the string's own, else the kind's default).
  const [stringPort, setStringPort] = useState(null);
  const [moved, setMoved] = useState(false);
  const [file, setFile] = useState(null);
  const [sendRows, setSendRows] = useState(true);
  const [everyone, setEveryone] = useState(true);
  const [allowed, setAllowed] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const reading = useMemo(() => readConnectionString(form.connection_string), [form.connection_string]);
  const stringShown = mode === 'mongodb' || (mode !== 'sqlite' && useString);
  const readKind = reading && !reading.error ? reading.kind : null;
  const needsPort = Boolean(readKind && reading.problem);
  const shownPort = stringPort ?? (needsPort ? '' : String(reading?.port || DEFAULT_PORTS[readKind] || ''));
  const portBad = stringShown
    ? Boolean(readKind && !reading.srv && !reading.servers && (needsPort || shownPort.trim() !== '') && !validPort(shownPort))
    : mode !== 'sqlite' && form.port.trim() !== '' && !validPort(form.port);

  // Another kind: its default port, unless a port of one's own was typed (one of the old kind's list gives way).
  const chooseMode = (key) => {
    setMode(key);
    setMessage(null);
    const listed = (PORT_OPTIONS[mode] || []).map(([port]) => String(port));
    setForm((f) => ({ ...f, port: !f.port.trim() || listed.includes(f.port.trim()) ? String(DEFAULT_PORTS[key] ?? '') : f.port }));
  };
  // A string for another kind moves the form to that kind; a port picked for the old kind is dropped.
  const takeString = (value) => {
    const next = readConnectionString(value);
    const kind = next && !next.error ? next.kind : null;
    setForm((f) => ({ ...f, connection_string: value }));
    if (kind !== readKind) setStringPort(null);
    if (kind && kind !== mode) chooseMode(kind);
    if (kind && kind !== 'mongodb') setUseString(true);
  };
  // A whole connection string pasted in the Host box is read as one.
  const onHost = (e) => {
    const { value } = e.target;
    if (isConnectionString(value)) {
      setForm((f) => ({ ...f, host: '' }));
      setUseString(true);
      setMoved(true);
      takeString(value.trim());
      return;
    }
    setForm((f) => ({ ...f, host: value }));
  };

  // Beside a string: the port when one was typed or picked, and what the string lacks when it is given here.
  const stringExtras = () => {
    if (!readKind) return {};
    const extras = {};
    if (stringPort != null && stringPort.trim() && !reading.srv && !reading.servers) extras.port = stringPort.trim();
    if (!reading.database && readKind !== 'mongodb' && form.database.trim()) extras.database = form.database.trim();
    if (!reading.username && form.username.trim()) extras.username = form.username.trim();
    if (!reading.hasPassword && form.password) extras.password = form.password;
    return extras;
  };

  const bigFile = mode === 'sqlite' ? tooBig(file, setup) : '';

  const submit = async (event) => {
    event.preventDefault();
    if (bigFile) {
      setMessage({ ok: false, text: bigFile });
      return;
    }
    setBusy(true); setMessage(null);
    const shared = { name: form.name, send_rows_to_ai: sendRows, everyone_may_ask: everyone, allowed_user_ids: everyone ? [] : allowed };
    try {
      const res = mode === 'sqlite'
        ? await analyst.uploadSqlite(file, shared)
        : mode === 'mongodb'
          ? await analyst.addConnection({ ...shared, kind: 'mongodb', connection_string: form.connection_string, database: form.database, ...stringExtras() })
          : await analyst.addConnection(useString
            ? { ...shared, connection_string: form.connection_string, ...stringExtras() }
            : { ...shared, kind: mode, host: form.host, port: form.port, database: form.database, username: form.username, password: form.password, use_ssl: form.use_ssl });
      const ok = res?.data?.status === 'ready' || res?.data?.status === 'loading';
      setMessage({ ok, text: ok ? res.message : (res?.data?.last_error || res.message) });
      onAdded?.();
      if (ok) {
        setForm((f) => ({ ...f, password: '', connection_string: '' }));
        setStringPort(null);
        setMoved(false);
      }
    } catch (e) {
      setMessage({ ok: false, text: mode === 'sqlite' ? uploadFailed(e) : e?.message || 'It could not be added.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className={`${panel} space-y-4 p-5`} data-testid="analyst-add">
      <h3 className="text-base font-semibold text-foreground">Add a database</h3>
      <div className="flex flex-wrap gap-2">
        {KINDS.map(([key, label]) => (
          <Button key={key} type="button" size="sm" variant={mode === key ? 'default' : 'outline'} onClick={() => { chooseMode(key); setMoved(false); }}>{label}</Button>
        ))}
      </div>
      <input className={field} placeholder="A name, e.g. Shop database" value={form.name} onChange={set('name')} aria-label="Name" />
      {mode === 'sqlite' ? (
        <>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
            <FileUp className="h-5 w-5" />
            <span>{file ? `${file.name} (${(file.size / 1048576).toFixed(1)} MB)` : `Choose a SQLite file, or a .sql dump from MySQL, PostgreSQL, SQLite or SQL Server (.sql or .sql.gz), up to ${setup?.max_file_mb || 500} MB`}</span>
            <input type="file" className="hidden" accept=".db,.sqlite,.sqlite3,.db3,.sql,.gz" onChange={(e) => { setFile(e.target.files?.[0] || null); setMessage(null); }} data-testid="analyst-file" />
          </label>
          {bigFile && <p className="text-sm text-red-300" data-testid="analyst-file-too-big">{bigFile}</p>}
        </>
      ) : (
        <>
          <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-3 text-xs text-violet-100">
            <p className="flex items-center gap-1 font-semibold"><ShieldCheck className="h-4 w-4" /> Before you connect</p>
            {mode === 'mongodb'
              ? <p className="mt-1">Allow our server's address <b data-testid="analyst-server-ip">{setup?.server_ip || '—'}</b> (in MongoDB Atlas: Network Access, Add IP Address), and give us a user that can only read:</p>
              : <p className="mt-1">Allow our server's address <b data-testid="analyst-server-ip">{setup?.server_ip || '—'}</b> in your database's firewall, and give us a user that can only read. For example:</p>}
            <pre className="mt-2 overflow-x-auto rounded bg-background/60 p-2 text-[11px] text-foreground">{READ_ONLY_USER[mode]}</pre>
          </div>
          {mode === 'mongodb' ? (
            <div className="space-y-3">
              <input className={field} placeholder="mongodb+srv://pp_reader:password@cluster0.abcde.mongodb.net/your_db"
                value={form.connection_string} onChange={(e) => takeString(e.target.value)} aria-label="Connection string" data-testid="analyst-mongo-string" />
              <StringReading reading={reading} port={shownPort} onPort={setStringPort} portTouched={stringPort != null} form={form} set={set} />
              <input className={field} placeholder="Database name, if the string has none" value={form.database} onChange={set('database')} aria-label="Database" />
              <p className="text-xs text-muted-foreground">The AI reads a sample of each collection to learn its fields; it keeps their names and types, never a value.</p>
            </div>
          ) : (<>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={useString} onChange={(e) => setUseString(e.target.checked)} /> Paste a connection string instead
          </label>
          {useString ? (
            <div className="space-y-3">
              <input className={field} placeholder={STRING_PLACEHOLDER[mode] || STRING_PLACEHOLDER.postgres}
                value={form.connection_string} onChange={(e) => takeString(e.target.value)} aria-label="Connection string" data-testid="analyst-sql-string" />
              {moved && <p className="text-xs text-muted-foreground">That was a whole connection string, so it is read here.</p>}
              <StringReading reading={reading} port={shownPort} onPort={setStringPort} portTouched={stringPort != null} form={form} set={set} />
            </div>
          ) : (
            <div className="grid items-start gap-3 sm:grid-cols-2">
              <input className={field} placeholder="Host, or paste a whole connection string" value={form.host} onChange={onHost} aria-label="Host" />
              <PortPicker kind={mode} value={form.port} onChange={(port) => setForm((f) => ({ ...f, port }))} />
              <input className={field} placeholder="Database name" value={form.database} onChange={set('database')} aria-label="Database" />
              <input className={field} placeholder="User (read-only)" value={form.username} onChange={set('username')} aria-label="User" />
              <input className={field} type="password" placeholder="Password" value={form.password} onChange={set('password')} aria-label="Password" autoComplete="new-password" />
              <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={form.use_ssl} onChange={set('use_ssl')} /> Require an encrypted connection (SSL)</label>
            </div>
          )}
          </>)}
        </>
      )}
      <label className="flex items-start gap-2 text-sm text-muted-foreground">
        <input type="checkbox" className="mt-1" checked={sendRows} onChange={(e) => setSendRows(e.target.checked)} />
        <span>Let the AI read the first rows of each result to write its answer. Off: it only writes the query, and the answer is the table.</span>
      </label>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} /> Everyone in the company may ask it
      </label>
      {!everyone && (
        <div className="grid gap-1 sm:grid-cols-2">
          {logins.map((l) => (
            <label key={l.id} className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={allowed.includes(l.id)} onChange={(e) => setAllowed((a) => (e.target.checked ? [...a, l.id] : a.filter((x) => x !== l.id)))} />
              {l.full_name || l.email}
            </label>
          ))}
          <p className="text-xs text-muted-foreground sm:col-span-2">Owners and admins may always ask.</p>
        </div>
      )}
      {message && <p className={`text-sm ${message.ok ? 'text-emerald-300' : 'text-red-300'}`} data-testid="analyst-add-message">{message.text}</p>}
      <Button type="submit" disabled={busy || portBad || Boolean(bigFile) || (mode === 'sqlite' && !file) || (mode === 'mongodb' && !form.connection_string.trim())}>
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Database className="mr-2 h-4 w-4" />} Add and test
      </Button>
    </form>
  );
}

function DatabasesTab({ setup, sources, reload }) {
  const [logins, setLogins] = useState([]);
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState('');
  useEffect(() => {
    if (setup?.can_manage) analyst.listLogins().then((r) => setLogins((r?.data?.logins || []).filter((l) => l.is_active !== false))).catch(() => {});
  }, [setup]);
  // A dump being read in the background: look again every few seconds until it is ready or has failed.
  const loading = sources.some((s) => s.status === 'loading');
  useEffect(() => {
    if (!loading) return undefined;
    const timer = setTimeout(reload, 4000);
    return () => clearTimeout(timer);
  }, [loading, sources, reload]);

  const test = async (s) => {
    setBusy(`t${s.id}`); setNote('');
    try { const r = await analyst.testSource(s.id); setNote(r.message); } catch (e) { setNote(e?.message || 'The test failed.'); }
    finally { setBusy(''); reload(); }
  };
  const remove = async (s) => {
    if (!window.confirm(`Remove "${s.name}"? Its questions and answers are removed too, and an uploaded file is deleted.`)) return;
    setBusy(`r${s.id}`);
    try { const r = await analyst.removeSource(s.id); setNote(r.message); } catch (e) { setNote(e?.message || 'It could not be removed.'); }
    finally { setBusy(''); reload(); }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_440px] [&>*]:min-w-0">
      <div className="space-y-3">
        {note && <p className="text-sm text-muted-foreground">{note}</p>}
        {sources.length === 0 && <p className={`${panel} p-6 text-sm text-muted-foreground`}>No database yet.</p>}
        {sources.map((s) => (
          <div key={s.id} className={`${panel} p-4`} data-testid="analyst-source">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-foreground">{s.name}</p>
                <p className="text-xs text-muted-foreground">
                  {s.kind_label}{s.host ? ` · ${s.host}${s.port ? `:${s.port}` : ''} · ${s.database} · ${s.username}` : ''}{s.file_name ? ` · ${s.file_name}` : ''}
                </p>
              </div>
              <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${s.status === 'ready' ? 'bg-emerald-500/15 text-emerald-300' : s.status === 'failed' ? 'bg-red-500/15 text-red-300' : s.status === 'loading' ? 'bg-violet-500/15 text-violet-200' : 'bg-muted text-muted-foreground'}`}>
                {s.status === 'ready' ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.status === 'loading' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                {s.status === 'ready' ? `Ready · ${s.tables_count} ${s.kind === 'mongodb' ? 'collections' : 'tables'}` : s.status === 'failed' ? (s.load ? 'Could not be read' : 'Could not connect') : s.status === 'loading' ? 'Loading the dump…' : 'Not tested'}
              </span>
            </div>
            {s.last_error && <p className="mt-2 text-sm text-red-300">{s.last_error}</p>}
            {s.load && !s.load.loading && s.status === 'ready' && (
              <p className="mt-2 text-xs text-muted-foreground" data-testid="analyst-load">
                From {s.load.dump_name} ({s.load.dialect_label} dump): {s.load.tables} tables, {(s.load.rows || 0).toLocaleString()} rows{s.load.skipped ? `; ${s.load.skipped} other statements skipped (${s.load.skipped_kinds.join(', ')})` : ''}.
                {s.load.problems?.length > 0 && <span className="block text-amber-300">{s.load.problems[0]}</span>}
              </p>
            )}
            {s.load?.loading && <p className="mt-2 text-xs text-muted-foreground">Reading {s.load.dump_name} ({s.load.dialect_label} dump). This page shows when it is ready.</p>}
            {s.user_can_write && (
              <p className="mt-2 flex items-center gap-1 text-xs text-amber-300"><AlertTriangle className="h-3.5 w-3.5" /> This user can change data. It is only ever used to read, but a read-only user is safer.</p>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              {s.send_rows_to_ai ? 'The AI reads the first rows of each result.' : 'The AI never sees rows: answers are the table.'}{' '}
              {s.everyone_may_ask ? 'Everyone may ask it.' : 'Only the chosen people may ask it.'}
            </p>
            <CompanyNotes source={s} canManage={!!setup?.can_manage} onSaved={reload} />
            {setup?.can_manage && (
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" onClick={() => test(s)} disabled={!!busy}>
                  {busy === `t${s.id}` ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />} {s.kind === 'mongodb' ? 'Test and read collections' : 'Test and read tables'}
                </Button>
                <Button size="sm" variant="outline" className="text-red-300" onClick={() => remove(s)} disabled={!!busy}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Remove
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
      {setup?.can_manage
        ? <AddDatabase setup={setup} logins={logins} onAdded={reload} />
        : <p className={`${panel} h-fit p-4 text-sm text-muted-foreground`}>Only an owner or admin of your company can add or remove a database.</p>}
    </div>
  );
}

/**
 * What the company says its data means (22 Nov 2026): the agent reads it before it picks tables and writes a query.
 * Most of the misses on the test databases were meanings the AI had to guess. Owners and admins write it.
 */
function CompanyNotes({ source, canManage, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(source.company_notes || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setText(source.company_notes || ''); }, [source.company_notes]);
  if (!canManage && !source.company_notes) return null;
  const save = async () => {
    setBusy(true); setError('');
    try { await analyst.updateSource(source.id, { company_notes: text }); setEditing(false); onSaved?.(); }
    catch (e) { setError(e?.message || 'The notes could not be saved.'); }
    finally { setBusy(false); }
  };
  return (
    <div className="mt-3 rounded-lg border border-border p-3" data-testid="analyst-company-notes">
      <p className="text-xs font-semibold text-foreground">What our data means</p>
      {editing ? (
        <>
          <Textarea rows={6} value={text} maxLength={8000} className="mt-1 text-xs" onChange={(e) => setText(e.target.value)}
            placeholder={'Revenue is invoices.total_usd of paid invoices.\nAn active customer ordered in the last 90 days.\nAmounts are in PKR unless the currency column says otherwise.'} />
          <p className="mt-1 text-[11px] text-muted-foreground">
            The agent reads this before every query. Say what your words mean, which table holds what, and what to leave out.
          </p>
          {error && <p className="mt-1 text-xs text-red-300">{error}</p>}
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={save} disabled={busy}>{busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null} Save</Button>
            <Button size="sm" variant="outline" onClick={() => { setEditing(false); setText(source.company_notes || ''); }}>Cancel</Button>
          </div>
        </>
      ) : (
        <>
          {source.company_notes
            ? <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">{source.company_notes}</p>
            : <p className="mt-1 text-xs text-muted-foreground">Nothing yet. Tell the agent what your words mean: it reads this before every query.</p>}
          {canManage && (
            <Button size="sm" variant="outline" className="mt-2" onClick={() => setEditing(true)}>
              {source.company_notes ? 'Change' : 'Add notes'}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

/** Saved reports (22 Nov 2026): run again on a schedule and emailed, or only when a figure crosses a line. */
function SavedTab() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [shown, setShown] = useState({});
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => (
    analyst.listSaved().then((r) => setItems(r?.data || [])).catch((e) => { setItems([]); setError(e?.message || ''); })
  ), []);
  useEffect(() => { load(); }, [load]);
  const run = async (s, send) => {
    setBusy(`${send ? 's' : 'r'}${s.id}`); setError('');
    try { const r = await analyst.runSaved(s.id, send); setShown((m) => ({ ...m, [s.id]: r?.data })); load(); }
    catch (e) { setError(e?.message || 'It could not run.'); }
    finally { setBusy(''); }
  };
  const toggle = async (s) => {
    try { await analyst.updateSaved(s.id, { is_active: !s.is_active }); load(); } catch (e) { setError(e?.message || ''); }
  };
  const remove = async (s) => {
    if (!window.confirm(`Remove "${s.title}"? Nobody gets it any more.`)) return;
    try { await analyst.removeSaved(s.id); load(); } catch (e) { setError(e?.message || ''); }
  };
  if (items === null) return <Loader2 className="h-6 w-6 animate-spin text-primary" />;
  const outcome = (s, r) => (r.emailed > 0 ? `Sent to ${r.emailed} ${r.emailed === 1 ? 'person' : 'people'}.`
    : r.outcome === 'quiet' ? `${s.alert_column} is ${r.value}: not ${s.alert_op} ${s.alert_value}, so nothing would be sent.`
      : 'As of now. Nothing was sent.');
  const badge = { sent: 'bg-emerald-500/15 text-emerald-300', quiet: 'bg-muted text-muted-foreground', failed: 'bg-red-500/15 text-red-300' };
  const said = { sent: 'Sent', quiet: 'Ran, nothing to send', failed: 'Could not run' };
  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-red-300">{error}</p>}
      {items.length === 0 && (
        <p className={`${panel} p-6 text-sm text-muted-foreground`}>
          No saved reports yet. Under any answer, press "Save or schedule" to have it run again by itself and emailed.
        </p>
      )}
      {items.map((s) => {
        const result = shown[s.id];
        return (
          <div key={s.id} className={`${panel} p-4`} data-testid="analyst-saved">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-semibold text-foreground">{s.title}</p>
                <p className="text-xs text-muted-foreground">
                  {s.source.name} · {s.is_active ? s.when : 'Paused'}
                  {s.alert_op ? ` · only when ${s.alert_column} is ${s.alert_op} ${s.alert_value}` : ''}
                </p>
                <p className="text-xs text-muted-foreground">
                  To {s.recipients.map((r) => r.name).join(', ') || 'nobody'}{s.created_by ? ` · set up by ${s.created_by}` : ''}
                </p>
              </div>
              {s.last_status && (
                <span className={`rounded-full px-2 py-0.5 text-xs ${badge[s.last_status] || ''}`}>
                  {said[s.last_status]}{s.last_run_at ? ` · ${new Date(s.last_run_at).toLocaleString()}` : ''}
                </span>
              )}
            </div>
            {s.last_status === 'failed' && s.last_error && <p className="mt-2 text-sm text-red-300">{s.last_error}</p>}
            {s.is_active && s.next_run_at && (
              <p className="mt-1 text-[11px] text-muted-foreground">Next: {new Date(s.next_run_at).toLocaleString()}</p>
            )}
            {result && (
              <>
                <p className="mt-2 text-xs text-muted-foreground">{outcome(s, result)}</p>
                <ResultTable columns={result.columns} rows={result.rows} more={result.more_rows} />
              </>
            )}
            {s.may_change && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => run(s, false)} disabled={!!busy}>
                  {busy === `r${s.id}` ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1 h-3.5 w-3.5" />} Run now
                </Button>
                <Button size="sm" variant="outline" onClick={() => run(s, true)} disabled={!!busy}>
                  {busy === `s${s.id}` ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Send className="mr-1 h-3.5 w-3.5" />} Send now
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(s)}>Change</Button>
                <Button size="sm" variant="outline" onClick={() => toggle(s)}>{s.is_active ? 'Pause' : 'Resume'}</Button>
                <Button size="sm" variant="outline" className="text-red-300" onClick={() => remove(s)}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Remove
                </Button>
              </div>
            )}
          </div>
        );
      })}
      <SaveReportDialog open={!!editing} onClose={() => setEditing(null)} saved={editing} onSaved={load} />
    </div>
  );
}

function HistoryTab({ setup }) {
  const [all, setAll] = useState(false);
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    analyst.listQuestions(all ? { all: '1' } : {}).then((r) => setRows(r?.data || [])).catch((e) => setError(e?.message || ''));
  }, [all]);
  const run = async (item) => {
    try { const r = await analyst.runAgain(item.id); setOpen({ ...item, ...r.data }); } catch (e) { setError(e?.message || ''); }
  };
  const csv = async (item) => { try { await analyst.downloadCsv(item.id); } catch (e) { setError(e?.message || ''); } };
  return (
    <div className="space-y-3">
      {setup?.can_manage && (
        <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Everyone's questions</label>
      )}
      {error && <p className="text-sm text-red-300">{error}</p>}
      <div className={`${panel} overflow-x-auto`}>
        <table className="min-w-full text-sm">
          <thead><tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-2">When</th><th className="px-4 py-2">Database</th>{all && <th className="px-4 py-2">Who</th>}<th className="px-4 py-2">Question</th><th className="px-4 py-2">Rows</th>
          </tr></thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.id} className="cursor-pointer border-t border-border hover:bg-accent" onClick={() => setOpen({ ...q, rows: null })}>
                <td className="whitespace-nowrap px-4 py-2 text-muted-foreground">{new Date(q.created_at).toLocaleString()}</td>
                <td className="px-4 py-2">{q.source?.name}</td>
                {all && <td className="px-4 py-2">{q.asked_by}</td>}
                <td className="px-4 py-2 text-foreground">
                  {q.question}
                  {q.hidden && <span className="ml-2 whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground" title="Its asker deleted this chat; it is kept here as a record">chat deleted</span>}
                </td>
                <td className="px-4 py-2 text-muted-foreground">{q.status === 'answered' ? q.row_count : q.status === 'failed' ? 'failed' : 'asked back'}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">No questions yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="space-y-2">
          <p className="text-sm font-semibold text-foreground">{open.question}</p>
          <Answer item={open} onRun={run} onCsv={csv} />
        </div>
      )}
    </div>
  );
}

export default function DataAnalystPage() {
  const navigate = useNavigate();
  const { purchasedModules, allPurchases, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  // ?tab=saved opens Saved reports: the reports' emails link there (22 Nov 2026).
  const [tab, setTab] = useState(() => {
    const wanted = new URLSearchParams(window.location.search).get('tab');
    return TABS.some((t) => t.key === wanted) ? wanted : 'ask';
  });
  const [setup, setSetup] = useState(null);
  const [sources, setSources] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { if (!companyUser) navigate('/company/login'); }, [companyUser, navigate]);
  const bought = purchasedModules.includes('data_analyst_agent');
  const reload = useCallback(() => (
    analyst.listSources().then((r) => setSources(r?.data || [])).catch((e) => { setSources([]); setError(e?.message || ''); })
  ), []);
  useEffect(() => {
    if (!modulesLoaded || !bought) return;
    analyst.getSetup().then((r) => setSetup(r?.data || null)).catch(() => {});
    reload();
  }, [modulesLoaded, bought, reload]);

  const handleLogout = async () => { await logoutCompany(); navigate('/company/login'); };
  const lapsed = allPurchases.find((p) => p.module_name === 'data_analyst_agent')?.status;

  return (
    <>
      <Helmet><title>AI Data Analyst | Pay Per Project</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar icon={Database} title="AI Data Analyst" subtitle="Questions answered from your own database"
          user={companyUser} userRole="Company User" onLogout={handleLogout} showNavTabs activeSection="data-analyst"
          navItems={getAgentNavItems(purchasedModules, 'data-analyst', navigate)} />
        <div className="container mx-auto max-w-full px-4 py-6 sm:px-10">
          {!modulesLoaded ? (
            <div className="flex justify-center pt-16"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>
          ) : !bought ? (
            lapsed ? <div className="flex justify-center pt-10"><AgentLocked title="AI Data Analyst" moduleKey="data_analyst_agent" status={lapsed} /></div> : (
              <div className={`${panel} mx-auto mt-10 max-w-md p-6 text-center`}>
                <Lock className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
                <h1 className="text-lg font-semibold text-foreground">The AI Data Analyst is not part of your plan</h1>
                <p className="mt-1 text-sm text-muted-foreground">It answers questions in plain words from your own database, read-only, and never copies your data.</p>
                <Button className="mt-4 w-full" onClick={() => navigate('/company/dashboard/ai-agents')}>See AI agents</Button>
              </div>
            )
          ) : (
            <>
              <div className="mb-4 flex flex-wrap gap-2" role="tablist">
                {TABS.map((t) => (
                  <Button key={t.key} role="tab" aria-selected={tab === t.key} variant={tab === t.key ? 'default' : 'outline'} size="sm" onClick={() => setTab(t.key)}>{t.label}</Button>
                ))}
              </div>
              {error && <p className="mb-3 text-sm text-red-300">{error}</p>}
              {sources === null ? <Loader2 className="h-6 w-6 animate-spin text-primary" />
                : tab === 'ask' ? <AskTab setup={setup} sources={sources} reload={reload} />
                  : tab === 'databases' ? <DatabasesTab setup={setup} sources={sources} reload={reload} />
                    : tab === 'saved' ? <SavedTab />
                      : <HistoryTab setup={setup} />}
            </>
          )}
        </div>
      </div>
    </>
  );
}
