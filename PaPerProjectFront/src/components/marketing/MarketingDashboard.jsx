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
import { Checkbox } from '@/components/ui/checkbox';
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
  X,
  ChevronLeft,
  ChevronRight,
  BarChart3 as BarChartIcon,
  PieChart,
  LineChart,
  AreaChart,
  Eye,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import marketingAgentService, {
  getSavedGraphPrompts,
  isGraphPromptOnDashboard,
  generateGraph,
} from '@/services/marketingAgentService';
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
  const [campaignsPage, setCampaignsPage] = useState(1);
  const [campaignsTotal, setCampaignsTotal] = useState(0);
  const [selectedCampaigns, setSelectedCampaigns] = useState(new Set());
  const [dashboardDeleting, setDashboardDeleting] = useState(false);
  const [dashboardDeleteConfirmOpen, setDashboardDeleteConfirmOpen] = useState(false);
  const DASHBOARD_CAMPAIGNS_PAGE_SIZE = 10;

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
  const [dashboardGraphPrompts, setDashboardGraphPrompts] = useState([]);
  const [savedGraphPrompts, setSavedGraphPrompts] = useState([]);
  const [savedGraphsLoading, setSavedGraphsLoading] = useState(false);
  const [savedGraphsPage, setSavedGraphsPage] = useState(1);
  const [savedGraphsTotalPages, setSavedGraphsTotalPages] = useState(1);
  const [savedGraphsTotal, setSavedGraphsTotal] = useState(0);
  const SAVED_GRAPHS_PAGE_SIZE = 9;
  const [viewingGraphId, setViewingGraphId] = useState(null);
  const [viewingGraphResult, setViewingGraphResult] = useState(null);
  const [viewingGraphLoading, setViewingGraphLoading] = useState(false);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchSavedGraphPrompts = async (page = savedGraphsPage) => {
    try {
      setSavedGraphsLoading(true);
      const response = await getSavedGraphPrompts({ page, page_size: SAVED_GRAPHS_PAGE_SIZE });
      if (response?.status === 'success' && Array.isArray(response.data)) {
        setSavedGraphPrompts(response.data);
        if (response.pagination) {
          setSavedGraphsPage(response.pagination.page);
          setSavedGraphsTotalPages(response.pagination.total_pages);
          setSavedGraphsTotal(response.pagination.total);
        }
      } else {
        setSavedGraphPrompts([]);
      }
    } catch (error) {
      console.error('Fetch saved graphs error:', error);
      setSavedGraphPrompts([]);
    } finally {
      setSavedGraphsLoading(false);
    }
  };

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
      fetchCampaigns(campaignsPage);
      fetchEmailAccounts();
      getSavedGraphPrompts()
        .then((res) => {
          if (res?.status === 'success' && Array.isArray(res.data)) {
            setDashboardGraphPrompts(res.data.filter(isGraphPromptOnDashboard));
          }
        })
        .catch(() => setDashboardGraphPrompts([]));
    } else if (activeTab === 'email') {
      fetchEmailAccounts();
    } else if (activeTab === 'saved-graphs') {
      fetchSavedGraphPrompts(1);
    }
  }, [activeTab, campaignsPage]);

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

  const fetchCampaigns = async (page = 1) => {
    try {
      setCampaignsLoading(true);
      const response = await marketingAgentService.listCampaigns({
        page,
        limit: DASHBOARD_CAMPAIGNS_PAGE_SIZE,
      });
      if (response?.status === 'success' && response?.data) {
        setCampaigns(response.data.campaigns || []);
        setCampaignsTotal(response.data.total ?? 0);
      }
    } catch {
      setCampaigns([]);
      setCampaignsTotal(0);
    } finally {
      setCampaignsLoading(false);
    }
  };

  // Clear campaign selection when campaigns list changes
  useEffect(() => {
    setSelectedCampaigns(new Set());
  }, [campaigns]);

  const selectableDashCampaigns = campaigns.filter((c) => c.status !== 'active');
  const allDashSelectableChecked = selectableDashCampaigns.length > 0 && selectableDashCampaigns.every((c) => selectedCampaigns.has(c.id));

  const toggleDashSelect = (id) => {
    setSelectedCampaigns((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleDashSelectAll = () => {
    if (allDashSelectableChecked) {
      setSelectedCampaigns(new Set());
    } else {
      setSelectedCampaigns(new Set(selectableDashCampaigns.map((c) => c.id)));
    }
  };

  const handleDashBulkDelete = async () => {
    setDashboardDeleteConfirmOpen(false);
    setDashboardDeleting(true);
    let successCount = 0;
    let failCount = 0;
    for (const cid of selectedCampaigns) {
      try {
        await marketingAgentService.campaignDelete(cid);
        successCount++;
      } catch {
        failCount++;
      }
    }
    setDashboardDeleting(false);
    setSelectedCampaigns(new Set());
    if (successCount > 0) {
      toast({ title: 'Deleted', description: `${successCount} campaign${successCount > 1 ? 's' : ''} deleted successfully` });
    }
    if (failCount > 0) {
      toast({ title: 'Error', description: `${failCount} campaign${failCount > 1 ? 's' : ''} failed to delete`, variant: 'destructive' });
    }
    fetchCampaigns(campaignsPage);
    fetchDashboardData();
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

  const handleDeleteGraphPrompt = async (promptId) => {
    try {
      const res = await marketingAgentService.deleteGraphPrompt(promptId);
      if (res?.status === 'success') {
        toast({ title: 'Success', description: 'Graph prompt deleted.' });
        const nextPage = savedGraphPrompts.length === 1 && savedGraphsPage > 1 ? savedGraphsPage - 1 : savedGraphsPage;
        fetchSavedGraphPrompts(nextPage);
        // Clear viewing if deleted prompt
        if (viewingGraphId === promptId) {
          setViewingGraphId(null);
          setViewingGraphResult(null);
        }
      } else {
        toast({ title: 'Error', description: res?.message || 'Delete failed.', variant: 'destructive' });
      }
    } catch (error) {
      console.error('Delete graph prompt error:', error);
      toast({ title: 'Error', description: 'Failed to delete graph prompt.', variant: 'destructive' });
    }
  };

  const handleViewGraph = async (prompt) => {
    setViewingGraphId(prompt.id);
    setViewingGraphResult(null);
    setViewingGraphLoading(true);
    try {
      const response = await generateGraph(prompt.prompt);
      if (response?.status === 'success' && response?.data) {
        const d = response.data;
        setViewingGraphResult({
          chart: d.chart || null,
          title: d.chart?.title || d.chartTitle || d.title || prompt?.title || 'Saved Graph',
          insights: d.insights || [],
        });
      } else {
        setViewingGraphResult({
          title: prompt?.title || 'Saved Graph',
          insights: [],
          chart: null,
        });
      }
    } catch (error) {
      console.error('Error generating graph:', error);
      setViewingGraphResult({
        title: prompt?.title || 'Saved Graph',
        insights: [],
        chart: null,
      });
    } finally {
      setViewingGraphLoading(false);
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

  const totalEmailsSent = emailAccounts.reduce((sum, account) => sum + (Number(account?.sent_count) || 0), 0);

  return (
    <div
      className="w-full rounded-2xl max-w-full border border-white/[0.06] p-0 overflow-hidden"
      style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
    >
    <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
      {/* Chart rendering helper */}
      {(() => {
        // Define renderChart as an IIFE to use in JSX
        window.renderChart = (chartData) => {
          if (!chartData) return null;
          const { type, data, title, color = '#3b82f6', colors } = chartData;
          
          // SimpleBarChart
          const SimpleBarChart = ({ data, colors, height = 250, title }) => {
            if (!data || Object.keys(data).length === 0) return null;
            const maxValue = Math.max(...Object.values(data), 1);
            const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
            const chartColors = colors || defaultColors;
            return (
              <div className="space-y-3" style={{ minHeight: `${height}px` }}>
                {title && <h4 className="font-medium text-sm text-muted-foreground mb-4">{title}</h4>}
                {Object.entries(data).map(([key, value], index) => (
                  <div key={key}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-sm">{key}</span>
                      <span className="font-semibold">{value}</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all"
                        style={{
                          width: `${(value / maxValue) * 100}%`,
                          backgroundColor: chartColors[index % chartColors.length],
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            );
          };
          
          // SimplePieChart
          const SimplePieChart = ({ data, colors, title }) => {
            if (!data || Object.keys(data).length === 0) return null;
            const total = Object.values(data).reduce((sum, val) => sum + val, 0);
            if (total === 0) return null;
            const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
            const chartColors = colors || defaultColors;
            let currentAngle = 0;
            const segments = Object.entries(data).map(([key, value], index) => {
              const percentage = (value / total) * 100;
              const sliceAngle = (value / total) * 360;
              const startAngle = currentAngle;
              currentAngle += sliceAngle;
              return { key, value, percentage, startAngle, sliceAngle, color: chartColors[index % chartColors.length] };
            });
            return (
              <div className="flex flex-col items-center gap-4">
                {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
                <div className="relative w-48 h-48 sm:w-56 sm:h-56">
                  <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
                    {segments.map((segment, index) => {
                      const startRad = (segment.startAngle * Math.PI) / 180;
                      const endRad = ((segment.startAngle + segment.sliceAngle) * Math.PI) / 180;
                      const x1 = 100 + 100 * Math.cos(startRad);
                      const y1 = 100 + 100 * Math.sin(startRad);
                      const x2 = 100 + 100 * Math.cos(endRad);
                      const y2 = 100 + 100 * Math.sin(endRad);
                      const largeArc = segment.sliceAngle > 180 ? 1 : 0;
                      const pathData = `M 100 100 L ${x1} ${y1} A 100 100 0 ${largeArc} 1 ${x2} ${y2} Z`;
                      return <path key={index} d={pathData} fill={segment.color} stroke="white" strokeWidth="2" />;
                    })}
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{total}</div>
                      <div className="text-xs text-muted-foreground">Total</div>
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
                  {segments.map((segment, index) => (
                    <div key={index} className="flex items-center gap-2 text-xs sm:text-sm">
                      <div className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: segment.color }} />
                      <span className="truncate flex-1">{segment.key}</span>
                      <span className="font-medium shrink-0">{segment.percentage.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          };
          
          // SimpleLineChart
          const SimpleLineChart = ({ data, color = '#3b82f6', height = 220, title }) => {
            if (!data || data.length === 0) return null;
            const values = data.map(d => d.value ?? d.count ?? 0);
            const maxValue = Math.max(...values, 1);
            const minValue = Math.min(...values, 0);
            const labels = data.map(d => d.label ?? d.date ?? d.month ?? '');
            const range = maxValue - minValue || 1;

            const formatVal = (v) => {
              const n = Number(v);
              if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
              if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
              return Number.isInteger(n) ? String(n) : n.toFixed(1);
            };

            const padL = 8;
            const padR = 3;
            const padT = 3;
            const padB = 3;
            const chartW = 100 - padL - padR;
            const chartH = 100 - padT - padB;
            const yTicks = [0, 1, 2, 3].map(i => ({
              val: minValue + (range * i) / 3,
              y: padT + chartH - (i / 3) * chartH,
            }));

            const chartPoints = values.map((value, index) => {
              const x = padL + (index / (values.length - 1 || 1)) * chartW;
              const y = padT + chartH - ((value - minValue) / range) * chartH;
              return { x, y };
            });
            const points = chartPoints.map(p => `${p.x},${p.y}`).join(' ');
            const lastX = chartPoints[chartPoints.length - 1]?.x ?? (padL + chartW);
            const firstX = chartPoints[0]?.x ?? padL;
            const areaPoints = `${firstX},${padT + chartH} ${points} ${lastX},${padT + chartH}`;

            return (
              <div className="space-y-2 overflow-hidden">
                {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
                <div className="relative w-full" style={{ height: `${height}px`, marginBottom: '22px' }}>
                  <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" className="overflow-visible">
                    {yTicks.map((tick, i) => (
                      <line key={i} x1={padL} y1={tick.y} x2={padL + chartW} y2={tick.y} stroke="rgba(255,255,255,0.06)" strokeWidth="0.15" />
                    ))}
                    <polygon points={areaPoints} fill={`${color}20`} />
                    <polyline points={points} fill="none" stroke={color} strokeWidth="0.5" strokeLinecap="round" strokeLinejoin="round" />
                    {chartPoints.map((pt, index) => (
                      <circle key={index} cx={pt.x} cy={pt.y} r="1" fill={color} />
                    ))}
                  </svg>
                  {/* Y-axis labels — positioned to match SVG grid lines */}
                  {yTicks.map((tick, i) => (
                    <span key={i} className="absolute text-[9px] text-white/40 leading-none" style={{ top: `${tick.y}%`, left: 0, width: '7%', textAlign: 'right', transform: 'translateY(-50%)' }}>
                      {formatVal(tick.val)}
                    </span>
                  ))}
                  {/* X-axis labels */}
                  <div className="absolute flex justify-between text-[10px] text-white/50" style={{ left: `${padL}%`, right: `${padR}%`, bottom: '-20px' }}>
                    {labels.map((label, i) => (
                      <span key={i} className="text-center truncate" style={{ maxWidth: `${Math.floor(90 / labels.length)}%` }}>{label}</span>
                    ))}
                  </div>
                </div>
              </div>
            );
          };
          
          switch (type) {
            case 'bar': return <SimpleBarChart data={data} colors={colors} title={title} />;
            case 'pie': return <SimplePieChart data={data} colors={colors} title={title} />;
            case 'line':
            case 'area': return <SimpleLineChart data={data} color={color} title={title} />;
            default: return null;
          }
        };
        return null;
      })()}

      {(() => {
        // Make renderChart globally available
        const renderChart = window.renderChart;
        return null; 
      })()}
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-8 w-full">
        {[
          {
            label: 'Total Campaigns',
            value: stats.totalCampaigns,
            sub: 'All time campaigns',
            icon: Target,
            color: '#a78bfa',
            bgColor: 'rgba(167,139,250,0.2)',
            borderColor: 'rgba(167,139,250,0.2)',
            gradientFrom: 'rgba(167,139,250,0.2)',
            gradientTo: 'rgba(147,51,234,0.1)',
          },
          {
            label: 'Active Campaigns',
            value: stats.activeCampaigns,
            sub: 'Currently running',
            icon: TrendingUp,
            color: '#60a5fa',
            bgColor: 'rgba(96,165,250,0.2)',
            borderColor: 'rgba(96,165,250,0.2)',
            gradientFrom: 'rgba(96,165,250,0.2)',
            gradientTo: 'rgba(34,211,238,0.1)',
          },
          {
            label: 'Total Emails Sent',
            value: totalEmailsSent,
            sub: 'Across all sender accounts',
            icon: Send,
            color: '#34d399',
            bgColor: 'rgba(52,211,153,0.2)',
            borderColor: 'rgba(52,211,153,0.2)',
            gradientFrom: 'rgba(52,211,153,0.2)',
            gradientTo: 'rgba(16,185,129,0.1)',
          },
          {
            label: 'Unread Alerts',
            value: notificationUnreadCount,
            sub: 'Need your attention',
            icon: Bell,
            color: '#f87171',
            bgColor: 'rgba(248,113,113,0.2)',
            borderColor: 'rgba(248,113,113,0.2)',
            gradientFrom: 'rgba(248,113,113,0.2)',
            gradientTo: 'rgba(252,165,165,0.1)',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="relative group w-full min-w-0 rounded-xl backdrop-blur-sm p-5 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg"
            style={{
              border: `1px solid ${card.borderColor}`,
              background: `linear-gradient(135deg, ${card.gradientFrom} 0%, ${card.gradientTo} 100%)`,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                <card.icon className="h-5 w-5" style={{ color: card.color }} />
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-white/50 tracking-wide">{card.label}</p>
              <p className="text-3xl font-bold text-white tracking-tight">{card.value}</p>
              <p className="text-xs text-white/40">{card.sub}</p>
            </div>
          </div>
        ))}
      </div>
      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <div className="pb-1">
          <TabsList
            className="grid w-full grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
            style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
          >
            {[
              { value: 'dashboard', label: 'Dashboard', icon: BarChart3 },
              { value: 'campaigns', label: 'Campaigns', icon: Megaphone },
              { value: 'email', label: 'Email', icon: Mail },
              { value: 'qa', label: 'Q&A', icon: MessageSquare },
              { value: 'research', label: 'Research', icon: Sparkles },
              { value: 'documents', label: 'Documents', icon: FileText },
              { value: 'notifications', label: 'Notifications', icon: Bell, badge: notificationUnreadCount },
              { value: 'saved-graphs', label: 'Saved Graphs', icon: Sparkles },
            ].map((item) => (
              <TabsTrigger
                key={item.value}
                value={item.value}
                className="w-full min-w-0 px-2 sm:px-3 py-2 text-sm font-medium rounded-md border transition-all duration-150 relative flex items-center justify-center gap-2"
                style={activeTab === item.value
                  ? {
                      background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)',
                      color: '#fff',
                      border: '1.5px solid #a259ff',
                      boxShadow: '0 0 8px 0 #a259ff55',
                    }
                  : {
                      background: 'rgba(60, 30, 90, 0.22)',
                      color: '#cfc6e6',
                      border: '1.5px solid #2d2342',
                      boxShadow: 'none',
                    }
                }
              >
                <item.icon className="h-4 w-4" />
                <span className="truncate">{item.label}</span>
                {item.badge > 0 && (
                  <span
                    className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground"
                    title={`${item.badge} unread`}
                  >
                    {item.badge > 99 ? '99+' : item.badge}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="dashboard" className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : (
            <div className="space-y-4">
              <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
                <CardHeader>
                  <div className="flex flex-row items-center justify-between">
                    <CardTitle className="text-white">Marketing Overview</CardTitle>
                    {/* Main action buttons */}
                    <div className="flex flex-wrap gap-3">
                      <Button
                        size="sm"
                        className="gap-2"
                        onClick={() => setActiveTab('campaigns')}
                      >
                        <Plus className="h-5 w-5" />
                        Create campaign
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        onClick={() => setActiveTab('email')}
                      >
                        <Mail className="h-5 w-5" />
                        Email accounts
                      </Button>
                    </div>
                  </div>
                  <CardDescription className="text-white/60">
                    Your marketing campaigns and performance metrics
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Use the Campaigns tab to create and manage email campaigns. Use the Email tab to manage accounts and see sending stats.
                  </p>



                  {/* Campaigns list (like backend campaigns_list.html) */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Your Campaigns</h3>
                      {selectedCampaigns.size > 0 && (
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={dashboardDeleting}
                          onClick={() => setDashboardDeleteConfirmOpen(true)}
                        >
                          {dashboardDeleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                          Delete ({selectedCampaigns.size})
                        </Button>
                      )}
                    </div>
                    {campaignsLoading ? (
                      <div className="flex justify-center py-6">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      </div>
                    ) : campaigns.length === 0 ? (
                      <div className="border-muted-foreground/30 bg-muted/20 p-8 text-center">
                        <Megaphone className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                        <p className="text-sm text-muted-foreground mb-4">No campaigns yet.</p>
                        <Button size="lg" className="gap-2" onClick={() => setActiveTab('campaigns')}>
                          <Plus className="h-5 w-5" />
                          Create campaign
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div className=" overflow-hidden">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-muted/50 border-b">
                                <th className="p-3 w-10">
                                  <Checkbox
                                    checked={allDashSelectableChecked}
                                    onCheckedChange={toggleDashSelectAll}
                                    disabled={selectableDashCampaigns.length === 0}
                                  />
                                </th>
                                <th className="text-left font-semibold p-3">Campaign Name</th>
                                <th className="text-left font-semibold p-3">Status</th>
                                <th className="text-left font-semibold p-3">Type</th>
                                <th className="text-left font-semibold p-3">Created</th>
                                <th className="text-left font-semibold p-3">Scheduled</th>
                                <th className="text-left font-semibold p-3">End Date</th>
                                <th className="text-left font-semibold p-3">Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {campaigns.map((campaign) => {
                                const isActive = campaign.status === 'active';
                                return (
                                <tr key={campaign.id} className={`border-b last:border-0 hover:bg-muted/30 ${selectedCampaigns.has(campaign.id) ? 'bg-primary/5' : ''}`}>
                                  <td className="p-3 w-10">
                                    <Checkbox
                                      checked={selectedCampaigns.has(campaign.id)}
                                      onCheckedChange={() => toggleDashSelect(campaign.id)}
                                      disabled={isActive}
                                      title={isActive ? 'Active campaigns cannot be deleted' : undefined}
                                    />
                                  </td>
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
                                  <td className="p-3 text-muted-foreground">{campaign.end_date ? formatDate(campaign.end_date) : '—'}</td>
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
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {campaignsTotal > DASHBOARD_CAMPAIGNS_PAGE_SIZE && (
                          <div className="flex flex-wrap items-center justify-between gap-3 pt-4 mt-4 border-t">
                            <p className="text-sm text-muted-foreground">
                              Showing page {campaignsPage} of {Math.max(1, Math.ceil(campaignsTotal / DASHBOARD_CAMPAIGNS_PAGE_SIZE))} ({campaignsTotal} total campaigns)
                            </p>
                            <div className="flex items-center gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={campaignsPage <= 1 || campaignsLoading}
                                onClick={() => setCampaignsPage((p) => Math.max(1, p - 1))}
                              >
                                <ChevronLeft className="h-4 w-4" />
                                Previous
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={campaignsPage >= Math.ceil(campaignsTotal / DASHBOARD_CAMPAIGNS_PAGE_SIZE) || campaignsLoading}
                                onClick={() => setCampaignsPage((p) => p + 1)}
                              >
                                Next
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  {/* Dashboard Graphs: saved AI graph prompts pinned to dashboard */}
                  {dashboardGraphPrompts.length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Dashboard Graphs</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {dashboardGraphPrompts.map((p) => (
                          <Card
                            key={p.id}
                            className="cursor-pointer hover:bg-muted/50 transition-colors"
                            onClick={() => {
                              setActiveTab('saved-graphs');
                              handleViewGraph(p);
                            }}
                          >
                            <CardContent className="p-3 flex items-center gap-3">
                              <div className="rounded-lg bg-primary/10 p-2">
                                <BarChartIcon className="h-5 w-5 text-primary" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="font-medium text-sm truncate">{p.title}</p>
                                <p className="text-xs text-muted-foreground truncate">{p.prompt}</p>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <div className="relative flex gap-4">
            <Card className={`border-white/10 bg-black/20 backdrop-blur-sm ${selectedAccount ? 'flex-1 min-w-0' : 'w-full'}`}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle className="text-white">Email accounts</CardTitle>
                  <CardDescription className="text-white/60">
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
              <div className="w-[380px] shrink-0 flex flex-col rounded-lg border border-white/10 bg-black/20 backdrop-blur-sm shadow-sm overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b border-white/10 bg-white/[0.03]">
                  <h3 className="font-semibold text-base text-white">Account details</h3>
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
                  </div>
                  {/* IMAP / inbox sync — drives the Reply Draft Agent. */}
                  <div className="pt-3 border-t space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Inbox sync (IMAP)</p>
                      {selectedAccount.enable_imap_sync ? (
                        selectedAccount.imap_ready ? (
                          <Badge className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            Syncing
                          </Badge>
                        ) : (
                          <Badge variant="destructive" className="gap-1">
                            <AlertCircle className="h-3 w-3" />
                            Enabled but incomplete
                          </Badge>
                        )
                      ) : (
                        <Badge variant="secondary">Disabled</Badge>
                      )}
                    </div>
                    {selectedAccount.enable_imap_sync && !selectedAccount.imap_ready && (
                      <p className="text-xs text-destructive">
                        IMAP sync is on, but host / username / password aren't all filled in — this account won't actually sync. Click <span className="font-medium">Edit</span> to complete it.
                      </p>
                    )}
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Host</span>
                        <span className="font-mono text-foreground/90 truncate ml-2" title={selectedAccount.imap_host || '—'}>
                          {selectedAccount.imap_host || '—'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Port</span>
                        <span className="font-mono text-foreground/90">
                          {selectedAccount.imap_port || '—'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Username</span>
                        <span className="font-mono text-foreground/90 truncate ml-2" title={selectedAccount.imap_username || '—'}>
                          {selectedAccount.imap_username || '—'}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">SSL</span>
                        <span className="font-mono text-foreground/90">
                          {selectedAccount.imap_use_ssl ? 'Yes' : 'No'}
                        </span>
                      </div>
                    </div>
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

        <TabsContent value="campaigns" className="!mt-2 min-h-[400px]">
          <Campaigns onRefresh={fetchStats} />
        </TabsContent>

        <TabsContent value="qa" className="!mt-2 h-[500px] overflow-y-auto min-h-[630px] scrollbar-black">
          <MarketingQA />
        </TabsContent>

        <TabsContent value="research" className="!mt-2 h-[500px] overflow-y-auto min-h-[630px] scrollbar-black">
          <MarketResearch />
        </TabsContent>

        <TabsContent value="documents">
          <Documents />
        </TabsContent>

        <TabsContent value="notifications">
          <Notifications onUnreadCountChange={fetchNotificationUnreadCount} />
        </TabsContent>

        <TabsContent value="saved-graphs" className="!mt-2">
          <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-amber-500" />
                Saved Graph Prompts
              </CardTitle>
              <CardDescription className="text-white/60">
                Manage your saved graph prompts. Click View to preview saved chart data without regenerating.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {savedGraphsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : savedGraphPrompts.length === 0 ? (
                <div className="text-center py-12">
                  <Sparkles className="h-12 w-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                  <p className="text-muted-foreground">No saved graphs yet</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Go to the Q&A tab and save your graph prompts
                  </p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {savedGraphPrompts.map((prompt) => {
                      const chartType = prompt.chart_type?.toLowerCase() || 'bar';
                      const ChartIcon = chartType === 'pie' ? PieChart
                        : chartType === 'line' ? LineChart
                        : chartType === 'area' ? AreaChart
                        : BarChart3;
                      const chartColor = chartType === 'pie' ? 'text-pink-400'
                        : chartType === 'line' ? 'text-cyan-400'
                        : chartType === 'area' ? 'text-emerald-400'
                        : 'text-violet-400';
                      const isActive = viewingGraphId === prompt.id;
                      const isLoading = viewingGraphLoading && isActive;

                      return (
                        <Card
                          key={prompt.id}
                          className={`group flex flex-col transition-all duration-200 border-white/10 bg-white/[0.03] backdrop-blur-sm ${
                            isActive
                              ? 'ring-2 ring-primary/60 bg-primary/10 border-primary/30'
                              : 'hover:bg-white/[0.06] hover:border-white/20'
                          }`}
                        >
                          <CardHeader className="pb-2 pt-4 px-4">
                            <div className="flex items-start gap-3">
                              <div className={`shrink-0 p-2 rounded-lg bg-white/5 border border-white/10 ${chartColor}`}>
                                <ChartIcon className="h-4 w-4" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                <CardTitle className="text-sm font-semibold line-clamp-2 leading-snug">
                                  {prompt.title}
                                </CardTitle>
                                 <Button
                                size="sm"
                                variant="ghost"
                                className="h-8 w-8 p-0 text-white/30 hover:text-red-400 hover:bg-red-400/10 transition-colors shrink-0"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteGraphPrompt(prompt.id);
                                }}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                                </div>
                                <div className='flex items-center justify-between gap-2'>
                                <span className={`inline-flex items-center gap-1 mt-1.5 text-[10px] font-medium uppercase tracking-wider ${chartColor}`}>
                                  <ChartIcon className="h-2.5 w-2.5" />
                                  {chartType} chart
                                </span>
                                 {prompt.tags && prompt.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2.5">
                                {prompt.tags.map((tag) => {
                                  const TAG_COLORS = [
                                    'bg-blue-500/15 text-blue-400 border-blue-500/25',
                                    'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
                                    'bg-purple-500/15 text-purple-400 border-purple-500/25',
                                    'bg-amber-500/15 text-amber-400 border-amber-500/25',
                                    'bg-rose-500/15 text-rose-400 border-rose-500/25',
                                    'bg-cyan-500/15 text-cyan-400 border-cyan-500/25',
                                    'bg-pink-500/15 text-pink-400 border-pink-500/25',
                                    'bg-indigo-500/15 text-indigo-400 border-indigo-500/25',
                                  ];
                                  const hash = [...tag].reduce((acc, c) => acc + c.charCodeAt(0), 0);
                                  const colorClass = TAG_COLORS[hash % TAG_COLORS.length];
                                  return (
                                    <Badge
                                      key={tag}
                                      variant="outline"
                                      className={`text-[10px] px-1.5 py-0 h-4 ${colorClass}`}
                                    >
                                      {tag}
                                    </Badge>
                                  );
                                })}
                              </div>
                            )}
                                </div>
                              </div>
                            </div>
                          </CardHeader>

                          <CardContent className="flex-1 px-4 pb-2">
                            <p className="text-xs text-white/50 line-clamp-2 leading-relaxed">
                              {prompt.prompt}
                            </p>
                           
                          </CardContent>

                          <div className="px-4 pb-3 pt-2 mt-auto">
                            <div className="flex items-center gap-2">
                              <Button
                                size="sm"
                                variant={isActive ? "default" : "secondary"}
                                className={`flex-1 text-xs h-8 font-medium transition-all ${
                                  isActive
                                    ? ''
                                    : 'bg-white/5 border-white/10 text-white/80 hover:bg-white/10 hover:text-white'
                                }`}
                                disabled={isLoading}
                                onClick={() => handleViewGraph(prompt)}
                              >
                                {isLoading ? (
                                  <>
                                    <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                                    Generating...
                                  </>
                                ) : (
                                  <>
                                    <Eye className="h-3 w-3 mr-1.5" />
                                    {isActive ? 'Viewing' : 'View Chart'}
                                  </>
                                )}
                              </Button>
                             
                            </div>
                          </div>
                        </Card>
                      );
                    })}
                  </div>

                  {/* Pagination */}
                  {savedGraphsTotalPages > 1 && (
                    <div className="flex items-center justify-between pt-2">
                      <p className="text-xs text-white/50">
                        Page {savedGraphsPage} of {savedGraphsTotalPages} ({savedGraphsTotal} total)
                      </p>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={savedGraphsPage <= 1 || savedGraphsLoading}
                          onClick={() => fetchSavedGraphPrompts(savedGraphsPage - 1)}
                        >
                          <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={savedGraphsPage >= savedGraphsTotalPages || savedGraphsLoading}
                          onClick={() => fetchSavedGraphPrompts(savedGraphsPage + 1)}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Loading state while generating graph */}
                  {viewingGraphLoading && (
                    <Card className="border-primary/20 bg-primary/5 backdrop-blur-sm">
                      <CardContent className="flex flex-col items-center justify-center py-16">
                        <div className="relative">
                          <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
                          <Loader2 className="h-8 w-8 animate-spin text-primary relative" />
                        </div>
                        <p className="text-sm text-white/60 mt-4">Generating graph from saved prompt...</p>
                      </CardContent>
                    </Card>
                  )}

                  {/* Show saved graph preview */}
                  {!viewingGraphLoading && viewingGraphResult && (
                    <Card className="border-primary/20 bg-gradient-to-b from-primary/5 to-transparent backdrop-blur-sm">
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
                              <BarChart3 className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                              <CardTitle className="text-base">
                                {viewingGraphResult.title || 'Saved Graph'}
                              </CardTitle>
                              {viewingGraphResult.insights && viewingGraphResult.insights.length > 0 && (
                                <CardDescription className="mt-1 text-white/50">
                                  {Array.isArray(viewingGraphResult.insights)
                                    ? viewingGraphResult.insights.join(' • ')
                                    : viewingGraphResult.insights
                                  }
                                </CardDescription>
                              )}
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-white/40 hover:text-white hover:bg-white/10"
                            onClick={() => {
                              setViewingGraphId(null);
                              setViewingGraphResult(null);
                            }}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <div className="bg-black/20 rounded-xl p-6 border border-white/5">
                          {viewingGraphResult.chart ? (
                            <div className="w-full overflow-hidden">
                              {viewingGraphResult.chart.type === 'pie' && (
                                <div className="flex justify-center">
                                  {renderChart(viewingGraphResult.chart)}
                                </div>
                              )}
                              {['bar', 'line', 'area'].includes(viewingGraphResult.chart.type) && (
                                <div className="w-full pb-6">
                                  {renderChart(viewingGraphResult.chart)}
                                </div>
                              )}
                              {!['pie', 'bar', 'line', 'area'].includes(viewingGraphResult.chart.type) && (
                                <div className="text-center text-white/40 py-4">
                                  Chart type '{viewingGraphResult.chart.type}' not supported
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-center text-white/40 py-8">Failed to generate chart. Please try again.</div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>

      {/* Bulk Delete Confirmation Dialog */}
      <Dialog open={dashboardDeleteConfirmOpen} onOpenChange={setDashboardDeleteConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete {selectedCampaigns.size} Campaign{selectedCampaigns.size > 1 ? 's' : ''}</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the selected campaign{selectedCampaigns.size > 1 ? 's' : ''}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDashboardDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDashBulkDelete}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MarketingDashboard;

