import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { 
  Loader2, 
  FileText, 
  Send, 
  Plus, 
  Download, 
  X, 
  Trash2,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
  Eye,
  Clock,
  Calendar,
  File,
  FileSpreadsheet,
  FileIcon,
  Presentation,
  Briefcase,
  TrendingUp,
  Target,
  Zap,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
  BookOpen,
  PenTool,
  FileOutput
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * Document Authoring sub-agent (PayPerProject).
 * List documents in table, create via inline form, view detail in wide modal.
 */

const DOCUMENT_TYPES = [
  { value: 'strategy', label: 'Marketing Strategy', icon: Target, color: 'text-blue-500', bgColor: 'bg-blue-500/10' },
  { value: 'proposal', label: 'Campaign Proposal', icon: Briefcase, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10' },
  { value: 'report', label: 'Performance Report', icon: TrendingUp, color: 'text-amber-500', bgColor: 'bg-amber-500/10' },
  { value: 'brief', label: 'Campaign Brief', icon: PenTool, color: 'text-purple-500', bgColor: 'bg-purple-500/10' },
  { value: 'presentation', label: 'Presentation Outline', icon: Presentation, color: 'text-rose-500', bgColor: 'bg-rose-500/10' },
];

const TYPE_BADGE_CLASS = {
  strategy: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  proposal: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  report: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800',
  brief: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800',
  presentation: 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300 border-rose-200 dark:border-rose-800',
};

const CAMPAIGN_STATUS_BADGE = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300 border-gray-200 dark:border-gray-700',
  scheduled: 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300 border-sky-200 dark:border-sky-800',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800',
  paused: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800',
  completed: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800',
};

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    const date = new Date(iso);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 86400000) { // Less than 24 hours
      return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } else if (diff < 604800000) { // Less than 7 days
      return date.toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    } else {
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    }
  } catch {
    return iso;
  }
};

const PAGE_SIZE = 10;

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  }
};

const tableRowVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: {
    opacity: 1,
    x: 0,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  },
  hover: {
    scale: 1.01,
    backgroundColor: "rgba(var(--primary), 0.05)",
    transition: { duration: 0.2 }
  }
};

const Documents = () => {
  const { toast } = useToast();
  const [documents, setDocuments] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [filterType, setFilterType] = useState('');
  const [filterCampaignId, setFilterCampaignId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
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
  const [showFilters, setShowFilters] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (filterType) params.type = filterType;
      if (filterCampaignId) params.campaign_id = filterCampaignId;
      if (searchQuery) params.search = searchQuery;
      
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
  }, [filterType, filterCampaignId, searchQuery, page]);

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
  }, [filterType, filterCampaignId, searchQuery]);

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
        toast({ 
          title: 'Document deleted',
          description: 'The document has been removed successfully.'
        });
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
      toast({ 
        title: 'Download started',
        description: `Downloading ${formatCode.toUpperCase()} format.`
      });
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
      toast({ 
        title: 'Campaign required', 
        description: 'Performance Report and Campaign Brief require a campaign.', 
        variant: 'destructive' 
      });
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
        const msg = /429|rate limit/i.test(response.message || '') 
          ? 'The service is busy. Please try again in a moment.' 
          : (response.message || 'Request failed');
        setError(msg);
        toast({ title: 'Error', description: msg, variant: 'destructive' });
        return;
      }
      
      const data = response.data;
      if (data.success === false) {
        const errMsg = data.error || 'Document generation failed';
        const msg = /429|rate limit/i.test(errMsg) 
          ? 'The service is busy. Please try again in a moment.' 
          : errMsg;
        setError(msg);
        toast({ title: 'Error', description: msg, variant: 'destructive' });
        return;
      }
      
      setResult(data);
      toast({ 
        title: '✅ Document created', 
        description: data.message || 'Your document has been generated successfully.'
      });
      setCreateExpanded(false);
      await fetchDocuments();
      if (data.document_id) {
        openDetail(data.document_id);
      }
      
      // Reset form
      setTitle('');
      setNotes('');
      setCampaignId('');
    } catch (err) {
      const raw = err.message || 'Failed to generate document';
      const msg = /429|rate limit/i.test(raw) 
        ? 'The service is busy. Please try again in a moment.' 
        : raw;
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
    setTitle('');
    setNotes('');
    setCampaignId('');
  };

  const clearFilters = () => {
    setFilterType('');
    setFilterCampaignId('');
    setSearchQuery('');
  };

  const getDocumentIcon = (type) => {
    const found = DOCUMENT_TYPES.find(t => t.value === type);
    return found ? found.icon : FileText;
  };

  return (
    <motion.div 
      className="space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Header with gradient */}
      <motion.div 
        variants={itemVariants}
        className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary/10 via-primary/5 to-background p-6"
      >
        <div className="relative z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <motion.div 
              whileHover={{ rotate: 15, scale: 1.1 }}
              className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/20"
            >
              <FileText className="h-7 w-7 text-primary" />
            </motion.div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Marketing Documents</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Create, manage, and collaborate on marketing documents with AI assistance
              </p>
            </div>
          </div>
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Button 
              onClick={() => setCreateExpanded(!createExpanded)} 
              size="lg" 
              className={cn(
                "shrink-0 gap-2 transition-all",
                createExpanded ? 'bg-secondary' : 'bg-primary hover:bg-primary/90'
              )}
            >
              {createExpanded ? (
                <>
                  <X className="h-4 w-4" />
                  Close Form
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  Create New Document
                </>
              )}
            </Button>
          </motion.div>
        </div>
        <div className="absolute inset-0 bg-grid-white/5 [mask-image:radial-gradient(ellipse_at_center,white,transparent)]" />
      </motion.div>

      {/* Create form (animated) */}
      <AnimatePresence>
        {createExpanded && (
          <motion.div
            initial={{ opacity: 0, y: -20, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, y: -20, height: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <Card className="relative border-0 shadow-lg overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent" />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-4 top-4 h-8 w-8 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive z-10"
                onClick={closeCreateForm}
              >
                <X className="h-4 w-4" />
              </Button>
              
              <CardHeader className="relative pb-2">
                <CardTitle className="text-xl flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                    <FileOutput className="h-4 w-4 text-primary" />
                  </div>
                  Generate New Document
                </CardTitle>
                <CardDescription>
                  Our AI will help you create professional marketing documents based on your requirements
                </CardDescription>
              </CardHeader>
              
              <CardContent className="relative">
                <form onSubmit={handleCreate} className="space-y-6">
                  <div className="grid gap-6 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Document Type</Label>
                      <Select value={documentType} onValueChange={(v) => { setDocumentType(v); setResult(null); setError(null); }}>
                        <SelectTrigger className="h-11">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DOCUMENT_TYPES.map((t) => {
                            const Icon = t.icon;
                            return (
                              <SelectItem key={t.value} value={t.value}>
                                <div className="flex items-center gap-2">
                                  <Icon className={cn("h-4 w-4", t.color)} />
                                  <span>{t.label}</span>
                                </div>
                              </SelectItem>
                            );
                          })}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-sm font-medium">
                        Campaign {documentType === 'report' || documentType === 'brief' ? '(required)' : '(optional)'}
                      </Label>
                      <Select
                        value={campaignId || (documentType === 'report' || documentType === 'brief' ? '__required__' : '__none__')}
                        onValueChange={(v) => setCampaignId(v === '__none__' || v === '__required__' ? '' : v)}
                      >
                        <SelectTrigger className="h-11">
                          <SelectValue placeholder={documentType === 'report' || documentType === 'brief' ? 'Select campaign (required)' : 'Select campaign'} />
                        </SelectTrigger>
                        <SelectContent>
                          {documentType !== 'report' && documentType !== 'brief' && (
                            <SelectItem value="__none__">No campaign (general document)</SelectItem>
                          )}
                          {(documentType === 'report' || documentType === 'brief') && (
                            <SelectItem value="__required__" disabled>Select campaign (required)</SelectItem>
                          )}
                          {campaigns.map((c) => (
                            <SelectItem key={c.id} value={String(c.id)}>
                              <div className="flex items-center gap-2">
                                <span>{c.name}</span>
                                {c.status && (
                                  <Badge variant="outline" className="text-[10px] h-4">
                                    {c.status}
                                  </Badge>
                                )}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Document Title (optional)</Label>
                    <Input 
                      placeholder="e.g., Q1 2024 Marketing Strategy" 
                      value={title} 
                      onChange={(e) => setTitle(e.target.value)} 
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Notes & Key Points (optional)</Label>
                    <Textarea 
                      placeholder="Add any specific requirements, context, or points to include..." 
                      value={notes} 
                      onChange={(e) => setNotes(e.target.value)} 
                      rows={4} 
                      className="resize-none"
                    />
                  </div>

                  <AnimatePresence>
                    {error && (
                      <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20"
                      >
                        <div className="flex items-center gap-2">
                          <AlertCircle className="h-4 w-4" />
                          {error}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div className="flex justify-end gap-3">
                    <Button 
                      type="button" 
                      variant="outline" 
                      onClick={closeCreateForm}
                      className="gap-2"
                    >
                      Cancel
                    </Button>
                    <Button 
                      type="submit" 
                      disabled={loadingCreate}
                      className="gap-2 min-w-[120px]"
                    >
                      {loadingCreate ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Generating...
                        </>
                      ) : (
                        <>
                          <Zap className="h-4 w-4" />
                          Generate Document
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Search and filters */}
      <motion.div variants={itemVariants}>
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4">
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search documents by title or content..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 h-10"
                  />
                  {searchQuery && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
                      onClick={() => setSearchQuery('')}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-10 w-10 shrink-0"
                  onClick={() => setShowFilters(!showFilters)}
                >
                  <Filter className={cn("h-4 w-4", showFilters && "text-primary")} />
                </Button>
                {(filterType || filterCampaignId || searchQuery) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearFilters}
                    className="h-10 gap-1"
                  >
                    <X className="h-3 w-3" />
                    Clear
                  </Button>
                )}
              </div>

              <AnimatePresence>
                {showFilters && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-muted-foreground">Document Type</Label>
                        <Select value={filterType || '__all__'} onValueChange={(v) => setFilterType(v === '__all__' ? '' : v)}>
                          <SelectTrigger className="h-9">
                            <SelectValue placeholder="All types" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__all__">All types</SelectItem>
                            {DOCUMENT_TYPES.map((t) => (
                              <SelectItem key={t.value} value={t.value}>
                                <div className="flex items-center gap-2">
                                  <t.icon className={cn("h-3 w-3", t.color)} />
                                  {t.label}
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-muted-foreground">Campaign</Label>
                        <Select value={filterCampaignId || '__all__'} onValueChange={(v) => setFilterCampaignId(v === '__all__' ? '' : v)}>
                          <SelectTrigger className="h-9">
                            <SelectValue placeholder="All campaigns" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__all__">All campaigns</SelectItem>
                            {campaigns.map((c) => (
                              <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Document list */}
      <motion.div variants={itemVariants}>
        <Card className="overflow-hidden border-0 shadow-lg">
          <CardContent className="p-0">
            {loadingList ? (
              <div className="flex flex-col items-center justify-center py-24">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 className="h-12 w-12 text-primary" />
                </motion.div>
                <p className="mt-4 text-sm text-muted-foreground">Loading documents...</p>
              </div>
            ) : documents.length === 0 ? (
              <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center justify-center py-24 px-4 text-center"
              >
                <div className="rounded-full bg-muted p-4 mb-4">
                  <FolderOpen className="h-12 w-12 text-muted-foreground/60" />
                </div>
                <h3 className="text-lg font-semibold mb-2">No documents found</h3>
                <p className="text-sm text-muted-foreground max-w-md mb-6">
                  {filterType || filterCampaignId || searchQuery 
                    ? 'No documents match your filters. Try adjusting them or clear filters.' 
                    : 'Get started by creating your first marketing document with AI.'}
                </p>
                {(filterType || filterCampaignId || searchQuery) ? (
                  <Button variant="outline" onClick={clearFilters} className="gap-2">
                    <X className="h-4 w-4" />
                    Clear Filters
                  </Button>
                ) : (
                  <Button onClick={() => setCreateExpanded(true)} className="gap-2">
                    <Plus className="h-4 w-4" />
                    Create Document
                  </Button>
                )}
              </motion.div>
            ) : (
              <>
                <div className="overflow-x-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="text-left font-semibold p-4 text-muted-foreground">Document</th>
                        <th className="text-left font-semibold p-4 text-muted-foreground">Campaign</th>
                        <th className="text-left font-semibold p-4 text-muted-foreground">Type</th>
                        <th className="text-left font-semibold p-4 text-muted-foreground">Created</th>
                        <th className="w-20 p-4 text-muted-foreground text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <AnimatePresence>
                        {documents.map((doc, index) => {
                          const Icon = getDocumentIcon(doc.document_type);
                          
                          return (
                            <motion.tr
                              key={doc.id}
                              variants={tableRowVariants}
                              initial="hidden"
                              animate="visible"
                              whileHover="hover"
                              exit={{ opacity: 0, x: -20 }}
                              transition={{ delay: index * 0.05 }}
                              className={cn(
                                'border-b last:border-0 cursor-pointer transition-colors',
                                selectedDocumentId === doc.id && 'bg-primary/5'
                              )}
                              onClick={() => openDetail(doc.id)}
                            >
                              <td className="p-4">
                                <div className="flex items-center gap-3">
                                  <div className={cn(
                                    "rounded-lg p-2",
                                    // TYPE_BADGE_CLASS[doc.document_type]?.split(' ')[0] + '/20'
                                  )}>
                                    <Icon className={cn("h-4 w-4", TYPE_BADGE_CLASS[doc.document_type]?.split(' ')[1])} />
                                  </div>
                                  <div>
                                    <p className="font-medium text-foreground">{doc.title || 'Untitled'}</p>
                                    {doc.notes && (
                                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{doc.notes}</p>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="p-4">
                                {doc.campaign_name ? (
                                  <div className="flex items-center gap-2">
                                    <span className="text-foreground">{doc.campaign_name}</span>
                                    {/* {doc.campaign_status && (
                                      <Badge variant="outline" className={cn(
                                        "text-[10px] h-4",
                                        CAMPAIGN_STATUS_BADGE[doc.campaign_status]
                                      )}>
                                        {doc.campaign_status}
                                      </Badge>
                                    )} */}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="p-4">
                                <Badge style ={{padding:'0.15rem 0.5rem', borderRadius:'0.5rem', hover:'none', cursor:'default'}} className ={cn(
                                  "font-medium",
                                  TYPE_BADGE_CLASS[doc.document_type]
                                )}>
                                  {doc.document_type_display}
                                </Badge>
                              </td>
                              <td className="p-4">
                                <div className="flex items-center gap-2 text-muted-foreground">
                                  <Clock className="h-3.5 w-3.5" />
                                  <span className="text-sm tabular-nums">{formatDate(doc.created_at)}</span>
                                </div>
                              </td>
                              <td className="p-4 text-right">
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-8 w-8"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <MoreVertical className="h-4 w-4" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuItem onClick={(e) => { e.stopPropagation(); openDetail(doc.id); }}>
                                      <Eye className="h-4 w-4 mr-2" />
                                      View
                                    </DropdownMenuItem>
                                    <DropdownMenuItem 
                                      onClick={(e) => handleDelete(doc.id, e)}
                                      className="text-destructive focus:text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4 mr-2" />
                                      Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </td>
                            </motion.tr>
                          );
                        })}
                      </AnimatePresence>
                    </tbody>
                  </table>
                </div>

                {pagination.total_pages > 1 && (
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 bg-muted/30"
                  >
                    <p className="text-sm text-muted-foreground">
                      Showing {(pagination.page - 1) * pagination.page_size + 1}–
                      {Math.min(pagination.page * pagination.page_size, pagination.total)} of {pagination.total} documents
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={pagination.page <= 1 || loadingList}
                        onClick={() => setPage((p) => p - 1)}
                        className="gap-1"
                      >
                        <ChevronLeft className="h-4 w-4" />
                        Previous
                      </Button>
                      <span className="text-sm text-muted-foreground tabular-nums min-w-[100px] text-center">
                        Page {pagination.page} of {pagination.total_pages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={pagination.page >= pagination.total_pages || loadingList}
                        onClick={() => setPage((p) => p + 1)}
                        className="gap-1"
                      >
                        Next
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </motion.div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Document detail modal */}
      <Dialog open={!!selectedDocumentId} onOpenChange={(open) => !open && setSelectedDocumentId(null)}>
        <DialogContent className="max-w-6xl w-[95vw] max-h-[90vh] overflow-hidden flex flex-col gap-0 p-0 border-0 shadow-2xl">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col h-full"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b bg-gradient-to-r from-primary/5 via-transparent to-transparent px-6 py-4 shrink-0">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  {detailDoc && (
                    <div className={cn(
                      "rounded-lg p-2",
                      // TYPE_BADGE_CLASS[detailDoc.document_type]?.split(' ')[0] + '/20'
                    )}>
                      {(() => {
                        const Icon = getDocumentIcon(detailDoc.document_type);
                        return <Icon className={cn("h-5 w-5", TYPE_BADGE_CLASS[detailDoc.document_type]?.split(' ')[1])} />;
                      })()}
                    </div>
                  )}
                  <DialogTitle className="text-xl font-semibold truncate">
                    {detailDoc?.title || 'Document'}
                  </DialogTitle>
                </div>
                
                {detailDoc && (
                  <div className="flex flex-wrap items-center gap-3 mt-3">
                    {/* <Badge className={cn("font-medium", TYPE_BADGE_CLASS[detailDoc.document_type])}>
                      {detailDoc.document_type_display}
                    </Badge> */}
                    
                    {detailDoc.campaign_name && (
                      <>
                        <span className="text-sm text-muted-foreground">•</span>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">Campaign:</span>
                          <span className="text-sm">{detailDoc.campaign_name}</span>
                          {detailDoc.campaign_status_display && (
                            <Badge variant="outline" className={cn(
                              "text-xs",
                              CAMPAIGN_STATUS_BADGE[detailDoc.campaign_status]
                            )}>
                              {detailDoc.campaign_status_display}
                            </Badge>
                          )}
                        </div>
                      </>
                    )}
                    
                    <span className="text-sm text-muted-foreground">•</span>
                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                      <Calendar className="h-3.5 w-3.5" />
                      {formatDate(detailDoc.created_at)}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Toolbar */}
            {detailDoc && (
              <div className="flex items-center justify-between gap-4 px-6 py-3 border-b bg-muted/30 shrink-0">
                <div className="flex items-center gap-2">
                  {detailDoc.available_formats?.length > 0 && (
                    <>
                      <span className="text-sm font-medium text-muted-foreground">Download as:</span>
                      {detailDoc.available_formats.map(({ code, name }) => (
                        <motion.div
                          key={code}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 bg-background"
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
                        </motion.div>
                      ))}
                    </>
                  )}
                </div>
                
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
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
                </motion.div>
              </div>
            )}

            {/* Content */}
            <div className="flex-1 overflow-y-auto min-h-0 bg-muted/10">
              {loadingDetail ? (
                <div className="flex flex-col items-center justify-center py-24">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  >
                    <Loader2 className="h-12 w-12 text-primary" />
                  </motion.div>
                  <p className="mt-4 text-sm text-muted-foreground">Loading document content...</p>
                </div>
              ) : detailDoc ? (
                <motion.div 
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-6"
                >
                  <div className="prose prose-sm dark:prose-invert max-w-none rounded-xl border bg-card p-8 shadow-sm">
                    {detailDoc.content ? (
                      <div className="whitespace-pre-wrap font-sans text-[15px] leading-relaxed">
                        {detailDoc.content}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12 text-center">
                        <FileText className="h-12 w-12 text-muted-foreground/30 mb-4" />
                        <p className="text-muted-foreground">No content available for this document.</p>
                      </div>
                    )}
                  </div>
                </motion.div>
              ) : null}
            </div>
          </motion.div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};

export default Documents;