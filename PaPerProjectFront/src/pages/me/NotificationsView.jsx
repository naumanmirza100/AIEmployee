import React, { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Bell, Loader2, RefreshCw, CheckCheck } from 'lucide-react';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * NotificationsView — /me/notifications
 *
 * Real inbox for individual employees. Uses /notifications (Django-token
 * user endpoint) since /me/* is scoped to employees. The classic navbar
 * dropdown truncates each row; this page shows the full text and lets
 * you mark items read/all-read without a page hop.
 */
export default function NotificationsView() {
  const { toast } = useToast();

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    fetchNotifications();
  }, []);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
      if (!token) { setItems([]); return; }
      const res = await fetch(`${API_BASE_URL}/notifications`, {
        headers: { 'Authorization': `Token ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      const list = data?.data?.notifications || data?.data || [];
      setItems(Array.isArray(list) ? list : []);
    } catch (err) {
      toast({ title: 'Error', description: 'Could not load notifications', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const markOneRead = async (id) => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
      await fetch(`${API_BASE_URL}/notifications/${id}/read`, {
        method: 'PUT',
        headers: { 'Authorization': `Token ${token}`, 'Content-Type': 'application/json' },
      });
      setItems((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n));
    } catch { /* silent */ }
  };

  const markAllRead = async () => {
    setMarkingAll(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
      await fetch(`${API_BASE_URL}/notifications/read-all`, {
        method: 'PUT',
        headers: { 'Authorization': `Token ${token}`, 'Content-Type': 'application/json' },
      });
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      toast({ title: 'All marked read' });
    } catch (err) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    } finally {
      setMarkingAll(false);
    }
  };

  const formatWhen = (iso) => {
    try {
      const diff = Date.now() - new Date(iso).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      const days = Math.floor(hrs / 24);
      if (days < 30) return `${days}d ago`;
      return new Date(iso).toLocaleDateString();
    } catch { return ''; }
  };

  const unreadCount = items.filter((n) => !n.is_read).length;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-white">
          <Bell className="h-6 w-6 text-violet-300" />
          <div>
            <h2 className="text-2xl font-bold">Notifications</h2>
            <p className="text-xs text-white/50">
              {loading ? 'Loading…' : `${items.length} total${unreadCount > 0 ? ` • ${unreadCount} unread` : ''}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <Button variant="outline" size="sm" onClick={markAllRead} disabled={markingAll}
              className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
              <CheckCheck className="h-3.5 w-3.5 mr-1" /> Mark all read
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={fetchNotifications}
            className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-violet-300" /></div>
      ) : items.length === 0 ? (
        <Card className="bg-white/[0.02] border-white/10">
          <CardContent className="py-16 text-center">
            <Bell className="h-10 w-10 mx-auto mb-3 text-white/25" />
            <p className="text-sm text-white/60">You're all clear. No notifications.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="divide-y divide-white/5 rounded-lg border border-white/[0.08] bg-white/[0.02]">
          {items.map((n) => (
            <button
              key={n.id}
              onClick={() => !n.is_read && markOneRead(n.id)}
              className={`w-full text-left px-4 py-3 hover:bg-white/[0.04] transition-colors ${!n.is_read ? 'bg-violet-500/[0.05]' : ''}`}
            >
              <div className="flex items-start gap-3">
                {!n.is_read && <div className="w-2 h-2 rounded-full bg-violet-400 mt-1.5 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className={`text-sm truncate ${!n.is_read ? 'text-white font-medium' : 'text-white/70'}`}>
                      {n.title}
                    </p>
                    <span className="text-[10px] text-white/40 shrink-0">{formatWhen(n.created_at)}</span>
                  </div>
                  {n.message && (
                    <p className="text-xs text-white/50 mt-0.5">{n.message}</p>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
