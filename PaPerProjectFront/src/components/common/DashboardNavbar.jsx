import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { LogOut, Building2, BrainCircuit, UserCheck, Megaphone, Menu } from 'lucide-react';

const DashboardNavbar = ({
  icon: Icon,
  title,
  subtitle,
  user,
  userRole,
  showNavTabs = false,
  activeSection,
  onSectionChange,
  onLogout,
  navItems = [],
}) => {
  const navigate = useNavigate();

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
    <header
      className="border-b border-white/[0.08]"
      style={{
        background: 'linear-gradient(180deg, #0a0a14 0%, #0d0b1a 40%, #110e1f 100%)',
      }}
    >
      <div className="container mx-auto px-3 sm:px-4 py-3 sm:py-4">
        {/* Header Row */}
        <div className="flex items-center justify-between mb-3 sm:mb-4 gap-2">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            {Icon && <Icon className="h-6 w-6 sm:h-8 sm:w-8 text-violet-400 shrink-0" />}
            <div className="min-w-0">
              <h1 className="text-lg sm:text-2xl font-bold truncate text-white">{title}</h1>
              {subtitle && (
                <p className="text-xs sm:text-sm text-white/50 truncate">{subtitle}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-4 shrink-0">
            {user && (
              <div className="text-right hidden sm:block">
                <p className="text-sm font-medium truncate max-w-[150px] text-white/80">{user.email || user.fullName || user.username}</p>
                {userRole && (
                  <p className="text-xs text-white/40">{userRole}</p>
                )}
              </div>
            )}
            <Button
              variant="outline"
              onClick={onLogout}
              size="sm"
              className="h-8 sm:h-9 px-2 sm:px-3 border-white/15 text-white/80 hover:text-white hover:bg-white/10 hover:border-white/25 bg-transparent"
            >
              <LogOut className="h-4 w-4 sm:mr-2" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
          </div>
        </div>
        {/* Navigation Tabs - Horizontal Scroll */}
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
  );
};

export default DashboardNavbar;

