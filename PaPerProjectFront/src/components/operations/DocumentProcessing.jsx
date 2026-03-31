import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  FileText, Search, Upload, Loader2, Trash2, Eye,
  FileSpreadsheet, FileType, Presentation, File,
  Tag, Hash, User, Calendar, BarChart3, RefreshCw,
} from 'lucide-react';
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
const getFileConfig = (type) => FILE_TYPE_CONFIG[type] || { icon: File, color: '#6b7280', label: type?.toUpperCase() || 'FILE' };

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
      toast({ title: 'Success', description: `"${res.document?.title || uploadFile.name}" processed successfully` });
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

  // ═══ RENDER ═══════════════════════════════
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <Input className="pl-10 bg-[#1a1333]/60 border-[#2d2342] text-white placeholder:text-gray-500" placeholder="Search documents..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        </div>
        <Button variant="outline" size="icon" onClick={fetchDocuments} className="border-[#2d2342] text-gray-400 hover:text-white">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button onClick={() => setShowUpload(true)} className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white">
          <Upload className="mr-2 h-4 w-4" />
          Upload
        </Button>
      </div>

      {/* Documents list */}
      {docsLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-amber-500" />
        </div>
      ) : documents.length === 0 ? (
        <Card className="bg-[#1a1333]/40 border-[#2d2342] border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-2xl bg-amber-500/10 flex items-center justify-center mb-4">
              <Upload className="h-8 w-8 text-amber-500" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">No documents yet</h3>
            <p className="text-gray-400 mb-6 max-w-sm">Upload your first document to get started. We support PDF, DOCX, Excel, PowerPoint, CSV, and text files.</p>
            <Button onClick={() => setShowUpload(true)} className="bg-amber-500 hover:bg-amber-600 text-white">
              <Upload className="mr-2 h-4 w-4" />Upload Document
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {documents.map((doc) => {
            const fc = getFileConfig(doc.file_type);
            const FileIcon = fc.icon;
            const dtColor = DOC_TYPE_COLORS[doc.document_type] || '#6b7280';
            return (
              <Card key={doc.id} className="bg-[#1a1333]/60 border-[#2d2342] hover:border-[#3a295a] transition-all duration-200 group">
                <CardContent className="p-4 flex items-center gap-4">
                  <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0" style={{ backgroundColor: `${fc.color}15` }}>
                    <FileIcon className="h-5 w-5" style={{ color: fc.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="text-sm font-semibold text-white truncate">{doc.title}</h4>
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0" style={{ borderColor: dtColor, color: dtColor }}>{doc.document_type}</Badge>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span className="flex items-center gap-1"><File className="h-3 w-3" />{fc.label} &middot; {formatFileSize(doc.file_size)}</span>
                      {doc.page_count > 0 && <span>{doc.page_count} pages</span>}
                      <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{formatDate(doc.created_at)}</span>
                      {doc.uploaded_by && <span className="hidden sm:flex items-center gap-1"><User className="h-3 w-3" />{doc.uploaded_by}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400 hover:text-white" onClick={() => openDetail(doc.id)} title="View details"><Eye className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400 hover:text-red-400" onClick={() => handleDelete(doc.id)} disabled={deletingId === doc.id} title="Delete">
                      {deletingId === doc.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* ═══ Upload Dialog ═══ */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent className="bg-[#0f0a20] border-[#2d2342] text-white sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Upload Document</DialogTitle>
            <DialogDescription className="text-gray-400">Supported: PDF, DOCX, XLSX, CSV, PPTX, TXT</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-gray-300">File</Label>
              <Input type="file" accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.pptx,.txt,.md" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} className="bg-[#1a1333]/60 border-[#2d2342] text-white file:text-amber-400 file:bg-transparent file:border-0 file:font-medium cursor-pointer" />
              {uploadFile && <p className="text-xs text-gray-500">{uploadFile.name} ({formatFileSize(uploadFile.size)})</p>}
            </div>
            <div className="space-y-2">
              <Label className="text-gray-300">Title (optional)</Label>
              <Input placeholder="Document title" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} className="bg-[#1a1333]/60 border-[#2d2342] text-white placeholder:text-gray-600" />
            </div>
            <div className="space-y-2">
              <Label className="text-gray-300">Tags (optional, comma-separated)</Label>
              <Input placeholder="finance, Q1, report" value={uploadTags} onChange={(e) => setUploadTags(e.target.value)} className="bg-[#1a1333]/60 border-[#2d2342] text-white placeholder:text-gray-600" />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowUpload(false)} className="border-[#2d2342] text-gray-300 hover:text-white">Cancel</Button>
            <Button onClick={handleUpload} disabled={uploading || !uploadFile} className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white">
              {uploading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Processing...</> : <><Upload className="mr-2 h-4 w-4" />Upload & Process</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Detail Dialog ═══ */}
      <Dialog open={!!selectedDoc || detailLoading} onOpenChange={(open) => { if (!open) setSelectedDoc(null); }}>
        <DialogContent className="bg-[#0f0a20] border-[#2d2342] text-white sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          {detailLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-amber-500" /></div>
          ) : selectedDoc && (
            <>
              <DialogHeader>
                <div className="flex items-center gap-3 mb-2">
                  {(() => { const fc = getFileConfig(selectedDoc.file_type); const FI = fc.icon; return (<div className="flex items-center justify-center w-10 h-10 rounded-xl" style={{ backgroundColor: `${fc.color}15` }}><FI className="h-5 w-5" style={{ color: fc.color }} /></div>); })()}
                  <div>
                    <DialogTitle className="text-white text-lg">{selectedDoc.title}</DialogTitle>
                    <p className="text-xs text-gray-500 mt-0.5">{selectedDoc.original_filename}</p>
                  </div>
                </div>
              </DialogHeader>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 my-4">
                {[
                  { label: 'Type', value: selectedDoc.document_type, icon: Tag },
                  { label: 'Format', value: selectedDoc.file_type?.toUpperCase(), icon: File },
                  { label: 'Size', value: formatFileSize(selectedDoc.file_size), icon: Hash },
                  { label: 'Pages', value: selectedDoc.page_count || 'N/A', icon: FileText },
                  { label: 'Chunks', value: selectedDoc.chunks_count || 0, icon: BarChart3 },
                  { label: 'Uploaded', value: formatDate(selectedDoc.created_at), icon: Calendar },
                ].map((m, i) => (
                  <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.03] border border-white/[0.04]">
                    <m.icon className="h-3.5 w-3.5 text-gray-500 shrink-0" />
                    <div>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{m.label}</p>
                      <p className="text-sm text-white font-medium">{m.value}</p>
                    </div>
                  </div>
                ))}
              </div>
              {selectedDoc.entities && Object.keys(selectedDoc.entities).length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-300">Extracted Entities</h4>
                  <div className="space-y-2">
                    {Object.entries(selectedDoc.entities).map(([key, values]) => (
                      Array.isArray(values) && values.length > 0 && (
                        <div key={key} className="flex flex-wrap items-center gap-1.5">
                          <span className="text-xs text-gray-500 capitalize w-24 shrink-0">{key.replace('_', ' ')}:</span>
                          {values.slice(0, 8).map((v, i) => (<Badge key={i} variant="outline" className="text-[10px] px-1.5 py-0 border-[#3a295a] text-gray-300">{v}</Badge>))}
                          {values.length > 8 && <span className="text-[10px] text-gray-500">+{values.length - 8} more</span>}
                        </div>
                      )
                    ))}
                  </div>
                </div>
              )}
              {selectedDoc.parsed_text && (
                <div className="space-y-2 mt-4">
                  <h4 className="text-sm font-semibold text-gray-300">Content Preview <span className="text-xs font-normal text-gray-500 ml-2">({selectedDoc.full_text_length?.toLocaleString() || 0} chars total)</span></h4>
                  <div className="bg-white/[0.02] border border-white/[0.04] rounded-lg p-4 max-h-60 overflow-y-auto">
                    <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed">{selectedDoc.parsed_text}</pre>
                  </div>
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DocumentProcessing;
