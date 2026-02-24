import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Loader2, FileText, Send, Plus, Download, X, Trash2 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { cn } from '@/lib/utils';

/**
 * Document Authoring sub-agent (PayPerProject).
 * List documents in table, create via inline form (red X to close), view detail in wide modal.
 */

const DOCUMENT_TYPES = [
  { value: 'strategy', label: 'Marketing Strategy' },
  { value: 'proposal', label: 'Campaign Proposal' },
  { value: 'report', label: 'Performance Report' },
  { value: 'brief', label: 'Campaign Brief' },
  // { value: 'presentation', label: 'Presentation Outline' },
];

const TYPE_BADGE_CLASS = {
  strategy: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  proposal: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  report: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  brief: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
  presentation: 'bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300',
};

const CAMPAIGN_STATUS_BADGE = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  scheduled: 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  paused: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  completed: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
};

const PAGE_SIZE = 10;

const Documents = () => {
  const { toast } = useToast();
  const [documents, setDocuments] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [filterType, setFilterType] = useState('');
  const [filterCampaignId, setFilterCampaignId] = useState('');
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 1 });
  const [createExpanded, setCreateExpanded] = useState(false);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [documentType, setDocumentType] = useState('strategy');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [campaignId, setCampaignId] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [detailDoc, setDetailDoc] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [downloading, setDownloading] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const fetchDocuments = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (filterType) params.type = filterType;
      if (filterCampaignId) params.campaign_id = filterCampaignId;
      const response = await marketingAgentService.listDocuments(params);
      if (response?.status === 'success' && response?.data) {
        setDocuments(response.data.documents ?? []);
        setPagination(response.data.pagination ?? { page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 1 });
        const totalPages = response.data.pagination?.total_pages ?? 1;
        if ((response.data.documents?.length ?? 0) === 0 && page > 1 && totalPages > 0) {
          setPage(Math.min(page - 1, totalPages));
        }
      } else {
        setDocuments([]);
      }
    } catch {
      setDocuments([]);
    } finally {
      setLoadingList(false);
    }
  }, [filterType, filterCampaignId, page]);

  const fetchCampaigns = useCallback(async () => {
    try {
      const response = await marketingAgentService.listCampaigns({ limit: 50 });
      if (response?.status === 'success' && response?.data?.campaigns) {
        setCampaigns(response.data.campaigns);
      }
    } catch {
      setCampaigns([]);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    setPage(1);
  }, [filterType, filterCampaignId]);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const openDetail = async (id) => {
    setSelectedDocumentId(id);
    setDetailDoc(null);
    setLoadingDetail(true);
    try {
      const response = await marketingAgentService.getDocument(id);
      if (response?.status === 'success' && response?.data) {
        setDetailDoc(response.data);
      } else {
        toast({ title: 'Error', description: 'Could not load document', variant: 'destructive' });
        setSelectedDocumentId(null);
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not load document', variant: 'destructive' });
      setSelectedDocumentId(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleDelete = async (docId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm('Delete this document? This cannot be undone.')) return;
    setDeletingId(docId);
    try {
      const response = await marketingAgentService.deleteDocument(docId);
      if (response?.status === 'success') {
        toast({ title: 'Document deleted' });
        if (selectedDocumentId === docId) {
          setSelectedDocumentId(null);
          setDetailDoc(null);
        }
        await fetchDocuments();
      } else {
        toast({ title: 'Delete failed', description: response?.message, variant: 'destructive' });
      }
    } catch (err) {
      toast({ title: 'Delete failed', description: err.message, variant: 'destructive' });
    } finally {
      setDeletingId(null);
    }
  };

  const handleDownload = async (docId, formatCode) => {
    const key = `${docId}-${formatCode}`;
    setDownloading(key);
    try {
      const blob = await marketingAgentService.downloadDocument(docId, formatCode);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `document-${docId}.${formatCode}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({ title: 'Download started' });
    } catch (err) {
      toast({ title: 'Download failed', description: err.message, variant: 'destructive' });
    } finally {
      setDownloading(null);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    const hasCampaign = campaignId && campaignId !== '__none__' && campaignId !== '__required__';
    const needsCampaign = documentType === 'report' || documentType === 'brief';
    if (needsCampaign && !hasCampaign) {
      toast({ title: 'Campaign required', description: 'Performance Report and Campaign Brief require a campaign.', variant: 'destructive' });
      return;
    }
    setLoadingCreate(true);
    try {
      const documentData = {};
      if (title?.trim()) documentData.title = title.trim();
      if (notes?.trim()) documentData.notes = notes.trim();
      const campaignIdNum = hasCampaign ? Number(campaignId) : null;
      const response = await marketingAgentService.documentAuthoring('create', documentType, documentData, campaignIdNum, {});
      if (response.status === 'error') {
        const msg = /429|rate limit/i.test(response.message || '') ? 'The service is busy. Please try again in a moment.' : (response.message || 'Request failed');
        setError(msg);
        toast({ title: 'Error', description: msg, variant: 'destructive' });
        return;
      }
      const data = response.data;
      if (data.success === false) {
        const errMsg = data.error || 'Document generation failed';
        const msg = /429|rate limit/i.test(errMsg) ? 'The service is busy. Please try again in a moment.' : errMsg;
        setError(msg);
        toast({ title: 'Error', description: msg, variant: 'destructive' });
        return;
      }
      setResult(data);
      toast({ title: 'Success', description: data.message || 'Document created' });
      setCreateExpanded(false);
      await fetchDocuments();
      if (data.document_id) {
        openDetail(data.document_id);
      }
    } catch (err) {
      const raw = err.message || 'Failed to generate document';
      const msg = /429|rate limit/i.test(raw) ? 'The service is busy. Please try again in a moment.' : raw;
      setError(msg);
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setLoadingCreate(false);
    }
  };

  const closeCreateForm = () => {
    setCreateExpanded(false);
    setError(null);
    setResult(null);
  };

  return (
    <div className="space-y-5">
      {/* Header + Create button */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-foreground">Marketing Documents</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            View and manage documents. Click a row to open, or create a new document with the AI agent.
          </p>
        </div>
        <Button onClick={() => setCreateExpanded((v) => !v)} size="default" className="shrink-0" variant={createExpanded ? 'secondary' : 'default'}>
          {createExpanded ? (
            <>
              <X className="h-4 w-4 mr-2" />
              Close
            </>
          ) : (
            <>
              <Plus className="h-4 w-4 mr-2" />
              Create New Document
            </>
          )}
        </Button>
      </div>

      {/* Create form (inline, collapsible) – red X to close */}
      {createExpanded && (
        <Card className="relative">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-3 top-3 h-8 w-8 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive z-10"
            onClick={closeCreateForm}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </Button>
          <CardHeader className="pr-12">
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" />
              Create New Document
            </CardTitle>
          <CardDescription>
              Generate a document using the Document Authoring Agent. Choose type, optional campaign, title and notes.
          </CardDescription>
        </CardHeader>
        <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Document type</Label>
                  <Select value={documentType} onValueChange={(v) => { setDocumentType(v); setResult(null); setError(null); }}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {DOCUMENT_TYPES.map((t) => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {/* Campaign: required for report/brief (only campaigns in dropdown); optional for strategy/proposal (show "No campaign" option) */}
                <div className="space-y-2">
                  <Label>
                    Campaign {documentType === 'report' || documentType === 'brief' ? '(required)' : '(optional – leave empty for general document)'}
                  </Label>
                  <Select
                    value={campaignId || (documentType === 'report' || documentType === 'brief' ? '__required__' : '__none__')}
                    onValueChange={(v) => setCampaignId(v === '__none__' || v === '__required__' ? '' : v)}
                  >
                    <SelectTrigger><SelectValue placeholder={documentType === 'report' || documentType === 'brief' ? 'Select campaign (required)' : 'Select campaign'} /></SelectTrigger>
                    <SelectContent>
                      {documentType !== 'report' && documentType !== 'brief' && (
                        <SelectItem value="__none__">No campaign (general document)</SelectItem>
                      )}
                      {(documentType === 'report' || documentType === 'brief') && (
                        <SelectItem value="__required__" disabled>Select campaign (required)</SelectItem>
                      )}
                      {campaigns.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Title (optional)</Label>
                <Input placeholder="e.g. Q1 Marketing Strategy" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Notes / key points (optional)</Label>
                <Textarea placeholder="Context, requirements..." value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="resize-none" />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              {result && result.document_id && (
                <p className="text-sm text-muted-foreground">Document created. Opening it in the viewer.</p>
              )}
              <div className='flex justify-end'>
              <Button type="submit" disabled={loadingCreate}>
                  {loadingCreate ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                  Generate
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Filters – full width */}
      <div className="flex flex-wrap gap-4 items-end w-full">
        <div className="space-y-1.5 flex-1 min-w-[180px]">
          <Label className="text-xs font-medium text-muted-foreground">Document type</Label>
          <Select value={filterType || '__all__'} onValueChange={(v) => setFilterType(v === '__all__' ? '' : v)}>
            <SelectTrigger className="h-9 w-full"><SelectValue placeholder="All types" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All types</SelectItem>
              {DOCUMENT_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 flex-1 min-w-[180px]">
          <Label className="text-xs font-medium text-muted-foreground">Campaign</Label>
          <Select value={filterCampaignId || '__all__'} onValueChange={(v) => setFilterCampaignId(v === '__all__' ? '' : v)}>
            <SelectTrigger className="h-9 w-full"><SelectValue placeholder="All campaigns" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All campaigns</SelectItem>
              {campaigns.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="secondary" size="sm" className="h-9 shrink-0" onClick={fetchDocuments} disabled={loadingList}>
          {loadingList ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Apply'}
        </Button>
      </div>

      {/* Document list – table */}
      <Card>
        <CardContent className="p-0">
          {loadingList ? (
            <div className="flex justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
              <FileText className="h-12 w-12 text-muted-foreground/60 mb-4" />
              <p className="font-medium text-foreground">No documents yet</p>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                {filterType || filterCampaignId ? 'No documents match the filters. Try changing them or create a new document.' : 'Create your first document with the button above.'}
              </p>
              <Button className="mt-5" variant="outline" onClick={() => setCreateExpanded(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create New Document
              </Button>
            </div>
          ) : (
            <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left font-semibold p-3 text-muted-foreground">Document</th>
                    <th className="text-left font-semibold p-3 text-muted-foreground">Campaign</th>
                    <th className="text-left font-semibold p-3 text-muted-foreground">Document type</th>
                    <th className="text-left font-semibold p-3 text-muted-foreground">Created on</th>
                    <th className="w-10 p-3 text-muted-foreground" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr
                      key={doc.id}
                      className={cn(
                        'border-b last:border-0 cursor-pointer transition-colors hover:bg-muted/40',
                        selectedDocumentId === doc.id && 'bg-primary/5'
                      )}
                      onClick={() => openDetail(doc.id)}
                    >
                      <td className="p-3">
                        <span className="font-medium text-foreground">{doc.title}</span>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {doc.campaign_name ? doc.campaign_name : '—'}
                      </td>
                      <td className="p-3">
                        <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-medium', TYPE_BADGE_CLASS[doc.document_type] || 'bg-muted text-muted-foreground')}>
                          {doc.document_type_display}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground tabular-nums">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="p-3">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          disabled={deletingId === doc.id}
                          onClick={(e) => handleDelete(doc.id, e)}
                          title="Delete document"
                        >
                          {deletingId === doc.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pagination.total_pages > 1 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 bg-muted/30">
                <p className="text-sm text-muted-foreground">
                  Showing {(pagination.page - 1) * pagination.page_size + 1}–{Math.min(pagination.page * pagination.page_size, pagination.total)} of {pagination.total} documents
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.page <= 1 || loadingList}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground tabular-nums">
                    Page {pagination.page} of {pagination.total_pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.page >= pagination.total_pages || loadingList}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Document detail modal – wide, professional */}
      <Dialog open={!!selectedDocumentId} onOpenChange={(open) => !open && setSelectedDocumentId(null)}>
        <DialogContent className="max-w-6xl w-[95vw] max-h-[90vh] overflow-hidden flex flex-col gap-0 p-0 border-0 shadow-2xl">
          {/* Header bar */}
          <div className="flex items-start justify-between gap-4 border-b bg-muted/30 px-6 py-4 shrink-0">
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold text-foreground truncate pr-8">
                {detailDoc?.title || 'Document'}
              </h2>
              {detailDoc && (
                <div className="flex flex-wrap items-center gap-2 mt-2 text-sm text-muted-foreground">
                  <span className={cn('inline-flex px-2 py-0.5 rounded text-xs font-medium', TYPE_BADGE_CLASS[detailDoc.document_type])}>
                    {detailDoc.document_type_display}
                  </span>
                  {detailDoc.campaign_name && (
                    <span className="flex items-center gap-1.5">
                      Campaign: <span className="font-medium text-foreground">{detailDoc.campaign_name}</span>
                      {detailDoc.campaign_status_display && (
                        <span className={cn('inline-flex px-2 py-0.5 rounded text-xs font-medium', CAMPAIGN_STATUS_BADGE[detailDoc.campaign_status] || 'bg-muted text-muted-foreground')}>
                          {detailDoc.campaign_status_display}
                        </span>
                      )}
                    </span>
                  )}
                  <span className="tabular-nums">{formatDate(detailDoc.created_at)}</span>
                </div>
              )}
            </div>
          </div>

          {/* Toolbar: Download + Delete */}
          {detailDoc && (
            <div className="flex items-center justify-between gap-4 px-6 py-3 border-b bg-background/80 shrink-0">
              <div className="flex items-center gap-2">
                {detailDoc.available_formats?.length > 0 && (
                  <>
                    <span className="text-sm font-medium text-muted-foreground mr-2">Download:</span>
                    {detailDoc.available_formats.map(({ code, name }) => (
                      <Button
                        key={code}
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={downloading === `${detailDoc.id}-${code}`}
                        onClick={() => handleDownload(detailDoc.id, code)}
                      >
                        {downloading === `${detailDoc.id}-${code}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Download className="h-3.5 w-3.5" />
                        )}
                        {name}
                      </Button>
                    ))}
                  </>
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deletingId === detailDoc.id}
                onClick={() => handleDelete(detailDoc.id)}
              >
                {deletingId === detailDoc.id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                Delete
              </Button>
            </div>
          )}

          {/* Content area */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {loadingDetail ? (
              <div className="flex justify-center items-center py-24">
                <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
              </div>
            ) : detailDoc ? (
              <div className="px-6 py-5">
                <div className="prose prose-sm dark:prose-invert max-w-none rounded-lg border bg-card p-6 text-foreground">
                  <div className="whitespace-pre-wrap font-sans text-[15px] leading-relaxed">
                    {detailDoc.content || 'No content.'}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Documents;
