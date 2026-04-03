import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Loader2, ArrowLeft, File, Trash2,
  FileSpreadsheet, FileType, Presentation,
  BookOpen, Clock, User, Hash, Calendar,
  Sparkles, Brain, Lightbulb, ListChecks, ArrowRight,
  TrendingUp, AlertTriangle, Target, Tag, Building2,
  MapPin, DollarSign, Users, Shield, Zap,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import * as operationsService from '@/services/operationsAgentService';

// ─── Helpers ────────────────────────────────
const FILE_TYPE_CONFIG = {
  pdf:  { icon: FileText,        color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'PDF' },
  docx: { icon: FileType,        color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', label: 'DOCX' },
  xlsx: { icon: FileSpreadsheet, color: '#10b981', bg: 'rgba(16,185,129,0.12)', label: 'XLSX' },
  csv:  { icon: FileSpreadsheet, color: '#14b8a6', bg: 'rgba(20,184,166,0.12)', label: 'CSV' },
  pptx: { icon: Presentation,    color: '#f97316', bg: 'rgba(249,115,22,0.12)', label: 'PPTX' },
  txt:  { icon: FileText,        color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: 'TXT' },
};
const getFileConfig = (type) => FILE_TYPE_CONFIG[type] || { icon: File, color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: 'FILE' };

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const formatDate = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

// ─── Markdown Renderer ──────────────────────
const markdownComponents = {
  h2: ({ children }) => (
    <div className="flex items-center gap-2.5 mt-7 mb-3 pb-2 border-b border-white/[0.06]">
      <div className="h-6 w-1 rounded-full bg-amber-500" />
      <h2 className="text-lg font-bold text-amber-400 m-0">{children}</h2>
    </div>
  ),
  h3: ({ children }) => (
    <div className="flex items-center gap-2 mt-5 mb-2">
      <div className="h-1.5 w-1.5 rounded-full bg-violet-400" />
      <h3 className="text-sm font-semibold text-violet-300 m-0">{children}</h3>
    </div>
  ),
  p: ({ children }) => (
    <p className="text-sm text-white/55 leading-relaxed my-2 ml-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="space-y-1.5 my-3 ml-1 list-none p-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="space-y-1.5 my-3 ml-1 list-none p-0 counter-reset-[item]">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="flex items-start gap-2.5 text-sm text-white/55 leading-relaxed p-0 m-0">
      <span className="flex items-center justify-center h-5 w-5 rounded-full shrink-0 mt-0.5 text-[10px] font-bold"
        style={{ background: 'rgba(245,158,11,0.12)', color: '#f59e0b' }}
      >•</span>
      <span className="flex-1">{children}</span>
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-white/80">{children}</strong>
  ),
  a: ({ children, href }) => (
    <a href={href} className="text-amber-400 underline underline-offset-2" target="_blank" rel="noopener noreferrer">{children}</a>
  ),
};

// ─── Config Maps ────────────────────────────
const SENTIMENT_CONFIG = {
  positive: { color: '#10b981', bg: 'rgba(16,185,129,0.1)', icon: TrendingUp, label: 'Positive' },
  negative: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', icon: AlertTriangle, label: 'Negative' },
  neutral:  { color: '#6b7280', bg: 'rgba(107,114,128,0.1)', icon: Target, label: 'Neutral' },
  mixed:    { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', icon: Brain, label: 'Mixed' },
};

const IMPORTANCE_CONFIG = {
  critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'Critical' },
  high:     { color: '#f97316', bg: 'rgba(249,115,22,0.12)', label: 'High' },
  medium:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', label: 'Medium' },
  low:      { color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: 'Low' },
};

// ─── Main Component ─────────────────────────
const SummaryDetailPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const id = (location.pathname.match(/\/operations\/summarization\/(\d+)/) || [])[1];
  const { toast } = useToast();

  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      setLoading(true);
      const res = await operationsService.getSummary(id);
      if (res.status === 'success') {
        setSummary(res.summary);
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to load summary details', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const handleDelete = async () => {
    try {
      setDeleting(true);
      await operationsService.deleteSummary(id);
      toast({ title: 'Deleted', description: 'Summary deleted successfully' });
      navigate('/operations/summarization');
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to delete', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <Loader2 className="h-10 w-10 animate-spin text-amber-500/60" />
        <p className="mt-4 text-sm text-white/40">Loading summary details...</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <FileText className="h-12 w-12 text-white/15 mb-4" />
        <p className="text-white/40 text-sm">Summary not found</p>
        <Button
          variant="ghost"
          className="mt-4 text-amber-400 hover:text-amber-300"
          onClick={() => navigate('/operations/summarization')}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Summaries
        </Button>
      </div>
    );
  }

  const fc = getFileConfig(summary.file_type);
  const FI = fc.icon;

  const sentimentCfg = SENTIMENT_CONFIG[summary.sentiment] || null;
  const SentimentIcon = sentimentCfg?.icon || Target;
  const importanceCfg = IMPORTANCE_CONFIG[summary.importance_level] || null;

  const hasEntities = summary.entities && (
    summary.entities.people?.length > 0 || summary.entities.organizations?.length > 0 ||
    summary.entities.locations?.length > 0 || summary.entities.dates?.length > 0 ||
    summary.entities.amounts?.length > 0
  );
  const hasInsights = sentimentCfg || importanceCfg || summary.topics?.length > 0 || hasEntities ||
    summary.risks?.length > 0 || summary.opportunities?.length > 0 || summary.deadlines?.length > 0;

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Button
        variant="ghost"
        className="text-white/50 hover:text-white gap-2 -ml-2"
        onClick={() => navigate('/operations/summarization')}
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Summaries
      </Button>

      {/* ── Header Card ── */}
      <div className="rounded-2xl border border-white/[0.06] p-6" style={{ background: 'rgba(0,0,0,0.25)' }}>
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl shrink-0" style={{ backgroundColor: fc.bg }}>
            <FI className="h-8 w-8" style={{ color: fc.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-white">{summary.original_filename}</h1>
              {summary.document_category && (
                <span className="text-[11px] px-3 py-1 rounded-full font-medium"
                  style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                  {summary.document_category}
                </span>
              )}
            </div>
            <p className="text-sm text-white/35">AI-powered summary with insights</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-white/40 hover:text-red-400 hover:bg-red-500/10 gap-1.5 shrink-0"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Delete
          </Button>
        </div>

        {/* Quick Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-6">
          {[
            { label: 'Format', value: summary.file_type?.toUpperCase(), icon: File, color: fc.color },
            { label: 'Size', value: formatFileSize(summary.file_size), icon: Hash, color: '#8b5cf6' },
            { label: 'Pages', value: summary.page_count || 'N/A', icon: BookOpen, color: '#3b82f6' },
            { label: 'Words', value: summary.word_count?.toLocaleString() || 'N/A', icon: FileText, color: '#14b8a6' },
            { label: 'Created', value: formatDate(summary.created_at), icon: Calendar, color: '#f59e0b' },
            { label: 'By', value: summary.created_by || 'Unknown', icon: User, color: '#ec4899' },
          ].map((m, i) => (
            <div key={i} className="flex items-center gap-2.5 p-3 rounded-xl border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
              <m.icon className="h-4 w-4 shrink-0" style={{ color: `${m.color}80` }} />
              <div className="min-w-0">
                <p className="text-[10px] text-white/30 uppercase tracking-wider">{m.label}</p>
                <p className="text-sm text-white font-semibold truncate">{m.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Sentiment + Importance + Topics badges */}
        {(sentimentCfg || importanceCfg || summary.topics?.length > 0) && (
          <div className="flex flex-wrap gap-3 mt-4">
            {sentimentCfg && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/[0.06]" style={{ background: sentimentCfg.bg }}>
                <SentimentIcon className="h-4 w-4" style={{ color: sentimentCfg.color }} />
                <span className="text-xs font-semibold" style={{ color: sentimentCfg.color }}>
                  Sentiment: {sentimentCfg.label}
                </span>
              </div>
            )}
            {importanceCfg && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/[0.06]" style={{ background: importanceCfg.bg }}>
                <Shield className="h-4 w-4" style={{ color: importanceCfg.color }} />
                <span className="text-xs font-semibold" style={{ color: importanceCfg.color }}>
                  Importance: {importanceCfg.label}
                </span>
              </div>
            )}
            {summary.topics?.length > 0 && summary.topics.map((topic, i) => (
              <span key={i} className="text-[11px] px-2.5 py-1.5 rounded-lg font-medium border border-white/[0.06]"
                style={{ background: 'rgba(139,92,246,0.1)', color: '#c4b5fd' }}>
                {topic}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Rich Summary ── */}
      {summary.rich_summary && (
        <div className="rounded-xl border border-white/[0.06] p-6" style={{ background: 'rgba(0,0,0,0.15)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="h-5 w-5 text-amber-400" />
            <h3 className="text-base font-bold text-white">Summary</h3>
          </div>
          <ReactMarkdown components={markdownComponents}>{summary.rich_summary}</ReactMarkdown>
        </div>
      )}

      {/* ── Insights Section ── */}
      {hasInsights && (
        <div className="space-y-5">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-violet-400" />
            <h3 className="text-base font-bold text-white">Document Insights</h3>
          </div>

          {/* Sentiment & Importance detail cards */}
          {(sentimentCfg || importanceCfg) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {sentimentCfg && (
                <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: sentimentCfg.bg }}>
                  <div className="flex items-center gap-2 mb-3">
                    <SentimentIcon className="h-5 w-5" style={{ color: sentimentCfg.color }} />
                    <h4 className="text-sm font-bold" style={{ color: sentimentCfg.color }}>
                      Sentiment — {sentimentCfg.label}
                    </h4>
                  </div>
                  {summary.sentiment_explanation && (
                    <p className="text-sm text-white/50 leading-relaxed">{summary.sentiment_explanation}</p>
                  )}
                </div>
              )}
              {importanceCfg && (
                <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: importanceCfg.bg }}>
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="h-5 w-5" style={{ color: importanceCfg.color }} />
                    <h4 className="text-sm font-bold" style={{ color: importanceCfg.color }}>
                      Importance — {importanceCfg.label}
                    </h4>
                  </div>
                  {summary.importance_reason && (
                    <p className="text-sm text-white/50 leading-relaxed">{summary.importance_reason}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Topics */}
          {summary.topics?.length > 0 && (
            <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <div className="flex items-center gap-2 mb-3">
                <Tag className="h-4 w-4 text-violet-400" />
                <h4 className="text-sm font-semibold text-white">Topics</h4>
              </div>
              <div className="flex flex-wrap gap-2">
                {summary.topics.map((topic, i) => (
                  <span key={i} className="text-xs px-3 py-1.5 rounded-full font-medium border border-white/[0.06]"
                    style={{ background: 'rgba(139,92,246,0.1)', color: '#c4b5fd' }}>
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Entities */}
          {hasEntities && (
            <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <div className="flex items-center gap-2 mb-4">
                <Zap className="h-4 w-4 text-amber-400" />
                <h4 className="text-sm font-semibold text-white">Entities Detected</h4>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {[
                  { key: 'people', label: 'People', icon: Users, color: '#3b82f6' },
                  { key: 'organizations', label: 'Organizations', icon: Building2, color: '#10b981' },
                  { key: 'locations', label: 'Locations', icon: MapPin, color: '#f43f5e' },
                  { key: 'dates', label: 'Dates', icon: Calendar, color: '#f97316' },
                  { key: 'amounts', label: 'Amounts', icon: DollarSign, color: '#eab308' },
                ].map(({ key, label, icon: Icon, color }) => {
                  const items = summary.entities?.[key];
                  if (!items?.length) return null;
                  return (
                    <div key={key} className="rounded-lg border border-white/[0.05] p-3" style={{ background: 'rgba(0,0,0,0.1)' }}>
                      <div className="flex items-center gap-1.5 mb-2">
                        <Icon className="h-3.5 w-3.5" style={{ color }} />
                        <span className="text-[11px] font-semibold" style={{ color }}>{label}</span>
                        <span className="text-[10px] text-white/25 ml-auto">{items.length}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((v, i) => (
                          <span key={i} className="text-[11px] px-2 py-0.5 rounded-md"
                            style={{ background: `${color}15`, color: `${color}cc` }}>
                            {v}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Risks & Opportunities */}
          {(summary.risks?.length > 0 || summary.opportunities?.length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {summary.risks?.length > 0 && (
                <div className="rounded-xl border border-red-500/10 p-5" style={{ background: 'rgba(239,68,68,0.04)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="h-4 w-4 text-red-400" />
                    <h4 className="text-sm font-semibold text-red-400">Risks & Concerns</h4>
                  </div>
                  <div className="space-y-2.5">
                    {summary.risks.map((risk, i) => (
                      <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg border border-red-500/10" style={{ background: 'rgba(239,68,68,0.05)' }}>
                        <span className="text-red-400 font-bold text-xs mt-0.5 shrink-0">!</span>
                        <span className="text-xs text-white/50 leading-relaxed">{risk}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {summary.opportunities?.length > 0 && (
                <div className="rounded-xl border border-emerald-500/10 p-5" style={{ background: 'rgba(16,185,129,0.04)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <TrendingUp className="h-4 w-4 text-emerald-400" />
                    <h4 className="text-sm font-semibold text-emerald-400">Opportunities</h4>
                  </div>
                  <div className="space-y-2.5">
                    {summary.opportunities.map((opp, i) => (
                      <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg border border-emerald-500/10" style={{ background: 'rgba(16,185,129,0.05)' }}>
                        <span className="text-emerald-400 font-bold text-xs mt-0.5 shrink-0">+</span>
                        <span className="text-xs text-white/50 leading-relaxed">{opp}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Deadlines */}
          {summary.deadlines?.length > 0 && (
            <div className="rounded-xl border border-orange-500/10 p-5" style={{ background: 'rgba(249,115,22,0.04)' }}>
              <div className="flex items-center gap-2 mb-3">
                <Calendar className="h-4 w-4 text-orange-400" />
                <h4 className="text-sm font-semibold text-orange-400">Key Deadlines</h4>
              </div>
              <div className="space-y-2">
                {summary.deadlines.map((dl, i) => (
                  <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg border border-orange-500/10" style={{ background: 'rgba(249,115,22,0.05)' }}>
                    <Clock className="h-3.5 w-3.5 text-orange-400 mt-0.5 shrink-0" />
                    <span className="text-xs text-white/50 leading-relaxed">{dl}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Key Findings ── */}
      {summary.key_findings?.length > 0 && (
        <div className="rounded-xl border border-amber-500/10 p-5" style={{ background: 'rgba(245,158,11,0.04)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Lightbulb className="h-5 w-5 text-amber-400" />
            <h3 className="text-base font-bold text-white">Key Findings</h3>
            <span className="text-[10px] text-white/30 ml-auto">{summary.key_findings.length} findings</span>
          </div>
          <div className="space-y-3">
            {summary.key_findings.map((finding, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div className="h-6 w-6 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background: 'rgba(245,158,11,0.12)' }}>
                  <span className="text-[11px] font-bold text-amber-400">{i + 1}</span>
                </div>
                <p className="text-sm text-white/55 leading-relaxed">{finding}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Action Items ── */}
      {summary.action_items?.length > 0 && (
        <div className="rounded-xl border border-emerald-500/10 p-5" style={{ background: 'rgba(16,185,129,0.04)' }}>
          <div className="flex items-center gap-2 mb-4">
            <ListChecks className="h-5 w-5 text-emerald-400" />
            <h3 className="text-base font-bold text-white">Action Items</h3>
            <span className="text-[10px] text-white/30 ml-auto">{summary.action_items.length} items</span>
          </div>
          <div className="space-y-2.5">
            {summary.action_items.map((item, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-emerald-500/10" style={{ background: 'rgba(16,185,129,0.04)' }}>
                <ArrowRight className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                <span className="text-sm text-white/55 leading-relaxed">{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SummaryDetailPage;
