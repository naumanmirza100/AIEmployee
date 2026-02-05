import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import { 
  Loader2, 
  TrendingUp, 
  Target, 
  BarChart3,
  MessageSquare,
  FileText,
  Bell,
  Megaphone,
  Sparkles,
  Mail,
  Plus,
  Pencil,
  Trash2,
  Send,
  X
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import MarketingQA from './MarketingQA';
import MarketResearch from './MarketResearch';
import Campaigns from './Campaigns';
import Documents from './Documents';
import Notifications from './Notifications';

const STATUS_LABELS = {
  draft: 'Draft',
  active: 'Active',
  paused: 'Paused',
  completed: 'Completed',
  scheduled: 'Scheduled',
  cancelled: 'Cancelled',
};

const STATUS_BADGE_CLASS = {
  draft: 'bg-gray-100 text-gray-800',
  active: 'bg-green-100 text-green-800',
  paused: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-blue-100 text-blue-800',
  scheduled: 'bg-indigo-100 text-indigo-800',
  cancelled: 'bg-red-100 text-red-800',
};

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
};

const ACCOUNT_TYPE_LABELS = {
  gmail: 'Gmail',
  outlook: 'Outlook',
  hostinger: 'Hostinger',
  smtp: 'Custom SMTP',
  custom: 'Custom SMTP',
};

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
  enable_imap_sync: false,
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
});

const MarketingDashboard = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [campaignsLoading, setCampaignsLoading] = useState(true);
  const [emailAccountsLoading, setEmailAccountsLoading] = useState(false);
  const [emailAccounts, setEmailAccounts] = useState([]);
  const [stats, setStats] = useState({
    totalCampaigns: 0,
    activeCampaigns: 0,
  });
  const [campaigns, setCampaigns] = useState([]);

  // Email tab: sidebar and modals
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [addOrEditModalOpen, setAddOrEditModalOpen] = useState(false);
  const [editingAccountId, setEditingAccountId] = useState(null);
  const [emailForm, setEmailForm] = useState(defaultEmailForm());
  const [emailFormLoading, setEmailFormLoading] = useState(false);
  const [showImap, setShowImap] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [testAccountId, setTestAccountId] = useState(null);
  const [testEmailTo, setTestEmailTo] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [notificationUnreadCount, setNotificationUnreadCount] = useState(0);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchNotificationUnreadCount = useCallback(async () => {
    try {
      const response = await marketingAgentService.getNotifications({ unread_only: true });
      if (response.status === 'success' && response.data && typeof response.data.unread_count === 'number') {
        setNotificationUnreadCount(response.data.unread_count);
      } else {
        setNotificationUnreadCount(0);
      }
    } catch {
      setNotificationUnreadCount(0);
    }
  }, []);

  useEffect(() => {
    fetchNotificationUnreadCount();
  }, [fetchNotificationUnreadCount]);

  useEffect(() => {
    if (activeTab === 'notifications') {
      fetchNotificationUnreadCount();
    }
  }, [activeTab, fetchNotificationUnreadCount]);

  useEffect(() => {
    if (activeTab === 'dashboard') {
      fetchCampaigns();
    } else if (activeTab === 'email') {
      fetchEmailAccounts();
    }
  }, [activeTab]);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const response = await marketingAgentService.getMarketingDashboard();
      
      if (response.status === 'success' && response.data) {
        setStats({
          totalCampaigns: response.data.stats?.total_campaigns || 0,
          activeCampaigns: response.data.stats?.active_campaigns || 0,
        });
      }
    } catch {
      setStats({ totalCampaigns: 0, activeCampaigns: 0 });
    } finally {
      setLoading(false);
    }
  };

  const fetchCampaigns = async () => {
    try {
      setCampaignsLoading(true);
      const response = await marketingAgentService.listCampaigns();
      if (response?.status === 'success' && response?.data) {
        setCampaigns(response.data.campaigns || []);
      }
    } catch {
      setCampaigns([]);
    } finally {
      setCampaignsLoading(false);
    }
  };

  const fetchEmailAccounts = async () => {
    try {
      setEmailAccountsLoading(true);
      const response = await marketingAgentService.listEmailAccounts();
      const list = response?.status === 'success' && response?.data ? response.data : [];
      setEmailAccounts(list);
      return list;
    } catch {
      setEmailAccounts([]);
      return [];
    } finally {
      setEmailAccountsLoading(false);
    }
  };

  const applyEmailTypeDefaults = (accountType) => {
    const d = SMTP_DEFAULTS[accountType] || SMTP_DEFAULTS.smtp;
    setEmailForm((prev) => ({
      ...prev,
      account_type: accountType,
      smtp_host: d.host,
      smtp_port: d.port,
      use_tls: d.useTLS,
      use_ssl: d.useSSL,
      is_gmail_app_password: accountType === 'gmail',
    }));
  };

  const openAddEmailAccount = () => {
    setEditingAccountId(null);
    setEmailForm(defaultEmailForm());
    applyEmailTypeDefaults('smtp');
    setShowImap(false);
    setAddOrEditModalOpen(true);
  };

  const openEditEmailAccount = useCallback(async (id) => {
    setEditingAccountId(id);
    setAddOrEditModalOpen(true);
    try {
      const res = await marketingAgentService.getEmailAccount(id);
      if (res?.status === 'success' && res?.data) {
        const d = res.data;
        setEmailForm({
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
  }, [toast]);

  const handleEmailSubmit = async (e) => {
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
    if (!editingAccountId && !emailForm.smtp_password) {
      toast({ title: 'Validation', description: 'SMTP password is required for new account.', variant: 'destructive' });
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
        use_tls: emailForm.use_tls,
        use_ssl: emailForm.use_ssl,
        is_gmail_app_password: emailForm.is_gmail_app_password,
        is_active: emailForm.is_active,
        is_default: emailForm.is_default,
        enable_imap_sync: emailForm.enable_imap_sync,
        imap_host: emailForm.imap_host || '',
        imap_port: emailForm.imap_port ? Number(emailForm.imap_port) : null,
        imap_username: emailForm.imap_username || '',
        imap_use_ssl: emailForm.imap_use_ssl,
      };
      if (emailForm.smtp_password) payload.smtp_password = emailForm.smtp_password;
      if (emailForm.imap_password) payload.imap_password = emailForm.imap_password;

      if (editingAccountId) {
        const res = await marketingAgentService.updateEmailAccount(editingAccountId, payload);
        if (res?.status === 'success') {
          toast({ title: 'Success', description: res?.data?.message || 'Account updated.' });
          setAddOrEditModalOpen(false);
          fetchEmailAccounts();
          if (selectedAccount?.id === editingAccountId) setSelectedAccount(null);
        } else {
          toast({ title: 'Error', description: res?.message || 'Update failed.', variant: 'destructive' });
        }
      } else {
        const res = await marketingAgentService.createEmailAccount(payload);
        if (res?.status === 'success') {
          toast({ title: 'Success', description: res?.data?.message || 'Account created.' });
          setAddOrEditModalOpen(false);
          fetchEmailAccounts();
        } else {
          toast({ title: 'Error', description: res?.message || 'Create failed.', variant: 'destructive' });
        }
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Request failed.', variant: 'destructive' });
    } finally {
      setEmailFormLoading(false);
    }
  };

  const handleEmailDelete = async (id, name) => {
    setDeleteLoading(true);
    try {
      const res = await marketingAgentService.deleteEmailAccount(id);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Account deleted.' });
        setDeleteConfirm(null);
        setSelectedAccount(null);
        fetchEmailAccounts();
      } else {
        toast({ title: 'Error', description: res?.message || 'Delete failed.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Delete failed.', variant: 'destructive' });
    } finally {
      setDeleteLoading(false);
    }
  };

  const openTestEmailAccount = (account) => {
    setTestAccountId(account.id);
    setTestEmailTo(account.email || '');
    setTestModalOpen(true);
  };

  const handleTestEmailAccount = async () => {
    const email = (testEmailTo || '').trim();
    if (!email) {
      toast({ title: 'Validation', description: 'Enter test email address.', variant: 'destructive' });
      return;
    }
    setTestLoading(true);
    try {
      const res = await marketingAgentService.testEmailAccount(testAccountId, email);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: res?.data?.message || 'Test email sent.' });
        setTestModalOpen(false);
        const list = await fetchEmailAccounts();
        if (selectedAccount?.id === testAccountId) {
          const updated = list.find((a) => a.id === testAccountId);
          if (updated) setSelectedAccount(updated);
        }
      } else {
        toast({ title: 'Test failed', description: res?.message || 'Could not send test email.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Test failed', description: e?.message || e?.data?.message || 'Could not send test email.', variant: 'destructive' });
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Campaigns</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalCampaigns}</div>
            <p className="text-xs text-muted-foreground">All campaigns</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Campaigns</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.activeCampaigns}</div>
            <p className="text-xs text-muted-foreground">Currently running</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex flex-wrap gap-1 w-full">
          <TabsTrigger value="dashboard" className="flex-1 min-w-[100px]">
            <BarChart3 className="h-4 w-4 mr-2" />
            Dashboard
          </TabsTrigger>
          <TabsTrigger value="campaigns" className="flex-1 min-w-[100px]">
            <Megaphone className="h-4 w-4 mr-2" />
            Campaigns
          </TabsTrigger>
          <TabsTrigger value="email" className="flex-1 min-w-[100px]">
            <Mail className="h-4 w-4 mr-2" />
            Email
          </TabsTrigger>
          <TabsTrigger value="qa" className="flex-1 min-w-[100px]">
            <MessageSquare className="h-4 w-4 mr-2" />
            Q&A
          </TabsTrigger>
          <TabsTrigger value="research" className="flex-1 min-w-[100px]">
            <Sparkles className="h-4 w-4 mr-2" />
            Research
          </TabsTrigger>
          <TabsTrigger value="documents" className="flex-1 min-w-[100px]">
            <FileText className="h-4 w-4 mr-2" />
            Documents
          </TabsTrigger>
          <TabsTrigger value="notifications" className="flex-1 min-w-[100px] relative">
            <Bell className="h-4 w-4 mr-2" />
            Notifications
            {notificationUnreadCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground"
                title={`${notificationUnreadCount} unread`}
              >
                {notificationUnreadCount > 99 ? '99+' : notificationUnreadCount}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Marketing Overview</CardTitle>
                  <CardDescription>
                    Your marketing campaigns and performance metrics
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Use the Campaigns tab to create and manage email campaigns. Use the Email tab to manage accounts and see sending stats.
                  </p>

                  {/* Campaigns list (like backend campaigns_list.html) */}
                  <div>
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Your Campaigns</h3>
                    {campaignsLoading ? (
                      <div className="flex justify-center py-6">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      </div>
                    ) : campaigns.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-4">No campaigns yet. Create one from the Campaigns tab.</p>
                    ) : (
                      <div className="rounded-lg border overflow-hidden">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="bg-muted/50 border-b">
                              <th className="text-left font-semibold p-3">Campaign Name</th>
                              <th className="text-left font-semibold p-3">Status</th>
                              <th className="text-left font-semibold p-3">Type</th>
                              <th className="text-left font-semibold p-3">Created</th>
                              <th className="text-left font-semibold p-3">Scheduled</th>
                              <th className="text-left font-semibold p-3">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {campaigns.map((campaign) => (
                              <tr key={campaign.id} className="border-b last:border-0 hover:bg-muted/30">
                                <td className="p-3">
                                  <div className="font-medium">{campaign.name}</div>
                                  {campaign.description && (
                                    <div className="text-muted-foreground truncate max-w-[200px]" title={campaign.description}>
                                      {campaign.description.length > 30 ? campaign.description.slice(0, 30) + '…' : campaign.description}
                                    </div>
                                  )}
                                </td>
                                <td className="p-3">
                                  <Badge variant="secondary" className={STATUS_BADGE_CLASS[campaign.status] || 'bg-gray-100 text-gray-800'}>
                                    {STATUS_LABELS[campaign.status] || campaign.status}
                                  </Badge>
                                </td>
                                <td className="p-3 text-muted-foreground">{campaign.campaign_type || '—'}</td>
                                <td className="p-3 text-muted-foreground">{formatDate(campaign.created_at)}</td>
                                <td className="p-3 text-muted-foreground">{campaign.start_date ? formatDate(campaign.start_date) : '—'}</td>
                                <td className="p-3">
                                  <Button
                                    variant="default"
                                    size="sm"
                                    asChild
                                  >
                                    <Link to={`/marketing/dashboard/campaign/${campaign.id}`}>Manage</Link>
                                  </Button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <div className="relative flex gap-4">
            <Card className={selectedAccount ? 'flex-1 min-w-0' : 'w-full'}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle>Email accounts</CardTitle>
                  <CardDescription>
                    Accounts used to send campaign emails. Click an account to see details in the sidebar.
                  </CardDescription>
                </div>
                <Button variant="default" size="sm" onClick={openAddEmailAccount}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add email account
                </Button>
              </CardHeader>
              <CardContent>
                {emailAccountsLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : emailAccounts.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <Mail className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p className="font-medium">No email accounts</p>
                    <p className="text-sm mt-1">Add an account to send campaign emails from sequences.</p>
                    <Button className="mt-4" onClick={openAddEmailAccount}>
                      <Plus className="mr-2 h-4 w-4" />
                      Add email account
                    </Button>
                  </div>
                ) : (
                  <div className="rounded-lg border overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-muted/50 border-b">
                          <th className="text-left font-semibold p-3">Account</th>
                          <th className="text-left font-semibold p-3">Email</th>
                          <th className="text-left font-semibold p-3">Type</th>
                          <th className="text-center font-semibold p-3">Status</th>
                          <th className="text-center font-semibold p-3">Test</th>
                          <th className="text-center font-semibold p-3">Sent</th>
                          {/* <th className="text-center font-semibold p-3">Opened</th> */}
                          <th className="text-center font-semibold p-3">Clicked</th>
                          {/* <th className="text-center font-semibold p-3">Open rate</th> */}
                          {/* <th className="text-center font-semibold p-3">Click rate</th> */}
                        </tr>
                      </thead>
                      <tbody>
                        {emailAccounts.map((acc) => (
                          <tr
                            key={acc.id}
                            className={`border-b last:border-0 hover:bg-muted/30 cursor-pointer ${selectedAccount?.id === acc.id ? 'bg-muted/50' : ''}`}
                            onClick={() => setSelectedAccount(acc)}
                          >
                            <td className="p-3">
                              <div className="font-medium">{acc.name}</div>
                              {acc.is_default && (
                                <Badge variant="secondary" className="text-xs mt-0.5">Default</Badge>
                              )}
                            </td>
                            <td className="p-3 text-muted-foreground">{acc.email}</td>
                            <td className="p-3">
                              <Badge variant="outline">{ACCOUNT_TYPE_LABELS[acc.account_type] || acc.account_type}</Badge>
                            </td>
                            <td className="p-3 text-center">
                              <Badge variant={acc.is_active ? 'default' : 'secondary'}>
                                {acc.is_active ? 'Active' : 'Inactive'}
                              </Badge>
                            </td>
                            <td className="p-3 text-center">
                              <Badge
                                variant={
                                  acc.test_status === 'success'
                                    ? 'default'
                                    : acc.test_status === 'failed'
                                      ? 'destructive'
                                      : 'secondary'
                                }
                              >
                                {acc.test_status === 'success' ? 'OK' : acc.test_status === 'failed' ? 'Failed' : 'Not tested'}
                              </Badge>
                            </td>
                            <td className="p-3 text-center font-medium">{acc.sent_count ?? 0}</td>
                            {/* <td className="p-3 text-center">{acc.opened_count ?? 0}</td> */}
                            <td className="p-3 text-center">{acc.clicked_count ?? 0}</td>
                            {/* <td className="p-3 text-center text-muted-foreground">
                              {(acc.open_rate ?? 0) > 0 ? `${acc.open_rate}%` : '—'}
                            </td> */}
                            {/* <td className="p-3 text-center text-muted-foreground">
                              {(acc.click_rate ?? 0) > 0 ? `${acc.click_rate}%` : '—'}
                            </td> */}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Right-side account details sidebar */}
            {selectedAccount && (
              <div className="w-[380px] shrink-0 flex flex-col rounded-lg border bg-card shadow-sm overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b bg-muted/30">
                  <h3 className="font-semibold text-base">Account details</h3>
                  <Button variant="ghost" size="icon" onClick={() => setSelectedAccount(null)} aria-label="Close">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Name</p>
                    <p className="font-medium">{selectedAccount.name}</p>
                    {selectedAccount.is_default && (
                      <Badge variant="secondary" className="mt-1">Default</Badge>
                    )}
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Email</p>
                    <p className="text-sm">{selectedAccount.email}</p>
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Type</p>
                    <Badge variant="outline">{ACCOUNT_TYPE_LABELS[selectedAccount.account_type] || selectedAccount.account_type}</Badge>
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Status</p>
                    <Badge variant={selectedAccount.is_active ? 'default' : 'secondary'}>
                      {selectedAccount.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Created</p>
                    <p className="text-sm">{formatDate(selectedAccount.created_at)}</p>
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Updated</p>
                    <p className="text-sm">{formatDate(selectedAccount.updated_at)}</p>
                  </div>
                  <div className="flex gap-2 items-center">
                    <p className="text-sm font-medium text-muted-foreground">Last tested</p>
                    <p className="text-sm">{formatDate(selectedAccount.last_tested_at) || 'Never'}</p>
                    <Badge
                      variant={
                        selectedAccount.test_status === 'success'
                          ? 'default'
                          : selectedAccount.test_status === 'failed'
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      {selectedAccount.test_status === 'success' ? 'Success' : selectedAccount.test_status === 'failed' ? 'Failed' : 'Not tested'}
                    </Badge>
                    {selectedAccount.test_error && (
                      <p className="text-xs text-destructive mt-1 break-words">{selectedAccount.test_error}</p>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-2 border-t">
                    <div className="text-center">
                      <p className="text-lg font-semibold">{selectedAccount.sent_count ?? 0}</p>
                      <p className="text-xs text-muted-foreground">Sent</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold">{selectedAccount.opened_count ?? 0}</p>
                      <p className="text-xs text-muted-foreground">Opened</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold">{selectedAccount.clicked_count ?? 0}</p>
                      <p className="text-xs text-muted-foreground">Clicked</p>
                    </div>
                  </div>
                  <div className="flex gap-6 text-sm text-muted-foreground justify-center">
                    <span>Open rate: {(selectedAccount.open_rate ?? 0) > 0 ? `${selectedAccount.open_rate}%` : '—'}</span>
                    <span>Click rate: {(selectedAccount.click_rate ?? 0) > 0 ? `${selectedAccount.click_rate}%` : '—'}</span>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2 border-t justify-center items-center">
                    <Button variant="outline" size="sm" onClick={() => openEditEmailAccount(selectedAccount.id)}>
                      <Pencil className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openTestEmailAccount(selectedAccount)}>
                      <Send className="h-4 w-4 mr-1" />
                      Test
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setDeleteConfirm({ id: selectedAccount.id, name: selectedAccount.name })}
                    >
                      <Trash2 className="h-4 w-4 mr-1" />
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Add/Edit email account modal */}
          <Dialog open={addOrEditModalOpen} onOpenChange={setAddOrEditModalOpen}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editingAccountId ? 'Edit email account' : 'Add email account'}</DialogTitle>
                <DialogDescription>SMTP settings for sending campaign emails. Leave password blank when editing to keep existing.</DialogDescription>
              </DialogHeader>
              <form onSubmit={handleEmailSubmit}>
                <div className="space-y-4 py-4">
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
                  <div>
                    <Label>Email *</Label>
                    <Input
                      type="email"
                      value={emailForm.email}
                      onChange={(e) => setEmailForm((p) => ({ ...p, email: e.target.value }))}
                      placeholder="your@email.com"
                    />
                  </div>
                  <div>
                    <Label>SMTP host *</Label>
                    <Input
                      value={emailForm.smtp_host}
                      onChange={(e) => setEmailForm((p) => ({ ...p, smtp_host: e.target.value }))}
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
                        value={emailForm.smtp_port}
                        onChange={(e) => setEmailForm((p) => ({ ...p, smtp_port: e.target.value }))}
                      />
                    </div>
                    <div>
                      <Label>SMTP username *</Label>
                      <Input
                        value={emailForm.smtp_username}
                        onChange={(e) => setEmailForm((p) => ({ ...p, smtp_username: e.target.value }))}
                        placeholder="Usually same as email"
                      />
                    </div>
                  </div>
                  <div>
                    <Label>SMTP password / App password * {editingAccountId && '(leave blank to keep)'}</Label>
                    <Input
                      type="password"
                      value={emailForm.smtp_password}
                      onChange={(e) => setEmailForm((p) => ({ ...p, smtp_password: e.target.value }))}
                      placeholder="App password for Gmail"
                    />
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={emailForm.use_tls} onChange={(e) => setEmailForm((p) => ({ ...p, use_tls: e.target.checked }))} />
                      <span className="text-sm">Use TLS</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={emailForm.use_ssl} onChange={(e) => setEmailForm((p) => ({ ...p, use_ssl: e.target.checked }))} />
                      <span className="text-sm">Use SSL</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={emailForm.is_gmail_app_password} onChange={(e) => setEmailForm((p) => ({ ...p, is_gmail_app_password: e.target.checked }))} />
                      <span className="text-sm">Gmail App Password</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={emailForm.is_active} onChange={(e) => setEmailForm((p) => ({ ...p, is_active: e.target.checked }))} />
                      <span className="text-sm">Active</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={emailForm.is_default} onChange={(e) => setEmailForm((p) => ({ ...p, is_default: e.target.checked }))} />
                      <span className="text-sm">Default account</span>
                    </label>
                  </div>
                  <div>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={emailForm.enable_imap_sync}
                        onChange={(e) => {
                          setEmailForm((p) => ({ ...p, enable_imap_sync: e.target.checked }));
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
                        <Input placeholder="IMAP host" value={emailForm.imap_host} onChange={(e) => setEmailForm((p) => ({ ...p, imap_host: e.target.value }))} />
                        <Input type="number" placeholder="Port" value={emailForm.imap_port} onChange={(e) => setEmailForm((p) => ({ ...p, imap_port: e.target.value }))} />
                      </div>
                      <Input placeholder="IMAP username" value={emailForm.imap_username} onChange={(e) => setEmailForm((p) => ({ ...p, imap_username: e.target.value }))} />
                      <Input type="password" placeholder="IMAP password" value={emailForm.imap_password} onChange={(e) => setEmailForm((p) => ({ ...p, imap_password: e.target.value }))} />
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={emailForm.imap_use_ssl} onChange={(e) => setEmailForm((p) => ({ ...p, imap_use_ssl: e.target.checked }))} />
                        <span className="text-sm">IMAP use SSL</span>
                      </label>
                    </div>
                  )}
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setAddOrEditModalOpen(false)}>Cancel</Button>
                  <Button type="submit" disabled={emailFormLoading}>
                    {emailFormLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : editingAccountId ? 'Save' : 'Create'}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>

          {/* Test email modal */}
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
                  value={testEmailTo}
                  onChange={(e) => setTestEmailTo(e.target.value)}
                  placeholder="recipient@example.com"
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setTestModalOpen(false)}>Cancel</Button>
                <Button onClick={handleTestEmailAccount} disabled={testLoading}>
                  {testLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send test'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Delete confirm dialog */}
          <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete email account?</DialogTitle>
                <DialogDescription>
                  This will permanently delete &quot;{deleteConfirm?.name}&quot;. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end gap-2 pt-4">
                <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
                <Button
                  variant="destructive"
                  disabled={deleteLoading}
                  onClick={() => deleteConfirm && handleEmailDelete(deleteConfirm.id, deleteConfirm.name)}
                >
                  {deleteLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Delete'}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>

        <TabsContent value="campaigns">
          <Campaigns onRefresh={fetchStats} />
        </TabsContent>

        <TabsContent value="qa">
          <MarketingQA />
        </TabsContent>

        <TabsContent value="research">
          <MarketResearch />
        </TabsContent>

        <TabsContent value="documents">
          <Documents />
        </TabsContent>

        <TabsContent value="notifications">
          <Notifications onUnreadCountChange={fetchNotificationUnreadCount} />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default MarketingDashboard;

