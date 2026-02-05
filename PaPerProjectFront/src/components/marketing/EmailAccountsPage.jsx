import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, ArrowLeft, Mail, Plus, Pencil, Trash2, Send } from 'lucide-react';
import {
  listEmailAccounts,
  createEmailAccount,
  getEmailAccount,
  updateEmailAccount,
  deleteEmailAccount,
  testEmailAccount,
} from '@/services/marketingAgentService';

const ACCOUNT_TYPES = [
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

const defaultForm = () => ({
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
  enable_imap_sync: false,
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
});

const EmailAccountsPage = () => {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(defaultForm());
  const [actionLoading, setActionLoading] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [testAccountId, setTestAccountId] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [showImap, setShowImap] = useState(false);

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listEmailAccounts();
      if (res?.status === 'success' && res?.data) {
        setAccounts(res.data);
      } else {
        setError(res?.message || 'Failed to load accounts');
      }
    } catch (e) {
      setError(e?.message || 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const applyTypeDefaults = (accountType) => {
    const d = SMTP_DEFAULTS[accountType] || SMTP_DEFAULTS.smtp;
    setForm((prev) => ({
      ...prev,
      account_type: accountType,
      smtp_host: d.host,
      smtp_port: d.port,
      use_tls: d.useTLS,
      use_ssl: d.useSSL,
      is_gmail_app_password: accountType === 'gmail',
    }));
  };

  const openAdd = () => {
    setEditingId(null);
    setForm(defaultForm());
    applyTypeDefaults('smtp');
    setShowImap(false);
    setModalOpen(true);
  };

  const openEdit = async (id) => {
    setEditingId(id);
    setModalOpen(true);
    try {
      const res = await getEmailAccount(id);
      if (res?.status === 'success' && res?.data) {
        const d = res.data;
        setForm({
          name: d.name || '',
          account_type: d.account_type || 'smtp',
          email: d.email || '',
          smtp_host: d.smtp_host || '',
          smtp_port: d.smtp_port ?? 587,
          smtp_username: d.smtp_username || '',
          smtp_password: '',
          use_tls: d.use_tls ?? true,
          use_ssl: d.use_ssl ?? false,
          is_gmail_app_password: d.is_gmail_app_password ?? false,
          is_active: d.is_active ?? true,
          is_default: d.is_default ?? false,
          enable_imap_sync: d.enable_imap_sync ?? false,
          imap_host: d.imap_host || '',
          imap_port: d.imap_port ?? 993,
          imap_username: d.imap_username || '',
          imap_password: '',
          imap_use_ssl: d.imap_use_ssl ?? true,
        });
        setShowImap(d.enable_imap_sync ?? false);
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to load account', variant: 'destructive' });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name?.trim()) {
      toast({ title: 'Validation', description: 'Account name is required.', variant: 'destructive' });
      return;
    }
    if (!form.email?.trim()) {
      toast({ title: 'Validation', description: 'Email is required.', variant: 'destructive' });
      return;
    }
    if (!form.smtp_host?.trim()) {
      toast({ title: 'Validation', description: 'SMTP host is required.', variant: 'destructive' });
      return;
    }
    if (!editingId && !form.smtp_password) {
      toast({ title: 'Validation', description: 'SMTP password is required for new account.', variant: 'destructive' });
      return;
    }
    setActionLoading(true);
    try {
      const payload = {
        name: form.name.trim(),
        account_type: form.account_type,
        email: form.email.trim(),
        smtp_host: form.smtp_host.trim(),
        smtp_port: Number(form.smtp_port) || 587,
        smtp_username: (form.smtp_username || '').trim() || form.email.trim(),
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
        is_gmail_app_password: form.is_gmail_app_password,
        is_active: form.is_active,
        is_default: form.is_default,
        enable_imap_sync: form.enable_imap_sync,
        imap_host: form.imap_host || '',
        imap_port: form.imap_port ? Number(form.imap_port) : null,
        imap_username: form.imap_username || '',
        imap_use_ssl: form.imap_use_ssl,
      };
      if (form.smtp_password) payload.smtp_password = form.smtp_password;
      if (form.imap_password) payload.imap_password = form.imap_password;

      if (editingId) {
        const res = await updateEmailAccount(editingId, payload);
        if (res?.status === 'success') {
          toast({ title: 'Success', description: res?.data?.message || 'Account updated.' });
          setModalOpen(false);
          fetchAccounts();
        } else {
          toast({ title: 'Error', description: res?.message || 'Update failed.', variant: 'destructive' });
        }
      } else {
        const res = await createEmailAccount(payload);
        if (res?.status === 'success') {
          toast({ title: 'Success', description: res?.data?.message || 'Account created.' });
          setModalOpen(false);
          fetchAccounts();
        } else {
          toast({ title: 'Error', description: res?.message || 'Create failed.', variant: 'destructive' });
        }
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Request failed.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (id, name) => {
    setActionLoading(true);
    try {
      const res = await deleteEmailAccount(id);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Account deleted.' });
        setDeleteConfirm(null);
        fetchAccounts();
      } else {
        toast({ title: 'Error', description: res?.message || 'Delete failed.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Delete failed.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const openTest = (account) => {
    setTestAccountId(account.id);
    setTestEmail(account.email || '');
    setTestModalOpen(true);
  };

  const handleTest = async () => {
    const email = (testEmail || '').trim();
    if (!email) {
      toast({ title: 'Validation', description: 'Enter test email address.', variant: 'destructive' });
      return;
    }
    setTestLoading(true);
    try {
      const res = await testEmailAccount(testAccountId, email);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Test email sent.' });
        setTestModalOpen(false);
        fetchAccounts();
      } else {
        toast({ title: 'Test failed', description: res?.message || 'Could not send test email.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Test failed', description: e?.message || e?.data?.message || 'Could not send test email.', variant: 'destructive' });
    } finally {
      setTestLoading(false);
    }
  };

  const accountTypeLabel = (type) => ACCOUNT_TYPES.find((t) => t.value === type)?.label || type;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[320px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Button variant="ghost" asChild>
            <Link to="/marketing/dashboard">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to dashboard
            </Link>
          </Button>
          <h1 className="text-2xl font-semibold mt-2 flex items-center gap-2">
            <Mail className="h-6 w-6" />
            Email accounts
          </h1>
          <CardDescription>Add and manage SMTP accounts for sending campaign emails.</CardDescription>
        </div>
        <Button onClick={openAdd}>
          <Plus className="mr-2 h-4 w-4" />
          Add email account
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {accounts.length === 0 && !error ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-12 text-muted-foreground">
              <Mail className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="font-medium">No email accounts</p>
              <p className="text-sm mt-1">Add your first account to send campaign emails.</p>
              <Button className="mt-4" onClick={openAdd}>
                <Plus className="mr-2 h-4 w-4" />
                Add email account
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Accounts</CardTitle>
            <CardDescription>Name, email, type, status, and actions.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Name</th>
                    <th className="text-left p-3 font-medium">Email</th>
                    <th className="text-left p-3 font-medium">Type</th>
                    <th className="text-center p-3 font-medium">Status</th>
                    <th className="text-center p-3 font-medium">Test</th>
                    <th className="text-center p-3 font-medium">Default</th>
                    <th className="text-right p-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="p-3 font-medium">{a.name}</td>
                      <td className="p-3">{a.email}</td>
                      <td className="p-3">
                        <Badge variant="outline">{accountTypeLabel(a.account_type)}</Badge>
                      </td>
                      <td className="p-3 text-center">
                        <Badge variant={a.is_active ? 'default' : 'secondary'}>
                          {a.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="p-3 text-center">
                        <Badge
                          variant={
                            a.test_status === 'success'
                              ? 'default'
                              : a.test_status === 'failed'
                                ? 'destructive'
                                : 'secondary'
                          }
                        >
                          {a.test_status === 'success' ? 'Success' : a.test_status === 'failed' ? 'Failed' : 'Not tested'}
                        </Badge>
                      </td>
                      <td className="p-3 text-center">{a.is_default ? 'Default' : '—'}</td>
                      <td className="p-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="outline" size="sm" onClick={() => openTest(a)}>
                            <Send className="h-4 w-4 mr-1" />
                            Test
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => openEdit(a.id)}>
                            <Pencil className="h-4 w-4 mr-1" />
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setDeleteConfirm({ id: a.id, name: a.name })}
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add/Edit modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Edit email account' : 'Add email account'}</DialogTitle>
            <DialogDescription>SMTP settings for sending campaign emails. Leave password blank when editing to keep existing.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div>
                <Label>Account name *</Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Main Gmail"
                />
              </div>
              <div>
                <Label>Account type</Label>
                <Select
                  value={form.account_type}
                  onValueChange={applyTypeDefaults}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ACCOUNT_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Email *</Label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
                  placeholder="your@email.com"
                />
              </div>
              <div>
                <Label>SMTP host *</Label>
                <Input
                  value={form.smtp_host}
                  onChange={(e) => setForm((p) => ({ ...p, smtp_host: e.target.value }))}
                  placeholder="smtp.gmail.com"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>SMTP port</Label>
                  <Input
                    type="number"
                    min={1}
                    max={65535}
                    value={form.smtp_port}
                    onChange={(e) => setForm((p) => ({ ...p, smtp_port: e.target.value }))}
                  />
                </div>
                <div>
                  <Label>SMTP username *</Label>
                  <Input
                    value={form.smtp_username}
                    onChange={(e) => setForm((p) => ({ ...p, smtp_username: e.target.value }))}
                    placeholder="Usually same as email"
                  />
                </div>
              </div>
              <div>
                <Label>SMTP password / App password * {editingId && '(leave blank to keep)'}</Label>
                <Input
                  type="password"
                  value={form.smtp_password}
                  onChange={(e) => setForm((p) => ({ ...p, smtp_password: e.target.value }))}
                  placeholder="App password for Gmail"
                />
              </div>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.use_tls}
                    onChange={(e) => setForm((p) => ({ ...p, use_tls: e.target.checked }))}
                  />
                  <span className="text-sm">Use TLS</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.use_ssl}
                    onChange={(e) => setForm((p) => ({ ...p, use_ssl: e.target.checked }))}
                  />
                  <span className="text-sm">Use SSL</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_gmail_app_password}
                    onChange={(e) => setForm((p) => ({ ...p, is_gmail_app_password: e.target.checked }))}
                  />
                  <span className="text-sm">Gmail App Password</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((p) => ({ ...p, is_active: e.target.checked }))}
                  />
                  <span className="text-sm">Active</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.is_default}
                    onChange={(e) => setForm((p) => ({ ...p, is_default: e.target.checked }))}
                  />
                  <span className="text-sm">Default account</span>
                </label>
              </div>
              <div>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.enable_imap_sync}
                    onChange={(e) => {
                      setForm((p) => ({ ...p, enable_imap_sync: e.target.checked }));
                      setShowImap(e.target.checked);
                    }}
                  />
                  <span className="text-sm">Enable IMAP sync (reply detection)</span>
                </label>
              </div>
              {showImap && (
                <div className="space-y-3 pt-2 border-t">
                  <Label>IMAP (optional)</Label>
                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      placeholder="IMAP host"
                      value={form.imap_host}
                      onChange={(e) => setForm((p) => ({ ...p, imap_host: e.target.value }))}
                    />
                    <Input
                      type="number"
                      placeholder="Port"
                      value={form.imap_port}
                      onChange={(e) => setForm((p) => ({ ...p, imap_port: e.target.value }))}
                    />
                  </div>
                  <Input
                    placeholder="IMAP username"
                    value={form.imap_username}
                    onChange={(e) => setForm((p) => ({ ...p, imap_username: e.target.value }))}
                  />
                  <Input
                    type="password"
                    placeholder="IMAP password"
                    value={form.imap_password}
                    onChange={(e) => setForm((p) => ({ ...p, imap_password: e.target.value }))}
                  />
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={form.imap_use_ssl}
                      onChange={(e) => setForm((p) => ({ ...p, imap_use_ssl: e.target.checked }))}
                    />
                    <span className="text-sm">IMAP use SSL</span>
                  </label>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={actionLoading}>
                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : editingId ? 'Save' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Test modal */}
      <Dialog open={testModalOpen} onOpenChange={setTestModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send test email</DialogTitle>
            <DialogDescription>Enter the recipient address to verify this account.</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label>Test email address</Label>
            <Input
              type="email"
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="recipient@example.com"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleTest} disabled={testLoading}>
              {testLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send test'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete email account?</DialogTitle>
            <DialogDescription>
              This will permanently delete &quot;{deleteConfirm?.name}&quot;. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={actionLoading}
              onClick={() => deleteConfirm && handleDelete(deleteConfirm.id, deleteConfirm.name)}
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default EmailAccountsPage;
