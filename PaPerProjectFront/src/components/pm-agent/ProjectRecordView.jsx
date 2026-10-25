import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import {
  Loader2, FolderPlus, ListPlus, UserCheck, CalendarClock, Gavel, CheckCircle2, Users, AlertTriangle, Flag,
  Trash2, Pencil, RefreshCw, Copy, Printer, ClipboardList, Lightbulb, Clock,
} from 'lucide-react';

// One project's story on a page or two: what was decided and done, in date order, then what is due, late and at
// risk, and who is doing what. Built by the server from stored entries (project_manager_agent/project_record.py);
// opening it makes no AI call.

const KIND = {
  created: { icon: FolderPlus, color: 'text-violet-300' },
  tasks: { icon: ListPlus, color: 'text-sky-300' },
  assigned: { icon: UserCheck, color: 'text-sky-300' },
  dates: { icon: CalendarClock, color: 'text-amber-300' },
  decision: { icon: Gavel, color: 'text-violet-300' },
  done: { icon: CheckCircle2, color: 'text-emerald-300' },
  meeting: { icon: Users, color: 'text-fuchsia-300' },
  risk: { icon: AlertTriangle, color: 'text-red-300' },
  priority: { icon: Flag, color: 'text-amber-300' },
  deleted: { icon: Trash2, color: 'text-white/50' },
  edit: { icon: Pencil, color: 'text-white/50' },
};

const SEVERITY = {
  critical: 'bg-red-900/60 text-red-200', high: 'bg-red-900/40 text-red-300',
  medium: 'bg-amber-900/40 text-amber-300', low: 'bg-white/[0.06] text-white/60',
};

const longDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};
const shortDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—');
const dueWords = (days) => {
  if (days === null || days === undefined) return '';
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} late`;
  if (days === 0) return 'due today';
  return `in ${days} day${days === 1 ? '' : 's'}`;
};

// The record as plain text, for Copy and for the printed page.
function asText(r) {
  const p = r.project;
  const lines = [`${p.name} — project record`, `${p.status} · ${p.done}/${p.tasks} tasks done · start ${shortDate(p.start)} · deadline ${shortDate(p.deadline)}`, ''];
  lines.push('TIMELINE');
  if (r.earlier) lines.push(`(${r.earlier})`);
  r.timeline.forEach((day) => {
    lines.push(longDate(day.date));
    day.items.forEach((i) => lines.push(`  • ${i.text}`));
  });
  const section = (title, rows) => { if (rows.length) { lines.push('', title, ...rows.map((x) => `  • ${x}`)); } };
  section('DECISIONS', r.decisions.map((d) => `${shortDate(d.date)} — ${d.text} (${d.source})`));
  section('LATE', r.due.late.map((t) => `${t.title} — ${t.owner}, due ${shortDate(t.due)} (${dueWords(t.days)})`));
  section('DUE IN THE NEXT 7 DAYS', r.due.soon.map((t) => `${t.title} — ${t.owner}, ${shortDate(t.due)}`));
  section('ACTIONS FROM MEETINGS', r.meeting_actions.map((a) => `${a.action} — ${a.owner || 'no owner'}${a.deadline ? `, ${a.deadline}` : ''}`));
  section('RISKS', r.risks.map((k) => `${k.text} [${k.severity}] (${k.source})`));
  section("WHO'S DOING WHAT", r.team.map((m) => `${m.name}: ${m.open} open, ${m.done} done${m.late ? `, ${m.late} late` : ''}`));
  section('NEXT STEPS', r.next_steps);
  return lines.join('\n');
}

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function printRecord(r) {
  const win = window.open('', '_blank', 'width=900,height=1000');
  if (!win) return false;
  const body = escapeHtml(asText(r)).replace(/^([A-Z][A-Z' 0-9]+)$/gm, '<h3>$1</h3>');
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(r.project.name)} — project record</title>
    <style>body{font:13px/1.5 system-ui,sans-serif;margin:32px;color:#111}pre{white-space:pre-wrap;font:inherit;margin:0}
    h3{font-size:12px;letter-spacing:.06em;color:#5b21b6;margin:14px 0 2px}</style></head>
    <body><pre>${body}</pre><script>window.onload=()=>{window.print()}</script></body></html>`);
  win.document.close();
  return true;
}

function Section({ icon: Icon, title, color = 'text-violet-300', children, testid }) {
  return (
    <Card className="bg-white/[0.02] border-white/[0.06]" data-testid={testid}>
      <CardHeader className="pb-2">
        <CardTitle className={`text-sm flex items-center gap-1.5 ${color}`}><Icon className="w-4 h-4" /> {title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm text-white/70">{children}</CardContent>
    </Card>
  );
}

export default function ProjectRecordView({ projectId }) {
  const { toast } = useToast();
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!projectId) { setRecord(null); return; }
    setLoading(true);
    try {
      const res = await pmAgentService.getProjectRecord(projectId);
      setRecord(res?.data || null);
    } catch (e) {
      setRecord(null);
      toast({ title: 'Could not load the project record', description: apiErrorMessage(e, ''), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [projectId]);

  if (!projectId) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-white/40" data-testid="record-pick-project">
        <ClipboardList className="w-12 h-12 mb-3 text-white/35" />
        <p className="text-sm text-center">Choose a project above to see its record: decisions, work handed out, due dates and risks.</p>
      </div>
    );
  }
  if (loading && !record) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div>;
  }
  if (!record) return null;

  const p = record.project;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText(record));
      toast({ title: 'Copied', description: 'The project record is on the clipboard.' });
    } catch {
      toast({ title: 'Copy did not work', description: 'Use Print instead.', variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-4" data-testid="project-record">
      {/* Where the project stands */}
      <Card className="bg-black/30 border-white/[0.06]">
        <CardContent className="pt-5 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-white">{p.name}</h3>
              <p className="text-xs text-white/55 mt-0.5">
                {p.status} · {p.priority} priority · start {shortDate(p.start)} · deadline {shortDate(p.deadline)}
                {p.days_left !== null && p.days_left !== undefined && (
                  <span className={p.days_left < 0 ? 'text-red-300' : p.days_left <= 7 ? 'text-amber-300' : ''}>
                    {' '}({p.days_left < 0 ? `${-p.days_left} days past` : `${p.days_left} days left`})
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={load} disabled={loading}>
                <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
              </Button>
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={copy} data-testid="record-copy">
                <Copy className="w-3.5 h-3.5 mr-1" /> Copy
              </Button>
              <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => printRecord(record) || copy()}>
                <Printer className="w-3.5 h-3.5 mr-1" /> Print / PDF
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            {[['Tasks', p.tasks], ['Done', p.done], ['Open', p.open], ['Late', p.late]].map(([label, n]) => (
              <div key={label} className="rounded-md bg-white/[0.03] py-2">
                <div className={`text-lg font-semibold ${label === 'Late' && n ? 'text-red-300' : 'text-white'}`}>{n}</div>
                <div className="text-[11px] text-white/45">{label}</div>
              </div>
            ))}
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-[11px] text-white/45">
              <span>{p.pct_done}% of tasks done</span>
              {p.pct_time !== null && p.pct_time !== undefined && <span>{p.pct_time}% of the time to the deadline gone</span>}
            </div>
            <div className="h-1.5 rounded bg-white/[0.06] relative overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-emerald-500/70" style={{ width: `${p.pct_done}%` }} />
              {p.pct_time !== null && p.pct_time !== undefined && (
                <div className="absolute inset-y-0 w-0.5 bg-amber-300" style={{ left: `${p.pct_time}%` }} title="Today" />
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* What happened, in date order */}
        <Card className="bg-white/[0.02] border-white/[0.06] lg:col-span-2" data-testid="record-timeline">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-violet-300 flex items-center gap-1.5"><Clock className="w-4 h-4" /> Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {record.earlier && <p className="text-xs text-white/40 mb-3">{record.earlier}</p>}
            {record.timeline.length === 0 && <p className="text-sm text-white/45">Nothing recorded yet.</p>}
            <ol className="relative border-l border-white/[0.08] ml-2 space-y-4">
              {record.timeline.map((day) => (
                <li key={day.date} className="ml-4">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-violet-500/80" />
                  <div className="text-xs font-medium text-white/80">{longDate(day.date)}</div>
                  <ul className="mt-1 space-y-1">
                    {day.items.map((item, i) => {
                      const k = KIND[item.kind] || KIND.edit;
                      const Icon = k.icon;
                      return (
                        <li key={i} className="flex items-start gap-2 text-sm text-white/70">
                          <Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${k.color}`} />
                          <span>{item.text}</span>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Section icon={Gavel} title={`Decisions (${record.decisions.length})`} testid="record-decisions">
            {record.decisions.length === 0 ? <p className="text-white/45">None recorded yet.</p> : record.decisions.map((d, i) => (
              <div key={i}><span className="text-white/45 text-xs mr-1.5">{shortDate(d.date)}</span>{d.text}
                <span className="text-[11px] text-white/35"> · {d.source}</span></div>
            ))}
          </Section>

          <Section icon={CalendarClock} title="Due and late" color="text-amber-300" testid="record-due">
            {record.due.late.length === 0 && record.due.soon.length === 0 && <p className="text-white/45">Nothing late or due this week.</p>}
            {record.due.late.map((t) => (
              <div key={t.id} className="flex justify-between gap-2"><span>{t.title} <span className="text-white/40 text-xs">· {t.owner}</span></span>
                <span className="text-red-300 text-xs whitespace-nowrap">{dueWords(t.days)}</span></div>
            ))}
            {record.due.more_late > 0 && <p className="text-xs text-white/40">and {record.due.more_late} more late</p>}
            {record.due.soon.map((t) => (
              <div key={t.id} className="flex justify-between gap-2"><span>{t.title} <span className="text-white/40 text-xs">· {t.owner}</span></span>
                <span className="text-amber-300 text-xs whitespace-nowrap">{shortDate(t.due)}</span></div>
            ))}
            {record.meeting_actions.length > 0 && (
              <div className="pt-2 border-t border-white/[0.06]">
                <div className="text-[11px] text-white/45 mb-1">Actions from recent meetings</div>
                {record.meeting_actions.map((a, i) => (
                  <div key={i} className="text-sm">{a.action} <span className="text-white/40 text-xs">· {a.owner || 'no owner'}{a.deadline ? ` · ${a.deadline}` : ''}</span></div>
                ))}
              </div>
            )}
          </Section>

          <Section icon={AlertTriangle} title={`Risks (${record.risks.length})`} color="text-red-300" testid="record-risks">
            {record.risks.length === 0 ? <p className="text-white/45">No open risks.</p> : record.risks.map((r, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase shrink-0 ${SEVERITY[r.severity] || SEVERITY.medium}`}>{r.severity}</span>
                <span>{r.text} <span className="text-[11px] text-white/35">· {r.source}</span></span>
              </div>
            ))}
          </Section>

          <Section icon={Users} title="Who's doing what" color="text-sky-300" testid="record-team">
            {record.team.length === 0 ? <p className="text-white/45">No tasks yet.</p> : record.team.map((m) => (
              <div key={m.name} className="flex justify-between"><span className={m.name === 'No owner' ? 'text-amber-300' : ''}>{m.name}</span>
                <span className="text-xs text-white/50">{m.open} open · {m.done} done{m.late ? <span className="text-red-300"> · {m.late} late</span> : null}</span></div>
            ))}
          </Section>

          {record.next_steps.length > 0 && (
            <Section icon={Lightbulb} title="Suggested next steps" color="text-emerald-300" testid="record-next">
              {record.next_steps.map((s, i) => <div key={i} className="flex gap-2"><span className="text-emerald-400">→</span><span>{s}</span></div>)}
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
