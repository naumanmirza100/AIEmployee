import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getBookingInfo, confirmBooking } from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pad(n) { return String(n).padStart(2, '0'); }

function fmtDate(isoStr) {
  return new Date(isoStr).toLocaleString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric',
    year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function isoDate(y, m, d) {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

function today() {
  const t = new Date();
  return isoDate(t.getFullYear(), t.getMonth(), t.getDate());
}

const MONTH_NAMES = ['January','February','March','April','May','June',
                     'July','August','September','October','November','December'];
const DAY_NAMES   = ['Su','Mo','Tu','We','Th','Fr','Sa'];

// The server sends the times the salesperson is free (weekdays, working hours, company time). The page used to
// offer every half hour from 08:00 to 18:00 of the lead's own day, any day, and refuse afterwards (CO-201).
function localDay(isoStr) {
  const d = new Date(isoStr);
  return isoDate(d.getFullYear(), d.getMonth(), d.getDate());
}

function localTime(isoStr) {
  return new Date(isoStr).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function slotsByDay(slots) {
  const byDay = {};
  (slots || []).forEach(iso => { (byDay[localDay(iso)] = byDay[localDay(iso)] || []).push(iso); });
  return byDay;
}

const LEAD_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

// ---------------------------------------------------------------------------
// Calendar component
// ---------------------------------------------------------------------------

function Calendar({ selectedDay, onSelect, available }) {
  const todayStr = today();
  const todayDate = new Date();

  const [viewYear, setViewYear]   = useState(todayDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(todayDate.getMonth());

  const firstDay  = new Date(viewYear, viewMonth, 1).getDay();  // 0=Sun
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  // Disable going back before current month
  const isCurrentMonth = viewYear === todayDate.getFullYear() && viewMonth === todayDate.getMonth();

  const cells = [];
  // Leading empty cells
  for (let i = 0; i < firstDay; i++) cells.push(null);
  // Day cells
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div style={{ userSelect: 'none' }}>
      {/* Month navigation */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <button
          onClick={prevMonth}
          disabled={isCurrentMonth}
          style={{ background: 'none', border: '1px solid var(--line-1)', borderRadius: 8, color: isCurrentMonth ? 'var(--line-1)' : 'hsl(var(--pt-9ca3af))', padding: '6px 12px', cursor: isCurrentMonth ? 'default' : 'pointer', fontSize: 16, lineHeight: 1 }}
        >‹</button>
        <span style={{ color: 'var(--text-soft)', fontWeight: 700, fontSize: 15 }}>
          {MONTH_NAMES[viewMonth]} {viewYear}
        </span>
        <button
          onClick={nextMonth}
          style={{ background: 'none', border: '1px solid var(--line-1)', borderRadius: 8, color: 'hsl(var(--pt-9ca3af))', padding: '6px 12px', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}
        >›</button>
      </div>

      {/* Day-of-week headers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 4, marginBottom: 6 }}>
        {DAY_NAMES.map(d => (
          <div key={d} style={{ textAlign: 'center', color: '#4b5563', fontSize: 11, fontWeight: 700, padding: '4px 0' }}>{d}</div>
        ))}
      </div>

      {/* Date grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 4 }}>
        {cells.map((day, i) => {
          if (!day) return <div key={`e-${i}`} />;

          const iso      = isoDate(viewYear, viewMonth, day);
          const isPast   = iso < todayStr || !available.has(iso);   // before today, or no free time
          const isToday  = iso === todayStr;
          const isActive = iso === selectedDay;

          let bg     = 'transparent';
          let color  = '#c4b5d4';
          let border = '1px solid transparent';
          let cursor = 'pointer';

          if (isPast) {
            color  = 'var(--line-1)';
            cursor = 'default';
          } else if (isActive) {
            bg     = 'linear-gradient(135deg,#a855f7,#6366f1)';
            color  = '#fff';
            border = '1px solid transparent';
          } else if (isToday) {
            border = '1px solid #a855f7';
            color  = '#c084fc';
          }

          return (
            <button
              key={iso}
              disabled={isPast}
              onClick={() => !isPast && onSelect(iso)}
              style={{
                background: bg, color, border, cursor,
                borderRadius: 8, padding: '9px 0', fontSize: 13,
                fontWeight: isActive || isToday ? 700 : 400,
                textAlign: 'center', transition: 'all 0.12s',
              }}
              onMouseEnter={e => { if (!isPast && !isActive) e.currentTarget.style.background = 'rgba(168,85,247,0.15)'; }}
              onMouseLeave={e => { if (!isPast && !isActive) e.currentTarget.style.background = 'transparent'; }}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main booking page
// ---------------------------------------------------------------------------

export default function MeetingBookingPage() {
  const { token } = useParams();

  const [info, setInfo]         = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  const [selectedDay, setSelectedDay]   = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [submitting, setSubmitting]     = useState(false);
  const [confirmed, setConfirmed]       = useState(null);
  const [bookError, setBookError]       = useState('');

  const load = () => getBookingInfo(token)
    .then(data => {
      setInfo(data);
      // Only a scheduled call shows as confirmed; a cancelled or finished one says so (CO-201).
      if (data.status === 'scheduled') {
        setConfirmed({
          title: data.title,
          scheduled_at: data.scheduled_at || null,
          duration_minutes: data.duration_minutes,
          sender_name: data.sender_name,
          meet_link: data.meet_link || null,
        });
      }
    })
    .catch(err => setError(err?.message || err?.error || 'Booking link not found.'))
    .finally(() => setLoading(false));

  useEffect(() => { load(); }, [token]);   // eslint-disable-line react-hooks/exhaustive-deps

  const handleConfirm = async () => {
    if (!selectedTime || submitting) return;
    setSubmitting(true);
    setBookError('');
    try {
      const result = await confirmBooking(token, selectedTime);
      setConfirmed(result);
    } catch (err) {
      // The picker stays, with the reason beside it and the free times read again: a refusal replaced the
      // whole page with "Link unavailable".
      setBookError(err?.message || err?.error || 'That time could not be booked. Please pick another.');
      setSelectedTime(null);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  // ── Base styles ──
  const page = {
    minHeight: '100vh', background: 'var(--sfc-07030f)',
    display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
    padding: '32px 16px', fontFamily: 'system-ui,-apple-system,sans-serif',
  };
  const card = {
    background: 'var(--sfc-0e0820)', border: '1px solid var(--sfc-1e1535)', borderRadius: 18,
    padding: '32px 32px 28px', maxWidth: 680, width: '100%',
    boxShadow: '0 12px 50px rgba(0,0,0,0.55)',
  };
  const sectionTitle = {
    color: '#9ca3af', fontSize: 11, fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: '0.08em',
    marginBottom: 12, display: 'block',
  };
  const timeBtn = (active) => ({
    padding: '9px 0', borderRadius: 8, border: '1px solid',
    cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500,
    textAlign: 'center', transition: 'all 0.12s',
    background: active ? 'linear-gradient(90deg,#a855f7,#6366f1)' : 'rgba(255,255,255,0.03)',
    borderColor: active ? 'transparent' : 'var(--line-1)',
    color: active ? '#fff' : '#c4b5d4',
  });

  // ── Loading state ──
  if (loading) return (
    <div style={page}>
      <div style={{ marginTop: 80, color: '#6b7280', fontSize: 14 }}>Loading booking details…</div>
    </div>
  );

  // ── Confirmed state ──
  if (confirmed) return (
    <div style={page}>
      <div style={{ ...card, textAlign: 'center', marginTop: 40 }}>
        <div style={{ fontSize: 52, marginBottom: 16 }}>🎉</div>
        <h1 style={{ color: 'var(--text-soft)', fontWeight: 800, fontSize: 24, margin: '0 0 8px' }}>
          You're confirmed!
        </h1>
        <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 14, margin: '0 0 20px' }}>
          A confirmation email is on its way to you.
        </p>

        <div style={{ margin: '0 0 20px', padding: '16px 20px', background: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.2)', borderRadius: 12 }}>
          {confirmed.scheduled_at && (
            <p style={{ color: '#a855f7', fontSize: 16, fontWeight: 700, margin: '0 0 4px' }}>
              {fmtDate(confirmed.scheduled_at)}
            </p>
          )}
          {confirmed.duration_minutes && (
            <p style={{ color: '#6b7280', fontSize: 13, margin: 0 }}>
              {confirmed.duration_minutes} minutes · with {confirmed.sender_name || 'our team'}
            </p>
          )}
          <p style={{ color: '#6b7280', fontSize: 13, margin: confirmed.scheduled_at ? '4px 0 0' : 0 }}>
            Your video call link will be included in that email.
          </p>
        </div>

        {confirmed.meet_link && (
          <div style={{ margin: '0 0 20px', padding: '14px 20px', background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 12 }}>
            <p style={{ color: '#6b7280', fontSize: 12, margin: '0 0 10px' }}>Your video call link</p>
            <a
              href={confirmed.meet_link}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-block',
                background: 'linear-gradient(90deg,#10b981,#059669)',
                color: '#fff', fontWeight: 700, fontSize: 14,
                padding: '10px 24px', borderRadius: 9, textDecoration: 'none',
              }}
            >
              🎥 Join Meeting
            </a>
          </div>
        )}

        <p style={{ color: '#4b5563', fontSize: 12 }}>See you then!</p>
      </div>
    </div>
  );

  // ── Error state ──
  if (error) return (
    <div style={page}>
      <div style={{ ...card, textAlign: 'center', marginTop: 40 }}>
        <div style={{ fontSize: 44, marginBottom: 12 }}>😕</div>
        <h1 style={{ color: 'var(--text-soft)', fontWeight: 800, fontSize: 20, margin: '0 0 8px' }}>
          Link unavailable
        </h1>
        <p style={{ color: '#6b7280', fontSize: 14 }}>{error}</p>
      </div>
    </div>
  );

  // ── A call that was cancelled or has been held ──
  if (info && ['cancelled', 'completed', 'no_show'].includes(info.status)) return (
    <div style={page}>
      <div style={{ ...card, textAlign: 'center', marginTop: 40 }}>
        <h1 style={{ color: 'var(--text-soft)', fontWeight: 800, fontSize: 20, margin: '0 0 8px' }}>
          {info.status === 'cancelled' ? 'This call was cancelled' : 'This call has already taken place'}
        </h1>
        <p style={{ color: '#6b7280', fontSize: 14 }}>
          If you would like to talk, just reply to the email you received and we will find a time.
        </p>
      </div>
    </div>
  );

  // ── Main booking UI ──
  const canConfirm = selectedTime && !submitting;
  const byDay = slotsByDay(info.free_slots);
  const available = new Set(Object.keys(byDay));

  return (
    <div style={page}>
      <div style={card}>

        {/* ── Header ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, background: 'linear-gradient(135deg,#a855f7,#6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>
            📅
          </div>
          <div>
            <h1 style={{ color: 'var(--text-soft)', fontWeight: 800, fontSize: 20, margin: 0 }}>
              {info.title}
            </h1>
            <p style={{ color: '#6b7280', fontSize: 12, margin: '3px 0 0' }}>
              {info.duration_minutes} min · with {info.sender_name || 'our team'}
              {info.sender_title ? `, ${info.sender_title}` : ''}
              {info.sender_company ? ` at ${info.sender_company}` : ''}
            </p>
          </div>
        </div>

        <p style={{ color: 'hsl(var(--pt-9ca3af))', fontSize: 13, lineHeight: 1.65, marginBottom: 28 }}>
          Hi <strong style={{ color: 'var(--text-soft)' }}>{info.lead_first_name || info.lead_name}</strong>,
          please pick a date and time below. Once you confirm, you'll receive a calendar invite.
        </p>
        <p data-testid="booking-zone" style={{ color: '#6b7280', fontSize: 12, margin: '-18px 0 22px' }}>
          Times are shown in your time zone ({LEAD_ZONE}).
        </p>
        {available.size === 0 && (
          <p style={{ color: '#f59e0b', fontSize: 13, margin: '0 0 18px' }}>
            There are no free times in the next two weeks. Please reply to the email and we will find one.
          </p>
        )}

        {/* ── Two-column layout: Calendar | Time picker ── */}
        <div style={{ display: 'grid', gridTemplateColumns: selectedDay ? '1fr 1fr' : '1fr', gap: 28, alignItems: 'start' }}>

          {/* Left: Calendar */}
          <div>
            <span style={sectionTitle}>Select a date</span>
            <div style={{ background: 'hsl(var(--surface-invert) / 0.02)', border: '1px solid var(--sfc-1e1535)', borderRadius: 12, padding: '16px 14px' }}>
              <Calendar
                selectedDay={selectedDay}
                available={available}
                onSelect={d => { setSelectedDay(d); setSelectedTime(null); setBookError(''); }}
              />
            </div>
          </div>

          {/* Right: Time slots (appears after date is chosen) */}
          {selectedDay && (
            <div>
              <span style={sectionTitle}>Select a time</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflowY: 'auto', paddingRight: 4 }}>
                {(byDay[selectedDay] || []).map(iso => (
                  <button key={iso} style={timeBtn(selectedTime === iso)} onClick={() => setSelectedTime(iso)}>
                    {localTime(iso)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Summary ── */}
        {selectedTime && (
          <div style={{ marginTop: 20, padding: '13px 16px', background: 'rgba(168,85,247,0.07)', border: '1px solid rgba(168,85,247,0.2)', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>📅</span>
            <div>
              <p style={{ color: 'hsl(var(--pt-c084fc))', fontWeight: 700, fontSize: 14, margin: 0 }}>
                {fmtDate(selectedTime)}
              </p>
              <p style={{ color: '#6b7280', fontSize: 12, margin: '2px 0 0' }}>
                {info.duration_minutes}-minute call
              </p>
            </div>
          </div>
        )}

        {/* ── Confirm button ── */}
        <button
          disabled={!canConfirm}
          onClick={handleConfirm}
          style={{
            marginTop: 20, width: '100%', padding: '13px', borderRadius: 10, border: 'none',
            background: canConfirm ? 'linear-gradient(90deg,#a855f7,#6366f1)' : 'var(--sfc-1a1030)',
            color: canConfirm ? '#fff' : '#3d2d60',
            fontWeight: 700, fontSize: 15,
            cursor: canConfirm ? 'pointer' : 'not-allowed',
            transition: 'all 0.2s',
          }}
        >
          {submitting ? 'Confirming…' : 'Confirm Meeting'}
        </button>
        {bookError && (
          <p data-testid="booking-error" style={{ color: '#f87171', fontSize: 13, marginTop: 10, textAlign: 'center' }}>
            {bookError}
          </p>
        )}

      </div>
    </div>
  );
}
