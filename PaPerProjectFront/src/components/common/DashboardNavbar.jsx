import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';

const DashboardNavbar = ({
  icon: Icon,
  title,
  subtitle,
  user,
  showNavTabs = false,
  activeSection,
  onSectionChange,
  onLogout,
  navItems = [],
}) => {
  const navigate = useNavigate();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleNavClick = (item) => {
    if (item.onClick) {
      item.onClick();
    } else if (item.path) {
      navigate(item.path);
    } else if (onSectionChange) {
      onSectionChange(item.section);
    }
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
