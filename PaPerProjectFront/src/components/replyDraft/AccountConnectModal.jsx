import React, { useState, useEffect } from 'react';
import { Inbox, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { createReplyAccount } from '@/services/replyDraftService';
import {
  ACCOUNT_TYPE_OPTIONS,
  SYNC_DAYS_OPTIONS,
  SYNC_EMAIL_LIMIT_OPTIONS,
  defaultNewForm,
} from './replyDraftConstants';

// Styling for fields that are display-only while editing. Changing the
// address or server settings of a live account would orphan every synced
// message already filed under it, so on edit we allow exactly the two
// things that legitimately change over time: the passwords (rotated app
// passwords) and the sync scope.
const LOCKED_CLS = 'opacity-70 cursor-not-allowed bg-muted/40';

export const AccountConnectModal = ({ open, onClose, onSaved, mode = 'add', existingAccount = null }) => {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(defaultNewForm());

  const isEdit = mode === 'edit' && existingAccount;

  useEffect(() => {
    if (!open) return;
    if (isEdit) {
      // Prefill from the server's account record. Passwords are never echoed
      // back from the list endpoint, so leave them blank — the backend treats
      // empty passwords as "keep existing" on re-attach.
      setForm({
        ...defaultNewForm(),
        name: existingAccount.name || 'Reply Draft Inbox',
        account_type: existingAccount.account_type || 'smtp',
        email: existingAccount.email || '',
        smtp_host: existingAccount.smtp_host || '',
        smtp_port: existingAccount.smtp_port || 587,
        smtp_username: existingAccount.smtp_username || existingAccount.email || '',
        smtp_password: '',
        use_tls: existingAccount.use_tls ?? true,
        use_ssl: existingAccount.use_ssl ?? false,
        is_gmail_app_password: existingAccount.is_gmail_app_password ?? (existingAccount.account_type === 'gmail'),
        imap_host: existingAccount.imap_host || '',
        imap_port: existingAccount.imap_port || 993,
        imap_username: existingAccount.imap_username || existingAccount.email || '',
        imap_password: '',
        imap_use_ssl: existingAccount.imap_use_ssl ?? true,
        imap_sync_days: existingAccount.imap_sync_days || 90,
        imap_sync_email_limit: existingAccount.imap_sync_email_limit || 200,
      });
    } else {
      setForm(defaultNewForm());
    }
  }, [open, isEdit, existingAccount]);

  const applyTypeDefaults = (typeValue) => {
    const t = ACCOUNT_TYPE_OPTIONS.find((x) => x.value === typeValue);
    if (!t) return;
    setForm((p) => ({
      ...p,
      account_type: typeValue,
      smtp_host: t.smtp_host,
      imap_host: t.imap_host,
      is_gmail_app_password: typeValue === 'gmail',
    }));
  };

  const handleSubmit = async () => {
    if (!form.email.trim()) {
      toast({ title: 'Missing email', description: 'Enter the email address.', variant: 'destructive' });
      return;
    }
    if (!form.smtp_host.trim()) {
      toast({ title: 'Missing SMTP host', description: 'SMTP host is required.', variant: 'destructive' });
      return;
    }
    if (!form.imap_host.trim()) {
      toast({ title: 'Missing IMAP host', description: 'IMAP host is required.', variant: 'destructive' });
      return;
    }
    // On create, passwords are required; on edit they're optional (empty ==
    // keep the stored password).
    if (!isEdit) {
      if (!form.smtp_password) {
        toast({ title: 'Missing SMTP password', description: 'SMTP password is required.', variant: 'destructive' });
        return;
      }
      if (!form.imap_password) {
        toast({ title: 'Missing IMAP password', description: 'IMAP password is required (needed to pull replies).', variant: 'destructive' });
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim() || 'Reply Draft Inbox',
        account_type: form.account_type,
        email: form.email.trim(),
        smtp_host: form.smtp_host.trim(),
        smtp_port: Number(form.smtp_port) || 587,
        smtp_username: (form.smtp_username || '').trim() || form.email.trim(),
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
        is_gmail_app_password: form.is_gmail_app_password,
        imap_host: form.imap_host.trim(),
        imap_port: Number(form.imap_port) || 993,
        imap_username: (form.imap_username || '').trim() || form.email.trim(),
        imap_use_ssl: form.imap_use_ssl,
        imap_sync_days: Number(form.imap_sync_days) || 90,
        imap_sync_email_limit: Number(form.imap_sync_email_limit) || 200,
      };
      // Only include password fields when the user actually typed something,
      // so an edit that leaves them blank preserves what's stored.
      if (form.smtp_password) payload.smtp_password = form.smtp_password;
      if (form.imap_password) payload.imap_password = form.imap_password;

      const res = await createReplyAccount(payload);
      if (res?.status === 'success') {
        toast({
          title: isEdit ? 'Account updated' : 'Account connected',
          description: `${form.email} is syncing now — mail lands within ~30 seconds.`,
        });
        onSaved();
      } else {
        toast({ title: isEdit ? 'Save failed' : 'Create failed', description: res?.message || 'Could not save account.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: isEdit ? 'Save failed' : 'Create failed', description: e?.message || 'Could not save account.', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl w-[95vw] max-h-[90vh] overflow-y-auto no-scrollbar">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Inbox className="h-5 w-5 text-primary" />
            {isEdit ? 'Edit inbox account' : 'Connect an inbox'}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'You can update the passwords and the sync scope. The address and server settings are fixed for a connected account - disconnect and re-add to change those.'
              : 'Add the email account the Reply Draft Agent will read replies from. Syncing starts automatically once you save.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Account basics — full width on top */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label className="text-xs">Account name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Reply inbox"
                readOnly={isEdit}
                disabled={isEdit}
                className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
              />
            </div>
            <div>
              <Label className="text-xs">Provider</Label>
              <select
                value={form.account_type}
                onChange={(e) => applyTypeDefaults(e.target.value)}
                disabled={isEdit}
                className={`mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm ${isEdit ? LOCKED_CLS : ''}`}
              >
                {ACCOUNT_TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs">Email address</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
                placeholder="you@example.com"
                readOnly={isEdit}
                disabled={isEdit}
                className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
              />
            </div>
          </div>

          {/* SMTP + IMAP side-by-side on lg+ */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-2 border-t">
            {/* SMTP */}
            <div className="space-y-3 pt-3">
              <div className="text-xs font-semibold text-muted-foreground">SMTP (for sending)</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Host</Label>
                  <Input
                    value={form.smtp_host}
                    onChange={(e) => setForm((p) => ({ ...p, smtp_host: e.target.value }))}
                    readOnly={isEdit}
                    disabled={isEdit}
                    className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
                  />
                </div>
                <div>
                  <Label className="text-xs">Port</Label>
                  <Input
                    type="number"
                    value={form.smtp_port}
                    onChange={(e) => setForm((p) => ({ ...p, smtp_port: e.target.value }))}
                    readOnly={isEdit}
                    disabled={isEdit}
                    className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs">
                  Password
                  {isEdit && <span className="ml-1 text-muted-foreground font-normal">— leave blank to keep current</span>}
                </Label>
                <Input
                  type="password"
                  value={form.smtp_password}
                  onChange={(e) => setForm((p) => ({ ...p, smtp_password: e.target.value }))}
                  placeholder={isEdit ? 'Enter a new password to change it' : '••••••••'}
                  className="mt-1 h-9"
                />
              </div>
            </div>

            {/* IMAP */}
            <div className="space-y-3 pt-3 lg:border-l lg:pl-6">
              <div className="text-xs font-semibold text-muted-foreground">IMAP (for receiving replies)</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Host</Label>
                  <Input
                    value={form.imap_host}
                    onChange={(e) => setForm((p) => ({ ...p, imap_host: e.target.value }))}
                    readOnly={isEdit}
                    disabled={isEdit}
                    className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
                  />
                </div>
                <div>
                  <Label className="text-xs">Port</Label>
                  <Input
                    type="number"
                    value={form.imap_port}
                    onChange={(e) => setForm((p) => ({ ...p, imap_port: e.target.value }))}
                    readOnly={isEdit}
                    disabled={isEdit}
                    className={`mt-1 h-9 ${isEdit ? LOCKED_CLS : ''}`}
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs">
                  Password
                  {isEdit && <span className="ml-1 text-muted-foreground font-normal">— leave blank to keep current</span>}
                </Label>
                <Input
                  type="password"
                  value={form.imap_password}
                  onChange={(e) => setForm((p) => ({ ...p, imap_password: e.target.value }))}
                  placeholder={isEdit ? 'Enter a new password to change it' : '••••••••'}
                  className="mt-1 h-9"
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="imap-ssl"
                  checked={form.imap_use_ssl}
                  onCheckedChange={(checked) => setForm((p) => ({ ...p, imap_use_ssl: checked }))}
                  disabled={isEdit}
                />
                <Label htmlFor="imap-ssl" className="text-xs cursor-pointer">Use SSL</Label>
              </div>
            </div>
          </div>

          {/* Sync scope — how much mail to pull. Both are capped server-side
              to these exact presets. The email cap is PER 30-day period and
              PER direction (Inbox vs Sent counted separately) — the helper
              text below spells this out. Smaller values keep the inbox light
              and the page fast; defaults (90 days / 200) suit most users. */}
          <div className="pt-4 border-t">
            <div className="text-xs font-semibold text-muted-foreground mb-2">Sync scope</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">How far back to sync</Label>
                <select
                  value={form.imap_sync_days}
                  onChange={(e) => setForm((p) => ({ ...p, imap_sync_days: Number(e.target.value) }))}
                  className="mt-1 w-full h-9 rounded-md border bg-background px-2 text-sm"
                >
                  {SYNC_DAYS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Max emails per 30 days</Label>
                <select
                  value={form.imap_sync_email_limit}
                  onChange={(e) => setForm((p) => ({ ...p, imap_sync_email_limit: Number(e.target.value) }))}
                  className="mt-1 w-full h-9 rounded-md border bg-background px-2 text-sm"
                >
                  {SYNC_EMAIL_LIMIT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              This cap applies to each 30-day period, and received (Inbox) and sent
              (Sent) mail are counted separately. For example, <span className="text-foreground/80 font-medium">90 days + 200</span> fetches up to
              200 received <span className="italic">and</span> up to 200 sent for each 30-day period — so up to
              600 received and 600 sent over the full 90 days. Most mailboxes have
              far fewer, so you'll usually get everything in the window. Lower values keep the inbox faster.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            {isEdit ? 'Save changes' : 'Save & start sync'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
