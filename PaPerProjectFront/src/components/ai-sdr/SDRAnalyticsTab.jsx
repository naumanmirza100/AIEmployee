import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart3, TrendingUp, TrendingDown, Minus,
  Users, Mail, Calendar, MessageSquare,
  AlertTriangle, RefreshCw, Send, Loader2,
  Flame, Thermometer, Snowflake, CheckCircle,
} from 'lucide-react';
import { getSdrAnalytics, sendSdrDailySummary } from '@/services/aiSdrService';
import { useToast } from '@/components/ui/use-toast';

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

function trend(curr, prev) {
  if (curr > prev) return { icon: TrendingUp,   color: '#4ade80', label: `+${curr - prev} vs last week` };
  if (curr < prev) return { icon: TrendingDown,  color: '#f87171', label: `${curr - prev} vs last week` };
  return           { icon: Minus,               color: '#9ca3af', label: 'same as last week' };
}

// --------------------------------------------------------------------------
// Sub-components
// --------------------------------------------------------------------------

function StatCard({ icon: Icon, label, value, sub, color, trend: t }) {
  const TIcon = t?.icon;
  return (
    <div style={{
      background: 'linear-gradient(135deg,rgba(15,10,31,0.95),rgba(20,8,40,0.95))',
      border: '1px solid #2d1f4a', borderRadius: 12, padding: '18px 20px',
      display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minWidth: 140,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: `${color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={18} style={{ color }} />
        </div>
        {t && TIcon && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: t.color }}>
            <TIcon size={12} />
            <span>{t.label}</span>
          </div>
        )}
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, color: '#e2d9f3', lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#6b7280' }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#4b5563' }}>{sub}</div>}
    </div>
  );
}

function FunnelBar({ stages }) {
  if (!stages?.length) return null;
  const max = stages[0]?.count || 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {stages.map((s, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <span style={{ fontSize: 12, color: '#9ca3af' }}>{s.stage}</span>
            <span style={{ fontSize: 12, color: '#e2d9f3', fontWeight: 600 }}>
              {s.count} <span style={{ color: '#4b5563', fontWeight: 400 }}>({pct(s.count, max)}%)</span>
            </span>
          </div>
          <div style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.06)' }}>
            <div style={{
              height: '100%', borderRadius: 4,
              width: `${pct(s.count, max)}%`,
              background: s.color,
              transition: 'width 0.6s ease',
              minWidth: s.count > 0 ? 4 : 0,
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function MiniBar({ value, max, color }) {
  return (
    <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.06)' }}>
      <div style={{
        height: '100%', borderRadius: 3,
        width: `${max ? Math.min(100, (value / max) * 100) : 0}%`,
        background: color, transition: 'width 0.5s ease',
        minWidth: value > 0 ? 3 : 0,
      }} />
    </div>
  );
}

function DailyTrendChart({ trend: data }) {
  if (!data?.length) return null;
  const maxEmails = Math.max(...data.map(d => d.emails), 1);
  const maxLeads  = Math.max(...data.map(d => d.leads), 1);

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 90 }}>
      {data.map((d, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 64 }}>
            {/* Emails bar */}
            <div style={{
              width: 10, borderRadius: '2px 2px 0 0',
              height: `${(d.emails / maxEmails) * 64}px`,
              background: '#a78bfa', minHeight: d.emails > 0 ? 3 : 0,
            }} title={`${d.emails} emails`} />
            {/* Leads bar */}
            <div style={{
              width: 10, borderRadius: '2px 2px 0 0',
              height: `${(d.leads / maxLeads) * 64}px`,
              background: '#60a5fa', minHeight: d.leads > 0 ? 3 : 0,
            }} title={`${d.leads} leads`} />
            {/* Meetings dot */}
            {d.meetings > 0 && (
              <div style={{
                width: 6, height: 6, borderRadius: '50%',
                background: '#4ade80', marginBottom: 2, alignSelf: 'flex-end',
              }} title={`${d.meetings} meeting(s)`} />
            )}
          </div>
          <span style={{ fontSize: 10, color: '#4b5563' }}>{d.day}</span>
        </div>
      ))}
    </div>
  );
}

const SENTIMENT_CFG = {
  positive:       { label: 'Interested',    color: '#4ade80' },
  positive_interest: { label: 'Interested', color: '#4ade80' },
  not_interested: { label: 'Not Interested',color: '#f87171' },
  negative:       { label: 'Not Interested',color: '#f87171' },
  out_of_office:  { label: 'OOO',           color: '#f59e0b' },
  wants_more_info:{ label: 'Wants Info',    color: '#60a5fa' },
  neutral:        { label: 'Neutral',       color: '#9ca3af' },
};

const SOURCE_CFG = {
  apollo:      { label: 'Apollo.io',  color: '#a78bfa' },
  apify:       { label: 'Apify',      color: '#60a5fa' },
  csv_import:  { label: 'CSV Import', color: '#4ade80' },
  manual:      { label: 'Manual',     color: '#f59e0b' },
  ai_generated:{ label: 'AI',         color: '#f43f5e' },
};

// --------------------------------------------------------------------------
// Main component
// --------------------------------------------------------------------------
export default function SDRAnalyticsTab() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // companyApi returns response.json() directly: { status, data: { metrics... } }
      const res = await getSdrAnalytics();
      setMetrics(res?.data || null);
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Unknown error';
      console.error('Analytics load failed:', msg, err?.response?.data);
      toast({ title: 'Failed to load analytics', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSendSummary = async () => {
    setSending(true);
    try {
      await sendSdrDailySummary();
      toast({ title: 'Daily summary email sent!' });
    } catch {
      toast({ title: 'Failed to send summary email', variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };

  const card = {
    background: 'linear-gradient(135deg,rgba(15,10,31,0.95),rgba(20,8,40,0.95))',
    border: '1px solid #2d1f4a', borderRadius: 12, padding: '20px 22px',
  };

  const sectionTitle = (t) => (
    <div style={{ fontSize: 13, fontWeight: 700, color: '#e2d9f3', marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t}</div>
  );

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
      <Loader2 size={28} style={{ color: '#7c3aed' }} className="animate-spin" />
    </div>
  );

  if (!metrics) return (
    <div style={{ textAlign: 'center', padding: 60, color: '#6b7280' }}>
      <BarChart3 size={40} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
      <div>No analytics data available yet.</div>
      <div style={{ fontSize: 12, marginTop: 6 }}>Start a campaign and enroll leads to see metrics.</div>
    </div>
  );

  const m = metrics;
  const totalSource = Object.values(m.source_counts || {}).reduce((a, b) => a + b, 0) || 1;
  const totalSentiment = Object.values(m.sentiment_counts || {}).reduce((a, b) => a + b, 0) || 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Alert banner */}
      {m.low_meetings_alert && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 18px', borderRadius: 10,
          background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)',
        }}>
          <AlertTriangle size={18} style={{ color: '#f59e0b', flexShrink: 0 }} />
          <div>
            <div style={{ color: '#fbbf24', fontWeight: 700, fontSize: 13 }}>
              Low Meeting Alert — only {m.meetings_week} meeting(s) this week (target: {m.meetings_alert_threshold})
            </div>
            <div style={{ color: '#92400e', fontSize: 12, marginTop: 2 }}>
              Review reply rates and follow-up sequences to improve booking rate.
            </div>
          </div>
        </div>
      )}

      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#e2d9f3' }}>Analytics & Pipeline</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={load} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
            borderRadius: 8, border: '1px solid #2d1f4a', background: 'transparent',
            color: '#9ca3af', fontSize: 12, cursor: 'pointer',
          }}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button onClick={handleSendSummary} disabled={sending} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
            borderRadius: 8, border: 'none',
            background: 'linear-gradient(90deg,#7c3aed,#a855f7)',
            color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}>
            {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            Send Daily Summary
          </button>
        </div>
      </div>

      {/* Top stat cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <StatCard
          icon={Users} label="New Leads This Week" value={m.leads_week}
          sub={`${m.leads_today} today · ${m.leads_total} total`}
          color="#a78bfa" trend={trend(m.leads_week, m.leads_lweek)}
        />
        <StatCard
          icon={Mail} label="Emails Sent This Week" value={m.emails_week}
          sub={`${m.emails_today} today · ${m.emails_total} total`}
          color="#60a5fa" trend={trend(m.emails_week, m.emails_lweek)}
        />
        <StatCard
          icon={MessageSquare} label="Replies This Week" value={m.replied_week}
          sub={`${m.reply_rate_week}% reply rate`}
          color="#4ade80" trend={trend(m.replied_week, m.replied_lweek)}
        />
        <StatCard
          icon={Calendar} label="Meetings This Week" value={m.meetings_week}
          sub={`${m.meetings_scheduled} scheduled · ${m.meetings_total} total`}
          color={m.low_meetings_alert ? '#f59e0b' : '#34d399'}
          trend={trend(m.meetings_week, m.meetings_lweek)}
        />
      </div>

      {/* Middle row: funnel + daily trend */}
      <div style={{ display: 'flex', gap: 16 }}>

        {/* Funnel */}
        <div style={{ ...card, flex: 1 }}>
          {sectionTitle('Pipeline Funnel')}
          <FunnelBar stages={m.funnel} />
          <div style={{ marginTop: 16, display: 'flex', gap: 12, fontSize: 11, color: '#6b7280' }}>
            <span>Reply rate: <strong style={{ color: '#4ade80' }}>{m.reply_rate_week}%</strong></span>
            <span>Meeting rate: <strong style={{ color: '#34d399' }}>{m.meeting_rate}%</strong></span>
          </div>
        </div>

        {/* Daily trend chart */}
        <div style={{ ...card, flex: 1 }}>
          {sectionTitle('Last 7 Days')}
          <DailyTrendChart trend={m.daily_trend} />
          <div style={{ marginTop: 10, display: 'flex', gap: 14, fontSize: 11, color: '#6b7280' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: '#a78bfa', display: 'inline-block' }} /> Emails
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: '#60a5fa', display: 'inline-block' }} /> Leads
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#4ade80', display: 'inline-block' }} /> Meetings
            </span>
          </div>
        </div>
      </div>

      {/* Bottom row: campaign table + breakdowns */}
      <div style={{ display: 'flex', gap: 16 }}>

        {/* Active campaigns */}
        <div style={{ ...card, flex: 2 }}>
          {sectionTitle('Active Campaigns')}
          {m.campaign_rows?.length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Campaign', 'Emails', 'Replies', 'Meetings', 'Reply %'].map(h => (
                    <th key={h} style={{ padding: '8px 10px', textAlign: h === 'Campaign' ? 'left' : 'center', color: '#4b5563', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #1e0f38' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {m.campaign_rows.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(45,31,74,0.5)' }}>
                    <td style={{ padding: '10px 10px', fontSize: 12, color: '#e2d9f3', fontWeight: 500 }}>{row.name}</td>
                    <td style={{ padding: '10px 10px', textAlign: 'center', fontSize: 12, color: '#9ca3af' }}>{row.emails_sent}</td>
                    <td style={{ padding: '10px 10px', textAlign: 'center', fontSize: 12, color: '#9ca3af' }}>{row.replies}</td>
                    <td style={{ padding: '10px 10px', textAlign: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#a78bfa' }}>{row.meetings}</span>
                    </td>
                    <td style={{ padding: '10px 10px', textAlign: 'center' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                        background: row.reply_rate >= 10 ? 'rgba(74,222,128,0.12)' : 'rgba(107,114,128,0.12)',
                        color: row.reply_rate >= 10 ? '#4ade80' : '#9ca3af',
                      }}>{row.reply_rate}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ color: '#4b5563', fontSize: 12, textAlign: 'center', padding: '24px 0' }}>
              No active campaigns yet.
            </div>
          )}
        </div>

        {/* Right column: breakdowns */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>

          {/* Lead temperature */}
          <div style={card}>
            {sectionTitle('Lead Temperature')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { key: 'hot',  label: 'Hot',  icon: Flame,       color: '#f43f5e' },
                { key: 'warm', label: 'Warm', icon: Thermometer, color: '#f59e0b' },
                { key: 'cold', label: 'Cold', icon: Snowflake,   color: '#60a5fa' },
              ].map(({ key, label, icon: Icon, color }) => {
                const count = m.temp_counts?.[key] || 0;
                const total = Object.values(m.temp_counts || {}).reduce((a, b) => a + b, 0) || 1;
                return (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Icon size={13} style={{ color, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: '#9ca3af', width: 36 }}>{label}</span>
                    <MiniBar value={count} max={total} color={color} />
                    <span style={{ fontSize: 12, color: '#e2d9f3', fontWeight: 600, minWidth: 24, textAlign: 'right' }}>{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Reply sentiment */}
          <div style={card}>
            {sectionTitle('Reply Sentiment')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {Object.entries(m.sentiment_counts || {}).length === 0 ? (
                <div style={{ color: '#4b5563', fontSize: 12 }}>No replies yet.</div>
              ) : (
                Object.entries(m.sentiment_counts).map(([key, count]) => {
                  const cfg = SENTIMENT_CFG[key] || { label: key, color: '#9ca3af' };
                  return (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 11, color: '#9ca3af', width: 80, flexShrink: 0 }}>{cfg.label}</span>
                      <MiniBar value={count} max={totalSentiment} color={cfg.color} />
                      <span style={{ fontSize: 12, color: '#e2d9f3', fontWeight: 600, minWidth: 20, textAlign: 'right' }}>{count}</span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Lead source */}
          <div style={card}>
            {sectionTitle('Lead Sources')}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {Object.entries(m.source_counts || {}).length === 0 ? (
                <div style={{ color: '#4b5563', fontSize: 12 }}>No leads yet.</div>
              ) : (
                Object.entries(m.source_counts).map(([key, count]) => {
                  const cfg = SOURCE_CFG[key] || { label: key, color: '#9ca3af' };
                  return (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 11, color: '#9ca3af', width: 70, flexShrink: 0 }}>{cfg.label}</span>
                      <MiniBar value={count} max={totalSource} color={cfg.color} />
                      <span style={{ fontSize: 12, color: '#e2d9f3', fontWeight: 600, minWidth: 20, textAlign: 'right' }}>{count}</span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

        </div>
      </div>

      {/* Lead status breakdown */}
      <div style={card}>
        {sectionTitle('Lead Status Breakdown')}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {[
            { key: 'new',               label: 'New',         color: '#6b7280' },
            { key: 'qualified',         label: 'Qualified',   color: '#60a5fa' },
            { key: 'contacted',         label: 'Contacted',   color: '#a78bfa' },
            { key: 'replied',           label: 'Replied',     color: '#4ade80' },
            { key: 'meeting_scheduled', label: 'Meeting',     color: '#34d399' },
            { key: 'converted',         label: 'Converted',   color: '#fbbf24' },
            { key: 'disqualified',      label: 'Disqualified',color: '#f87171' },
          ].map(({ key, label, color }) => {
            const count = m.status_counts?.[key] || 0;
            return (
              <div key={key} style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                padding: '12px 18px', borderRadius: 10, minWidth: 90,
                background: `${color}10`, border: `1px solid ${color}25`,
              }}>
                <div style={{ fontSize: 22, fontWeight: 700, color }}>{count}</div>
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{label}</div>
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}
