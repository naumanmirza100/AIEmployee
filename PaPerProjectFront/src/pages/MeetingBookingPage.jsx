import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getBookingInfo, confirmBooking } from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pad(n) { return String(n).padStart(2, '0'); }

function toLocalIso(dateStr, timeStr) {
  return new Date(`${dateStr}T${timeStr}:00`).toISOString();
}

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

const TIMES = [
  '08:00','08:30','09:00','09:30','10:00','10:30',
  '11:00','11:30','12:00','12:30','13:00','13:30',
  '14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30','18:00',
];

// ---------------------------------------------------------------------------
// Calendar component
// ---------------------------------------------------------------------------

function Calendar({ selectedDay, onSelect }) {
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
          style={{ background: 'none', border: '1px solid #2d1f4a', borderRadius: 8, color: isCurrentMonth ? '#2d1f4a' : '#9ca3af', padding: '6px 12px', cursor: isCurrentMonth ? 'default' : 'pointer', fontSize: 16, lineHeight: 1 }}
        >‹</button>
        <span style={{ color: '#e2d9f3', fontWeight: 700, fontSize: 15 }}>
          {MONTH_NAMES[viewMonth]} {viewYear}
        </span>
        <button
          onClick={nextMonth}
          style={{ background: 'none', border: '1px solid #2d1f4a', borderRadius: 8, color: '#9ca3af', padding: '6px 12px', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}
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
          const isPast   = iso < todayStr;          // before today
          const isToday  = iso === todayStr;
          const isActive = iso === selectedDay;

          let bg     = 'transparent';
          let color  = '#c4b5d4';
          let border = '1px solid transparent';
          let cursor = 'pointer';

          if (isPast) {
            color  = '#2d1f4a';
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

  useEffect(() => {
    getBookingInfo(token)
      .then(setInfo)
      .catch(err => setError(err?.message || err?.error || 'Booking link not found.'))
      .finally(() => setLoading(false));
  }, [token]);

  const handleConfirm = async () => {
    if (!selectedDay || !selectedTime || submitting) return;
    setSubmitting(true);
    try {
      const result = await confirmBooking(token, toLocalIso(selectedDay, selectedTime));
      setConfirmed(result);
    } catch (err) {
      setError(err?.message || err?.error || 'Failed to book. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Base styles ──
  const page = {
    minHeight: '100vh', background: '#07030f',
    display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
    padding: '32px 16px', fontFamily: 'system-ui,-apple-system,sans-serif',
  };
  const card = {
    background: '#0e0820', border: '1px solid #1e1535', borderRadius: 18,
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
    borderColor: active ? 'transparent' : '#2d1f4a',
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
        <h1 style={{ color: '#e2d9f3', fontWeight: 800, fontSize: 24, margin: '0 0 8px' }}>
          You're confirmed!
        </h1>
        <p style={{ color: '#9ca3af', fontSize: 14, margin: '0 0 4px' }}>
          <strong style={{ color: '#e2d9f3' }}>{confirmed.title}</strong>
        </p>
        <div style={{ margin: '20px 0', padding: '16px 20px', background: 'rgba(168,85,247,0.08)', border: '1px solid rgba(168,85,247,0.2)', borderRadius: 12 }}>
          <p style={{ color: '#a855f7', fontSize: 16, fontWeight: 700, margin: '0 0 4px' }}>
            {fmtDate(confirmed.scheduled_at)}
          </p>
          <p style={{ color: '#6b7280', fontSize: 13, margin: 0 }}>
            {confirmed.duration_minutes} minutes · with {confirmed.sender_name || 'our team'}
          </p>
        </div>

        {/* Meeting join link */}
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
                color: '#fff',
                fontWeight: 700,
                fontSize: 14,
                padding: '10px 24px',
                borderRadius: 9,
                textDecoration: 'none',
              }}
            >
              Join Meeting
            </a>
            <p style={{ color: '#374151', fontSize: 11, margin: '10px 0 0', wordBreak: 'break-all' }}>
              {confirmed.meet_link}
            </p>
          </div>
        )}

        <p style={{ color: '#4b5563', fontSize: 12 }}>
          A confirmation email has been sent with the meeting link. See you then!
        </p>
      </div>
    </div>
  );

  // ── Error state ──
  if (error) return (
    <div style={page}>
      <div style={{ ...card, textAlign: 'center', marginTop: 40 }}>
        <div style={{ fontSize: 44, marginBottom: 12 }}>😕</div>
        <h1 style={{ color: '#e2d9f3', fontWeight: 800, fontSize: 20, margin: '0 0 8px' }}>
          Link unavailable
        </h1>
        <p style={{ color: '#6b7280', fontSize: 14 }}>{error}</p>
      </div>
    </div>
  );

  // ── Main booking UI ──
  const canConfirm = selectedDay && selectedTime && !submitting;

  return (
    <div style={page}>
      <div style={card}>

        {/* ── Header ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, background: 'linear-gradient(135deg,#a855f7,#6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>
            📅
          </div>
          <div>
            <h1 style={{ color: '#e2d9f3', fontWeight: 800, fontSize: 20, margin: 0 }}>
              {info.title}
            </h1>
            <p style={{ color: '#6b7280', fontSize: 12, margin: '3px 0 0' }}>
              {info.duration_minutes} min · with {info.sender_name || 'our team'}
              {info.sender_title ? `, ${info.sender_title}` : ''}
              {info.sender_company ? ` at ${info.sender_company}` : ''}
            </p>
          </div>
        </div>

        <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.65, marginBottom: 28 }}>
          Hi <strong style={{ color: '#e2d9f3' }}>{info.lead_first_name || info.lead_name}</strong>,
          please pick a date and time below. Once you confirm, you'll receive a calendar invite.
        </p>

        {/* ── Two-column layout: Calendar | Time picker ── */}
        <div style={{ display: 'grid', gridTemplateColumns: selectedDay ? '1fr 1fr' : '1fr', gap: 28, alignItems: 'start' }}>

          {/* Left: Calendar */}
          <div>
            <span style={sectionTitle}>Select a date</span>
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid #1e1535', borderRadius: 12, padding: '16px 14px' }}>
              <Calendar
                selectedDay={selectedDay}
                onSelect={d => { setSelectedDay(d); setSelectedTime(null); }}
              />
            </div>
          </div>

          {/* Right: Time slots (appears after date is chosen) */}
          {selectedDay && (
            <div>
              <span style={sectionTitle}>Select a time</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflowY: 'auto', paddingRight: 4 }}>
                {TIMES.map(t => (
                  <button key={t} style={timeBtn(selectedTime === t)} onClick={() => setSelectedTime(t)}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Summary ── */}
        {selectedDay && selectedTime && (
          <div style={{ marginTop: 20, padding: '13px 16px', background: 'rgba(168,85,247,0.07)', border: '1px solid rgba(168,85,247,0.2)', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>📅</span>
            <div>
              <p style={{ color: '#c084fc', fontWeight: 700, fontSize: 14, margin: 0 }}>
                {fmtDate(toLocalIso(selectedDay, selectedTime))}
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
            background: canConfirm ? 'linear-gradient(90deg,#a855f7,#6366f1)' : '#1a1030',
            color: canConfirm ? '#fff' : '#3d2d60',
            fontWeight: 700, fontSize: 15,
            cursor: canConfirm ? 'pointer' : 'not-allowed',
            transition: 'all 0.2s',
          }}
        >
          {submitting ? 'Confirming…' : 'Confirm Meeting'}
        </button>

      </div>
    </div>
  );
}
