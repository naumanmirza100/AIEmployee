import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Loader2, CheckCircle2, Clock, Briefcase, Mail, Calendar,
  Video, AlertCircle, ChevronRight, ExternalLink, MapPin,
  User, RefreshCw, LayoutGrid,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/* ─── tiny helpers ─────────────────────────────────────────────────────── */
const fmt = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
const fmtFull = (iso) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null;

const STATUS_CONFIG = {
  pending:     { label: 'Under Review',  color: 'blue',   bg: 'rgba(59,130,246,0.12)',  border: 'rgba(59,130,246,0.3)',  text: '#60a5fa' },
  reviewed:    { label: 'Reviewed',      color: 'yellow', bg: 'rgba(234,179,8,0.12)',   border: 'rgba(234,179,8,0.3)',   text: '#fbbf24' },
  shortlisted: { label: 'Shortlisted',   color: 'green',  bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)', text: '#34d399' },
  rejected:    { label: 'Not Selected',  color: 'red',    bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.3)',   text: '#f87171' },
};

const INTERVIEW_STATUS = {
  PENDING:     { label: 'Awaiting Your Slot Selection', color: '#f59e0b' },
  SCHEDULED:   { label: 'Interview Scheduled',          color: '#34d399' },
  COMPLETED:   { label: 'Interview Completed',          color: '#818cf8' },
  CANCELLED:   { label: 'Interview Cancelled',          color: '#f87171' },
  RESCHEDULED: { label: 'Interview Rescheduled',        color: '#f59e0b' },
};

/* ─── timeline steps ───────────────────────────────────────────────────── */
function buildSteps(appStatus, interview) {
  const decided = appStatus !== 'pending';
  const shortlisted = appStatus === 'shortlisted' || !!interview;
  const hasInterview = !!interview;
  const interviewDone = interview?.status === 'COMPLETED';

  return [
    {
      id: 'submitted',
      label: 'Application Submitted',
      sub: 'Your application was received',
      done: true,
      active: false,
    },
    {
      id: 'review',
      label: 'Under Review',
      sub: 'Recruiter reviewing your CV',
      done: decided,
      active: !decided,
    },
    {
      id: 'shortlisted',
      label: 'Shortlisted',
      sub: 'Selected for further evaluation',
      done: shortlisted,
      active: decided && !shortlisted,
    },
    {
      id: 'interview',
      label: 'Interview',
      sub: hasInterview
        ? INTERVIEW_STATUS[interview.status]?.label || interview.status
        : 'Pending shortlisting',
      done: interviewDone,
      active: hasInterview && !interviewDone,
    },
    {
      id: 'decision',
      label: 'Final Decision',
      sub: 'Offer or outcome communicated',
      done: false,
      active: interviewDone,
    },
  ];
}

/* ─── sub-components ───────────────────────────────────────────────────── */
function StatusBadge({ appStatus }) {
  const cfg = STATUS_CONFIG[appStatus] || STATUS_CONFIG.pending;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.text }}
    >
      <span
        className="w-2 h-2 rounded-full"
        style={{ background: cfg.text }}
      />
      {cfg.label}
    </span>
  );
}

function InfoRow({ label, value, children }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-white/[0.06] last:border-0">
      <span className="text-xs text-white/40 uppercase tracking-wider">{label}</span>
      <span className="text-sm text-white/80 font-medium text-right">{children || value}</span>
    </div>
  );
}

function StepIcon({ done, active }) {
  if (done)
    return (
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
        style={{ background: 'rgba(16,185,129,0.2)', border: '2px solid #10b981' }}>
        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
      </div>
    );
  if (active)
    return (
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
        style={{ background: 'rgba(99,102,241,0.2)', border: '2px solid #6366f1' }}>
        <Clock className="w-4 h-4 text-indigo-400 animate-pulse" />
      </div>
    );
  return (
    <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
      style={{ background: 'rgba(255,255,255,0.04)', border: '2px solid rgba(255,255,255,0.1)' }}>
      <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
    </div>
  );
}

function Timeline({ steps }) {
  return (
    <div className="space-y-0">
      {steps.map((step, i) => (
        <div key={step.id} className="flex gap-4">
          {/* Left column: icon + connector */}
          <div className="flex flex-col items-center">
            <StepIcon done={step.done} active={step.active} />
            {i < steps.length - 1 && (
              <div
                className="w-0.5 flex-1 min-h-[24px] mt-1"
                style={{
                  background: step.done
                    ? 'linear-gradient(to bottom, #10b981, rgba(16,185,129,0.3))'
                    : 'rgba(255,255,255,0.08)',
                }}
              />
            )}
          </div>
          {/* Right column: text */}
          <div className={`pb-6 ${i === steps.length - 1 ? 'pb-0' : ''}`}>
            <p className={`text-sm font-semibold leading-tight ${step.done || step.active ? 'text-white' : 'text-white/30'}`}>
              {step.label}
            </p>
            <p className={`text-xs mt-0.5 ${step.done || step.active ? 'text-white/50' : 'text-white/20'}`}>
              {step.sub}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function InterviewCard({ interview, backendBase }) {
  const cfg = INTERVIEW_STATUS[interview.status] || {};
  const slot = fmtFull(interview.scheduled_datetime);
  const slotUrl = interview.confirmation_token
    ? `${backendBase}/recruitment/interview/select/${interview.confirmation_token}/`
    : null;

  return (
    <div
      className="rounded-xl p-5 space-y-4"
      style={{ background: 'rgba(99,102,241,0.07)', border: '1px solid rgba(99,102,241,0.25)' }}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Interview Details</p>
        <span
          className="text-xs px-2.5 py-1 rounded-full font-semibold"
          style={{ background: 'rgba(99,102,241,0.15)', color: cfg.color || '#818cf8', border: `1px solid ${cfg.color || '#818cf8'}33` }}
        >
          {cfg.label || interview.status}
        </span>
      </div>

      {interview.interview_type && (
        <div className="flex items-center gap-2 text-sm text-white/70">
          <Video className="w-4 h-4 text-indigo-400 shrink-0" />
          {interview.interview_type}
        </div>
      )}

      {slot && (
        <div className="flex items-center gap-2 text-sm text-white/70">
          <Calendar className="w-4 h-4 text-indigo-400 shrink-0" />
          {slot}
        </div>
      )}

      {interview.meeting_link && interview.status === 'SCHEDULED' && (
        <a
          href={interview.meeting_link}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 text-sm font-semibold text-white w-full justify-center py-2.5 rounded-lg transition-opacity hover:opacity-90"
          style={{ background: 'linear-gradient(135deg,#6366f1,#4f46e5)' }}
        >
          <Video className="w-4 h-4" />
          Join Meeting
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      )}

      {interview.status === 'PENDING' && slotUrl && (
        <a
          href={slotUrl}
          className="flex items-center gap-2 text-sm font-semibold text-white w-full justify-center py-2.5 rounded-lg transition-opacity hover:opacity-90"
          style={{ background: 'linear-gradient(135deg,#10b981,#059669)' }}
        >
          <Calendar className="w-4 h-4" />
          Select Interview Slot
          <ChevronRight className="w-4 h-4" />
        </a>
      )}
    </div>
  );
}

/* ─── main page ─────────────────────────────────────────────────────────── */
export default function ApplicationTrackerPage() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const backendBase = (import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/public/applications/track/${token}/`, { cache: 'no-store' });
      const json = await res.json();
      if (json.status === 'success') setData(json.data);
      else setError(json.message || 'Unable to load application status.');
    } catch {
      setError('Network error — please check your connection and try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, [token]);

  /* ── loading ── */
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0f0f23' }}>
        <div className="text-center space-y-4">
          <Loader2 className="w-10 h-10 animate-spin text-indigo-400 mx-auto" />
          <p className="text-white/50 text-sm">Loading your application…</p>
        </div>
      </div>
    );
  }

  /* ── error ── */
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#0f0f23' }}>
        <div
          className="max-w-md w-full rounded-2xl p-8 text-center space-y-4"
          style={{ background: '#1a1a2e', border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <div
            className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
            style={{ background: 'rgba(239,68,68,0.12)' }}
          >
            <AlertCircle className="w-8 h-8 text-red-400" />
          </div>
          <h2 className="text-xl font-bold text-white">Link Not Found</h2>
          <p className="text-white/50 text-sm leading-relaxed">{error}</p>
          <p className="text-white/30 text-xs">
            If you believe this is a mistake, please contact the recruiter directly.
          </p>
        </div>
      </div>
    );
  }

  const { application, job, cv_record, interview } = data;
  const steps = buildSteps(application.status, interview);
  const appDate = fmt(application.applied_at);

  return (
    <div className="min-h-screen px-4 py-10 pb-20" style={{ background: '#0f0f23' }}>
      <div className="max-w-lg mx-auto space-y-4">

        {/* ── Page header ── */}
        <div className="text-center mb-8">
          <div
            className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center text-2xl"
            style={{ background: 'linear-gradient(135deg,#6366f1,#4f46e5)' }}
          >
            📋
          </div>
          <h1 className="text-2xl font-bold text-white">Application Tracker</h1>
          <p className="text-white/40 text-sm mt-1">Track your application status in real time</p>
        </div>

        {/* ── Candidate + Job card ── */}
        <div
          className="rounded-2xl p-5"
          style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          {/* Job header */}
          <div className="flex items-start gap-3 pb-4 border-b border-white/[0.06] mb-4">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: 'rgba(99,102,241,0.15)' }}
            >
              <Briefcase className="w-5 h-5 text-indigo-400" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-bold text-white leading-tight">{job.title}</h2>
              {job.company_name && (
                <p className="text-xs text-indigo-300 mt-0.5">{job.company_name}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-1.5">
                {job.location && (
                  <span className="flex items-center gap-1 text-xs text-white/40">
                    <MapPin className="w-3 h-3" />{job.location}
                  </span>
                )}
                {job.department && (
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}
                  >
                    {job.department}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Candidate info */}
          <InfoRow label="Applicant">
            <span className="flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-white/30" />
              {application.first_name} {application.last_name}
            </span>
          </InfoRow>
          <InfoRow label="Email">
            <span className="flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5 text-white/30" />
              {application.email}
            </span>
          </InfoRow>
          <InfoRow label="Applied On">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-white/30" />
              {appDate}
            </span>
          </InfoRow>
          <InfoRow label="Status">
            <StatusBadge appStatus={application.status} />
          </InfoRow>
        </div>

        {/* ── Timeline card ── */}
        <div
          className="rounded-2xl p-5"
          style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.07)' }}
        >
          <p className="text-xs font-bold text-white/30 uppercase tracking-wider mb-5">Application Journey</p>
          <Timeline steps={steps} />
        </div>

        {/* ── Interview card (if exists) ── */}
        {interview && (
          <div
            className="rounded-2xl p-5"
            style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.07)' }}
          >
            <InterviewCard interview={interview} backendBase={backendBase} />
          </div>
        )}

        {/* ── What's next info box ── */}
        {application.status === 'pending' && !interview && (
          <div
            className="rounded-2xl p-5 space-y-2"
            style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}
          >
            <p className="text-xs font-bold text-emerald-400 uppercase tracking-wider">What happens next?</p>
            <ul className="space-y-1.5 text-sm text-white/60">
              <li className="flex items-start gap-2"><ChevronRight className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />Our team is reviewing your application</li>
              <li className="flex items-start gap-2"><ChevronRight className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />If shortlisted, you will receive an interview invitation by email</li>
              <li className="flex items-start gap-2"><ChevronRight className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />Refresh this page anytime to check your latest status</li>
            </ul>
          </div>
        )}

        {/* ── Bottom links ── */}
        <div className="flex items-center justify-center gap-4 pt-2">
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition-colors px-3 py-2 rounded-lg hover:bg-white/5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          <span className="text-white/10 select-none">|</span>
          <Link to="/candidate-portal"
            className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors px-3 py-2 rounded-lg hover:bg-white/5"
          >
            <LayoutGrid className="w-3.5 h-3.5" />View all my applications
          </Link>
        </div>

      </div>
    </div>
  );
}
