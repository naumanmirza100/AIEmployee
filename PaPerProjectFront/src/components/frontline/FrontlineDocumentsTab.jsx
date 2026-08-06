import React from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  FileText, Upload, Loader2, FileSearch, ListChecks, Trash2,
  ChevronUp, ChevronDown,
} from 'lucide-react';
import InfoHint from './InfoHint';
import { HINTS } from './frontlineTutorialSteps';

/**
 * FrontlineDocumentsTab — extracted from the inline `documents` TabsContent
 * in FrontlineDashboard.jsx (Chunk B of FRONTLINE_AGENT_UX_REDESIGN.md).
 *
 * Renders the knowledge-base document grid: format badge, processing status
 * badge, expandable summary, action bar (Summarize / Extract / Outdated /
 * Delete). Purely presentational — all state lives in the parent so both the
 * hidden legacy `documents` TabsContent AND the new KnowledgeView can render
 * this component with identical behaviour and share a single copy of docs
 * data.
 *
 * The Upload dialog itself stays in the parent (mounted outside the tab)
 * because opening it is a state toggle, not a form the tab owns. This
 * component just fires `onOpenUpload` from its header button.
 */
export default function FrontlineDocumentsTab({
  documents,
  docSummaries,
  onOpenUpload,
  onToggleSummary,
  onSummarize,
  onExtract,
  onToggleOutdated,
  onDelete,
}) {
  const docs = Array.isArray(documents) ? documents : [];
  return (
    <Card className="w-full min-w-0">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <CardTitle>Documents</CardTitle>
            <InfoHint {...HINTS.docsGrid} />
          </div>
          <CardDescription>Upload and manage knowledge base documents</CardDescription>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
          <Button data-tour-docs="upload" onClick={onOpenUpload} className="w-full sm:w-auto">
            <Upload className="mr-2 h-4 w-4" />
            Upload Document
          </Button>
          <InfoHint {...HINTS.docsUpload} />
        </div>
      </CardHeader>
      <CardContent>
        {docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
              <FileText className="h-7 w-7 text-violet-400" />
            </div>
            <div className="font-medium mb-1">No documents yet</div>
            <div className="text-sm text-muted-foreground max-w-sm">
              Upload a document to give the knowledge agent something to answer from.
            </div>
          </div>
        ) : (
          <div data-tour-docs="grid" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {docs.map((doc) => (
              <DocCard
                key={doc.id}
                doc={doc}
                summaryState={docSummaries[doc.id]}
                onToggleSummary={onToggleSummary}
                onSummarize={onSummarize}
                onExtract={onExtract}
                onToggleOutdated={onToggleOutdated}
                onDelete={onDelete}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// One card per document. Extracted into its own component so the main grid
// map stays readable — nothing else references it.
function DocCard({ doc, summaryState, onToggleSummary, onSummarize, onExtract, onToggleOutdated, onDelete }) {
  const fmt = (doc.file_format || 'other').toLowerCase();
  const fmtColor = {
    pdf: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
    docx: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
    doc: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
    txt: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
    md: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
    html: 'bg-amber-500/15 text-amber-400 border-amber-400/30',
  }[fmt] || 'bg-violet-500/15 text-violet-400 border-violet-400/30';
  const sizeKB = doc.file_size ? Math.max(1, Math.round(doc.file_size / 1024)) : null;
  const sizeDisplay = sizeKB && sizeKB >= 1024
    ? `${(sizeKB / 1024).toFixed(1)} MB`
    : (sizeKB ? `${sizeKB} KB` : null);
  const procStatus = doc.processing_status || (doc.is_indexed ? 'ready' : 'pending');
  const procLabel = {
    ready: 'Indexed',
    processing: 'Processing',
    pending: 'Queued',
    failed: 'Failed',
  }[procStatus] || procStatus;
  const procColor = {
    ready: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
    processing: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
    pending: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
    failed: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
  }[procStatus] || 'bg-white/[0.04] text-white/55 border-white/[0.08]';

  return (
    <div className="group flex flex-col rounded-xl border border-white/[0.08] bg-gradient-to-br from-white/[0.04] to-white/[0.01] hover:border-violet-400/40 hover:shadow-[0_0_0_1px_rgba(139,92,246,0.15),0_8px_32px_-8px_rgba(139,92,246,0.25)] transition-all duration-200 overflow-hidden">
      {/* Header: format badge + title + status */}
      <div className="p-4 pb-3">
        <div className="flex items-start gap-3">
          <div className={`shrink-0 h-10 w-10 rounded-lg border flex items-center justify-center ${fmtColor}`}>
            <FileText className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="font-medium truncate text-sm" title={doc.title}>{doc.title}</div>
            <div className="mt-0.5 text-xs text-muted-foreground truncate">
              {fmt.toUpperCase()}
              {doc.document_type ? ` • ${doc.document_type.replace(/_/g, ' ')}` : ''}
              {sizeDisplay ? ` • ${sizeDisplay}` : ''}
            </div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-1.5 flex-wrap">
          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${procColor}`}>
            {procLabel}
          </Badge>
          {doc.is_outdated && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-rose-500/10 text-rose-300 border-rose-400/30">
              outdated
            </Badge>
          )}
          {doc.created_at && (
            <span className="text-[10px] text-muted-foreground">
              {new Date(doc.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>

      {/* Expandable summary */}
      <div className="px-4 pb-3 flex-1">
        {summaryState?.expanded ? (
          <div className="rounded-md bg-black/20 border border-white/[0.06] p-3 text-xs text-white/80 space-y-2">
            {summaryState.loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Generating summary...</span>
              </div>
            ) : summaryState.error ? (
              <div className="text-rose-400">{summaryState.error}</div>
            ) : (
              <div className="whitespace-pre-wrap break-words leading-relaxed">
                {summaryState.summary || 'No summary available.'}
              </div>
            )}
            <button
              onClick={() => onToggleSummary(doc)}
              disabled={summaryState.loading}
              className="text-violet-400 hover:text-violet-300 text-[11px] font-medium flex items-center gap-0.5"
            >
              Show less <ChevronUp className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => onToggleSummary(doc)}
            className="text-violet-400 hover:text-violet-300 text-xs font-medium flex items-center gap-0.5"
          >
            Show summary <ChevronDown className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Action bar */}
      <div data-tour-docs="card-actions" className="border-t border-white/[0.06] px-2 py-1.5 flex items-center justify-between bg-black/10">
        <div className="flex items-center">
          <InfoHint {...HINTS.docsCardActions} className="ml-1 mr-2" />
          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => onSummarize(doc)} title="Full summary">
            <FileSearch className="h-3.5 w-3.5 mr-1" /> Summarize
          </Button>
          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => onExtract(doc)} title="Extract structured data">
            <ListChecks className="h-3.5 w-3.5 mr-1" /> Extract
          </Button>
          {doc.is_outdated ? (
            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-emerald-400 hover:text-emerald-300"
              onClick={() => onToggleOutdated(doc, false)}
              title="Restore — bring this doc back into retrieval">
              Restore
            </Button>
          ) : (
            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-amber-400 hover:text-amber-300"
              onClick={() => onToggleOutdated(doc, true)}
              title="Mark outdated — excluded from knowledge retrieval until restored">
              Outdated
            </Button>
          )}
        </div>
        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-rose-400" onClick={() => onDelete(doc.id)} title="Delete">
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
