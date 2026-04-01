import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Search, Upload, Loader2, Trash2, Eye, X,
  FileSpreadsheet, FileType, Presentation, File,
  Tag, Hash, User, Calendar, BarChart3, RefreshCw,
  CheckCircle2, AlertCircle, Clock, Layers, BookOpen,
  Lightbulb, Brain, ChevronRight, Download, Sparkles,
  FileCheck, Zap, ArrowRight, Info,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
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

// ─── Animation Variants ─────────────────────
const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

// ─── Stat Card ──────────────────────────────
const StatCard = ({ icon: Icon, label, value, color, sub }) => (
  <motion.div
    variants={itemVariants}
    className="relative rounded-xl border border-white/[0.06] p-4 overflow-hidden"
    style={{ background: 'rgba(0,0,0,0.2)' }}
  >
    <div className="absolute top-0 left-0 w-1 h-full rounded-full" style={{ background: color }} />
    <div className="flex items-center gap-3 pl-2">
      <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${color}18` }}>
        <Icon className="h-4.5 w-4.5" style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] text-white/40 uppercase tracking-wider font-medium">{label}</p>
        <p className="text-lg font-bold text-white leading-tight">{value}</p>
        {sub && <p className="text-[10px] text-white/30 mt-0.5">{sub}</p>}
      </div>
    </div>
  </motion.div>
);

// ═════════════════════════════════════════════
const DocumentProcessing = () => {
  const { toast } = useToast();

  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Upload
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadTags, setUploadTags] = useState('');
  const [uploading, setUploading] = useState(false);

  // Detail
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailTab, setDetailTab] = useState('summary');

  // Delete
  const [deletingId, setDeletingId] = useState(null);

  // ─── Fetch ────────────────────────────────
  const fetchDocuments = useCallback(async () => {
    try {
      setDocsLoading(true);
      const params = {};
      if (searchQuery) params.search = searchQuery;
      const res = await operationsService.listDocuments(params);
      if (res.status === 'success') setDocuments(res.documents || []);
    } catch (e) {
      console.error('Documents fetch error:', e);
    } finally {
      setDocsLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  // ─── Upload ───────────────────────────────
  const handleUpload = async () => {
    if (!uploadFile) {
      toast({ title: 'Error', description: 'Please select a file', variant: 'destructive' });
      return;
    }
    try {
      setUploading(true);
      const res = await operationsService.uploadDocument(uploadFile, uploadTitle, uploadTags);
      toast({ title: 'Document Processed', description: `"${res.document?.title || uploadFile.name}" uploaded and analyzed successfully` });
      setShowUpload(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadTags('');
      fetchDocuments();
    } catch (e) {
      toast({ title: 'Upload Failed', description: e.message || 'Something went wrong', variant: 'destructive' });
    } finally {
      setUploading(false);
    }
  };

  // ─── Detail ───────────────────────────────
  const openDetail = async (docId) => {
    try {
      setDetailLoading(true);
      setSelectedDoc(null);
      setDetailTab('summary');
      const res = await operationsService.getDocument(docId);
      if (res.status === 'success') setSelectedDoc(res.document);
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to load document details', variant: 'destructive' });
    } finally {
      setDetailLoading(false);
    }
  };

  // ─── Delete ───────────────────────────────
  const handleDelete = async (docId) => {
    try {
      setDeletingId(docId);
      await operationsService.deleteDocument(docId);
      toast({ title: 'Deleted', description: 'Document deleted successfully' });
      fetchDocuments();
      if (selectedDoc?.id === docId) setSelectedDoc(null);
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to delete', variant: 'destructive' });
    } finally {
      setDeletingId(null);
    }
  };

  // ─── Computed stats ───────────────────────
  const totalDocs = documents.length;
  const processedDocs = documents.filter(d => d.is_processed).length;
  const totalPages = documents.reduce((sum, d) => sum + (d.page_count || 0), 0);
  const totalSize = documents.reduce((sum, d) => sum + (d.file_size || 0), 0);

  // ═══ RENDER ═══════════════════════════════
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-5"
    >
      {/* ── Toolbar ── */}
      <motion.div variants={itemVariants} className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
          <Input
            className="pl-10 h-10 rounded-xl text-sm text-white placeholder:text-white/30 border-white/[0.08] focus:border-amber-500/40"
            style={{ background: 'rgba(0,0,0,0.25)' }}
            placeholder="Search documents by title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={fetchDocuments}
          className="h-10 w-10 rounded-xl border-white/[0.08] text-white/40 hover:text-white hover:border-white/20"
          style={{ background: 'rgba(0,0,0,0.25)' }}
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button
          onClick={() => setShowUpload(true)}
          className="h-10 rounded-xl px-5 text-sm font-medium border-0"
          style={{
            background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
            color: '#fff',
            boxShadow: '0 0 20px rgba(245,158,11,0.25)',
          }}
        >
          <Upload className="mr-2 h-4 w-4" />
          Upload Document
        </Button>
      </motion.div>

      {/* ── Documents List ── */}
      {docsLoading ? (
        <motion.div variants={itemVariants} className="flex flex-col items-center justify-center py-20">
          <Loader2 className="h-10 w-10 animate-spin text-amber-500/60" />
          <p className="mt-4 text-sm text-white/40">Loading documents...</p>
        </motion.div>
      ) : documents.length === 0 ? (
        <motion.div variants={itemVariants}>
          <Card className="border-dashed border-white/[0.08]" style={{ background: 'rgba(0,0,0,0.15)' }}>
            <CardContent className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-5" style={{ background: 'rgba(245,158,11,0.1)' }}>
                <Upload className="h-10 w-10 text-amber-500/60" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">No documents yet</h3>
              <p className="text-white/40 mb-6 max-w-sm text-sm">
                Upload your first document to get started. We support PDF, DOCX, Excel, PowerPoint, CSV, and text files.
              </p>
              <Button
                onClick={() => setShowUpload(true)}
                className="rounded-xl border-0"
                style={{ background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)', color: '#fff' }}
              >
                <Upload className="mr-2 h-4 w-4" />Upload Document
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      ) : (
        <motion.div variants={containerVariants} className="space-y-2.5">
          <AnimatePresence>
            {documents.map((doc, index) => {
              const fc = getFileConfig(doc.file_type);
              const FileIcon = fc.icon;
              const dtColor = DOC_TYPE_COLORS[doc.document_type] || '#6b7280';
              const hasSummary = !!(doc.summary);
              return (
                <motion.div
                  key={doc.id}
                  variants={itemVariants}
                  layout
                  className="group relative rounded-xl border border-white/[0.06] overflow-hidden transition-all duration-200 hover:border-white/[0.12]"
                  style={{ background: 'rgba(0,0,0,0.2)' }}
                >
                  {/* Processing status indicator line */}
                  <div
                    className="absolute top-0 left-0 w-full h-[2px]"
                    style={{ background: doc.is_processed ? `linear-gradient(90deg, ${fc.color}, transparent)` : 'linear-gradient(90deg, #ef4444, transparent)' }}
                  />

                  <div className="p-4 flex items-start gap-4">
                    {/* File type icon */}
                    <div
                      className="flex items-center justify-center w-12 h-12 rounded-xl shrink-0 mt-0.5"
                      style={{ backgroundColor: fc.bg }}
                    >
                      <FileIcon className="h-6 w-6" style={{ color: fc.color }} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <h4 className="text-sm font-semibold text-white truncate max-w-[300px]">{doc.title}</h4>
                        <Badge
                          variant="outline"
                          className="text-[10px] px-2 py-0 rounded-full capitalize shrink-0"
                          style={{ borderColor: `${dtColor}50`, color: dtColor, background: `${dtColor}12` }}
                        >
                          {doc.document_type}
                        </Badge>
                        {doc.is_processed ? (
                          <span className="flex items-center gap-1 text-[10px] text-emerald-400/80">
                            <CheckCircle2 className="h-3 w-3" /> Processed
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[10px] text-amber-400/80">
                            <Clock className="h-3 w-3" /> Pending
                          </span>
                        )}
                      </div>

                      {/* Summary preview */}
                      {hasSummary && (
                        <p className="text-xs text-white/35 line-clamp-2 mb-2 leading-relaxed max-w-xl">
                          {doc.summary}
                        </p>
                      )}

                      {/* Meta row */}
                      <div className="flex items-center gap-4 text-[11px] text-white/30 flex-wrap">
                        <span className="flex items-center gap-1">
                          <File className="h-3 w-3" />
                          {fc.label} &middot; {formatFileSize(doc.file_size)}
                        </span>
                        {doc.page_count > 0 && (
                          <span className="flex items-center gap-1">
                            <BookOpen className="h-3 w-3" />{doc.page_count} pages
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />{formatDate(doc.created_at)}
                        </span>
                        {doc.uploaded_by && (
                          <span className="hidden sm:flex items-center gap-1">
                            <User className="h-3 w-3" />{doc.uploaded_by}
                          </span>
                        )}
                        {doc.tags && (
                          <span className="flex items-center gap-1">
                            <Tag className="h-3 w-3" />{doc.tags.split(',').length} tags
                          </span>
                        )}
                      </div>

                      {/* Tags inline */}
                      {doc.tags && (
                        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                          {doc.tags.split(',').slice(0, 4).map((t, i) => (
                            <span
                              key={i}
                              className="text-[10px] px-2 py-0.5 rounded-full text-white/50 border border-white/[0.06]"
                              style={{ background: 'rgba(255,255,255,0.03)' }}
                            >
                              {t.trim()}
                            </span>
                          ))}
                          {doc.tags.split(',').length > 4 && (
                            <span className="text-[10px] text-white/25">+{doc.tags.split(',').length - 4} more</span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0 opacity-40 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-3 rounded-lg text-white/60 hover:text-amber-400 hover:bg-amber-500/10 gap-1.5 text-xs"
                        onClick={() => openDetail(doc.id)}
                      >
                        <Eye className="h-3.5 w-3.5" />
                        View
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-lg text-white/40 hover:text-red-400 hover:bg-red-500/10"
                        onClick={() => handleDelete(doc.id)}
                        disabled={deletingId === doc.id}
                      >
                        {deletingId === doc.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </motion.div>
      )}

      {/* ═══ Upload Dialog ═══ */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent className="sm:max-w-md border-white/[0.08] text-white" style={{ background: '#0c0816' }}>
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Upload className="h-5 w-5 text-amber-500" />
              Upload & Process Document
            </DialogTitle>
            <DialogDescription className="text-white/40">
              Upload a file and our AI will automatically extract text, classify the document, identify entities, and generate a summary.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-2">
            {/* Processing steps indicator */}
            <div className="rounded-xl border border-white/[0.06] p-3" style={{ background: 'rgba(245,158,11,0.05)' }}>
              <p className="text-[11px] text-amber-400/80 font-medium mb-2 flex items-center gap-1.5">
                <Zap className="h-3.5 w-3.5" /> AI Processing Pipeline
              </p>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'Text Extraction', icon: FileText },
                  { label: 'Auto-Classification', icon: Brain },
                  { label: 'Entity Detection', icon: Search },
                  { label: 'Summary Generation', icon: Sparkles },
                ].map((step, i) => (
                  <div key={i} className="flex items-center gap-2 text-[10px] text-white/35">
                    <step.icon className="h-3 w-3 text-amber-500/50" />
                    {step.label}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-white/60 text-xs">File</Label>
              <Input
                type="file"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.pptx,.txt,.md"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="h-10 rounded-xl border-white/[0.08] text-white file:text-amber-400 file:bg-transparent file:border-0 file:font-medium cursor-pointer"
                style={{ background: 'rgba(0,0,0,0.3)' }}
              />
              {uploadFile && (
                <div className="flex items-center gap-2 text-xs text-white/40 px-1">
                  <FileCheck className="h-3 w-3 text-emerald-400" />
                  {uploadFile.name} ({formatFileSize(uploadFile.size)})
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label className="text-white/60 text-xs">Title (optional)</Label>
              <Input
                placeholder="Document title"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
                className="h-10 rounded-xl border-white/[0.08] text-white placeholder:text-white/20"
                style={{ background: 'rgba(0,0,0,0.3)' }}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-white/60 text-xs">Tags (optional, comma-separated)</Label>
              <Input
                placeholder="finance, Q1, report"
                value={uploadTags}
                onChange={(e) => setUploadTags(e.target.value)}
                className="h-10 rounded-xl border-white/[0.08] text-white placeholder:text-white/20"
                style={{ background: 'rgba(0,0,0,0.3)' }}
              />
            </div>

            {/* Supported formats */}
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(FILE_TYPE_CONFIG).map(([ext, cfg]) => (
                <span
                  key={ext}
                  className="text-[10px] px-2 py-0.5 rounded-full border"
                  style={{ borderColor: `${cfg.color}30`, color: `${cfg.color}90`, background: `${cfg.color}08` }}
                >
                  .{ext}
                </span>
              ))}
            </div>
          </div>

          <DialogFooter className="gap-2 mt-2">
            <Button
              variant="outline"
              onClick={() => setShowUpload(false)}
              className="rounded-xl border-white/[0.08] text-white/60 hover:text-white"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={uploading || !uploadFile}
              className="rounded-xl border-0"
              style={{
                background: uploading ? 'rgba(245,158,11,0.3)' : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                color: '#fff',
              }}
            >
              {uploading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Processing...</>
              ) : (
                <><Sparkles className="mr-2 h-4 w-4" />Upload & Analyze</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Detail Dialog ═══ */}
      <Dialog open={!!selectedDoc || detailLoading} onOpenChange={(open) => { if (!open) setSelectedDoc(null); }}>
        <DialogContent className="sm:max-w-3xl max-h-[88vh] overflow-hidden border-white/[0.08] text-white p-0" style={{ background: '#0c0816' }}>
          {detailLoading ? (
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="h-10 w-10 animate-spin text-amber-500/60" />
              <p className="mt-4 text-sm text-white/40">Loading document details...</p>
            </div>
          ) : selectedDoc && (
            <div className="flex flex-col h-full max-h-[88vh]">
              {/* Header */}
              <div className="shrink-0 px-6 pt-6 pb-4 border-b border-white/[0.06]">
                <div className="flex items-start gap-4">
                  {(() => {
                    const fc = getFileConfig(selectedDoc.file_type);
                    const FI = fc.icon;
                    return (
                      <div className="flex items-center justify-center w-14 h-14 rounded-2xl shrink-0" style={{ backgroundColor: fc.bg }}>
                        <FI className="h-7 w-7" style={{ color: fc.color }} />
                      </div>
                    );
                  })()}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <h2 className="text-lg font-bold text-white truncate">{selectedDoc.title}</h2>
                      {selectedDoc.is_processed && (
                        <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full text-emerald-400 border border-emerald-400/20" style={{ background: 'rgba(16,185,129,0.08)' }}>
                          <CheckCircle2 className="h-3 w-3" /> Processed
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-white/35">{selectedDoc.original_filename}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 rounded-lg text-white/40 hover:text-white shrink-0"
                    onClick={() => setSelectedDoc(null)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {/* Quick Stats Row */}
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mt-4">
                  {[
                    { label: 'Type', value: selectedDoc.document_type, icon: Tag, color: DOC_TYPE_COLORS[selectedDoc.document_type] || '#6b7280' },
                    { label: 'Format', value: selectedDoc.file_type?.toUpperCase(), icon: File, color: getFileConfig(selectedDoc.file_type).color },
                    { label: 'Size', value: formatFileSize(selectedDoc.file_size), icon: Hash, color: '#8b5cf6' },
                    { label: 'Pages', value: selectedDoc.page_count || 'N/A', icon: BookOpen, color: '#3b82f6' },
                    { label: 'Chunks', value: selectedDoc.chunks_count || 0, icon: Layers, color: '#14b8a6' },
                    { label: 'Uploaded', value: formatDate(selectedDoc.created_at), icon: Calendar, color: '#f59e0b' },
                  ].map((m, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded-lg border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <m.icon className="h-3.5 w-3.5 shrink-0" style={{ color: `${m.color}80` }} />
                      <div className="min-w-0">
                        <p className="text-[9px] text-white/30 uppercase tracking-wider">{m.label}</p>
                        <p className="text-xs text-white font-semibold truncate capitalize">{m.value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tabbed Content */}
              <div className="flex-1 overflow-y-auto">
                <Tabs value={detailTab} onValueChange={setDetailTab} className="h-full">
                  <div className="sticky top-0 z-10 px-6 pt-3 pb-0" style={{ background: '#0c0816' }}>
                    <TabsList className="h-9 p-0.5 rounded-lg w-full justify-start gap-0.5" style={{ background: 'rgba(255,255,255,0.04)' }}>
                      {[
                        { value: 'summary', label: 'Summary', icon: Sparkles },
                        { value: 'entities', label: 'Entities', icon: Brain },
                        { value: 'content', label: 'Content', icon: FileText },
                      ].map((tab) => (
                        <TabsTrigger
                          key={tab.value}
                          value={tab.value}
                          className="text-xs rounded-md px-3 gap-1.5 data-[state=active]:bg-amber-500/20 data-[state=active]:text-amber-300 text-white/40 data-[state=active]:shadow-none"
                        >
                          <tab.icon className="h-3.5 w-3.5" />
                          {tab.label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </div>

                  <div className="px-6 py-4">
                    {/* Summary Tab */}
                    <TabsContent value="summary" className="mt-0 space-y-4">
                      {/* AI Summary */}
                      {selectedDoc.summary ? (
                        <div className="rounded-xl border border-amber-500/10 p-4" style={{ background: 'rgba(245,158,11,0.04)' }}>
                          <div className="flex items-center gap-2 mb-3">
                            <Sparkles className="h-4 w-4 text-amber-400" />
                            <h4 className="text-sm font-semibold text-white">AI Summary</h4>
                          </div>
                          <p className="text-sm text-white/60 leading-relaxed">{selectedDoc.summary}</p>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-white/[0.06] p-4 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <Info className="h-5 w-5 text-white/20 mx-auto mb-2" />
                          <p className="text-xs text-white/30">No summary available. Re-upload the document to generate an AI summary.</p>
                        </div>
                      )}

                      {/* Key Insights */}
                      {selectedDoc.key_insights && selectedDoc.key_insights.length > 0 && (
                        <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <div className="flex items-center gap-2 mb-3">
                            <Lightbulb className="h-4 w-4 text-amber-400" />
                            <h4 className="text-sm font-semibold text-white">Key Insights</h4>
                            <span className="text-[10px] text-white/30 ml-auto">{selectedDoc.key_insights.length} findings</span>
                          </div>
                          <div className="space-y-2">
                            {selectedDoc.key_insights.map((insight, i) => (
                              <div key={i} className="flex items-start gap-2.5 p-2 rounded-lg border border-white/[0.04]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                                <div className="h-5 w-5 rounded-full flex items-center justify-center shrink-0 mt-0.5" style={{ background: 'rgba(245,158,11,0.12)' }}>
                                  <span className="text-[10px] font-bold text-amber-400">{i + 1}</span>
                                </div>
                                <p className="text-xs text-white/50 leading-relaxed">{insight}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Processing Info */}
                      <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: 'rgba(0,0,0,0.15)' }}>
                        <div className="flex items-center gap-2 mb-3">
                          <Zap className="h-4 w-4 text-emerald-400" />
                          <h4 className="text-sm font-semibold text-white">Processing Details</h4>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          {[
                            { label: 'Word Count', value: selectedDoc.metadata?.word_count?.toLocaleString() || 'N/A' },
                            { label: 'Character Count', value: selectedDoc.metadata?.char_count?.toLocaleString() || 'N/A' },
                            { label: 'Text Chunks', value: selectedDoc.chunks_count || 0 },
                            { label: 'Processed At', value: selectedDoc.processed_at ? formatDateTime(selectedDoc.processed_at) : 'N/A' },
                          ].map((item, i) => (
                            <div key={i} className="p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
                              <p className="text-[10px] text-white/30 uppercase tracking-wider mb-0.5">{item.label}</p>
                              <p className="text-xs text-white/70 font-medium">{item.value}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Tags */}
                      {selectedDoc.tags && (
                        <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <div className="flex items-center gap-2 mb-3">
                            <Tag className="h-4 w-4 text-violet-400" />
                            <h4 className="text-sm font-semibold text-white">Tags</h4>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {selectedDoc.tags.split(',').map((tag, i) => (
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
                    <TabsContent value="entities" className="mt-0 space-y-4">
                      {selectedDoc.entities && Object.keys(selectedDoc.entities).length > 0 ? (
                        Object.entries(selectedDoc.entities).map(([key, values]) => {
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
                            <div key={key} className="rounded-xl border border-white/[0.06] p-4" style={{ background: 'rgba(0,0,0,0.15)' }}>
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
                        <div className="rounded-xl border border-white/[0.06] p-8 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <Brain className="h-8 w-8 text-white/15 mx-auto mb-3" />
                          <p className="text-sm text-white/30">No entities were extracted from this document.</p>
                          <p className="text-xs text-white/20 mt-1">Entity extraction works best with text-rich documents.</p>
                        </div>
                      )}
                    </TabsContent>

                    {/* Content Tab */}
                    <TabsContent value="content" className="mt-0 space-y-4">
                      {selectedDoc.parsed_text ? (
                        <div className="rounded-xl border border-white/[0.06] overflow-hidden" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                            <div className="flex items-center gap-2">
                              <FileText className="h-4 w-4 text-white/30" />
                              <h4 className="text-xs font-semibold text-white/60">Extracted Content</h4>
                            </div>
                            <span className="text-[10px] text-white/25">{selectedDoc.full_text_length?.toLocaleString() || 0} characters total</span>
                          </div>
                          <div className="p-4 max-h-[400px] overflow-y-auto">
                            <pre className="text-xs text-white/40 whitespace-pre-wrap font-mono leading-relaxed">{selectedDoc.parsed_text}</pre>
                          </div>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-white/[0.06] p-8 text-center" style={{ background: 'rgba(0,0,0,0.15)' }}>
                          <FileText className="h-8 w-8 text-white/15 mx-auto mb-3" />
                          <p className="text-sm text-white/30">No content preview available for this document.</p>
                        </div>
                      )}
                    </TabsContent>
                  </div>
                </Tabs>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};

export default DocumentProcessing;
