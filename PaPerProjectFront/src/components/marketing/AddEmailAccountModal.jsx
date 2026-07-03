import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';

const EMAIL_ACCOUNT_TYPES = [
  { value: 'gmail', label: 'Gmail' },
  { value: 'outlook', label: 'Outlook' },
  { value: 'hostinger', label: 'Hostinger' },
  { value: 'smtp', label: 'Custom SMTP' },
];

const SMTP_DEFAULTS = {
  gmail: { host: 'smtp.gmail.com', port: 587, useTLS: true, useSSL: false },
  outlook: { host: 'smtp-mail.outlook.com', port: 587, useTLS: true, useSSL: false },
  hostinger: { host: 'smtp.hostinger.com', port: 587, useTLS: true, useSSL: false },
  smtp: { host: '', port: 587, useTLS: true, useSSL: false },
};

const IMAP_DEFAULTS = {
  gmail: { host: 'imap.gmail.com', port: 993, useSSL: true },
  outlook: { host: 'outlook.office365.com', port: 993, useSSL: true },
  hostinger: { host: 'imap.hostinger.com', port: 993, useSSL: true },
  smtp: { host: '', port: 993, useSSL: true },
};

const defaultEmailForm = () => ({
  name: '',
  account_type: 'smtp',
  email: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  use_tls: true,
  use_ssl: false,
  is_gmail_app_password: false,
  is_active: true,
  is_default: false,
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
});

/**
 * Standalone "Add/Edit email account" modal — same form as the Email tab on the
 * Marketing dashboard, usable inline from anywhere (e.g. a "no email account yet"
 * prompt) without navigating away from the current page.
 */
const AddEmailAccountModal = ({ open, onOpenChange, onCreated }) => {
  const { toast } = useToast();
  const [emailForm, setEmailForm] = useState(defaultEmailForm());
  const [emailFormLoading, setEmailFormLoading] = useState(false);
  // Auto-fill SMTP username / IMAP host & username from the account type + email,
  // but stop overwriting a field the moment the user edits it directly.
  const [usernameTouched, setUsernameTouched] = useState(false);
  const [imapHostTouched, setImapHostTouched] = useState(false);
  const [imapUsernameTouched, setImapUsernameTouched] = useState(false);

  useEffect(() => {
    if (open) {
      setEmailForm(defaultEmailForm());
      setUsernameTouched(false);
      setImapHostTouched(false);
      setImapUsernameTouched(false);
    }
  }, [open]);

  const applyEmailTypeDefaults = (accountType) => {
    const d = SMTP_DEFAULTS[accountType] || SMTP_DEFAULTS.smtp;
    const imapD = IMAP_DEFAULTS[accountType] || IMAP_DEFAULTS.smtp;
    setEmailForm((prev) => ({
      ...prev,
      account_type: accountType,
      smtp_host: d.host,
      smtp_port: d.port,
      use_tls: d.useTLS,
      use_ssl: d.useSSL,
      is_gmail_app_password: accountType === 'gmail',
      imap_host: imapHostTouched ? prev.imap_host : imapD.host,
      imap_port: imapD.port,
      imap_use_ssl: imapD.useSSL,
    }));
  };

  const handleEmailChange = (value) => {
    setEmailForm((prev) => ({
      ...prev,
      email: value,
      smtp_username: usernameTouched ? prev.smtp_username : value,
      imap_username: imapUsernameTouched ? prev.imap_username : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!emailForm.name?.trim()) {
      toast({ title: 'Validation', description: 'Account name is required.', variant: 'destructive' });
      return;
    }
    if (!emailForm.email?.trim()) {
      toast({ title: 'Validation', description: 'Email is required.', variant: 'destructive' });
      return;
    }
    if (!emailForm.smtp_host?.trim()) {
      toast({ title: 'Validation', description: 'SMTP host is required.', variant: 'destructive' });
      return;
    }
    if (!emailForm.smtp_password) {
      toast({ title: 'Validation', description: 'SMTP password is required for new account.', variant: 'destructive' });
      return;
    }
    if (!emailForm.imap_host?.trim()) {
      toast({ title: 'Validation', description: 'IMAP host is required (needed for reply detection).', variant: 'destructive' });
      return;
    }
    if (!emailForm.imap_username?.trim()) {
      toast({ title: 'Validation', description: 'IMAP username is required (needed for reply detection).', variant: 'destructive' });
      return;
    }
    if (!emailForm.imap_password) {
      toast({ title: 'Validation', description: 'IMAP password is required (needed for reply detection).', variant: 'destructive' });
      return;
    }
    setEmailFormLoading(true);
    try {
      const payload = {
        name: emailForm.name.trim(),
        account_type: emailForm.account_type,
        email: emailForm.email.trim(),
        smtp_host: emailForm.smtp_host.trim(),
        smtp_port: Number(emailForm.smtp_port) || 587,
        smtp_username: (emailForm.smtp_username || '').trim() || emailForm.email.trim(),
        smtp_password: emailForm.smtp_password,
        use_tls: emailForm.use_tls,
        use_ssl: emailForm.use_ssl,
        is_gmail_app_password: emailForm.is_gmail_app_password,
        is_active: emailForm.is_active,
        is_default: emailForm.is_default,
        enable_imap_sync: true,
        imap_host: emailForm.imap_host || '',
        imap_port: emailForm.imap_port ? Number(emailForm.imap_port) : null,
        imap_username: emailForm.imap_username || '',
        imap_use_ssl: emailForm.imap_use_ssl,
      };
      if (emailForm.imap_password) payload.imap_password = emailForm.imap_password;

      const res = await marketingAgentService.createEmailAccount(payload);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Account created.' });
        onOpenChange(false);
        if (onCreated) onCreated(res.data);
      } else {
        toast({ title: 'Error', description: res?.message || 'Create failed.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Request failed.', variant: 'destructive' });
    } finally {
      setEmailFormLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add email account</DialogTitle>
          <DialogDescription>SMTP settings for sending campaign emails.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="py-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: account basics + flags */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground">Account</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Account name *</Label>
                    <Input
                      value={emailForm.name}
                      onChange={(e) => setEmailForm((p) => ({ ...p, name: e.target.value }))}
                      placeholder="e.g. Main Gmail"
                    />
                  </div>
                  <div>
                    <Label>Account type</Label>
                    <Select value={emailForm.account_type} onValueChange={applyEmailTypeDefaults}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {EMAIL_ACCOUNT_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label>Email *</Label>
                  <Input
                    type="email"
                    value={emailForm.email}
                    onChange={(e) => handleEmailChange(e.target.value)}
                    placeholder="your@email.com"
                  />
                </div>
                <div className="flex flex-wrap gap-4 pt-1">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={emailForm.is_active} onChange={(e) => setEmailForm((p) => ({ ...p, is_active: e.target.checked }))} />
                    <span className="text-sm">Active</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={emailForm.is_default} onChange={(e) => setEmailForm((p) => ({ ...p, is_default: e.target.checked }))} />
                    <span className="text-sm">Default account</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={emailForm.is_gmail_app_password} onChange={(e) => setEmailForm((p) => ({ ...p, is_gmail_app_password: e.target.checked }))} />
                    <span className="text-sm">Gmail App Password</span>
                  </label>
                </div>
              </div>

              {/* Right: SMTP */}
              <div className="space-y-4 lg:border-l lg:pl-6">
                <h3 className="text-sm font-semibold text-muted-foreground">SMTP settings</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>SMTP host *</Label>
                    <Input
                      value={emailForm.smtp_host}
                      onChange={(e) => setEmailForm((p) => ({ ...p, smtp_host: e.target.value }))}
                      placeholder="smtp.gmail.com"
                    />
                  </div>
                  <div>
                    <Label>SMTP port</Label>
                    <Input
                      type="number"
                      min={1}
                      max={65535}
                      value={emailForm.smtp_port}
                      onChange={(e) => setEmailForm((p) => ({ ...p, smtp_port: e.target.value }))}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>SMTP username *</Label>
                    <Input
                      value={emailForm.smtp_username}
                      onChange={(e) => {
                        setUsernameTouched(true);
                        setEmailForm((p) => ({ ...p, smtp_username: e.target.value }));
                      }}
                      placeholder="Usually same as email"
                    />
                  </div>
                  <div>
                    <Label>SMTP / App password *</Label>
                    <Input
                      type="password"
                      value={emailForm.smtp_password}
                      onChange={(e) => setEmailForm((p) => ({ ...p, smtp_password: e.target.value }))}
                      placeholder="App password for Gmail"
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-4 pt-1">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={emailForm.use_tls} onChange={(e) => setEmailForm((p) => ({ ...p, use_tls: e.target.checked }))} />
                    <span className="text-sm">Use TLS</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={emailForm.use_ssl} onChange={(e) => setEmailForm((p) => ({ ...p, use_ssl: e.target.checked }))} />
                    <span className="text-sm">Use SSL</span>
                  </label>
                </div>
              </div>
            </div>

            {/* IMAP — full width below the two columns. Always on: reply detection
                requires it, so there's no toggle — just editable fields, pre-filled
                from the account type + email and adjustable before saving. */}
            <div className="mt-6 pt-4 border-t">
              <Label className="text-sm font-medium">IMAP settings (reply detection)</Label>
              <div className="mt-3 space-y-3">
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                  <Input
                    placeholder="IMAP host *"
                    value={emailForm.imap_host}
                    onChange={(e) => {
                      setImapHostTouched(true);
                      setEmailForm((p) => ({ ...p, imap_host: e.target.value }));
                    }}
                  />
                  <Input
                    type="number"
                    placeholder="Port"
                    value={emailForm.imap_port}
                    onChange={(e) => setEmailForm((p) => ({ ...p, imap_port: e.target.value }))}
                  />
                  <Input
                    placeholder="IMAP username *"
                    value={emailForm.imap_username}
                    onChange={(e) => {
                      setImapUsernameTouched(true);
                      setEmailForm((p) => ({ ...p, imap_username: e.target.value }));
                    }}
                  />
                  <Input
                    type="password"
                    placeholder="IMAP password *"
                    value={emailForm.imap_password}
                    onChange={(e) => setEmailForm((p) => ({ ...p, imap_password: e.target.value }))}
                  />
                </div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={emailForm.imap_use_ssl} onChange={(e) => setEmailForm((p) => ({ ...p, imap_use_ssl: e.target.checked }))} />
                  <span className="text-sm">IMAP use SSL</span>
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={emailFormLoading}>
              {emailFormLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AddEmailAccountModal;
