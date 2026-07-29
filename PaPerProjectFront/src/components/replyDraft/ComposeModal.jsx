import React, { useState, useEffect, useCallback } from 'react';
import { PenSquare, Type, Code2, Paperclip, Loader2, X, AlertCircle, Trash2, Send } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import {
  composeCreateDraft,
  composeUpdateDraft,
  uploadDraftAttachment,
  deleteDraftAttachment,
  approveDraft,
  sendDraft,
  rejectDraft,
} from '@/services/replyDraftService';
import { DRAFT_ATTACHMENT_MAX_BYTES, DRAFT_ATTACHMENT_MAX_COUNT } from './replyDraftConstants';
import { ATTACHMENT_ORIGIN, fileIconChar, formatFileSize, humanizeSendError } from './replyDraftHelpers';

// Gmail-style "+ Compose" dialog. Builds a fresh ReplyDraft (no source
// email) on first user action — either when they pick an attachment or
// when they hit Send. Until then the form is purely client-side state,
// so opening + closing the modal without typing creates no DB rows.
//
// The HTML toggle flips `body_format` between 'text' and 'html'. Backend
// uses the body verbatim as text/html when format='html', otherwise
// derives HTML from the plain body via the same converter that powers
// AI reply sends — so the recipient experience is identical between
// reply drafts and compose drafts.
export const ComposeModal = ({ open, onClose, onSent }) => {
  const { toast } = useToast();
  const [draftId, setDraftId] = useState(null);
  const [toEmail, setToEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [bodyFormat, setBodyFormat] = useState('text');
  const [attachments, setAttachments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Inline send error — displayed in a banner inside the modal so the user
  // doesn't dismiss it without reading (a toast pops out of the modal and
  // disappears on its own; for SMTP rejections we want it to persist until
  // the user takes action).
  const [sendError, setSendError] = useState('');
  // True once the user has attempted Send (regardless of outcome). Used to
  // decide whether closing the modal should auto-reject the draft. Without
  // this, a failed send followed by an accidental Esc / outside click would
  // discard the draft on the server, surprising the user — they couldn't
  // even reopen it from the Drafts tab to fix and retry.
  const [sendAttempted, setSendAttempted] = useState(false);
  const fileInputRef = React.useRef(null);

  // Reset the form whenever the modal closes — without this, opening it
  // again would briefly show the prior message before the parent
  // re-renders.
  useEffect(() => {
    if (!open) {
      setDraftId(null);
      setToEmail('');
      setSubject('');
      setBody('');
      setBodyFormat('text');
      setAttachments([]);
      setBusy(false);
      setUploading(false);
      setSendError('');
      setSendAttempted(false);
    }
  }, [open]);

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(toEmail.trim());
  const canSend = validEmail && subject.trim() && body.trim() && !busy && !uploading;

  // Lazy draft creation. Both Send and the first attachment upload need
  // a draft_id, so they call this. Subsequent calls just return the
  // already-created draft id.
  const ensureDraft = useCallback(async () => {
    if (draftId) return draftId;
    const res = await composeCreateDraft({
      toEmail: toEmail.trim(),
      subject: subject.trim(),
      body,
      bodyFormat,
    });
    if (res?.status === 'success' && res?.data?.id) {
      setDraftId(res.data.id);
      return res.data.id;
    }
    throw new Error(res?.message || 'Failed to create draft');
  }, [draftId, toEmail, subject, body, bodyFormat]);

  const handlePickFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter(Boolean);
    if (files.length === 0) return;

    if (!validEmail || !subject.trim()) {
      toast({
        title: 'Add recipient & subject first',
        description: 'A draft is created when you attach a file — fill these so the draft is valid.',
        variant: 'destructive',
      });
      return;
    }
    if (attachments.length + files.length > DRAFT_ATTACHMENT_MAX_COUNT) {
      toast({
        title: 'Too many attachments',
        description: `A draft can have at most ${DRAFT_ATTACHMENT_MAX_COUNT} files.`,
        variant: 'destructive',
      });
      return;
    }

    setUploading(true);
    try {
      const id = await ensureDraft();
      const added = [];
      for (const file of files) {
        if ((file.size || 0) > DRAFT_ATTACHMENT_MAX_BYTES) {
          toast({
            title: 'File too large',
            description: `${file.name} is over ${Math.floor(DRAFT_ATTACHMENT_MAX_BYTES / (1024 * 1024))} MB and was skipped.`,
            variant: 'destructive',
          });
          continue;
        }
        try {
          const res = await uploadDraftAttachment(id, file);
          if (res?.data) added.push(res.data);
        } catch (e) {
          toast({ title: `Upload failed: ${file.name}`, description: e.message, variant: 'destructive' });
        }
      }
      if (added.length > 0) {
        setAttachments((prev) => [...prev, ...added]);
      }
    } catch (e) {
      toast({ title: 'Could not attach file', description: e.message, variant: 'destructive' });
    } finally {
      setUploading(false);
    }
  };

  const handleRemoveAttachment = async (attachmentId) => {
    if (!draftId) return;
    try {
      await deleteDraftAttachment(draftId, attachmentId);
      setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
    } catch (e) {
      toast({ title: 'Could not remove attachment', description: e.message, variant: 'destructive' });
    }
  };

  const handleSend = async () => {
    if (!canSend) return;
    setBusy(true);
    setSendError('');
    setSendAttempted(true);
    try {
      // Either create the draft (no attachments path) or sync the latest
      // form state to an existing one (attachments path may have made the
      // draft earlier with stale subject/body).
      let id = draftId;
      if (!id) {
        id = await ensureDraft();
      } else {
        await composeUpdateDraft(id, {
          toEmail: toEmail.trim(),
          subject: subject.trim(),
          body,
          bodyFormat,
        });
      }
      const ap = await approveDraft(id, { editedSubject: subject.trim(), editedBody: body });
      if (ap.status !== 'success') throw new Error(ap.message || 'Approve failed');
      const sent = await sendDraft(id);
      if (sent.status !== 'success') throw new Error(sent.message || 'Send failed');
      toast({ title: 'Email sent', description: `Delivered to ${toEmail.trim()}.` });
      onSent?.();
    } catch (e) {
      // Render inside the modal instead of a toast so SMTP rejections (e.g.
      // Gmail's 552 security block) stay visible while the user edits.
      // Preserve the raw error in the console for diagnostics.
      console.error('Compose send failed', e);
      setSendError(humanizeSendError(e?.message));
    } finally {
      setBusy(false);
    }
  };

  const handleDiscard = async () => {
    // Explicit Discard button — the user wants the draft gone.
    if (draftId) {
      try {
        await rejectDraft(draftId);
      } catch (e) {
        // Non-fatal; user is closing anyway.
        console.error('Discard compose failed', e);
      }
    }
    onClose?.();
  };

  // Closing via the dialog's top-right X / Esc / outside click. Distinct
  // from Discard: a soft close should AUTOSAVE the message so it shows up
  // in the Drafts tab — Gmail-style. The user can come back later, edit,
  // and send. Discard (explicit) is the only path that destroys the draft.
  //
  // Three branches:
  //   1. Draft already exists on the server (created via attach or a
  //      prior Send attempt) → push the latest typed content so what's
  //      saved matches what the user just had on screen.
  //   2. No draft yet, but user has the minimum (valid email + subject)
  //      → create one so it lands in Drafts.
  //   3. Empty / partial compose (no email or no subject) → nothing to
  //      save; just close. The backend's compose_create_draft requires
  //      both fields; respecting that here keeps Drafts tab tidy and
  //      avoids 400-on-close noise.
  const handleClose = async () => {
    const trimmedTo = toEmail.trim();
    const trimmedSubject = subject.trim();
    const hasMinimum = validEmail && !!trimmedSubject;
    if (draftId) {
      try {
        await composeUpdateDraft(draftId, {
          toEmail: trimmedTo,
          subject: trimmedSubject,
          body,
          bodyFormat,
        });
      } catch (e) {
        console.error('Compose autosave on close (update) failed', e);
      }
    } else if (hasMinimum) {
      try {
        await composeCreateDraft({
          toEmail: trimmedTo,
          subject: trimmedSubject,
          body,
          bodyFormat,
        });
      } catch (e) {
        console.error('Compose autosave on close (create) failed', e);
      }
    }
    onClose?.();
  };

  const handleDownloadAtt = async (att) => {
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
      console.error('Compose attachment download failed', e);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !busy) handleClose(); }}>
      {/* Compact Gmail-style composer. Inline-prefixed To/Subject rows
          collapse the per-field label space; textarea stays modest in
          height (auto-grows on resize). DialogContent is capped at 85vh
          with internal scroll so a busy compose with lots of attachments
          stays inside the viewport. */}
      <DialogContent className="max-w-2xl bg-[#0d0b1f] border border-white/10 text-white p-4 max-h-[85vh] flex flex-col gap-2">
        <DialogHeader className="space-y-0">
          <DialogTitle className="flex items-center gap-2 text-white text-sm font-semibold">
            <PenSquare className="h-4 w-4 text-fuchsia-300" />
            New message
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-2 pr-1">
          {/* To row — inline label so it's a single ~36px row instead of
              two stacked elements. */}
          <div className={`flex items-center gap-2 border-b transition ${toEmail && !validEmail ? 'border-rose-500/40' : 'border-white/10'
            }`}>
            <span className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 w-20 shrink-0">To</span>
            <input
              type="email"
              autoComplete="off"
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              placeholder="recipient@example.com"
              className="flex-1 bg-transparent py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none"
              disabled={busy}
            />
            {toEmail && !validEmail && (
              <span className="text-[10px] text-rose-300 shrink-0">invalid</span>
            )}
          </div>

          <div className="flex items-center gap-2 border-b border-white/10">
            <span className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 w-20 shrink-0">Subject</span>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Subject"
              className="flex-1 bg-transparent py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none"
              disabled={busy}
            />
            {/* HTML/Text toggle moves up to the subject row so the body
                section doesn't need its own header strip. */}
            <div className="flex items-center gap-0.5 text-[10px] shrink-0">
              <button
                type="button"
                onClick={() => setBodyFormat('text')}
                className={`px-1.5 py-0.5 rounded flex items-center gap-1 transition ${bodyFormat === 'text'
                    ? 'bg-cyan-500/20 text-cyan-200'
                    : 'text-gray-500 hover:text-white'
                  }`}
                disabled={busy}
                title="Plain text — URLs autolink, line breaks preserved"
              >
                <Type className="h-3 w-3" />
                Text
              </button>
              <button
                type="button"
                onClick={() => setBodyFormat('html')}
                className={`px-1.5 py-0.5 rounded flex items-center gap-1 transition ${bodyFormat === 'html'
                    ? 'bg-fuchsia-500/20 text-fuchsia-200'
                    : 'text-gray-500 hover:text-white'
                  }`}
                disabled={busy}
                title="HTML — markup sent as-is"
              >
                <Code2 className="h-3 w-3" />
                HTML
              </button>
            </div>
          </div>

          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            placeholder={bodyFormat === 'html' ? '<p>Your HTML…</p>' : 'Type your message…'}
            className={`w-full bg-transparent text-sm text-white placeholder-gray-600 focus:outline-none resize-y min-h-[120px] max-h-[32vh] overflow-y-auto ${bodyFormat === 'html' ? 'font-mono text-xs' : 'font-sans leading-relaxed'
              }`}
            disabled={busy}
          />

          {/* Attachments — header is just a button + count to keep this
              compact. List items are slim 28px-ish rows. */}
          <div className="border-t border-white/10 pt-2">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-400">
                <Paperclip className="h-3 w-3 text-emerald-300" />
                {attachments.length > 0 ? `Attachments · ${attachments.length}` : 'Attachments'}
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || busy || attachments.length >= DRAFT_ATTACHMENT_MAX_COUNT}
                className="bg-white/5 border-white/10 text-white hover:bg-white/10 h-6 px-2 text-[11px]"
              >
                {uploading ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Paperclip className="h-3 w-3 mr-1" />
                )}
                {uploading ? 'Uploading…' : 'Attach'}
              </Button>
            </div>
            {attachments.length > 0 && (
              <div className="space-y-1">
                {attachments.map((att) => (
                  <div
                    key={att.id}
                    className="flex items-center gap-2 px-2 py-1 rounded bg-white/5 border border-white/10 hover:border-emerald-500/30 transition group"
                  >
                    <span className="text-sm shrink-0" aria-hidden="true">
                      {fileIconChar(att.filename, att.content_type)}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDownloadAtt(att)}
                      className="min-w-0 flex-1 text-left text-xs text-gray-100 truncate group-hover:text-white"
                      title="Download"
                    >
                      {att.filename || 'attachment'}
                      <span className="text-[10px] text-gray-500 ml-1.5">{formatFileSize(att.size_bytes)}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveAttachment(att.id)}
                      title="Remove"
                      className="h-5 w-5 flex items-center justify-center rounded text-gray-400 hover:text-rose-300 hover:bg-rose-500/10 transition shrink-0"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={(e) => {
                handlePickFiles(e.target.files);
                e.target.value = '';
              }}
              className="hidden"
            />
          </div>
        </div>

        {sendError && (
          <div
            className="mt-1 mb-1 flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-100"
            role="alert"
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-300" />
            <div className="flex-1 leading-snug">
              <div className="font-semibold text-rose-200 mb-0.5">Send failed</div>
              <div className="text-rose-100/90">{sendError}</div>
            </div>
            <button
              type="button"
              onClick={() => setSendError('')}
              className="shrink-0 text-rose-300/70 hover:text-rose-100 transition"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <DialogFooter className="flex justify-between gap-2 pt-2 border-t border-white/10">
          <Button
            type="button"
            variant="outline"
            onClick={handleDiscard}
            disabled={busy}
            className="bg-transparent border-rose-500/30 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Discard
          </Button>
          <Button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold shadow-lg shadow-emerald-500/20 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
            {busy ? 'Sending…' : 'Send'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
