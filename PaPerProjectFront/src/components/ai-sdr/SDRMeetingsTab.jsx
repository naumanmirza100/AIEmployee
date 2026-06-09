import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Calendar, CheckCircle2, XCircle, AlertCircle, RefreshCw, Send,
  Sparkles, Bell, Loader2, CalendarCheck, ChevronLeft, ChevronRight,
  Search, ChevronDown, ChevronUp, ExternalLink, Clock, PhoneCall, Eye, X,
  ChevronsLeft, ChevronsRight, Flame, Thermometer, Snowflake,
  ArrowUpDown, CheckCircle, SlidersHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import {
  listMeetings, listCampaigns, confirmMeeting, sendMeetingReminder,
  generateMeetingPrep, resendSchedulingEmail, updateMeeting, checkAllReplies,
} from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_CONFIG = {
  pending:           { label: 'Pending',            color: '#f59e0b', bg: 'rgba(245,158,11,0.1)'   },
  awaiting_approval: { label: 'Awaiting Lead',      color: '#6366f1', bg: 'rgba(99,102,241,0.1)'   },
  scheduled:         { label: 'Scheduled',          color: '#10b981', bg: 'rgba(16,185,129,0.1)'   },
  completed:         { label: 'Completed',          color: '#6b7280', bg: 'rgba(107,114,128,0.1)'  },
  cancelled:         { label: 'Cancelled',          color: '#ef4444', bg: 'rgba(239,68,68,0.1)'    },
  no_show:           { label: "Didn't Show Up",     color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)'   },
};

const TEMP_COLOR = { hot: '#ef4444', warm: '#f59e0b', cold: '#6b7280' };

const CAMPAIGN_STATUS_LABEL = {
  active:    { label: 'Active',    color: '#10b981' },
  paused:    { label: 'Paused',    color: '#f59e0b' },
  completed: { label: 'Ended',     color: '#6b7280' },
  draft:     { label: 'Draft',     color: '#4b5563' },
  scheduled: { label: 'Scheduled', color: '#6366f1' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Pagination button style
// ---------------------------------------------------------------------------
const pgBtn = (disabled, active = false) => ({
  minWidth: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
  borderRadius: 7, fontSize: 13, fontWeight: active ? 700 : 400,
  cursor: disabled ? 'not-allowed' : 'pointer',
  border: `1px solid ${active ? '#a855f7' : 'rgba(255,255,255,0.08)'}`,
  background: active ? 'rgba(168,85,247,0.18)' : 'rgba(255,255,255,0.03)',
  color: disabled ? '#2d1f4a' : active ? '#c084fc' : '#9ca3af',
  opacity: disabled ? 0.5 : 1, transition: 'all 0.15s', padding: '0 8px',
});

// ---------------------------------------------------------------------------
// Custom Filter Dropdown
// ---------------------------------------------------------------------------
const FilterDropdown = ({ label, value, options, onChange, icon: LabelIcon, fullWidth }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const selected = options.find(o => o.key === value) || options[0];

  return (
    <div ref={ref} style={{ position: 'relative', userSelect: 'none', width: fullWidth ? '100%' : 'auto' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 7, padding: '7px 12px',
          borderRadius: 9, cursor: 'pointer', whiteSpace: 'nowrap',
          minWidth: fullWidth ? 'auto' : 130,
          width: fullWidth ? '100%' : 'auto',
          background: value ? `${selected?.color}15` : 'rgba(255,255,255,0.04)',
          border: `1px solid ${value ? selected?.color + '60' : '#2d1f4a'}`,
          color: value ? selected?.color : '#9ca3af',
          fontSize: 13, fontWeight: value ? 600 : 400, transition: 'all 0.15s',
        }}
      >
        {LabelIcon && <LabelIcon size={13} style={{ color: value ? selected?.color : '#6b7280' }} />}
        <span style={{ flex: 1, textAlign: 'left' }}>{value ? selected?.label : label}</span>
        <ChevronDown size={12} style={{ color: '#6b7280', transform: open ? 'rotate(180deg)' : 'none', transition: '0.15s', flexShrink: 0 }} />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50,
          background: 'linear-gradient(135deg,#0f0a1f,#140830)',
          border: '1px solid #2d1f4a', borderRadius: 11,
          boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
          minWidth: '100%', width: 'max-content', overflow: 'hidden',
          animation: 'fadeDown 0.12s ease',
        }}>
          {options.map((opt, idx) => {
            const isSel = opt.key === value;
            return (
              <button key={opt.key} onClick={() => { onChange(opt.key); setOpen(false); }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                  padding: '9px 14px', border: 'none', cursor: 'pointer',
                  background: isSel ? `${opt.color}18` : 'transparent',
                  borderBottom: idx < options.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
                onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0, background: opt.key ? opt.color : 'transparent', border: opt.key ? `2px solid ${opt.color}` : '2px solid #2d1f4a' }} />
                {opt.Icon && <opt.Icon size={13} style={{ color: opt.color, flexShrink: 0 }} />}
                <span style={{ flex: 1, textAlign: 'left', fontSize: 13, color: isSel ? opt.color : opt.key ? '#d1d5db' : '#6b7280', fontWeight: isSel ? 600 : 400 }}>
                  {opt.label}
                </span>
                {isSel && <CheckCircle size={13} style={{ color: opt.color, flexShrink: 0 }} />}
              </button>
            );
          })}
        </div>
      )}
      <style>{`@keyframes fadeDown{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}`}</style>
    </div>
  );
};

const PAGE_SIZE_OPTIONS = [10, 20, 50];

const MEET_SORT_OPTIONS = [
  { value: 'created_desc',   label: 'Newest First' },
  { value: 'created_asc',    label: 'Oldest First' },
  { value: 'scheduled_asc',  label: 'Scheduled: Soonest' },
  { value: 'scheduled_desc', label: 'Scheduled: Latest' },
  { value: 'score_desc',     label: 'Lead Score: High → Low' },
  { value: 'name_asc',       label: 'Name A → Z' },
];

// ---------------------------------------------------------------------------
// PrepNotesPanel  (used in expanded row)
// ---------------------------------------------------------------------------

function PrepNotesPanel({ notes, loading, onRegenerate }) {
  if (!notes || Object.keys(notes).length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0' }}>
        <span style={{ color: '#6b7280', fontSize: 13 }}>No prep notes yet</span>
        <button onClick={onRegenerate} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'linear-gradient(90deg,#a855f7,#6366f1)', color: '#fff', border: 'none', borderRadius: 7, padding: '5px 12px', fontSize: 12, cursor: 'pointer', fontWeight: 600 }}>
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          Generate with AI
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={13} color="#a855f7" />
          <span style={{ color: '#c084fc', fontWeight: 700, fontSize: 13 }}>AI Prep Notes</span>
          {notes.opportunity_score && (
            <span style={{ background: 'rgba(16,185,129,0.15)', color: '#10b981', borderRadius: 6, padding: '1px 8px', fontSize: 11, fontWeight: 600 }}>
              {notes.opportunity_score}/10
            </span>
          )}
        </div>
        <button onClick={onRegenerate} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'transparent', border: '1px solid #2d1f4a', color: '#6b7280', borderRadius: 6, padding: '3px 9px', fontSize: 11, cursor: 'pointer' }}>
          {loading ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} Refresh
        </button>
      </div>

      {notes.key_insight && (
        <div style={{ background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.18)', borderRadius: 8, padding: '8px 12px' }}>
          <span style={{ color: '#fbbf24', fontSize: 11, fontWeight: 700 }}>KEY INSIGHT  </span>
          <span style={{ color: '#e2d9f3', fontSize: 13 }}>{notes.key_insight}</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {notes.talking_points?.length > 0 && (
          <div>
            <div style={{ color: '#6b7280', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>TALKING POINTS</div>
            {notes.talking_points.map((p, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 5 }}>
                <span style={{ color: '#a855f7', fontSize: 11 }}>▸</span>
                <span style={{ color: '#c4b5d4', fontSize: 12, lineHeight: 1.5 }}>{p}</span>
              </div>
            ))}
          </div>
        )}
        {notes.questions_to_ask?.length > 0 && (
          <div>
            <div style={{ color: '#6b7280', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>QUESTIONS TO ASK</div>
            {notes.questions_to_ask.map((q, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, marginBottom: 5 }}>
                <span style={{ color: '#6366f1', fontSize: 11 }}>?</span>
                <span style={{ color: '#c4b5d4', fontSize: 12, lineHeight: 1.5 }}>{q}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {notes.risks?.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ color: '#6b7280', fontSize: 11, fontWeight: 700, alignSelf: 'center' }}>RISKS:</span>
          {notes.risks.map((r, i) => (
            <span key={i} style={{ background: 'rgba(239,68,68,0.09)', color: '#f87171', borderRadius: 5, padding: '2px 9px', fontSize: 11 }}>{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PrepNotesModal  (full-screen overlay — triggered by Eye icon in table row)
// ---------------------------------------------------------------------------

function PrepNotesModal({ meeting, onClose, onNotesUpdated }) {
  const [notes, setNotes]   = useState(meeting.prep_notes || {});
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const resp = await generateMeetingPrep(meeting.id);
      const fresh = resp.prep_notes || {};
      setNotes(fresh);
      onNotesUpdated(fresh);
      toast({ title: 'Prep notes generated!' });
    } catch (e) {
      toast({ title: 'Failed', description: e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={onClose}
    >
      <div
        style={{ background: '#0e0820', border: '1px solid #2d1f4a', borderRadius: 16, padding: '28px 32px', maxWidth: 700, width: '100%', maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.6)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Modal header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <div style={{ color: '#e2d9f3', fontWeight: 800, fontSize: 16 }}>AI Prep Notes</div>
            <div style={{ color: '#4b5563', fontSize: 12, marginTop: 2 }}>{meeting.lead_name} · {meeting.lead_company || 'Unknown company'}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', padding: 4 }}>
            <X size={18} />
          </button>
        </div>

        <PrepNotesPanel notes={notes} loading={loading} onRegenerate={handleGenerate} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ClockTimePicker — circular analog clock style picker
// ---------------------------------------------------------------------------

function ClockTimePicker({ value, onChange, ampm, onAmpmChange }) {
  const [mode, setMode]   = useState('hour'); // 'hour' | 'minute'
  const [hour, setHour]   = useState(null);
  const [minute, setMinute] = useState(null);
  const radius = 70, cx = 85, cy = 85;

  const commit = (h, m, ap) => {
    if (h === null || m === null) return;
    let h24 = h % 12;
    if (ap === 'PM') h24 += 12;
    onChange(`${String(h24).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
  };

  const pickHour = (h) => { setHour(h); setMode('minute'); commit(h, minute ?? 0, ampm); };
  const pickMinute = (m) => { setMinute(m); commit(hour ?? 12, m, ampm); };
  const toggleAmpm = (ap) => { onAmpmChange(ap); commit(hour ?? 12, minute ?? 0, ap); };

  const hourNums  = [12,1,2,3,4,5,6,7,8,9,10,11];
  const minuteNums = [0,5,10,15,20,25,30,35,40,45,50,55];

  const getPos = (i, total, r) => {
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };

  const nums   = mode === 'hour' ? hourNums : minuteNums;
  const selNum = mode === 'hour' ? hour : minute;
  const selPos = selNum !== null ? getPos(nums.indexOf(selNum), nums.length, radius) : null;

  const displayH = hour === null ? '--' : String(hour).padStart(2,'0');
  const displayM = minute === null ? '--' : String(minute).padStart(2,'0');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      {/* Clock face */}
      <svg width={170} height={170}>
        {/* Face */}
        <circle cx={cx} cy={cy} r={radius + 18} fill="#0d0820" stroke="#2d1f4a" strokeWidth={1} />
        <circle cx={cx} cy={cy} r={3} fill="#a855f7" />
        {/* Hand */}
        {selPos && <line x1={cx} y1={cy} x2={selPos.x} y2={selPos.y} stroke="#a855f7" strokeWidth={2} strokeLinecap="round" />}
        {/* Numbers */}
        {nums.map((n, i) => {
          const pos = getPos(i, nums.length, radius);
          const selected = n === selNum;
          return (
            <g key={n} onClick={() => mode === 'hour' ? pickHour(n) : pickMinute(n)} style={{ cursor: 'pointer' }}>
              <circle cx={pos.x} cy={pos.y} r={16} fill={selected ? '#a855f7' : 'transparent'} />
              <text x={pos.x} y={pos.y + 5} textAnchor="middle" fontSize={12} fontWeight={selected ? 700 : 400}
                fill={selected ? '#fff' : '#c4b5d4'}>{mode === 'minute' ? String(n).padStart(2,'0') : n}</text>
            </g>
          );
        })}
      </svg>
      <p style={{ color: '#6b7280', fontSize: 11, margin: 0 }}>
        {mode === 'hour' ? 'Select hour' : 'Select minute'}
      </p>
    </div>
  );
}

// ConfirmModal
// ---------------------------------------------------------------------------

function ConfirmModal({ meeting, onClose, onConfirmed }) {
  const today = new Date();
  const [selDate, setSelDate] = useState('');
  const [selTime, setSelTime] = useState('');
  const [ampm, setAmpm] = useState('AM');
  const [duration, setDuration] = useState(String(meeting.duration_minutes || 30));
  const [notes, setNotes]  = useState(meeting.notes || '');
  const [saving, setSaving] = useState(false);
  const [calMonth, setCalMonth] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const { toast } = useToast();

  // Build calendar days grid
  const daysInMonth = (y, m) => new Date(y, m + 1, 0).getDate();
  const firstDay    = (y, m) => new Date(y, m, 1).getDay();
  const y = calMonth.getFullYear(), mo = calMonth.getMonth();
  const totalDays = daysInMonth(y, mo);
  const startBlank = firstDay(y, mo);
  const cells = [];
  for (let i = 0; i < startBlank; i++) cells.push(null);
  for (let d = 1; d <= totalDays; d++) cells.push(d);

  const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dayNames   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

  const selectDay = (d) => {
    if (!d) return;
    const dd = String(d).padStart(2,'0');
    const mm = String(mo + 1).padStart(2,'0');
    setSelDate(`${y}-${mm}-${dd}`);
  };

  const isToday = (d) => {
    const t = new Date();
    return d === t.getDate() && mo === t.getMonth() && y === t.getFullYear();
  };
  const isPast = (d) => new Date(y, mo, d) < new Date(new Date().setHours(0,0,0,0));

  const handleConfirm = async (sendApproval = false) => {
    if (!selDate || !selTime) { toast({ title: 'Pick a date & time', variant: 'destructive' }); return; }
    setSaving(true);
    try {
      const resp = await confirmMeeting(meeting.id, {
        scheduled_at: new Date(`${selDate}T${selTime}`).toISOString(),
        duration_minutes: parseInt(duration),
        notes,
        send_approval: sendApproval,
        browser_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      if (sendApproval) {
        toast({ title: 'Approval email sent!', description: 'Lead will receive an email asking if the time works.' });
      } else {
        toast({ title: 'Meeting confirmed!', description: 'Confirmation email sent to the lead.' });
      }
      onConfirmed(resp.data);
      onClose();
    } catch (e) {
      toast({ title: 'Confirm failed', description: e.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const inp = { width: '100%', background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 8, color: '#e2d9f3', padding: '8px 12px', fontSize: 14, boxSizing: 'border-box', outline: 'none' };
  const lbl = { color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 6, display: 'block' };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={onClose}>
      <div style={{ background: 'linear-gradient(145deg,#1a1030,#120d24)', border: '1px solid #2d1f4a', borderRadius: 16, padding: 20, width: 520, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', scrollbarWidth: 'none' }} onClick={e => e.stopPropagation()}>
        <h3 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 17, margin: '0 0 4px' }}>Confirm Meeting</h3>
        <p style={{ color: '#6b7280', fontSize: 13, margin: '0 0 16px' }}>
          Set time for <strong style={{ color: '#a855f7' }}>{meeting.lead_name}</strong>.{' '}
          <span style={{ color: '#818cf8' }}>Ask Lead First</span> sends an approval email.{' '}
          <span style={{ color: '#10b981' }}>Confirm Directly</span> schedules immediately.
        </p>

        {/* ── Calendar + Clock together ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 14 }}>

          {/* Calendar */}
          <div style={{ background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 12, padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <button onClick={() => setCalMonth(new Date(y, mo - 1, 1))}
                style={{ background: 'none', border: 'none', color: '#a855f7', cursor: 'pointer', fontSize: 16, padding: '0 4px' }}>‹</button>
              <span style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 12 }}>{monthNames[mo].slice(0,3)} {y}</span>
              <button onClick={() => setCalMonth(new Date(y, mo + 1, 1))}
                style={{ background: 'none', border: 'none', color: '#a855f7', cursor: 'pointer', fontSize: 16, padding: '0 4px' }}>›</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 1, marginBottom: 3 }}>
              {dayNames.map(d => <div key={d} style={{ textAlign: 'center', color: '#6b7280', fontSize: 9, fontWeight: 600 }}>{d.slice(0,1)}</div>)}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 1 }}>
              {cells.map((d, i) => {
                const dateStr = d ? `${y}-${String(mo+1).padStart(2,'0')}-${String(d).padStart(2,'0')}` : '';
                const selected = dateStr === selDate;
                const past = d ? isPast(d) : false;
                const todayD = d ? isToday(d) : false;
                return (
                  <div key={i} onClick={() => !past && d && selectDay(d)}
                    style={{
                      textAlign: 'center', padding: '5px 0', borderRadius: 4, fontSize: 11,
                      cursor: d && !past ? 'pointer' : 'default',
                      background: selected ? '#a855f7' : todayD ? 'rgba(168,85,247,0.15)' : 'transparent',
                      color: !d ? 'transparent' : past ? '#2d1f4a' : selected ? '#fff' : todayD ? '#a855f7' : '#c4b5d4',
                      border: todayD && !selected ? '1px solid rgba(168,85,247,0.3)' : '1px solid transparent',
                    }}>
                    {d || ''}
                  </div>
                );
              })}
            </div>
            {selDate && <p style={{ color: '#10b981', fontSize: 10, marginTop: 6, textAlign: 'center' }}>✓ {new Date(selDate + 'T00:00').toDateString()}</p>}
          </div>

          {/* Clock */}
          <div style={{ background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 12, padding: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <ClockTimePicker value={selTime} onChange={setSelTime} ampm={ampm} onAmpmChange={setAmpm} />
          </div>
        </div>

        {/* Duration + AM/PM */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={lbl}>Duration</label>
            <select value={duration} onChange={e => setDuration(e.target.value)}
              style={{ ...inp, height: 42, appearance: 'none', WebkitAppearance: 'none', paddingRight: 32,
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center', cursor: 'pointer' }}>
              {['15','30','45','60','90'].map(d => <option key={d} value={d}>{d} min</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Time</label>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 8, padding: '0 20px', height: 42, boxSizing: 'border-box' }}>
              {/* HH : MM display — clicking switches clock mode */}
              <span style={{ fontSize: 22, fontWeight: 700, cursor: 'pointer', color: '#e2d9f3', letterSpacing: 1 }}>
                {selTime ? (() => { const [hh,mm] = selTime.split(':').map(Number); const h12 = hh % 12 || 12; return `${String(h12).padStart(2,'0')}:${String(mm).padStart(2,'0')}`; })() : '--:--'}
              </span>
              {/* AM / PM toggle buttons */}
              <div style={{ display: 'flex', flexDirection: 'row', gap: 3, marginLeft: 6 }}>
                {['AM','PM'].map(ap => (
                  <button key={ap} type="button" onClick={() => {
                    setAmpm(ap);
                    if (selTime) {
                      const [hh, mm] = selTime.split(':').map(Number);
                      const h12 = hh % 12 || 12;
                      let h24 = h12 % 12;
                      if (ap === 'PM') h24 += 12;
                      setSelTime(`${String(h24).padStart(2,'0')}:${String(mm).padStart(2,'0')}`);
                    }
                  }}
                    style={{
                      padding: '2px 8px', borderRadius: 4, border: '1px solid',
                      fontWeight: 700, fontSize: 11, cursor: 'pointer', transition: 'all 0.12s',
                      background: ampm === ap ? '#a855f7' : 'transparent',
                      borderColor: ampm === ap ? '#a855f7' : '#2d1f4a',
                      color: ampm === ap ? '#fff' : '#6b7280',
                    }}>{ap}</button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Notes — full width */}
        <div style={{ marginBottom: 16 }}>
          <label style={lbl}>Notes (optional)</label>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
            style={{ ...inp, resize: 'none', width: '100%' }} />
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <Button variant="outline" onClick={onClose} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>

          {/* Option 1: Ask lead first */}
          <Button onClick={() => handleConfirm(true)} disabled={saving || !selDate || !selTime}
            style={{ background: 'linear-gradient(90deg,#7c3aed,#6d28d9)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 13 }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            <span style={{ marginLeft: 5 }}>Ask Lead First</span>
          </Button>

          {/* Option 2: Confirm directly */}
          <Button onClick={() => handleConfirm(false)} disabled={saving || !selDate || !selTime}
            style={{ background: 'linear-gradient(90deg,#10b981,#059669)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 13 }}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : <CalendarCheck size={13} />}
            <span style={{ marginLeft: 5 }}>Confirm Directly</span>
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Expanded Row
// ---------------------------------------------------------------------------

function ExpandedRow({ meeting, colSpan, onUpdated }) {
  const [local, setLocal] = useState(meeting);
  const [actionLoading, setActionLoading] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [earlyWarning, setEarlyWarning] = useState(null); // { status, label, timeLeft }
  const { toast } = useToast();

  const act = async (key, toastLabel, fn) => {
    setActionLoading(key);
    try {
      const resp = await fn();
      toast({ title: `${toastLabel} — done!` });
      const updated = resp?.data?.data || resp?.data || local;
      setLocal(updated);
      onUpdated(updated);
    } catch (e) {
      toast({ title: `${toastLabel} failed`, description: e.message, variant: 'destructive' });
    } finally { setActionLoading(null); }
  };

  const doStatus = async (s) => {
    setActionLoading(`status_${s}`);
    try {
      const resp = await updateMeeting(local.id, { status: s });
      const updated = resp?.data?.data || resp?.data || { ...local, status: s };
      setLocal(updated);
      onUpdated(updated);
      toast({ title: `Marked as ${STATUS_CONFIG[s]?.label || s}` });
    } catch (e) {
      toast({ title: 'Failed', description: e.message, variant: 'destructive' });
    } finally { setActionLoading(null); }
  };

  const handleStatus = (s) => {
    if ((s === 'completed' || s === 'no_show') && local.scheduled_at) {
      const meetingTime = new Date(local.scheduled_at);
      if (meetingTime > new Date()) {
        const diff = meetingTime - new Date();
        const hrs  = Math.floor(diff / 3600000);
        const mins = Math.floor((diff % 3600000) / 60000);
        const timeLeft = hrs > 0 ? `${hrs}h ${mins}m` : `${mins} min`;
        setEarlyWarning({ status: s, label: s === 'completed' ? 'Mark Completed' : "Lead Didn't Show Up", timeLeft });
        return;
      }
    }
    doStatus(s);
  };

  const btnBase = { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 };

  return (
    <tr>
      <td colSpan={colSpan} style={{ padding: '0 0 2px 0', background: 'rgba(168,85,247,0.04)' }}>
        {showConfirm && (
          <ConfirmModal
            meeting={local}
            onClose={() => setShowConfirm(false)}
            onConfirmed={(u) => { setLocal(u); onUpdated(u); }}
          />
        )}

        {earlyWarning && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
            onClick={() => setEarlyWarning(null)}>
            <div style={{ background: 'linear-gradient(145deg,#1a1030,#120d24)', border: '1px solid #2d1f4a', borderRadius: 14, padding: 24, width: 380, maxWidth: '95vw' }}
              onClick={e => e.stopPropagation()}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <AlertCircle size={18} style={{ color: '#a855f7', flexShrink: 0 }} />
                <h4 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 15, margin: 0 }}>Meeting hasn't started yet</h4>
              </div>
              <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.6, margin: '0 0 6px' }}>
                Starts in <strong style={{ color: '#c084fc' }}>{earlyWarning.timeLeft}</strong>. Are you sure you want to "{earlyWarning.label}" now?
              </p>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
                <button onClick={() => setEarlyWarning(null)}
                  style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid #2d1f4a', background: 'transparent', color: '#9ca3af', cursor: 'pointer', fontSize: 13 }}>
                  Cancel
                </button>
                <button onClick={() => { doStatus(earlyWarning.status); setEarlyWarning(null); }}
                  style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: 'linear-gradient(90deg,#a855f7,#7c3aed)', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                  Yes, proceed
                </button>
              </div>
            </div>
          </div>
        )}

        <div style={{ padding: '16px 24px', borderLeft: '3px solid #a855f7' }}>
          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
            {(local.status === 'pending' || local.status === 'awaiting_approval') && (
              <button style={{ ...btnBase, background: 'linear-gradient(90deg,#10b981,#059669)', color: '#fff' }}
                onClick={() => setShowConfirm(true)}>
                <CalendarCheck size={12} /> {local.status === 'awaiting_approval' ? 'Change Proposed Time' : 'Set Time & Confirm'}
              </button>
            )}
            {local.status === 'pending' && (
              <button disabled={actionLoading === 'resend'}
                style={{ ...btnBase, background: 'rgba(168,85,247,0.12)', color: '#c084fc', border: '1px solid rgba(168,85,247,0.25)' }}
                onClick={() => act('resend', 'Scheduling email resent', () => resendSchedulingEmail(local.id))}>
                {actionLoading === 'resend' ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Resend Scheduling Email
              </button>
            )}
            {local.status === 'scheduled' && (
              <button disabled={actionLoading === 'reminder'}
                style={{ ...btnBase, background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.25)' }}
                onClick={() => act('reminder', 'Reminder sent', () => sendMeetingReminder(local.id))}>
                {actionLoading === 'reminder' ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />} Send Reminder
              </button>
            )}
            {local.status === 'scheduled' && (
              <>
                <button disabled={!!actionLoading}
                  style={{ ...btnBase, background: 'rgba(107,114,128,0.12)', color: '#9ca3af', border: '1px solid #2d1f4a' }}
                  onClick={() => handleStatus('completed')}>
                  {actionLoading === 'status_completed' ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />} Mark Completed
                </button>
                <button disabled={!!actionLoading}
                  style={{ ...btnBase, background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
                  onClick={() => handleStatus('no_show')}>
                  {actionLoading === 'status_no_show' ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />} Lead Didn't Show Up
                </button>
              </>
            )}
            {(local.status === 'no_show' || local.status === 'cancelled') && (
              <button disabled={!!actionLoading}
                style={{ ...btnBase, background: 'rgba(16,185,129,0.12)', color: '#10b981', border: '1px solid rgba(16,185,129,0.25)' }}
                onClick={() => handleStatus('pending')}>
                {actionLoading === 'status_pending' ? <Loader2 size={12} className="animate-spin" /> : <CalendarCheck size={12} />} Reschedule
              </button>
            )}
            {local.status === 'completed' && (
              <button disabled={!!actionLoading}
                style={{ ...btnBase, background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.25)' }}
                onClick={() => handleStatus('pending')}>
                {actionLoading === 'status_pending' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Reopen
              </button>
            )}
            {local.calendar_link && (
              <a href={local.calendar_link} target="_blank" rel="noopener noreferrer"
                style={{ ...btnBase, background: 'transparent', color: '#a855f7', border: '1px solid rgba(168,85,247,0.3)', textDecoration: 'none' }}>
                <ExternalLink size={12} /> Calendar Link
              </a>
            )}
          </div>

          {/* Status timestamps — one relevant badge per state */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14, fontSize: 11 }}>
            {local.status === 'awaiting_approval' && local.approval_proposed_at && (
              <span style={{ color: '#6366f1' }}>⏳ Approval email sent {fmt(local.approval_proposed_at)}</span>
            )}
            {local.status === 'scheduled' && local.confirmed_at && (
              <span style={{ color: '#10b981' }}>✓ Confirmed {fmt(local.confirmed_at)}</span>
            )}
            {local.status === 'scheduled' && local.reminder_sent_at && (
              <span style={{ color: '#6366f1' }}>✓ Reminder sent {fmt(local.reminder_sent_at)}</span>
            )}
            {(local.status === 'pending' || local.status === 'awaiting_approval') && local.scheduling_email_sent_at && (
              <span style={{ color: '#10b981' }}>✓ Scheduling email sent {fmt(local.scheduling_email_sent_at)}</span>
            )}
            {(local.status === 'completed' || local.status === 'no_show') && local.confirmed_at && (
              <span style={{ color: '#6b7280' }}>✓ Was scheduled {fmt(local.confirmed_at)}</span>
            )}
          </div>

          {/* Awaiting approval info banner */}
          {local.status === 'awaiting_approval' && (
            <div style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 18 }}>📨</span>
              <div>
                <p style={{ margin: 0, color: '#818cf8', fontSize: 12, fontWeight: 700 }}>WAITING FOR LEAD RESPONSE</p>
                <p style={{ margin: '2px 0 0', color: '#9ca3af', fontSize: 12 }}>
                  Approval email was sent. Lead will confirm or suggest another time.
                  {local.scheduled_at && <> Proposed time: <strong style={{ color: '#e2d9f3' }}>{fmt(local.scheduled_at)}</strong></>}
                </p>
              </div>
            </div>
          )}

          {/* Reply snippet */}
          {local.reply_snippet && (
            <div style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', borderRadius: 8, padding: '8px 12px', marginBottom: 14 }}>
              <span style={{ color: '#818cf8', fontSize: 11, fontWeight: 700 }}>LEAD'S REPLY  </span>
              <span style={{ color: '#9ca3af', fontSize: 12, fontStyle: 'italic' }}>"{local.reply_snippet}"</span>
            </div>
          )}

        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------

const SDRMeetingsTab = () => {
  const [data, setData]             = useState({ results: [], total: 0, total_pages: 1, page: 1, has_next: false, has_prev: false });
  const [campaigns, setCampaigns]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [checkingReplies, setCheckingReplies] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [prepModal, setPrepModal]   = useState(null);
  const [prepGenIds, setPrepGenIds] = useState(new Set());
  const mountCheckDone = useRef(false);

  // Filters
  const [filtersOpen, setFiltersOpen]       = useState(false);
  const [searchRaw, setSearchRaw]           = useState('');
  const [statusFilter, setStatusFilter]     = useState('');
  const [campaignFilter, setCampaignFilter] = useState('');
  const [tempFilter, setTempFilter]         = useState('');
  const [sortBy, setSortBy]                 = useState('created_desc');
  const [activeOnly, setActiveOnly]         = useState(false);
  const [page, setPage]                     = useState(1);
  const [pageSize, setPageSize]             = useState(20);

  const search = useDebounce(searchRaw, 400);
  const { toast } = useToast();

  const load = useCallback(async (overrides = {}) => {
    setLoading(true);
    try {
      const [meetingsResp, campaignsResp] = await Promise.all([
        listMeetings({
          status:      overrides.status      ?? statusFilter,
          campaign_id: overrides.campaign_id ?? campaignFilter,
          search:      overrides.search      ?? search,
          temperature: overrides.temperature ?? tempFilter,
          sort:        overrides.sort        ?? sortBy,
          active_only: overrides.active_only ?? activeOnly,
          page:        overrides.page        ?? page,
          page_size:   overrides.page_size   ?? pageSize,
        }),
        listCampaigns(),
      ]);
      // companyApi returns response.json() directly
      setData(meetingsResp || { results: [], total: 0, total_pages: 1, page: 1 });
      setCampaigns(campaignsResp?.data || campaignsResp || []);
    } catch (e) {
      toast({ title: 'Failed to load meetings', description: e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  }, [search, statusFilter, campaignFilter, tempFilter, sortBy, activeOnly, page, pageSize, toast]);

  useEffect(() => { load(); }, [load]);

  // On first mount: check all active campaigns for new replies in the background,
  // then reload meetings so any new replies appear immediately without waiting for
  // the 5-minute background scheduler.
  useEffect(() => {
    if (mountCheckDone.current) return;
    mountCheckDone.current = true;

    setCheckingReplies(true);
    checkAllReplies()
      .then((res) => {
        const newReplies = res?.new_replies ?? 0;
        const newMeetings = res?.new_meetings ?? 0;
        if (newReplies > 0 || newMeetings > 0) {
          load(); // refresh table if new data arrived
          if (newMeetings > 0) {
            toast({
              title: `${newMeetings} new meeting${newMeetings > 1 ? 's' : ''} booked!`,
              description: `${newReplies} new repl${newReplies > 1 ? 'ies' : 'y'} detected from your active campaigns.`,
            });
          }
        }
      })
      .catch(() => {}) // silent — IMAP errors shouldn't break the page
      .finally(() => setCheckingReplies(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset to page 1 when any filter changes
  useEffect(() => { setPage(1); }, [search, statusFilter, campaignFilter, tempFilter, sortBy, activeOnly, pageSize]);

  const handleRowUpdate = useCallback((updated) => {
    setData(d => ({
      ...d,
      results: d.results.map(m => m.id === updated.id ? updated : m),
    }));
  }, []);

  const handleGeneratePrep = useCallback(async (meeting, e) => {
    e.stopPropagation();
    if (prepGenIds.has(meeting.id)) return;
    setPrepGenIds(s => new Set(s).add(meeting.id));
    try {
      const resp = await generateMeetingPrep(meeting.id);
      const fresh = resp.prep_notes || {};
      setData(d => ({
        ...d,
        results: d.results.map(m => m.id === meeting.id ? { ...m, prep_notes: fresh } : m),
      }));
      // If modal is open for this meeting, update it too
      setPrepModal(pm => pm && pm.id === meeting.id ? { ...pm, prep_notes: fresh } : pm);
      toast({ title: 'Prep notes generated!' });
    } catch (err) {
      toast({ title: 'Prep generation failed', description: apiErrorMessage(err, 'Failed to generate prep notes'), variant: 'destructive' });
    } finally {
      setPrepGenIds(s => { const n = new Set(s); n.delete(meeting.id); return n; });
    }
  }, [prepGenIds, toast]);

  const { results: meetings, total, total_pages } = data;

  // Stats from current full dataset (approximate from page data)
  const pending   = meetings.filter(m => m.status === 'pending').length;
  const scheduled = meetings.filter(m => m.status === 'scheduled').length;

  // ── Styles ──
  const th = { padding: '10px 14px', color: '#6b7280', fontSize: 11, fontWeight: 700, textAlign: 'left', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #1e1535', whiteSpace: 'nowrap' };
  const td = { padding: '12px 14px', color: '#c4b5d4', fontSize: 13, borderBottom: '1px solid #1a1030', verticalAlign: 'middle' };
  const inp = { background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 8, color: '#e2d9f3', padding: '7px 12px', fontSize: 13, outline: 'none' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0616' }}>

      {/* ── Prep Notes Modal ── */}
      {prepModal && (
        <PrepNotesModal
          meeting={prepModal}
          onClose={() => setPrepModal(null)}
          onNotesUpdated={(fresh) => {
            setData(d => ({
              ...d,
              results: d.results.map(m => m.id === prepModal.id ? { ...m, prep_notes: fresh } : m),
            }));
          }}
        />
      )}

      {/* ── Header ── */}
      <div style={{ padding: '20px 24px 0', borderBottom: '1px solid #1e1535' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h2 style={{ color: '#e2d9f3', fontWeight: 800, fontSize: 20, margin: 0 }}>Meeting Scheduler</h2>
            <p style={{ color: '#4b5563', fontSize: 12, margin: '3px 0 0' }}>
              {total} meeting{total !== 1 ? 's' : ''} · {pending} pending · {scheduled} scheduled
              {!activeOnly && <span style={{ color: '#f59e0b', marginLeft: 8 }}>· showing all campaigns</span>}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* Live reply-check indicator */}
            {checkingReplies && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#6b7280', fontSize: 11, fontWeight: 500 }}>
                <Loader2 size={11} className="animate-spin" style={{ color: '#a855f7' }} />
                Checking for new replies…
              </span>
            )}
            {/* Active-only toggle */}
            <button onClick={() => setActiveOnly(o => !o)}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, border: '1px solid #2d1f4a', cursor: 'pointer', background: activeOnly ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.08)', color: activeOnly ? '#10b981' : '#f59e0b', fontSize: 12, fontWeight: 600 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: activeOnly ? '#10b981' : '#f59e0b', display: 'inline-block' }} />
              {activeOnly ? 'Active campaigns' : 'All campaigns'}
            </button>
            <button
              disabled={checkingReplies}
              onClick={() => {
                if (checkingReplies) return;
                setCheckingReplies(true);
                checkAllReplies()
                  .then((res) => {
                    const newReplies = res?.new_replies ?? 0;
                    const newMeetings = res?.new_meetings ?? 0;
                    if (newReplies > 0 || newMeetings > 0) {
                      load();
                      if (newMeetings > 0) {
                        toast({
                          title: `${newMeetings} new meeting${newMeetings > 1 ? 's' : ''} booked!`,
                          description: `${newReplies} new repl${newReplies > 1 ? 'ies' : 'y'} detected.`,
                        });
                      }
                    } else {
                      load();
                    }
                  })
                  .catch(() => load())
                  .finally(() => setCheckingReplies(false));
              }}
              style={{ background: 'none', border: '1px solid #2d1f4a', borderRadius: 8, padding: '6px 11px', color: checkingReplies ? '#4b5563' : '#6b7280', cursor: checkingReplies ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>

        {/* ── Filter / Search bar ── */}
        <div style={{ paddingBottom: 14 }}>

          {/* Top row: search + filter toggle + sort + page size + refresh */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>

            {/* Search */}
            <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
              <Search size={13} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: '#4b5563', pointerEvents: 'none' }} />
              <input
                placeholder="Search name, email, company, title…"
                value={searchRaw}
                onChange={e => setSearchRaw(e.target.value)}
                style={{ ...inp, width: '100%', paddingLeft: 32, paddingRight: searchRaw ? 30 : 12, boxSizing: 'border-box' }}
              />
              {searchRaw && (
                <button onClick={() => setSearchRaw('')} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', display: 'flex', padding: 0 }}>
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Filters toggle */}
            {(() => {
              const mActiveCount = [statusFilter, tempFilter, campaignFilter].filter(Boolean).length;
              const mTotalActive = mActiveCount + (sortBy !== 'created_desc' ? 1 : 0);
              return (
                <button
                  onClick={() => setFiltersOpen(v => !v)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px',
                    borderRadius: 9, cursor: 'pointer', whiteSpace: 'nowrap',
                    background: filtersOpen || mTotalActive > 0 ? 'rgba(168,85,247,0.12)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${filtersOpen || mTotalActive > 0 ? 'rgba(168,85,247,0.5)' : '#2d1f4a'}`,
                    color: filtersOpen || mTotalActive > 0 ? '#c084fc' : '#9ca3af',
                    fontSize: 13, fontWeight: mTotalActive > 0 ? 600 : 400, transition: 'all 0.15s',
                  }}
                >
                  <SlidersHorizontal size={13} />
                  Filters
                  {mTotalActive > 0 && (
                    <span style={{ background: 'linear-gradient(135deg,#a855f7,#6366f1)', color: '#fff', borderRadius: '50%', width: 18, height: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700 }}>
                      {mTotalActive}
                    </span>
                  )}
                  <ChevronDown size={11} style={{ color: '#6b7280', transform: filtersOpen ? 'rotate(180deg)' : 'none', transition: '0.15s', flexShrink: 0 }} />
                </button>
              );
            })()}

            {/* Page size */}
            <select
              value={pageSize}
              onChange={e => setPageSize(Number(e.target.value))}
              style={{ ...inp, cursor: 'pointer', padding: '7px 10px', fontSize: 13, width: 'auto' }}
            >
              {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n} / page</option>)}
            </select>

            {/* Refresh */}
            <button onClick={() => load()} style={{ display: 'flex', alignItems: 'center', padding: '7px 10px', background: 'none', border: '1px solid #2d1f4a', borderRadius: 9, cursor: 'pointer', color: '#6b7280' }}>
              <RefreshCw size={13} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>

          {/* ── Collapsible filter panel ── */}
          {filtersOpen && (
            <div style={{
              marginTop: 10,
              padding: '16px 16px 14px',
              background: 'linear-gradient(135deg,rgba(10,4,28,0.92),rgba(16,6,38,0.95))',
              border: '1px solid rgba(168,85,247,0.2)',
              borderRadius: 11,
              boxShadow: 'inset 0 1px 0 rgba(168,85,247,0.06), 0 4px 20px rgba(0,0,0,0.3)',
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>

                {/* Status */}
                <div>
                  <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} /> STATUS
                  </div>
                  <FilterDropdown fullWidth
                    label="All Statuses"
                    value={statusFilter}
                    onChange={setStatusFilter}
                    options={[
                      { key: '',                   label: 'All Statuses',    color: '#6b7280' },
                      { key: 'pending',            label: 'Pending',         color: '#f59e0b', dot: true },
                      { key: 'awaiting_approval',  label: 'Awaiting Lead',   color: '#6366f1', dot: true },
                      { key: 'scheduled',          label: 'Scheduled',       color: '#10b981', dot: true },
                      { key: 'completed',          label: 'Completed',       color: '#6b7280', dot: true },
                      { key: 'cancelled',          label: 'Cancelled',       color: '#ef4444', dot: true },
                      { key: 'no_show',            label: "Didn't Show Up",  color: '#8b5cf6', dot: true },
                    ]}
                  />
                </div>

                {/* Temperature */}
                <div>
                  <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Thermometer size={11} style={{ color: '#f59e0b' }} /> LEAD TEMP
                  </div>
                  <FilterDropdown fullWidth
                    label="All Temps"
                    value={tempFilter}
                    onChange={setTempFilter}
                    icon={Thermometer}
                    options={[
                      { key: '',     label: 'All Temps', color: '#6b7280' },
                      { key: 'hot',  label: 'Hot',       color: '#f43f5e', dot: true, Icon: Flame },
                      { key: 'warm', label: 'Warm',      color: '#f59e0b', dot: true, Icon: Thermometer },
                      { key: 'cold', label: 'Cold',      color: '#60a5fa', dot: true, Icon: Snowflake },
                    ]}
                  />
                </div>

                {/* Campaign */}
                <div>
                  <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#6366f1', display: 'inline-block' }} /> CAMPAIGN
                  </div>
                  <FilterDropdown fullWidth
                    label="All Campaigns"
                    value={campaignFilter}
                    onChange={setCampaignFilter}
                    options={[
                      { key: '', label: 'All Campaigns', color: '#6b7280' },
                      ...campaigns.map(c => ({
                        key: String(c.id),
                        label: c.name.length > 26 ? c.name.slice(0, 24) + '…' : c.name,
                        color: CAMPAIGN_STATUS_LABEL[c.status]?.color || '#6b7280',
                        dot: true,
                      })),
                    ]}
                  />
                </div>

                {/* Sort */}
                <div>
                  <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', marginBottom: 7, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <ArrowUpDown size={11} style={{ color: '#a78bfa' }} /> SORT BY
                  </div>
                  <FilterDropdown fullWidth
                    label="Sort by"
                    value={sortBy}
                    onChange={setSortBy}
                    icon={ArrowUpDown}
                    options={MEET_SORT_OPTIONS.map(o => ({ key: o.value, label: o.label, color: '#a78bfa' }))}
                  />
                </div>
              </div>

              {/* Panel footer */}
              {(() => {
                const mTotalActive = [statusFilter, tempFilter, campaignFilter].filter(Boolean).length + (sortBy !== 'created_desc' ? 1 : 0);
                return mTotalActive > 0 ? (
                  <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <button
                      onClick={() => { setStatusFilter(''); setTempFilter(''); setCampaignFilter(''); setSortBy('created_desc'); }}
                      style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', borderRadius: 8, background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.25)', color: '#f87171', fontSize: 12, cursor: 'pointer' }}
                    >
                      <X size={11} /> Clear all
                    </button>
                    <span style={{ color: '#6b7280', fontSize: 12 }}>{mTotalActive} active</span>
                  </div>
                ) : null;
              })()}
            </div>
          )}

          {/* Result summary */}
          <div style={{ marginTop: 8, fontSize: 12, color: '#4b5563', display: 'flex', alignItems: 'center', gap: 8 }}>
            {loading
              ? <span style={{ color: '#a78bfa' }}>Loading…</span>
              : <>
                  <span>
                    Showing <strong style={{ color: '#e2d9f3' }}>
                      {data.total === 0 ? 0 : ((data.page - 1) * pageSize) + 1}–{Math.min(data.page * pageSize, data.total)}
                    </strong> of <strong style={{ color: '#e2d9f3' }}>{data.total}</strong> meetings
                  </span>
                  {(searchRaw || statusFilter || tempFilter || campaignFilter) && (
                    <span style={{ padding: '1px 8px', borderRadius: 10, background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.25)', color: '#a78bfa', fontSize: 11 }}>
                      filtered
                    </span>
                  )}
                </>
            }
          </div>
        </div>
        <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
      </div>

      {/* ── Table ── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: '#4b5563', gap: 10 }}>
            <Loader2 size={20} className="animate-spin" /> Loading meetings…
          </div>
        ) : meetings.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 240, color: '#4b5563' }}>
            <Calendar size={36} style={{ opacity: 0.25, marginBottom: 12 }} />
            <p style={{ fontWeight: 600, color: '#4b5563', fontSize: 15, margin: 0 }}>No meetings found</p>
            <p style={{ fontSize: 12, marginTop: 6, color: '#374151' }}>
              {activeOnly
                ? 'Meetings from active campaigns will appear here when leads reply with interest.'
                : 'No meetings match the current filters.'}
            </p>
            {activeOnly && (
              <button onClick={() => setActiveOnly(false)} style={{ marginTop: 12, fontSize: 12, color: '#a855f7', background: 'none', border: '1px solid rgba(168,85,247,0.3)', borderRadius: 7, padding: '5px 14px', cursor: 'pointer' }}>
                Show all campaigns
              </button>
            )}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, background: '#0d0820', zIndex: 1 }}>
              <tr>
                <th style={th}>Lead</th>
                <th style={th}>Company</th>
                <th style={th}>Campaign</th>
                <th style={th}>Status</th>
                <th style={th}>Scheduled</th>
                <th style={th}>Score</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {meetings.map(m => {
                const sc = STATUS_CONFIG[m.status] || STATUS_CONFIG.pending;
                const isExpanded = expandedId === m.id;

                return (
                  <React.Fragment key={m.id}>
                    <tr
                      onClick={() => setExpandedId(id => id === m.id ? null : m.id)}
                      style={{ cursor: 'pointer', background: isExpanded ? 'rgba(168,85,247,0.06)' : 'transparent', transition: 'background 0.15s' }}
                      onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
                      onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = 'transparent'; }}
                    >
                      {/* Lead */}
                      <td style={td}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                          <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'linear-gradient(135deg,#a855f7,#6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: '#fff', flexShrink: 0 }}>
                            {(m.lead_name || '?')[0].toUpperCase()}
                          </div>
                          <div>
                            <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13 }}>{m.lead_name}</div>
                            <div style={{ color: '#4b5563', fontSize: 11 }}>{m.lead_email}</div>
                          </div>
                        </div>
                      </td>

                      {/* Company */}
                      <td style={td}>
                        <div style={{ color: '#c4b5d4', fontSize: 13 }}>{m.lead_company || '—'}</div>
                        {m.lead_job_title && <div style={{ color: '#4b5563', fontSize: 11 }}>{m.lead_job_title}</div>}
                      </td>

                      {/* Campaign */}
                      <td style={td}>
                        {m.campaign_name ? (
                          <span style={{ fontSize: 12, color: '#818cf8', background: 'rgba(99,102,241,0.1)', borderRadius: 6, padding: '2px 9px', fontWeight: 600 }}>
                            {m.campaign_name}
                          </span>
                        ) : '—'}
                      </td>

                      {/* Status */}
                      <td style={td}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: sc.bg, color: sc.color, borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 700 }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: sc.color }} />
                          {sc.label}
                        </span>
                      </td>

                      {/* Scheduled */}
                      <td style={td}>
                        <div style={{ color: m.scheduled_at ? '#c4b5d4' : '#374151', fontSize: 12 }}>
                          {m.scheduled_at ? fmt(m.scheduled_at) : 'Not confirmed'}
                        </div>
                        {m.duration_minutes && m.scheduled_at && (
                          <div style={{ color: '#374151', fontSize: 11 }}>{m.duration_minutes} min</div>
                        )}
                      </td>

                      {/* Score */}
                      <td style={td}>
                        {m.lead_score ? (
                          <div>
                            <span style={{ color: '#a855f7', fontWeight: 700, fontSize: 13 }}>{m.lead_score}</span>
                            <span style={{ color: '#374151', fontSize: 11 }}>/100</span>
                          </div>
                        ) : '—'}
                        {m.lead_temperature && (
                          <span style={{ fontSize: 10, fontWeight: 700, color: TEMP_COLOR[m.lead_temperature] || '#6b7280', textTransform: 'uppercase' }}>
                            {m.lead_temperature}
                          </span>
                        )}
                      </td>

                      {/* Actions + expand toggle */}
                      <td style={{ ...td, textAlign: 'right' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          {/* Generate Prep Notes */}
                          <button
                            title="Generate AI prep notes"
                            onClick={e => handleGeneratePrep(m, e)}
                            disabled={prepGenIds.has(m.id)}
                            style={{ background: 'rgba(168,85,247,0.1)', border: '1px solid rgba(168,85,247,0.25)', borderRadius: 6, padding: '4px 7px', cursor: prepGenIds.has(m.id) ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', color: '#a855f7' }}
                          >
                            {prepGenIds.has(m.id)
                              ? <Loader2 size={12} className="animate-spin" />
                              : <Sparkles size={12} />}
                          </button>

                          {/* View Prep Notes (eye) — only when notes exist */}
                          {m.prep_notes && Object.keys(m.prep_notes).length > 0 && (
                            <button
                              title="View prep notes"
                              onClick={e => { e.stopPropagation(); setPrepModal(m); }}
                              style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 6, padding: '4px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center', color: '#818cf8' }}
                            >
                              <Eye size={12} />
                            </button>
                          )}

                          {/* Expand chevron */}
                          <span style={{ color: '#4b5563' }}>
                            {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                          </span>
                        </div>
                      </td>
                    </tr>

                    {/* Expanded details row */}
                    {isExpanded && (
                      <ExpandedRow
                        meeting={m}
                        colSpan={7}
                        onUpdated={handleRowUpdate}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Pagination footer ── */}
      {total_pages > 1 && !loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, padding: '12px 20px', borderTop: '1px solid #1e1535', background: '#0a0616' }}>

          {/* Left: page info */}
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            Page <strong style={{ color: '#e2d9f3' }}>{page}</strong> of <strong style={{ color: '#e2d9f3' }}>{total_pages}</strong>
            <span style={{ color: '#4b5563', marginLeft: 8 }}>({total.toLocaleString()} total)</span>
          </span>

          {/* Right: page controls */}
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            {/* First */}
            <button onClick={() => { setPage(1); load({ page: 1 }); }} disabled={page <= 1} style={pgBtn(page <= 1)} title="First page">
              <ChevronsLeft size={14} />
            </button>
            {/* Prev */}
            <button onClick={() => { const p = page - 1; setPage(p); load({ page: p }); }} disabled={page <= 1} style={pgBtn(page <= 1)} title="Previous">
              <ChevronLeft size={14} />
            </button>

            {/* Page numbers with smart ellipsis */}
            {Array.from({ length: total_pages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === total_pages || Math.abs(p - page) <= 2)
              .reduce((acc, p, idx, arr) => {
                if (idx > 0 && p - arr[idx - 1] > 1) acc.push('…');
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                p === '…'
                  ? <span key={`ellipsis-${i}`} style={{ color: '#4b5563', padding: '0 4px', fontSize: 13 }}>…</span>
                  : <button key={p} onClick={() => { setPage(p); load({ page: p }); }} style={pgBtn(false, p === page)}>
                      {p}
                    </button>
              )}

            {/* Next */}
            <button onClick={() => { const p = page + 1; setPage(p); load({ page: p }); }} disabled={page >= total_pages} style={pgBtn(page >= total_pages)} title="Next">
              <ChevronRight size={14} />
            </button>
            {/* Last */}
            <button onClick={() => { setPage(total_pages); load({ page: total_pages }); }} disabled={page >= total_pages} style={pgBtn(page >= total_pages)} title="Last page">
              <ChevronsRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SDRMeetingsTab;
