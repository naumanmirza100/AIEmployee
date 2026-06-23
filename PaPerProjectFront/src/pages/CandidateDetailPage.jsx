import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Loader2, ArrowLeft, Mail, Phone, Briefcase, MapPin,
  DollarSign, Building2, Link2, ExternalLink, Star,
  CheckCircle2, Clock, Calendar, User, GraduationCap,
  TrendingUp, AlertCircle, CheckCircle, XCircle, FileText, Printer,
} from 'lucide-react';
import { getCVRecordDetail, getCVRecordDecisionHistory } from '@/services/recruitmentAgentService';
import QualificationReasoning from '@/components/recruitment/QualificationReasoning';

/* ── helpers ── */
const DecisionChip = ({ decision }) => {
  const map = {
    INTERVIEW: { bg: 'rgba(52,211,153,0.15)', border: 'rgba(52,211,153,0.35)', color: '#34d399', label: 'Interview' },
    HOLD:      { bg: 'rgba(251,191,36,0.15)',  border: 'rgba(251,191,36,0.35)',  color: '#fbbf24', label: 'Hold' },
    REJECT:    { bg: 'rgba(248,113,113,0.15)', border: 'rgba(248,113,113,0.35)', color: '#f87171', label: 'Reject' },
  };
  const s = map[decision] || { bg: 'rgba(255,255,255,0.08)', border: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.5)', label: decision || 'N/A' };
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full"
      style={{ background: s.bg, border: `1px solid ${s.border}`, color: s.color }}>
      {decision === 'INTERVIEW' && <CheckCircle className="h-3 w-3" />}
      {decision === 'HOLD'      && <Clock        className="h-3 w-3" />}
      {decision === 'REJECT'    && <XCircle      className="h-3 w-3" />}
      {s.label}
    </span>
  );
};

const ScoreRing = ({ score, label, color = '#7c3aed' }) => {
  if (score == null) return null;
  const r = 32, circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-20 h-20">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
          <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-bold text-white">{score}<span className="text-xs text-white/50">%</span></span>
        </div>
      </div>
      <span className="text-xs text-white/40">{label}</span>
    </div>
  );
};

const Block = ({ title, icon, children }) => (
  <div className="rounded-2xl p-5"
    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}>
    {title && (
      <div className="flex items-center gap-2 mb-4">
        {icon && <span className="text-violet-400">{icon}</span>}
        <h3 className="text-xs font-semibold uppercase tracking-widest text-violet-400">{title}</h3>
      </div>
    )}
    {children}
  </div>
);

const InfoPill = ({ icon, label, value }) => {
  if (!value) return null;
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
      <span className="text-white/30 shrink-0">{icon}</span>
      <div className="min-w-0">
        <p className="text-[10px] text-white/30 uppercase tracking-wider">{label}</p>
        <p className="text-sm text-white/80 truncate">{value}</p>
      </div>
    </div>
  );
};

const SkillChip = ({ label, variant = 'default' }) => {
  const styles = {
    matched:  { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)', color: '#34d399' },
    related:  { bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)',  color: '#60a5fa' },
    missing:  { bg: 'rgba(248,113,113,0.10)', border: 'rgba(248,113,113,0.25)', color: '#f87171' },
    default:  { bg: 'rgba(167,139,250,0.10)', border: 'rgba(167,139,250,0.25)', color: '#a78bfa' },
  };
  const s = styles[variant] || styles.default;
  return (
    <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full"
      style={{ background: s.bg, border: `1px solid ${s.border}`, color: s.color }}>
      {label}
    </span>
  );
};

/* ── main page ── */
const CandidateDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [decisionHistory, setDecisionHistory] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const [res, histRes] = await Promise.allSettled([
          getCVRecordDetail(Number(id)),
          getCVRecordDecisionHistory(Number(id)),
        ]);
        if (res.status === 'fulfilled' && res.value?.status === 'success') setDetail(res.value.data);
        else setError('Candidate not found.');
        if (histRes.status === 'fulfilled' && histRes.value?.status === 'success') setDecisionHistory(histRes.value.data || []);
      } catch {
        setError('Failed to load candidate.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handlePrint = () => {
    if (!detail) return;
    const p = detail.parsed || {};
    const q = detail.qualified || {};
    const ins = detail.insights || {};
    const app = detail.application || null;
    const ivs = detail.interviews || [];
    const skills = (p.skills || []).join(', ');
    const summary = ins.summary || ins.summary_text || '';
    const exact = (q.exact_matched_skills || []).join(', ');
    const related = (q.related_matched_skills || []).join(', ');
    const missing = (q.missing_skills || []).join(', ');
    const exp = (p.experience || p.work_experience || []).map(e =>
      `<tr><td>${e.title || e.position || '—'}</td><td>${e.company || e.organization || '—'}</td><td>${e.start_date || ''}${e.start_date && e.end_date ? ' – ' : ''}${e.end_date || e.period || ''}</td></tr>`
    ).join('');
    const edu = (p.education || []).map(e =>
      `<tr><td>${e.degree || e.qualification || '—'}</td><td>${e.institution || e.university || e.school || '—'}</td><td>${e.year || e.graduation_year || ''}</td></tr>`
    ).join('');
    const decisionColor = { INTERVIEW: '#16a34a', HOLD: '#d97706', REJECT: '#dc2626' }[detail.qualification_decision] || '#6b7280';

    const dName = app ? `${app.first_name} ${app.last_name}`.trim() : (p.name || detail.file_name || 'Unknown');
    const dEmail = app?.email || p.email || '';
    const dPhone = app?.phone || p.phone || '';
    const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<title>Candidate Report — ${dName}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#111;background:#fff;padding:32px}
  h1{font-size:24px;font-weight:700;color:#1a1a2e;margin-bottom:4px}
  .subtitle{color:#6b7280;font-size:13px;margin-bottom:20px}
  .decision{display:inline-block;padding:4px 14px;border-radius:99px;font-size:12px;font-weight:700;color:#fff;background:${decisionColor};margin-bottom:16px}
  .scores{display:flex;gap:24px;margin-bottom:20px}
  .score-box{border:1px solid #e5e7eb;border-radius:10px;padding:10px 18px;text-align:center}
  .score-box .num{font-size:22px;font-weight:700;color:#7c3aed}
  .score-box .lbl{font-size:11px;color:#9ca3af;margin-top:2px}
  h2{font-size:14px;font-weight:700;color:#374151;border-bottom:2px solid #7c3aed;padding-bottom:4px;margin:20px 0 10px}
  p{color:#4b5563;line-height:1.6;margin-bottom:8px}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .chip{padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600}
  .chip-green{background:#dcfce7;color:#15803d}
  .chip-blue{background:#dbeafe;color:#1d4ed8}
  .chip-red{background:#fee2e2;color:#b91c1c}
  .chip-gray{background:#f3f4f6;color:#374151}
  table{width:100%;border-collapse:collapse;margin-bottom:8px}
  th{background:#f9f7ff;color:#374151;padding:7px 10px;text-align:left;font-size:11px;font-weight:600;border-bottom:1px solid #e5e7eb}
  td{padding:6px 10px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#4b5563;vertical-align:top}
  .info-row{display:flex;gap:6px;margin-bottom:4px;font-size:12px}
  .info-label{color:#9ca3af;min-width:100px}
  .footer{margin-top:32px;padding-top:12px;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;display:flex;justify-content:space-between}
  @media print{body{padding:16px}}
</style></head>
<body>
  <h1>${dName}</h1>
  <div class="subtitle">
    ${dEmail ? `✉ ${dEmail}` : ''}
    ${dPhone ? `&nbsp;&nbsp;📞 ${dPhone}` : ''}
    ${detail.job_description_title ? `&nbsp;&nbsp;💼 ${detail.job_description_title}` : ''}
  </div>
  <div class="decision">${detail.qualification_decision || 'N/A'}</div>

  <div class="scores">
    ${detail.role_fit_score != null ? `<div class="score-box"><div class="num">${detail.role_fit_score}%</div><div class="lbl">Role Fit</div></div>` : ''}
    ${detail.qualification_confidence != null ? `<div class="score-box"><div class="num">${detail.qualification_confidence}%</div><div class="lbl">AI Confidence</div></div>` : ''}
    ${detail.rank != null ? `<div class="score-box"><div class="num">#${detail.rank}</div><div class="lbl">Rank</div></div>` : ''}
  </div>

  ${summary ? `<h2>AI Summary</h2><p>${summary}</p>` : ''}

  ${skills ? `<h2>Skills</h2><div class="chips">${(p.skills || []).map(s => `<span class="chip chip-gray">${s}</span>`).join('')}</div>` : ''}

  ${(exact || related || missing) ? `
  <h2>Skill Match</h2>
  ${exact ? `<p style="font-size:11px;color:#15803d;font-weight:600;margin-bottom:4px">✓ Exact Matches</p><div class="chips">${(q.exact_matched_skills || []).map(s => `<span class="chip chip-green">${s}</span>`).join('')}</div>` : ''}
  ${related ? `<p style="font-size:11px;color:#1d4ed8;font-weight:600;margin-bottom:4px">↗ Related Matches</p><div class="chips">${(q.related_matched_skills || []).map(s => `<span class="chip chip-blue">${s}</span>`).join('')}</div>` : ''}
  ${missing ? `<p style="font-size:11px;color:#b91c1c;font-weight:600;margin-bottom:4px">✗ Missing Skills</p><div class="chips">${(q.missing_skills || []).map(s => `<span class="chip chip-red">${s}</span>`).join('')}</div>` : ''}
  ` : ''}

  ${exp ? `<h2>Work Experience</h2><table><thead><tr><th>Position</th><th>Company</th><th>Period</th></tr></thead><tbody>${exp}</tbody></table>` : ''}

  ${edu ? `<h2>Education</h2><table><thead><tr><th>Degree</th><th>Institution</th><th>Year</th></tr></thead><tbody>${edu}</tbody></table>` : ''}

  ${app ? `<h2>Application Details</h2>
  ${app.current_location ? `<div class="info-row"><span class="info-label">Location:</span>${app.current_location}</div>` : ''}
  ${app.salary_expectation ? `<div class="info-row"><span class="info-label">Expected Salary:</span>${app.salary_expectation}</div>` : ''}
  ${app.previous_company ? `<div class="info-row"><span class="info-label">Prev Company:</span>${app.previous_company}</div>` : ''}
  ${app.cover_letter ? `<p style="margin-top:8px"><strong>Cover Letter:</strong><br/>${app.cover_letter.substring(0, 500)}${app.cover_letter.length > 500 ? '...' : ''}</p>` : ''}
  ` : ''}

  ${ivs.length > 0 ? `<h2>Interviews (${ivs.length})</h2><table><thead><tr><th>Type</th><th>Status</th><th>Scheduled</th><th>Outcome</th></tr></thead><tbody>
  ${ivs.map(iv => `<tr><td>${iv.interview_type || '—'}</td><td>${iv.status || '—'}</td><td>${iv.scheduled_datetime ? new Date(iv.scheduled_datetime).toLocaleString() : '—'}</td><td>${iv.outcome || '—'}</td></tr>`).join('')}
  </tbody></table>` : ''}

  <div class="footer">
    <span>Generated: ${new Date().toLocaleString()}</span>
    <span>PayPerProject — Recruitment Agent</span>
  </div>
</body></html>`;

    const win = window.open('', '_blank');
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => win.print(), 400);
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center"
      style={{ background: 'linear-gradient(135deg, #0a0a1a 0%, #0d1020 100%)' }}>
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-9 w-9 animate-spin text-violet-400" />
        <p className="text-sm text-white/40">Loading candidate profile...</p>
      </div>
    </div>
  );

  if (error || !detail) return (
    <div className="min-h-screen flex items-center justify-center"
      style={{ background: 'linear-gradient(135deg, #0a0a1a 0%, #0d1020 100%)' }}>
      <div className="text-center space-y-4">
        <AlertCircle className="h-12 w-12 mx-auto text-red-400" />
        <p className="text-white/60">{error || 'Candidate not found.'}</p>
        <button onClick={() => navigate('/recruitment/candidates')}
          className="text-sm text-violet-400 hover:text-violet-300 underline">
          Back to Candidates
        </button>
      </div>
    </div>
  );

  const parsed     = detail.parsed     || {};
  const qualified  = detail.qualified  || {};
  const insights   = detail.insights   || {};
  const application= detail.application|| null;
  const interviews = detail.interviews || [];
  const skills     = parsed.skills     || [];
  const experience = parsed.experience || parsed.work_experience || [];
  const education  = parsed.education  || [];
  const summary    = insights.summary  || insights.summary_text  || null;
  const exactSkills   = qualified.exact_matched_skills   || [];
  const relatedSkills = qualified.related_matched_skills || [];
  const missingSkills = qualified.missing_skills         || [];

  // Prefer real application data over AI-parsed text (AI parser may extract garbled values)
  const displayEmail = application?.email || parsed.email || '';
  const displayPhone = application?.phone || parsed.phone || '';
  const displayName  = application
    ? `${application.first_name} ${application.last_name}`.trim()
    : (parsed.name || detail.file_name || 'Unknown Candidate');

  const links = {
    LinkedIn:  parsed.linkedin   || parsed.linkedin_url,
    GitHub:    parsed.github     || parsed.github_url,
    Portfolio: parsed.portfolio  || parsed.portfolio_url || parsed.website,
  };

  const tabs = [
    { id: 'overview',    label: 'Overview' },
    { id: 'cv',         label: 'CV Details' },
    { id: 'application', label: application ? 'Application ✓' : 'Application' },
    { id: 'interviews',  label: `Interviews (${interviews.length})` },
    { id: 'history',     label: `History (${decisionHistory.length})` },
  ];

  const statusColors = {
    PENDING: '#fbbf24', SCHEDULED: '#34d399', COMPLETED: '#60a5fa',
    CANCELLED: '#f87171', RESCHEDULED: '#a78bfa',
  };

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #0a0a1a 0%, #0d1020 100%)' }}>

      {/* ── Top bar ── */}
      <div className="sticky top-0 z-20 px-6 py-3 flex items-center justify-between gap-3 border-b border-white/6 backdrop-blur-md"
        style={{ background: 'rgba(10,10,26,0.85)' }}>
        <button onClick={() => navigate('/recruitment/candidates')}
          className="inline-flex items-center gap-2 text-sm text-white/50 hover:text-white transition-colors">
          <ArrowLeft className="h-4 w-4" />Back to Candidates
        </button>
        {detail && (
          <button onClick={handlePrint}
            className="inline-flex items-center gap-2 text-sm font-medium px-4 py-1.5 rounded-lg transition-colors text-white hover:bg-white/10"
            style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}>
            <Printer className="h-4 w-4" />Print Report
          </button>
        )}
      </div>

      <div className="w-full px-4 sm:px-8 lg:px-12 py-8 space-y-6 max-w-[1400px] mx-auto">

        {/* ── Hero card ── */}
        <div className="rounded-2xl overflow-hidden"
          style={{ background: 'linear-gradient(135deg, rgba(124,58,237,0.15) 0%, rgba(96,165,250,0.08) 100%)', border: '1px solid rgba(167,139,250,0.2)' }}>
          <div className="p-6 sm:p-8">
            <div className="flex flex-col lg:flex-row lg:items-start gap-6">

              {/* Avatar + name */}
              <div className="flex items-start gap-4 flex-1 min-w-0">
                <div className="shrink-0 w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold text-white"
                  style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #a259ff 100%)' }}>
                  {(displayName || '?')[0].toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <DecisionChip decision={detail.qualification_decision} />
                    {detail.qualification_priority && (
                      <span className="text-xs px-2.5 py-1 rounded-full font-medium text-white/60"
                        style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}>
                        {detail.qualification_priority}
                      </span>
                    )}
                    {detail.rank != null && (
                      <span className="text-xs px-2.5 py-1 rounded-full font-medium text-amber-300"
                        style={{ background: 'rgba(251,191,36,0.12)', border: '1px solid rgba(251,191,36,0.25)' }}>
                        Rank #{detail.rank}
                      </span>
                    )}
                  </div>
                  <h1 className="text-2xl sm:text-3xl font-bold text-white leading-tight">
                    {displayName}
                  </h1>
                  {detail.job_description_title && (
                    <p className="mt-1 text-sm text-violet-300 flex items-center gap-1.5">
                      <Briefcase className="h-3.5 w-3.5" />{detail.job_description_title}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {displayEmail && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-white/60 px-2.5 py-1 rounded-lg"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}>
                        <Mail className="h-3 w-3" />{displayEmail}
                      </span>
                    )}
                    {displayPhone && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-white/60 px-2.5 py-1 rounded-lg"
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}>
                        <Phone className="h-3 w-3" />{displayPhone}
                      </span>
                    )}
                    {detail.created_at && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-white/40 px-2.5 py-1 rounded-lg"
                        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <Clock className="h-3 w-3" />
                        {new Date(detail.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Score rings */}
              <div className="flex gap-6 shrink-0 self-start lg:self-auto">
                <ScoreRing score={detail.role_fit_score}          label="Role Fit"   color="#7c3aed" />
                <ScoreRing score={detail.qualification_confidence} label="Confidence" color="#60a5fa" />
              </div>
            </div>
          </div>

          {/* Tab bar */}
          <div className="flex gap-0 border-t border-white/8 overflow-x-auto">
            {tabs.map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                className="relative px-5 py-3 text-sm font-medium whitespace-nowrap transition-colors"
                style={{ color: activeTab === tab.id ? '#a78bfa' : 'rgba(255,255,255,0.4)' }}>
                {tab.label}
                {activeTab === tab.id && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full"
                    style={{ background: 'linear-gradient(90deg, #7c3aed, #a259ff)' }} />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ── Tab: Overview ── */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {summary && (
                <Block title="AI Summary" icon={<FileText className="h-4 w-4" />}>
                  <p className="text-sm text-white/70 leading-relaxed">{summary}</p>
                </Block>
              )}

              {skills.length > 0 && (
                <Block title="Skills" icon={<CheckCircle2 className="h-4 w-4" />}>
                  <div className="flex flex-wrap gap-2">
                    {skills.map((s, i) => <SkillChip key={i} label={s} />)}
                  </div>
                </Block>
              )}

              {qualified.reasoning && (
                <Block title="Qualification Analysis" icon={<TrendingUp className="h-4 w-4" />}>
                  <QualificationReasoning
                    reasoning={qualified.reasoning}
                    exactMatchedSkills={exactSkills}
                    relatedMatchedSkills={relatedSkills}
                    missingSkills={missingSkills}
                    inferredSkills={[]}
                  />
                </Block>
              )}
            </div>

            <div className="space-y-6">
              {(exactSkills.length > 0 || relatedSkills.length > 0 || missingSkills.length > 0) && (
                <Block title="Skill Match">
                  {exactSkills.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] text-emerald-400 uppercase tracking-wider font-semibold mb-2">Exact Match</p>
                      <div className="flex flex-wrap gap-1.5">
                        {exactSkills.map((s, i) => <SkillChip key={i} label={s} variant="matched" />)}
                      </div>
                    </div>
                  )}
                  {relatedSkills.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] text-blue-400 uppercase tracking-wider font-semibold mb-2">Related</p>
                      <div className="flex flex-wrap gap-1.5">
                        {relatedSkills.map((s, i) => <SkillChip key={i} label={s} variant="related" />)}
                      </div>
                    </div>
                  )}
                  {missingSkills.length > 0 && (
                    <div>
                      <p className="text-[10px] text-red-400 uppercase tracking-wider font-semibold mb-2">Missing</p>
                      <div className="flex flex-wrap gap-1.5">
                        {missingSkills.map((s, i) => <SkillChip key={i} label={s} variant="missing" />)}
                      </div>
                    </div>
                  )}
                </Block>
              )}

              {Object.entries(links).some(([, v]) => v) && (
                <Block title="Links" icon={<Link2 className="h-4 w-4" />}>
                  <div className="space-y-2">
                    {Object.entries(links).map(([label, url]) => url ? (
                      <a key={label} href={url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm text-violet-300 hover:text-violet-200 transition-colors group"
                        style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.15)' }}>
                        <span>{label}</span>
                        <ExternalLink className="h-3.5 w-3.5 opacity-50 group-hover:opacity-100 transition-opacity" />
                      </a>
                    ) : null)}
                  </div>
                </Block>
              )}
            </div>
          </div>
        )}

        {/* ── Tab: CV Details ── */}
        {activeTab === 'cv' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {experience.length > 0 && (
              <Block title="Work Experience" icon={<Briefcase className="h-4 w-4" />}>
                <div className="space-y-4">
                  {experience.map((exp, i) => (
                    <div key={i} className="relative pl-4 border-l-2 border-violet-500/30">
                      <div className="absolute -left-1.5 top-1 w-3 h-3 rounded-full bg-violet-500/60 border-2 border-violet-800" />
                      <div className="flex items-start justify-between gap-2 mb-0.5">
                        <p className="text-sm font-semibold text-white">
                          {exp.title || exp.position || exp.role || '—'}
                        </p>
                        {(exp.start_date || exp.end_date || exp.period || exp.duration) && (
                          <span className="text-xs text-white/30 shrink-0">
                            {exp.start_date || ''}{exp.start_date && (exp.end_date || exp.period) ? ' – ' : ''}{exp.end_date || exp.period || exp.duration || ''}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-violet-300/80 mb-1">{exp.company || exp.organization || '—'}</p>
                      {(exp.description || exp.responsibilities) && (
                        <p className="text-xs text-white/50 leading-relaxed">
                          {Array.isArray(exp.responsibilities)
                            ? exp.responsibilities.join(' • ')
                            : (exp.description || exp.responsibilities)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </Block>
            )}

            <div className="space-y-6">
              {education.length > 0 && (
                <Block title="Education" icon={<GraduationCap className="h-4 w-4" />}>
                  <div className="space-y-3">
                    {education.map((edu, i) => (
                      <div key={i} className="p-3 rounded-xl"
                        style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-white">
                              {edu.degree || edu.qualification || edu.field || '—'}
                            </p>
                            <p className="text-xs text-violet-300/80 mt-0.5">
                              {edu.institution || edu.university || edu.school || '—'}
                            </p>
                          </div>
                          {(edu.year || edu.graduation_year || edu.end_year) && (
                            <span className="text-xs text-white/30 shrink-0">
                              {edu.year || edu.graduation_year || edu.end_year}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </Block>
              )}

              {Object.entries(links).some(([, v]) => v) && (
                <Block title="Links" icon={<Link2 className="h-4 w-4" />}>
                  <div className="space-y-2">
                    {Object.entries(links).map(([label, url]) => url ? (
                      <a key={label} href={url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm text-violet-300 hover:text-violet-200 transition-colors group"
                        style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.15)' }}>
                        <span>{label}</span>
                        <ExternalLink className="h-3.5 w-3.5 opacity-50 group-hover:opacity-100 transition-opacity" />
                      </a>
                    ) : null)}
                  </div>
                </Block>
              )}

              {skills.length > 0 && (
                <Block title="Skills" icon={<CheckCircle2 className="h-4 w-4" />}>
                  <div className="flex flex-wrap gap-2">
                    {skills.map((s, i) => <SkillChip key={i} label={s} />)}
                  </div>
                </Block>
              )}
            </div>
          </div>
        )}

        {/* ── Tab: Application ── */}
        {activeTab === 'application' && (
          !application ? (
            <Block>
              <div className="py-12 text-center space-y-3">
                <FileText className="h-12 w-12 mx-auto text-white/15" />
                <p className="text-white/40 text-sm">No application form submission found.</p>
                <p className="text-white/25 text-xs">Candidate was processed via CV upload, not the public form.</p>
              </div>
            </Block>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Block title="Personal Information" icon={<User className="h-4 w-4" />}>
                <div className="grid grid-cols-1 gap-3">
                  <InfoPill icon={<User className="h-3.5 w-3.5" />}        label="Name"            value={`${application.first_name} ${application.last_name}`} />
                  <InfoPill icon={<Mail className="h-3.5 w-3.5" />}        label="Email"           value={application.email} />
                  <InfoPill icon={<Phone className="h-3.5 w-3.5" />}       label="Phone"           value={application.phone} />
                  <InfoPill icon={<MapPin className="h-3.5 w-3.5" />}      label="Location"        value={application.current_location} />
                  <InfoPill icon={<DollarSign className="h-3.5 w-3.5" />}  label="Expected Salary" value={application.salary_expectation} />
                  <InfoPill icon={<Building2 className="h-3.5 w-3.5" />}   label="Previous Company" value={application.previous_company} />
                  <InfoPill icon={<DollarSign className="h-3.5 w-3.5" />}  label="Previous Salary" value={application.previous_salary} />
                  <InfoPill icon={<GraduationCap className="h-3.5 w-3.5"/>}label="Education"       value={application.education} />
                </div>
              </Block>

              <div className="space-y-6">
                {(application.linkedin_url || application.github_url || application.other_links) && (
                  <Block title="Links" icon={<Link2 className="h-4 w-4" />}>
                    <div className="space-y-2">
                      {application.linkedin_url && (
                        <a href={application.linkedin_url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm text-violet-300 hover:text-violet-200 transition-colors"
                          style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.15)' }}>
                          LinkedIn <ExternalLink className="h-3.5 w-3.5 opacity-50" />
                        </a>
                      )}
                      {application.github_url && (
                        <a href={application.github_url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm text-violet-300 hover:text-violet-200 transition-colors"
                          style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.15)' }}>
                          GitHub <ExternalLink className="h-3.5 w-3.5 opacity-50" />
                        </a>
                      )}
                      {application.other_links && <p className="text-xs text-white/50 px-1">{application.other_links}</p>}
                    </div>
                  </Block>
                )}

                {application.cover_letter && (
                  <Block title="Cover Letter" icon={<FileText className="h-4 w-4" />}>
                    <p className="text-sm text-white/65 leading-relaxed whitespace-pre-wrap">{application.cover_letter}</p>
                  </Block>
                )}

                <div className="flex items-center justify-between text-xs text-white/30 px-1">
                  <span>Applied: {application.applied_at ? new Date(application.applied_at).toLocaleString() : '—'}</span>
                  <span className="px-2.5 py-1 rounded-full capitalize"
                    style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}>
                    {application.status}
                  </span>
                </div>
              </div>
            </div>
          )
        )}

        {/* ── Tab: Interviews ── */}
        {activeTab === 'interviews' && (
          interviews.length === 0 ? (
            <Block>
              <div className="py-12 text-center space-y-3">
                <Calendar className="h-12 w-12 mx-auto text-white/15" />
                <p className="text-white/40 text-sm">No interviews scheduled yet.</p>
              </div>
            </Block>
          ) : (
            <div className="space-y-4">
              {interviews.map((iv) => (
                <div key={iv.id} className="rounded-2xl overflow-hidden"
                  style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}>

                  {/* Header row */}
                  <div className="flex flex-wrap items-center gap-2 px-5 pt-4 pb-3">
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full text-white"
                      style={{ background: statusColors[iv.status] || '#6b7280' }}>
                      {iv.status}
                    </span>
                    {iv.outcome && (
                      <span className="text-xs px-2.5 py-1 rounded-full text-white/70"
                        style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)' }}>
                        {iv.outcome.replace(/_/g, ' ')}
                      </span>
                    )}
                    <span className="text-xs px-2.5 py-1 rounded-full text-violet-300"
                      style={{ background: 'rgba(167,139,250,0.10)', border: '1px solid rgba(167,139,250,0.2)' }}>
                      {iv.interview_type}
                    </span>
                    <span className="text-xs text-white/25 ml-auto">
                      Created: {iv.created_at ? new Date(iv.created_at).toLocaleDateString() : '—'}
                    </span>
                  </div>

                  {/* Main info */}
                  <div className="px-5 pb-4 space-y-2">
                    {/* Scheduled time */}
                    {(iv.scheduled_datetime || iv.selected_slot) && (
                      <div className="flex items-center gap-2 text-sm text-white/70">
                        <Clock className="h-4 w-4 text-violet-400 shrink-0" />
                        <span>
                          {iv.scheduled_datetime
                            ? new Date(iv.scheduled_datetime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
                            : iv.selected_slot}
                        </span>
                      </div>
                    )}

                    {/* Candidate contact info (from DB, always reliable) */}
                    <div className="flex flex-wrap gap-4 text-xs text-white/50">
                      {iv.candidate_name && (
                        <span className="flex items-center gap-1.5">
                          <User className="h-3 w-3 text-white/30" />{iv.candidate_name}
                        </span>
                      )}
                      {iv.candidate_email && (
                        <span className="flex items-center gap-1.5">
                          <Mail className="h-3 w-3 text-white/30" />{iv.candidate_email}
                        </span>
                      )}
                      {iv.candidate_phone && (
                        <span className="flex items-center gap-1.5">
                          <Phone className="h-3 w-3 text-white/30" />{iv.candidate_phone}
                        </span>
                      )}
                    </div>

                    {/* Google Meet link */}
                    {iv.meeting_link && (
                      <a href={iv.meeting_link} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg mt-1 transition-opacity hover:opacity-80"
                        style={{ background: 'rgba(26,115,232,0.15)', border: '1px solid rgba(26,115,232,0.3)', color: '#60a5fa' }}>
                        <ExternalLink className="h-3 w-3" />
                        Join Google Meet
                      </a>
                    )}

                    {/* Notes */}
                    {iv.notes && (
                      <p className="text-xs text-white/40 italic mt-1">{iv.notes}</p>
                    )}
                  </div>

                  {/* Feedback section */}
                  {iv.feedback_rating && (
                    <div className="px-5 py-3 border-t border-white/6 space-y-2"
                      style={{ background: 'rgba(255,255,255,0.015)' }}>
                      <div className="flex items-center gap-3">
                        <div className="flex gap-0.5">
                          {[1,2,3,4,5].map(s => (
                            <Star key={s} className={`h-4 w-4 ${s <= iv.feedback_rating ? 'text-amber-400 fill-amber-400' : 'text-white/15'}`} />
                          ))}
                        </div>
                        <span className="text-xs text-white/35">
                          {iv.feedback_submitted_at
                            ? new Date(iv.feedback_submitted_at).toLocaleDateString()
                            : 'Feedback submitted'}
                        </span>
                      </div>
                      {iv.feedback_notes && (
                        <p className="text-xs text-white/55 leading-relaxed">{iv.feedback_notes}</p>
                      )}
                      <div className="flex flex-wrap gap-3">
                        {iv.feedback_strengths && (
                          <span className="text-xs text-emerald-400/80">
                            <span className="font-semibold">Strengths:</span> {iv.feedback_strengths}
                          </span>
                        )}
                        {iv.feedback_improvements && (
                          <span className="text-xs text-amber-400/80">
                            <span className="font-semibold">Improve:</span> {iv.feedback_improvements}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                </div>
              ))}
            </div>
          )
        )}

        {/* ── History tab ── */}
        {activeTab === 'history' && (() => {
          const DS = {
            INTERVIEW: { color: '#34d399', glow: 'rgba(52,211,153,0.25)',  bg: 'rgba(52,211,153,0.10)',  border: 'rgba(52,211,153,0.25)',  label: 'Interview' },
            HOLD:      { color: '#fbbf24', glow: 'rgba(251,191,36,0.25)',   bg: 'rgba(251,191,36,0.10)',   border: 'rgba(251,191,36,0.25)',   label: 'Hold'      },
            REJECT:    { color: '#f87171', glow: 'rgba(248,113,113,0.25)',  bg: 'rgba(248,113,113,0.10)',  border: 'rgba(248,113,113,0.25)',  label: 'Reject'    },
          };
          const getDS = (d) => DS[d] || { color: '#a78bfa', glow: 'rgba(167,139,250,0.2)', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.2)', label: d || '—' };

          return (
            <div className="max-w-2xl space-y-4">
              {/* header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg p-2" style={{ background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.2)' }}>
                    <Clock className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white">Decision History</h3>
                    <p className="text-xs text-white/35">Complete audit trail of status changes</p>
                  </div>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full font-medium text-violet-300"
                  style={{ background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.2)' }}>
                  {decisionHistory.length} {decisionHistory.length === 1 ? 'entry' : 'entries'}
                </span>
              </div>

              {decisionHistory.length === 0 ? (
                <div className="rounded-2xl flex flex-col items-center py-16 gap-4"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div className="rounded-2xl p-4" style={{ background: 'rgba(255,255,255,0.04)' }}>
                    <Clock className="h-8 w-8 text-white/20" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium text-white/40">No history yet</p>
                    <p className="text-xs text-white/20 mt-1">Decision changes will be recorded here automatically</p>
                  </div>
                </div>
              ) : (
                <div className="relative">
                  {/* vertical line */}
                  <div className="absolute left-5 top-6 bottom-6 w-px" style={{ background: 'linear-gradient(to bottom, rgba(167,139,250,0.3), rgba(167,139,250,0.05))' }} />

                  <ol className="space-y-3">
                    {decisionHistory.map((log, idx) => {
                      const toDS  = getDS(log.to_decision);
                      const fromDS = log.from_decision ? getDS(log.from_decision) : null;
                      const isAI  = log.source === 'AI';
                      const isFirst = idx === 0;
                      const dateStr = log.changed_at
                        ? new Date(log.changed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
                        : '—';

                      return (
                        <li key={log.id} className="relative flex gap-4 items-start">
                          {/* dot */}
                          <div className="relative z-10 shrink-0 mt-1">
                            <div className="h-10 w-10 rounded-full flex items-center justify-center"
                              style={{
                                background: toDS.bg,
                                border: `1.5px solid ${toDS.border}`,
                                boxShadow: `0 0 12px ${toDS.glow}`,
                              }}>
                              {log.to_decision === 'INTERVIEW' && <CheckCircle className="h-4 w-4" style={{ color: toDS.color }} />}
                              {log.to_decision === 'HOLD'      && <Clock        className="h-4 w-4" style={{ color: toDS.color }} />}
                              {log.to_decision === 'REJECT'    && <XCircle      className="h-4 w-4" style={{ color: toDS.color }} />}
                              {!['INTERVIEW','HOLD','REJECT'].includes(log.to_decision) && (
                                <span className="h-2 w-2 rounded-full" style={{ background: toDS.color }} />
                              )}
                            </div>
                          </div>

                          {/* card */}
                          <div className="flex-1 min-w-0 rounded-2xl overflow-hidden"
                            style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)' }}>

                            {/* colored top accent */}
                            <div className="h-0.5 w-full" style={{ background: `linear-gradient(90deg, ${toDS.color}55, transparent)` }} />

                            <div className="p-4">
                              {/* top row: from→to + source badge */}
                              <div className="flex items-center gap-2 flex-wrap mb-3">
                                {fromDS ? (
                                  <>
                                    <span className="inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full"
                                      style={{ background: fromDS.bg, border: `1px solid ${fromDS.border}`, color: fromDS.color }}>
                                      {fromDS.label}
                                    </span>
                                    <svg className="h-3 w-3 shrink-0" viewBox="0 0 12 12" fill="none">
                                      <path d="M2 6h8M7 3l3 3-3 3" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                    </svg>
                                  </>
                                ) : (
                                  <span className="text-xs text-white/25 italic">Initial decision</span>
                                )}
                                <span className="inline-flex items-center text-xs font-bold px-2.5 py-1 rounded-full"
                                  style={{ background: toDS.bg, border: `1px solid ${toDS.border}`, color: toDS.color }}>
                                  {toDS.label}
                                </span>

                                <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full"
                                  style={isAI
                                    ? { background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.25)', color: '#c4b5fd' }
                                    : { background: 'rgba(96,165,250,0.10)',  border: '1px solid rgba(96,165,250,0.22)',  color: '#93c5fd' }}>
                                  {isAI ? (
                                    <><Star className="h-3 w-3" /> AI Processing</>
                                  ) : (
                                    <><User className="h-3 w-3" /> Manual</>
                                  )}
                                </span>
                              </div>

                              {/* bottom row: date + user */}
                              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-2.5"
                                style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                <span className="flex items-center gap-1.5 text-xs text-white/35">
                                  <Calendar className="h-3 w-3" />{dateStr}
                                </span>
                                {log.changed_by && (
                                  <span className="flex items-center gap-1.5 text-xs text-white/35">
                                    <User className="h-3 w-3" />{log.changed_by}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              )}
            </div>
          );
        })()}

      </div>
    </div>
  );
};

export default CandidateDetailPage;
