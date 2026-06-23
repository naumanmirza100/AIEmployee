import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Loader2, ArrowLeft,
  FileSpreadsheet, FileType, Presentation, File,
  Tag, Hash, User, Calendar, BarChart3,
  CheckCircle2, Layers, BookOpen,
  Lightbulb, Brain, Sparkles, Zap, Info,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import * as operationsService from '@/services/operationsAgentService';

// ─── Markdown components for the Content tab ─────────────────────────
// Plain extracted text from PDFs / DOCX is converted into markdown by
// `plainTextToMarkdown` below, then rendered with these styled blocks
// so resumes / contracts / manuals show clear headings and lists instead
// of a wall of monospace text.
const contentMarkdownComponents = {
  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-white mt-6 mb-3 pb-2 border-b border-white/[0.08]">{children}</h1>
  ),
  h2: ({ children }) => (
    <div className="flex items-center gap-2.5 mt-6 mb-3 pb-2 border-b border-white/[0.06]">
      <div className="h-5 w-1 rounded-full bg-amber-500" />
      <h2 className="text-base font-bold text-amber-400 m-0">{children}</h2>
    </div>
  ),
  h3: ({ children }) => (
    <div className="flex items-center gap-2 mt-5 mb-2">
      <div className="h-1.5 w-1.5 rounded-full bg-violet-400" />
      <h3 className="text-sm font-semibold text-violet-300 m-0">{children}</h3>
    </div>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-white/80 mt-4 mb-2">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="text-sm text-white/65 leading-relaxed my-2">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="space-y-1.5 my-3 ml-1 list-none p-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="space-y-1.5 my-3 ml-1 list-none p-0">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="flex items-start gap-2.5 text-sm text-white/65 leading-relaxed p-0 m-0">
      <span className="flex items-center justify-center h-4 w-4 rounded-full shrink-0 mt-1 text-[9px] font-bold"
        style={{ background: 'rgba(245,158,11,0.12)', color: '#f59e0b' }}
      >•</span>
      <span className="flex-1">{children}</span>
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-white/90">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="text-white/70">{children}</em>
  ),
  a: ({ children, href }) => (
    <a href={href} className="text-amber-400 underline underline-offset-2 break-all" target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  hr: () => <hr className="my-6 border-white/[0.08]" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-white/20 pl-3 my-3 text-sm text-white/55 italic">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-white/[0.06]">
      <table className="w-full text-xs text-white/65">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-semibold text-white/80 border-b border-white/[0.06] bg-white/[0.02]">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 border-b border-white/[0.04]">{children}</td>
  ),
};

// Small connector words that don't need to be capitalised for a line to count
// as "title-case" (so "Education and Experience" still counts as a heading).
const TITLE_CASE_SMALL_WORDS = new Set([
  'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into', 'of',
  'on', 'or', 'the', 'to', 'with', 'vs', 'via', 'per',
]);

const isTitleCaseLine = (line) => {
  const words = line.split(/\s+/).filter(Boolean);
  if (words.length < 1) return false;
  let capCount = 0;
  for (const w of words) {
    const clean = w.replace(/[^A-Za-z0-9]/g, '');
    if (!clean) continue;
    const first = clean[0];
    if (first >= 'A' && first <= 'Z') capCount += 1;
    else if (!TITLE_CASE_SMALL_WORDS.has(clean.toLowerCase()) && /[a-z]/.test(first)) return false;
  }
  return capCount >= 1;
};

// Convert raw extracted document text into structured markdown.
//   ALL-CAPS short lines       → ## heading
//   Title-Case standalone lines → ## heading (when followed by content)
//   "1. Foo" / "1.1 Foo"        → ### numbered heading (when short + title-case)
//   Short lines ending in ":"   → ### heading
//   •, ●, ○, *, -, ▪ prefixes   → unordered list
//   "1." / "1)" prefixes in body → ordered list
//   Form-feed / explicit page break → horizontal rule
// Falls through to plain paragraphs for everything else, and escapes any
// stray markdown special chars so resume bullet points like "C++" aren't
// rendered as code.
const escapeMarkdown = (s) => s.replace(/([\\`*_{}\[\]()<>#+!|])/g, '\\$1');

const plainTextToMarkdown = (raw) => {
  if (!raw) return '';
  // Normalise newlines, page breaks → ---
  const text = raw
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\f/g, '\n\n---\n\n');

  const lines = text.split('\n').map(l => l.replace(/\s+$/, ''));
  const out = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    const nextNonEmpty = lines.slice(i + 1).find(l => l.trim()) || '';

    if (!line) {
      out.push('');
      continue;
    }

    // Already a horizontal rule we injected
    if (line === '---') { out.push('---'); continue; }

    // 1) Bullet list items
    const bulletMatch = line.match(/^[•●○▪■▶►·⁃\-\*]\s+(.+)/);
    if (bulletMatch) {
      out.push(`- ${escapeMarkdown(bulletMatch[1])}`);
      continue;
    }

    // 2) Numbered "1.", "1)" — could be heading or list item
    const numberedMatch = line.match(/^(\d{1,3})[.)]\s+(.+)$/);
    if (numberedMatch) {
      const content = numberedMatch[2];
      const wordCount = content.split(/\s+/).length;
      const looksLikeHeading =
        content.length <= 70 &&
        wordCount <= 10 &&
        !/[.!?]$/.test(content) &&
        isTitleCaseLine(content);
      if (looksLikeHeading) {
        out.push(`### ${numberedMatch[1]}. ${escapeMarkdown(content)}`);
      } else {
        out.push(`${numberedMatch[1]}. ${escapeMarkdown(content)}`);
      }
      continue;
    }

    // 3) Dotted numeric headings: "1.1 Foo", "1.1.1 Foo"
    const dottedNumMatch = line.match(/^(\d+(?:\.\d+){1,3})\s+(.+)$/);
    if (dottedNumMatch && dottedNumMatch[2].length <= 80) {
      out.push(`### ${dottedNumMatch[1]} ${escapeMarkdown(dottedNumMatch[2])}`);
      continue;
    }

    // 4) ALL-CAPS heading: ≥3 letters, no terminal sentence punctuation, ≤ 80 chars
    const letters = line.replace(/[^A-Za-z]/g, '');
    if (
      letters.length >= 3 &&
      letters === letters.toUpperCase() &&
      line.length <= 80 &&
      !/[.!?]$/.test(line)
    ) {
      // Title-case it for nicer display while keeping acronyms intact:
      // here we just keep ALL CAPS — markdown rendering already styles it.
      out.push(`## ${escapeMarkdown(line)}`);
      continue;
    }

    // 5) Short line ending with `:` → subheading
    if (/:$/.test(line) && line.length <= 60 && line.split(/\s+/).length <= 8) {
      out.push(`### ${escapeMarkdown(line.replace(/:\s*$/, ''))}`);
      continue;
    }

    // 6) Title-Case standalone short line that is followed by a blank line
    //    (i.e. ends a section break) → heading. Requiring the immediate next
    //    line to be empty avoids classifying body-text Title-Case lines like
    //    "Bachelor of Computer Science\nUniversity of …" as headings.
    const immediateNext = (lines[i + 1] || '').trim();
    if (
      line.length <= 70 &&
      line.split(/\s+/).length <= 10 &&
      !/[.!?,;:]$/.test(line) &&
      isTitleCaseLine(line) &&
      immediateNext === '' &&
      nextNonEmpty
    ) {
      out.push(`## ${escapeMarkdown(line)}`);
      continue;
    }

    // 7) Default — plain paragraph (escape markdown specials)
    out.push(escapeMarkdown(line));
  }

  // Collapse 3+ blank lines to a single paragraph break
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};

// ─── Helpers ────────────────────────────────
const FILE_TYPE_CONFIG = {
  pdf:  { icon: FileText,        color: '#ef4444', bg: 'rgba(239,68,68,0.12)', label: 'PDF' },
  docx: { icon: FileType,        color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', label: 'DOCX' },
  xlsx: { icon: FileSpreadsheet, color: '#10b981', bg: 'rgba(16,185,129,0.12)', label: 'XLSX' },
  csv:  { icon: FileSpreadsheet, color: '#14b8a6', bg: 'rgba(20,184,166,0.12)', label: 'CSV' },
  pptx: { icon: Presentation,    color: '#f97316', bg: 'rgba(249,115,22,0.12)', label: 'PPTX' },
  txt:  { icon: FileText,        color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: 'TXT' },
};
const getFileConfig = (type) => FILE_TYPE_CONFIG[type] || { icon: File, color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: type?.toUpperCase() || 'FILE' };

const DOC_TYPE_COLORS = {
  report: '#3b82f6', invoice: '#10b981', contract: '#f59e0b', memo: '#8b5cf6',
  spreadsheet: '#14b8a6', presentation: '#f97316', policy: '#ef4444', manual: '#6366f1', other: '#6b7280',
};

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

const formatDateTime = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const DocumentDetailPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const id = (location.pathname.match(/\/operations\/documents\/(\d+)/) || [])[1];
  const { toast } = useToast();

  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailTab, setDetailTab] = useState('summary');

  const fetchDocument = useCallback(async () => {
    try {
      setLoading(true);
      const res = await operationsService.getDocument(id);
      if (res.status === 'success') {
        setDocument(res.document);
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to load document details', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => { fetchDocument(); }, [fetchDocument]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <Loader2 className="h-10 w-10 animate-spin text-amber-500/60" />
        <p className="mt-4 text-sm text-white/40">Loading document details...</p>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <FileText className="h-12 w-12 text-white/15 mb-4" />
        <p className="text-white/40 text-sm">Document not found</p>
        <Button
          variant="ghost"
          className="mt-4 text-amber-400 hover:text-amber-300"
          onClick={() => navigate('/operations/documents')}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Documents
        </Button>
      </div>
    );
  }

  const fc = getFileConfig(document.file_type);
  const FI = fc.icon;

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Button
        variant="ghost"
        className="text-white/50 hover:text-white gap-2 -ml-2"
        onClick={() => navigate('/operations/documents')}
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Documents
      </Button>

      {/* Header Card */}
      <div className="rounded-2xl border border-white/[0.06] p-6" style={{ background: 'rgba(0,0,0,0.25)' }}>
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl shrink-0" style={{ backgroundColor: fc.bg }}>
            <FI className="h-8 w-8" style={{ color: fc.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-1 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-white">{document.title}</h1>
              {document.is_processed && (
                <span className="flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full text-emerald-400 border border-emerald-400/20" style={{ background: 'rgba(16,185,129,0.08)' }}>
                  <CheckCircle2 className="h-3 w-3" /> Processed
                </span>
              )}
            </div>
            <p className="text-sm text-white/35">{document.original_filename}</p>
          </div>
        </div>

        {/* Quick Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-6">
          {[
            { label: 'Type', value: document.document_type, icon: Tag, color: DOC_TYPE_COLORS[document.document_type] || '#6b7280' },
            { label: 'Format', value: document.file_type?.toUpperCase(), icon: File, color: getFileConfig(document.file_type).color },
            { label: 'Size', value: formatFileSize(document.file_size), icon: Hash, color: '#8b5cf6' },
            { label: 'Pages', value: document.page_count || 'N/A', icon: BookOpen, color: '#3b82f6' },
            { label: 'Chunks', value: document.chunks_count || 0, icon: Layers, color: '#14b8a6' },
            { label: 'Uploaded', value: formatDate(document.created_at), icon: Calendar, color: '#f59e0b' },
          ].map((m, i) => (
            <div key={i} className="flex items-center gap-2.5 p-3 rounded-xl border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
              <m.icon className="h-4 w-4 shrink-0" style={{ color: `${m.color}80` }} />
              <div className="min-w-0">
                <p className="text-[10px] text-white/30 uppercase tracking-wider">{m.label}</p>
                <p className="text-sm text-white font-semibold truncate capitalize">{m.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabbed Content */}
      <Tabs value={detailTab} onValueChange={setDetailTab}>
        <TabsList className="h-10 p-1 rounded-xl w-full sm:w-auto justify-start gap-1 bg-[#1a1333] border border-[#3a295a]">
          {[
            { value: 'summary', label: 'Summary', icon: Sparkles },
            { value: 'entities', label: 'Entities', icon: Brain },
            { value: 'content', label: 'Content', icon: FileText },
          ].map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="text-sm rounded-lg px-4 gap-2 data-[state=active]:bg-amber-500/20 data-[state=active]:text-amber-300 text-white/40 data-[state=active]:shadow-none"
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Summary Tab */}
        <TabsContent value="summary" className="mt-6 space-y-4">
          {document.summary ? (
            <div className="rounded-xl border border-amber-500/10 p-5" style={{ background: 'rgba(245,158,11,0.04)' }}>
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-amber-400" />
                <h4 className="text-sm font-semibold text-white">AI Summary</h4>
              </div>
              <p className="text-sm text-white/60 leading-relaxed">{document.summary}</p>
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.06] p-6 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <Info className="h-5 w-5 text-white/20 mx-auto mb-2" />
              <p className="text-xs text-white/30">No summary available. Re-upload the document to generate an AI summary.</p>
            </div>
          )}

          {document.key_insights && document.key_insights.length > 0 && (
            <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb className="h-4 w-4 text-amber-400" />
                <h4 className="text-sm font-semibold text-white">Key Insights</h4>
                <span className="text-[10px] text-white/30 ml-auto">{document.key_insights.length} findings</span>
              </div>
              <div className="space-y-2">
                {document.key_insights.map((insight, i) => (
                  <div key={i} className="flex items-start gap-2.5 p-3 rounded-lg border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <div className="h-5 w-5 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background: 'rgba(245,158,11,0.12)' }}>
                      <span className="text-[10px] font-bold text-amber-400">{i + 1}</span>
                    </div>
                    <p className="text-xs text-white/50 leading-relaxed">{insight}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
            <div className="flex items-center gap-2 mb-3">
              <Zap className="h-4 w-4 text-emerald-400" />
              <h4 className="text-sm font-semibold text-white">Processing Details</h4>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Word Count', value: document.metadata?.word_count?.toLocaleString() || 'N/A' },
                { label: 'Character Count', value: document.metadata?.char_count?.toLocaleString() || 'N/A' },
                { label: 'Text Chunks', value: document.chunks_count || 0 },
                { label: 'Processed At', value: document.processed_at ? formatDateTime(document.processed_at) : 'N/A' },
              ].map((item, i) => (
                <div key={i} className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <p className="text-[10px] text-white/30 uppercase tracking-wider mb-1">{item.label}</p>
                  <p className="text-sm text-white/70 font-medium">{item.value}</p>
                </div>
              ))}
            </div>
          </div>

          {document.tags && (
            <div className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <div className="flex items-center gap-2 mb-3">
                <Tag className="h-4 w-4 text-violet-400" />
                <h4 className="text-sm font-semibold text-white">Tags</h4>
              </div>
              <div className="flex flex-wrap gap-2">
                {document.tags.split(',').map((tag, i) => (
                  <span
                    key={i}
                    className="text-xs px-3 py-1 rounded-full text-violet-300 border border-violet-400/20"
                    style={{ background: 'rgba(139,92,246,0.08)' }}
                  >
                    {tag.trim()}
                  </span>
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        {/* Entities Tab */}
        <TabsContent value="entities" className="mt-6 space-y-4">
          {document.entities && Object.keys(document.entities).length > 0 ? (
            Object.entries(document.entities).map(([key, values]) => {
              if (!Array.isArray(values) || values.length === 0) return null;
              const colorMap = {
                dates: '#f59e0b', amounts: '#10b981', names: '#3b82f6',
                organizations: '#8b5cf6', key_terms: '#ec4899',
              };
              const iconMap = {
                dates: Calendar, amounts: Hash, names: User,
                organizations: BarChart3, key_terms: Brain,
              };
              const EntityIcon = iconMap[key] || Tag;
              const entityColor = colorMap[key] || '#6b7280';
              return (
                <div key={key} className="rounded-xl border border-white/[0.06] p-5" style={{ background: 'rgba(0,0,0,0.15)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <EntityIcon className="h-4 w-4" style={{ color: entityColor }} />
                    <h4 className="text-sm font-semibold text-white capitalize">{key.replace(/_/g, ' ')}</h4>
                    <span className="text-[10px] text-white/25 ml-auto">{values.length} found</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {values.map((v, i) => (
                      <span
                        key={i}
                        className="text-xs px-2.5 py-1 rounded-full border"
                        style={{ borderColor: `${entityColor}25`, color: `${entityColor}cc`, background: `${entityColor}0a` }}
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-xl border border-white/[0.06] p-10 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <Brain className="h-8 w-8 text-white/15 mx-auto mb-3" />
              <p className="text-sm text-white/30">No entities were extracted from this document.</p>
              <p className="text-xs text-white/20 mt-1">Entity extraction works best with text-rich documents.</p>
            </div>
          )}
        </TabsContent>

        {/* Content Tab */}
        <TabsContent value="content" className="mt-6 space-y-4">
          {document.parsed_text ? (
            <div className="rounded-xl border border-white/[0.06] overflow-hidden" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-white/30" />
                  <h4 className="text-xs font-semibold text-white/60">Extracted Content</h4>
                </div>
                <span className="text-[10px] text-white/25">{document.full_text_length?.toLocaleString() || 0} characters total</span>
              </div>
              <div className="p-5 max-h-[600px] overflow-y-auto">
                <div className="prose-content">
                  <ReactMarkdown components={contentMarkdownComponents}>
                    {plainTextToMarkdown(document.parsed_text)}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-white/[0.06] p-10 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
              <FileText className="h-8 w-8 text-white/15 mx-auto mb-3" />
              <p className="text-sm text-white/30">No content preview available for this document.</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DocumentDetailPage;
