import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Loader2,
  ArrowLeft,
  Target,
  BarChart3,
  Mail,
  Eye,
  AlertCircle,
  MousePointer,
  MessageSquare,
  TrendingUp,
  Pencil,
  Trash2,
  Upload,
  Download,
  Rocket,
  Calendar,
  Zap,
  Pause,
  ListOrdered,
  FileText,
  Users,
} from 'lucide-react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import marketingAgentService from '@/services/marketingAgentService';
import SequenceManagementPage from './SequenceManagementPage';
import EmailSendingStatusPage from './EmailSendingStatusPage';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

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

const EMAIL_SEND_STATUS_LABELS = {
  pending: 'Pending',
  sent: 'Sent',
  delivered: 'Delivered',
  opened: 'Opened',
  clicked: 'Clicked',
  bounced: 'Bounced',
  failed: 'Failed',
  unsubscribed: 'Unsubscribed',
};

const LEAD_STATUS_LABELS = {
  new: 'New',
  contacted: 'Contacted',
  qualified: 'Qualified',
  converted: 'Converted',
  lost: 'Lost',
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

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
};

const getBackendBase = () => {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
  return apiUrl.replace(/\/api\/?$/, '');
};

const getBackendCampaignUrl = (campaignId) => `${getBackendBase()}/marketing/campaigns/${campaignId}/`;

const PERFORMANCE_CHART_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { position: 'top' },
    title: { display: false },
  },
  scales: {
    y: {
      type: 'linear',
      display: true,
      position: 'left',
      beginAtZero: true,
    },
  },
};

const PerformanceOverTimeChart = ({ chartData, height = 300 }) => {
  if (!chartData?.dates?.length) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed bg-muted/20 text-muted-foreground text-sm" style={{ height: `${height}px` }}>
        📊 Performance data will appear here once emails are sent and tracked.
      </div>
    );
  }

  const labels = chartData.dates;
  const sent = chartData.impressions || [];
  const opened = chartData.conversions || [];
  const clicked = chartData.clicks || [];
  const replied = chartData.replied || [];

  const data = {
    labels,
    datasets: [
      {
        label: 'Sent',
        data: sent,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.4,
        fill: true,
      },
      {
        label: 'Opened',
        data: opened,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        tension: 0.4,
        fill: true,
      },
      {
        label: 'Clicked',
        data: clicked,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        tension: 0.4,
        fill: true,
      },
      {
        label: 'Replied',
        data: replied,
        borderColor: '#ec4899',
        backgroundColor: 'rgba(236, 72, 153, 0.1)',
        tension: 0.4,
        fill: true,
      },
    ],
  };

  return (
    <div style={{ height: `${height}px`, position: 'relative' }}>
      <Line data={data} options={PERFORMANCE_CHART_OPTIONS} />
    </div>
  );
};

const CampaignDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [campaign, setCampaign] = useState(null);
  const [emailStats, setEmailStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [emailSends, setEmailSends] = useState([]);
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [uploadLeadsOpen, setUploadLeadsOpen] = useState(false);
  const [editLeadOpen, setEditLeadOpen] = useState(false);
  const [launchStart, setLaunchStart] = useState('');
  const [launchEnd, setLaunchEnd] = useState('');
  const [scheduleStart, setScheduleStart] = useState('');
  const [scheduleEnd, setScheduleEnd] = useState('');
  const [editForm, setEditForm] = useState({});
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [editingLead, setEditingLead] = useState(null);
  const [editLeadForm, setEditLeadForm] = useState({});

  const fetchDetail = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      const response = await marketingAgentService.getCampaign(id, { detail: 1 });
      if (response?.status === 'success' && response?.data) {
        const d = response.data;
        setCampaign(d.campaign ?? null);
        setEmailStats(d.email_stats || null);
        setAnalytics(d.analytics || null);
        setChartData(d.chart_data || null);
        setEmailSends(d.email_sends || []);
        setLeads(d.leads || []);
      } else {
        setCampaign(null);
        setEmailStats(null);
        setAnalytics(null);
        setChartData(null);
        setEmailSends([]);
        setLeads([]);
      }
    } catch {
      setCampaign(null);
      setEmailStats(null);
      setAnalytics(null);
      setChartData(null);
      setEmailSends([]);
      setLeads([]);
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const handleLaunch = async () => {
    if (!launchStart) {
      toast({ title: 'Validation', description: 'Start date is required', variant: 'destructive' });
      return;
    }
    setActionLoading('launch');
    try {
      await marketingAgentService.outreachCampaign('launch', {
        start_date: launchStart,
        end_date: launchEnd || undefined,
      }, id);
      toast({ title: 'Success', description: 'Campaign launched' });
      setLaunchOpen(false);
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Launch failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSchedule = async () => {
    if (!scheduleStart || !scheduleEnd) {
      toast({ title: 'Validation', description: 'Start and end dates required', variant: 'destructive' });
      return;
    }
    setActionLoading('schedule');
    try {
      await marketingAgentService.outreachCampaign('schedule', {
        start_date: scheduleStart,
        end_date: scheduleEnd,
      }, id);
      toast({ title: 'Success', description: 'Campaign scheduled' });
      setScheduleOpen(false);
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Schedule failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleOptimize = async () => {
    setActionLoading('optimize');
    try {
      await marketingAgentService.outreachCampaign('optimize', {}, id);
      toast({ title: 'Success', description: 'Optimization requested' });
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Optimize failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    if (!window.confirm('Are you sure you want to stop this campaign?')) return;
    setActionLoading('stop');
    try {
      await marketingAgentService.campaignStop(id);
      toast({ title: 'Success', description: 'Campaign stopped' });
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Stop failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this campaign? This cannot be undone.')) return;
    setActionLoading('delete');
    try {
      await marketingAgentService.campaignDelete(id);
      toast({ title: 'Success', description: 'Campaign deleted' });
      navigate('/marketing/dashboard');
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Delete failed', variant: 'destructive' });
      setActionLoading(null);
    }
  };

  const handleUpdateCampaign = async () => {
    setActionLoading('edit');
    try {
      await marketingAgentService.updateCampaign(id, editForm);
      toast({ title: 'Success', description: 'Campaign updated' });
      setEditOpen(false);
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Update failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleUploadLeads = async () => {
    if (!uploadFile) {
      setUploadMessage('Please select a file');
      return;
    }
    setUploadMessage('');
    setActionLoading('upload');
    try {
      await marketingAgentService.uploadCampaignLeads(id, uploadFile);
      toast({ title: 'Success', description: 'Leads uploaded' });
      setUploadLeadsOpen(false);
      setUploadFile(null);
      fetchDetail();
    } catch (e) {
      setUploadMessage(e.message || 'Upload failed');
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpdateLead = async () => {
    if (!editingLead) return;
    setActionLoading('editLead');
    try {
      await marketingAgentService.updateCampaignLead(id, editingLead.id, editLeadForm);
      toast({ title: 'Success', description: 'Lead updated' });
      setEditLeadOpen(false);
      setEditingLead(null);
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Update failed', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteLead = async (leadId, email) => {
    if (!window.confirm(`Remove "${email}" from this campaign?`)) return;
    try {
      await marketingAgentService.deleteCampaignLead(id, leadId);
      toast({ title: 'Success', description: 'Lead removed' });
      fetchDetail();
    } catch (e) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const handleExportLeads = () => {
    const url = marketingAgentService.getExportLeadsUrl(id);
    const token = localStorage.getItem('company_auth_token');
    fetch(url, { headers: token ? { Authorization: `Token ${token}` } : {} })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `campaign_${id}_leads.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
        toast({ title: 'Success', description: 'Export downloaded' });
      })
      .catch(() => toast({ title: 'Error', description: 'Export failed', variant: 'destructive' }));
  };

  const openEdit = () => {
    setEditForm({
      name: campaign?.name || '',
      description: campaign?.description || '',
      campaign_type: campaign?.campaign_type || 'email',
      status: campaign?.status || 'draft',
      target_leads: campaign?.target_leads ?? '',
      target_conversions: campaign?.target_conversions ?? '',
      age_range: campaign?.age_range || '',
      location: campaign?.location || '',
      industry: campaign?.industry || '',
      company_size: campaign?.company_size || '',
      interests: campaign?.interests || '',
      language: campaign?.language || '',
      start_date: campaign?.start_date ? campaign.start_date.slice(0, 10) : '',
      end_date: campaign?.end_date ? campaign.end_date.slice(0, 10) : '',
    });
    setEditOpen(true);
  };

  const openEditLead = (lead) => {
    setEditingLead(lead);
    setEditLeadForm({
      email: lead.email || '',
      first_name: lead.first_name || '',
      last_name: lead.last_name || '',
      phone: lead.phone || '',
      company: lead.company || '',
      job_title: lead.job_title || '',
      status: lead.status || 'new',
      source: lead.source || '',
      notes: lead.notes || '',
    });
    setEditLeadOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-muted-foreground mb-4">Campaign not found.</p>
          <Button asChild variant="outline">
            <Link to="/marketing/dashboard">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Dashboard
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const isDraftOrPaused = campaign.status === 'draft' || campaign.status === 'paused';
  const isScheduled = campaign.status === 'scheduled';
  const isActive = campaign.status === 'active';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="icon">
            <Link to="/marketing/dashboard">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{campaign.name}</h1>
            <p className="text-sm text-muted-foreground">Created {formatDate(campaign.created_at)}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          
          {(isDraftOrPaused || isScheduled) && (
            <Button
              size="sm"
              onClick={() => {
                setLaunchStart(campaign.start_date ? campaign.start_date.slice(0, 10) : new Date().toISOString().slice(0, 10));
                setLaunchEnd(campaign.end_date ? campaign.end_date.slice(0, 10) : '');
                setLaunchOpen(true);
              }}
              disabled={!!actionLoading}
            >
              <Rocket className="mr-2 h-4 w-4" />
              Launch
            </Button>
          )}
          {(isDraftOrPaused || isScheduled) && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setScheduleStart(campaign.start_date ? campaign.start_date.slice(0, 10) : new Date().toISOString().slice(0, 10));
                setScheduleEnd(campaign.end_date ? campaign.end_date.slice(0, 10) : '');
                setScheduleOpen(true);
              }}
              disabled={!!actionLoading}
            >
              <Calendar className="mr-2 h-4 w-4" />
              Schedule
            </Button>
          )}
          {(isScheduled || isActive) && (
            <Button size="sm" variant="outline" onClick={handleOptimize} disabled={!!actionLoading}>
              <Zap className="mr-2 h-4 w-4" />
              Optimize
            </Button>
          )}
          {isActive && (
            <Button size="sm" variant="outline" onClick={handleStop} disabled={!!actionLoading}>
              <Pause className="mr-2 h-4 w-4" />
              Stop
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={openEdit} disabled={!!actionLoading}>
            <Pencil className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <Button size="sm" variant="destructive" onClick={handleDelete} disabled={!!actionLoading}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Tabs: Overview, Analytics, Email sequences, Email sending activity, Campaign leads */}
      <Tabs defaultValue="overview" className="space-y-4 flex flex-col">
        <TabsList className="flex flex-wrap gap-1 w-full h-auto justify-evenly">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="analytics" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Analytics & dashboard
          </TabsTrigger>
          <TabsTrigger value="sequences" className="flex items-center gap-2">
            <ListOrdered className="h-4 w-4" />
            Email sequences
          </TabsTrigger>
          <TabsTrigger value="email-activity" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Email sending activity
          </TabsTrigger>
          <TabsTrigger value="leads" className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Campaign leads
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Campaign information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <Badge variant="secondary" className={STATUS_BADGE_CLASS[campaign.status] || 'bg-gray-100 text-gray-800'}>
                    {STATUS_LABELS[campaign.status] || campaign.status}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Type</span>
                  <span>{campaign.campaign_type || '—'}</span>
                </div>
                {campaign.start_date && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Start date</span>
                    <span>{formatDate(campaign.start_date)}</span>
                  </div>
                )}
                {campaign.end_date && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">End date</span>
                    <span>{formatDate(campaign.end_date)}</span>
                  </div>
                )}
                 {campaign.language && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Language</span>
                        <span>{campaign.language}</span>
                      </div>
                    )}
                {campaign.description && (
                  <div className="pt-2 border-t">
                    <span className="text-muted-foreground block mb-1">Description</span>
                    <p className="text-muted-foreground">{campaign.description}</p>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Goals & target audience</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {(campaign.target_leads != null || campaign.target_conversions != null) && (
                  <>
                    {campaign.target_leads != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Target leads</span>
                        <span>{campaign.target_leads}</span>
                      </div>
                    )}
                    {campaign.target_conversions != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Target conversions</span>
                        <span>{campaign.target_conversions}</span>
                      </div>
                    )}
                  </>
                )}
                {(campaign.leads_count != null || campaign.sequences_count != null) && (
                  <div className="pt-2 border-t space-y-1">
                    {campaign.leads_count != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Leads</span>
                        <span>{campaign.leads_count}</span>
                      </div>
                    )}
                    {campaign.sequences_count != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Email sequences</span>
                        <span>{campaign.sequences_count}</span>
                      </div>
                    )}
                  </div>
                )}
                {(campaign.age_range || campaign.location || campaign.industry || campaign.company_size || campaign.language) && (
                  <div className="pt-2 border-t space-y-1">
                    {campaign.age_range && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Age range</span>
                        <span>{campaign.age_range}</span>
                      </div>
                    )}
                    {campaign.location && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Location</span>
                        <span>{campaign.location}</span>
                      </div>
                    )}
                    {campaign.industry && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Industry</span>
                        <span>{campaign.industry}</span>
                      </div>
                    )}
                    {campaign.company_size && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Company size</span>
                        <span>{campaign.company_size}</span>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          {emailStats && analytics ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Analytics & dashboard
                </CardTitle>
                <CardDescription>Campaign performance and engagement</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
                  <div className="rounded-lg border p-4 text-center">
                    <Mail className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{emailStats.total_sent ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Emails sent</div>
                  </div>
                  <div className="rounded-lg border p-4 text-center">
                    <Eye className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{emailStats.total_opened ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Open rate: {analytics.open_rate_percent ?? 0}%</div>
                  </div>
                  <div className="rounded-lg border p-4 text-center">
                    <MousePointer className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{emailStats.total_clicked ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Click rate: {analytics.click_rate_percent ?? 0}%</div>
                  </div>
                  <div className="rounded-lg border p-4 text-center">
                    <MessageSquare className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{emailStats.total_replied ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Reply rate: {analytics.reply_rate ?? 0}%</div>
                  </div>
                  <div className="rounded-lg border p-4 text-center">
                    <TrendingUp className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{analytics.engagement ?? 0}%</div>
                    <div className="text-xs text-muted-foreground">Engagement</div>
                  </div>
                  <div className="rounded-lg border p-4 text-center">
                    <AlertCircle className="h-6 w-6 mx-auto mb-1 text-muted-foreground" />
                    <div className="text-2xl font-bold">{emailStats.total_failed ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Failed Emails</div>
                  </div>
                </div>
                {(analytics.target_leads || analytics.target_conversions) && (
                  <div className="space-y-6">
                    <h4 className="text-base font-semibold text-foreground">Progress Towards Targets</h4>
                    <div className="grid gap-6">
                      {analytics.target_conversions != null && (
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <span className="font-semibold text-muted-foreground">Conversions Target</span>
                            <span className="font-semibold text-foreground">
                              {emailStats.total_clicked ?? 0} / {analytics.target_conversions}
                            </span>
                          </div>
                          <div className="w-full h-4 bg-muted rounded-lg overflow-hidden">
                            <div
                              className="h-full rounded-lg bg-gradient-to-r from-emerald-500 to-emerald-600 transition-all"
                              style={{ width: `${Math.min(analytics.conversion_progress ?? 0, 100)}%` }}
                            />
                          </div>
                          <div className="text-right mt-1.5 text-sm text-muted-foreground font-medium">
                            {(analytics.conversion_progress ?? 0).toFixed(1)}% Complete
                          </div>
                        </div>
                      )}
                      {analytics.target_leads != null && (
                        <div className="bg-muted/40 rounded-xl p-5 border border-border">
                          <div className="flex flex-wrap items-center gap-6 mb-3">
                            <span className="font-semibold text-muted-foreground">Leads Target:</span>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">Uploaded:</span>
                              <span className="font-bold text-foreground">{emailStats.total_leads ?? 0}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">Clicked:</span>
                              <span className="font-bold text-blue-600">{emailStats.total_clicked ?? 0}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">Positive Replies:</span>
                              <span className="font-bold text-emerald-600">{emailStats.positive_replies ?? 0}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">Target:</span>
                              <span className="font-bold text-amber-600">{analytics.target_leads}</span>
                            </div>
                          </div>
                          <div className="w-full h-[18px] bg-muted rounded-full overflow-hidden mb-2">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all"
                              style={{ width: `${Math.min(analytics.leads_progress ?? 0, 100)}%` }}
                            />
                          </div>
                          <div className="text-right text-sm text-muted-foreground font-medium">
                            {(analytics.leads_progress ?? 0).toFixed(1)}% Complete
                            {(emailStats.total_replied ?? 0) > 0 && (
                              <span className="ml-4 pl-4 border-l border-border">
                                <span className="text-amber-800 dark:text-amber-200">Total Replies: <strong>{emailStats.total_replied ?? 0}</strong></span>
                                <span className="ml-3 text-emerald-600">Positive/Neutral: <strong>{emailStats.positive_replies ?? 0}</strong></span>
                                <span className="ml-3 text-red-600">Negative: <strong>{emailStats.negative_replies ?? 0}</strong></span>
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {chartData && (
                  <div>
                    <h4 className="text-sm font-semibold mb-2">📈 Performance Over Time (Last 30 Days)</h4>
                    <PerformanceOverTimeChart chartData={chartData} height={300} />
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                No analytics yet. Launch the campaign and send emails to see performance.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="sequences" className="space-y-4">
          <SequenceManagementPage embedded />
        </TabsContent>

        <TabsContent value="email-activity" className="space-y-4">
          <EmailSendingStatusPage embedded />
        </TabsContent>

        <TabsContent value="leads" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2">Campaign leads</CardTitle>
                  <CardDescription>Upload CSV/Excel or manage leads</CardDescription>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => { setUploadLeadsOpen(true); setUploadMessage(''); setUploadFile(null); }}>
                    <Upload className="mr-2 h-4 w-4" />
                    Upload leads
                  </Button>
                  {leads.length > 0 && (
                    <Button size="sm" variant="outline" onClick={handleExportLeads}>
                      <Download className="mr-2 h-4 w-4" />
                      Export CSV
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {leads.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">No leads yet. Upload a CSV/Excel file to get started.</p>
              ) : (
                <div className="rounded-md border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="text-left p-2 font-medium">Email</th>
                        <th className="text-left p-2 font-medium">Name</th>
                        <th className="text-left p-2 font-medium">Company</th>
                        <th className="text-left p-2 font-medium">Status</th>
                        <th className="text-right p-2 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leads.map((lead) => (
                        <tr key={lead.id} className="border-b last:border-0">
                          <td className="p-2">{lead.email}</td>
                          <td className="p-2">{[lead.first_name, lead.last_name].filter(Boolean).join(' ') || '—'}</td>
                          <td className="p-2">{lead.company || '—'}</td>
                          <td className="p-2">
                            <Badge variant="secondary" className="text-xs">
                              {LEAD_STATUS_LABELS[lead.status] || lead.status}
                            </Badge>
                          </td>
                          <td className="p-2 text-right">
                            <Button size="sm" variant="ghost" className="h-8" onClick={() => openEditLead(lead)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button size="sm" variant="ghost" className="h-8 text-destructive" onClick={() => handleDeleteLead(lead.id, lead.email)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {campaign.target_leads && (
                <p className="text-muted-foreground text-sm mt-2">
                  Total: <strong>{leads.length}</strong> lead{leads.length !== 1 ? 's' : ''} (Target: {campaign.target_leads})
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Launch modal */}
      <Dialog open={launchOpen} onOpenChange={setLaunchOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Launch campaign</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Start date *</Label>
              <Input
                type="date"
                value={launchStart}
                onChange={(e) => setLaunchStart(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label>End date (optional)</Label>
              <Input
                type="date"
                value={launchEnd}
                onChange={(e) => setLaunchEnd(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLaunchOpen(false)}>Cancel</Button>
            <Button onClick={handleLaunch} disabled={actionLoading === 'launch'}>
              {actionLoading === 'launch' ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Launch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Schedule modal */}
      <Dialog open={scheduleOpen} onOpenChange={setScheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule campaign</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Start date *</Label>
              <Input type="date" value={scheduleStart} onChange={(e) => setScheduleStart(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label>End date *</Label>
              <Input type="date" value={scheduleEnd} onChange={(e) => setScheduleEnd(e.target.value)} className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScheduleOpen(false)}>Cancel</Button>
            <Button onClick={handleSchedule} disabled={actionLoading === 'schedule'}>
              {actionLoading === 'schedule' ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit campaign modal */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit campaign</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Name</Label>
              <Input value={editForm.name || ''} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <Label>Description</Label>
              <Input value={editForm.description || ''} onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))} className="mt-1" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Target leads</Label>
                <Input type="number" value={editForm.target_leads ?? ''} onChange={(e) => setEditForm((f) => ({ ...f, target_leads: e.target.value ? parseInt(e.target.value, 10) : '' }))} className="mt-1" />
              </div>
              <div>
                <Label>Target conversions</Label>
                <Input type="number" value={editForm.target_conversions ?? ''} onChange={(e) => setEditForm((f) => ({ ...f, target_conversions: e.target.value ? parseInt(e.target.value, 10) : '' }))} className="mt-1" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Start date</Label>
                <Input type="date" value={editForm.start_date || ''} onChange={(e) => setEditForm((f) => ({ ...f, start_date: e.target.value }))} className="mt-1" />
              </div>
              <div>
                <Label>End date</Label>
                <Input type="date" value={editForm.end_date || ''} onChange={(e) => setEditForm((f) => ({ ...f, end_date: e.target.value }))} className="mt-1" />
              </div>
            </div>
            <div>
              <Label>Location</Label>
              <Input value={editForm.location || ''} onChange={(e) => setEditForm((f) => ({ ...f, location: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <Label>Industry</Label>
              <Input value={editForm.industry || ''} onChange={(e) => setEditForm((f) => ({ ...f, industry: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <Label>Company size</Label>
              <Input value={editForm.company_size || ''} onChange={(e) => setEditForm((f) => ({ ...f, company_size: e.target.value }))} className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>Cancel</Button>
            <Button onClick={handleUpdateCampaign} disabled={actionLoading === 'edit'}>
              {actionLoading === 'edit' ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload leads modal */}
      <Dialog open={uploadLeadsOpen} onOpenChange={setUploadLeadsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload leads</DialogTitle>
            <CardDescription>CSV or Excel with Email column (required). Optional: First Name, Last Name, Phone, Company, Job Title, Source.</CardDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>File (CSV, XLSX, XLS)</Label>
              <Input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="mt-1"
              />
            </div>
            {uploadMessage && <p className="text-sm text-destructive">{uploadMessage}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadLeadsOpen(false)}>Cancel</Button>
            <Button onClick={handleUploadLeads} disabled={actionLoading === 'upload'}>
              {actionLoading === 'upload' ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit lead modal */}
      <Dialog open={editLeadOpen} onOpenChange={(open) => { if (!open) setEditingLead(null); setEditLeadOpen(open); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit lead</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 py-4">
            <div className="sm:col-span-2">
              <Label className="text-xs font-medium text-muted-foreground">Email</Label>
              <Input
                type="email"
                value={editLeadForm.email || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, email: e.target.value }))}
                className="mt-1.5"
                placeholder="lead@example.com"
              />
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">First name</Label>
              <Input
                value={editLeadForm.first_name || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, first_name: e.target.value }))}
                className="mt-1.5"
                placeholder="First name"
              />
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Last name</Label>
              <Input
                value={editLeadForm.last_name || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, last_name: e.target.value }))}
                className="mt-1.5"
                placeholder="Last name"
              />
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Phone</Label>
              <Input
                value={editLeadForm.phone || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, phone: e.target.value }))}
                className="mt-1.5"
                placeholder="Phone"
              />
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Status</Label>
              <select
                className="w-full mt-1.5 h-9 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                value={editLeadForm.status || 'new'}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, status: e.target.value }))}
              >
                {Object.entries(LEAD_STATUS_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Company</Label>
              <Input
                value={editLeadForm.company || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, company: e.target.value }))}
                className="mt-1.5"
                placeholder="Company"
              />
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Job title</Label>
              <Input
                value={editLeadForm.job_title || ''}
                onChange={(e) => setEditLeadForm((f) => ({ ...f, job_title: e.target.value }))}
                className="mt-1.5"
                placeholder="Job title"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setEditLeadOpen(false)}>Cancel</Button>
            <Button onClick={handleUpdateLead} disabled={actionLoading === 'editLead'}>
              {actionLoading === 'editLead' ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CampaignDetail;
