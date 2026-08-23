import React, { useState, useEffect } from 'react';
import { Settings as SettingsIcon, Edit3, Trash2, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { deleteReplyAccount } from '@/services/replyDraftService';

// Settings dialog surfaced from the header gear button once an account is
// attached. Account info with edit/disconnect actions. Email activity now
// lives only on the dashboard — it was duplicated here, and the dashboard
// card is always visible rather than hidden behind a gear icon.

export const SettingsModal = ({ open, account, onClose, onEdit, onDeleted }) => {
  const { toast } = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setConfirmDelete(false);
  }, [open]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const res = await deleteReplyAccount();
      if (res?.status === 'success') {
        toast({ title: 'Account disconnected', description: res?.data?.message || 'Inbox cleared.' });
        onDeleted();
      } else {
        toast({ title: 'Delete failed', description: res?.message || 'Could not disconnect the account.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.message || 'Could not disconnect the account.', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SettingsIcon className="h-5 w-5 text-primary" />
            Inbox settings
          </DialogTitle>
          <DialogDescription>
            Manage the mailbox the Reply Draft Agent reads from.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-5">
          {/* Account info + actions */}
          <section className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="text-xs text-muted-foreground">Connected account</div>
                <div className="text-sm font-semibold truncate">{account?.email || '—'}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {account?.account_type || 'smtp'} · IMAP: {account?.imap_host || '—'}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onEdit} disabled={deleting}>
                  <Edit3 className="h-3.5 w-3.5 mr-2" />
                  Edit
                </Button>
                {!confirmDelete ? (
                  <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)} disabled={deleting}>
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    Disconnect
                  </Button>
                ) : (
                  <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>
                    {deleting ? <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-2" />}
                    Really disconnect?
                  </Button>
                )}
              </div>
            </div>
            {confirmDelete && (
              <div className="rounded-md border border-rose-200 bg-rose-500/5 p-3 text-xs text-rose-700 dark:text-rose-400 dark:border-rose-800">
                Disconnecting deletes this account <strong>and all its synced inbox mail + drafts</strong>. This cannot be undone.{' '}
                <button type="button" onClick={() => setConfirmDelete(false)} className="underline">
                  Cancel
                </button>
              </div>
            )}
          </section>

        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
