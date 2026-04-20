import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { LogOut, Bell, Key } from 'lucide-react';
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
}) => {
  const navigate = useNavigate();
  const [showConfirm, setShowConfirm] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const notifRef = useRef(null);

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

  const handleNavClick = (item) => {
    if (item.onClick) {
      item.onClick();
    } else if (item.path) {
      navigate(item.path);
    } else if (onSectionChange) {
      onSectionChange(item.section);
    }
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
        className="border-b border-white/[0.08]"
        style={{ background: 'linear-gradient(180deg, #0a0a14 0%, #0d0b1a 40%, #110e1f 100%)' }}
      >
        <div className="container mx-auto px-3 sm:px-4 py-3 sm:py-4">
          {/* Header Row */}
          <div className="flex items-center justify-between mb-3 sm:mb-4 gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
              {Icon && <Icon className="h-6 w-6 sm:h-8 sm:w-8 text-violet-400 shrink-0" />}
              <div className="min-w-0">
                <h1 className="text-lg sm:text-2xl font-bold truncate text-white">{title}</h1>
                {subtitle && <p className="text-xs sm:text-sm text-white/50 truncate">{subtitle}</p>}
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
                    className="absolute right-0 top-11 w-80 max-h-[400px] overflow-y-auto rounded-xl border border-white/10 z-50"
                    style={{ background: 'linear-gradient(180deg, #0d0b1a 0%, #1a0a2e 100%)', boxShadow: '0 8px 40px rgba(0,0,0,0.5)' }}
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
                              if (onNotificationClick) onNotificationClick(n);
                            }}
                            className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors ${!n.is_read ? 'bg-violet-500/5' : ''}`}
                          >
                            <div className="flex items-start gap-2">
                              {!n.is_read && <div className="w-2 h-2 rounded-full bg-violet-500 mt-1.5 shrink-0" />}
                              <div className="flex-1 min-w-0">
                                <p className={`text-xs font-medium ${getNotifColor(n.type)} truncate`}>{n.title}</p>
                                <p className="text-[11px] text-white/50 mt-0.5 line-clamp-2">{n.message}</p>
                                <p className="text-[10px] text-white/30 mt-1">{formatTimeAgo(n.created_at)}</p>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {user && (
                <div className="flex items-center gap-2 sm:gap-3">
                  {/* Avatar */}
                  <div
                    className="h-8 w-8 sm:h-10 sm:w-10 rounded-full flex items-center justify-center shrink-0 text-white font-bold text-sm sm:text-base select-none"
                    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #a259ff 100%)', boxShadow: '0 0 10px rgba(124,58,237,0.45)' }}
                  >
                    {(user.fullName || user.username || user.email || 'U').charAt(0).toUpperCase()}
                  </div>
                  {/* Name + Email */}
                  <div className="hidden sm:block text-left">
                    <p className="text-sm font-semibold text-white leading-tight truncate max-w-[160px]">
                      {user.fullName || user.username || user.email?.split('@')[0] || 'User'}
                    </p>
                    <p className="text-xs text-white/40 leading-tight truncate max-w-[160px]">{user.email}</p>
                  </div>
                </div>
              )}
              {/* API Keys (company users only) */}
              {isCompanyUser && (
                <button
                  onClick={() => navigate('/company/settings/api-keys')}
                  className="h-8 w-8 sm:h-9 sm:w-9 rounded-full flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors"
                  title="API Keys & Token Quota"
                >
                  <Key className="h-4 w-4" />
                </button>
              )}
              {/* Logout */}
              <button
                onClick={() => setShowConfirm(true)}
                className="h-8 w-8 sm:h-9 sm:w-9 rounded-full flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          {showNavTabs && navItems.length > 0 && (
            <div className="border-t border-white/[0.08] pt-3 sm:pt-4 -mx-3 sm:-mx-4 px-3 sm:px-4">
              <div className="flex gap-1.5 sm:gap-2 overflow-x-auto scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent pb-1">
                {navItems.map((item) => {
                  const isActive = item.section === activeSection;
                  return (
                    <Button
                      key={item.section || item.path || item.label}
                      variant={isActive ? 'default' : 'ghost'}
                      onClick={() => handleNavClick(item)}
                      size="sm"
                      className={`flex items-center gap-1.5 sm:gap-2 whitespace-nowrap shrink-0 h-8 sm:h-9 px-2.5 sm:px-3 text-xs sm:text-sm ${
                        isActive
                          ? 'bg-violet-600 hover:bg-violet-700 text-white shadow-[0_0_12px_rgba(139,92,246,0.3)]'
                          : 'text-white/60 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      {item.icon && <item.icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
                      <span className="hidden xs:inline sm:inline">{item.label}</span>
                      <span className="xs:hidden sm:hidden">{item.shortLabel || item.label.split(' ')[0]}</span>
                    </Button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </header>

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
