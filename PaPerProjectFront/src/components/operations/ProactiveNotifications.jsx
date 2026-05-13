import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import {
  Bell, BellOff, BellRing, CheckCheck, Trash2, Loader2, RefreshCw,
  AlertTriangle, AlertCircle, Info, FileText, Sparkles, CalendarClock,
  TrendingUp, Filter, Eye, X,
} from 'lucide-react';
import * as operationsService from '@/services/operationsAgentService';
import ConfirmDialog from './ConfirmDialog';

// ──────────────────────────────────────────────
// Metadata — maps severity / type → icon + colour
// ──────────────────────────────────────────────
const SEVERITY_META = {
  critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.28)', label: 'Critical', icon: AlertTriangle },
  warning:  { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.28)', label: 'Warning',  icon: AlertCircle },
  info:     { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.28)', label: 'Info',     icon: Info },
};

const TYPE_META = {
  anomaly_detected: { label: 'Anomaly',  icon: AlertTriangle },
  threshold_breach: { label: 'Deadline', icon: CalendarClock },
  report_ready:     { label: 'Ready',    icon: FileText },
  document_update:  { label: 'Document', icon: FileText },
  metric_change:    { label: 'Insight',  icon: TrendingUp },
  digest_ready:     { label: 'Digest',   icon: Sparkles },
};

const FILTERS = [
  { value: 'all',      label: 'All' },
  { value: 'unread',   label: 'Unread' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning',  label: 'Warnings' },
  { value: 'info',     label: 'Info' },
];

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────
const relativeTime = (iso) => {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const groupByDay = (items) => {
  if (!items?.length) return [];
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const weekAgo = today - 7 * 86400000;

  const buckets = { Today: [], Yesterday: [], 'Earlier this week': [], Older: [] };
  items.forEach((n) => {
    const ts = new Date(n.created_at).getTime();
    if (ts >= today) buckets['Today'].push(n);
    else if (ts >= yesterday) buckets['Yesterday'].push(n);
    else if (ts >= weekAgo) buckets['Earlier this week'].push(n);
    else buckets['Older'].push(n);
  });

  return Object.entries(buckets)
    .filter(([, arr]) => arr.length > 0)
    .map(([label, arr]) => ({ label, items: arr }));
};

// ──────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────
const ProactiveNotifications = () => {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('all');
  const [busyIds, setBusyIds] = useState(new Set());
  const [confirmState, setConfirmState] = useState(null);
  const closeConfirm = () => setConfirmState(null);

  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setRefreshing(true);
      const res = await operationsService.listNotifications({ page_size: 100 });
      if (res?.status === 'success') {
        setItems(res.notifications || []);
      }
    } catch (err) {
      toast({
        title: 'Could not load notifications',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // Poll every 60s for fresh items
  useEffect(() => {
    const id = setInterval(() => load(true), 60000);
    return () => clearInterval(id);
  }, [load]);

  const totalUnread = useMemo(() => items.filter((n) => !n.is_read).length, [items]);

  const filtered = useMemo(() => {
    if (filter === 'all') return items;
    if (filter === 'unread') return items.filter((n) => !n.is_read);
    return items.filter((n) => n.severity === filter);
  }, [items, filter]);

  const grouped = useMemo(() => groupByDay(filtered), [filtered]);

  // ── Actions ──
  const handleMarkRead = async (n) => {
    if (n.is_read) return;
    setBusyIds((prev) => new Set(prev).add(n.id));
    try {
      await operationsService.markNotificationRead(n.id);
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
    } catch (err) {
      toast({ title: 'Action failed', description: err?.message, variant: 'destructive' });
    } finally {
      setBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(n.id);
        return next;
      });
    }
  };

  const handleMarkAllRead = async () => {
    if (totalUnread === 0) return;
    try {
      await operationsService.markAllNotificationsRead();
      setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
      toast({ title: 'All notifications marked read' });
    } catch (err) {
      toast({ title: 'Action failed', description: err?.message, variant: 'destructive' });
    }
  };

  const handleDeleteOne = (n) => {
    setConfirmState({
      title: 'Delete this notification?',
      description: 'This action cannot be undone.',
      confirmLabel: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          setConfirmState((prev) => (prev ? { ...prev, loading: true } : prev));
          await operationsService.deleteNotification(n.id);
          setItems((prev) => prev.filter((x) => x.id !== n.id));
          toast({ title: 'Notification deleted' });
        } catch (err) {
          toast({ title: 'Delete failed', description: err?.message, variant: 'destructive' });
        } finally {
          closeConfirm();
        }
      },
    });
  };

  const handleClearAll = () => {
    if (items.length === 0) return;
    setConfirmState({
      title: 'Clear all notifications?',
      description: 'Every notification in this inbox will be permanently removed.',
      confirmLabel: 'Clear all',
      variant: 'danger',
      onConfirm: async () => {
        try {
          setConfirmState((prev) => (prev ? { ...prev, loading: true } : prev));
          await operationsService.clearAllNotifications();
          setItems([]);
          toast({ title: 'Inbox cleared' });
        } catch (err) {
          toast({ title: 'Clear failed', description: err?.message, variant: 'destructive' });
        } finally {
          closeConfirm();
        }
      },
    });
  };

  return (
    <div
      className="w-full rounded-2xl border border-amber-500/10 overflow-hidden shadow-[0_8px_40px_-12px_rgba(245,158,11,0.15)] p-5 sm:p-6"
      style={{
        background: 'linear-gradient(135deg, #1a1333 0%, #1a1333 45%, rgba(64,40,10,0.55) 100%)',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-5 flex-wrap">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-11 h-11 rounded-xl relative"
            style={{ backgroundColor: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.28)' }}
          >
            {totalUnread > 0 ? (
              <BellRing className="h-5 w-5" style={{ color: '#f59e0b' }} />
            ) : (
              <Bell className="h-5 w-5" style={{ color: '#f59e0b' }} />
            )}
            {totalUnread > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                {totalUnread > 99 ? '99+' : totalUnread}
              </span>
            )}
          </div>
          <div>
            <h2 className="text-white text-lg font-semibold">Notifications</h2>
            <p className="text-white/55 text-xs">
              {totalUnread > 0
                ? `${totalUnread} unread · ${items.length} total`
                : items.length > 0
                  ? `All caught up · ${items.length} total`
                  : 'All caught up'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            title="Refresh"
            className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 bg-black/30 hover:bg-white/5 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-white/70 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <Button
            onClick={handleMarkAllRead}
            disabled={totalUnread === 0}
            size="sm"
            variant="outline"
            className="h-8 text-xs border-white/10 bg-transparent text-white/80 hover:bg-amber-500/10 hover:border-amber-500/30 hover:text-amber-200 disabled:opacity-40"
          >
            <CheckCheck className="h-3.5 w-3.5 mr-1" /> Mark all read
          </Button>
          <Button
            onClick={handleClearAll}
            disabled={items.length === 0}
            size="sm"
            variant="outline"
            className="h-8 text-xs border-white/10 bg-transparent text-white/80 hover:bg-red-500/10 hover:border-red-500/30 hover:text-red-300 disabled:opacity-40"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" /> Clear
          </Button>
        </div>
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Filter className="h-3.5 w-3.5 text-white/45" />
        {FILTERS.map((f) => {
          const active = filter === f.value;
          const count =
            f.value === 'all' ? items.length :
            f.value === 'unread' ? totalUnread :
            items.filter((n) => n.severity === f.value).length;
          return (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3 py-1 rounded-full text-[11px] font-semibold transition-colors flex items-center gap-1.5 ${
                active
                  ? 'bg-amber-500/20 text-amber-200 border border-amber-500/30'
                  : 'border border-white/10 bg-black/20 text-white/65 hover:text-white/90 hover:bg-white/5'
              }`}
            >
              {f.label}
              <span className={`${active ? 'text-amber-300' : 'text-white/40'} tabular-nums`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-white/50 text-sm">
          <Loader2 className="h-5 w-5 animate-spin mr-2" style={{ color: '#f59e0b' }} />
          Loading notifications...
        </div>
      ) : grouped.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <div className="space-y-5">
          {grouped.map((bucket) => (
            <div key={bucket.label}>
              <div className="flex items-center gap-2 mb-2">
                <div className="text-[10px] uppercase tracking-wider text-white/45 font-semibold">
                  {bucket.label}
                </div>
                <div className="flex-1 h-px bg-white/5" />
                <div className="text-[10px] text-white/35">{bucket.items.length}</div>
              </div>
              <div className="space-y-2">
                {bucket.items.map((n) => (
                  <NotificationCard
                    key={n.id}
                    n={n}
                    busy={busyIds.has(n.id)}
                    onMarkRead={() => handleMarkRead(n)}
                    onDelete={() => handleDeleteOne(n)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        onOpenChange={(next) => { if (!next) closeConfirm(); }}
        title={confirmState?.title}
        description={confirmState?.description}
        confirmLabel={confirmState?.confirmLabel}
        variant={confirmState?.variant}
        loading={!!confirmState?.loading}
        onConfirm={confirmState?.onConfirm}
      />
    </div>
  );
};

// ──────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────

const NotificationCard = ({ n, busy, onMarkRead, onDelete }) => {
  const sev = SEVERITY_META[n.severity] || SEVERITY_META.info;
  const typ = TYPE_META[n.notification_type] || { label: n.notification_type, icon: Info };
  const SevIcon = sev.icon;
  const TypeIcon = typ.icon;

  return (
    <div
      className={`group relative rounded-xl border px-4 py-3 transition-all ${
        n.is_read
          ? 'border-white/10 bg-white/[0.02]'
          : 'border-amber-500/25 bg-amber-500/[0.06] shadow-[0_0_0_1px_rgba(245,158,11,0.08)]'
      }`}
    >
      {!n.is_read && (
        <span
          className="absolute top-3 left-1.5 h-2 w-2 rounded-full bg-amber-400"
          title="Unread"
        />
      )}

      <div className="flex items-start gap-3 pl-2">
        <div
          className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0 mt-0.5"
          style={{ backgroundColor: sev.bg, border: `1px solid ${sev.border}` }}
        >
          <SevIcon className="h-4 w-4" style={{ color: sev.color }} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <h4 className={`text-sm font-semibold truncate ${n.is_read ? 'text-white/85' : 'text-white'}`}>
              {n.title}
            </h4>
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-semibold"
              style={{ backgroundColor: sev.bg, color: sev.color, border: `1px solid ${sev.border}` }}
            >
              <TypeIcon className="h-2.5 w-2.5" />
              {typ.label}
            </span>
          </div>
          {n.message && (
            <p className="text-xs text-white/60 leading-relaxed line-clamp-2">
              {n.message}
            </p>
          )}
          <div className="text-[10px] text-white/35 mt-1">
            {relativeTime(n.created_at)}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          {!n.is_read && (
            <button
              onClick={onMarkRead}
              disabled={busy}
              title="Mark as read"
              className="h-7 w-7 flex items-center justify-center rounded-md border border-white/10 bg-black/30 hover:bg-amber-500/10 hover:border-amber-500/30 text-white/70 hover:text-amber-200 disabled:opacity-50"
            >
              <Eye className="h-3 w-3" />
            </button>
          )}
          <button
            onClick={onDelete}
            title="Delete"
            className="h-7 w-7 flex items-center justify-center rounded-md border border-white/10 bg-black/30 hover:bg-red-500/10 hover:border-red-500/30 text-white/70 hover:text-red-300"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
};

const EmptyState = ({ filter }) => {
  const copy = {
    all:      { title: 'No notifications yet', sub: 'As you upload, summarise and generate documents, alerts will appear here.' },
    unread:   { title: 'Nothing unread', sub: 'You are all caught up.' },
    critical: { title: 'No critical alerts', sub: 'No critical items flagged right now.' },
    warning:  { title: 'No warnings', sub: 'No warnings to review.' },
    info:     { title: 'No info alerts', sub: 'Nothing informational at the moment.' },
  }[filter] || { title: 'Nothing here', sub: '' };
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div
        className="w-14 h-14 rounded-2xl mb-3 flex items-center justify-center"
        style={{ backgroundColor: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.18)' }}
      >
        <BellOff className="h-6 w-6 text-amber-300/70" />
      </div>
      <div className="text-white/90 text-sm font-semibold">{copy.title}</div>
      {copy.sub && <div className="text-white/45 text-xs mt-1 max-w-md">{copy.sub}</div>}
    </div>
  );
};

export default ProactiveNotifications;
