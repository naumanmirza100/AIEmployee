import React from 'react';
import { Loader2, Paperclip, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DRAFT_ATTACHMENT_MAX_COUNT } from './replyDraftConstants';
import { ATTACHMENT_ORIGIN, fileIconChar, formatFileSize } from './replyDraftHelpers';

// Skeleton shown while the lazy-fetch endpoint is still pulling
// attachments from IMAP for an InboxEmail row that was synced with
// attachments_fetched=false. Two muted skeleton cards + a small
// "Loading attachments…" tag so the user understands the email isn't
// missing files — they're still streaming. Replaced by AttachmentList
// when fetch resolves, or by nothing when the email genuinely has no
// attachments.
export const AttachmentLoading = () => (
  <div className="mt-4 pt-4 border-t border-white/10">
    <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-cyan-300 mb-2">
      <Loader2 className="h-3 w-3 animate-spin" />
      Loading attachments…
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {[0, 1].map((i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 border border-white/10 animate-pulse"
        >
          <span className="text-xl shrink-0 opacity-40" aria-hidden="true">📎</span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="h-3 w-3/4 rounded bg-white/10" />
            <div className="h-2 w-1/3 rounded bg-white/10" />
          </div>
        </div>
      ))}
    </div>
  </div>
);

export const AttachmentList = ({ attachments }) => {
  const handleDownload = async (att) => {
    // Token-authenticated download: fetch with the auth header, turn the
    // response into a Blob, then synthesise an <a download> click. Direct
    // <a href> links wouldn't carry the company-user token and would 401.
    try {
      const token = localStorage.getItem('company_auth_token') || '';
      const url = `${ATTACHMENT_ORIGIN}${att.download_url}`;
      const res = await fetch(url, {
        method: 'GET',
        headers: token ? { Authorization: `Token ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = att.filename || 'attachment';
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Tiny delay so the click triggers before the URL is revoked. 200ms
      // is enough for any browser to start the save.
      setTimeout(() => URL.revokeObjectURL(objUrl), 200);
    } catch (e) {
      console.error('Attachment download failed', e);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-white/10">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300 mb-2">
        <span>📎</span>
        Attachments · {attachments.length}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {attachments.map((att) => (
          <button
            key={att.id}
            type="button"
            onClick={() => handleDownload(att)}
            className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 hover:border-emerald-500/30 transition text-left group"
          >
            <span className="text-xl shrink-0" aria-hidden="true">
              {fileIconChar(att.filename, att.content_type)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-gray-100 truncate group-hover:text-white">
                {att.filename || 'attachment'}
              </div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                {formatFileSize(att.size_bytes)}
                {att.content_type && (
                  <span className="ml-1 opacity-60">· {att.content_type}</span>
                )}
              </div>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300 opacity-0 group-hover:opacity-100 transition shrink-0">
              Download
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};

// Outgoing-attachment editor shown inside the draft composer. Reuses the
// same download/icon helpers as the incoming AttachmentList so the visual
// language stays consistent — the only behavioral difference is the X
// remove control on each row plus the upload button.
export const DraftAttachmentsSection = ({ draft, uploading, isReadOnly, onPickFiles, onRemove }) => {
  const inputRef = React.useRef(null);
  const attachments = Array.isArray(draft?.attachments) ? draft.attachments : [];
  const atLimit = attachments.length >= DRAFT_ATTACHMENT_MAX_COUNT;

  const handleDownload = async (att) => {
    // Same token-auth blob trick as AttachmentList — direct <a href> links
    // wouldn't carry the company-user token, so this fetches with the
    // header and synthesises a download.
    try {
      const token = localStorage.getItem('company_auth_token') || '';
      const url = `${ATTACHMENT_ORIGIN}${att.download_url}`;
      const res = await fetch(url, {
        method: 'GET',
        headers: token ? { Authorization: `Token ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = att.filename || 'attachment';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objUrl), 200);
    } catch (e) {
      console.error('Draft attachment download failed', e);
    }
  };

  const handlePicked = (e) => {
    const files = e.target.files;
    onPickFiles(files);
    // Reset so the same filename can be picked again after a remove.
    e.target.value = '';
  };

  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-300">
          <Paperclip className="h-3.5 w-3.5 text-emerald-300" />
          Attachments
          <span className="text-gray-500 font-normal">
            ({attachments.length}{attachments.length > 0 ? ` · ${DRAFT_ATTACHMENT_MAX_COUNT} max` : ''})
          </span>
        </div>
        {!isReadOnly && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => inputRef.current?.click()}
            disabled={uploading || atLimit}
            className="bg-white/5 border-white/10 text-white hover:bg-white/10 h-7 px-2 text-xs"
            title={atLimit ? `At most ${DRAFT_ATTACHMENT_MAX_COUNT} files per draft` : 'Add a file'}
          >
            {uploading ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <Paperclip className="h-3.5 w-3.5 mr-1.5" />
            )}
            {uploading ? 'Uploading…' : 'Add file'}
          </Button>
        )}
      </div>

      {attachments.length === 0 ? (
        <div className="text-[11px] text-gray-500">
          {isReadOnly
            ? 'No attachments were sent with this draft.'
            : 'Add files (up to 25 MB each) — they\'ll go out with this reply.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {attachments.map((att) => (
            <div
              key={att.id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-black/20 border border-white/10 hover:border-emerald-500/30 transition group"
            >
              <span className="text-xl shrink-0" aria-hidden="true">
                {fileIconChar(att.filename, att.content_type)}
              </span>
              <button
                type="button"
                onClick={() => handleDownload(att)}
                className="min-w-0 flex-1 text-left"
                title="Download"
              >
                <div className="text-sm text-gray-100 truncate group-hover:text-white">
                  {att.filename || 'attachment'}
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">
                  {formatFileSize(att.size_bytes)}
                  {att.content_type && (
                    <span className="ml-1 opacity-60">· {att.content_type}</span>
                  )}
                </div>
              </button>
              {!isReadOnly && (
                <button
                  type="button"
                  onClick={() => onRemove(att.id)}
                  title="Remove attachment"
                  className="h-7 w-7 flex items-center justify-center rounded-md text-gray-400 hover:text-rose-300 hover:bg-rose-500/10 transition shrink-0"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {!isReadOnly && (
        <input
          ref={inputRef}
          type="file"
          multiple
          onChange={handlePicked}
          className="hidden"
        />
      )}
    </div>
  );
};
