/**
 * HRDashboard — main HR Support Agent dashboard.
 *
 * Visual language ported from `pages/ProjectManagerDashboardPage.jsx`:
 *   * Outer wrapper: `rounded-2xl` gradient panel.
 *   * Stat cards: `rounded-xl` gradient + colored icon tile.
 *   * Tabs: violet pill-style with active gradient + mobile hamburger fallback.
 *   * Section cards: `border-white/10 bg-black/20 backdrop-blur-sm`.
 *   * List rows: `border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06]`.
 *   * Empty states: centered icon tile + sub-line.
 */
import React, { useState, useEffect } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Loader2, LayoutDashboard, MessageSquare, Users, FileText, GitBranch,
  CalendarClock, Plus, Upload, Menu, Check, UserCheck, Clock, AlertTriangle,
  PlaneTakeoff, ClipboardList, MoreHorizontal, Trash2, FileSearch, ListChecks,
  Play, Power, Pencil, History,
} from 'lucide-react';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import hrAgentService from '@/services/hrAgentService';
import HRKnowledgeQAAgent from './HRKnowledgeQAAgent';
import HRMeetingScheduler from './HRMeetingScheduler';
import HRNotificationsTab from './HRNotificationsTab';
import HRLeaveTab from './HRLeaveTab';
import HREmployeeDetailDrawer from './HREmployeeDetailDrawer';

// ---------- Tab metadata ----------
const HR_TAB_ITEMS = [
  { value: 'overview', label: 'Overview', icon: LayoutDashboard },
  { value: 'qa', label: 'Knowledge Q&A', icon: MessageSquare },
  { value: 'employees', label: 'Employees', icon: Users },
  { value: 'documents', label: 'Documents', icon: FileText },
  { value: 'workflows', label: 'Workflows', icon: GitBranch },
  { value: 'meetings', label: 'Meetings', icon: CalendarClock },
  { value: 'leave', label: 'Leave', icon: ClipboardList },
  { value: 'notifications', label: 'Notifications', icon: AlertTriangle },
];

// ---------- Stat card colour tokens (mirror PM dashboard) ----------
const STAT_PALETTE = {
  violet: { color: '#a78bfa', bg: 'rgba(167,139,250,0.2)', border: 'rgba(167,139,250,0.2)', from: 'rgba(167,139,250,0.2)', to: 'rgba(147,51,234,0.1)' },
  emerald:{ color: '#34d399', bg: 'rgba(52,211,153,0.2)',  border: 'rgba(52,211,153,0.2)',  from: 'rgba(52,211,153,0.2)',  to: 'rgba(22,163,74,0.1)' },
  amber:  { color: '#fbbf24', bg: 'rgba(251,191,36,0.2)',  border: 'rgba(251,191,36,0.2)',  from: 'rgba(251,191,36,0.15)', to: 'rgba(245,158,11,0.08)' },
  sky:    { color: '#60a5fa', bg: 'rgba(96,165,250,0.2)',  border: 'rgba(96,165,250,0.2)',  from: 'rgba(96,165,250,0.2)',  to: 'rgba(34,211,238,0.1)' },
  rose:   { color: '#fb7185', bg: 'rgba(251,113,133,0.2)', border: 'rgba(251,113,133,0.2)', from: 'rgba(251,113,133,0.18)', to: 'rgba(225,29,72,0.08)' },
  pink:   { color: '#f472b6', bg: 'rgba(244,114,182,0.2)', border: 'rgba(244,114,182,0.2)', from: 'rgba(244,114,182,0.18)', to: 'rgba(219,39,119,0.08)' },
};


const HRDashboard = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('overview');

  // Overview
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Employees
  const [employees, setEmployees] = useState([]);
  const [empLoading, setEmpLoading] = useState(false);
  const [empSearch, setEmpSearch] = useState('');

  // Documents
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const [uploadDocType, setUploadDocType] = useState('policy');
  const [uploadConfidentiality, setUploadConfidentiality] = useState('employee');
  const [uploading, setUploading] = useState(false);

  // Employee detail drawer
  const [employeeDrawer, setEmployeeDrawer] = useState({ open: false, id: null });

  // Document action dialogs (summary / extract / delete confirm)
  const [docResult, setDocResult] = useState({
    open: false, type: null, title: '', loading: false, content: null, error: null,
  });
  const [docDelete, setDocDelete] = useState({ open: false, doc: null, loading: false });

  // Workflows
  const [workflows, setWorkflows] = useState([]);
  const [wfLoading, setWfLoading] = useState(false);
  const [wfDialog, setWfDialog] = useState({ open: false, mode: 'create', wf: null });
  const [wfDelete, setWfDelete] = useState({ open: false, wf: null, loading: false });
  const [wfHistory, setWfHistory] = useState({ open: false, wf: null, loading: false, rows: [] });
  const [wfBusyId, setWfBusyId] = useState(null);

  // ---------- Loaders ----------
  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const res = await hrAgentService.getHRDashboard();
      setStats(res?.data || null);
    } catch (e) {
      toast({ title: 'Failed to load HR overview', description: e.message, variant: 'destructive' });
    } finally {
      setStatsLoading(false);
    }
  };

  const loadEmployees = async () => {
    setEmpLoading(true);
    try {
      const res = await hrAgentService.listHREmployees({ q: empSearch });
      setEmployees(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load employees', description: e.message, variant: 'destructive' });
    } finally {
      setEmpLoading(false);
    }
  };

  const loadDocuments = async () => {
    setDocsLoading(true);
    try {
      const res = await hrAgentService.listHRDocuments();
      setDocuments(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load documents', description: e.message, variant: 'destructive' });
    } finally {
      setDocsLoading(false);
    }
  };

  const loadWorkflows = async () => {
    setWfLoading(true);
    try {
      const res = await hrAgentService.listHRWorkflows();
      setWorkflows(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load workflows', description: e.message, variant: 'destructive' });
    } finally {
      setWfLoading(false);
    }
  };

  useEffect(() => { loadStats(); }, []);
  useEffect(() => {
    if (activeTab === 'employees') loadEmployees();
    if (activeTab === 'documents') loadDocuments();
    if (activeTab === 'workflows') loadWorkflows();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // ---------- Handlers ----------
  const handleUpload = async () => {
    if (!uploadFile) {
      toast({ title: 'Pick a file first', variant: 'destructive' });
      return;
    }
    setUploading(true);
    try {
      const res = await hrAgentService.uploadHRDocument(uploadFile, uploadTitle, uploadDescription, {
        document_type: uploadDocType,
        confidentiality: uploadConfidentiality,
      });
      const status = res?.data?.processing_status;
      const mode = res?.data?.dispatch_mode;
      toast({
        title: 'Document uploaded',
        description: mode === 'inline'
          ? `Processed inline. Status: ${status}.`
          : 'Processing in the background — refresh to see status.',
      });
      setUploadOpen(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadDescription('');
      loadDocuments();
    } catch (e) {
      toast({ title: 'Upload failed', description: e.message, variant: 'destructive' });
    } finally {
      setUploading(false);
    }
  };

  // ---------- Document actions ----------
  const handleSummarizeDoc = async (d) => {
    setDocResult({ open: true, type: 'summary', title: `Summary: ${d.title}`,
                   loading: true, content: null, error: null });
    try {
      const res = await hrAgentService.summarizeHRDocument(d.id, {});
      const summary = res?.data?.summary || '(empty summary)';
      setDocResult((s) => ({ ...s, loading: false, content: summary }));
    } catch (e) {
      setDocResult((s) => ({ ...s, loading: false, error: e.message || 'Summarize failed' }));
    }
  };

  const handleExtractDoc = async (d) => {
    setDocResult({ open: true, type: 'extract', title: `Extracted fields: ${d.title}`,
                   loading: true, content: null, error: null });
    try {
      const res = await hrAgentService.extractHRDocument(d.id, {});
      const data = res?.data?.extracted ?? {};
      const pretty = typeof data === 'object' ? JSON.stringify(data, null, 2) : String(data);
      setDocResult((s) => ({ ...s, loading: false, content: pretty }));
    } catch (e) {
      setDocResult((s) => ({ ...s, loading: false, error: e.message || 'Extract failed' }));
    }
  };

  const handleDeleteDoc = async () => {
    const d = docDelete.doc;
    if (!d) return;
    setDocDelete((s) => ({ ...s, loading: true }));
    try {
      await hrAgentService.deleteHRDocument(d.id);
      setDocuments((arr) => arr.filter((x) => x.id !== d.id));
      toast({ title: 'Document deleted' });
      setDocDelete({ open: false, doc: null, loading: false });
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
      setDocDelete((s) => ({ ...s, loading: false }));
    }
  };

  // ---------- Workflow actions ----------
  const openCreateWorkflow = () => setWfDialog({
    open: true, mode: 'create',
    wf: {
      name: '', description: '',
      trigger_event: 'employee_hired', trigger_filters: {},
      steps_text: JSON.stringify([
        { type: 'send_email', template_name: 'welcome_email', recipient: '{{employee_email}}' },
        { type: 'wait', seconds: 0 },
      ], null, 2),
      is_active: true, requires_approval: false, timeout_seconds: 0,
    },
  });

  const openEditWorkflow = (w) => setWfDialog({
    open: true, mode: 'edit',
    wf: {
      id: w.id, name: w.name, description: w.description || '',
      trigger_event: w.trigger_conditions?.on || '',
      trigger_filters: { ...w.trigger_conditions, on: undefined },
      steps_text: JSON.stringify(w.steps || [], null, 2),
      is_active: !!w.is_active, requires_approval: !!w.requires_approval,
      timeout_seconds: w.timeout_seconds || 0,
    },
  });

  const handleSaveWorkflow = async () => {
    const wf = wfDialog.wf;
    if (!wf?.name?.trim()) {
      toast({ title: 'Name required', variant: 'destructive' });
      return;
    }
    let steps;
    try {
      steps = JSON.parse(wf.steps_text || '[]');
      if (!Array.isArray(steps)) throw new Error('steps must be a JSON array');
    } catch (e) {
      toast({ title: 'Steps JSON invalid', description: e.message, variant: 'destructive' });
      return;
    }
    const trigger_conditions = {};
    if (wf.trigger_event) trigger_conditions.on = wf.trigger_event;
    Object.entries(wf.trigger_filters || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') trigger_conditions[k] = v;
    });
    const payload = {
      name: wf.name.trim(),
      description: wf.description || '',
      trigger_conditions,
      steps,
      is_active: !!wf.is_active,
      requires_approval: !!wf.requires_approval,
      timeout_seconds: Number(wf.timeout_seconds) || 0,
    };
    try {
      if (wfDialog.mode === 'create') {
        const res = await hrAgentService.createHRWorkflow(payload);
        toast({ title: 'Workflow created', description: res?.data?.name || '' });
      } else {
        await hrAgentService.updateHRWorkflow(wf.id, payload);
        toast({ title: 'Workflow saved' });
      }
      setWfDialog({ open: false, mode: 'create', wf: null });
      loadWorkflows();
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
  };

  const handleToggleActive = async (w) => {
    setWfBusyId(w.id);
    try {
      await hrAgentService.updateHRWorkflow(w.id, { is_active: !w.is_active });
      setWorkflows((arr) => arr.map((x) => (x.id === w.id ? { ...x, is_active: !w.is_active } : x)));
    } catch (e) {
      toast({ title: 'Toggle failed', description: e.message, variant: 'destructive' });
    } finally {
      setWfBusyId(null);
    }
  };

  const handleRunWorkflow = async (w) => {
    setWfBusyId(w.id);
    try {
      const res = await hrAgentService.executeHRWorkflow(w.id, {});
      const status = res?.data?.status || 'completed';
      const sc = res?.data?.result_data?.steps_completed;
      toast({
        title: `Workflow ${status}`,
        description: sc != null ? `${sc} step(s) completed` : undefined,
      });
    } catch (e) {
      toast({ title: 'Run failed', description: e.message, variant: 'destructive' });
    } finally {
      setWfBusyId(null);
    }
  };

  const handleDeleteWorkflow = async () => {
    const w = wfDelete.wf;
    if (!w) return;
    setWfDelete((s) => ({ ...s, loading: true }));
    try {
      await hrAgentService.deleteHRWorkflow(w.id);
      setWorkflows((arr) => arr.filter((x) => x.id !== w.id));
      toast({ title: 'Workflow deleted' });
      setWfDelete({ open: false, wf: null, loading: false });
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
      setWfDelete((s) => ({ ...s, loading: false }));
    }
  };

  const handleViewHistory = async (w) => {
    setWfHistory({ open: true, wf: w, loading: true, rows: [] });
    try {
      const res = await hrAgentService.listHRWorkflowExecutions(w.id);
      setWfHistory({ open: true, wf: w, loading: false, rows: res?.data || [] });
    } catch (e) {
      toast({ title: 'Failed to load history', description: e.message, variant: 'destructive' });
      setWfHistory({ open: true, wf: w, loading: false, rows: [] });
    }
  };

  // ---------- Stat-card model ----------
  const statCards = stats ? [
    {
      label: 'Active employees',
      value: stats.employees?.active ?? 0,
      sub: `${stats.employees?.total ?? 0} total`,
      icon: UserCheck,
      ...STAT_PALETTE.emerald,
    },
    {
      label: 'On leave',
      value: stats.employees?.on_leave ?? 0,
      sub: `${stats.employees?.on_probation ?? 0} on probation`,
      icon: PlaneTakeoff,
      ...STAT_PALETTE.amber,
    },
    {
      label: 'Pending leave requests',
      value: stats.leave_requests?.pending ?? 0,
      sub: 'Awaiting approval',
      icon: ClipboardList,
      ...STAT_PALETTE.violet,
    },
    {
      label: 'Upcoming meetings',
      value: stats.meetings_upcoming ?? 0,
      sub: 'Scheduled ahead',
      icon: CalendarClock,
      ...STAT_PALETTE.sky,
    },
    {
      label: 'Indexed documents',
      value: stats.documents?.indexed ?? 0,
      sub: `${stats.documents?.total ?? 0} uploaded · ${stats.documents?.failed ?? 0} failed`,
      icon: FileText,
      ...STAT_PALETTE.pink,
    },
    {
      label: 'Probation ending in 30d',
      value: stats.probation_ending_soon ?? 0,
      sub: 'Schedule a review',
      icon: AlertTriangle,
      ...STAT_PALETTE.rose,
    },
  ] : [];

  const currentTab = HR_TAB_ITEMS.find((t) => t.value === activeTab) || HR_TAB_ITEMS[0];
  const CurrentTabIcon = currentTab.icon;

  return (
    <div className="space-y-4">
      <div
        className="w-full rounded-2xl border border-white/[0.06] p-0"
        style={{ background: 'linear-gradient(90deg, #020308 0%, #020308 55%, rgba(10,37,64,0.68) 85%, rgba(14,39,71,0.52) 100%)' }}
      >
        <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">

          {/* Header */}
          <div className="flex items-center gap-3">
            <div className="rounded-xl p-2.5" style={{ backgroundColor: STAT_PALETTE.violet.bg }}>
              <Users className="h-5 w-5" style={{ color: STAT_PALETTE.violet.color }} />
            </div>
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight">HR Support Agent</h1>
              <p className="text-sm text-white/50">
                Knowledge Q&A · Documents · Workflows · Notifications · Meetings — for your employees
              </p>
            </div>
          </div>

          {/* Stat cards */}
          {statsLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-violet-400 mr-2" />
              <span className="text-sm text-white/50">Loading HR overview...</span>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3 w-full">
              {statCards.map((card) => {
                const Icon = card.icon;
                return (
                  <div
                    key={card.label}
                    className="relative group w-full min-w-0 rounded-lg backdrop-blur-sm p-3 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg"
                    style={{
                      border: `1px solid ${card.border}`,
                      background: `linear-gradient(135deg, ${card.from} 0%, ${card.to} 100%)`,
                    }}
                  >
                    <div className="flex items-start justify-between mb-1.5">
                      <div className="rounded-md p-1.5" style={{ backgroundColor: card.bg }}>
                        <Icon className="h-4 w-4" style={{ color: card.color }} />
                      </div>
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-[10px] font-medium text-white/50 tracking-wide uppercase truncate">{card.label}</p>
                      <p className="text-xl font-bold text-white tracking-tight leading-none">{card.value}</p>
                      {card.sub && <p className="text-[10px] text-white/40 truncate" title={card.sub}>{card.sub}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            {/* Mobile: Hamburger menu (below lg) */}
            <div className="lg:hidden w-full mb-4">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="w-full justify-between h-11 border-[#3a295a] bg-[#1a1333] text-white/80 hover:bg-[#231845] hover:text-white">
                    <div className="flex items-center gap-2 min-w-0">
                      <CurrentTabIcon className="h-4 w-4 shrink-0 text-violet-400" />
                      <span className="font-medium truncate">{currentTab.label}</span>
                    </div>
                    <Menu className="h-5 w-5 text-white/40 shrink-0" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)] max-w-sm max-h-[60vh] overflow-y-auto border-[#3a295a] bg-[#161630]">
                  {HR_TAB_ITEMS.map((item) => {
                    const isActive = item.value === activeTab;
                    const ItemIcon = item.icon;
                    return (
                      <DropdownMenuItem
                        key={item.value}
                        onClick={() => setActiveTab(item.value)}
                        className={`flex items-center justify-between py-3 cursor-pointer ${isActive ? 'bg-violet-600/20' : 'hover:bg-white/5'}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <ItemIcon className={`h-4 w-4 shrink-0 ${isActive ? 'text-violet-400' : 'text-white/40'}`} />
                          <span className={isActive ? 'font-medium text-violet-300' : 'text-white/70'}>{item.label}</span>
                        </div>
                        {isActive && <Check className="h-4 w-4 text-violet-400 shrink-0" />}
                      </DropdownMenuItem>
                    );
                  })}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Desktop: Pill tabs (lg and above) */}
            <div className="hidden lg:block overflow-x-auto pb-1">
              <TabsList
                className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]"
                style={{ boxShadow: '0 2px 12px 0 #a259ff0a' }}
              >
                {HR_TAB_ITEMS.map((item) => {
                  const TabIcon = item.icon;
                  return (
                    <TabsTrigger
                      key={item.value}
                      value={item.value}
                      className="whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
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
                      <TabIcon className="h-4 w-4 mr-2" />
                      {item.label}
                    </TabsTrigger>
                  );
                })}
              </TabsList>
            </div>

            {/* OVERVIEW — agent quick-links */}
            <TabsContent value="overview" className="mt-6">
              <ErrorBoundary>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5 w-full min-w-0">
                  <AgentTile
                    icon={MessageSquare} accent={STAT_PALETTE.violet}
                    title="Knowledge Q&A"
                    desc="Ask the assistant about company policy, leave, benefits — answers cite the source doc."
                    onClick={() => setActiveTab('qa')}
                  />
                  <AgentTile
                    icon={Users} accent={STAT_PALETTE.emerald}
                    title="Employees"
                    desc="Browse your company's employees — auto-synced from auth.User via UserProfile."
                    onClick={() => setActiveTab('employees')}
                  />
                  <AgentTile
                    icon={FileText} accent={STAT_PALETTE.pink}
                    title="Documents"
                    desc="Handbook, policies, contracts, payroll. Confidentiality-gated retrieval."
                    onClick={() => setActiveTab('documents')}
                  />
                  <AgentTile
                    icon={GitBranch} accent={STAT_PALETTE.amber}
                    title="Workflows / SOPs"
                    desc="Onboarding, offboarding, leave approvals — runs on lifecycle events."
                    onClick={() => setActiveTab('workflows')}
                  />
                  <AgentTile
                    icon={CalendarClock} accent={STAT_PALETTE.sky}
                    title="Meetings"
                    desc="Schedule HR meetings in plain English. 1:1s, reviews, exits, training."
                    onClick={() => setActiveTab('meetings')}
                  />
                </div>
              </ErrorBoundary>
            </TabsContent>

            {/* KNOWLEDGE Q&A */}
            <TabsContent value="qa" className="mt-6">
              <ErrorBoundary><HRKnowledgeQAAgent /></ErrorBoundary>
            </TabsContent>

            {/* EMPLOYEES */}
            <TabsContent value="employees" className="mt-6">
              <ErrorBoundary>
                <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
                  <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Users className="h-5 w-5 text-violet-400" /> Employees
                      </CardTitle>
                      <CardDescription>Auto-synced from your company's auth.User accounts.</CardDescription>
                    </div>
                    <div className="flex gap-2">
                      <Input
                        placeholder="Search by name or email"
                        value={empSearch}
                        onChange={(e) => setEmpSearch(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') loadEmployees(); }}
                        className="w-64 bg-white/[0.03] border-white/[0.08]"
                      />
                      <Button variant="outline" onClick={loadEmployees}>Search</Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {empLoading ? (
                      <Spinner />
                    ) : employees.length === 0 ? (
                      <EmptyState icon={Users} title="No employees yet"
                        sub="When new auth.Users are added under your company, they'll appear here automatically." />
                    ) : (
                      <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
                        <div className="overflow-x-auto">
                          <Table>
                            <TableHeader>
                              <TableRow className="border-white/[0.06] hover:bg-transparent">
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Employee</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Email</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Title</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Department</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Status</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Type</TableHead>
                                <TableHead className="text-white/60 uppercase text-[10px] tracking-wider">Start date</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {employees.map((e) => {
                                const statusBadgeClass = {
                                  active: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
                                  on_leave: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
                                  probation: 'bg-sky-500/10 text-sky-300 border-sky-400/30',
                                  notice: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
                                  offboarded: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
                                  candidate: 'bg-violet-500/10 text-violet-300 border-violet-400/30',
                                  onboarding: 'bg-violet-500/10 text-violet-300 border-violet-400/30',
                                }[e.employment_status] || 'bg-white/[0.04] text-white/70';
                                return (
                                  <TableRow
                                    key={e.id}
                                    className="border-white/[0.06] hover:bg-white/[0.04] transition-colors cursor-pointer"
                                    onClick={() => setEmployeeDrawer({ open: true, id: e.id })}
                                  >
                                    <TableCell className="font-medium text-white/95">
                                      <div className="flex items-center gap-2.5 min-w-0">
                                        <div className="h-7 w-7 rounded-full flex items-center justify-center shrink-0"
                                             style={{ backgroundColor: STAT_PALETTE.violet.bg }}>
                                          <span className="text-[11px] font-semibold" style={{ color: STAT_PALETTE.violet.color }}>
                                            {(e.full_name || e.work_email || '?').slice(0, 1).toUpperCase()}
                                          </span>
                                        </div>
                                        <span className="truncate">{e.full_name || e.username || '—'}</span>
                                      </div>
                                    </TableCell>
                                    <TableCell className="text-white/70 text-sm">{e.work_email || '—'}</TableCell>
                                    <TableCell className="text-white/70 text-sm">{e.job_title || '—'}</TableCell>
                                    <TableCell className="text-white/70 text-sm">{e.department || '—'}</TableCell>
                                    <TableCell>
                                      <Badge variant="outline" className={`text-[10px] ${statusBadgeClass}`}>
                                        {e.employment_status || 'active'}
                                      </Badge>
                                    </TableCell>
                                    <TableCell className="text-white/70 text-xs">
                                      {e.employment_type ? e.employment_type.replace(/_/g, ' ') : '—'}
                                    </TableCell>
                                    <TableCell className="text-white/60 text-xs">
                                      {e.start_date ? new Date(e.start_date).toLocaleDateString() : '—'}
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </ErrorBoundary>
            </TabsContent>

            {/* DOCUMENTS */}
            <TabsContent value="documents" className="mt-6">
              <ErrorBoundary>
                <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
                  <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-violet-400" /> HR Documents
                      </CardTitle>
                      <CardDescription>Handbook, policies, contracts, payroll. Confidentiality-gated.</CardDescription>
                    </div>
                    <Button onClick={() => setUploadOpen(true)}>
                      <Upload className="h-4 w-4 mr-1" /> Upload
                    </Button>
                  </CardHeader>
                  <CardContent>
                    {docsLoading ? (
                      <Spinner />
                    ) : documents.length === 0 ? (
                      <EmptyState icon={FileText} title="No documents uploaded yet"
                        sub="Click Upload to add your first HR document — handbook, policy, contract." />
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                        {documents.map((d) => {
                          const fmt = (d.file_format || 'other').toLowerCase();
                          const fmtPalette = { pdf: STAT_PALETTE.rose, docx: STAT_PALETTE.sky, doc: STAT_PALETTE.sky,
                                                txt: STAT_PALETTE.violet, md: STAT_PALETTE.emerald,
                                                html: STAT_PALETTE.amber }[fmt] || STAT_PALETTE.violet;
                          const psBadge = {
                            ready: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
                            processing: 'bg-sky-500/10 text-sky-300 border-sky-400/30',
                            pending: 'bg-slate-500/10 text-slate-300 border-slate-400/30',
                            failed: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
                          }[d.processing_status] || 'bg-white/[0.04] text-white/70';
                          return (
                            <div key={d.id}
                                 className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 transition-all hover:bg-white/[0.06] hover:border-violet-400/30 flex flex-col">
                              <div className="flex items-start gap-3">
                                <div className="h-10 w-10 rounded-lg shrink-0 flex items-center justify-center"
                                     style={{ backgroundColor: fmtPalette.bg }}>
                                  <FileText className="h-5 w-5" style={{ color: fmtPalette.color }} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="font-medium truncate text-white/95">{d.title}</div>
                                  <div className="text-xs text-white/50 truncate">
                                    {fmt.toUpperCase()}{d.document_type ? ` · ${d.document_type.replace(/_/g, ' ')}` : ''}
                                  </div>
                                </div>
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" title="Actions">
                                      <MoreHorizontal className="h-4 w-4 text-white/60" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end" className="border-[#3a295a] bg-[#161630]">
                                    <DropdownMenuItem onClick={() => handleSummarizeDoc(d)} className="text-white/80">
                                      <FileSearch className="h-4 w-4 mr-2 text-violet-400" /> Summarize
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => handleExtractDoc(d)} className="text-white/80">
                                      <ListChecks className="h-4 w-4 mr-2 text-emerald-400" /> Extract fields
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      onClick={() => setDocDelete({ open: true, doc: d, loading: false })}
                                      className="text-rose-400 focus:text-rose-300">
                                      <Trash2 className="h-4 w-4 mr-2" /> Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-1">
                                <Badge variant="outline" className={`text-[10px] ${psBadge}`}>
                                  {d.processing_status || 'pending'}
                                </Badge>
                                <Badge variant="outline" className="text-[10px]">{d.confidentiality}</Badge>
                                {d.chunks_total > 0 && (
                                  <Badge variant="outline" className="text-[10px] bg-white/[0.04]">
                                    {d.chunks_processed}/{d.chunks_total} chunks
                                  </Badge>
                                )}
                              </div>
                              {d.processing_error && (
                                <div className="mt-2 text-[11px] text-rose-300/80 line-clamp-2" title={d.processing_error}>
                                  {d.processing_error}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Upload dialog */}
                <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
                  <DialogContent className="max-w-md">
                    <DialogHeader>
                      <DialogTitle>Upload HR Document</DialogTitle>
                      <DialogDescription>
                        Pick a file, set its type and confidentiality. The agent indexes it for Knowledge Q&A.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor="hr-upload-file">File</Label>
                        <Input id="hr-upload-file" type="file"
                          accept=".pdf,.docx,.doc,.txt,.md,.html,.htm"
                          onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
                      </div>
                      <div>
                        <Label htmlFor="hr-upload-title">Title</Label>
                        <Input id="hr-upload-title" placeholder="Defaults to filename"
                          value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} />
                      </div>
                      <div>
                        <Label htmlFor="hr-upload-desc">Description</Label>
                        <Textarea id="hr-upload-desc" rows={2}
                          value={uploadDescription} onChange={(e) => setUploadDescription(e.target.value)} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label>Type</Label>
                          <Select value={uploadDocType} onValueChange={setUploadDocType}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="handbook">Employee Handbook</SelectItem>
                              <SelectItem value="policy">Policy</SelectItem>
                              <SelectItem value="procedure">Procedure / SOP</SelectItem>
                              <SelectItem value="offer_letter">Offer Letter</SelectItem>
                              <SelectItem value="contract">Contract</SelectItem>
                              <SelectItem value="payslip">Payslip</SelectItem>
                              <SelectItem value="payroll">Payroll / Comp</SelectItem>
                              <SelectItem value="performance_review">Performance Review</SelectItem>
                              <SelectItem value="leave_form">Leave Form</SelectItem>
                              <SelectItem value="training">Training</SelectItem>
                              <SelectItem value="benefits">Benefits</SelectItem>
                              <SelectItem value="compliance">Compliance</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label>Confidentiality</Label>
                          <Select value={uploadConfidentiality} onValueChange={setUploadConfidentiality}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="public">Public</SelectItem>
                              <SelectItem value="employee">All Employees</SelectItem>
                              <SelectItem value="manager">Managers + HR</SelectItem>
                              <SelectItem value="hr_only">HR Only</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setUploadOpen(false)} disabled={uploading}>Cancel</Button>
                      <Button onClick={handleUpload} disabled={uploading || !uploadFile}>
                        {uploading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Upload className="h-4 w-4 mr-1" />}
                        Upload
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>

                {/* Document action result dialog (summarize / extract) */}
                <Dialog open={docResult.open} onOpenChange={(open) => setDocResult((s) => ({ ...s, open }))}>
                  <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
                    <DialogHeader>
                      <DialogTitle>{docResult.title}</DialogTitle>
                      <DialogDescription>
                        {docResult.type === 'summary'
                          ? 'AI-generated summary, grounded in the document only.'
                          : 'Structured fields extracted by the LLM (offer-letter / contract style).'}
                      </DialogDescription>
                    </DialogHeader>
                    <div className="flex-1 overflow-auto rounded-lg border border-white/[0.08] bg-black/30 p-3 min-h-[140px]">
                      {docResult.loading ? (
                        <div className="flex items-center gap-2 text-white/50">
                          <Loader2 className="h-4 w-4 animate-spin" /> Working on it...
                        </div>
                      ) : docResult.error ? (
                        <div className="text-rose-300 text-sm">{docResult.error}</div>
                      ) : docResult.type === 'extract' ? (
                        <pre className="text-xs text-white/85 whitespace-pre-wrap break-words">{docResult.content}</pre>
                      ) : (
                        <div className="text-sm text-white/85 whitespace-pre-wrap break-words leading-relaxed">{docResult.content}</div>
                      )}
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setDocResult({ open: false, type: null, title: '', loading: false, content: null, error: null })}>Close</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>

                {/* Document delete-confirm dialog */}
                <Dialog open={docDelete.open} onOpenChange={(open) => setDocDelete((s) => ({ ...s, open }))}>
                  <DialogContent className="max-w-sm">
                    <DialogHeader>
                      <DialogTitle>Delete document?</DialogTitle>
                      <DialogDescription>
                        Permanently removes <strong>{docDelete.doc?.title}</strong> and its indexed chunks.
                        Knowledge Q&A will no longer cite this document.
                      </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setDocDelete({ open: false, doc: null, loading: false })} disabled={docDelete.loading}>Keep</Button>
                      <Button onClick={handleDeleteDoc} disabled={docDelete.loading}
                        className="bg-rose-600 hover:bg-rose-500">
                        {docDelete.loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
                        Delete
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </ErrorBoundary>
            </TabsContent>

            {/* WORKFLOWS */}
            <TabsContent value="workflows" className="mt-6">
              <ErrorBoundary>
                <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
                  <CardHeader className="flex flex-row items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <GitBranch className="h-5 w-5 text-violet-400" /> HR Workflows / SOPs
                      </CardTitle>
                      <CardDescription>Onboarding · offboarding · approvals · reminders. Triggers fire on lifecycle events.</CardDescription>
                    </div>
                    <Button onClick={openCreateWorkflow}>
                      <Plus className="h-4 w-4 mr-1" /> New workflow
                    </Button>
                  </CardHeader>
                  <CardContent>
                    {wfLoading ? (
                      <Spinner />
                    ) : workflows.length === 0 ? (
                      <EmptyState icon={GitBranch} title="No workflows yet"
                        sub="Create your first workflow — onboarding, offboarding, leave approval, or any custom SOP." />
                    ) : (
                      <div className="space-y-2">
                        {workflows.map((w) => {
                          const trig = w.trigger_conditions || {};
                          const trigEvent = trig.on || null;
                          const trigExtras = Object.entries(trig).filter(([k]) => k !== 'on');
                          const stepCount = (w.steps || []).length;
                          const busy = wfBusyId === w.id;
                          return (
                            <div key={w.id}
                                 className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 transition-all hover:bg-white/[0.06] hover:border-violet-400/30">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <div className="font-medium text-white/95 truncate">{w.name}</div>
                                    <Badge variant="outline" className={w.is_active
                                      ? 'text-[10px] bg-emerald-500/10 text-emerald-300 border-emerald-400/30'
                                      : 'text-[10px] bg-slate-500/10 text-slate-300 border-slate-400/30'}>
                                      {w.is_active ? 'Active' : 'Inactive'}
                                    </Badge>
                                    {w.requires_approval && (
                                      <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-300 border-amber-400/30">
                                        Requires approval
                                      </Badge>
                                    )}
                                  </div>
                                  {w.description && (
                                    <div className="text-xs text-white/60 mt-1">{w.description}</div>
                                  )}
                                  <div className="text-xs text-white/45 mt-2 flex flex-wrap items-center gap-2">
                                    {trigEvent ? (
                                      <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-300 border-violet-400/30">
                                        on: {trigEvent}
                                      </Badge>
                                    ) : (
                                      <span className="italic">Runs on demand only</span>
                                    )}
                                    {trigExtras.map(([k, v]) => (
                                      <Badge key={k} variant="outline" className="text-[10px]">
                                        {k}: {String(v)}
                                      </Badge>
                                    ))}
                                    <span className="text-white/40">· {stepCount} step{stepCount === 1 ? '' : 's'}</span>
                                    {w.timeout_seconds > 0 && (
                                      <span className="text-white/40">· timeout {w.timeout_seconds}s</span>
                                    )}
                                  </div>
                                </div>
                                <div className="flex flex-col gap-1 shrink-0">
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={() => handleRunWorkflow(w)} disabled={busy}>
                                    {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3 mr-1" />}
                                    <span className="ml-1">Run</span>
                                  </Button>
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={() => openEditWorkflow(w)}>
                                    <Pencil className="h-3 w-3 mr-1" /> Edit
                                  </Button>
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={() => handleToggleActive(w)} disabled={busy}>
                                    <Power className="h-3 w-3 mr-1" />
                                    {w.is_active ? 'Disable' : 'Enable'}
                                  </Button>
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={() => handleViewHistory(w)}>
                                    <History className="h-3 w-3 mr-1" /> Runs
                                  </Button>
                                  <Button variant="outline" size="sm" className="h-7 text-xs text-rose-400 hover:text-rose-300"
                                    onClick={() => setWfDelete({ open: true, wf: w, loading: false })}>
                                    <Trash2 className="h-3 w-3 mr-1" /> Delete
                                  </Button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Workflow create / edit dialog */}
                <Dialog open={wfDialog.open} onOpenChange={(open) => setWfDialog((s) => ({ ...s, open }))}>
                  <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
                    <DialogHeader>
                      <DialogTitle>{wfDialog.mode === 'create' ? 'New workflow' : 'Edit workflow'}</DialogTitle>
                      <DialogDescription>
                        Set the trigger event + the step list. Steps run top-down; supported types include
                        <code className="text-violet-300"> send_email</code>,
                        <code className="text-violet-300"> update_employee</code>,
                        <code className="text-violet-300"> update_leave_balance</code>,
                        <code className="text-violet-300"> schedule_meeting</code>,
                        <code className="text-violet-300"> provision_account</code>,
                        <code className="text-violet-300"> assign_training</code>,
                        <code className="text-violet-300"> notify_template</code>,
                        <code className="text-violet-300"> branch</code>,
                        <code className="text-violet-300"> wait</code>.
                      </DialogDescription>
                    </DialogHeader>
                    {wfDialog.wf && (
                      <div className="space-y-3 overflow-y-auto pr-1">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <Label>Name</Label>
                            <Input value={wfDialog.wf.name}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, name: e.target.value } }))}
                              placeholder="e.g. Standard onboarding" />
                          </div>
                          <div>
                            <Label>Trigger event</Label>
                            <Select
                              value={wfDialog.wf.trigger_event || ''}
                              onValueChange={(v) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, trigger_event: v === '__none__' ? '' : v } }))}>
                              <SelectTrigger><SelectValue placeholder="Pick an event" /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="__none__">(none — manual run only)</SelectItem>
                                <SelectItem value="employee_hired">employee_hired</SelectItem>
                                <SelectItem value="employee_leaving">employee_leaving</SelectItem>
                                <SelectItem value="employee_on_leave">employee_on_leave</SelectItem>
                                <SelectItem value="employee_on_probation">employee_on_probation</SelectItem>
                                <SelectItem value="leave_request_submitted">leave_request_submitted</SelectItem>
                                <SelectItem value="leave_request_approved">leave_request_approved</SelectItem>
                                <SelectItem value="leave_request_rejected">leave_request_rejected</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                        <div>
                          <Label>Description</Label>
                          <Textarea rows={2} value={wfDialog.wf.description || ''}
                            onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, description: e.target.value } }))}
                            placeholder="Optional — what this workflow does" />
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <Label>Filter: leave_type (optional)</Label>
                            <Input
                              value={wfDialog.wf.trigger_filters?.leave_type || ''}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: {
                                ...s.wf,
                                trigger_filters: { ...(s.wf.trigger_filters || {}), leave_type: e.target.value || undefined },
                              } }))}
                              placeholder="vacation / sick / parental / ..." />
                          </div>
                          <div>
                            <Label>Filter: department (optional)</Label>
                            <Input
                              value={wfDialog.wf.trigger_filters?.department || ''}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: {
                                ...s.wf,
                                trigger_filters: { ...(s.wf.trigger_filters || {}), department: e.target.value || undefined },
                              } }))}
                              placeholder="Engineering / Sales / ..." />
                          </div>
                        </div>
                        <div>
                          <Label>Steps (JSON array)</Label>
                          <Textarea rows={10} className="font-mono text-xs"
                            value={wfDialog.wf.steps_text}
                            onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, steps_text: e.target.value } }))} />
                        </div>
                        <div className="flex items-center gap-4 flex-wrap">
                          <label className="flex items-center gap-2 text-sm select-none">
                            <input type="checkbox" checked={!!wfDialog.wf.is_active}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, is_active: e.target.checked } }))}
                              className="h-4 w-4" />
                            <span>Active (auto-runs on event)</span>
                          </label>
                          <label className="flex items-center gap-2 text-sm select-none">
                            <input type="checkbox" checked={!!wfDialog.wf.requires_approval}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, requires_approval: e.target.checked } }))}
                              className="h-4 w-4" />
                            <span>Requires approval before running</span>
                          </label>
                          <div>
                            <Label className="mr-2">Timeout (s)</Label>
                            <Input type="number" min={0} className="w-28 inline-block"
                              value={wfDialog.wf.timeout_seconds}
                              onChange={(e) => setWfDialog((s) => ({ ...s, wf: { ...s.wf, timeout_seconds: Number(e.target.value) || 0 } }))} />
                          </div>
                        </div>
                      </div>
                    )}
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setWfDialog({ open: false, mode: 'create', wf: null })}>Cancel</Button>
                      <Button onClick={handleSaveWorkflow}>{wfDialog.mode === 'create' ? 'Create' : 'Save'}</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>

                {/* Workflow delete confirm */}
                <Dialog open={wfDelete.open} onOpenChange={(open) => setWfDelete((s) => ({ ...s, open }))}>
                  <DialogContent className="max-w-sm">
                    <DialogHeader>
                      <DialogTitle>Delete workflow?</DialogTitle>
                      <DialogDescription>
                        Removes <strong>{wfDelete.wf?.name}</strong> and stops all future auto-runs. Past
                        execution rows are kept for audit.
                      </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setWfDelete({ open: false, wf: null, loading: false })} disabled={wfDelete.loading}>Keep</Button>
                      <Button onClick={handleDeleteWorkflow} disabled={wfDelete.loading} className="bg-rose-600 hover:bg-rose-500">
                        {wfDelete.loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
                        Delete
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>

                {/* Workflow run history */}
                <Dialog open={wfHistory.open} onOpenChange={(open) => setWfHistory((s) => ({ ...s, open }))}>
                  <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
                    <DialogHeader>
                      <DialogTitle>Run history{wfHistory.wf ? ` — ${wfHistory.wf.name}` : ''}</DialogTitle>
                      <DialogDescription>Most recent 100 executions, newest first.</DialogDescription>
                    </DialogHeader>
                    <div className="flex-1 overflow-auto">
                      {wfHistory.loading ? (
                        <Spinner />
                      ) : wfHistory.rows.length === 0 ? (
                        <div className="text-center text-sm text-white/50 py-10">No executions yet.</div>
                      ) : (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="text-[10px] uppercase">Started</TableHead>
                              <TableHead className="text-[10px] uppercase">Status</TableHead>
                              <TableHead className="text-[10px] uppercase">Steps done</TableHead>
                              <TableHead className="text-[10px] uppercase">Completed</TableHead>
                              <TableHead className="text-[10px] uppercase">Error</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {wfHistory.rows.map((row) => (
                              <TableRow key={row.id} className="border-white/[0.06]">
                                <TableCell className="text-xs">{row.started_at ? new Date(row.started_at).toLocaleString() : '—'}</TableCell>
                                <TableCell>
                                  <Badge variant="outline" className={`text-[10px] ${
                                    {
                                      completed: 'bg-emerald-500/10 text-emerald-300 border-emerald-400/30',
                                      failed: 'bg-rose-500/10 text-rose-300 border-rose-400/30',
                                      paused: 'bg-amber-500/10 text-amber-300 border-amber-400/30',
                                      in_progress: 'bg-sky-500/10 text-sky-300 border-sky-400/30',
                                      awaiting_approval: 'bg-violet-500/10 text-violet-300 border-violet-400/30',
                                    }[row.status] || 'bg-white/[0.04] text-white/70'
                                  }`}>{row.status}</Badge>
                                </TableCell>
                                <TableCell className="text-xs">{row.steps_completed ?? '—'}</TableCell>
                                <TableCell className="text-xs">{row.completed_at ? new Date(row.completed_at).toLocaleString() : '—'}</TableCell>
                                <TableCell className="text-xs text-rose-300 max-w-[14rem] truncate" title={row.error_message || ''}>
                                  {row.error_message || ''}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      )}
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setWfHistory({ open: false, wf: null, loading: false, rows: [] })}>Close</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </ErrorBoundary>
            </TabsContent>

            {/* MEETINGS */}
            <TabsContent value="meetings" className="mt-6">
              <ErrorBoundary><HRMeetingScheduler /></ErrorBoundary>
            </TabsContent>

            {/* LEAVE */}
            <TabsContent value="leave" className="mt-6">
              <ErrorBoundary><HRLeaveTab /></ErrorBoundary>
            </TabsContent>

            {/* NOTIFICATIONS */}
            <TabsContent value="notifications" className="mt-6">
              <ErrorBoundary><HRNotificationsTab /></ErrorBoundary>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Employee detail drawer (outside Tabs so it overlays from any tab) */}
      <HREmployeeDetailDrawer
        open={employeeDrawer.open}
        employeeId={employeeDrawer.id}
        onOpenChange={(open) => setEmployeeDrawer((s) => ({ ...s, open }))}
      />
    </div>
  );
};


// ---------- Reusable little pieces ----------

const Spinner = () => (
  <div className="flex justify-center py-8">
    <Loader2 className="h-5 w-5 animate-spin text-white/40" />
  </div>
);

const EmptyState = ({ icon: Icon, title, sub }) => (
  <div className="flex flex-col items-center justify-center py-14 text-center">
    <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
      <Icon className="h-7 w-7 text-violet-400" />
    </div>
    <div className="font-medium text-white/90 mb-1">{title}</div>
    {sub && <div className="text-sm text-white/50 max-w-sm">{sub}</div>}
  </div>
);

const AgentTile = ({ icon: Icon, accent, title, desc, onClick }) => (
  <button
    onClick={onClick}
    className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer w-full min-w-0"
    onMouseEnter={(e) => (e.currentTarget.style.borderColor = accent.color)}
    onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
  >
    <div className="rounded-lg p-2.5" style={{ backgroundColor: accent.bg }}>
      <Icon className="h-5 w-5" style={{ color: accent.color }} />
    </div>
    <div className="space-y-1 w-full min-w-0">
      <h3 className="text-base font-semibold text-white/95">{title}</h3>
      <p className="text-sm text-white/50">{desc}</p>
    </div>
  </button>
);


export default HRDashboard;
