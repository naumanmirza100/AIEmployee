import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { LogOut, Bell, Key, User, Menu } from 'lucide-react';
import AgentSidebar, { EXPANDED_W, COLLAPSED_W } from '@/components/common/AgentSidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { API_BASE_URL } from '@/config/apiConfig';

const DashboardNavbar = ({
  icon: Icon,
  title,
  subtitle,
  user,
  showNavTabs = false,
  activeSection,
  onSectionChange,
  onLogout,
  onNotificationClick,
  navItems = [],
  sidebarLoading = false,
}) => {
  const navigate = useNavigate();
  const [showConfirm, setShowConfirm] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const notifRef = useRef(null);

  // ── Agent sidebar state ──
  const hasSidebar = showNavTabs && navItems.length > 0;
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('agentSidebarCollapsed') === '1'; } catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggleCollapsed = () => {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem('agentSidebarCollapsed', next ? '1' : '0'); } catch {}
      return next;
    });
  };

  // Reserve space for the fixed desktop sidebar by padding the document body,
  // so page content (centered in its own container) shifts right without any
  // per-page change. Restored on unmount. Mobile (< md) reserves nothing — the
  // sidebar is an overlay drawer there.
  useEffect(() => {
    if (!hasSidebar) return undefined;
    const mq = window.matchMedia('(min-width: 768px)');
    const apply = () => {
      const w = mq.matches ? (collapsed ? COLLAPSED_W : EXPANDED_W) : 0;
      document.body.style.paddingLeft = `${w}px`;
    };
    apply();
    mq.addEventListener('change', apply);
    return () => {
      mq.removeEventListener('change', apply);
      document.body.style.paddingLeft = '';
    };
  }, [hasSidebar, collapsed]);

  // Fetch notifications for project users (Django User auth)
  // Determine which auth token and notification endpoint to use
  const isCompanyUser = !!localStorage.getItem('company_auth_token');
  const authToken = localStorage.getItem('auth_token') || localStorage.getItem('company_auth_token');
  const notifEndpoint = isCompanyUser && !localStorage.getItem('auth_token')
    ? `${API_BASE_URL}/project-manager/ai/notifications`
    : `${API_BASE_URL}/notifications`;

  useEffect(() => {
    const fetchNotifications = async () => {
      try {
        if (!authToken) return;
        const res = await fetch(notifEndpoint, {
          headers: { 'Authorization': `Token ${authToken}` },
        });
        if (!res.ok) return;
        const data = await res.json();
        // PMNotification endpoint returns { data: { notifications: [...], unread_count } }
        // User Notification endpoint returns { data: [...] }
        const notifs = data?.data?.notifications || data?.data || [];
        setNotifications(Array.isArray(notifs) ? notifs : []);
        const unread = data?.data?.unread_count ?? notifs.filter((n) => !n.is_read).length;
        setUnreadCount(unread);
      } catch {}
    };
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, []);

  // Close panel on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setShowNotifPanel(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const markAsRead = async (id) => {
    try {
      if (isCompanyUser && !localStorage.getItem('auth_token')) {
        // PMNotifications use a different mark-read endpoint
        await fetch(`${API_BASE_URL}/project-manager/ai/notifications/read`, {
          method: 'POST',
          headers: { 'Authorization': `Token ${authToken}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ notification_ids: [id] }),
        });
      } else {
        await fetch(`${API_BASE_URL}/notifications/${id}/read`, {
          method: 'PUT',
          headers: { 'Authorization': `Token ${authToken}`, 'Content-Type': 'application/json' },
        });
      }
      setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n));
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {}
  };

  const markAllRead = async () => {
    try {
      if (isCompanyUser && !localStorage.getItem('auth_token')) {
        const allIds = notifications.filter((n) => !n.is_read).map((n) => n.id);
        if (allIds.length) {
          await fetch(`${API_BASE_URL}/project-manager/ai/notifications/read`, {
            method: 'POST',
            headers: { 'Authorization': `Token ${authToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ notification_ids: allIds }),
          });
        }
      } else {
        await fetch(`${API_BASE_URL}/notifications/read-all`, {
          method: 'PUT',
          headers: { 'Authorization': `Token ${authToken}`, 'Content-Type': 'application/json' },
        });
      }
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {}
  };

  const getNotifColor = (type) => {
    if (type?.includes('meeting_request') || type?.includes('meeting_counter')) return 'text-violet-400';
    if (type?.includes('accepted')) return 'text-green-400';
    if (type?.includes('rejected') || type?.includes('withdrawn')) return 'text-red-400';
    return 'text-blue-400';
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

  return (
    <>
      <header
        className="border-b border-white/[0.08] sticky top-0 z-30"
        style={{ background: 'linear-gradient(180deg, #0a0a14 0%, #0d0b1a 40%, #110e1f 100%)' }}
      >
        <div className="container mx-auto px-3 sm:px-4 py-2 sm:py-2.5">
          {/* Header Row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 sm:gap-2.5 min-w-0 flex-1">
              {hasSidebar && (
                <button
                  onClick={() => setMobileOpen(true)}
                  className="md:hidden h-8 w-8 shrink-0 flex items-center justify-center rounded-md text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                  title="Open menu"
                >
                  <Menu className="h-5 w-5" />
                </button>
              )}
              {/* Logo only when there's no sidebar (the sidebar already shows the
                  brand); avoids a duplicate logo in the top bar. */}
              {!hasSidebar && (
                <Link to="/" className="shrink-0" title="Pay Per Project — Home">
                  <img
                    src="/logo.png"
                    alt="Pay Per Project logo"
                    className="h-8 w-8 sm:h-9 sm:w-9 rounded-md object-contain"
                  />
                </Link>
              )}
              {Icon && <Icon className="h-5 w-5 sm:h-6 sm:w-6 text-violet-400 shrink-0" />}
              <div className="min-w-0">
                <h1 className="text-sm sm:text-lg font-bold truncate text-white leading-tight">{title}</h1>
                {subtitle && <p className="text-[11px] sm:text-xs text-white/45 truncate leading-tight">{subtitle}</p>}
              </div>
            </div>
            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              {/* Notification Bell */}
              <div className="relative" ref={notifRef}>
                <button
                  onClick={() => setShowNotifPanel((v) => !v)}
                  className="h-8 w-8 sm:h-9 sm:w-9 rounded-full flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors relative"
                  title="Notifications"
                >
                  <Bell className="h-4 w-4" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 h-4 w-4 rounded-full bg-red-500 text-[10px] font-bold text-white flex items-center justify-center"
                      style={{ boxShadow: '0 0 6px rgba(239,68,68,0.5)' }}>
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </button>

                {/* Notification Dropdown */}
                {showNotifPanel && (
                  <div
                    className="absolute right-0 top-11 w-80 max-h-[400px] overflow-y-auto scrollbar-none rounded-xl border border-white/10 z-50"
                    style={{ background: 'linear-gradient(180deg, #0d0b1a 0%, #1a0a2e 100%)', boxShadow: '0 8px 40px rgba(0,0,0,0.5)', scrollbarWidth: 'none', msOverflowStyle: 'none' }}
                  >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                      <span className="text-sm font-semibold text-white">Notifications</span>
                      {unreadCount > 0 && (
                        <button onClick={markAllRead} className="text-[11px] text-violet-400 hover:text-violet-300">
                          Mark all read
                        </button>
                      )}
                    </div>
                    {notifications.length === 0 ? (
                      <div className="p-6 text-center text-sm text-white/40">No notifications</div>
                    ) : (
                      <div className="divide-y divide-white/5">
                        {notifications.slice(0, 20).map((n) => (
                          <button
                            key={n.id}
                            onClick={() => {
                              if (!n.is_read) markAsRead(n.id);
                              setShowNotifPanel(false);
                              // Pages that pass their own handler (User / PM dashboards)
                              // keep their tab-switching behaviour; everywhere else we
                              // open the full-detail page, since the dropdown truncates.
                              if (onNotificationClick) {
                                onNotificationClick(n);
                              } else {
                                navigate('/notifications');
                              }
                            }}
                            className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors ${!n.is_read ? 'bg-violet-500/5' : ''}`}
                          >
                            <div className="flex items-start gap-2">
                              {!n.is_read && <div className="w-2 h-2 rounded-full bg-violet-500 mt-1.5 shrink-0" />}
                              <div className="flex-1 min-w-0" title={`${n.title}\n\n${n.message}`}>
                                <p className={`text-xs font-medium ${getNotifColor(n.type)} truncate`}>{n.title}</p>
                                <p className="text-[11px] text-white/50 mt-0.5 line-clamp-2">{n.message}</p>
                                <p className="text-[10px] text-white/30 mt-1">{formatTimeAgo(n.created_at)}</p>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Escape hatch to the full-detail page — the rows above are
                        truncated, and pages with their own click handler never
                        navigate here otherwise. */}
                    <button
                      onClick={() => {
                        setShowNotifPanel(false);
                        navigate('/notifications');
                      }}
                      className="w-full px-4 py-2.5 text-center text-[11px] font-medium text-violet-400 hover:text-violet-300 hover:bg-white/5 border-t border-white/10 transition-colors sticky bottom-0"
                      style={{ background: 'linear-gradient(180deg, rgba(13,11,26,0.9) 0%, #1a0a2e 100%)' }}
                    >
                      View all notifications
                    </button>
                  </div>
                )}
              </div>

              {/* Profile dropdown — avatar + name/email; opens a menu with profile, API keys, logout */}
              {user && (
                <DropdownMenu>
                  <DropdownMenuTrigger className="flex items-center gap-2 rounded-full focus:outline-none focus:ring-2 focus:ring-violet-400/50 pr-1">
                    <div
                      className="h-8 w-8 rounded-full flex items-center justify-center shrink-0 text-white font-bold text-sm select-none"
                      style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #a259ff 100%)', boxShadow: '0 0 10px rgba(124,58,237,0.45)' }}
                    >
                      {(user.fullName || user.username || user.email || 'U').charAt(0).toUpperCase()}
                    </div>
                    <div className="hidden sm:block text-left">
                      <p className="text-xs font-semibold text-white leading-tight truncate max-w-[150px]">
                        {user.fullName || user.username || user.email?.split('@')[0] || 'User'}
                      </p>
                      <p className="text-[11px] text-white/40 leading-tight truncate max-w-[150px]">{user.email}</p>
                    </div>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel className="font-normal">
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">
                            {user.fullName || user.username || user.email?.split('@')[0] || 'User'}
                          </p>
                          {user.email && (
                            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                          )}
                        </div>
                      </div>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => navigate(isCompanyUser ? '/company/profile' : '/me/profile')}
                      className="cursor-pointer"
                    >
                      <User className="mr-2 h-4 w-4" />
                      Profile
                    </DropdownMenuItem>
                    {isCompanyUser && (
                      <DropdownMenuItem
                        onClick={() => navigate('/company/settings/api-keys')}
                        className="cursor-pointer"
                      >
                        <Key className="mr-2 h-4 w-4" />
                        API Keys
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => setShowConfirm(true)}
                      className="cursor-pointer text-red-500 focus:text-red-500"
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      Logout
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>

          {/* Cross-agent navigation now lives in the left AgentSidebar (below),
              not in top tabs. */}
        </div>
      </header>

      {/* ── Left agent sidebar (replaces the old top tabs) ── */}
      {hasSidebar && (
        <AgentSidebar
          navItems={navItems}
          activeSection={activeSection}
          collapsed={collapsed}
          onToggle={toggleCollapsed}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
          loading={sidebarLoading}
        />
      )}

      {/* Logout Confirmation Modal */}
      {showConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
          onClick={() => setShowConfirm(false)}
        >
          <div
            className="w-full max-w-sm mx-4 rounded-2xl p-6 flex flex-col gap-4"
            style={{
              background: 'linear-gradient(135deg, #0d0b1a 0%, #1a0a2e 100%)',
              border: '1px solid rgba(124,58,237,0.3)',
              boxShadow: '0 8px 40px 0 rgba(124,58,237,0.2)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Icon */}
            <div className="flex justify-center">
              <div
                className="h-14 w-14 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(124,58,237,0.15)', border: '1px solid rgba(124,58,237,0.3)' }}
              >
                <LogOut className="h-6 w-6 text-violet-400" />
              </div>
            </div>
            {/* Text */}
            <div className="text-center">
              <h3 className="text-lg font-semibold text-white">Logout?</h3>
              <p className="text-sm text-white/50 mt-1">Are you sure you want to logout?</p>
            </div>
            {/* Buttons */}
            <div className="flex gap-3 mt-1">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 h-10 rounded-xl text-sm font-medium text-white/70 hover:text-white transition-colors"
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
              >
                Cancel
              </button>
              <button
                onClick={() => { setShowConfirm(false); onLogout(); }}
                className="flex-1 h-10 rounded-xl text-sm font-bold text-white transition-all hover:opacity-90"
                style={{ background: 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)', boxShadow: '0 0 12px rgba(124,58,237,0.4)' }}
              >
                Yes, Logout
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default DashboardNavbar;
