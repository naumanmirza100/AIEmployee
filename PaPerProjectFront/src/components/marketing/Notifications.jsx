import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, RefreshCw, Search, Trash2, CheckCheck, Inbox, History, BarChart3 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { cn } from '@/lib/utils';

/**
 * Proactive Notification sub-agent (PayPerProject backend).
 */
const NOTIFICATION_TYPE_LABELS = {
  performance_alert: 'Performance',
  opportunity: 'Opportunity',
  anomaly: 'Anomaly',
  milestone: 'Milestone',
  campaign_status: 'Status',
  email_delivery: 'Delivery',
  engagement: 'Engagement',
};

/** Notification types that represent issues (alerts/problems). */
const ISSUE_TYPES = ['performance_alert', 'anomaly', 'email_delivery', 'engagement', 'campaign_status'];

/** Only count high/critical priority as "issues" for the stats. */
const HIGH_PRIORITY = ['high', 'critical'];

const getNotificationStats = (notifications) => {
  const totalIssues = notifications.filter(
    (n) => ISSUE_TYPES.includes(n.notification_type) && HIGH_PRIORITY.includes(n.priority)
  ).length;
  const totalOpportunities = notifications.filter((n) => n.notification_type === 'opportunity').length;
  return { totalIssues, totalOpportunities };
};

const getPriorityVariant = (priority) => {
  if (priority === 'critical' || priority === 'high') return 'destructive';
  if (priority === 'medium') return 'default';
  return 'secondary';
};

const getPriorityBorderClass = (priority) => {
  if (priority === 'critical' || priority === 'high') return 'border-l-destructive';
  if (priority === 'medium') return 'border-l-primary';
  return 'border-l-muted-foreground/50';
};

const Notifications = ({ onUnreadCountChange }) => {
  const { toast } = useToast();
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState('');
  const [loadingCampaigns, setLoadingCampaigns] = useState(false);
  const [loading, setLoading] = useState(true);
  const [monitoring, setMonitoring] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [history, setHistory] = useState([]);
  const [monitorSummary, setMonitorSummary] = useState(null);
  const [error, setError] = useState(null);
  const [actioningId, setActioningId] = useState(null);

  const fetchCampaigns = useCallback(async () => {
    setLoadingCampaigns(true);
    try {
      const res = await marketingAgentService.listCampaigns();
      const list = Array.isArray(res?.data?.campaigns) ? res.data.campaigns : [];
      setCampaigns(list);
    } catch {
      setCampaigns([]);
    } finally {
      setLoadingCampaigns(false);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await marketingAgentService.getNotifications({ unread_only: true });
      if (response.status === 'success' && response.data) {
        const data = response.data;
        setNotifications(Array.isArray(data.notifications) ? data.notifications : []);
        setUnreadCount(typeof data.unread_count === 'number' ? data.unread_count : 0);
        onUnreadCountChange?.();
      } else {
        setNotifications([]);
        setUnreadCount(0);
        onUnreadCountChange?.();
      }
    } catch (err) {
      setError(err.message || 'Failed to load notifications');
      setNotifications([]);
      setUnreadCount(0);
      onUnreadCountChange?.();
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast, onUnreadCountChange]);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await marketingAgentService.getNotifications({ unread_only: false });
      if (response.status === 'success' && response.data && Array.isArray(response.data.notifications)) {
        const read = response.data.notifications.filter((n) => n.is_read);
        setHistory(read);
      } else {
        setHistory([]);
      }
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const runMonitor = async () => {
    setMonitoring(true);
    setMonitorSummary(null);
    setError(null);
    try {
      const cid = campaignId && campaignId !== '__none__' ? Number(campaignId) : null;
      const response = await marketingAgentService.monitorCampaigns(cid);
      if (response.status === 'success' && response.data) {
        setMonitorSummary(response.data);
        await fetchNotifications();
        await fetchHistory();
        onUnreadCountChange?.();
        toast({
          title: 'Monitoring complete',
          description: `Campaigns monitored: ${response.data.campaigns_monitored ?? 1}. New notifications: ${response.data.notifications_created ?? 0}.`,
        });
      } else {
        toast({ title: 'Error', description: response.message || 'Monitor failed', variant: 'destructive' });
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Monitor failed', variant: 'destructive' });
    } finally {
      setMonitoring(false);
    }
  };

  const handleMarkRead = async (id) => {
    setActioningId(id);
    try {
      const response = await marketingAgentService.markNotificationRead(id);
      if (response.status === 'success') {
        await fetchNotifications();
        await fetchHistory();
        onUnreadCountChange?.();
        toast({ title: 'Marked as read' });
      } else {
        toast({ title: 'Error', description: response.message, variant: 'destructive' });
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setActioningId(null);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this notification?')) return;
    setActioningId(id);
    try {
      const response = await marketingAgentService.deleteNotification(id);
      if (response.status === 'success') {
        await fetchNotifications();
        await fetchHistory();
        onUnreadCountChange?.();
        toast({ title: 'Notification deleted' });
      } else {
        toast({ title: 'Error', description: response.message, variant: 'destructive' });
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setActioningId(null);
    }
  };

  const refreshAll = () => {
    fetchNotifications();
    fetchHistory();
  };

  const renderNotification = (n, isHistory) => (
    <article
      key={n.id}
      className={cn(
        'group relative rounded-lg border border-l-4 bg-card p-4 transition-colors hover:bg-muted/30',
        getPriorityBorderClass(n.priority)
      )}
    >
      <div className="flex gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h5 className="font-medium text-foreground">{n.title}</h5>
            <Badge variant={getPriorityVariant(n.priority)} className="text-xs font-medium capitalize">
              {n.priority}
            </Badge>
            <Badge variant="outline" className="text-xs font-normal text-muted-foreground">
              {NOTIFICATION_TYPE_LABELS[n.notification_type] || n.notification_type}
            </Badge>
            {n.campaign_name && (
              <span className="text-xs text-muted-foreground">· {n.campaign_name}</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">{n.message}</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <time dateTime={n.created_at}>
              {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
            </time>
            {n.action_url && (
              <a
                href={n.action_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-primary hover:underline"
              >
                View campaign
              </a>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-start gap-1">
          {!n.is_read && !isHistory && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              disabled={actioningId === n.id}
              onClick={() => handleMarkRead(n.id)}
              title="Mark as read"
            >
              {actioningId === n.id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCheck className="h-4 w-4" />
              )}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            disabled={actioningId === n.id}
            onClick={() => handleDelete(n.id)}
            title="Delete"
          >
            {actioningId === n.id ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </article>
  );

  const EmptyState = ({ icon: Icon, title, description }) => (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 px-4 text-center">
      <div className="rounded-full bg-muted p-4">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 max-w-[280px] text-xs text-muted-foreground">{description}</p>
    </div>
  );

  const allNotifications = [...notifications, ...history];
  const { totalIssues, totalOpportunities } = getNotificationStats(allNotifications);
  const totalNotifications = allNotifications.length;
  const totalRead = history.length;
  const totalUnread = unreadCount;

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Notifications</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Monitor campaigns and manage alerts from the Proactive Notification Agent.
        </p>
      </div>

      {/* Stats: Total notifications, Total read, Total unread, Total issues, Total opportunities */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-lg border bg-card px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">Total notifications</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{totalNotifications}</p>
        </div>
        <div className="rounded-lg border bg-card px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">Total read</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{totalRead}</p>
        </div>
        <div className="rounded-lg border bg-card px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">Total unread</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{totalUnread}</p>
        </div>
        <div className="rounded-lg border bg-card px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">Total issues (high)</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{totalIssues}</p>
        </div>
        <div className="rounded-lg border bg-card px-4 py-3 shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">Total opportunities</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{totalOpportunities}</p>
        </div>
      </div>

      {/* Monitor section */}
      <Card className="border-0 bg-muted/30 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
              <BarChart3 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">Monitor campaigns</CardTitle>
              <CardDescription className="text-xs">
                Run a check on one campaign or all active campaigns.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="w-[80%] space-y-2">
              <Label htmlFor="monitor-campaign" className="text-xs font-medium text-muted-foreground">
                Campaign (optional)
              </Label>
              <Select value={campaignId || '__none__'} onValueChange={setCampaignId} disabled={loadingCampaigns}>
                <SelectTrigger id="monitor-campaign" className="h-9">
                  <SelectValue placeholder="All campaigns" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">All campaigns</SelectItem>
                  {campaigns.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name} · {c.status || '—'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={runMonitor} disabled={monitoring} size="default" className="h-9">
              {monitoring ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running…
                </>
              ) : (
                <>
                  <Search className="mr-2 h-4 w-4" />
                  Run monitor
                </>
              )}
            </Button>
          </div>
          {monitorSummary && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: 'Campaigns checked', value: monitorSummary.campaigns_monitored ?? 1 },
                { label: 'New notifications', value: monitorSummary.notifications_created ?? 0 },
                { label: 'Total issues', value: monitorSummary.issues_found ?? 0 },
                { label: 'Opportunities', value: monitorSummary.opportunities_found ?? 0 },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg border bg-background/80 px-3 py-2">
                  <p className="text-xs font-medium text-muted-foreground">{label}</p>
                  <p className="text-lg font-semibold tabular-nums text-foreground">{value}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Unread notifications */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Inbox className="h-4 w-4 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">Unread</CardTitle>
              <CardDescription className="text-xs">
                {unreadCount} notification{unreadCount !== 1 ? 's' : ''}
              </CardDescription>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={refreshAll}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : notifications.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No unread notifications"
              description="Run a monitor above to check for new alerts, or you’re all caught up."
            />
          ) : (
            <ul className="space-y-3">
              {notifications.map((n) => renderNotification(n, false))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* History */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
              <History className="h-4 w-4 text-muted-foreground" />
            </div>
            <div>
              <CardTitle className="text-base">History</CardTitle>
              <CardDescription className="text-xs">
                {history.length} read notification{history.length !== 1 ? 's' : ''}
              </CardDescription>
            </div>
          </div>
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={fetchHistory} disabled={loading}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <EmptyState
              icon={History}
              title="No history yet"
              description="Notifications you mark as read will appear here."
            />
          ) : (
            <ul className="space-y-3">
              {history.map((n) => renderNotification(n, true))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Notifications;
