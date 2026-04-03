import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Search, Loader2, Sparkles, RefreshCw, Upload,
  FileSpreadsheet, FileType, Presentation, File, Trash2,
  ChevronDown, ChevronUp, ArrowRight, Clock, BookOpen,
  Lightbulb, ListChecks, User,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import * as operationsService from '@/services/operationsAgentService';

// ─── Helpers ────────────────────────────────
const FILE_TYPE_CONFIG = {
  pdf:  { icon: FileText,        color: '#ef4444', label: 'PDF' },
  docx: { icon: FileType,        color: '#3b82f6', label: 'DOCX' },
  xlsx: { icon: FileSpreadsheet, color: '#10b981', label: 'XLSX' },
  csv:  { icon: FileSpreadsheet, color: '#14b8a6', label: 'CSV' },
  pptx: { icon: Presentation,    color: '#f97316', label: 'PPTX' },
  txt:  { icon: FileText,        color: '#6b7280', label: 'TXT' },
};
const getFileConfig = (type) => FILE_TYPE_CONFIG[type] || { icon: File, color: '#6b7280', label: 'FILE' };

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
};

const formatDate = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

// ─── Markdown Renderer with colored headings/bullets ──────────
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
  li: ({ children, ordered, index }) => (
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

const MarkdownSummary = ({ content }) => {
  if (!content) return null;
  return (
    <div className="space-y-1">
      <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
    </div>
  );
};

// ─── Main Component ─────────────────────────
const SummarizationInsights = () => {
  const { toast } = useToast();
  const fileInputRef = useRef(null);

  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  // Fetch summaries
  const fetchSummaries = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (searchQuery) params.search = searchQuery;
      const res = await operationsService.listSummaries(params);
      if (res.status === 'success') {
        setSummaries(res.summaries || []);
      }
    } catch (e) {
      console.error('Fetch summaries error:', e);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => { fetchSummaries(); }, [fetchSummaries]);

  // Upload and summarize
  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = '';

    try {
      setUploading(true);
      const res = await operationsService.uploadAndSummarize(file);
      if (res.status === 'success') {
        toast({
          title: 'Summary Generated',
          description: `"${file.name}" has been summarized successfully`,
        });
        // Add the new summary to the top
        if (res.summary) {
          setSummaries(prev => [res.summary, ...prev]);
          setExpandedId(res.summary.id);
        } else {
          fetchSummaries();
        }
      }
    } catch (e) {
      toast({
        title: 'Summarization Failed',
        description: e.message || 'Failed to process document',
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  // Delete summary
  const handleDelete = async (summaryId) => {
    try {
      setDeletingId(summaryId);
      await operationsService.deleteSummary(summaryId);
      toast({ title: 'Deleted', description: 'Summary deleted successfully' });
      setSummaries(prev => prev.filter(s => s.id !== summaryId));
      if (expandedId === summaryId) setExpandedId(null);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to delete', variant: 'destructive' });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-white">Document Summarization</h2>
          <p className="text-gray-400 text-sm mt-1">Upload any document and get an AI-powered comprehensive summary</p>
        </div>
        <Badge variant="outline" className="text-xs py-1 px-3 w-fit" style={{ borderColor: '#f59e0b40', color: '#f59e0b' }}>
          {summaries.length} {summaries.length === 1 ? 'Summary' : 'Summaries'}
        </Badge>
      </div>

      {/* Upload Area */}
      <div
        className="relative rounded-2xl border-2 border-dashed border-white/[0.08] hover:border-amber-500/30 transition-colors cursor-pointer overflow-hidden"
        style={{ background: 'rgba(0,0,0,0.15)' }}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md"
          onChange={handleFileSelect}
          disabled={uploading}
        />
        <div className="flex flex-col items-center justify-center py-10 px-4">
          {uploading ? (
            <>
              <div className="relative">
                <Loader2 className="h-10 w-10 animate-spin text-amber-500" />
              </div>
              <p className="mt-4 text-sm font-medium text-amber-400">Processing & Summarizing...</p>
              <p className="text-xs text-white/30 mt-1">This may take a moment for large documents</p>
            </>
          ) : (
            <>
              <div className="flex items-center justify-center w-14 h-14 rounded-2xl mb-4" style={{ background: 'rgba(245,158,11,0.1)' }}>
                <Upload className="h-7 w-7 text-amber-500" />
              </div>
              <p className="text-sm font-medium text-white">Upload Document to Summarize</p>
              <p className="text-xs text-white/30 mt-1">PDF, DOCX, XLSX, CSV, PPTX, TXT (Max 50 MB)</p>
              <Button
                size="sm"
                className="mt-4 text-xs gap-2"
                style={{ background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', color: '#fff' }}
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
              >
                <Upload className="h-3.5 w-3.5" />
                Choose File
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Search & Refresh */}
      {summaries.length > 0 && (
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
            <Input
              placeholder="Search summaries..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 bg-white/[0.03] border-white/[0.08] text-white placeholder:text-white/30"
            />
          </div>
          <Button
            variant="outline"
            size="icon"
            className="h-10 w-10 border-white/[0.08] text-white/50 hover:text-white"
            onClick={fetchSummaries}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-amber-500/60" />
          <p className="mt-3 text-sm text-white/40">Loading summaries...</p>
        </div>
      ) : summaries.length === 0 && !uploading ? (
        <div className="flex flex-col items-center justify-center py-16 rounded-2xl border border-white/[0.06]" style={{ background: 'rgba(0,0,0,0.1)' }}>
          <Sparkles className="h-10 w-10 text-white/10 mb-3" />
          <p className="text-white/40 text-sm">No summaries yet</p>
          <p className="text-white/25 text-xs mt-1">Upload a document above to generate your first summary</p>
        </div>
      ) : (
        /* Summaries List */
        <div className="space-y-3">
          <AnimatePresence>
            {summaries.map((s) => {
              const fc = getFileConfig(s.file_type);
              const FIcon = fc.icon;
              const isExpanded = expandedId === s.id;

              return (
                <motion.div
                  key={s.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="rounded-xl border border-white/[0.06] overflow-hidden"
                  style={{ background: 'rgba(0,0,0,0.2)' }}
                >
                  {/* Summary Row */}
                  <div className="flex items-center gap-4 p-4">
                    {/* File Icon */}
                    <div
                      className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0"
                      style={{ backgroundColor: `${fc.color}15` }}
                    >
                      <FIcon className="h-5 w-5" style={{ color: fc.color }} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-white truncate">{s.original_filename}</p>
                      <div className="flex items-center gap-3 mt-1 text-[11px] text-white/30 flex-wrap">
                        <span className="flex items-center gap-1">
                          <BookOpen className="h-3 w-3" /> {s.page_count} pages
                        </span>
                        <span>{formatFileSize(s.file_size)}</span>
                        <span>{s.word_count?.toLocaleString()} words</span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" /> {formatDate(s.created_at)}
                        </span>
                        {s.created_by && (
                          <span className="flex items-center gap-1">
                            <User className="h-3 w-3" /> {s.created_by}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-3 text-xs text-white/50 hover:text-amber-400 hover:bg-amber-500/10 gap-1.5 rounded-lg"
                        onClick={() => setExpandedId(isExpanded ? null : s.id)}
                      >
                        {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                        {isExpanded ? 'Hide' : 'View'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-lg text-white/40 hover:text-red-400 hover:bg-red-500/10"
                        onClick={() => handleDelete(s.id)}
                        disabled={deletingId === s.id}
                      >
                        {deletingId === s.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  </div>

                  {/* Expanded Summary Content */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25 }}
                        className="overflow-hidden"
                      >
                        <div className="border-t border-white/[0.06] px-5 py-5 space-y-4">
                          {/* Rich Markdown Summary */}
                          <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
                            <MarkdownSummary content={s.rich_summary} />
                          </div>

                          {/* Key Findings (separate card if available) */}
                          {s.key_findings && s.key_findings.length > 0 && (
                            <div className="rounded-xl border border-amber-500/10 p-4" style={{ background: 'rgba(245,158,11,0.04)' }}>
                              <div className="flex items-center gap-2 mb-3">
                                <Lightbulb className="h-4 w-4 text-amber-400" />
                                <h4 className="text-sm font-semibold text-white">Key Findings</h4>
                                <span className="text-[10px] text-white/30 ml-auto">{s.key_findings.length} findings</span>
                              </div>
                              <div className="space-y-2">
                                {s.key_findings.map((finding, i) => (
                                  <div key={i} className="flex items-start gap-2.5 p-2 rounded-lg border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                                    <div className="h-5 w-5 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background: 'rgba(245,158,11,0.12)' }}>
                                      <span className="text-[10px] font-bold text-amber-400">{i + 1}</span>
                                    </div>
                                    <p className="text-xs text-white/50 leading-relaxed">{finding}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Action Items */}
                          {s.action_items && s.action_items.length > 0 && (
                            <div className="rounded-xl border border-emerald-500/10 p-4" style={{ background: 'rgba(16,185,129,0.04)' }}>
                              <div className="flex items-center gap-2 mb-3">
                                <ListChecks className="h-4 w-4 text-emerald-400" />
                                <h4 className="text-sm font-semibold text-white">Action Items</h4>
                                <span className="text-[10px] text-white/30 ml-auto">{s.action_items.length} items</span>
                              </div>
                              <div className="space-y-1.5">
                                {s.action_items.map((item, i) => (
                                  <div key={i} className="flex items-start gap-2 text-xs text-white/50">
                                    <ArrowRight className="h-3 w-3 text-emerald-400 mt-0.5 shrink-0" />
                                    <span>{item}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
};

export default SummarizationInsights;
