import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Cpu, BadgePoundSterling, Gift, Briefcase, Rocket, UserPlus, LogIn, LayoutDashboard, LogOut, User, Key } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";


const TopInfoBar = () => {
    const { t } = useTranslation();
    const { toast } = useToast();
    const navigate = useNavigate();
    const [companyUser, setCompanyUser] = useState(() => getCompanyUser());
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
    const [loggingOut, setLoggingOut] = useState(false);

    // Keep login state in sync across tabs / when returning to this tab.
    useEffect(() => {
      const refreshUser = () => setCompanyUser(getCompanyUser());
      window.addEventListener('storage', refreshUser);
      window.addEventListener('focus', refreshUser);
      return () => {
        window.removeEventListener('storage', refreshUser);
        window.removeEventListener('focus', refreshUser);
      };
    }, []);

    // Ask for confirmation before logging out.
    const handleLogout = () => setShowLogoutConfirm(true);

    const confirmLogout = async () => {
      try {
        setLoggingOut(true);
        await logoutCompany();
        setCompanyUser(null);
        setShowLogoutConfirm(false);
        navigate('/company/login');
      } finally {
        setLoggingOut(false);
      }
    };

    const infoItems = [
      {
        icon: Rocket,
        text: t('top_bar_startups', 'For Startups'),
        link: '/startups',
        color: 'text-blue-500',
        bg: 'bg-blue-500/10',
        toast: {
          title: t('top_bar_startups_toast_title', "🚀 Powering Innovation"),
          description: t('top_bar_startups_toast_desc', "Special programs and pricing for startups. Let's build the next big thing together!"),
        }
      },
      {
        icon: BadgePoundSterling,
        text: t('top_bar_cost', 'Value & Pricing'),
        link: '/value-and-pricing',
        color: 'text-green-500',
        bg: 'bg-green-500/10',
        toast: {
          title: t('top_bar_cost_toast_title', "💰 Unbeatable Value"),
          description: t('top_bar_cost_toast_desc', "Our managed model provides top-tier talent at rates lower than traditional freelancers. See how we provide more for less!"),
        }
      },
      {
        icon: Cpu,
        text: t('top_bar_ai_driven', '78% Projects are AI Driven'),
        link: '/agentic-ai-models',
        color: 'text-pink-500',
        bg: 'bg-pink-500/10',
        toast: {
          title: t('top_bar_ai_driven_toast_title', "🤖 The AI Revolution"),
          description: t('top_bar_ai_driven_toast_desc', "Discover how our Agentic AI models are transforming industries and delivering unparalleled results."),
        }
      },
      {
        icon: UserPlus,
        text: 'Build Employees',
        link: '/start-project',
        color: 'text-teal-500',
        bg: 'bg-teal-500/10',
        toast: {
          title: "🤖 Build Your AI Workforce",
          description: "Create autonomous AI agents to handle tasks and drive growth. Let's build your digital employees!",
        }
      },
      {
        icon: Gift,
        text: t('top_bar_referrals', 'Refer & Earn'),
        link: '/referrals',
        color: 'text-orange-500',
        bg: 'bg-orange-500/10',
        toast: {
          title: t('top_bar_referrals_toast_title', "🎉 Refer & Earn!"),
          description: t('top_bar_referrals_toast_desc', "Love our service? Share it with your network and earn significant rewards. Check out our referral program!"),
        }
      },
      {
        icon: Briefcase,
        text: t('top_bar_careers', 'Apply for Jobs'),
        link: '/careers/apply',
        color: 'text-purple-500',
        bg: 'bg-purple-500/10',
        toast: {
          title: t('top_bar_careers_toast_title', "🚀 Join Our Team!"),
          description: t('top_bar_careers_toast_desc', "Looking for your next big challenge? Explore our open positions and become part of our elite global talent network!"),
        }
      }
    ];

  // Auth-aware cells appended after the info items.
  // Logged out → "Company Login" cell. Logged in → a profile icon that opens
  // a dropdown with the email, Dashboard, and Logout (rendered separately).
  const authItems = companyUser
    ? []
    : [
        {
          icon: LogIn,
          text: t('top_bar_company_login', 'Company Login'),
          link: '/company/login',
          color: 'text-violet-400',
          bg: 'bg-violet-500/10',
        },
      ];

  const allItems = [...infoItems, ...authItems];
  // The profile dropdown occupies one extra grid column when logged in.
  const columnCount = allItems.length + (companyUser ? 1 : 0);

  const handleClick = (e, item) => {
    // Items without toast/link (e.g. Logout) run their own handler.
    if (item.onClick) {
      e.preventDefault();
      item.onClick();
      return;
    }
    if (item.toast) toast(item.toast);
    if (item.link.startsWith('/#')) {
      e.preventDefault();
      const id = item.link.substring(2);
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
        e.preventDefault();
        navigate(item.link);
    }
  };

  return (
    <>
    <motion.div
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}
      className="bg-card border-b border-border hidden md:block"
    >
      <div className="container mx-auto px-4 md:px-6">
        <div
          className="grid grid-cols-1 gap-px bg-border"
          style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
        >
          {allItems.map((item, index) => (
            <Link
              to={item.link || '#'}
              key={index}
              onClick={(e) => handleClick(e, item)}
              className="group bg-card hover:bg-secondary/50 transition-colors duration-300"
            >
              <div className="flex items-center justify-center text-center p-3 gap-3">
                <div className={`flex-shrink-0 p-2 rounded-full ${item.bg} transition-transform duration-300 group-hover:scale-110`}>
                  <item.icon className={`h-5 w-5 ${item.color}`} />
                </div>
                <p className="text-sm font-medium text-muted-foreground group-hover:text-primary transition-colors duration-300 truncate">
                  {item.text}
                </p>
              </div>
            </Link>
          ))}

          {companyUser && (
            <DropdownMenu>
              <DropdownMenuTrigger className="group bg-card hover:bg-secondary/50 transition-colors duration-300 focus:outline-none">
                <div className="flex items-center justify-center text-center p-3 gap-3">
                  <div className="flex-shrink-0 p-2 rounded-full bg-primary/10 transition-transform duration-300 group-hover:scale-110">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <p className="text-sm font-medium text-muted-foreground group-hover:text-primary transition-colors duration-300 truncate">
                    {t('top_bar_profile', 'Profile')}
                  </p>
                </div>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="font-normal">
                  <p className="text-sm font-medium text-foreground truncate">
                    {companyUser.fullName || companyUser.companyName || 'Company'}
                  </p>
                  {companyUser.email && (
                    <p className="text-xs text-muted-foreground truncate">{companyUser.email}</p>
                  )}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link to="/company/profile" className="cursor-pointer">
                    <User className="mr-2 h-4 w-4" />
                    {t('top_bar_profile', 'Profile')}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link to="/company/dashboard" className="cursor-pointer">
                    <LayoutDashboard className="mr-2 h-4 w-4" />
                    {t('top_bar_dashboard', 'Dashboard')}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link to="/company/settings/api-keys" className="cursor-pointer">
                    <Key className="mr-2 h-4 w-4" />
                    {t('top_bar_api_keys', 'API Keys')}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={handleLogout}
                  className="cursor-pointer text-red-500 focus:text-red-500"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  {t('top_bar_logout', 'Logout')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </motion.div>

    {/* Logout confirmation */}
    <Dialog open={showLogoutConfirm} onOpenChange={setShowLogoutConfirm}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Log out?</DialogTitle>
          <DialogDescription>
            Are you sure you want to log out of your company account?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowLogoutConfirm(false)} disabled={loggingOut}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={confirmLogout} disabled={loggingOut}>
            <LogOut className="mr-2 h-4 w-4" />
            {loggingOut ? 'Logging out...' : 'Log out'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
};

export default TopInfoBar;