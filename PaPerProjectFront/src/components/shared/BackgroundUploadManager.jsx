/**
 * BackgroundUploadManager — global, non-blocking document upload UX.
 *
 * Usage:
 *   1) Wrap the app once at the root:
 *        <BackgroundUploadProvider><App /></BackgroundUploadProvider>
 *      This also renders the floating "uploads in progress" widget.
 *
 *   2) In any component that triggers uploads:
 *        const { startUpload } = useBackgroundUpload();
 *        startUpload({
 *          title: file.name,
 *          agent: 'hr' | 'frontline',
 *          upload: (onProgress) => hrAgentService.uploadHRDocument(...),
 *          poll: (documentId) => hrAgentService.getHRDocumentStatus(documentId),
 *          onDone: (result) => refreshDocsList(),
 *        });
 *
 * Behaviour:
 *   * Immediate "Upload started" toast + the caller UI can close its dialog.
 *   * A floating bottom-right pill shows a count + spinner while uploads run.
 *   * Clicking the pill expands a panel with per-upload progress bars.
 *   * Toast fires again when each upload finishes (or fails).
 *   * Provider owns the upload lifecycle so navigating away doesn't cancel it.
 */
import React, { createContext, useContext, useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, Upload, CheckCircle2, XCircle, X, ChevronDown, FileText } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';

const BackgroundUploadContext = createContext(null);

let _nextId = 1;

export function BackgroundUploadProvider({ children }) {
  const { toast } = useToast();
  // `uploads` is a Map-like object: { id → { id, title, agent, status,
  // uploadPercent, indexPercent, indexStatus, error, done, addedAt } }.
  // Kept as an object (not a Map) so React can shallow-compare on renders.
  const [uploads, setUploads] = useState({});
  const [expanded, setExpanded] = useState(false);
  // Ref mirror so async callbacks can read latest state without stale-closure
  // gotchas. Reads happen inside setUploads updater fn where React gives us
  // the fresh state, so we mostly don't need this — kept for safety on toasts.
  const uploadsRef = useRef(uploads);
  uploadsRef.current = uploads;

  const patch = useCallback((id, updates) => {
    setUploads((prev) => {
      const cur = prev[id];
      if (!cur) return prev;
      return { ...prev, [id]: { ...cur, ...updates } };
    });
  }, []);

  const dismiss = useCallback((id) => {
    setUploads((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const dismissAllDone = useCallback(() => {
    setUploads((prev) => {
      const next = {};
      for (const [id, u] of Object.entries(prev)) {
        if (!u.done) next[id] = u;
      }
      return next;
    });
  }, []);

  /**
   * Start a background upload.
   *
   * @param {object} args
   * @param {string} args.title              — display name (usually file.name).
   * @param {'hr'|'frontline'} args.agent    — used for icon color / grouping.
   * @param {(onProgress: (p:{percent:number, loaded:number, total:number}) => void) => Promise<object>} args.upload
   *        — function that performs the actual upload; must call onProgress
   *          and resolve with `{ data: { id, processing_status } }` shape.
   * @param {(documentId:number) => Promise<object>} args.poll
   *        — function to poll the doc status endpoint; must resolve with
   *          `{ data: { processing_status, percent|progress_percent,
   *            chunks_processed, chunks_total, processing_error } }`.
   * @param {(result:object) => void} [args.onDone]  — called after ready.
   * @returns {number} upload id (for callers that need to track).
   */
  const startUpload = useCallback(({ title, agent, upload, poll, onDone }) => {
    const id = _nextId++;
    setUploads((prev) => ({
      ...prev,
      [id]: {
        id,
        title: title || 'Untitled',
        agent: agent || 'frontline',
        status: 'uploading',       // 'uploading' | 'indexing' | 'ready' | 'failed'
        uploadPercent: 0,
        indexPercent: 0,
        indexStatus: 'idle',
        indexDone: 0,
        indexTotal: 0,
        error: '',
        done: false,
        addedAt: Date.now(),
      },
    }));

    // Immediate toast so the user knows the work has been kicked off and
    // they can close the dialog / navigate away safely.
    toast({
      title: 'Upload started',
      description: `${title || 'Document'} is uploading in the background.`,
    });

    // Fire-and-forget async runner. Errors are caught and surfaced via
    // toast + the widget's failed-state UI.
    (async () => {
      try {
        const res = await upload(({ percent }) => {
          patch(id, { uploadPercent: percent });
        });
        patch(id, { uploadPercent: 100, status: 'indexing' });

        const documentId = res?.data?.id;
        const initialStatus = res?.data?.processing_status;

        if (initialStatus === 'ready' || !documentId) {
          // Fast path: inline processing or no id returned.
          patch(id, {
            status: 'ready', indexStatus: 'ready', indexPercent: 100, done: true,
          });
          toast({
            title: 'Upload complete',
            description: `"${title}" is ready.`,
          });
          try { onDone?.(res); } catch (_) { /* swallow */ }
          _autoDismiss(id);
          return;
        }

        // Poll the status endpoint every 1.5s until ready/failed or timeout.
        const MAX_MS = 15 * 60 * 1000;      // 15 min hard ceiling for huge docs
        const INTERVAL_MS = 1500;
        const startedAt = Date.now();
        while (Date.now() - startedAt < MAX_MS) {
          try {
            const statusRes = await poll(documentId);
            const s = statusRes?.data || {};
            const pct = Number(
              s.percent != null ? s.percent :
              s.progress_percent != null ? s.progress_percent : 0
            );
            patch(id, {
              indexStatus: s.processing_status || 'processing',
              indexPercent: Math.round(pct),
              indexDone: Number(s.chunks_processed || 0),
              indexTotal: Number(s.chunks_total || 0),
              error: s.processing_error || '',
            });
            if (s.processing_status === 'ready') {
              patch(id, { status: 'ready', done: true, indexPercent: 100 });
              toast({
                title: 'Indexing complete',
                description: `"${title}" — ${s.chunks_total || 0} chunk(s) embedded.`,
              });
              try { onDone?.(statusRes); } catch (_) { /* swallow */ }
              _autoDismiss(id);
              return;
            }
            if (s.processing_status === 'failed') {
              patch(id, {
                status: 'failed', done: true,
                error: s.processing_error || 'Indexing failed.',
              });
              toast({
                title: 'Indexing failed',
                description: `"${title}": ${s.processing_error || 'The document could not be indexed.'}`,
                variant: 'destructive',
              });
              return;
            }
          } catch (pollErr) {
            // Transient — keep polling.
            console.warn('BackgroundUpload poll error:', pollErr);
          }
          await new Promise((r) => setTimeout(r, INTERVAL_MS));
        }
        // Timed out but likely still running server-side.
        patch(id, { status: 'ready', done: true, indexPercent: Math.max(0, uploadsRef.current[id]?.indexPercent || 0) });
        toast({
          title: 'Still processing',
          description: `"${title}" is taking a while — it will finish in the background.`,
        });
        try { onDone?.(null); } catch (_) { /* swallow */ }
        _autoDismiss(id);
      } catch (err) {
        console.error('BackgroundUpload failed:', err);
        patch(id, { status: 'failed', done: true, error: err?.message || 'Upload failed.' });
        toast({
          title: 'Upload failed',
          description: `"${title}": ${err?.message || 'Unknown error'}`,
          variant: 'destructive',
        });
      }
    })();

    return id;
  }, [patch, toast]);

  // Auto-dismiss finished entries after a short grace period so the widget
  // stays uncluttered. Users can also dismiss manually via the ×.
  const _autoDismiss = useCallback((id) => {
    setTimeout(() => dismiss(id), 8000);
  }, [dismiss]);

  const value = { startUpload, uploads, dismiss, dismissAllDone };

  return (
    <BackgroundUploadContext.Provider value={value}>
      {children}
      <BackgroundUploadWidget
        uploads={uploads}
        expanded={expanded}
        setExpanded={setExpanded}
        dismiss={dismiss}
        dismissAllDone={dismissAllDone}
      />
    </BackgroundUploadContext.Provider>
  );
}

export function useBackgroundUpload() {
  const ctx = useContext(BackgroundUploadContext);
  if (!ctx) {
    throw new Error('useBackgroundUpload must be used inside <BackgroundUploadProvider>.');
  }
  return ctx;
}


// ---------------------------------------------------------------------------
// Floating widget — collapsed pill (bottom-right) + expandable panel
// ---------------------------------------------------------------------------

function BackgroundUploadWidget({ uploads, expanded, setExpanded, dismiss, dismissAllDone }) {
  const items = Object.values(uploads).sort((a, b) => b.addedAt - a.addedAt);
  if (items.length === 0) return null;

  const active = items.filter((u) => !u.done);
  const failed = items.filter((u) => u.status === 'failed');
  const anyActive = active.length > 0;

  const pillLabel = anyActive
    ? `Uploading ${active.length}`
    : failed.length > 0
      ? `${failed.length} failed`
      : `${items.length} ready`;

  return createPortal(
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col items-end gap-2 pointer-events-none">
      {expanded && (
        <div className="pointer-events-auto w-[340px] max-h-[60vh] overflow-y-auto rounded-xl border border-white/10 bg-[#12121a] shadow-2xl">
          <div className="sticky top-0 flex items-center justify-between px-3 py-2 border-b border-white/10 bg-[#12121a]">
            <div className="text-xs font-semibold text-white/80">Document uploads</div>
            <div className="flex items-center gap-1">
              {items.some((u) => u.done) && (
                <button
                  type="button"
                  onClick={dismissAllDone}
                  className="text-[10px] text-white/50 hover:text-white/80 px-2 py-0.5 rounded hover:bg-white/[0.06]"
                >
                  Clear done
                </button>
              )}
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="p-1 rounded hover:bg-white/[0.06] text-white/60"
                aria-label="Collapse"
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="p-2 space-y-2">
            {items.map((u) => (
              <UploadRow key={u.id} u={u} onDismiss={() => dismiss(u.id)} />
            ))}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={`pointer-events-auto flex items-center gap-2 rounded-full px-3 py-2 text-xs font-medium shadow-lg border transition-all ${
          failed.length > 0
            ? 'bg-red-500/15 border-red-400/40 text-red-200 hover:bg-red-500/25'
            : anyActive
              ? 'bg-violet-500/20 border-violet-400/40 text-violet-100 hover:bg-violet-500/30'
              : 'bg-emerald-500/15 border-emerald-400/40 text-emerald-200 hover:bg-emerald-500/25'
        }`}
      >
        {failed.length > 0 ? (
          <XCircle className="h-4 w-4" />
        ) : anyActive ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <CheckCircle2 className="h-4 w-4" />
        )}
        <span>{pillLabel}</span>
      </button>
    </div>,
    document.body
  );
}


function UploadRow({ u, onDismiss }) {
  const isUploading = u.status === 'uploading';
  const isIndexing = u.status === 'indexing';
  const isReady = u.status === 'ready';
  const isFailed = u.status === 'failed';

  const primaryPct = isUploading ? u.uploadPercent : (isIndexing ? u.indexPercent : 100);
  const primaryLabel = isFailed
    ? 'Failed'
    : isReady
      ? 'Complete'
      : isIndexing
        ? (u.indexTotal > 0 ? `Indexing ${u.indexDone}/${u.indexTotal}` : 'Indexing…')
        : `Uploading ${u.uploadPercent}%`;
  const barColor = isFailed
    ? 'bg-red-500/70'
    : isReady
      ? 'bg-emerald-500/80'
      : isIndexing
        ? 'bg-gradient-to-r from-amber-500 to-orange-500'
        : 'bg-gradient-to-r from-violet-500 to-indigo-500';

  return (
    <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-2.5 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <FileText className="h-3.5 w-3.5 text-white/50 shrink-0" />
          <div className="text-[11px] text-white/85 truncate">{u.title}</div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`text-[9px] px-1.5 py-[1px] rounded uppercase tracking-wider font-semibold ${
            u.agent === 'hr'
              ? 'bg-blue-500/15 text-blue-200 border border-blue-400/25'
              : u.agent === 'operations'
                ? 'bg-amber-500/15 text-amber-200 border border-amber-400/25'
                : 'bg-violet-500/15 text-violet-200 border border-violet-400/25'
          }`}>
            {u.agent}
          </span>
          {u.done && (
            <button
              type="button"
              onClick={onDismiss}
              className="p-0.5 rounded hover:bg-white/[0.08] text-white/40"
              aria-label="Dismiss"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between text-[10px] text-white/60">
        <span className="flex items-center gap-1">
          {isUploading && <Upload className="h-2.5 w-2.5 text-violet-300" />}
          {isIndexing && <Loader2 className="h-2.5 w-2.5 text-amber-300 animate-spin" />}
          {isReady && <CheckCircle2 className="h-2.5 w-2.5 text-emerald-300" />}
          {isFailed && <XCircle className="h-2.5 w-2.5 text-red-300" />}
          {primaryLabel}
        </span>
        <span className="font-mono text-white/50">{primaryPct}%</span>
      </div>
      <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
        <div
          className={`h-full transition-all duration-200 ease-out ${barColor}`}
          style={{ width: `${primaryPct}%` }}
        />
      </div>
      {isFailed && u.error && (
        <div className="text-[10px] text-red-300/90 pt-1">{u.error}</div>
      )}
    </div>
  );
}
