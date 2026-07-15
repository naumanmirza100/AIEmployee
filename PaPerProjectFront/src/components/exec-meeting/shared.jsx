// Shared, self-contained helpers, style constants, and stateless components for
// the AI Executive Meeting Assistant dashboard. Extracted from
// ExecMeetingDashboard.jsx so the main file can focus on the stateful panels.
// Nothing here closes over dashboard state — everything takes props/args.

import React, { useState } from 'react';
import { format } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar as CalendarIcon, Trash2, Loader2, Check, Search, X, SlidersHorizontal } from 'lucide-react';

// ── Markdown → HTML renderer (violet theme, matches this dashboard) ─────────
export function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => {
    let out = escape(s);
    out = out.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-white/10 text-violet-200 text-[0.85em] font-mono">$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-violet-200">$1</strong>');
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em class="italic text-white/85">$2</em>');
    return out;
  };
  const getIndent = (line) => {
    const m = line.match(/^(\s*)(?:[-*•]|\d+\.)\s+/);
    if (!m) return -1;
    return Math.floor(m[1].length / 2);
  };
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let listDepth = -1;
  const closeLists = (target) => { while (listDepth > target) { out.push('</ul>'); listDepth--; } };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (t.startsWith('|') && t.endsWith('|')) {
      closeLists(-1);
      const rows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map((c) => c.trim()).filter(Boolean);
        if (cells.length && cells.every((c) => /^[-:\s]+$/.test(c))) { j++; continue; }
        rows.push(cells);
        j++;
      }
      i = j;
      if (rows.length) {
        out.push('<div class="my-4 overflow-x-auto rounded-lg border border-white/10">');
        out.push('<table class="w-full text-sm"><thead><tr class="bg-violet-500/10">');
        rows[0].forEach((c) => out.push(`<th class="px-3 py-2 text-left font-semibold text-violet-300">${inline(c)}</th>`));
        out.push('</tr></thead><tbody>');
        rows.slice(1).forEach((r, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-white/[0.02]' : ''} hover:bg-white/[0.04]">`);
          r.forEach((c) => out.push(`<td class="px-3 py-2 border-t border-white/5 text-white/85">${inline(c)}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }
    if (/^---+$/.test(t)) { closeLists(-1); out.push('<hr class="my-5 border-white/20" />'); i++; continue; }
    if (/^#### /.test(t)) { closeLists(-1); out.push(`<h4 class="text-sm font-semibold mt-3 mb-1.5 text-violet-100/90">${inline(t.slice(5))}</h4>`); i++; continue; }
    if (/^### /.test(t))  { closeLists(-1); out.push(`<h3 class="text-base font-bold mt-5 mb-2 text-violet-200">${inline(t.slice(4))}</h3>`); i++; continue; }
    if (/^## /.test(t))   { closeLists(-1); out.push(`<h2 class="text-lg font-bold mt-6 mb-2.5 text-violet-300 border-b border-violet-500/30 pb-1.5">${inline(t.slice(3))}</h2>`); i++; continue; }
    if (/^# /.test(t))    { closeLists(-1); out.push(`<h1 class="text-2xl font-bold mt-2 mb-4 text-white">${inline(t.slice(2))}</h1>`); i++; continue; }
    const indent = getIndent(line);
    if (indent >= 0) {
      const content = t.replace(/^[\s]*(?:[-*•]|\d+\.)\s+/, '');
      if (indent > listDepth) {
        while (listDepth < indent) {
          const isTop = listDepth === -1;
          out.push(`<ul class="${isTop ? 'pl-4 my-2 space-y-1.5' : 'pl-5 mt-1 mb-1 space-y-1 border-l border-white/[0.06]'}">`);
          listDepth++;
        }
      } else if (indent < listDepth) {
        closeLists(indent);
      }
      const bullet = indent === 0 ? '•' : '›';
      const color  = indent === 0 ? 'text-violet-400' : 'text-white/30';
      const textColor = indent === 0 ? 'text-white/90' : 'text-white/70';
      out.push(
        `<li class="text-sm leading-relaxed ${textColor} flex gap-2 ${indent === 0 ? 'pt-1' : ''}">` +
        `<span class="${color} shrink-0 mt-0.5">${bullet}</span><span>${inline(content)}</span></li>`,
      );
      i++; continue;
    }
    if (t === '' && listDepth >= 0) {
      let k = i + 1;
      while (k < lines.length && lines[k].trim() === '') k++;
      if (k >= lines.length || getIndent(lines[k]) < 0) closeLists(-1);
      i++; continue;
    }
    if (t === '') { i++; continue; }
    closeLists(-1);
    out.push(`<p class="text-sm leading-relaxed text-white/85 my-2.5">${inline(t)}</p>`);
    i++;
  }
  closeLists(-1);
  return out.join('\n');
}

// Display ISO datetime string as UTC — avoids browser timezone shifting the date
export const fmtUtc = (isoStr) => {
  if (!isoStr) return '—';
  const [datePart, timePart] = isoStr.replace('Z', '').replace('+00:00', '').split('T');
  if (!datePart) return '—';
  const [y, mo, d] = datePart.split('-');
  if (!timePart) return `${mo}/${d}/${y}`;
  const [h, m] = timePart.split(':');
  const hour = parseInt(h, 10);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h12 = hour % 12 || 12;
  return `${mo}/${d}/${y}, ${h12}:${m} ${ampm}`;
};

// ── Style constants ─────────────────────────────────────────────────────────
export const CARD_STYLE = {
  background: 'rgba(0,0,0,0.25)',
  border: '1px solid rgba(255,255,255,0.08)',
  backdropFilter: 'blur(8px)',
};

export const ROW_STYLE = {
  borderBottom: '1px solid rgba(255,255,255,0.05)',
};

export const STAT_PALETTE = {
  violet: { color: '#a78bfa', bg: 'rgba(167,139,250,0.2)', border: 'rgba(167,139,250,0.2)', from: 'rgba(167,139,250,0.2)', to: 'rgba(147,51,234,0.1)' },
  emerald:{ color: '#34d399', bg: 'rgba(52,211,153,0.2)',  border: 'rgba(52,211,153,0.2)',  from: 'rgba(52,211,153,0.2)',  to: 'rgba(22,163,74,0.1)' },
  amber:  { color: '#fbbf24', bg: 'rgba(251,191,36,0.2)',  border: 'rgba(251,191,36,0.2)',  from: 'rgba(251,191,36,0.15)', to: 'rgba(245,158,11,0.08)' },
  sky:    { color: '#60a5fa', bg: 'rgba(96,165,250,0.2)',  border: 'rgba(96,165,250,0.2)',  from: 'rgba(96,165,250,0.2)',  to: 'rgba(34,211,238,0.1)' },
  rose:   { color: '#fb7185', bg: 'rgba(251,113,133,0.2)', border: 'rgba(251,113,133,0.2)', from: 'rgba(251,113,133,0.18)', to: 'rgba(225,29,72,0.08)' },
};

// ── Hour / minute options ───────────────────────────────────────────────────
const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'));
const MINUTES = ['00', '15', '30', '45'];

// ── DateTimePicker component ────────────────────────────────────────────────
export const DateTimePicker = ({ value, onChange, allowPast = false }) => {
  const [calOpen, setCalOpen] = useState(false);

  // Parse ISO string → { date, hour, minute }
  const parsed = value ? new Date(value) : null;
  const selectedDate = parsed && !isNaN(parsed) ? parsed : null;
  const selectedHour  = selectedDate ? String(selectedDate.getHours()).padStart(2, '0') : '09';
  const selectedMin   = selectedDate
    ? (['00','15','30','45'].includes(String(selectedDate.getMinutes()).padStart(2,'0'))
        ? String(selectedDate.getMinutes()).padStart(2,'0')
        : '00')
    : '00';

  const buildISO = (date, hour, minute) => {
    if (!date) return '';
    const d = new Date(date);
    d.setHours(parseInt(hour, 10), parseInt(minute, 10), 0, 0);
    // return local ISO-like string backend can parse
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
  };

  // When past times aren't allowed and the chosen day is today, block any
  // hour/minute already in the past so only "now or later" can be picked.
  const now = new Date();
  const isToday = selectedDate
    && selectedDate.getFullYear() === now.getFullYear()
    && selectedDate.getMonth() === now.getMonth()
    && selectedDate.getDate() === now.getDate();
  const restrictTimes = !allowPast && isToday;
  const isHourDisabled = (h) => restrictTimes && parseInt(h, 10) < now.getHours();
  const isMinDisabled = (m) =>
    restrictTimes && parseInt(selectedHour, 10) === now.getHours() && parseInt(m, 10) < now.getMinutes();

  const handleDateSelect = (date) => {
    setCalOpen(false);
    // If picking today and the currently-held hour is now in the past, bump the
    // time forward to the next valid slot so we never emit a past datetime.
    let hour = selectedHour, minute = selectedMin;
    const pickIsToday = date
      && date.getFullYear() === now.getFullYear()
      && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate();
    if (!allowPast && pickIsToday && parseInt(hour, 10) < now.getHours()) {
      hour = String(now.getHours()).padStart(2, '0');
      minute = '00';
    }
    onChange(buildISO(date, hour, minute));
  };

  const handleHourChange = (h) => onChange(buildISO(selectedDate, h, selectedMin));
  const handleMinChange  = (m) => onChange(buildISO(selectedDate, selectedHour, m));

  return (
    <div className="flex gap-2">
      {/* Calendar popover */}
      <Popover open={calOpen} onOpenChange={setCalOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className="flex-1 justify-start text-left font-normal bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white"
          >
            <CalendarIcon className="mr-2 h-4 w-4 text-violet-400 flex-shrink-0" />
            {selectedDate ? format(selectedDate, 'dd MMM yyyy') : <span className="text-white/40">Pick a date</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-auto p-0 bg-[#0d0b1f] border-white/10"
          align="start"
          style={{ zIndex: 9999 }}
        >
          <Calendar
            mode="single"
            selected={selectedDate}
            onSelect={handleDateSelect}
            fromDate={allowPast ? undefined : new Date()}
            initialFocus
            classNames={{
              months: 'flex flex-col',
              month: 'space-y-2',
              caption: 'flex justify-center pt-1 relative items-center text-white',
              caption_label: 'text-sm font-medium text-white',
              nav: 'space-x-1 flex items-center',
              nav_button: 'h-7 w-7 bg-white/10 border border-white/10 rounded p-0 hover:bg-white/20 text-white',
              nav_button_previous: 'absolute left-1',
              nav_button_next: 'absolute right-1',
              table: 'w-full border-collapse',
              head_row: 'flex',
              head_cell: 'text-white/40 rounded-md w-9 font-normal text-[0.8rem]',
              row: 'flex w-full mt-1',
              cell: 'h-9 w-9 text-center text-sm p-0 relative focus-within:relative focus-within:z-20',
              day: 'h-9 w-9 p-0 font-normal text-white/70 rounded hover:bg-violet-600/40 hover:text-white transition-colors',
              day_selected: 'bg-violet-600 text-white hover:bg-violet-600 hover:text-white',
              day_today: 'bg-white/10 text-white',
              day_outside: 'text-white/20',
              day_disabled: 'text-white/20 cursor-not-allowed',
            }}
          />
        </PopoverContent>
      </Popover>

      {/* Hour select */}
      <Select value={selectedHour} onValueChange={handleHourChange}>
        <SelectTrigger className="w-20 bg-white/5 border-white/10 text-white">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-48 overflow-y-auto">
          {HOURS.map(h => <SelectItem key={h} value={h} disabled={isHourDisabled(h)}>{h}:00</SelectItem>)}
        </SelectContent>
      </Select>

      {/* Minute select */}
      <Select value={selectedMin} onValueChange={handleMinChange}>
        <SelectTrigger className="w-20 bg-white/5 border-white/10 text-white">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MINUTES.map(m => <SelectItem key={m} value={m} disabled={isMinDisabled(m)}>:{m}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
};

// ── Date-only picker (for tasks) ────────────────────────────────────────────
export const DateOnlyPicker = ({ value, onChange, disableWeekends = false }) => {
  const [open, setOpen] = useState(false);
  const selected = value ? new Date(value + 'T00:00:00') : null;

  const handleSelect = (date) => {
    setOpen(false);
    if (!date) { onChange(''); return; }
    const pad = n => String(n).padStart(2, '0');
    onChange(`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-start text-left font-normal bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white"
        >
          <CalendarIcon className="mr-2 h-4 w-4 text-violet-400 flex-shrink-0" />
          {selected && !isNaN(selected)
            ? format(selected, 'dd MMM yyyy')
            : <span className="text-white/40">Pick a date</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-auto p-0 bg-[#0d0b1f] border-white/10"
        align="start"
        style={{ zIndex: 9999 }}
      >
        <Calendar
          mode="single"
          selected={selected && !isNaN(selected) ? selected : undefined}
          onSelect={handleSelect}
          disabled={disableWeekends ? { dayOfWeek: [0, 6] } : undefined}
          initialFocus
          classNames={{
            months: 'flex flex-col',
            month: 'space-y-2',
            caption: 'flex justify-center pt-1 relative items-center text-white',
            caption_label: 'text-sm font-medium text-white',
            nav: 'space-x-1 flex items-center',
            nav_button: 'h-7 w-7 bg-white/10 border border-white/10 rounded p-0 hover:bg-white/20 text-white',
            nav_button_previous: 'absolute left-1',
            nav_button_next: 'absolute right-1',
            table: 'w-full border-collapse',
            head_row: 'flex',
            head_cell: 'text-white/40 rounded-md w-9 font-normal text-[0.8rem]',
            row: 'flex w-full mt-1',
            cell: 'h-9 w-9 text-center text-sm p-0 relative focus-within:relative focus-within:z-20',
            day: 'h-9 w-9 p-0 font-normal text-white/70 rounded hover:bg-violet-600/40 hover:text-white transition-colors',
            day_selected: 'bg-violet-600 text-white hover:bg-violet-600 hover:text-white',
            day_today: 'bg-white/10 text-white',
            day_outside: 'text-white/20',
            day_disabled: 'text-white/20 cursor-not-allowed line-through',
          }}
        />
      </PopoverContent>
    </Popover>
  );
};

// ── StatCard ────────────────────────────────────────────────────────────────
export const StatCard = ({ label, value, icon: Icon, palette }) => {
  const p = STAT_PALETTE[palette] || STAT_PALETTE.violet;
  return (
    <div
      className="rounded-2xl p-4 flex items-center gap-4 transition-transform duration-200 hover:scale-[1.03] cursor-default"
      style={{
        background: `linear-gradient(135deg, ${p.from}, ${p.to})`,
        border: `1px solid ${p.border}`,
        backdropFilter: 'blur(8px)',
      }}
    >
      <div className="rounded-xl p-2.5 flex-shrink-0" style={{ background: p.bg, boxShadow: `0 0 12px 0 ${p.color}33` }}>
        <Icon className="h-5 w-5" style={{ color: p.color }} />
      </div>
      <div>
        <p className="text-2xl font-bold text-white">{value ?? '—'}</p>
        <p className="text-xs text-white/50">{label}</p>
      </div>
    </div>
  );
};

// ── Priority / status badges ────────────────────────────────────────────────
export const priorityBadge = (priority) => {
  const map = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high:     'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium:   'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low:      'bg-green-500/20 text-green-400 border-green-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${map[priority] || map.medium}`}>
      {priority}
    </span>
  );
};

export const statusBadge = (status) => {
  const map = {
    scheduled:   'bg-blue-500/20 text-blue-400 border-blue-500/30',
    in_progress: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    completed:   'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    cancelled:   'bg-red-500/20 text-red-400 border-red-500/30',
    todo:        'bg-slate-500/20 text-slate-400 border-slate-500/30',
    review:      'bg-purple-500/20 text-purple-400 border-purple-500/30',
    done:        'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    blocked:     'bg-red-500/20 text-red-400 border-red-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${map[status] || map.todo}`}>
      {status?.replace('_', ' ')}
    </span>
  );
};

// ── Assignee avatars ────────────────────────────────────────────────────────
const AVATAR_COLORS = [
  'bg-violet-500/40 text-violet-100', 'bg-sky-500/40 text-sky-100', 'bg-emerald-500/40 text-emerald-100',
  'bg-amber-500/40 text-amber-100', 'bg-rose-500/40 text-rose-100', 'bg-cyan-500/40 text-cyan-100',
];
const avatarColorFor = (id) => AVATAR_COLORS[Math.abs(Number(id) || 0) % AVATAR_COLORS.length];

// Overlapping initials avatars for a task/subtask's assignees — replaces the
// old plain "· name, name" comma-joined text on the collapsed row.
export const AssigneeAvatars = ({ assignees, size = 'md' }) => {
  const list = assignees || [];
  if (list.length === 0) return null;
  const dim = size === 'sm' ? 'h-4 w-4 text-[8px]' : 'h-5 w-5 text-[9px]';
  const shown = list.slice(0, 3);
  const overflow = list.length - shown.length;
  return (
    <span className="flex items-center -space-x-1.5 ml-1" title={list.map(a => a.full_name).join(', ')}>
      {shown.map(a => (
        <span key={a.id} className={`${dim} rounded-full flex items-center justify-center font-semibold border border-[#0d0b1f] ${avatarColorFor(a.id)}`}>
          {a.full_name?.[0]?.toUpperCase() || '?'}
        </span>
      ))}
      {overflow > 0 && (
        <span className={`${dim} rounded-full flex items-center justify-center font-semibold border border-[#0d0b1f] bg-white/10 text-white/60`}>
          +{overflow}
        </span>
      )}
    </span>
  );
};

// ── EmptyState ──────────────────────────────────────────────────────────────
export const EmptyState = ({ icon: Icon, label }) => (
  <div className="flex flex-col items-center justify-center py-16 gap-3 text-white/30">
    <div className="rounded-2xl p-4" style={{ background: 'rgba(162,89,255,0.08)', border: '1px solid rgba(162,89,255,0.15)' }}>
      <Icon className="h-8 w-8 text-violet-400/40" />
    </div>
    <p className="text-sm">{label}</p>
  </div>
);

// ── Meeting-link validation ─────────────────────────────────────────────────
const VALID_MEETING_LINK_PATTERN = /^https?:\/\/(meet\.google\.com|zoom\.us|[\w-]+\.zoom\.us|us\d+web\.zoom\.us|teams\.microsoft\.com|[\w-]+\.jitsi\.meet|meet\.jit\.si|webex\.com|[\w-]+\.webex\.com|whereby\.com|[\w-]+\.whereby\.com|bluejeans\.com|gotomeet\.me|goto\.meeting)[\w\-/?=&#%+.]*$/i;

export const validateMeetingLink = (url) => {
  if (!url || !url.trim()) return true; // blank is OK (auto-generated)
  return VALID_MEETING_LINK_PATTERN.test(url.trim());
};

// True if a YYYY-MM-DD string falls on a Saturday/Sunday. Used to keep task
// deadlines on weekdays.
export const isWeekend = (ymd) => {
  if (!ymd) return false;
  const d = new Date(ymd + 'T00:00:00');
  if (isNaN(d)) return false;
  const day = d.getDay();
  return day === 0 || day === 6;
};

// ── Bulk-select toolbar ─────────────────────────────────────────────────────
// A small header row with a "select all" checkbox and, once anything is
// selected, a count + "Delete selected" button. Used by the Tasks, Documents
// and Notifications panels. `allIds` is the full list of selectable ids on the
// current view; `selected` is a Set; `onToggleAll` flips between none/all.
export const BulkSelectBar = ({ allIds, selected, onToggleAll, onDelete, deleting, label = 'item' }) => {
  const total = allIds.length;
  const count = selected.size;
  const allChecked = total > 0 && count === total;
  if (total === 0) return null;
  return (
    <div className="flex items-center justify-between px-1 py-1">
      <button type="button" onClick={onToggleAll} className="flex items-center gap-2 cursor-pointer select-none group">
        <SelectCheckbox checked={allChecked} indeterminate={count > 0 && !allChecked} onChange={onToggleAll} />
        <span className="text-xs text-white/50 group-hover:text-white/70 transition-colors">
          {count > 0 ? `${count} selected` : 'Select all'}
        </span>
      </button>
      {count > 0 && (
        <Button size="sm" variant="ghost" onClick={onDelete} disabled={deleting}
          className="h-7 px-3 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 gap-1.5">
          {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          Delete selected ({count})
        </Button>
      )}
    </div>
  );
};

// A custom-styled checkbox (light-purple to match the dashboard) for selecting
// an item in a bulk list. Renders a rounded box that fills violet with a white
// check when selected. `indeterminate` shows a dash (used by "select all").
export const SelectCheckbox = ({ checked, indeterminate = false, onChange }) => (
  <span
    role="checkbox"
    aria-checked={checked}
    tabIndex={0}
    onClick={e => { e.stopPropagation(); onChange && onChange(e); }}
    onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); onChange && onChange(e); } }}
    className={`inline-flex items-center justify-center h-4 w-4 rounded-[5px] border cursor-pointer flex-shrink-0 transition-all ${
      checked || indeterminate
        ? 'bg-violet-500 border-violet-400 shadow-[0_0_6px_0_rgba(162,89,255,0.5)]'
        : 'bg-violet-500/10 border-violet-400/40 hover:border-violet-400/70 hover:bg-violet-500/20'
    }`}
  >
    {checked && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
    {indeterminate && !checked && <span className="h-0.5 w-2 rounded-full bg-white" />}
  </span>
);

// ── Filter date picker ───────────────────────────────────────────────────────
// A compact, clearable calendar button used inside the filter bar. Unlike
// DateOnlyPicker it shows a small "×" to clear the chosen day and never blocks
// weekends (you may well want to filter to a Saturday meeting).
export const FilterDatePicker = ({ value, onChange, placeholder = 'Any date' }) => {
  const [open, setOpen] = useState(false);
  const selected = value ? new Date(value + 'T00:00:00') : null;
  const handleSelect = (date) => {
    setOpen(false);
    if (!date) { onChange(''); return; }
    const pad = n => String(n).padStart(2, '0');
    onChange(`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`);
  };
  return (
    <div className="relative">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className={`h-9 justify-start text-left font-normal bg-white/5 border-white/10 hover:bg-white/10 hover:text-white ${value ? 'text-white pr-7' : 'text-white/50'}`}
          >
            <CalendarIcon className="mr-2 h-3.5 w-3.5 text-violet-400 flex-shrink-0" />
            {selected && !isNaN(selected) ? format(selected, 'dd MMM yyyy') : placeholder}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 bg-[#0d0b1f] border-white/10" align="start" style={{ zIndex: 9999 }}>
          <Calendar
            mode="single"
            selected={selected && !isNaN(selected) ? selected : undefined}
            onSelect={handleSelect}
            initialFocus
            classNames={{
              months: 'flex flex-col', month: 'space-y-2',
              caption: 'flex justify-center pt-1 relative items-center text-white',
              caption_label: 'text-sm font-medium text-white',
              nav: 'space-x-1 flex items-center',
              nav_button: 'h-7 w-7 bg-white/10 border border-white/10 rounded p-0 hover:bg-white/20 text-white',
              nav_button_previous: 'absolute left-1', nav_button_next: 'absolute right-1',
              table: 'w-full border-collapse', head_row: 'flex',
              head_cell: 'text-white/40 rounded-md w-9 font-normal text-[0.8rem]',
              row: 'flex w-full mt-1',
              cell: 'h-9 w-9 text-center text-sm p-0 relative focus-within:relative focus-within:z-20',
              day: 'h-9 w-9 p-0 font-normal text-white/70 rounded hover:bg-violet-600/40 hover:text-white transition-colors',
              day_selected: 'bg-violet-600 text-white hover:bg-violet-600 hover:text-white',
              day_today: 'bg-white/10 text-white', day_outside: 'text-white/20',
            }}
          />
        </PopoverContent>
      </Popover>
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          title="Clear date"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/80"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
};

// ── FilterBar ────────────────────────────────────────────────────────────────
// A reusable search + dropdown-filters + date row shared by the Meetings,
// Tasks, Documents and Notifications panels. Purely presentational: every
// value + setter is passed in. Renders nothing but styled controls; the parent
// owns the state and re-fetches on change.
//
// props:
//   search, onSearchChange, searchPlaceholder
//   selects: [{ value, onChange, placeholder, allLabel, options: [{value,label}] }]
//   date, onDateChange   (omit both to hide the date picker)
//   onClear              shown as a "Clear" button when any filter is active
//   active               boolean — whether any filter is currently set
export const FilterBar = ({
  search, onSearchChange, searchPlaceholder = 'Search…',
  selects = [], date, onDateChange, onClear, active = false,
}) => (
  <div className="flex flex-wrap items-center gap-2 mb-3">
    <div className="relative flex-1 min-w-[180px]">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30" />
      <Input
        value={search}
        onChange={e => onSearchChange(e.target.value)}
        placeholder={searchPlaceholder}
        className="h-9 pl-8 bg-white/5 border-white/10 text-white text-sm placeholder:text-white/30"
      />
      {search && (
        <button
          type="button"
          onClick={() => onSearchChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/80"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>

    {selects.map((sel, i) => (
      <Select key={i} value={sel.value || 'all'} onValueChange={v => sel.onChange(v === 'all' ? '' : v)}>
        <SelectTrigger className="h-9 w-auto min-w-[130px] gap-1.5 bg-white/5 border-white/10 text-white text-sm data-[placeholder]:text-white/40">
          <SlidersHorizontal className="h-3.5 w-3.5 text-violet-400 flex-shrink-0" />
          <SelectValue placeholder={sel.placeholder} />
        </SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-white/10 text-white">
          <SelectItem value="all">{sel.allLabel || sel.placeholder || 'All'}</SelectItem>
          {sel.options.map(o => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    ))}

    {onDateChange && (
      <FilterDatePicker value={date} onChange={onDateChange} />
    )}

    {active && onClear && (
      <Button
        size="sm" variant="ghost" onClick={onClear}
        className="h-9 px-2.5 text-xs text-white/50 hover:text-white hover:bg-white/5 gap-1"
      >
        <X className="h-3.5 w-3.5" /> Clear
      </Button>
    )}
  </div>
);
