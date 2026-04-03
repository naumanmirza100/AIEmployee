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
                <pre className="text-sm text-white/40 whitespace-pre-wrap font-mono leading-relaxed">{document.parsed_text}</pre>
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
