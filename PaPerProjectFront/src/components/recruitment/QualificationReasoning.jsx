import React, { useState } from 'react';
import {
  CheckCircle, Clock, XCircle, TrendingUp, Zap,
  Link, AlertTriangle, ChevronDown, ChevronUp, Award,
} from 'lucide-react';

/* ── small helpers ── */
const extract = (lines, ...keys) => {
  for (const line of lines) {
    for (const key of keys) {
      const re = new RegExp(`${key}[:\\s]+(.+)`, 'i');
      const m = line.replace(/\*\*/g, '').match(re);
      if (m) return m[1].trim();
    }
  }
  return null;
};

const extractPercent = (lines) => {
  for (const line of lines) {
    const m = line.match(/(\d+)%/);
    if (m && /match|requirement/i.test(line)) return parseInt(m[1]);
  }
  return null;
};

const extractBullets = (lines, heading) => {
  const results = [];
  let capturing = false;
  for (const line of lines) {
    const clean = line.replace(/\*\*/g, '').trim();
    if (new RegExp(heading, 'i').test(clean)) { capturing = true; continue; }
    if (capturing) {
      if (/^(Weakness|Concern|Risk|Recommendation|Decision|Confidence|Primary|Seniority|Job Req|Missing|Exact|Related|Professional|Role Fit)/i.test(clean) && !clean.startsWith('•') && !clean.startsWith('-')) break;
      if (clean.startsWith('•') || clean.startsWith('-')) results.push(clean.replace(/^[•\-]\s*/, ''));
    }
  }
  return results;
};

const Chip = ({ label, variant = 'default' }) => {
  const s = {
    matched: { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)', color: '#34d399' },
    related: { bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)',  color: '#60a5fa' },
    missing: { bg: 'rgba(248,113,113,0.10)', border: 'rgba(248,113,113,0.25)', color: '#f87171' },
    default: { bg: 'rgba(167,139,250,0.10)', border: 'rgba(167,139,250,0.2)', color: '#a78bfa' },
  }[variant] || {};
  return (
    <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full"
      style={{ background: s.bg, border: `1px solid ${s.border}`, color: s.color }}>
      {label}
    </span>
  );
};

const SkillGroup = ({ title, skills, icon, variant, showAll = false }) => {
  const [expanded, setExpanded] = useState(showAll);
  if (!skills || skills.length === 0) return null;
  const visible = expanded ? skills : skills.slice(0, 6);
  const hidden = skills.length - 6;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: icon.props.style?.color || '#a78bfa' }}>{title}</span>
        <span className="text-xs text-white/25 ml-1">({skills.length})</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((s, i) => <Chip key={i} label={s} variant={variant} />)}
        {!expanded && hidden > 0 && (
          <button onClick={() => setExpanded(true)}
            className="inline-flex items-center text-xs px-2.5 py-1 rounded-full font-medium text-violet-300 hover:text-violet-200 transition-colors"
            style={{ background: 'rgba(167,139,250,0.10)', border: '1px solid rgba(167,139,250,0.2)' }}>
            +{hidden} more <ChevronDown className="h-3 w-3 ml-1" />
          </button>
        )}
        {expanded && hidden > 0 && (
          <button onClick={() => setExpanded(false)}
            className="inline-flex items-center text-xs px-2.5 py-1 rounded-full text-white/30 hover:text-white/50 transition-colors">
            Show less <ChevronUp className="h-3 w-3 ml-1" />
          </button>
        )}
      </div>
    </div>
  );
};

const QualificationReasoning = ({ reasoning, exactMatchedSkills = [], relatedMatchedSkills = [], missingSkills = [], inferredSkills = [] }) => {
  if (!reasoning) return null;

  const lines = Array.isArray(reasoning)
    ? reasoning
    : (typeof reasoning === 'string' ? reasoning.split('\n').filter(l => l.trim()) : []);

  if (lines.length === 0) return null;

  /* parse metadata */
  const decision    = extract(lines, 'Decision');
  const confidence  = extract(lines, 'Confidence Score', 'Confidence');
  const role        = extract(lines, 'Primary Role', 'Role');
  const seniority   = extract(lines, 'Seniority Level', 'Seniority');
  const experience  = extract(lines, 'Professional Experience', 'Experience');
  const roleFit     = extract(lines, 'Role Fit Score', 'Role Fit');
  const matchPct    = extractPercent(lines);
  const strengths   = extractBullets(lines, 'Strength');
  const weaknesses  = extractBullets(lines, 'Weakness|Concern|Risk');

  const decisionMap = {
    INTERVIEW: { color: '#34d399', bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)', icon: <CheckCircle className="h-4 w-4" /> },
    HOLD:      { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)',  icon: <Clock       className="h-4 w-4" /> },
    REJECT:    { color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)', icon: <XCircle     className="h-4 w-4" /> },
  };
  const ds = decisionMap[decision?.toUpperCase()] || decisionMap.HOLD;

  const confNum  = confidence ? parseInt(confidence) : null;
  const fitNum   = roleFit    ? parseInt(roleFit)    : null;

  const Bar = ({ value, color }) => (
    <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.07)' }}>
      <div className="h-full rounded-full transition-all duration-700"
        style={{ width: `${Math.min(value, 100)}%`, background: color }} />
    </div>
  );

  return (
    <div className="space-y-4">

      {/* ── Decision + scores banner ── */}
      <div className="rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-4"
        style={{ background: ds.bg, border: `1px solid ${ds.border}` }}>
        <div className="flex items-center gap-2 flex-1">
          <span style={{ color: ds.color }}>{ds.icon}</span>
          <span className="font-bold text-base" style={{ color: ds.color }}>
            {decision?.toUpperCase() || 'N/A'}
          </span>
        </div>
        <div className="flex flex-wrap gap-3 sm:gap-5">
          {confNum != null && (
            <div className="text-center">
              <p className="text-xs text-white/30 mb-0.5">Confidence</p>
              <p className="text-sm font-bold text-white">{confNum}<span className="text-white/30 text-xs">/100</span></p>
            </div>
          )}
          {matchPct != null && (
            <div className="text-center">
              <p className="text-xs text-white/30 mb-0.5">Job Match</p>
              <p className="text-sm font-bold text-white">{matchPct}<span className="text-white/30 text-xs">%</span></p>
            </div>
          )}
          {fitNum != null && (
            <div className="text-center">
              <p className="text-xs text-white/30 mb-0.5">Role Fit</p>
              <p className="text-sm font-bold text-white">{fitNum}<span className="text-white/30 text-xs">/100</span></p>
            </div>
          )}
        </div>
      </div>

      {/* ── Meta info chips ── */}
      {(role || seniority || experience) && (
        <div className="flex flex-wrap gap-2">
          {role && (
            <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full text-white/70"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <Award className="h-3 w-3 text-violet-400" />{role}
            </span>
          )}
          {seniority && (
            <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full text-white/70"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <TrendingUp className="h-3 w-3 text-blue-400" />{seniority}
            </span>
          )}
          {experience && (
            <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full text-white/70"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <Clock className="h-3 w-3 text-amber-400" />{experience}
            </span>
          )}
        </div>
      )}

      {/* ── Score bars ── */}
      {(confNum != null || matchPct != null) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {matchPct != null && (
            <div className="rounded-xl p-3 space-y-2"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/40">Job Requirements Match</span>
                <span className="text-xs font-bold text-white">{matchPct}%</span>
              </div>
              <Bar value={matchPct} color={matchPct >= 60 ? '#34d399' : matchPct >= 35 ? '#fbbf24' : '#f87171'} />
            </div>
          )}
          {confNum != null && (
            <div className="rounded-xl p-3 space-y-2"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/40">AI Confidence</span>
                <span className="text-xs font-bold text-white">{confNum}%</span>
              </div>
              <Bar value={confNum} color={confNum >= 60 ? '#34d399' : confNum >= 35 ? '#fbbf24' : '#f87171'} />
            </div>
          )}
        </div>
      )}

      {/* ── Strengths / Weaknesses ── */}
      {(strengths.length > 0 || weaknesses.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {strengths.length > 0 && (
            <div className="rounded-xl p-4"
              style={{ background: 'rgba(52,211,153,0.05)', border: '1px solid rgba(52,211,153,0.15)' }}>
              <div className="flex items-center gap-1.5 mb-3">
                <Zap className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Strengths</span>
              </div>
              <ul className="space-y-1.5">
                {strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-white/65">
                    <span className="mt-0.5 shrink-0 text-emerald-400">•</span>{s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {weaknesses.length > 0 && (
            <div className="rounded-xl p-4"
              style={{ background: 'rgba(248,113,113,0.05)', border: '1px solid rgba(248,113,113,0.15)' }}>
              <div className="flex items-center gap-1.5 mb-3">
                <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-red-400">Concerns</span>
              </div>
              <ul className="space-y-1.5">
                {weaknesses.map((w, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-white/65">
                    <span className="mt-0.5 shrink-0 text-red-400">•</span>{w}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

    </div>
  );
};

export default QualificationReasoning;
