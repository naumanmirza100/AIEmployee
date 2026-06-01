import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, Flame, Thermometer, Snowflake, Mail, Calendar,
  MessageSquare, TrendingUp, TrendingDown, Minus, RefreshCw,
  Zap, Brain, AlertTriangle, Loader2,
  Activity, ChevronRight, Send, HelpCircle,
  CheckCircle, Copy, ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { useNavigate } from 'react-router-dom';
import {
  getSdrDashboard, getSdrAnalytics, checkAllReplies,
  qualifyAllLeads, researchLeads, sendSdrDailySummary,
  listIcpProfiles,
} from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TEMP_CFG = {
  hot:  { label: 'Hot',  Icon: Flame,       color: '#f43f5e', bg: 'rgba(244,63,94,0.12)',  border: 'rgba(244,63,94,0.25)'  },
  warm: { label: 'Warm', Icon: Thermometer, color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.25)' },
  cold: { label: 'Cold', Icon: Snowflake,   color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.25)' },
};

const STATUS_CFG = {
  new:               { label: 'New',              color: '#6b7280' },
  qualified:         { label: 'Qualified',         color: '#60a5fa' },
  contacted:         { label: 'Contacted',         color: '#a78bfa' },
  replied:           { label: 'Replied',           color: '#4ade80' },
  meeting_scheduled: { label: 'Meeting Scheduled', color: '#34d399' },
  converted:         { label: 'Converted',         color: '#fbbf24' },
  disqualified:      { label: 'Disqualified',      color: '#f87171' },
};

const SOURCE_LABELS = {
  apollo: 'Apollo', apify: 'Apify', ai_generated: 'AI Gen',
  csv_import: 'CSV', manual: 'Manual',
};

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------
const card = {
  background: 'linear-gradient(135deg,rgba(15,10,31,0.95) 0%,rgba(20,8,40,0.95) 100%)',
  border: '1px solid #2d1f4a', borderRadius: 12,
};

const inputStyle = {
  background: 'rgba(30,10,50,0.6)', border: '1px solid #2d1f4a',
  borderRadius: 8, padding: '8px 12px', color: '#e2d9f3',
  outline: 'none', fontSize: 14, width: '100%', boxSizing: 'border-box',
};

function pct(a, b) { return b ? Math.round((a / b) * 100) : 0; }
function SCORE_COLOR(s) { return s >= 70 ? '#f43f5e' : s >= 40 ? '#f59e0b' : '#60a5fa'; }

function trend(curr, prev) {
  if (curr > prev) return { Icon: TrendingUp,   color: '#4ade80', label: `+${curr - prev} vs last wk` };
  if (curr < prev) return { Icon: TrendingDown,  color: '#f87171', label: `−${prev - curr} vs last wk` };
  return             { Icon: Minus,             color: '#6b7280', label: 'same as last wk' };
}

// ---------------------------------------------------------------------------
// Micro-components
// ---------------------------------------------------------------------------
function KPICard({ Icon, label, value, sub, color, trendData, onClick }) {
  const T = trendData;
  return (
    <div
      style={{
        ...card, padding: '16px 18px', cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.2s', flex: 1, minWidth: 150,
      }}
      onMouseEnter={e => onClick && (e.currentTarget.style.borderColor = color)}
      onMouseLeave={e => onClick && (e.currentTarget.style.borderColor = '#2d1f4a')}
      onClick={onClick}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `${color}18` }}>
          <Icon size={17} style={{ color }} />
        </div>
        {T && <div style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: T.color }}><T.Icon size={11} /><span>{T.label}</span></div>}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: '#e2d9f3', lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#4b5563', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function MiniBar({ value, max, color }) {
  return (
    <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.07)' }}>
      <div style={{ height: '100%', borderRadius: 3, minWidth: value > 0 ? 3 : 0, width: `${max ? Math.min(100, (value / max) * 100) : 0}%`, background: color, transition: 'width 0.5s' }} />
    </div>
  );
}

function SectionTitle({ children, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <span style={{ fontSize: 14, fontWeight: 700, color: '#c4b5fd', letterSpacing: '0.01em' }}>{children}</span>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Setup Guide content (same as in SDRLeadsTab)
// ---------------------------------------------------------------------------
function SetupGuideContent({ which, copiedKey, setCopiedKey }) {
  const apifySteps = [
    { step: 1, title: 'Create an Apify account', detail: 'Go to apify.com and sign up. Upgrade to a paid plan (Starter $49/month) for production-level scraping.', link: 'https://apify.com/sign-up', linkLabel: 'apify.com/sign-up' },
    { step: 2, title: 'Get your API Token', detail: 'After login → profile icon → Settings → Integrations. Copy your "Personal API token".', note: 'URL: console.apify.com/account/integrations' },
    { step: 3, title: 'Add token to your .env file', detail: 'Open .env in your project root and add this line:', code: 'APIFY_API_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxxxxxx' },
    { step: 4, title: 'Choose your scraping actor', detail: 'Default actor searches Google for LinkedIn profiles. Set in .env:', code: 'APIFY_ACTOR_ID=apify/google-search-scraper' },
    { step: 5, title: 'Restart the server & generate leads', detail: 'Stop your Django server (Ctrl+C) and start again. Then generate leads with Apify selected.', code: 'python manage.py runserver' },
  ];
  const apolloSteps = [
    { step: 1, title: 'Create an Apollo.io account', detail: 'Go to app.apollo.io and sign up. Free plan has 50 credits/month but no API access.', link: 'https://app.apollo.io', linkLabel: 'app.apollo.io' },
    { step: 2, title: 'Upgrade to a paid plan', detail: 'Settings → Plans & Billing. The "Basic" plan ($49/month) includes People Search API. Without it you get a 403 error.' },
    { step: 3, title: 'Get your API Key', detail: 'Go to developer.apollo.io → Create Account → Create API Key. Copy it immediately — shown only once.', link: 'https://developer.apollo.io', linkLabel: 'developer.apollo.io' },
    { step: 4, title: 'Add API key to your .env file', detail: 'Open .env in your project root and add:', code: 'APOLLO_API_KEY=your_apollo_api_key_here' },
    { step: 5, title: 'Restart the server & generate leads', detail: 'Stop the server, restart, then select Apollo.io and click Generate.', code: 'python manage.py runserver' },
  ];

  const steps = which === 'apify' ? apifySteps : apolloSteps;
  const accent = which === 'apify' ? '#a855f7' : '#3b82f6';
  const accentBg = which === 'apify' ? 'rgba(168,85,247,0.2)' : 'rgba(59,130,246,0.2)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 0 8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
        <span>⚠️</span>
        <span style={{ color: '#fcd34d', fontSize: 13, fontWeight: 600 }}>
          {which === 'apify' ? 'Apify requires a paid plan for production-level lead scraping' : 'Apollo People Search API requires a PAID plan ($49+/month)'}
        </span>
      </div>
      {which === 'apollo' && (
        <div style={{ padding: '8px 12px', borderRadius: 8, background: 'rgba(168,85,247,0.06)', border: '1px solid #2d1f4a', color: '#9ca3af', fontSize: 12 }}>
          💡 <strong style={{ color: '#e2d9f3' }}>Recommendation:</strong> Use <strong style={{ color: '#a855f7' }}>Apify</strong> for lead generation if you don't have a paid Apollo plan.
        </div>
      )}
      {steps.map(s => (
        <div key={s.step} style={{ display: 'flex', gap: 12 }}>
          <div style={{ flexShrink: 0, width: 24, height: 24, borderRadius: '50%', background: accentBg, border: `1px solid ${accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: accent, fontSize: 12, fontWeight: 700, marginTop: 2 }}>{s.step}</div>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#e2d9f3', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{s.title}</div>
            <div style={{ color: '#9ca3af', fontSize: 12, lineHeight: 1.5 }}>{s.detail}</div>
            {s.link && <a href={s.link} target="_blank" rel="noreferrer" style={{ color: accent, fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 4 }}><ExternalLink size={11} />{s.linkLabel}</a>}
            {s.note && <div style={{ marginTop: 4, padding: '4px 8px', borderRadius: 6, background: 'rgba(255,255,255,0.04)', color: '#6b7280', fontSize: 11, fontFamily: 'monospace' }}>{s.note}</div>}
            {s.code && (
              <div style={{ marginTop: 6, padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid #1e1035', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <code style={{ color: accent, fontSize: 11, flex: 1, wordBreak: 'break-all' }}>{s.code}</code>
                <button
                  onClick={() => { navigator.clipboard.writeText(s.code); setCopiedKey(s.step); setTimeout(() => setCopiedKey(null), 2000); }}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedKey === s.step ? '#4ade80' : '#6b7280', flexShrink: 0 }}
                >
                  {copiedKey === s.step ? <CheckCircle size={13} /> : <Copy size={13} />}
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===========================================================================
// Main component
// ===========================================================================
export default function SDROverviewTab() {
  const { toast } = useToast();
  const navigate = useNavigate();

  // Dashboard data
  const [dash, setDash]       = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState('');

  // Generate Leads modal
  const [showGenModal, setShowGenModal]     = useState(false);
  const [genSource, setGenSource]           = useState('apify');
  const [genCount, setGenCount]             = useState(10);
  const [genIcpId, setGenIcpId]             = useState('');
  const [icpProfiles, setIcpProfiles]       = useState([]);
  const [generating, setGenerating]         = useState(false);
  const [showSetupGuide, setShowSetupGuide] = useState(null); // 'apify' | 'apollo'
  const [copiedKey, setCopiedKey]           = useState(null);

  // ── Load dashboard data ────────────────────────────────────────────────
  const load = useCallback(async () => {
    try {
      setLoading(true);
      // companyApi returns response.json() directly
      // Backend shape: { status, data: { stats, recent_hot_leads } } for dashboard
      //                { status, data: { leads_today, ... } } for analytics
      const [dRes, mRes] = await Promise.all([getSdrDashboard(), getSdrAnalytics()]);
      setDash(dRes?.data   || null);
      setMetrics(mRes?.data || null);
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Unknown error';
      toast({ title: 'Failed to load dashboard', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // ── Open Generate Leads modal (fetch ICP profiles first) ───────────────
  const openGenModal = async () => {
    try {
      const profiles = await listIcpProfiles();
      setIcpProfiles(profiles);
      if (profiles.length > 0) {
        setGenIcpId(profiles.find(p => p.is_active)?.id || profiles[0].id);
      }
    } catch (_) { setIcpProfiles([]); }
    setShowGenModal(true);
  };

  // ── Generate leads ────────────────────────────────────────────────────
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const resp = await researchLeads({ count: genCount, source: genSource, icp_id: genIcpId || undefined });
      const created = resp?.data?.leads_created ?? resp?.leads_created ?? '?';
      toast({ title: `✅ ${created} leads generated!`, description: `Source: ${genSource.toUpperCase()}` });
      setShowGenModal(false);
      await load();
    } catch (e) {
      toast({ title: 'Generate failed', description: e?.response?.data?.message || e.message, variant: 'destructive' });
    } finally { setGenerating(false); }
  };

  // ── Other quick actions ───────────────────────────────────────────────
  async function runAction(key, fn, successMsg) {
    setActionBusy(key);
    try {
      const res = await fn();
      toast({ title: '✅ Done', description: res?.data?.message || res?.data?.details || successMsg });
      await load();
    } catch (err) {
      toast({ title: 'Error', description: err?.response?.data?.message || err?.message, variant: 'destructive' });
    } finally { setActionBusy(''); }
  }

  // ── Derived values ────────────────────────────────────────────────────
  const stats    = dash?.stats || {};
  const hotLeads = dash?.recent_hot_leads || [];
  const m        = metrics || {};

  const leadsTotal  = m.leads_total   ?? stats.total  ?? 0;
  const leadsWeek   = m.leads_week    ?? 0;
  const leadsLweek  = m.leads_lweek   ?? 0;
  const emailsWeek  = m.emails_week   ?? 0;
  const emailsLweek = m.emails_lweek  ?? 0;
  const meetWeek    = m.meetings_week  ?? 0;
  const meetLweek   = m.meetings_lweek ?? 0;
  const repliedWeek = m.replied_week  ?? 0;
  const repliedLwk  = m.replied_lweek ?? 0;
  const replyRate   = m.reply_rate_week ?? 0;
  const meetTotal   = m.meetings_total  ?? 0;
  const campActive  = m.campaigns_active ?? 0;
  const lowAlert    = m.low_meetings_alert ?? false;
  const alertThresh = m.meetings_alert_threshold ?? 5;

  const statusCounts = m.status_counts   || {};
  const tempCounts   = m.temp_counts     || {};
  const sentCounts   = m.sentiment_counts || {};
  const campaignRows = m.campaign_rows   || [];
  const funnel       = m.funnel          || [];
  const dailyTrend   = m.daily_trend     || [];

  const maxCampEmails  = Math.max(...campaignRows.map(r => r.emails_sent), 1);
  const maxDailyEmails = Math.max(...dailyTrend.map(d => d.emails), 1);

  // ── Loading state ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 320, gap: 12 }}>
        <Loader2 size={32} style={{ color: '#a78bfa', animation: 'spin 1s linear infinite' }} />
        <span style={{ color: '#6b7280', fontSize: 14 }}>Loading dashboard…</span>
        <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  // ── Main render ───────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Alert banner */}
      {lowAlert && (
        <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: 10, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <AlertTriangle size={16} style={{ color: '#f59e0b', flexShrink: 0 }} />
          <span style={{ fontSize: 13, color: '#fcd34d' }}>
            <strong>Low meetings alert:</strong> Only <strong>{meetWeek}</strong> meeting(s) this week — below target of {alertThresh}. Review reply rates or adjust email sequences.
          </span>
        </div>
      )}

      {/* KPI cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KPICard Icon={Users}         label="Total Leads"        value={leadsTotal} color="#a78bfa"
          sub={`${stats.hot ?? tempCounts.hot ?? 0} hot · ${stats.warm ?? tempCounts.warm ?? 0} warm`}
          trendData={trend(leadsWeek, leadsLweek)} onClick={() => navigate('/ai-sdr/leads')} />
        <KPICard Icon={Mail}          label="Emails This Week"   value={emailsWeek} color="#60a5fa"
          sub={`${m.emails_total ?? 0} total sent`}
          trendData={trend(emailsWeek, emailsLweek)} onClick={() => navigate('/ai-sdr/outreach')} />
        <KPICard Icon={MessageSquare} label="Replies This Week"  value={repliedWeek} color="#4ade80"
          sub={`${replyRate}% reply rate`} trendData={trend(repliedWeek, repliedLwk)} />
        <KPICard Icon={Calendar}      label="Meetings This Week" value={meetWeek}   color="#34d399"
          sub={`${meetTotal} total · ${m.meetings_scheduled ?? 0} scheduled`}
          trendData={trend(meetWeek, meetLweek)} onClick={() => navigate('/ai-sdr/meetings')} />
        <KPICard Icon={Activity}      label="Active Campaigns"   value={campActive} color="#f59e0b"
          sub={`${m.campaigns_total ?? 0} total`} onClick={() => navigate('/ai-sdr/outreach')} />
      </div>

      {/* Quick Actions */}
      <div style={{ ...card, padding: '14px 18px' }}>
        <SectionTitle>⚡ Quick Actions</SectionTitle>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {/* Research Leads — opens modal */}
          <button
            disabled={!!actionBusy || generating}
            onClick={openGenModal}
            style={{
              display: 'flex', alignItems: 'center', gap: 7, padding: '9px 14px',
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 9, color: '#e2d9f3', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = '#a78bfa'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; }}
          >
            <Brain size={14} style={{ color: '#a78bfa' }} /> Research Leads
          </button>

          {/* Other actions */}
          {[
            { key: 'qualify',  label: 'Qualify All',       color: '#f59e0b', Icon: Brain,     fn: () => qualifyAllLeads() },
            { key: 'replies',  label: 'Check Replies',     color: '#4ade80', Icon: RefreshCw, fn: () => checkAllReplies() },
            { key: 'summary',  label: 'Send Daily Report', color: '#60a5fa', Icon: Send,      fn: () => sendSdrDailySummary() },
          ].map(({ key, label, color, Icon, fn }) => (
            <button key={key} disabled={!!actionBusy} onClick={() => runAction(key, fn, `${label} complete`)}
              style={{
                display: 'flex', alignItems: 'center', gap: 7, padding: '9px 14px',
                background: actionBusy === key ? `${color}22` : 'rgba(255,255,255,0.04)',
                border: `1px solid ${actionBusy === key ? color : 'rgba(255,255,255,0.1)'}`,
                borderRadius: 9, color: '#e2d9f3', fontSize: 13,
                cursor: actionBusy ? 'not-allowed' : 'pointer', transition: 'all 0.2s',
                opacity: actionBusy && actionBusy !== key ? 0.5 : 1,
              }}
              onMouseEnter={e => { if (!actionBusy) e.currentTarget.style.borderColor = color; }}
              onMouseLeave={e => { if (!actionBusy) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; }}
            >
              {actionBusy === key
                ? <Loader2 size={14} style={{ color, animation: 'spin 1s linear infinite' }} />
                : <Icon size={14} style={{ color }} />}
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Hot leads + Funnel */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16 }}>

        {/* Hot leads */}
        <div style={{ ...card, padding: '14px 18px' }}>
          <SectionTitle>
            🔥 Top Hot Leads
            <button onClick={() => navigate('/ai-sdr/leads')} style={{ display:'flex',alignItems:'center',gap:4,fontSize:12,color:'#a78bfa',background:'none',border:'none',cursor:'pointer' }}>
              View all <ChevronRight size={13} />
            </button>
          </SectionTitle>
          {hotLeads.length === 0 ? (
            <div style={{ textAlign:'center',padding:'24px 0',color:'#4b5563',fontSize:13 }}>
              No hot leads yet — click <strong style={{ color:'#a78bfa' }}>Research Leads</strong> above
            </div>
          ) : (
            <div style={{ display:'flex',flexDirection:'column',gap:8 }}>
              {hotLeads.map(lead => (
                <div key={lead.id} style={{ display:'flex',alignItems:'center',gap:12,background:'rgba(255,255,255,0.03)',borderRadius:9,padding:'10px 12px',border:'1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ width:38,height:38,borderRadius:10,flexShrink:0,background:`${SCORE_COLOR(lead.score)}18`,border:`1px solid ${SCORE_COLOR(lead.score)}40`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:13,fontWeight:700,color:SCORE_COLOR(lead.score) }}>
                    {lead.score ?? '—'}
                  </div>
                  <div style={{ flex:1,minWidth:0 }}>
                    <div style={{ fontSize:13,fontWeight:600,color:'#e2d9f3',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis' }}>{lead.full_name || '(No Name)'}</div>
                    <div style={{ fontSize:11,color:'#6b7280',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis' }}>{[lead.job_title,lead.company_name].filter(Boolean).join(' · ') || lead.email}</div>
                  </div>
                  <div style={{ display:'flex',alignItems:'center',gap:6,flexShrink:0 }}>
                    {lead.temperature && TEMP_CFG[lead.temperature] && (() => {
                      const { Icon: TIcon, color, bg, border } = TEMP_CFG[lead.temperature];
                      return <span style={{ display:'flex',alignItems:'center',gap:3,fontSize:11,fontWeight:600,color,background:bg,border:`1px solid ${border}`,borderRadius:6,padding:'2px 7px' }}><TIcon size={11} />{TEMP_CFG[lead.temperature].label}</span>;
                    })()}
                    {lead.status && STATUS_CFG[lead.status] && (
                      <span style={{ fontSize:10,fontWeight:600,borderRadius:5,padding:'2px 7px',color:STATUS_CFG[lead.status].color,background:`${STATUS_CFG[lead.status].color}18`,border:`1px solid ${STATUS_CFG[lead.status].color}35` }}>
                        {STATUS_CFG[lead.status].label}
                      </span>
                    )}
                    <span style={{ fontSize:10,color:'#4b5563' }}>{SOURCE_LABELS[lead.source] || lead.source}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Funnel */}
        <div style={{ ...card, padding:'14px 18px' }}>
          <SectionTitle>📊 Pipeline Funnel</SectionTitle>
          {funnel.length === 0
            ? <div style={{ color:'#4b5563',fontSize:12,textAlign:'center',paddingTop:20 }}>No data yet</div>
            : <div style={{ display:'flex',flexDirection:'column',gap:12 }}>
                {funnel.map((s,i) => (
                  <div key={i}>
                    <div style={{ display:'flex',justifyContent:'space-between',marginBottom:4 }}>
                      <span style={{ fontSize:12,color:'#9ca3af' }}>{s.stage}</span>
                      <span style={{ fontSize:12,color:'#e2d9f3',fontWeight:600 }}>
                        {s.count}<span style={{ fontSize:10,color:'#4b5563',fontWeight:400 }}> ({pct(s.count,funnel[0]?.count??1)}%)</span>
                      </span>
                    </div>
                    <div style={{ height:7,borderRadius:4,background:'rgba(255,255,255,0.06)' }}>
                      <div style={{ height:'100%',borderRadius:4,width:`${pct(s.count,funnel[0]?.count??1)}%`,background:s.color,transition:'width 0.6s ease',minWidth:s.count>0?4:0 }} />
                    </div>
                  </div>
                ))}
              </div>}
        </div>
      </div>

      {/* 7-day trend + Active campaigns */}
      <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr',gap:16 }}>

        {/* 7-day chart */}
        <div style={{ ...card,padding:'14px 18px' }}>
          <SectionTitle>📈 Last 7 Days</SectionTitle>
          {dailyTrend.length === 0
            ? <div style={{ color:'#4b5563',fontSize:12,textAlign:'center',paddingTop:20 }}>No data yet</div>
            : <>
                <div style={{ display:'flex',gap:14,marginBottom:12,fontSize:11 }}>
                  {[['#60a5fa','Emails'],['#a78bfa','Leads'],['#34d399','Meetings']].map(([c,l]) => (
                    <span key={l} style={{ display:'flex',alignItems:'center',gap:5,color:'#6b7280' }}>
                      <span style={{ width:10,height:10,borderRadius:3,background:c,display:'inline-block' }} />{l}
                    </span>
                  ))}
                </div>
                <div style={{ display:'flex',alignItems:'flex-end',gap:6,height:90 }}>
                  {dailyTrend.map((d,i) => {
                    const maxAll = Math.max(maxDailyEmails, Math.max(...dailyTrend.map(x => x.leads),1));
                    return (
                      <div key={i} style={{ flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:3 }}>
                        <div style={{ display:'flex',alignItems:'flex-end',gap:2,height:70 }}>
                          {[{val:d.emails,color:'#60a5fa'},{val:d.leads,color:'#a78bfa'},{val:d.meetings,color:'#34d399'}].map(({val,color},j) => (
                            <div key={j} style={{ width:7,borderRadius:'2px 2px 0 0',height:`${maxAll?Math.max(2,(val/maxAll)*70):2}px`,background:color,transition:'height 0.5s ease',opacity:val===0?0.25:1 }} />
                          ))}
                        </div>
                        <span style={{ fontSize:10,color:'#4b5563' }}>{d.day}</span>
                      </div>
                    );
                  })}
                </div>
              </>}
        </div>

        {/* Active campaigns */}
        <div style={{ ...card,padding:'14px 18px' }}>
          <SectionTitle>
            🚀 Active Campaigns
            <button onClick={() => navigate('/ai-sdr/outreach')} style={{ display:'flex',alignItems:'center',gap:4,fontSize:12,color:'#a78bfa',background:'none',border:'none',cursor:'pointer' }}>Manage <ChevronRight size={13} /></button>
          </SectionTitle>
          {campaignRows.length === 0
            ? <div style={{ color:'#4b5563',fontSize:12,textAlign:'center',paddingTop:20 }}>No active campaigns</div>
            : <div style={{ display:'flex',flexDirection:'column',gap:10 }}>
                {campaignRows.map(c => (
                  <div key={c.id} style={{ background:'rgba(255,255,255,0.03)',borderRadius:9,padding:'10px 12px',border:'1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:7 }}>
                      <span style={{ fontSize:13,fontWeight:600,color:'#e2d9f3',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:'55%' }}>{c.name}</span>
                      <div style={{ display:'flex',gap:10,fontSize:11,color:'#6b7280' }}>
                        <span>{c.emails_sent} <span style={{ color:'#4b5563' }}>sent</span></span>
                        <span style={{ color:'#4ade80' }}>{c.replies} <span style={{ color:'#4b5563' }}>replies</span></span>
                        <span style={{ color:'#34d399',fontWeight:600 }}>{c.meetings} mtg</span>
                      </div>
                    </div>
                    <div style={{ display:'flex',alignItems:'center',gap:8 }}>
                      <MiniBar value={c.emails_sent} max={maxCampEmails} color="#60a5fa" />
                      <span style={{ fontSize:10,color:'#a78bfa',fontWeight:600,whiteSpace:'nowrap' }}>{c.reply_rate}% reply</span>
                    </div>
                  </div>
                ))}
              </div>}
        </div>
      </div>

      {/* Breakdowns row */}
      <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:16 }}>

        {/* Lead status */}
        <div style={{ ...card,padding:'14px 18px' }}>
          <SectionTitle>👤 Lead Status</SectionTitle>
          {Object.keys(statusCounts).length === 0
            ? <div style={{ color:'#4b5563',fontSize:12,textAlign:'center',paddingTop:12 }}>No leads yet</div>
            : <div style={{ display:'flex',flexDirection:'column',gap:8 }}>
                {Object.entries(STATUS_CFG).map(([key,cfg]) => {
                  const cnt = statusCounts[key] ?? 0;
                  if (!cnt) return null;
                  const maxC = Math.max(...Object.values(statusCounts),1);
                  return (
                    <div key={key} style={{ display:'flex',alignItems:'center',gap:8 }}>
                      <span style={{ fontSize:11,color:'#6b7280',width:100,flexShrink:0 }}>{cfg.label}</span>
                      <MiniBar value={cnt} max={maxC} color={cfg.color} />
                      <span style={{ fontSize:11,fontWeight:600,color:cfg.color,width:24,textAlign:'right' }}>{cnt}</span>
                    </div>
                  );
                })}
              </div>}
        </div>

        {/* Temperature */}
        <div style={{ ...card,padding:'14px 18px' }}>
          <SectionTitle>🌡️ Temperature</SectionTitle>
          <div style={{ display:'flex',flexDirection:'column',gap:10 }}>
            {['hot','warm','cold'].map(key => {
              const cfg = TEMP_CFG[key];
              const cnt = tempCounts[key] ?? 0;
              const maxC = Math.max(...['hot','warm','cold'].map(k => tempCounts[k]??0),1);
              return (
                <div key={key}>
                  <div style={{ display:'flex',justifyContent:'space-between',marginBottom:4 }}>
                    <span style={{ display:'flex',alignItems:'center',gap:5,fontSize:12,color:cfg.color }}><cfg.Icon size={12} />{cfg.label}</span>
                    <span style={{ fontSize:12,fontWeight:700,color:cfg.color }}>{cnt}</span>
                  </div>
                  <div style={{ height:6,borderRadius:3,background:'rgba(255,255,255,0.06)' }}>
                    <div style={{ height:'100%',borderRadius:3,background:cfg.color,transition:'width 0.5s',width:`${pct(cnt,maxC)}%`,minWidth:cnt>0?4:0 }} />
                  </div>
                </div>
              );
            })}
            {(stats.unscored??0)>0 && (
              <div style={{ display:'flex',justifyContent:'space-between',marginTop:4,paddingTop:8,borderTop:'1px solid rgba(255,255,255,0.07)' }}>
                <span style={{ fontSize:11,color:'#4b5563' }}>Unscored</span>
                <span style={{ fontSize:11,color:'#4b5563',fontWeight:600 }}>{stats.unscored}</span>
              </div>
            )}
          </div>
        </div>

        {/* Reply sentiment */}
        <div style={{ ...card,padding:'14px 18px' }}>
          <SectionTitle>💬 Reply Sentiment</SectionTitle>
          {Object.keys(sentCounts).length === 0
            ? <div style={{ color:'#4b5563',fontSize:12,textAlign:'center',paddingTop:12 }}>No replies yet</div>
            : <div style={{ display:'flex',flexDirection:'column',gap:8 }}>
                {[
                  { key:'positive',       label:'🎉 Positive',       color:'#4ade80' },
                  { key:'wants_more_info',label:'ℹ️ Wants Info',     color:'#60a5fa' },
                  { key:'out_of_office',  label:'🏖️ Out of Office', color:'#f59e0b' },
                  { key:'neutral',        label:'💬 Neutral',        color:'#9ca3af' },
                  { key:'not_interested', label:'❌ Not Interested', color:'#f87171' },
                ].map(({ key,label,color }) => {
                  const cnt = sentCounts[key] ?? 0;
                  if (!cnt) return null;
                  const maxS = Math.max(...Object.values(sentCounts),1);
                  return (
                    <div key={key} style={{ display:'flex',alignItems:'center',gap:8 }}>
                      <span style={{ fontSize:11,color:'#6b7280',width:110,flexShrink:0 }}>{label}</span>
                      <MiniBar value={cnt} max={maxS} color={color} />
                      <span style={{ fontSize:11,fontWeight:600,color,width:20,textAlign:'right' }}>{cnt}</span>
                    </div>
                  );
                })}
              </div>}
        </div>
      </div>

      {/* Refresh footer */}
      <div style={{ display:'flex',justifyContent:'flex-end',paddingTop:4 }}>
        <button onClick={load} disabled={loading} style={{ display:'flex',alignItems:'center',gap:6,fontSize:12,color:'#4b5563',background:'none',border:'none',cursor:'pointer',padding:'4px 8px' }}>
          <RefreshCw size={13} style={{ animation:loading?'spin 1s linear infinite':'none' }} /> Refresh dashboard
        </button>
      </div>

      {/* ================================================================
          GENERATE LEADS MODAL
          ================================================================ */}
      <Dialog open={showGenModal} onOpenChange={setShowGenModal}>
        <DialogContent style={{ background:'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',border:'1px solid #2d1f4a',color:'#e2d9f3',maxWidth:480 }}>
          <DialogHeader>
            <DialogTitle style={{ color:'#e2d9f3',display:'flex',alignItems:'center',gap:8 }}>
              <Zap size={18} color="#a855f7" /> Generate Leads Automatically
            </DialogTitle>
          </DialogHeader>

          <div style={{ display:'flex',flexDirection:'column',gap:18,padding:'8px 0' }}>

            {/* Source selector */}
            <div>
              <label style={{ color:'#9ca3af',fontSize:12,display:'block',marginBottom:8 }}>Source</label>
              <div style={{ display:'flex',gap:8 }}>
                {[
                  { key:'apify',  label:'⚡ Apify',    desc:'Web scraping — LinkedIn & Google', color:'#a855f7' },
                  { key:'apollo', label:'🚀 Apollo.io', desc:'Verified B2B contact database',    color:'#3b82f6' },
                ].map(s => (
                  <button key={s.key} onClick={() => setGenSource(s.key)} style={{
                    flex:1, padding:'10px 14px', borderRadius:10, cursor:'pointer', textAlign:'left',
                    background: genSource===s.key ? `${s.color}22` : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${genSource===s.key ? s.color : '#2d1f4a'}`,
                    transition:'all 0.2s',
                  }}>
                    <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center' }}>
                      <span style={{ color:'#e2d9f3',fontWeight:600,fontSize:14 }}>{s.label}</span>
                      <div style={{ display:'flex',alignItems:'center',gap:5 }}>
                        <span style={{ fontSize:10,padding:'1px 6px',borderRadius:4,background:'rgba(234,179,8,0.15)',color:'#fcd34d' }}>PAID</span>
                        <span
                          title="How to Connect"
                          onClick={e => { e.stopPropagation(); setShowSetupGuide(s.key); }}
                          style={{ color:'#4b5563',cursor:'pointer',display:'flex',alignItems:'center',transition:'color 0.2s' }}
                          onMouseEnter={e => e.currentTarget.style.color = s.color}
                          onMouseLeave={e => e.currentTarget.style.color = '#4b5563'}
                        >
                          <HelpCircle size={13} />
                        </span>
                      </div>
                    </div>
                    <div style={{ color:'#6b7280',fontSize:12,marginTop:2 }}>{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* ICP Profile selector */}
            {icpProfiles.length > 1 && (
              <div>
                <label style={{ color:'#9ca3af',fontSize:12,display:'block',marginBottom:6 }}>ICP Profile</label>
                <select value={genIcpId} onChange={e => setGenIcpId(e.target.value)} style={{ ...inputStyle }}>
                  {icpProfiles.map(p => <option key={p.id} value={p.id}>{p.name}{p.is_active?' (Active)':''}</option>)}
                </select>
              </div>
            )}
            {icpProfiles.length === 1 && (
              <div style={{ padding:'8px 12px',borderRadius:8,background:'rgba(168,85,247,0.08)',border:'1px solid #2d1f4a' }}>
                <span style={{ color:'#9ca3af',fontSize:12 }}>ICP: </span>
                <span style={{ color:'#e2d9f3',fontSize:13,fontWeight:600 }}>{icpProfiles[0].name}</span>
              </div>
            )}
            {icpProfiles.length === 0 && (
              <div style={{ padding:12,borderRadius:8,background:'rgba(244,63,94,0.08)',border:'1px solid rgba(244,63,94,0.2)',color:'#f87171',fontSize:13 }}>
                No ICP profile found. Set up your ICP profile in the Leads tab first.
              </div>
            )}

            {/* Count slider */}
            <div>
              <label style={{ color:'#9ca3af',fontSize:12,display:'block',marginBottom:6 }}>
                Number of Leads: <span style={{ color:'#a855f7',fontWeight:700 }}>{genCount}</span>
              </label>
              <input type="range" min={5} max={50} step={5} value={genCount} onChange={e => setGenCount(Number(e.target.value))} style={{ width:'100%',accentColor:'#a855f7' }} />
              <div style={{ display:'flex',justifyContent:'space-between',color:'#4b5563',fontSize:11,marginTop:2 }}>
                <span>5</span><span>50</span>
              </div>
            </div>

          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGenModal(false)} style={{ border:'1px solid #2d1f4a',color:'#9ca3af',borderRadius:8 }}>Cancel</Button>
            <Button onClick={handleGenerate} disabled={generating || icpProfiles.length === 0} style={{ background:'linear-gradient(90deg,#7c3aed,#a855f7)',color:'#fff',border:'none',borderRadius:8,fontWeight:600,display:'flex',alignItems:'center',gap:6 }}>
              {generating ? <Loader2 size={13} style={{ animation:'spin 1s linear infinite' }} /> : <Zap size={13} />}
              {generating ? 'Generating...' : `Generate ${genCount} Leads`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ================================================================
          SETUP GUIDE MODAL
          ================================================================ */}
      <Dialog open={!!showSetupGuide} onOpenChange={() => setShowSetupGuide(null)}>
        <DialogContent style={{ background:'linear-gradient(135deg,#0f0a1f 0%,#14082a 100%)',border:'1px solid #2d1f4a',color:'#e2d9f3',maxWidth:560,maxHeight:'85vh',overflowY:'auto' }}>
          <DialogHeader>
            <DialogTitle style={{ color:'#e2d9f3',display:'flex',alignItems:'center',gap:8 }}>
              {showSetupGuide === 'apify'
                ? <><span style={{ fontSize:20 }}>⚡</span> How to Connect Apify</>
                : <><span style={{ fontSize:20 }}>🚀</span> How to Connect Apollo.io</>}
            </DialogTitle>
          </DialogHeader>

          {showSetupGuide && (
            <SetupGuideContent which={showSetupGuide} copiedKey={copiedKey} setCopiedKey={setCopiedKey} />
          )}

          <DialogFooter>
            <Button
              onClick={() => { setGenSource(showSetupGuide); setShowSetupGuide(null); }}
              style={{ background: showSetupGuide === 'apify' ? 'linear-gradient(90deg,#7c3aed,#a855f7)' : 'linear-gradient(90deg,#1d4ed8,#3b82f6)', color:'#fff',border:'none',borderRadius:8,fontWeight:600 }}
            >
              Got it — Use {showSetupGuide === 'apify' ? 'Apify' : 'Apollo.io'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
