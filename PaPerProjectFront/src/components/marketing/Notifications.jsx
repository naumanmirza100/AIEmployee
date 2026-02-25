import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import { 
  Loader2, 
  RefreshCw, 
  Search, 
  Trash2, 
  CheckCheck, 
  Inbox, 
  History, 
  BarChart3, 
  ChevronLeft, 
  ChevronRight,
  Bell,
  AlertCircle,
  TrendingUp,
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  Mail,
  Eye,
  EyeOff,
  Filter,
  MoreVertical,
  Archive,
  Star,
  BellRing
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

/** Backend may send /marketing/campaigns/{id}/ (old) or /marketing/dashboard/campaign/{id} (new). Normalize to in-app path. */
const normalizeCampaignActionUrl = (actionUrl) => {
  if (!actionUrl || typeof actionUrl !== 'string') return null;
  const u = actionUrl.replace(/\/+$/, '').trim();
  if (u.startsWith('/marketing/dashboard/campaign/')) return u;
  const match = u.match(/^\/marketing\/campaigns\/(\d+)(?:\/(.*))?$/);
  if (!match) return null;
  const [, id, sub] = match;
  const base = `/marketing/dashboard/campaign/${id}`;
  if (sub === 'sequences') return `${base}/sequences`;
  return base;
};

/**
 * Proactive Notification sub-agent (PayPerProject backend).
 */
const NOTIFICATION_TYPE_CONFIG = {
  performance_alert: {
    label: 'Performance',
    icon: AlertCircle,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-l-amber-500'
  },
  opportunity: {
    label: 'Opportunity',
    icon: TrendingUp,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-l-emerald-500'
  },
  anomaly: {
    label: 'Anomaly',
    icon: Zap,
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-l-purple-500'
  },
  milestone: {
    label: 'Milestone',
    icon: Star,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-l-blue-500'
  },
  campaign_status: {
    label: 'Status',
    icon: Clock,
    color: 'text-slate-500',
    bgColor: 'bg-slate-500/10',
    borderColor: 'border-l-slate-500'
  },
  email_delivery: {
    label: 'Delivery',
    icon: Mail,
    color: 'text-indigo-500',
    bgColor: 'bg-indigo-500/10',
    borderColor: 'border-l-indigo-500'
  },
  engagement: {
    label: 'Engagement',
    icon: Bell,
    color: 'text-rose-500',
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-l-rose-500'
  },
};

/** Notification types that represent issues (alerts/problems). */
const ISSUE_TYPES = ['performance_alert', 'anomaly', 'email_delivery', 'engagement', 'campaign_status'];

/** Only count high/critical priority as "issues" for the stats. */
const HIGH_PRIORITY = ['high', 'critical'];

const NOTIFICATIONS_PAGE_SIZE = 10;

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  }
};

const statCardVariants = {
  hidden: { scale: 0.9, opacity: 0 },
  visible: {
    scale: 1,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 15
    }
  }
};

const pulseVariants = {
  pulse: {
    scale: [1, 1.02, 1],
    transition: {
      duration: 2,
      repeat: Infinity,
      ease: "easeInOut"
    }
  }
};

/** Reusable pagination bar: previous / page info / next */
const PaginationBar = ({ page, totalItems, pageSize, loading, onPageChange }) => {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const from = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, totalItems);
  
  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 mt-4"
    >
      <p className="text-sm text-muted-foreground">
        {totalItems === 0 ? 'No items' : `Showing ${from}–${to} of ${totalItems}`}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1 || loading}
          onClick={() => onPageChange((p) => Math.max(1, p - 1))}
          className="gap-1 transition-all hover:scale-105"
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </Button>
        <span className="text-sm text-muted-foreground min-w-[100px] text-center">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages || loading}
          onClick={() => onPageChange((p) => p + 1)}
          className="gap-1 transition-all hover:scale-105"
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </motion.div>
  );
};

/** Treat as connection/backend unreachable – don't show error toast or banner; show blank/empty state instead. */
const isConnectionError = (err) => {
  const msg = (err?.message || err?.data?.message || String(err || '')).toLowerCase();
  return (
    msg.includes('connect') ||
    msg.includes('network') ||
    msg.includes('backend') ||
    msg.includes('running') ||
    msg.includes('cors') ||
    msg.includes('failed to fetch') ||
    msg.includes('load failed')
  );
};

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

const getTimeAgo = (timestamp) => {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);
  
  if (diffInSeconds < 60) return 'just now';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
  return date.toLocaleDateString();
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
  const [unreadPage, setUnreadPage] = useState(1);
  const [unreadTotal, setUnreadTotal] = useState(0);
  const [history, setHistory] = useState([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [monitorSummary, setMonitorSummary] = useState(null);
  const [error, setError] = useState(null);
  const [actioningId, setActioningId] = useState(null);
  const [filterType, setFilterType] = useState('all');
  const [showFilters, setShowFilters] = useState(false);

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

  const fetchNotifications = useCallback(async (page = 1) => {
    setError(null);
    setLoading(true);
    try {
      const response = await marketingAgentService.getNotifications({
        unread_only: true,
        page,
        page_size: NOTIFICATIONS_PAGE_SIZE,
      });
      if (response.status === 'success' && response.data) {
        const data = response.data;
        setNotifications(Array.isArray(data.notifications) ? data.notifications : []);
        setUnreadTotal(typeof data.total === 'number' ? data.total : 0);
        setUnreadCount(typeof data.unread_count === 'number' ? data.unread_count : 0);
        onUnreadCountChange?.();
      } else {
        setNotifications([]);
        setUnreadTotal(0);
        setUnreadCount(0);
        onUnreadCountChange?.();
      }
    } catch (err) {
      setNotifications([]);
      setUnreadTotal(0);
      setUnreadCount(0);
      onUnreadCountChange?.();
      if (!isConnectionError(err)) {
        setError(err.message || 'Failed to load notifications');
        toast({ title: 'Error', description: err.message, variant: 'destructive' });
      } else {
        setError(null);
      }
    } finally {
      setLoading(false);
    }
  }, [toast, onUnreadCountChange]);

  const fetchHistory = useCallback(async (page = 1) => {
    setHistoryLoading(true);
    try {
      const response = await marketingAgentService.getNotifications({
        read_only: true,
        page,
        page_size: NOTIFICATIONS_PAGE_SIZE,
      });
      if (response.status === 'success' && response.data && Array.isArray(response.data.notifications)) {
        setHistory(response.data.notifications);
        setHistoryTotal(typeof response.data.total === 'number' ? response.data.total : 0);
      } else {
        setHistory([]);
        setHistoryTotal(0);
      }
    } catch {
      setHistory([]);
      setHistoryTotal(0);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  useEffect(() => {
    fetchNotifications(unreadPage);
  }, [unreadPage]);

  useEffect(() => {
    fetchHistory(historyPage);
  }, [historyPage]);

  const runMonitor = async () => {
    setMonitoring(true);
    setMonitorSummary(null);
    setError(null);
    try {
      const cid = campaignId && campaignId !== '__none__' ? Number(campaignId) : null;
      const response = await marketingAgentService.monitorCampaigns(cid);
      if (response.status === 'success' && response.data) {
        setMonitorSummary(response.data);
        await fetchNotifications(unreadPage);
        await fetchHistory(historyPage);
        onUnreadCountChange?.();
        toast({
          title: '✨ Monitoring complete',
          description: `Campaigns monitored: ${response.data.campaigns_monitored ?? 1}. New notifications: ${response.data.notifications_created ?? 0}.`,
        });
      } else {
        toast({ title: 'Error', description: response.message || 'Monitor failed', variant: 'destructive' });
      }
    } catch (err) {
      if (!isConnectionError(err)) {
        toast({ title: 'Error', description: err.message || 'Monitor failed', variant: 'destructive' });
      }
    } finally {
      setMonitoring(false);
    }
  };

  const handleMarkRead = async (id) => {
    setActioningId(id);
    try {
      const response = await marketingAgentService.markNotificationRead(id);
      if (response.status === 'success') {
        await fetchNotifications(unreadPage);
        await fetchHistory(historyPage);
        onUnreadCountChange?.();
        toast({ 
          title: 'Marked as read',
          description: 'Notification moved to history'
        });
      } else {
        toast({ title: 'Error', description: response.message, variant: 'destructive' });
      }
    } catch (err) {
      if (!isConnectionError(err)) {
        toast({ title: 'Error', description: err.message, variant: 'destructive' });
      }
    } finally {
      setActioningId(null);
    }
  };

  const handleMarkAllRead = async () => {
    const unreadIds = notifications.map(n => n.id);
    for (const id of unreadIds) {
      await handleMarkRead(id);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this notification?')) return;
    setActioningId(id);
    try {
      const response = await marketingAgentService.deleteNotification(id);
      if (response.status === 'success') {
        await fetchNotifications(unreadPage);
        await fetchHistory(historyPage);
        onUnreadCountChange?.();
        toast({ 
          title: 'Notification deleted',
          description: 'The notification has been removed'
        });
      } else {
        toast({ title: 'Error', description: response.message, variant: 'destructive' });
      }
    } catch (err) {
      if (!isConnectionError(err)) {
        toast({ title: 'Error', description: err.message, variant: 'destructive' });
      }
    } finally {
      setActioningId(null);
    }
  };

  const refreshAll = () => {
    fetchNotifications(unreadPage);
    fetchHistory(historyPage);
  };

  const filteredNotifications = notifications.filter(n => {
    if (filterType === 'all') return true;
    if (filterType === 'issues') return ISSUE_TYPES.includes(n.notification_type);
    if (filterType === 'opportunities') return n.notification_type === 'opportunity';
    return true;
  });

  const renderNotification = (n, isHistory) => {
    const typeConfig = NOTIFICATION_TYPE_CONFIG[n.notification_type] || {
      label: n.notification_type,
      icon: Bell,
      color: 'text-slate-500',
      bgColor: 'bg-slate-500/10',
      borderColor: 'border-l-slate-500'
    };
    const Icon = typeConfig.icon;
    const timeAgo = getTimeAgo(n.created_at);

    return (
      <motion.article
        key={n.id}
        layout
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: -20 }}
        whileHover={{ scale: 1.01, transition: { duration: 0.2 } }}
        className={cn(
          'group relative overflow-hidden rounded-xl border bg-card p-4 transition-all',
          'hover:shadow-lg hover:shadow-primary/5',
          'border-l-4',
          typeConfig.borderColor,
          !n.is_read && !isHistory && 'bg-gradient-to-r from-primary/5 via-transparent to-transparent'
        )}
      >
        {/* Animated background for unread notifications */}
        {!n.is_read && !isHistory && (
          <motion.div
            className="absolute inset-0 bg-gradient-to-r from-primary/10 via-transparent to-transparent"
            animate={{
              x: ['0%', '100%', '0%'],
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: "linear"
            }}
            style={{ pointerEvents: 'none' }}
          />
        )}

        <div className="flex gap-4 relative z-10">
          {/* Icon */}
          <motion.div 
            whileHover={{ scale: 1.1, rotate: 5 }}
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
              typeConfig.bgColor
            )}
          >
            <Icon className={cn('h-5 w-5', typeConfig.color)} />
          </motion.div>

          {/* Content */}
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h5 className="font-semibold text-foreground">{n.title}</h5>
              <div className="flex flex-wrap gap-1.5">
                <Badge 
                  variant={getPriorityVariant(n.priority)} 
                  className="text-xs font-medium capitalize shadow-sm"
                >
                  {n.priority}
                </Badge>
                <Badge 
                  variant="outline" 
                  className={cn(
                    'text-xs font-normal border-0',
                    typeConfig.bgColor,
                    typeConfig.color
                  )}
                >
                  {typeConfig.label}
                </Badge>
              </div>
            </div>
            
            <p className="text-sm text-muted-foreground leading-relaxed">{n.message}</p>
            
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                {timeAgo}
              </span>
              
              {n.campaign_name && (
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <BarChart3 className="h-3.5 w-3.5" />
                  {n.campaign_name}
                </span>
              )}
              
              {n.action_url && (() => {
                const to = normalizeCampaignActionUrl(n.action_url);
                if (to) {
                  return (
                    <Link 
                      to={to} 
                      className="flex items-center gap-1.5 font-medium text-primary hover:underline group/link"
                    >
                      <Eye className="h-3.5 w-3.5 transition-transform group-hover/link:scale-110" />
                      View details
                    </Link>
                  );
                }
                return (
                  <a 
                    href={n.action_url} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="flex items-center gap-1.5 font-medium text-primary hover:underline group/link"
                  >
                    <Eye className="h-3.5 w-3.5 transition-transform group-hover/link:scale-110" />
                    View details
                  </a>
                );
              })()}
            </div>
          </div>

          {/* Actions */}
          <motion.div 
            className="flex shrink-0 items-start gap-1"
            initial={{ opacity: 0.5 }}
            whileHover={{ opacity: 1 }}
          >
            {!n.is_read && !isHistory && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"
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
              className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
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
          </motion.div>
        </div>
      </motion.article>
    );
  };

  const EmptyState = ({ icon: Icon, title, description, action }) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed py-16 px-4 text-center"
    >
      <motion.div 
        animate={pulseVariants.pulse}
        className="rounded-full bg-muted p-4"
      >
        <Icon className="h-8 w-8 text-muted-foreground" />
      </motion.div>
      <p className="mt-4 text-lg font-semibold text-foreground">{title}</p>
      <p className="mt-2 max-w-[280px] text-sm text-muted-foreground">{description}</p>
      {action && (
        <Button onClick={action} className="mt-6">
          {action}
        </Button>
      )}
    </motion.div>
  );

  const currentPageNotifications = [...notifications, ...history];
  const { totalIssues, totalOpportunities } = getNotificationStats(currentPageNotifications);
  const totalNotifications = unreadTotal + historyTotal;
  const totalRead = historyTotal;
  const totalUnread = unreadCount;

  const stats = [
    { 
      label: 'Total notifications', 
      value: totalNotifications, 
      icon: BellRing, 
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10'
    },
    { 
      label: 'Unread', 
      value: totalUnread, 
      icon: Bell, 
      color: 'text-amber-500',
      bgColor: 'bg-amber-500/10'
    },
    { 
      label: 'Read', 
      value: totalRead, 
      icon: CheckCircle2, 
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10'
    },
    { 
      label: 'Issues (high)', 
      value: totalIssues, 
      icon: AlertCircle, 
      color: 'text-rose-500',
      bgColor: 'bg-rose-500/10'
    },
    { 
      label: 'Opportunities', 
      value: totalOpportunities, 
      icon: TrendingUp, 
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10'
    },
  ];

  return (
    <motion.div 
      className="space-y-8"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Page header with animated gradient */}
      <motion.div variants={itemVariants}>
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary/10 via-primary/5 to-background p-8">
          <div className="relative z-10">
            <div className="flex items-center gap-3">
              <motion.div 
                whileHover={{ rotate: 15, scale: 1.1 }}
                className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/20"
              >
                <BellRing className="h-6 w-6 text-primary" />
              </motion.div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-foreground">Notifications</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Monitor campaigns and manage alerts from the Proactive Notification Agent
                </p>
              </div>
            </div>
          </div>
          <div className="absolute inset-0 bg-grid-white/5 [mask-image:radial-gradient(ellipse_at_center,white,transparent)]" />
        </div>
      </motion.div>

      {/* Stats with animations */}
      <motion.div 
        variants={itemVariants}
        className="grid grid-cols-2 gap-4 sm:grid-cols-5"
      >
        {stats.map((stat, index) => (
          <motion.div
            key={stat.label}
            variants={statCardVariants}
            whileHover={{ scale: 1.02, y: -2 }}
            className="group relative overflow-hidden rounded-xl border bg-card p-4 transition-all hover:shadow-lg"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="relative z-10">
              <div className={cn(
                'mb-2 inline-flex rounded-lg p-2',
                stat.bgColor
              )}>
                <stat.icon className={cn('h-4 w-4', stat.color)} />
              </div>
              <p className="text-xs font-medium text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold tabular-nums text-foreground">
                {stat.value}
              </p>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Monitor section with enhanced design */}
      <motion.div variants={itemVariants}>
        <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-muted/50 via-background to-background shadow-lg">
          <div className="absolute inset-0 bg-grid-white/5 [mask-image:radial-gradient(ellipse_at_center,white,transparent)]" />
          <CardHeader className="relative pb-3">
            <div className="flex items-center gap-3">
              <motion.div 
                whileHover={{ rotate: 360 }}
                transition={{ duration: 0.5 }}
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10"
              >
                <BarChart3 className="h-5 w-5 text-primary" />
              </motion.div>
              <div>
                <CardTitle className="text-lg">Monitor Campaigns</CardTitle>
                <CardDescription className="text-sm">
                  Run a health check on your campaigns to discover insights and opportunities
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="relative space-y-4">
            <div className="flex flex-wrap items-end gap-4">
              <div className="w-[80%] space-y-2">
                <Label htmlFor="monitor-campaign" className="text-sm font-medium">
                  Select Campaign
                </Label>
                <Select value={campaignId || '__none__'} onValueChange={setCampaignId} disabled={loadingCampaigns}>
                  <SelectTrigger id="monitor-campaign" className="h-10 bg-background/50 backdrop-blur-sm">
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
              <motion.div
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Button 
                  onClick={runMonitor} 
                  disabled={monitoring} 
                  size="lg" 
                  className="h-10 gap-2 bg-primary hover:bg-primary/90"
                >
                  {monitoring ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4" />
                      Run Analysis
                    </>
                  )}
                </Button>
              </motion.div>
            </div>
            
            <AnimatePresence>
              {monitorSummary && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 pt-4">
                    {[
                      { label: 'Campaigns checked', value: monitorSummary.campaigns_monitored ?? 1, icon: BarChart3, color: 'text-blue-500' },
                      { label: 'New notifications', value: monitorSummary.notifications_created ?? 0, icon: Bell, color: 'text-amber-500' },
                      { label: 'Issues found', value: monitorSummary.issues_found ?? 0, icon: AlertCircle, color: 'text-rose-500' },
                      { label: 'Opportunities', value: monitorSummary.opportunities_found ?? 0, icon: TrendingUp, color: 'text-emerald-500' },
                    ].map(({ label, value, icon: Icon, color }) => (
                      <motion.div
                        key={label}
                        initial={{ scale: 0.9, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: 0.1 }}
                        className="group relative overflow-hidden rounded-xl border bg-background/50 backdrop-blur-sm p-4"
                      >
                        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="flex items-center gap-3">
                          <div className={cn('rounded-lg p-2', color.replace('text', 'bg') + '/10')}>
                            <Icon className={cn('h-4 w-4', color)} />
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground">{label}</p>
                            <p className="text-xl font-bold text-foreground">{value}</p>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </CardContent>
        </Card>
      </motion.div>

      {/* Unread notifications with filters */}
      <motion.div variants={itemVariants}>
        <Card className="overflow-hidden border-0 shadow-lg">
          <CardHeader className="bg-gradient-to-r from-primary/5 via-transparent to-transparent pb-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <motion.div 
                  whileHover={{ scale: 1.1, rotate: 10 }}
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10"
                >
                  <Inbox className="h-5 w-5 text-primary" />
                </motion.div>
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    Unread Notifications
                    {unreadCount > 0 && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary"
                      >
                        {unreadCount} new
                      </motion.div>
                    )}
                  </CardTitle>
                  <CardDescription className="text-sm">
                    {unreadCount === 0 ? 'All caught up!' : `${unreadCount} notification${unreadCount !== 1 ? 's' : ''} awaiting your attention`}
                  </CardDescription>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowFilters(!showFilters)}
                  className={cn(
                    'gap-2 transition-all',
                    showFilters && 'bg-primary/10 border-primary'
                  )}
                >
                  <Filter className="h-4 w-4" />
                  Filter
                </Button>
                {unreadCount > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleMarkAllRead}
                    className="gap-2"
                  >
                    <CheckCheck className="h-4 w-4" />
                    Mark all read
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={refreshAll}
                  disabled={loading}
                  className="gap-2"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  Refresh
                </Button>
              </div>
            </div>
            
            <AnimatePresence>
              {showFilters && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden pt-4"
                >
                  <div className="flex w-full rounded-lg bg-muted/40 p-1 gap-0.5">
                    <Button
                      variant={filterType === 'all' ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setFilterType('all')}
                      className="flex-1 gap-2 rounded-md shadow-sm"
                    >
                      <Bell className="h-4 w-4 shrink-0" />
                      All
                    </Button>
                    <Button
                      variant={filterType === 'issues' ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setFilterType('issues')}
                      className="flex-1 gap-2 rounded-md shadow-sm"
                    >
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      Issues
                    </Button>
                    <Button
                      variant={filterType === 'opportunities' ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setFilterType('opportunities')}
                      className="flex-1 gap-2 rounded-md shadow-sm"
                    >
                      <TrendingUp className="h-4 w-4 shrink-0" />
                      Opportunities
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </CardHeader>
          
          <CardContent className="p-6">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-4 rounded-lg bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20"
              >
                <div className="flex items-center gap-2">
                  <XCircle className="h-4 w-4" />
                  {error}
                </div>
              </motion.div>
            )}
            
            {loading ? (
              <div className="flex flex-col items-center justify-center py-20">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 className="h-10 w-10 text-primary" />
                </motion.div>
                <p className="mt-4 text-sm text-muted-foreground">Loading notifications...</p>
              </div>
            ) : filteredNotifications.length === 0 ? (
              <EmptyState
                icon={Inbox}
                title="No unread notifications"
                description="Run a monitor above to check for new alerts, or you're all caught up."
                action="Run Monitor"
              />
            ) : (
              <>
                <motion.div 
                  className="space-y-3"
                  layout
                >
                  <AnimatePresence mode="popLayout">
                    {filteredNotifications.map((n) => renderNotification(n, false))}
                  </AnimatePresence>
                </motion.div>
                {unreadTotal > NOTIFICATIONS_PAGE_SIZE && (
                  <PaginationBar
                    page={unreadPage}
                    totalItems={unreadTotal}
                    pageSize={NOTIFICATIONS_PAGE_SIZE}
                    loading={loading}
                    onPageChange={setUnreadPage}
                  />
                )}
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* History with similar enhancements */}
      <motion.div variants={itemVariants}>
        <Card className="overflow-hidden border-0 shadow-lg">
          <CardHeader className="bg-gradient-to-r from-muted/30 via-transparent to-transparent pb-4">
            <div className="flex items-center gap-3">
              <motion.div 
                whileHover={{ scale: 1.1, rotate: -10 }}
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted"
              >
                <History className="h-5 w-5 text-muted-foreground" />
              </motion.div>
              <div>
                <CardTitle className="text-lg">History</CardTitle>
                <CardDescription className="text-sm">
                  {historyTotal} archived notification{historyTotal !== 1 ? 's' : ''}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          
          <CardContent className="p-6">
            {historyLoading && history.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 className="h-10 w-10 text-muted-foreground" />
                </motion.div>
                <p className="mt-4 text-sm text-muted-foreground">Loading history...</p>
              </div>
            ) : history.length === 0 ? (
              <EmptyState
                icon={History}
                title="No history yet"
                description="Notifications you mark as read will appear here."
              />
            ) : (
              <>
                <motion.div 
                  className="space-y-3"
                  layout
                >
                  <AnimatePresence mode="popLayout">
                    {history.map((n) => renderNotification(n, true))}
                  </AnimatePresence>
                </motion.div>
                {historyTotal > NOTIFICATIONS_PAGE_SIZE && (
                  <PaginationBar
                    page={historyPage}
                    totalItems={historyTotal}
                    pageSize={NOTIFICATIONS_PAGE_SIZE}
                    loading={historyLoading}
                    onPageChange={setHistoryPage}
                  />
                )}
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  );
};

export default Notifications;