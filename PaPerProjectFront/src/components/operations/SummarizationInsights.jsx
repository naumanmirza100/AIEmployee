import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Search, Loader2, Sparkles, RefreshCw, Upload,
  FileSpreadsheet, FileType, Presentation, File, Trash2,
  ArrowRight, Clock, BookOpen, User, X, Plus, LayoutList, LayoutGrid,
  ChevronLeft, ChevronRight, Eye,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
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

// ─── Main Component ─────────────────────────
const SummarizationInsights = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [viewMode, setViewMode] = useState('table');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Fetch summaries
  const fetchSummaries = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, page_size: pageSize };
      if (searchQuery) params.search = searchQuery;
      const res = await operationsService.listSummaries(params);
      if (res.status === 'success') {
        setSummaries(res.summaries || []);
        setTotalItems(res.total || 0);
        setTotalPages(res.total_pages || 1);
      }
    } catch (e) {
      console.error('Fetch summaries error:', e);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, page, pageSize]);

  useEffect(() => { fetchSummaries(); }, [fetchSummaries]);

  // File selection in modal
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Upload and summarize
  const handleUpload = async () => {
    if (!selectedFile) return;

    try {
      setUploading(true);
      const res = await operationsService.uploadAndSummarize(selectedFile);
      if (res.status === 'success') {
        toast({
          title: 'Summary Generated',
          description: `"${selectedFile.name}" has been summarized successfully`,
        });
        if (res.summary) {
          setSummaries(prev => [res.summary, ...prev]);
        } else {
          fetchSummaries();
        }
        setShowUploadModal(false);
        setSelectedFile(null);
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

  // Close modal
  const closeModal = () => {
    if (uploading) return;
    setShowUploadModal(false);
    setSelectedFile(null);
  };

  // Delete summary
  const handleDelete = async (summaryId) => {
    try {
      setDeletingId(summaryId);
      await operationsService.deleteSummary(summaryId);
      toast({ title: 'Deleted', description: 'Summary deleted successfully' });
      setSummaries(prev => prev.filter(s => s.id !== summaryId));
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to delete', variant: 'destructive' });
    } finally {
      setDeletingId(null);
    }
  };

  // Get file config for selected file
  const getSelectedFileConfig = () => {
    if (!selectedFile) return null;
    const ext = selectedFile.name.split('.').pop()?.toLowerCase();
    return getFileConfig(ext);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-white">Document Summarization</h2>
          <p className="text-gray-400 text-sm mt-1">Upload any document and get an AI-powered comprehensive summary</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-xs py-1 px-3 w-fit" style={{ borderColor: '#f59e0b40', color: '#f59e0b' }}>
            {summaries.length} {summaries.length === 1 ? 'Summary' : 'Summaries'}
          </Badge>
          <Button
            size="sm"
            className="gap-2 text-xs font-semibold"
            style={{ background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', color: '#fff' }}
            onClick={() => setShowUploadModal(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            Upload & Summarize
          </Button>
        </div>
      </div>

      {/* Search & Refresh */}
      {(summaries.length > 0 || searchQuery) && (
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
            <Input
              placeholder="Search summaries..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-10 h-10 rounded-xl bg-white/[0.03] border-white/[0.08] text-white placeholder:text-white/30"
            />
          </div>
          {/* Rows per page */}
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="h-10 rounded-xl border border-white/[0.08] text-xs text-white/70 pl-3 pr-8 shrink-0 cursor-pointer outline-none focus:border-amber-500/40 transition-colors"
            style={{ background: 'rgba(0,0,0,0.25)', backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23f59e0b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center' }}>
            {[5, 10, 20, 30, 50].map(n => (
              <option key={n} value={n} className="bg-[#1a1028] text-white">{n} rows</option>
            ))}
          </select>
          {/* View Toggle */}
          <div className="flex items-center h-10 rounded-xl border border-white/[0.08] overflow-hidden" style={{ background: 'rgba(0,0,0,0.25)' }}>
            <button onClick={() => setViewMode('list')}
              className={`h-full px-2.5 flex items-center justify-center transition-colors ${viewMode === 'list' ? 'text-amber-400 bg-amber-500/10' : 'text-white/30 hover:text-white/50'}`}>
              <LayoutList className="h-4 w-4" />
            </button>
            <div className="w-px h-5 bg-white/[0.08]" />
            <button onClick={() => setViewMode('table')}
              className={`h-full px-2.5 flex items-center justify-center transition-colors ${viewMode === 'table' ? 'text-amber-400 bg-amber-500/10' : 'text-white/30 hover:text-white/50'}`}>
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
          <Button variant="outline" size="icon" className="h-10 w-10 rounded-xl border-white/[0.08] text-white/50 hover:text-white"
            onClick={fetchSummaries}>
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
      ) : summaries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 rounded-2xl border border-white/[0.06]" style={{ background: 'rgba(0,0,0,0.1)' }}>
          <Sparkles className="h-10 w-10 text-white/10 mb-3" />
          <p className="text-white/40 text-sm">No summaries yet</p>
          <p className="text-white/25 text-xs mt-1">Click "Upload & Summarize" to generate your first summary</p>
        </div>
      ) : (
        <>
          {/* ── List View ── */}
          {viewMode === 'list' && (
            <div className="space-y-3">
              <AnimatePresence>
                {summaries.map((s) => {
                  const fc = getFileConfig(s.file_type);
                  const FIcon = fc.icon;
                  return (
                    <motion.div
                      key={s.id}
                      layout
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      className="group rounded-xl border border-white/[0.06] overflow-hidden hover:border-white/[0.12] transition-all"
                      style={{ background: 'rgba(0,0,0,0.2)' }}
                    >
                      <div className="flex items-center gap-4 p-4">
                        <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0" style={{ backgroundColor: `${fc.color}15` }}>
                          <FIcon className="h-5 w-5" style={{ color: fc.color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-white truncate">{s.original_filename}</p>
                          <div className="flex items-center gap-3 mt-1 text-[11px] text-white/30 flex-wrap">
                            <span className="flex items-center gap-1"><BookOpen className="h-3 w-3" /> {s.page_count} pages</span>
                            <span>{formatFileSize(s.file_size)}</span>
                            <span>{s.word_count?.toLocaleString()} words</span>
                            <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDate(s.created_at)}</span>
                            {s.created_by && <span className="flex items-center gap-1"><User className="h-3 w-3" /> {s.created_by}</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0 opacity-50 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="sm" className="h-8 px-3 text-xs text-white/50 hover:text-amber-400 hover:bg-amber-500/10 gap-1.5 rounded-lg"
                            onClick={() => navigate(`/operations/summarization/${s.id}`)}>
                            <ArrowRight className="h-3.5 w-3.5" />View
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-white/40 hover:text-red-400 hover:bg-red-500/10"
                            onClick={() => handleDelete(s.id)} disabled={deletingId === s.id}>
                            {deletingId === s.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          )}

          {/* ── Table View ── */}
          {viewMode === 'table' && (
            <div className="rounded-xl border border-white/[0.06] overflow-hidden" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Document</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Format</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Size</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Pages</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Words</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider">Created</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-white/40 uppercase tracking-wider text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaries.map((s) => {
                      const fc = getFileConfig(s.file_type);
                      const FIcon = fc.icon;
                      return (
                        <tr key={s.id} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors group">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <div className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0" style={{ backgroundColor: `${fc.color}15` }}>
                                <FIcon className="h-4 w-4" style={{ color: fc.color }} />
                              </div>
                              <p className="text-sm font-medium text-white truncate max-w-[250px]">{s.original_filename}</p>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-[11px] px-2 py-0.5 rounded-full font-medium" style={{ background: `${fc.color}15`, color: fc.color }}>
                              {fc.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-white/40">{formatFileSize(s.file_size)}</td>
                          <td className="px-4 py-3 text-xs text-white/40">{s.page_count || '—'}</td>
                          <td className="px-4 py-3 text-xs text-white/40">{s.word_count?.toLocaleString() || '—'}</td>
                          <td className="px-4 py-3">
                            <div className="text-xs text-white/40">{formatDate(s.created_at)}</div>
                            {s.created_by && <div className="text-[10px] text-white/25">{s.created_by}</div>}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1 opacity-50 group-hover:opacity-100 transition-opacity">
                              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md text-white/60 hover:text-amber-400 hover:bg-amber-500/10"
                                onClick={() => navigate(`/operations/summarization/${s.id}`)}>
                                <Eye className="h-3.5 w-3.5" />
                              </Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md text-white/40 hover:text-red-400 hover:bg-red-500/10"
                                onClick={() => handleDelete(s.id)} disabled={deletingId === s.id}>
                                {deletingId === s.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Pagination ── */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-[11px] text-white/25">
              Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalItems)} of {totalItems}
            </span>
            {totalPages > 1 && (
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-white/40 hover:text-white disabled:opacity-20"
                  disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                  .reduce((acc, p, i, arr) => {
                    if (i > 0 && p - arr[i - 1] > 1) acc.push('...');
                    acc.push(p);
                    return acc;
                  }, [])
                  .map((p, i) =>
                    p === '...' ? (
                      <span key={`dot-${i}`} className="text-[11px] text-white/20 px-1">...</span>
                    ) : (
                      <button key={p} onClick={() => setPage(p)}
                        className={`h-8 min-w-[32px] rounded-lg text-[11px] font-medium transition-colors ${p === page ? 'bg-amber-500/20 text-amber-400' : 'text-white/40 hover:text-white hover:bg-white/[0.05]'}`}>
                        {p}
                      </button>
                    )
                  )}
                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-white/40 hover:text-white disabled:opacity-20"
                  disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Upload Modal ── */}
      <AnimatePresence>
        {showUploadModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
            onClick={closeModal}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-md rounded-2xl border border-white/[0.08] overflow-hidden"
              style={{ background: '#1a1028' }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="flex items-center justify-center w-9 h-9 rounded-xl" style={{ background: 'rgba(245,158,11,0.12)' }}>
                    <Upload className="h-4.5 w-4.5 text-amber-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">Upload & Summarize</h3>
                    <p className="text-[11px] text-white/35">Select a document to generate AI summary & insights</p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-lg text-white/40 hover:text-white"
                  onClick={closeModal}
                  disabled={uploading}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>

              {/* Modal Body */}
              <div className="px-6 py-5 space-y-4">
                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md"
                  onChange={handleFileChange}
                  disabled={uploading}
                />

                {/* Drop/Select Area */}
                {!selectedFile ? (
                  <div
                    className="rounded-xl border-2 border-dashed border-white/[0.08] hover:border-amber-500/30 transition-colors cursor-pointer p-8"
                    style={{ background: 'rgba(0,0,0,0.15)' }}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <div className="flex flex-col items-center text-center">
                      <div className="flex items-center justify-center w-12 h-12 rounded-2xl mb-3" style={{ background: 'rgba(245,158,11,0.1)' }}>
                        <Upload className="h-6 w-6 text-amber-500" />
                      </div>
                      <p className="text-sm font-medium text-white">Click to select document</p>
                      <p className="text-xs text-white/30 mt-1">PDF, DOCX, XLSX, CSV, PPTX, TXT</p>
                      <p className="text-[10px] text-white/20 mt-0.5">Maximum 50 MB</p>
                    </div>
                  </div>
                ) : (
                  /* Selected File Preview */
                  <div className="rounded-xl border border-white/[0.08] p-4" style={{ background: 'rgba(0,0,0,0.15)' }}>
                    <div className="flex items-center gap-3">
                      {(() => {
                        const sfc = getSelectedFileConfig();
                        const SFIcon = sfc?.icon || File;
                        return (
                          <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0"
                            style={{ backgroundColor: `${sfc?.color || '#6b7280'}15` }}>
                            <SFIcon className="h-5 w-5" style={{ color: sfc?.color || '#6b7280' }} />
                          </div>
                        );
                      })()}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-white truncate">{selectedFile.name}</p>
                        <p className="text-[11px] text-white/30 mt-0.5">{formatFileSize(selectedFile.size)}</p>
                      </div>
                      {!uploading && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 rounded-lg text-white/40 hover:text-white"
                          onClick={() => setSelectedFile(null)}
                        >
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>

                    {/* Uploading Progress */}
                    {uploading && (
                      <div className="mt-4 space-y-2">
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin text-amber-500" />
                          <span className="text-xs text-amber-400 font-medium">Processing & Summarizing...</span>
                        </div>
                        <p className="text-[10px] text-white/25">Extracting text, generating summary & insights</p>
                        <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                          <motion.div
                            className="h-full rounded-full"
                            style={{ background: 'linear-gradient(90deg, #f59e0b, #f97316)' }}
                            initial={{ width: '5%' }}
                            animate={{ width: '85%' }}
                            transition={{ duration: 15, ease: 'easeOut' }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-white/[0.06]" style={{ background: 'rgba(0,0,0,0.1)' }}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-white/40 hover:text-white"
                  onClick={closeModal}
                  disabled={uploading}
                >
                  Cancel
                </Button>
                <div className="flex items-center gap-2">
                  {selectedFile && !uploading && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs text-white/50 hover:text-white"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Change File
                    </Button>
                  )}
                  <Button
                    size="sm"
                    className="gap-2 text-xs font-semibold"
                    style={{ background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', color: '#fff' }}
                    onClick={handleUpload}
                    disabled={!selectedFile || uploading}
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5" />
                        Summarize
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SummarizationInsights;
