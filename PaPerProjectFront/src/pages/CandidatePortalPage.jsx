import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Loader2, Mail, Send, CheckCircle2, Clock, Briefcase, MapPin,
  Calendar, Video, ChevronDown, ChevronUp, ExternalLink, ChevronRight,
  AlertCircle, Phone, GraduationCap, Building2, DollarSign,
  FileText, MessageSquare, RefreshCw, ArrowLeft, User, Linkedin,
  Github, LayoutGrid, Shield, Sparkles, X, Link2,
} from 'lucide-react';

const API_BASE     = import.meta.env.VITE_API_URL     || 'http://localhost:8000/api';
const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

/* ─── formatters ─────────────────────────────────────────────────────────── */
const fmt     = (iso) => iso ? new Date(iso).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' }) : '—';
const fmtFull = (iso) => iso ? new Date(iso).toLocaleString('en-GB', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' }) : null;

/* ─── config maps ────────────────────────────────────────────────────────── */
const STATUS = {
  pending:     { label:'Under Review', color:'#60a5fa', bg:'rgba(59,130,246,0.12)',  border:'rgba(59,130,246,0.3)',  dot:'#3b82f6' },
  reviewed:    { label:'Reviewed',     color:'#fbbf24', bg:'rgba(234,179,8,0.12)',   border:'rgba(234,179,8,0.3)',   dot:'#eab308' },
  shortlisted: { label:'Shortlisted',  color:'#34d399', bg:'rgba(16,185,129,0.12)',  border:'rgba(16,185,129,0.3)',  dot:'#10b981' },
  rejected:    { label:'Not Selected', color:'#f87171', bg:'rgba(239,68,68,0.12)',   border:'rgba(239,68,68,0.3)',   dot:'#ef4444' },
};
const INTERVIEW = {
  PENDING:     { label:'Awaiting Slot', color:'#f59e0b', bg:'rgba(245,158,11,0.1)'  },
  SCHEDULED:   { label:'Scheduled',     color:'#34d399', bg:'rgba(16,185,129,0.1)'  },
  COMPLETED:   { label:'Completed',     color:'#818cf8', bg:'rgba(129,140,248,0.1)' },
  CANCELLED:   { label:'Cancelled',     color:'#f87171', bg:'rgba(239,68,68,0.1)'   },
  RESCHEDULED: { label:'Rescheduled',   color:'#f59e0b', bg:'rgba(245,158,11,0.1)'  },
};

/* ─── small reusables ────────────────────────────────────────────────────── */
const StatusPill = ({ s }) => {
  const c = STATUS[s] || STATUS.pending;
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
      style={{ background:c.bg, border:`1px solid ${c.border}`, color:c.color }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background:c.dot }} />
      {c.label}
    </span>
  );
};

const InterviewPill = ({ status }) => {
  const c = INTERVIEW[status] || {};
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium"
      style={{ background:c.bg, color:c.color, border:`1px solid ${c.color}33` }}>
      <Video className="w-3 h-3" />{c.label || status}
    </span>
  );
};

/* ─── Timeline ───────────────────────────────────────────────────────────── */
const STEPS = [
  { key:'submitted',   label:'Submitted'    },
  { key:'review',      label:'Under Review' },
  { key:'shortlisted', label:'Shortlisted'  },
  { key:'interview',   label:'Interview'    },
  { key:'decision',    label:'Decision'     },
];

function getStepState(step, appStatus, interview) {
  const hasInterview   = !!interview;
  const interviewDone  = interview?.status === 'COMPLETED';
  const shortlisted    = appStatus === 'shortlisted' || hasInterview;
  const reviewed       = appStatus !== 'pending';
  if (step === 'submitted')   return 'done';
  if (step === 'review')      return reviewed ? 'done' : 'active';
  if (step === 'shortlisted') return shortlisted ? 'done' : reviewed ? 'active' : 'future';
  if (step === 'interview')   return interviewDone ? 'done' : hasInterview ? 'active' : 'future';
  if (step === 'decision')    return interviewDone ? 'active' : 'future';
  return 'future';
}

function MiniTimeline({ appStatus, interview }) {
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((step, i) => {
        const state = getStepState(step.key, appStatus, interview);
        return (
          <React.Fragment key={step.key}>
            <div className="flex flex-col items-center gap-1">
              <div className="w-6 h-6 rounded-full flex items-center justify-center"
                style={{
                  background: state === 'done' ? '#10b981' : state === 'active' ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.06)',
                  border: state === 'active' ? '2px solid #6366f1' : '2px solid transparent',
                }}>
                {state === 'done'
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-white" />
                  : <div className="w-1.5 h-1.5 rounded-full"
                      style={{ background: state === 'active' ? '#818cf8' : 'rgba(255,255,255,0.2)' }} />
                }
              </div>
              <span className="text-[9px] whitespace-nowrap"
                style={{ color: state === 'done' ? '#6ee7b7' : state === 'active' ? '#a5b4fc' : 'rgba(255,255,255,0.2)' }}>
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="flex-1 h-px mx-1 mb-4" style={{ minWidth:12,
                background: state === 'done' ? '#10b981' : 'rgba(255,255,255,0.08)' }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ─── Detail Row ─────────────────────────────────────────────────────────── */
function DetailRow({ icon: Icon, label, value, link }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b" style={{ borderColor:'rgba(255,255,255,0.05)' }}>
      <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
        style={{ background:'rgba(99,102,241,0.1)' }}>
        <Icon className="w-3.5 h-3.5 text-indigo-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] text-white/30 uppercase tracking-wider mb-0.5">{label}</p>
        {link
          ? <a href={value} target="_blank" rel="noreferrer"
              className="text-sm text-indigo-400 hover:text-indigo-300 flex items-center gap-1 break-all">
              {value}<ExternalLink className="w-3 h-3 shrink-0" />
            </a>
          : <p className="text-sm text-white/75 whitespace-pre-line break-words">{value}</p>
        }
      </div>
    </div>
  );
}

/* ─── Submission Modal ───────────────────────────────────────────────────── */
function SubmissionModal({ item, onClose }) {
  const { application: app, job, interview } = item;
  const trackUrl = app.access_token ? `/track-application/${app.access_token}` : null;

  // close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  // prevent body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background:'rgba(0,0,0,0.75)', backdropFilter:'blur(6px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="relative w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl overflow-hidden"
        style={{ background:'#0f1022', border:'1px solid rgba(99,102,241,0.3)', boxShadow:'0 25px 60px rgba(0,0,0,0.6)' }}
      >
        {/* Modal header */}
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b shrink-0"
          style={{ borderColor:'rgba(255,255,255,0.07)' }}>
          <div>
            <h2 className="font-bold text-white text-lg leading-tight">{job.title}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              {job.company_name && (
                <span className="flex items-center gap-1 text-xs text-indigo-300 font-medium">
                  <Building2 className="w-3 h-3" />{job.company_name}
                </span>
              )}
              {job.location && (
                <span className="flex items-center gap-1 text-xs text-white/40">
                  <MapPin className="w-3 h-3" />{job.location}
                </span>
              )}
              <StatusPill s={app.status} />
            </div>
          </div>
          <button onClick={onClose}
            className="p-2 rounded-xl text-white/40 hover:text-white hover:bg-white/8 transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-5">

          {/* Interview section */}
          {interview && (
            <div className="rounded-xl p-4" style={{ background:'rgba(99,102,241,0.07)', border:'1px solid rgba(99,102,241,0.2)' }}>
              <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-3">Interview Details</p>
              <div className="grid grid-cols-2 gap-4">
                {interview.interview_type && (
                  <div>
                    <p className="text-[10px] text-white/30 mb-0.5">Type</p>
                    <p className="text-sm text-white/80 font-medium">{interview.interview_type}</p>
                  </div>
                )}
                {interview.scheduled_datetime && (
                  <div>
                    <p className="text-[10px] text-white/30 mb-0.5">Scheduled</p>
                    <p className="text-sm text-white/80 font-medium">{fmtFull(interview.scheduled_datetime)}</p>
                  </div>
                )}
                <div>
                  <p className="text-[10px] text-white/30 mb-0.5">Status</p>
                  <InterviewPill status={interview.status} />
                </div>
              </div>
              {/* Interview actions inside modal */}
              <div className="mt-3 flex gap-2">
                {interview.status === 'PENDING' && interview.confirmation_token && (
                  <a href={`${BACKEND_BASE}/recruitment/interview/select/${interview.confirmation_token}/`}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white transition-opacity hover:opacity-90"
                    style={{ background:'linear-gradient(135deg,#10b981,#059669)' }}>
                    <Calendar className="w-3.5 h-3.5" />Select Slot
                  </a>
                )}
                {interview.status === 'SCHEDULED' && interview.meeting_link && (
                  <a href={interview.meeting_link} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white transition-opacity hover:opacity-90"
                    style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
                    <Video className="w-3.5 h-3.5" />Join Meeting<ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Submitted data */}
          <div>
            <p className="text-[10px] font-bold text-white/25 uppercase tracking-widest mb-3 flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />Information You Submitted
            </p>
            <DetailRow icon={User}          label="Full Name"        value={`${app.first_name} ${app.last_name}`} />
            <DetailRow icon={Mail}          label="Email"            value={app.email} />
            <DetailRow icon={Phone}         label="Phone"            value={app.phone} />
            <DetailRow icon={MapPin}        label="Current Location" value={app.current_location} />
            <DetailRow icon={GraduationCap} label="Education"        value={app.education} />
            <DetailRow icon={Building2}     label="Previous Company" value={app.previous_company} />
            <DetailRow icon={DollarSign}    label="Previous Salary"  value={app.previous_salary} />
            <DetailRow icon={DollarSign}    label="Expected Salary"  value={app.salary_expectation} />
            <DetailRow icon={Linkedin}      label="LinkedIn"         value={app.linkedin_url}  link />
            <DetailRow icon={Github}        label="GitHub"           value={app.github_url}    link />
            <DetailRow icon={Link2}         label="Other Links"      value={app.other_links} />
            <DetailRow icon={FileText}      label="CV File"          value={app.cv_file_name} />
          </div>

          {app.cover_letter && (
            <div className="rounded-xl p-4" style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.07)' }}>
              <p className="text-[10px] font-bold text-white/30 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5" />Cover Letter
              </p>
              <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line">{app.cover_letter}</p>
            </div>
          )}

          {/* Applied date */}
          <p className="text-xs text-white/25 text-right">Applied on {fmt(app.applied_at)}</p>
        </div>

        {/* Modal footer */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-t shrink-0"
          style={{ borderColor:'rgba(255,255,255,0.07)', background:'rgba(255,255,255,0.02)' }}>
          {trackUrl
            ? <Link to={trackUrl} onClick={onClose}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-colors"
                style={{ background:'rgba(99,102,241,0.12)', color:'#818cf8', border:'1px solid rgba(99,102,241,0.25)' }}>
                <ChevronRight className="w-3.5 h-3.5" />Track This Application
              </Link>
            : <span />
          }
          <button onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold text-white/50 hover:text-white/80 transition-colors"
            style={{ background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.1)' }}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Application Card ───────────────────────────────────────────────────── */
function AppCard({ item, idx, onViewDetails }) {
  const { application: app, job, interview } = item;
  const trackUrl = app.access_token ? `/track-application/${app.access_token}` : null;
  const sc = STATUS[app.status] || STATUS.pending;

  return (
    <div className="rounded-2xl overflow-hidden transition-all duration-200"
      style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.07)' }}>

      {/* ── Card top strip by status ── */}
      <div className="h-1" style={{ background: `linear-gradient(90deg,${sc.dot},transparent)` }} />

      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl shrink-0 flex items-center justify-center font-bold text-sm"
              style={{ background:'rgba(99,102,241,0.15)', color:'#818cf8', border:'1px solid rgba(99,102,241,0.2)' }}>
              #{idx + 1}
            </div>
            <div className="min-w-0">
              <h3 className="font-bold text-white text-base leading-tight">{job.title}</h3>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {job.company_name && (
                  <span className="flex items-center gap-1 text-xs text-indigo-300 font-medium">
                    <Building2 className="w-3 h-3" />{job.company_name}
                  </span>
                )}
                {job.location && (
                  <span className="flex items-center gap-1 text-xs text-white/40">
                    <MapPin className="w-3 h-3" />{job.location}
                  </span>
                )}
                {job.type && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                    style={{ background:'rgba(255,255,255,0.06)', color:'rgba(255,255,255,0.5)' }}>
                    {job.type}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="shrink-0">
            <StatusPill s={app.status} />
          </div>
        </div>

        {/* Meta info */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-4">
          <span className="flex items-center gap-1 text-xs text-white/40">
            <Calendar className="w-3 h-3" />Applied {fmt(app.applied_at)}
          </span>
          {interview && <InterviewPill status={interview.status} />}
        </div>

        {/* Mini timeline */}
        <div className="mb-4 px-1">
          <MiniTimeline appStatus={app.status} interview={interview} />
        </div>

        {/* Interview quick actions */}
        {interview?.status === 'PENDING' && interview.confirmation_token && (
          <a href={`${BACKEND_BASE}/recruitment/interview/select/${interview.confirmation_token}/`}
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold text-white mb-3 transition-opacity hover:opacity-90"
            style={{ background:'linear-gradient(135deg,#10b981,#059669)' }}>
            <Calendar className="w-3.5 h-3.5" />Select Your Interview Slot
          </a>
        )}
        {interview?.status === 'SCHEDULED' && interview.meeting_link && (
          <a href={interview.meeting_link} target="_blank" rel="noreferrer"
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-bold text-white mb-3 transition-opacity hover:opacity-90"
            style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
            <Video className="w-3.5 h-3.5" />Join Interview Meeting
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
        {interview?.scheduled_datetime && interview.status === 'SCHEDULED' && (
          <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-xl text-xs text-emerald-300 font-medium"
            style={{ background:'rgba(16,185,129,0.08)', border:'1px solid rgba(16,185,129,0.2)' }}>
            <Calendar className="w-3.5 h-3.5" />Interview: {fmtFull(interview.scheduled_datetime)}
          </div>
        )}

        {/* Buttons */}
        <div className="flex items-center gap-2">
          <button onClick={onViewDetails}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold transition-colors"
            style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.1)', color:'rgba(255,255,255,0.5)' }}>
            <FileText className="w-3.5 h-3.5" />View My Submission
          </button>
          {trackUrl && (
            <Link to={trackUrl}
              className="flex items-center gap-1 py-2 px-4 rounded-xl text-xs font-semibold transition-colors"
              style={{ background:'rgba(99,102,241,0.12)', color:'#818cf8', border:'1px solid rgba(99,102,241,0.25)' }}>
              Track<ChevronRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Stats bar ──────────────────────────────────────────────────────────── */
function StatsBar({ apps }) {
  const total       = apps.length;
  const pending     = apps.filter(a => a.application.status === 'pending').length;
  const shortlisted = apps.filter(a => a.application.status === 'shortlisted').length;
  const interviews  = apps.filter(a => !!a.interview).length;
  const rejected    = apps.filter(a => a.application.status === 'rejected').length;

  const stats = [
    { label:'Total',      val:total,       color:'#818cf8', bg:'rgba(99,102,241,0.12)'  },
    { label:'Reviewing',  val:pending,     color:'#60a5fa', bg:'rgba(59,130,246,0.12)'  },
    { label:'Shortlisted',val:shortlisted, color:'#34d399', bg:'rgba(16,185,129,0.12)'  },
    { label:'Interviews', val:interviews,  color:'#a78bfa', bg:'rgba(167,139,250,0.12)' },
    { label:'Rejected',   val:rejected,    color:'#f87171', bg:'rgba(239,68,68,0.12)'   },
  ];

  return (
    <div className="grid grid-cols-5 gap-4">
      {stats.map(s => (
        <div key={s.label} className="rounded-xl p-3 text-center"
          style={{ background:s.bg, border:`1px solid ${s.color}33` }}>
          <div className="text-2xl font-bold" style={{ color:s.color }}>{s.val}</div>
          <div className="text-[10px] mt-0.5" style={{ color:`${s.color}99` }}>{s.label}</div>
        </div>
      ))}
    </div>
  );
}

/* ─── Filter tabs ────────────────────────────────────────────────────────── */
const TABS = [
  { key:'all',         label:'All'          },
  { key:'pending',     label:'Under Review' },
  { key:'shortlisted', label:'Shortlisted'  },
  { key:'interview',   label:'Interview'    },
  { key:'rejected',    label:'Not Selected' },
];

/* ═══════════════════════════════════════════════════════════════════════════
   EMAIL ENTRY PAGE
═══════════════════════════════════════════════════════════════════════════ */
function EmailEntryPage() {
  const [email,   setEmail]   = useState('');
  const [loading, setLoading] = useState(false);
  const [sent,    setSent]    = useState(false);
  const [error,   setError]   = useState('');
  const inputRef = useRef(null);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 300); }, []);

  const submit = async (e) => {
    e.preventDefault();
    const val = email.trim();
    if (!val) { setError('Please enter your email address.'); return; }
    if (!/^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(val)) {
      setError('Please enter a valid email address (e.g. name@example.com)');
      return;
    }
    setError(''); setLoading(true);
    try {
      const res  = await fetch(`${API_BASE}/public/candidate/request-access/`, {
        method:'POST', headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ email: val.toLowerCase() }),
      });
      const data = await res.json();
      if (data.status === 'success') setSent(true);
      else setError(data.message || 'Something went wrong. Please try again.');
    } catch { setError('Network error. Please check your connection.'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background:'#080b1a' }}>

      {/* Background glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-20%] left-[10%] w-[500px] h-[500px] rounded-full opacity-20"
          style={{ background:'radial-gradient(circle,#6366f1,transparent 70%)', filter:'blur(60px)' }} />
        <div className="absolute bottom-[-10%] right-[5%] w-[400px] h-[400px] rounded-full opacity-15"
          style={{ background:'radial-gradient(circle,#4f46e5,transparent 70%)', filter:'blur(80px)' }} />
        <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] rounded-full opacity-10"
          style={{ background:'radial-gradient(circle,#818cf8,transparent 70%)', filter:'blur(60px)' }} />
      </div>

      {/* Header */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-5 border-b" style={{ borderColor:'rgba(255,255,255,0.06)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
            <LayoutGrid className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white text-sm">Candidate Portal</span>
        </div>
        <Link to="/careers" className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />Back to Jobs
        </Link>
      </nav>

      {/* Main */}
      <div className="relative z-10 flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">

          {sent ? (
            /* ── Sent state ── */
            <div className="text-center space-y-6">
              <div className="relative inline-flex">
                <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto"
                  style={{ background:'rgba(16,185,129,0.15)', border:'1px solid rgba(16,185,129,0.3)' }}>
                  <CheckCircle2 className="w-10 h-10 text-emerald-400" />
                </div>
                <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
                  <span className="text-[10px] text-white font-bold">✓</span>
                </div>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white mb-2">Check Your Inbox</h1>
                <p className="text-white/50 text-sm leading-relaxed">
                  We sent a secure access link to<br />
                  <span className="text-indigo-300 font-semibold text-base">{email}</span>
                </p>
              </div>
              <div className="rounded-2xl p-5 text-left space-y-3"
                style={{ background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.08)' }}>
                {[
                  ['📬','Check your email for a message from us'],
                  ['🔗','Click the "View My Applications" link'],
                  ['📋','Your full application history will open'],
                  ['⏰','Link is valid for 24 hours'],
                ].map(([icon, text]) => (
                  <div key={text} className="flex items-center gap-3 text-sm text-white/50">
                    <span className="text-base">{icon}</span>{text}
                  </div>
                ))}
              </div>
              <button onClick={() => { setSent(false); setEmail(''); }}
                className="text-sm text-white/30 hover:text-white/60 transition-colors">
                Try a different email →
              </button>
            </div>

          ) : (
            /* ── Email form ── */
            <div className="space-y-8">
              {/* Heading */}
              <div className="text-center space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-2"
                  style={{ background:'rgba(99,102,241,0.15)', color:'#a5b4fc', border:'1px solid rgba(99,102,241,0.25)' }}>
                  <Shield className="w-3 h-3" />Secure Access — No Password Needed
                </div>
                <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight">
                  View Your<br />
                  <span style={{ background:'linear-gradient(135deg,#818cf8,#6366f1)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
                    Applications
                  </span>
                </h1>
                <p className="text-white/50 text-base leading-relaxed">
                  Enter your email to receive a magic link.<br />Click it to see all your job applications instantly.
                </p>
              </div>

              {/* Card */}
              <div className="rounded-2xl p-7 space-y-5"
                style={{ background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.09)', backdropFilter:'blur(12px)' }}>
                <form onSubmit={submit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">
                      Your Email Address
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
                      <input
                        ref={inputRef}
                        type="email"
                        value={email}
                        onChange={e => { setEmail(e.target.value); setError(''); }}
                        placeholder="you@example.com"
                        className="w-full pl-10 pr-4 py-3.5 rounded-xl text-sm text-white placeholder-white/25 outline-none transition-all"
                        style={{
                          background:'rgba(255,255,255,0.06)',
                          border: error ? '1px solid rgba(239,68,68,0.6)' : '1px solid rgba(255,255,255,0.1)',
                        }}
                        onFocus={e => { if (!error) e.target.style.borderColor = 'rgba(99,102,241,0.7)'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
                        onBlur={e => { if (!error) e.target.style.borderColor = 'rgba(255,255,255,0.1)'; e.target.style.boxShadow = 'none'; }}
                      />
                    </div>
                    {error && (
                      <p className="text-xs text-red-400 mt-2 flex items-center gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />{error}
                      </p>
                    )}
                  </div>

                  <button type="submit" disabled={loading}
                    className="w-full py-3.5 rounded-xl text-sm font-bold text-white flex items-center justify-center gap-2 transition-all hover:opacity-90 disabled:opacity-50"
                    style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)', boxShadow:'0 4px 20px rgba(99,102,241,0.35)' }}>
                    {loading
                      ? <><Loader2 className="w-4 h-4 animate-spin" />Sending secure link…</>
                      : <><Send className="w-4 h-4" />Send My Access Link</>
                    }
                  </button>
                </form>

                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px" style={{ background:'rgba(255,255,255,0.07)' }} />
                  <span className="text-xs text-white/20">or</span>
                  <div className="flex-1 h-px" style={{ background:'rgba(255,255,255,0.07)' }} />
                </div>

                <p className="text-center text-xs text-white/30 leading-relaxed">
                  Already have a tracking link from your confirmation email?<br />
                  <span className="text-white/50">Click it directly to view that application.</span>
                </p>
              </div>

              {/* Trust badges */}
              <div className="flex items-center justify-center gap-6 flex-wrap">
                {[
                  [Shield,    'Secure & Private'],
                  [Clock,     '24-hr Link Validity'],
                  [Sparkles,  'No Password Required'],
                ].map(([Icon, text]) => (
                  <div key={text} className="flex items-center gap-1.5 text-xs text-white/25">
                    <Icon className="w-3 h-3" />{text}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   PORTAL DASHBOARD
═══════════════════════════════════════════════════════════════════════════ */
function PortalDashboard({ token }) {
  const [loading,    setLoading]    = useState(true);
  const [data,       setData]       = useState(null);
  const [error,      setError]      = useState(null);
  const [refreshing,   setRefreshing]   = useState(false);
  const [activeTab,    setActiveTab]    = useState('all');
  const [modalItem,    setModalItem]    = useState(null);

  const load = async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    try {
      const res  = await fetch(`${API_BASE}/public/candidate/portal/${token}/`, { cache:'no-store' });
      const json = await res.json();
      if (json.status === 'success') setData(json);
      else setError(json.message || 'Unable to load your applications.');
    } catch { setError('Network error. Please check your connection.'); }
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { load(); }, [token]);

  /* ── Loading ── */
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background:'#080b1a' }}>
      <div className="text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center"
          style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
          <Loader2 className="w-7 h-7 text-white animate-spin" />
        </div>
        <p className="text-white/40 text-sm">Loading your portal…</p>
      </div>
    </div>
  );

  /* ── Error ── */
  if (error) return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background:'#080b1a' }}>
      <div className="max-w-md w-full text-center space-y-5">
        <div className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
          style={{ background:'rgba(239,68,68,0.1)', border:'1px solid rgba(239,68,68,0.2)' }}>
          <AlertCircle className="w-8 h-8 text-red-400" />
        </div>
        <h2 className="text-xl font-bold text-white">Link Expired</h2>
        <p className="text-white/50 text-sm leading-relaxed">{error}</p>
        <Link to="/candidate-portal"
          className="inline-flex items-center gap-2 text-sm font-semibold px-5 py-2.5 rounded-xl transition-opacity hover:opacity-90 text-white"
          style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
          <ArrowLeft className="w-4 h-4" />Request New Access Link
        </Link>
      </div>
    </div>
  );

  const { email, data: apps, total } = data;
  const firstName = apps[0]?.application?.first_name || '';

  /* ── Tab filtering ── */
  const filtered = apps.filter(item => {
    if (activeTab === 'all')         return true;
    if (activeTab === 'interview')   return !!item.interview;
    return item.application.status === activeTab;
  });

  const tabCount = (key) => {
    if (key === 'all')       return apps.length;
    if (key === 'interview') return apps.filter(a => !!a.interview).length;
    return apps.filter(a => a.application.status === key).length;
  };

  return (
    <div className="min-h-screen" style={{ background:'#080b1a' }}>

      {/* Background glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[400px] opacity-10"
          style={{ background:'radial-gradient(ellipse,#6366f1,transparent 70%)', filter:'blur(80px)' }} />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] opacity-8"
          style={{ background:'radial-gradient(ellipse,#4f46e5,transparent 70%)', filter:'blur(80px)' }} />
      </div>

      {/* ── Nav ── */}
      <nav className="relative z-20 sticky top-0 flex items-center justify-between px-5 py-4 border-b"
        style={{ background:'rgba(8,11,26,0.85)', borderColor:'rgba(255,255,255,0.07)', backdropFilter:'blur(16px)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background:'linear-gradient(135deg,#6366f1,#4f46e5)' }}>
            <LayoutGrid className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white text-sm hidden sm:block">Candidate Portal</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 text-xs text-white/40 px-3 py-1.5 rounded-full"
            style={{ background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.08)' }}>
            <Mail className="w-3.5 h-3.5" />{email}
          </div>
          <button onClick={() => load(true)} disabled={refreshing}
            className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <Link to="/candidate-portal"
            className="p-2 rounded-lg text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors" title="Sign out">
            <X className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      <div className="relative z-10 w-full px-6 py-8 space-y-6">

        {/* ── Hero greeting ── */}
        <div className="rounded-2xl p-6 relative overflow-hidden"
          style={{ background:'linear-gradient(135deg,rgba(99,102,241,0.15),rgba(79,70,229,0.08))', border:'1px solid rgba(99,102,241,0.2)' }}>
          <div className="absolute top-0 right-0 w-32 h-32 opacity-10 pointer-events-none"
            style={{ background:'radial-gradient(circle,#818cf8,transparent)', filter:'blur(20px)' }} />
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <h1 className="text-2xl font-bold text-white">
                {firstName ? `Hi, ${firstName}! 👋` : 'My Applications'}
              </h1>
              <p className="text-white/40 text-sm mt-0.5 flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5" />{email}
              </p>
            </div>
            <div className="text-right shrink-0">
              <div className="text-3xl font-bold text-indigo-400">{total}</div>
              <div className="text-xs text-white/30">{total === 1 ? 'Application' : 'Applications'}</div>
            </div>
          </div>
          <StatsBar apps={apps} />
        </div>

        {/* ── Filter tabs ── */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {TABS.map(tab => {
            const count   = tabCount(tab.key);
            const isActive = activeTab === tab.key;
            return (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all"
                style={{
                  background: isActive ? 'rgba(99,102,241,0.2)'  : 'rgba(255,255,255,0.04)',
                  border:     isActive ? '1px solid rgba(99,102,241,0.4)' : '1px solid rgba(255,255,255,0.08)',
                  color:      isActive ? '#a5b4fc' : 'rgba(255,255,255,0.35)',
                }}>
                {tab.label}
                {count > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold"
                    style={{ background: isActive ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.08)', color: isActive ? '#c7d2fe' : 'rgba(255,255,255,0.3)' }}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Application cards ── */}
        {filtered.length === 0 ? (
          <div className="text-center py-16 rounded-2xl"
            style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.06)' }}>
            <Briefcase className="w-10 h-10 text-white/15 mx-auto mb-3" />
            <p className="text-white/30 text-sm">No applications in this category.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((item, i) => (
              <AppCard key={item.application.id} item={item} idx={i} onViewDetails={() => setModalItem(item)} />
            ))}
          </div>
        )}

        {/* ── Footer ── */}
        <div className="text-center pt-4 pb-8 space-y-2">
          <p className="text-xs text-white/20">
            Showing applications for <span className="text-white/40">{email}</span>
          </p>
          <Link to="/careers" className="text-xs text-indigo-400/60 hover:text-indigo-400 transition-colors">
            ← Browse more jobs
          </Link>
        </div>

      </div>

      {/* ── Submission modal ── */}
      {modalItem && <SubmissionModal item={modalItem} onClose={() => setModalItem(null)} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   PAGE SHELL
═══════════════════════════════════════════════════════════════════════════ */
export default function CandidatePortalPage() {
  const { token } = useParams();
  return token ? <PortalDashboard token={token} /> : <EmailEntryPage />;
}
