import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Calendar, CheckCircle2, XCircle, AlertCircle, RefreshCw, Send,
  Sparkles, Bell, Loader2, CalendarCheck, ChevronLeft, ChevronRight,
  Search, ChevronDown, ChevronUp, ExternalLink, Clock, PhoneCall,
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
  pending:   { label: 'Pending',   color: '#f59e0b', bg: 'rgba(245,158,11,0.1)'   },
  scheduled: { label: 'Scheduled', color: '#10b981', bg: 'rgba(16,185,129,0.1)'  },
  completed: { label: 'Completed', color: '#6b7280', bg: 'rgba(107,114,128,0.1)' },
  cancelled: { label: 'Cancelled', color: '#ef4444', bg: 'rgba(239,68,68,0.1)'   },
  no_show:   { label: 'No Show',   color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)'  },
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
// ConfirmModal
// ---------------------------------------------------------------------------

function ConfirmModal({ meeting, onClose, onConfirmed }) {
  const [scheduledAt, setScheduledAt] = useState('');
  const [duration, setDuration] = useState(String(meeting.duration_minutes || 30));
  const [notes, setNotes] = useState(meeting.notes || '');
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const handleConfirm = async () => {
    if (!scheduledAt) { toast({ title: 'Pick a date & time', variant: 'destructive' }); return; }
    setSaving(true);
    try {
      const resp = await confirmMeeting(meeting.id, {
        scheduled_at: new Date(scheduledAt).toISOString(),
        duration_minutes: parseInt(duration),
        notes,
      });
      toast({ title: 'Meeting confirmed!', description: 'Confirmation email sent to the lead.' });
      onConfirmed(resp.data);
      onClose();
    } catch (e) {
      toast({ title: 'Confirm failed', description: e.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const inp = { width: '100%', background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 8, color: '#e2d9f3', padding: '8px 12px', fontSize: 14, boxSizing: 'border-box', outline: 'none' };
  const lbl = { color: '#9ca3af', fontSize: 12, fontWeight: 600, marginBottom: 5, display: 'block' };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={onClose}>
      <div style={{ background: 'linear-gradient(145deg,#1a1030,#120d24)', border: '1px solid #2d1f4a', borderRadius: 16, padding: 28, width: 460, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <h3 style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 17, margin: '0 0 4px' }}>Confirm Meeting</h3>
        <p style={{ color: '#6b7280', fontSize: 13, margin: '0 0 20px' }}>
          Set time for <strong style={{ color: '#a855f7' }}>{meeting.lead_name}</strong>. Confirmation email will be sent automatically.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div><label style={lbl}>Date & Time</label><input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} style={inp} /></div>
          <div><label style={lbl}>Duration</label>
            <select value={duration} onChange={e => setDuration(e.target.value)} style={inp}>
              {['15', '30', '45', '60', '90'].map(d => <option key={d} value={d}>{d} min</option>)}
            </select>
          </div>
          <div><label style={lbl}>Notes (optional)</label><textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} /></div>
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
          <Button variant="outline" onClick={onClose} style={{ border: '1px solid #2d1f4a', color: '#9ca3af', borderRadius: 8 }}>Cancel</Button>
          <Button onClick={handleConfirm} disabled={saving || !scheduledAt}
            style={{ background: 'linear-gradient(90deg,#10b981,#059669)', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600 }}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <CalendarCheck size={14} />}
            <span style={{ marginLeft: 6 }}>Confirm & Send Email</span>
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
  const [prepLoading, setPrepLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const { toast } = useToast();

  const act = async (label, fn) => {
    setActionLoading(label);
    try {
      const resp = await fn();
      toast({ title: `${label} — done!` });
      const updated = resp?.data || local;
      setLocal(updated);
      onUpdated(updated);
    } catch (e) {
      toast({ title: `${label} failed`, description: e.message, variant: 'destructive' });
    } finally { setActionLoading(null); }
  };

  const handlePrep = async () => {
    setPrepLoading(true);
    try {
      const resp = await generateMeetingPrep(local.id);
      setLocal(m => ({ ...m, prep_notes: resp.prep_notes }));
      toast({ title: 'Prep notes generated!' });
    } catch (e) {
      toast({ title: 'Failed', description: e.message, variant: 'destructive' });
    } finally { setPrepLoading(false); }
  };

  const handleStatus = async (s) => {
    setActionLoading('status');
    try {
      const resp = await updateMeeting(local.id, { status: s });
      const updated = resp?.data || { ...local, status: s };
      setLocal(updated);
      onUpdated(updated);
      toast({ title: `Marked as ${STATUS_CONFIG[s]?.label || s}` });
    } catch (e) {
      toast({ title: 'Failed', description: e.message, variant: 'destructive' });
    } finally { setActionLoading(null); }
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

        <div style={{ padding: '16px 24px', borderLeft: '3px solid #a855f7' }}>
          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
            {local.status === 'pending' && (
              <button style={{ ...btnBase, background: 'linear-gradient(90deg,#10b981,#059669)', color: '#fff' }}
                onClick={() => setShowConfirm(true)}>
                <CalendarCheck size={12} /> Set Time & Confirm
              </button>
            )}
            {local.status === 'pending' && (
              <button disabled={actionLoading === 'resend'}
                style={{ ...btnBase, background: 'rgba(168,85,247,0.12)', color: '#c084fc', border: '1px solid rgba(168,85,247,0.25)' }}
                onClick={() => act('Scheduling email resent', () => resendSchedulingEmail(local.id))}>
                {actionLoading === 'resend' ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Resend Scheduling Email
              </button>
            )}
            {local.status === 'scheduled' && (
              <button disabled={actionLoading === 'reminder'}
                style={{ ...btnBase, background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.25)' }}
                onClick={() => act('Reminder sent', () => sendMeetingReminder(local.id))}>
                {actionLoading === 'reminder' ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />} Send Reminder
              </button>
            )}
            {local.status === 'scheduled' && (
              <>
                <button disabled={actionLoading === 'status'}
                  style={{ ...btnBase, background: 'rgba(107,114,128,0.12)', color: '#9ca3af', border: '1px solid #2d1f4a' }}
                  onClick={() => handleStatus('completed')}>
                  <CheckCircle2 size={12} /> Mark Completed
                </button>
                <button disabled={actionLoading === 'status'}
                  style={{ ...btnBase, background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
                  onClick={() => handleStatus('no_show')}>
                  <XCircle size={12} /> No Show
                </button>
              </>
            )}
            {local.calendar_link && (
              <a href={local.calendar_link} target="_blank" rel="noopener noreferrer"
                style={{ ...btnBase, background: 'transparent', color: '#a855f7', border: '1px solid rgba(168,85,247,0.3)', textDecoration: 'none' }}>
                <ExternalLink size={12} /> Calendar Link
              </a>
            )}
          </div>

          {/* Status timestamps */}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 14, fontSize: 11 }}>
            {local.scheduling_email_sent_at && <span style={{ color: '#10b981' }}>✓ Scheduling email sent {fmt(local.scheduling_email_sent_at)}</span>}
            {local.reminder_sent_at && <span style={{ color: '#6366f1' }}>✓ Reminder sent {fmt(local.reminder_sent_at)}</span>}
            {local.confirmed_at && <span style={{ color: '#10b981' }}>✓ Confirmed {fmt(local.confirmed_at)}</span>}
          </div>

          {/* Reply snippet */}
          {local.reply_snippet && (
            <div style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', borderRadius: 8, padding: '8px 12px', marginBottom: 14 }}>
              <span style={{ color: '#818cf8', fontSize: 11, fontWeight: 700 }}>LEAD'S REPLY  </span>
              <span style={{ color: '#9ca3af', fontSize: 12, fontStyle: 'italic' }}>"{local.reply_snippet}"</span>
            </div>
          )}

          {/* Prep notes */}
          <PrepNotesPanel notes={local.prep_notes} loading={prepLoading} onRegenerate={handlePrep} />
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------

const SDRMeetingsTab = () => {
  const [data, setData]             = useState({ results: [], total: 0, total_pages: 1, page: 1 });
  const [campaigns, setCampaigns]   = useState([]);
  const [loading, setLoading]       = useState(true);
  const [checkingReplies, setCheckingReplies] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const mountCheckDone = useRef(false);

  // Filters (all server-side)
  const [search, setSearch]               = useState('');
  const [statusFilter, setStatusFilter]   = useState('');
  const [campaignFilter, setCampaignFilter] = useState('');
  const [activeOnly, setActiveOnly]       = useState(true);
  const [page, setPage]                   = useState(1);
  const PAGE_SIZE = 20;

  const debouncedSearch = useDebounce(search, 400);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [meetingsResp, campaignsResp] = await Promise.all([
        listMeetings({
          status: statusFilter,
          campaign_id: campaignFilter,
          search: debouncedSearch,
          active_only: activeOnly,
          page,
          page_size: PAGE_SIZE,
        }),
        listCampaigns(),
      ]);
      setData(meetingsResp);
      setCampaigns(campaignsResp?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load meetings', description: e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  }, [debouncedSearch, statusFilter, campaignFilter, activeOnly, page]);

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
  useEffect(() => { setPage(1); }, [debouncedSearch, statusFilter, campaignFilter, activeOnly]);

  const handleRowUpdate = useCallback((updated) => {
    setData(d => ({
      ...d,
      results: d.results.map(m => m.id === updated.id ? updated : m),
    }));
  }, []);

  const { results: meetings, total, total_pages } = data;

  // Stats from current full dataset (approximate from page data)
  const pending   = meetings.filter(m => m.status === 'pending').length;
  const scheduled = meetings.filter(m => m.status === 'scheduled').length;

  // ── Styles ──
  const th = { padding: '10px 14px', color: '#6b7280', fontSize: 11, fontWeight: 700, textAlign: 'left', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #1e1535', whiteSpace: 'nowrap' };
  const td = { padding: '12px 14px', color: '#c4b5d4', fontSize: 13, borderBottom: '1px solid #1a1030', verticalAlign: 'middle' };
  const inp = { background: '#0d0820', border: '1px solid #2d1f4a', borderRadius: 8, color: '#e2d9f3', padding: '7px 12px', fontSize: 13, outline: 'none' };
  const filterBtn = (active) => ({
    padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: active ? 700 : 400,
    cursor: 'pointer', border: 'none',
    background: active ? 'linear-gradient(90deg,#a855f7,#6366f1)' : 'rgba(255,255,255,0.04)',
    color: active ? '#fff' : '#6b7280',
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0616' }}>

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
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', paddingBottom: 14 }}>
          {/* Search */}
          <div style={{ position: 'relative', flex: '1 1 220px', minWidth: 180 }}>
            <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#4b5563' }} />
            <input
              placeholder="Search name, email, company…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ ...inp, width: '100%', paddingLeft: 30, boxSizing: 'border-box' }}
            />
          </div>

          {/* Status filter */}
          <div style={{ display: 'flex', gap: 5 }}>
            {['', 'pending', 'scheduled', 'completed', 'cancelled', 'no_show'].map(s => (
              <button key={s} style={filterBtn(statusFilter === s)} onClick={() => setStatusFilter(s)}>
                {s === '' ? 'All' : STATUS_CONFIG[s]?.label || s}
              </button>
            ))}
          </div>

          {/* Campaign filter */}
          {campaigns.length > 0 && (
            <select value={campaignFilter} onChange={e => setCampaignFilter(e.target.value)}
              style={{ ...inp, cursor: 'pointer', color: campaignFilter ? '#c084fc' : '#6b7280', minWidth: 160 }}>
              <option value="">All Campaigns</option>
              {campaigns.map(c => {
                const cs = CAMPAIGN_STATUS_LABEL[c.status] || {};
                return <option key={c.id} value={c.id}>{c.name} ({cs.label || c.status})</option>;
              })}
            </select>
          )}
        </div>
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

                      {/* Expand toggle */}
                      <td style={{ ...td, textAlign: 'right', color: '#4b5563' }}>
                        {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
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

      {/* ── Pagination ── */}
      {total_pages > 1 && !loading && (
        <div style={{ padding: '12px 24px', borderTop: '1px solid #1e1535', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#0a0616' }}>
          <span style={{ color: '#4b5563', fontSize: 12 }}>
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} meetings
          </span>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              style={{ padding: '5px 10px', borderRadius: 7, border: '1px solid #2d1f4a', background: 'transparent', color: page <= 1 ? '#2d1f4a' : '#9ca3af', cursor: page <= 1 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center' }}>
              <ChevronLeft size={14} />
            </button>

            {Array.from({ length: Math.min(7, total_pages) }, (_, i) => {
              let p;
              if (total_pages <= 7) {
                p = i + 1;
              } else if (page <= 4) {
                p = i + 1;
              } else if (page >= total_pages - 3) {
                p = total_pages - 6 + i;
              } else {
                p = page - 3 + i;
              }
              return (
                <button key={p} onClick={() => setPage(p)}
                  style={{ padding: '5px 10px', minWidth: 32, borderRadius: 7, border: '1px solid #2d1f4a', background: page === p ? 'linear-gradient(90deg,#a855f7,#6366f1)' : 'transparent', color: page === p ? '#fff' : '#6b7280', cursor: 'pointer', fontSize: 13, fontWeight: page === p ? 700 : 400 }}>
                  {p}
                </button>
              );
            })}

            <button
              onClick={() => setPage(p => Math.min(total_pages, p + 1))}
              disabled={page >= total_pages}
              style={{ padding: '5px 10px', borderRadius: 7, border: '1px solid #2d1f4a', background: 'transparent', color: page >= total_pages ? '#2d1f4a' : '#9ca3af', cursor: page >= total_pages ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center' }}>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SDRMeetingsTab;
