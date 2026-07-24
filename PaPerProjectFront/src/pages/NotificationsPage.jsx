import { useState, useEffect, useMemo } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Bell, Check, Search, RefreshCw, Loader2, ChevronLeft,
  AlertTriangle, CheckCircle2, Inbox, Clock, ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Full-page notification list.
 *
 * The navbar dropdown truncates every title and clamps the body to two lines, so
 * long messages (token quota, key requests) are unreadable there. This page shows
 * each one in full.
 *
 * Like DashboardNavbar, it reads whichever of the two notification systems applies
 * to the logged-in user: PMNotification for company users, the core Notification
 * model for Django users. Keep the endpoint choice below in sync with the navbar.
 */

const GRADIENT_BG = 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';

// Severity drives the left border + icon, so critical items are scannable.
const getSeverity = (n) => {
  const type = `${n.type || ''} ${n.notification_type || ''}`;
  const sev = n.severity || '';
  if (sev === 'critical' || type.includes('exhausted') || type.includes('rejected')
    || type.includes('at_risk') || type.includes('overdue') || type.includes('blocked')) {
    return 'critical';
  }
  if (sev === 'warning' || type.includes('quota') || type.includes('warning')
    || type.includes('approaching') || type.includes('imbalance')) {
    return 'warning';
  }
  if (type.includes('approved') || type.includes('accepted') || type.includes('completed')
    || type.includes('milestone')) {
    return 'success';
  }
  return 'info';
};

const SEVERITY_STYLE = {
  critical: {
    accent: 'border-l-red-500',
    icon: AlertTriangle,
    iconClass: 'text-red-400 bg-red-500/10 border-red-500/25',
    title: 'text-red-300',
  },
  warning: {
    accent: 'border-l-amber-500',
    icon: AlertTriangle,
    iconClass: 'text-amber-400 bg-amber-500/10 border-amber-500/25',
    title: 'text-amber-300',
  },
  success: {
    accent: 'border-l-emerald-500',
    icon: CheckCircle2,
    iconClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25',
    title: 'text-emerald-300',
  },
  info: {
    accent: 'border-l-violet-500',
    icon: Bell,
    iconClass: 'text-violet-400 bg-violet-500/10 border-violet-500/25',
    title: 'text-violet-300',
  },
};

const formatFullTime = (iso) => {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch { return ''; }
};

const formatTimeAgo = (iso) => {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch { return ''; }
};

// 'quota_warning' -> 'Quota Warning'
const humanizeType = (type) =>
  (type || 'other').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const StatCard = ({ icon: Icon, label, value, accent }) => (
  <div className="bg-[#120d22] border border-[#2d2342] rounded-xl p-4 hover:border-violet-500/30 transition-colors">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-xs uppercase tracking-wider text-white/40 mb-1">{label}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
  </div>
);

const NotificationsPage = () => {
  const navigate = useNavigate();

  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [readFilter, setReadFilter] = useState('all');

  // Same endpoint selection as DashboardNavbar.
  const isCompanyUser = !!localStorage.getItem('company_auth_token');
  const authToken = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
  const isPM = isCompanyUser && !localStorage.getItem('auth_token');
  const notifEndpoint = isPM
    ? `${API_BASE_URL}/project-manager/ai/notifications`
    : `${API_BASE_URL}/notifications`;

  const fetchNotifications = async () => {
    try {
      if (!authToken) return;
      const res = await fetch(notifEndpoint, { headers: { Authorization: `Token ${authToken}` } });
      if (!res.ok) return;
      const data = await res.json();
      // PM endpoint: { data: { notifications: [...] } }; core: { data: [...] }
      const notifs = data?.data?.notifications || data?.data || [];
      setNotifications(Array.isArray(notifs) ? notifs : []);
    } catch {
      /* network hiccup — keep what's on screen */
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markAsRead = async (id) => {
    try {
      if (isPM) {
        await fetch(`${API_BASE_URL}/project-manager/ai/notifications/read`, {
          method: 'POST',
          headers: { Authorization: `Token ${authToken}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ notification_ids: [id] }),
        });
      } else {
        await fetch(`${API_BASE_URL}/notifications/${id}/read`, {
          method: 'PUT',
          headers: { Authorization: `Token ${authToken}` },
        });
      }
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch { /* row just stays unread */ }
  };

  const markAllRead = async () => {
    try {
      if (isPM) {
        const allIds = notifications.filter((n) => !n.is_read).map((n) => n.id);
        if (allIds.length) {
          await fetch(`${API_BASE_URL}/project-manager/ai/notifications/read`, {
            method: 'POST',
            headers: { Authorization: `Token ${authToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ notification_ids: allIds }),
          });
        }
      } else {
        await fetch(`${API_BASE_URL}/notifications/read-all`, {
          method: 'PUT',
          headers: { Authorization: `Token ${authToken}` },
        });
      }
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch { /* ignore */ }
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const criticalCount = notifications.filter((n) => getSeverity(n) === 'critical').length;

  const visible = useMemo(() => notifications.filter((n) => {
    if (readFilter === 'unread' && n.is_read) return false;
    if (readFilter === 'read' && !n.is_read) return false;
    if (search) {
      const hay = `${n.title || ''} ${n.message || ''}`.toLowerCase();
      if (!hay.includes(search.toLowerCase())) return false;
    }
    return true;
  }), [notifications, readFilter, search]);

  const hasFilters = search || readFilter !== 'all';

  return (
    <>
      <Helmet><title>Notifications — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={Bell}
          title="Notifications"
          subtitle="All your alerts, reminders and updates in one place"
        />

        <div className="container mx-auto px-4 py-8 max-w-5xl">
          {/* Back link */}
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1 text-sm text-white/50 hover:text-white transition-colors mb-4"
          >
            <ChevronLeft className="w-4 h-4" />
            Back
          </button>

          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <StatCard
              icon={Inbox}
              label="Total"
              value={notifications.length}
              accent="text-violet-300 bg-violet-500/10 border border-violet-500/25"
            />
            <StatCard
              icon={Bell}
              label="Unread"
              value={unreadCount}
              accent="text-blue-300 bg-blue-500/10 border border-blue-500/25"
            />
            <StatCard
              icon={AlertTriangle}
              label="Needs attention"
              value={criticalCount}
              accent="text-red-300 bg-red-500/10 border border-red-500/25"
            />
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-2 mb-5">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
              <Input
                placeholder="Search notifications..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 bg-[#120d22] border-[#2d2342] text-white placeholder:text-white/30"
              />
            </div>
            {/* No type filter: the backend stores nearly every notification as
                notification_type='custom', so the dropdown offered a single
                meaningless option. Search covers the same ground until the
                backend assigns real types. */}
            <Select value={readFilter} onValueChange={setReadFilter}>
              <SelectTrigger className="w-[130px] bg-[#120d22] border-[#2d2342] text-white">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="unread">Unread</SelectItem>
                <SelectItem value="read">Read</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="icon"
              onClick={() => { setRefreshing(true); fetchNotifications(); }}
              disabled={refreshing}
              className="border-[#2d2342] bg-[#120d22] text-white/70 hover:bg-white/5 hover:text-white shrink-0"
            >
              {refreshing
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <RefreshCw className="h-4 w-4" />}
            </Button>
            {unreadCount > 0 && (
              <Button
                onClick={markAllRead}
                className="shrink-0 text-white"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}
              >
                <Check className="h-4 w-4 mr-1" />
                Mark all read
              </Button>
            )}
          </div>

          {/* List */}
          {loading ? (
            <div className="flex justify-center py-20">
              <Loader2 className="h-7 w-7 animate-spin text-violet-400" />
            </div>
          ) : visible.length === 0 ? (
            <div className="rounded-xl border border-[#2d2342] bg-[#120d22] py-20 text-center">
              <Inbox className="h-10 w-10 mx-auto text-white/15 mb-3" />
              <p className="text-white/60 text-sm font-medium">
                {notifications.length === 0 ? 'No notifications yet' : 'Nothing matches these filters'}
              </p>
              <p className="text-white/30 text-xs mt-1">
                {notifications.length === 0
                  ? "You're all caught up."
                  : 'Try clearing the search or filters.'}
              </p>
              {hasFilters && notifications.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setSearch(''); setReadFilter('all'); }}
                  className="mt-4 border-[#2d2342] text-white/70 hover:bg-white/5 hover:text-white"
                >
                  Clear filters
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {visible.map((n, i) => {
                const type = n.type || n.notification_type || '';
                const sev = getSeverity(n);
                const style = SEVERITY_STYLE[sev];
                const Icon = style.icon;
                // Only the core Notification model carries link/action_url; PM rows won't.
                const target = n.link || n.action_url;

                return (
                  <motion.div
                    key={n.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18, delay: Math.min(i * 0.02, 0.2) }}
                    className={`rounded-xl border border-[#2d2342] border-l-4 ${style.accent} p-4 transition-colors hover:border-violet-500/30 ${
                      n.is_read ? 'bg-[#120d22]' : 'bg-[#181030]'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${style.iconClass}`}>
                        <Icon className="w-4 h-4" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-3 flex-wrap">
                          <div className="flex items-center gap-2 min-w-0">
                            {!n.is_read && (
                              <span className="w-2 h-2 rounded-full bg-violet-500 shrink-0" />
                            )}
                            {/* Full title — no truncate; this is the point of the page */}
                            <h3 className={`text-sm font-semibold ${style.title}`}>{n.title}</h3>
                          </div>
                          {/* 'custom' is the backend's catch-all for anything without a
                              real type — a badge reading "Custom" tells the user nothing,
                              so skip it. Genuine types still get a badge. */}
                          {type && type !== 'custom' && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full border border-[#3a295a] bg-white/5 text-white/45 shrink-0">
                              {humanizeType(type)}
                            </span>
                          )}
                        </div>

                        {/* Full message — nothing clamped */}
                        <p className="text-sm text-white/70 mt-2 leading-relaxed whitespace-pre-wrap break-words">
                          {n.message}
                        </p>

                        <div className="flex items-center gap-4 mt-3 flex-wrap">
                          <span className="inline-flex items-center gap-1 text-[11px] text-white/30">
                            <Clock className="w-3 h-3" />
                            {formatTimeAgo(n.created_at)} · {formatFullTime(n.created_at)}
                          </span>
                          {target && (
                            <button
                              onClick={() => { if (!n.is_read) markAsRead(n.id); navigate(target); }}
                              className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-400 hover:text-violet-300"
                            >
                              <ExternalLink className="w-3 h-3" />
                              Open
                            </button>
                          )}
                          {!n.is_read && (
                            <button
                              onClick={() => markAsRead(n.id)}
                              className="inline-flex items-center gap-1 text-[11px] text-white/35 hover:text-white/70"
                            >
                              <Check className="w-3 h-3" />
                              Mark as read
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default NotificationsPage;
