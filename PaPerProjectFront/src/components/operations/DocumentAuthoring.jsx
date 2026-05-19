import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  PenTool, Sparkles, FileText, Loader2, Plus, Trash2, Save, Search,
  RefreshCw, Copy, X, ChevronsLeft, ChevronsRight,
  Eye, Code, Pencil, History, Layers, ChevronDown, Zap,
} from 'lucide-react';
import * as operationsService from '@/services/operationsAgentService';
import ExportMenu from './ExportMenu';
import TemplatePickerDialog from './TemplatePickerDialog';
import ReferenceDocsPickerDialog from './ReferenceDocsPickerDialog';
import ConfirmDialog from './ConfirmDialog';
import {
  TEMPLATES, TONES, getTemplate, getTone,
  AUTHORING_ACCENT as ACCENT_SHARED,
} from './authoringConstants';

// ──────────────────────────────────────────────
// Theming — matches the rest of the Operations module (amber/orange)
// ──────────────────────────────────────────────
const ACCENT = '#f59e0b';
const ACCENT_SOFT = 'rgba(245,158,11,0.12)';
const ACCENT_BORDER = 'rgba(245,158,11,0.28)';
const ACCENT_STRONG = 'rgba(245,158,11,0.40)';

// ──────────────────────────────────────────────
// Markdown renderer (amber accent)
// ──────────────────────────────────────────────
function markdownToHtml(md) {
  if (!md || typeof md !== 'string') return '';
  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => {
    let out = escape(s);
    out = out.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-white/10 text-amber-200 text-[0.85em] font-mono">$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-amber-200">$1</strong>');
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em class="italic text-white/85">$2</em>');
    return out;
  };

  const getIndent = (line) => {
    const m = line.match(/^(\s*)(?:[-*•]|\d+\.)\s+/);
    if (!m) return -1;
    return Math.floor(m[1].length / 2);
  };

  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let listDepth = -1;
  const closeLists = (target) => { while (listDepth > target) { out.push('</ul>'); listDepth--; } };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    if (t.startsWith('|') && t.endsWith('|')) {
      closeLists(-1);
      const rows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map((c) => c.trim()).filter(Boolean);
        if (cells.length && cells.every((c) => /^[-:\s]+$/.test(c))) { j++; continue; }
        rows.push(cells);
        j++;
      }
      i = j;
      if (rows.length) {
        out.push('<div class="my-4 overflow-x-auto rounded-lg border border-white/10">');
        out.push('<table class="w-full text-sm"><thead><tr class="bg-amber-500/10">');
        rows[0].forEach((c) => out.push(`<th class="px-3 py-2 text-left font-semibold text-amber-300">${inline(c)}</th>`));
        out.push('</tr></thead><tbody>');
        rows.slice(1).forEach((r, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-white/[0.02]' : ''} hover:bg-white/[0.04]">`);
          r.forEach((c) => out.push(`<td class="px-3 py-2 border-t border-white/5 text-white/85">${inline(c)}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }

    if (/^---+$/.test(t)) { closeLists(-1); out.push('<hr class="my-5 border-white/10" />'); i++; continue; }
    if (/^#### /.test(t)) { closeLists(-1); out.push(`<h4 class="text-sm font-semibold mt-3 mb-1.5 text-amber-100/90">${inline(t.slice(5))}</h4>`); i++; continue; }
    if (/^### /.test(t))  { closeLists(-1); out.push(`<h3 class="text-base font-bold mt-5 mb-2 text-amber-200">${inline(t.slice(4))}</h3>`); i++; continue; }
    if (/^## /.test(t))   { closeLists(-1); out.push(`<h2 class="text-lg font-bold mt-6 mb-2.5 text-amber-300 border-b border-amber-500/20 pb-1.5">${inline(t.slice(3))}</h2>`); i++; continue; }
    if (/^# /.test(t))    { closeLists(-1); out.push(`<h1 class="text-2xl font-bold mt-2 mb-4 text-white">${inline(t.slice(2))}</h1>`); i++; continue; }

    const indent = getIndent(line);
    if (indent >= 0) {
      const content = t.replace(/^[\s]*(?:[-*•]|\d+\.)\s+/, '');
      if (indent > listDepth) {
        while (listDepth < indent) {
          const isTop = listDepth === -1;
          out.push(`<ul class="${isTop ? 'pl-4 my-2 space-y-1.5' : 'pl-5 mt-1 mb-1 space-y-1 border-l border-white/[0.06]'}">`);
          listDepth++;
        }
      } else if (indent < listDepth) {
        closeLists(indent);
      }
      const bullet = indent === 0 ? '•' : '›';
      const color = indent === 0 ? 'text-amber-400' : 'text-white/30';
      const textColor = indent === 0 ? 'text-white/90' : 'text-white/70';
      out.push(
        `<li class="text-sm leading-relaxed ${textColor} flex gap-2 ${indent === 0 ? 'pt-1' : ''}">` +
        `<span class="${color} shrink-0 mt-0.5">${bullet}</span><span>${inline(content)}</span></li>`,
      );
      i++; continue;
    }

    if (t === '' && listDepth >= 0) {
      let k = i + 1;
      while (k < lines.length && lines[k].trim() === '') k++;
      if (k >= lines.length || getIndent(lines[k]) < 0) closeLists(-1);
      i++; continue;
    }
    if (t === '') { i++; continue; }

    closeLists(-1);
    out.push(`<p class="text-sm leading-relaxed text-white/85 my-2.5">${inline(t)}</p>`);
    i++;
  }
  closeLists(-1);
  return out.join('\n');
}

// ──────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────
const DocumentAuthoring = () => {
  const { toast } = useToast();

  // view: 'create' | 'view'
  const [view, setView] = useState('create');
  const [showSidebar, setShowSidebar] = useState(true);

  // History list
  const [generatedDocs, setGeneratedDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [sidebarSearch, setSidebarSearch] = useState('');

  // Create form state
  const [template, setTemplate] = useState('weekly_report');
  const [tone, setTone] = useState('formal');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [availableDocs, setAvailableDocs] = useState([]);
  const [selectedRefIds, setSelectedRefIds] = useState([]);
  const [loadingAvailable, setLoadingAvailable] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Picker dialogs
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const [refsPickerOpen, setRefsPickerOpen] = useState(false);

  // Reusable confirm dialog — holds the active prompt's config
  const [confirmState, setConfirmState] = useState(null);
  // Shape: { title, description, confirmLabel, variant, onConfirm, loading }
  const closeConfirm = () => setConfirmState(null);

  // Streaming state
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingTitle, setStreamingTitle] = useState('');
  const streamAbortRef = useRef(null);

  // Current doc (view mode)
  const [currentDoc, setCurrentDoc] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [tab, setTab] = useState('preview'); // preview | edit-markdown

  const scrollRef = useRef(null);

  // ──────────────────────────────────────────────
  // Data loaders
  // ──────────────────────────────────────────────
  const loadGenerated = useCallback(async () => {
    try {
      setLoadingDocs(true);
      const res = await operationsService.listGeneratedDocuments({ page_size: 50 });
      if (res?.status === 'success') {
        setGeneratedDocs(res.documents || []);
      }
    } catch (err) {
      console.error('Load generated docs failed:', err);
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  const loadAvailable = useCallback(async () => {
    try {
      setLoadingAvailable(true);
      const res = await operationsService.listDocuments({ page_size: 50, is_processed: true });
      if (res?.status === 'success') {
        setAvailableDocs(res.documents || []);
      }
    } catch (err) {
      console.error('Load available docs failed:', err);
    } finally {
      setLoadingAvailable(false);
    }
  }, []);

  useEffect(() => {
    loadGenerated();
    loadAvailable();
  }, [loadGenerated, loadAvailable]);

  // ──────────────────────────────────────────────
  // Actions
  // ──────────────────────────────────────────────
  const handleGenerate = async () => {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) {
      toast({ title: 'Prompt required', description: 'Describe what you want the AI to write.', variant: 'destructive' });
      return;
    }

    // Enter streaming mode — switch to view area with a live panel
    setGenerating(true);
    setIsStreaming(true);
    setStreamingContent('');
    setStreamingTitle(title.trim() || 'Generating...');
    setCurrentDoc(null);
    setView('view');
    setEditMode(false);
    setTab('preview');

    const controller = new AbortController();
    streamAbortRef.current = controller;

    const autoScroll = () => {
      requestAnimationFrame(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    };

    try {
      await operationsService.streamGenerateDocument(
        {
          prompt: cleanPrompt,
          template_type: template,
          tone,
          title: title.trim() || undefined,
          reference_document_ids: selectedRefIds.length ? selectedRefIds : undefined,
        },
        {
          signal: controller.signal,
          onMeta: (meta) => {
            if (meta?.title) setStreamingTitle(meta.title);
          },
          onText: (chunk) => {
            setStreamingContent((prev) => prev + (chunk || ''));
            autoScroll();
          },
          onDone: (payload) => {
            const doc = payload?.document;
            if (doc) {
              setCurrentDoc(doc);
              setEditTitle(doc.title);
              setEditContent(doc.content);
              loadGenerated();
              toast({ title: 'Document ready', description: `"${doc.title}" generated.` });
            }
            setIsStreaming(false);
            setStreamingContent('');
            setStreamingTitle('');
            requestAnimationFrame(() => {
              if (scrollRef.current) scrollRef.current.scrollTop = 0;
            });
          },
          onError: (message, meta) => {
            setIsStreaming(false);
            setStreamingContent('');
            setStreamingTitle('');
            setView('create');
            const isQuota = meta?.status === 402 || meta?.error_code === 'quota_exhausted' || meta?.error_code === 'no_key';
            toast({
              title: isQuota ? 'Token Limit Reached' : 'Generation failed',
              description: message || (isQuota ? 'Token quota exhausted. Add your own API key or request a managed key.' : 'Please try again.'),
              variant: 'destructive',
            });
          },
        },
      );
    } catch (err) {
      setIsStreaming(false);
      setStreamingContent('');
      setStreamingTitle('');
      setView('create');
      if (err?.name !== 'AbortError') {
        const isQuota = err?.status === 402;
        toast({
          title: isQuota ? 'Token Limit Reached' : 'Generation failed',
          description: isQuota
            ? (err.message || 'Token quota exhausted. Add your own API key or request a managed key.')
            : (err?.message || 'Please try again.'),
          variant: 'destructive',
        });
      }
    } finally {
      setGenerating(false);
      streamAbortRef.current = null;
    }
  };

  const handleCancelStream = () => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }
    setIsStreaming(false);
    setStreamingContent('');
    setStreamingTitle('');
    setGenerating(false);
    setView('create');
  };

  const openDoc = async (docId) => {
    try {
      const res = await operationsService.getGeneratedDocument(docId);
      if (res?.status === 'success' && res.document) {
        setCurrentDoc(res.document);
        setEditTitle(res.document.title);
        setEditContent(res.document.content);
        setView('view');
        setEditMode(false);
        setTab('preview');
        requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; });
      } else {
        throw new Error(res?.message || 'Failed to load document');
      }
    } catch (err) {
      toast({
        title: 'Could not open document',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    }
  };

  const handleNewDocument = () => {
    setView('create');
    setCurrentDoc(null);
    setEditMode(false);
    setPrompt('');
    setTitle('');
    setSelectedRefIds([]);
  };

  const handleSave = async () => {
    if (!currentDoc) return;
    const cleanTitle = editTitle.trim();
    const hasChanges = cleanTitle !== currentDoc.title || editContent !== currentDoc.content;
    if (!hasChanges) {
      setEditMode(false);
      return;
    }
    try {
      setSaving(true);
      const res = await operationsService.updateGeneratedDocument(currentDoc.id, {
        title: cleanTitle || currentDoc.title,
        content: editContent,
      });
      if (res?.status === 'success' && res.document) {
        setCurrentDoc(res.document);
        setEditTitle(res.document.title);
        setEditContent(res.document.content);
        setEditMode(false);
        loadGenerated();
        toast({ title: 'Saved', description: `Version ${res.document.version}` });
      } else {
        throw new Error(res?.message || 'Save failed');
      }
    } catch (err) {
      toast({
        title: 'Save failed',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const performRegenerate = async () => {
    if (!currentDoc) return;
    try {
      setConfirmState((prev) => (prev ? { ...prev, loading: true } : prev));
      setRegenerating(true);
      const res = await operationsService.regenerateDocument(currentDoc.id);
      if (res?.status === 'success' && res.document) {
        setCurrentDoc(res.document);
        setEditTitle(res.document.title);
        setEditContent(res.document.content);
        setEditMode(false);
        loadGenerated();
        toast({ title: 'Regenerated', description: `New version: ${res.document.version}` });
        requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; });
      } else {
        throw new Error(res?.message || 'Regeneration failed');
      }
    } catch (err) {
      toast({
        title: 'Regeneration failed',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setRegenerating(false);
      closeConfirm();
    }
  };

  const handleRegenerate = () => {
    if (!currentDoc) return;
    setConfirmState({
      title: 'Regenerate this document?',
      description: (
        <>
          The current version will be archived in history, and version number will bump to{' '}
          <strong className="text-amber-300">v{currentDoc.version + 1}</strong>.
        </>
      ),
      confirmLabel: 'Regenerate',
      variant: 'default',
      onConfirm: performRegenerate,
    });
  };

  const performDeleteCurrent = async () => {
    if (!currentDoc) return;
    try {
      setConfirmState((prev) => (prev ? { ...prev, loading: true } : prev));
      const res = await operationsService.deleteGeneratedDocument(currentDoc.id);
      if (res?.status === 'success') {
        setGeneratedDocs((prev) => prev.filter((d) => d.id !== currentDoc.id));
        handleNewDocument();
        toast({ title: 'Deleted' });
      } else {
        throw new Error(res?.message || 'Delete failed');
      }
    } catch (err) {
      toast({
        title: 'Delete failed',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      closeConfirm();
    }
  };

  const handleDelete = () => {
    if (!currentDoc) return;
    setConfirmState({
      title: `Delete "${currentDoc.title}"?`,
      description: 'This action cannot be undone. The document and its edit history will be permanently removed.',
      confirmLabel: 'Delete',
      variant: 'danger',
      onConfirm: performDeleteCurrent,
    });
  };

  const performDeleteFromSidebar = async (doc) => {
    try {
      setConfirmState((prev) => (prev ? { ...prev, loading: true } : prev));
      const res = await operationsService.deleteGeneratedDocument(doc.id);
      if (res?.status === 'success') {
        setGeneratedDocs((prev) => prev.filter((d) => d.id !== doc.id));
        if (currentDoc?.id === doc.id) handleNewDocument();
        toast({ title: 'Deleted' });
      } else {
        throw new Error(res?.message || 'Delete failed');
      }
    } catch (err) {
      toast({ title: 'Error', description: err?.message || 'Could not delete', variant: 'destructive' });
    } finally {
      closeConfirm();
    }
  };

  const handleDeleteFromSidebar = (e, doc) => {
    e.stopPropagation();
    setConfirmState({
      title: `Delete "${doc.title}"?`,
      description: 'This action cannot be undone.',
      confirmLabel: 'Delete',
      variant: 'danger',
      onConfirm: () => performDeleteFromSidebar(doc),
    });
  };

  const handleCopy = async () => {
    if (!currentDoc?.content) return;
    try {
      await navigator.clipboard.writeText(currentDoc.content);
      toast({ title: 'Copied to clipboard' });
    } catch {
      toast({ title: 'Copy failed', description: 'Clipboard unavailable', variant: 'destructive' });
    }
  };


  const filteredSidebar = useMemo(() => {
    const q = sidebarSearch.trim().toLowerCase();
    if (!q) return generatedDocs;
    return generatedDocs.filter((d) => (d.title || '').toLowerCase().includes(q));
  }, [generatedDocs, sidebarSearch]);

  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const same = d.toDateString() === now.toDateString();
      return same
        ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
        : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };


  // ──────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────
  return (
    <div
      className="w-full rounded-2xl border border-amber-500/10 overflow-hidden shadow-[0_8px_40px_-12px_rgba(245,158,11,0.15)]"
      style={{
        background: 'linear-gradient(135deg, #1a1333 0%, #1a1333 45%, rgba(64,40,10,0.55) 100%)',
      }}
    >
      <div className="flex w-full max-w-full relative" style={{ height: 'calc(100vh - 120px)', minHeight: 680 }}>
        {/* ── Sidebar ── */}
        <div
          className={`shrink-0 transition-all duration-300 ease-in-out border-r border-white/10 ${
            showSidebar ? 'w-72 opacity-100' : 'w-0 opacity-0 border-0'
          }`}
          style={{ minWidth: showSidebar ? '18rem' : 0, overflow: 'hidden' }}
        >
          <div className="w-72 h-full flex flex-col bg-black/30">
            <div className="px-3 pt-3 pb-2 border-b border-white/10 flex flex-col gap-2 shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="flex items-center justify-center w-8 h-8 rounded-lg"
                    style={{ backgroundColor: ACCENT_SOFT }}
                  >
                    <PenTool className="h-4 w-4" style={{ color: ACCENT }} />
                  </div>
                  <span className="text-sm font-semibold text-white/90">My documents</span>
                </div>
                <button
                  onClick={() => setShowSidebar(false)}
                  title="Hide sidebar"
                  className="h-7 w-7 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/20 hover:bg-white/5 transition-colors"
                >
                  <ChevronsLeft className="h-3.5 w-3.5 text-white/70" />
                </button>
              </div>

              <Button
                onClick={handleNewDocument}
                size="sm"
                className="text-xs h-8 w-full font-semibold"
                style={{ backgroundColor: ACCENT, color: '#1a0e00', border: 'none' }}
              >
                <Plus className="h-3.5 w-3.5 mr-1" /> New document
              </Button>

              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/40" />
                <input
                  value={sidebarSearch}
                  onChange={(e) => setSidebarSearch(e.target.value)}
                  placeholder="Search..."
                  className="w-full bg-black/30 border border-white/10 rounded-md pl-8 pr-2.5 py-1.5 text-xs text-white/90 placeholder-white/40 focus:outline-none focus:border-amber-500/40"
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
              {loadingDocs ? (
                <div className="flex items-center justify-center h-24 text-white/50 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading...
                </div>
              ) : filteredSidebar.length === 0 ? (
                <div className="text-center text-white/40 text-xs px-2 py-6">
                  {sidebarSearch ? 'No matches.' : 'No documents yet. Generate your first one!'}
                </div>
              ) : (
                filteredSidebar.map((d) => {
                  const tpl = TEMPLATES.find((t) => t.value === d.template_type);
                  const Icon = tpl?.icon || FileText;
                  const isActive = currentDoc?.id === d.id && view === 'view';
                  return (
                    <div
                      key={d.id}
                      onClick={() => openDoc(d.id)}
                      className={`group relative rounded-lg px-2.5 py-2 cursor-pointer transition-colors ${
                        isActive ? 'bg-amber-500/10 border border-amber-500/25' : 'hover:bg-white/[0.04] border border-transparent'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <div
                          className="flex items-center justify-center w-7 h-7 rounded-md shrink-0 mt-0.5"
                          style={{ backgroundColor: ACCENT_SOFT }}
                        >
                          <Icon className="h-3.5 w-3.5" style={{ color: ACCENT }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-white/90 font-medium truncate">
                            {d.title || 'Untitled'}
                          </div>
                          <div className="text-[10px] text-white/40 mt-0.5 flex items-center gap-1.5">
                            <span className="truncate">{tpl?.label || d.template_type}</span>
                            <span>•</span>
                            <span>v{d.version}</span>
                            <span>•</span>
                            <span>{formatDate(d.updated_at)}</span>
                          </div>
                        </div>
                        <button
                          onClick={(e) => handleDeleteFromSidebar(e, d)}
                          title="Delete"
                          className="opacity-0 group-hover:opacity-100 h-6 w-6 flex items-center justify-center rounded hover:bg-red-500/20 shrink-0 transition-opacity"
                        >
                          <Trash2 className="h-3 w-3 text-white/60 hover:text-red-400" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* ── Main area ── */}
        <div className="flex-1 flex flex-col min-w-0">
          {view === 'create' ? (
            <CreateView
              template={template}
              tone={tone}
              setTone={setTone}
              title={title}
              setTitle={setTitle}
              prompt={prompt}
              setPrompt={setPrompt}
              availableDocs={availableDocs}
              selectedRefIds={selectedRefIds}
              onClearRefs={() => setSelectedRefIds([])}
              onOpenTemplatePicker={() => setTemplatePickerOpen(true)}
              onOpenRefsPicker={() => setRefsPickerOpen(true)}
              generating={generating}
              onGenerate={handleGenerate}
              showSidebar={showSidebar}
              setShowSidebar={setShowSidebar}
            />
          ) : isStreaming ? (
            <StreamingView
              scrollRef={scrollRef}
              title={streamingTitle}
              content={streamingContent}
              onCancel={handleCancelStream}
              showSidebar={showSidebar}
              setShowSidebar={setShowSidebar}
            />
          ) : (
            <ViewView
              scrollRef={scrollRef}
              doc={currentDoc}
              editMode={editMode}
              setEditMode={setEditMode}
              editTitle={editTitle}
              setEditTitle={setEditTitle}
              editContent={editContent}
              setEditContent={setEditContent}
              saving={saving}
              regenerating={regenerating}
              tab={tab}
              setTab={setTab}
              onSave={handleSave}
              onRegenerate={handleRegenerate}
              onDelete={handleDelete}
              onCopy={handleCopy}
              onBack={handleNewDocument}
              showSidebar={showSidebar}
              setShowSidebar={setShowSidebar}
            />
          )}
        </div>
      </div>

      <TemplatePickerDialog
        open={templatePickerOpen}
        value={template}
        onChange={setTemplate}
        onOpenChange={setTemplatePickerOpen}
      />
      <ReferenceDocsPickerDialog
        open={refsPickerOpen}
        docs={availableDocs}
        loading={loadingAvailable}
        value={selectedRefIds}
        onChange={setSelectedRefIds}
        onOpenChange={setRefsPickerOpen}
      />
      <ConfirmDialog
        open={!!confirmState}
        onOpenChange={(next) => { if (!next) closeConfirm(); }}
        title={confirmState?.title}
        description={confirmState?.description}
        confirmLabel={confirmState?.confirmLabel}
        variant={confirmState?.variant}
        loading={!!confirmState?.loading}
        onConfirm={confirmState?.onConfirm}
      />
    </div>
  );
};

// ──────────────────────────────────────────────
// Create view
// ──────────────────────────────────────────────
const CreateView = ({
  template, tone, setTone, title, setTitle, prompt, setPrompt,
  availableDocs, selectedRefIds, onClearRefs,
  onOpenTemplatePicker, onOpenRefsPicker,
  generating, onGenerate, showSidebar, setShowSidebar,
}) => {
  const tpl = getTemplate(template);
  const TplIcon = tpl.icon;

  return (
    <>
      {/* Header */}
      <div className="px-6 py-4 border-b border-white/10 flex items-center gap-3 bg-black/25">
        {!showSidebar && (
          <button
            onClick={() => setShowSidebar(true)}
            title="Show sidebar"
            className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/30 hover:bg-white/5 transition-colors"
          >
            <ChevronsRight className="h-4 w-4 text-white/70" />
          </button>
        )}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div
            className="flex items-center justify-center w-10 h-10 rounded-xl shrink-0"
            style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
          >
            <Sparkles className="h-5 w-5" style={{ color: ACCENT }} />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white/95">Create a new document</div>
            <div className="text-xs text-white/55">AI-authored, referencing your uploaded documents.</div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className={`mx-auto space-y-4 transition-[max-width] duration-300 ${showSidebar ? 'max-w-3xl' : 'max-w-5xl'}`}>

          {/* Compact config row: Template + References */}
          <div className="grid sm:grid-cols-2 gap-3">
            {/* Template selector */}
            <SelectorCard
              label="Template"
              onClick={onOpenTemplatePicker}
              primaryText={tpl.label}
              secondaryText={tpl.description}
              icon={<TplIcon className="h-4 w-4" style={{ color: ACCENT }} />}
            />

            {/* References selector */}
            <SelectorCard
              label="References"
              onClick={onOpenRefsPicker}
              primaryText={selectedRefIds.length
                ? `${selectedRefIds.length} document${selectedRefIds.length === 1 ? '' : 's'} selected`
                : 'No references selected'}
              secondaryText={selectedRefIds.length
                ? 'Tap to change selection'
                : `${availableDocs.length} documents available`}
              icon={<Layers className="h-4 w-4" style={{ color: ACCENT }} />}
              trailingAction={selectedRefIds.length > 0 ? (
                <button
                  onClick={(e) => { e.stopPropagation(); onClearRefs?.(); }}
                  className="text-[11px] text-amber-300/80 hover:text-amber-200 px-2 py-1"
                  type="button"
                >
                  Clear
                </button>
              ) : null}
            />
          </div>

          {/* Tone pills */}
          <div>
            <Label className="text-[11px] uppercase tracking-wider text-white/55 mb-2 block">
              Tone
            </Label>
            <div className="flex flex-wrap gap-2">
              {TONES.map((t) => {
                const active = tone === t.value;
                return (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setTone(t.value)}
                    className={`rounded-lg border px-3 py-2 text-xs transition-colors flex flex-col items-start gap-0.5 ${
                      active
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-200'
                        : 'border-white/10 bg-white/[0.02] text-white/80 hover:bg-white/[0.06] hover:border-white/25'
                    }`}
                  >
                    <span className="font-semibold">{t.label}</span>
                    <span className="text-[10px] text-white/50">{t.hint}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Title */}
          <div>
            <Label className="text-[11px] uppercase tracking-wider text-white/55 mb-2 block">
              Title <span className="text-white/35 normal-case">(optional)</span>
            </Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={`e.g. ${tpl.label} – Q3 Operations`}
              className="bg-black/30 border-white/10 text-white/95 placeholder-white/35 text-sm h-10 focus-visible:ring-1 focus-visible:ring-amber-500/40 focus-visible:border-amber-500/40"
            />
          </div>

          {/* Prompt — hero field */}
          <div>
            <Label className="text-[11px] uppercase tracking-wider text-white/55 mb-2 block">
              What should the document cover?
            </Label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={`Describe the document you want. Example: "Draft a weekly operations report focusing on the risks from the latest Q3 financial document and recommended mitigation steps."`}
              rows={7}
              className="resize-y bg-black/30 border-white/10 text-white/95 placeholder-white/35 text-sm leading-relaxed focus-visible:ring-1 focus-visible:ring-amber-500/40 focus-visible:border-amber-500/40 min-h-[180px]"
            />
            <p className="text-[11px] text-white/45 mt-1.5">
              Tip: be specific about the audience, key sections, and any data to emphasize.
            </p>
          </div>
        </div>
      </div>

      {/* Footer with CTA */}
      <div className="border-t border-white/10 px-6 py-4 bg-black/25">
        <div className={`mx-auto flex items-center justify-between gap-4 transition-[max-width] duration-300 ${showSidebar ? 'max-w-4xl' : 'max-w-5xl'}`}>
          <div className="text-[11px] text-white/45">
            Powered by AI · Always review before sharing
          </div>
          <Button
            onClick={onGenerate}
            disabled={!prompt.trim() || generating}
            className="h-10 px-5 text-sm font-semibold disabled:opacity-50"
            style={{ backgroundColor: ACCENT, color: '#1a0e00', border: 'none' }}
          >
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                Generate document
              </>
            )}
          </Button>
        </div>
      </div>
    </>
  );
};

// ──────────────────────────────────────────────
// Streaming view — shown while the AI is generating
// ──────────────────────────────────────────────
const StreamingView = ({ scrollRef, title, content, onCancel, showSidebar, setShowSidebar }) => {
  return (
    <>
      {/* Header */}
      <div className="px-6 py-3 border-b border-white/10 flex items-center gap-3 bg-black/25">
        {!showSidebar && (
          <button
            onClick={() => setShowSidebar(true)}
            title="Show sidebar"
            className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/30 hover:bg-white/5 transition-colors"
          >
            <ChevronsRight className="h-4 w-4 text-white/70" />
          </button>
        )}
        <div
          className="flex items-center justify-center w-10 h-10 rounded-xl shrink-0"
          style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
        >
          <Sparkles className="h-5 w-5 animate-pulse" style={{ color: ACCENT }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white/95 truncate">
            {title || 'Generating document...'}
          </div>
          <div className="text-xs text-white/55 flex items-center gap-2 mt-0.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400/70" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400" />
            </span>
            AI is writing...
          </div>
        </div>
        <Button
          onClick={onCancel}
          variant="outline"
          size="sm"
          className="h-8 text-xs border-white/10 bg-transparent text-white/80 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-300"
        >
          <X className="h-3.5 w-3.5 mr-1" /> Cancel
        </Button>
      </div>

      {/* Live content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className={`mx-auto px-8 py-8 transition-[max-width] duration-300 ${showSidebar ? 'max-w-3xl' : 'max-w-5xl'}`}>
          {content ? (
            <article
              className="prose prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(content) + '<span class="inline-block w-[2px] h-4 bg-amber-400 align-middle ml-0.5 animate-pulse" />' }}
            />
          ) : (
            <div className="flex items-center gap-3 text-white/55 text-sm py-10">
              <Loader2 className="h-4 w-4 animate-spin" style={{ color: ACCENT }} />
              Preparing your document...
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// ──────────────────────────────────────────────
// View/Edit view
// ──────────────────────────────────────────────
const ViewView = ({
  scrollRef, doc, editMode, setEditMode, editTitle, setEditTitle,
  editContent, setEditContent, saving, regenerating, tab, setTab,
  onSave, onRegenerate, onDelete, onCopy, onBack,
  showSidebar, setShowSidebar,
}) => {
  if (!doc) {
    return (
      <div className="flex-1 flex items-center justify-center text-white/50 text-sm">
        Loading document...
      </div>
    );
  }
  const tpl = TEMPLATES.find((t) => t.value === doc.template_type);
  const toneLbl = TONES.find((t) => t.value === doc.tone)?.label || doc.tone;

  return (
    <>
      {/* Header */}
      <div className="px-6 py-3 border-b border-white/10 flex items-center gap-3 bg-black/25">
        {!showSidebar && (
          <button
            onClick={() => setShowSidebar(true)}
            title="Show sidebar"
            className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 hover:border-white/30 bg-black/30 hover:bg-white/5 transition-colors"
          >
            <ChevronsRight className="h-4 w-4 text-white/70" />
          </button>
        )}
        <button
          onClick={onBack}
          title="New document"
          className="h-8 px-2.5 flex items-center gap-1.5 rounded-md border border-white/10 hover:border-white/30 bg-black/30 hover:bg-white/5 transition-colors text-xs text-white/75"
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </button>

        <div className="flex items-center gap-2 flex-1 min-w-0">
          {editMode ? (
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="bg-black/30 border-white/10 text-white/95 font-semibold h-9 focus-visible:ring-1 focus-visible:ring-amber-500/40 focus-visible:border-amber-500/40"
              placeholder="Document title"
            />
          ) : (
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white/95 truncate">{doc.title}</div>
              <div className="text-[11px] text-white/50 flex items-center gap-2 mt-0.5">
                {tpl && <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-200 bg-amber-500/10">{tpl.label}</Badge>}
                <Badge variant="outline" className="text-[10px] border-white/10 text-white/70 bg-white/5">{toneLbl}</Badge>
                <span>v{doc.version}</span>
                <span>·</span>
                <span>{doc.word_count} words</span>
                {doc.reference_documents?.length > 0 && (
                  <>
                    <span>·</span>
                    <span>{doc.reference_documents.length} ref{doc.reference_documents.length === 1 ? '' : 's'}</span>
                  </>
                )}
                {doc.tokens_used?.total_tokens ? (
                  <>
                    <span>·</span>
                    <TokenBadge tokens={doc.tokens_used} />
                  </>
                ) : null}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {editMode ? (
            <>
              <Button
                onClick={() => { setEditMode(false); setEditTitle(doc.title); setEditContent(doc.content); }}
                variant="outline"
                size="sm"
                className="h-8 text-xs border-white/10 bg-transparent text-white/80 hover:bg-white/5"
                disabled={saving}
              >
                <X className="h-3.5 w-3.5 mr-1" /> Cancel
              </Button>
              <Button
                onClick={onSave}
                size="sm"
                className="h-8 text-xs font-semibold"
                style={{ backgroundColor: ACCENT, color: '#1a0e00', border: 'none' }}
                disabled={saving}
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Save className="h-3.5 w-3.5 mr-1" />}
                Save
              </Button>
            </>
          ) : (
            <>
              <IconButton title="Copy markdown" onClick={onCopy}><Copy className="h-3.5 w-3.5" /></IconButton>
              <ExportMenu
                docId={doc.id}
                title={doc.title}
                content={doc.content}
                fetchPdfBlob={operationsService.fetchGeneratedDocumentPdf}
              />
              <IconButton title="Edit" onClick={() => { setEditMode(true); setTab('edit-markdown'); }}>
                <Pencil className="h-3.5 w-3.5" />
              </IconButton>
              <IconButton
                title="Regenerate (new version)"
                onClick={onRegenerate}
                disabled={regenerating}
              >
                {regenerating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              </IconButton>
              <IconButton title="Delete" onClick={onDelete} danger>
                <Trash2 className="h-3.5 w-3.5" />
              </IconButton>
            </>
          )}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="px-6 py-2 border-b border-white/10 bg-black/15 flex items-center gap-1">
        <TabButton active={tab === 'preview'} onClick={() => setTab('preview')} icon={Eye}>
          Preview
        </TabButton>
        <TabButton active={tab === 'edit-markdown'} onClick={() => setTab('edit-markdown')} icon={Code}>
          Markdown
        </TabButton>
        {doc.edit_history && doc.edit_history.length > 0 && (
          <div className="ml-auto flex items-center gap-1.5 text-[11px] text-white/45">
            <History className="h-3 w-3" />
            {doc.edit_history.length} edit{doc.edit_history.length === 1 ? '' : 's'}
          </div>
        )}
      </div>

      {/* Content */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {tab === 'preview' ? (
          <div className={`mx-auto px-8 py-8 transition-[max-width] duration-300 ${showSidebar ? 'max-w-3xl' : 'max-w-5xl'}`}>
            <article
              className="prose prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: markdownToHtml(editMode ? editContent : doc.content) }}
            />
          </div>
        ) : (
          <div className="h-full px-6 py-4">
            <Textarea
              value={editMode ? editContent : doc.content}
              onChange={(e) => setEditContent(e.target.value)}
              readOnly={!editMode}
              className="w-full h-full resize-none bg-black/40 border-white/10 text-white/90 text-sm leading-relaxed font-mono focus-visible:ring-1 focus-visible:ring-amber-500/40 focus-visible:border-amber-500/40"
              style={{ minHeight: 'calc(100vh - 360px)' }}
            />
          </div>
        )}
      </div>
    </>
  );
};

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────
/**
 * A compact button-card used for opening pickers (template / references).
 * Keeps the form short by hiding list UI behind a dialog.
 */
/**
 * Compact token-usage pill shown in the document header.
 * Tooltip-ish title attr shows the full breakdown.
 */
const TokenBadge = ({ tokens }) => {
  if (!tokens) return null;
  const total = tokens.total_tokens;
  const prompt = tokens.prompt_tokens;
  const completion = tokens.completion_tokens;
  const estimated = tokens.estimated;
  if (!total) return null;
  const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : '-');
  const tip = `Input: ${fmt(prompt)} tokens · Output: ${fmt(completion)} tokens · Total: ${fmt(total)}${estimated ? ' (estimated)' : ''}`;
  return (
    <span
      title={tip}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/25 text-amber-200 text-[10px] font-medium"
    >
      <Zap className="h-2.5 w-2.5" />
      {fmt(total)} tokens{estimated ? '*' : ''}
    </span>
  );
};

const SelectorCard = ({ label, primaryText, secondaryText, icon, onClick, trailingAction }) => (
  <div>
    <Label className="text-[11px] uppercase tracking-wider text-white/55 mb-2 block">
      {label}
    </Label>
    <button
      type="button"
      onClick={onClick}
      className="group w-full text-left rounded-xl border border-white/10 bg-black/30 hover:bg-white/[0.04] hover:border-amber-500/30 transition-colors px-3 py-2.5 flex items-center gap-3"
    >
      <div
        className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0"
        style={{ backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT_BORDER}` }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-white/95 truncate">{primaryText}</div>
        <div className="text-[11px] text-white/50 truncate">{secondaryText}</div>
      </div>
      {trailingAction}
      <ChevronDown className="h-3.5 w-3.5 text-white/40 group-hover:text-amber-300 shrink-0" />
    </button>
  </div>
);

const IconButton = ({ children, onClick, title, danger = false, disabled = false }) => (
  <button
    onClick={onClick}
    title={title}
    disabled={disabled}
    className={`h-8 w-8 flex items-center justify-center rounded-md border transition-colors ${
      danger
        ? 'border-white/10 bg-black/30 text-white/70 hover:text-red-300 hover:bg-red-500/10 hover:border-red-500/30'
        : 'border-white/10 bg-black/30 text-white/75 hover:text-amber-200 hover:bg-amber-500/10 hover:border-amber-500/30'
    } disabled:opacity-50 disabled:cursor-not-allowed`}
  >
    {children}
  </button>
);

const TabButton = ({ active, onClick, icon: Icon, children }) => (
  <button
    onClick={onClick}
    className={`px-3 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-colors ${
      active
        ? 'bg-amber-500/15 text-amber-200 border border-amber-500/30'
        : 'text-white/65 hover:text-white/90 hover:bg-white/5 border border-transparent'
    }`}
  >
    <Icon className="h-3.5 w-3.5" />
    {children}
  </button>
);

export default DocumentAuthoring;
