import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { LogOut, Building2, BrainCircuit, UserCheck, Megaphone } from 'lucide-react';

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
    <header className="border-b bg-card">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {Icon && <Icon className="h-8 w-8 text-primary" />}
            <div>
              <h1 className="text-2xl font-bold">{title}</h1>
              {subtitle && (
                <p className="text-sm text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {user && (
              <div className="text-right">
                <p className="text-sm font-medium">{user.email || user.fullName || user.username}</p>
                {userRole && (
                  <p className="text-xs text-muted-foreground">{userRole}</p>
                )}
              </div>
            )}
            <Button variant="outline" onClick={onLogout}>
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
        {/* Navigation Tabs */}
        {showNavTabs && navItems.length > 0 && (
          <div className="flex gap-2 border-t pt-4">
            {navItems.map((item) => {
              const isActive = item.section === activeSection;
              return (
                <Button
                  key={item.section || item.path || item.label}
                  variant={isActive ? 'default' : 'ghost'}
                  onClick={() => handleNavClick(item)}
                  className="flex items-center gap-2"
                >
                  {item.icon && <item.icon className="h-4 w-4" />}
                  {item.label}
                </Button>
              );
            })}
          </div>
        )}
      </div>
    </header>
  );
};

export default DashboardNavbar;

