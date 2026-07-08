import React, { useState, useEffect } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Layers, Menu, X, BrainCircuit, ChevronDown, Wrench, ArrowRight, Briefcase, Wand2, HeartHandshake as Handshake, BookOpen, Users, Video, GraduationCap, LifeBuoy, FileText, Sparkles, Cpu, Lightbulb, Rocket, LogIn, LogOut, LayoutDashboard, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import LanguageSwitcher from '@/components/layout/LanguageSwitcher';
import Logo from '@/components/layout/Logo';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { cn } from '@/lib/utils';
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
  DropdownMenuGroup
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/components/ui/use-toast";

const industries = [
  { name: 'Agriculture', slug: 'agriculture' },
  { name: 'Automotive', slug: 'automotive' },
  { name: 'Aviation', slug: 'aviation' },
  { name: 'Banking', slug: 'banking' },
  { name: 'Biotechnology & Life Sciences', slug: 'biotechnology-life-sciences' },
  { name: 'Construction', slug: 'construction' },
  { name: 'Education & EdTech', slug: 'education-edtech' },
  { name: 'Entertainment', slug: 'entertainment' },
  { name: 'Finance', slug: 'finance' },
  { name: 'Fintech', slug: 'fintech' },
  { name: 'Healthcare', slug: 'healthcare' },
  { name: 'Insurance', slug: 'insurance' },
  { name: 'IT & Consulting Solutions', slug: 'it-consulting-solutions' },
  { name: 'Labor Market', slug: 'labor-market' },
  { name: 'Martech', slug: 'martech' },
  { name: 'Oil and Gas', slug: 'oil-and-gas' },
  { name: 'Pharmaceuticals', slug: 'pharmaceuticals' },
  { name: 'Public Sector & Government', slug: 'public-sector-government' },
  { name: 'Real Estate', slug: 'real-estate' },
  { name: 'Research & Development (R&D)', slug: 'research-development' },
  { name: 'Retail', slug: 'retail' },
  { name: 'Supply Chain', slug: 'supply-chain' },
  { name: 'Telecommunications', slug: 'telecommunications' },
  { name: 'Utilities & Clean Energy', slug: 'utilities-clean-energy' },
];

const solutions = [
    { to: '/features', title: 'nav_features_main', default: 'All Features' },
    { to: '/solutions/it-consulting-solutions', title: 'nav_it_solutions', default: 'IT & Solutions' },
    { to: '/solutions/ai-automations', title: 'nav_ai_automations', default: 'AI & Automations' },
    { to: '/solutions/sell-buy-businesses', title: 'nav_sell_buy_businesses', default: 'Sell & Buy Businesses' },
    { to: '/hire-talent', title: 'nav_hire_talent', default: 'Hire Talent' },
    { to: '/careers', title: 'nav_careers', default: 'Careers & Jobs' },
    { to: '/white-label-products', title: 'nav_white_label_products', default: 'White-Label Products' },
    { to: '/expert-advice', title: 'nav_expert_advice', default: 'Expert Advice' },
];

const resources = {
  learn: [
    { to: '/blog', title: 'Blog', icon: BookOpen },
    { to: '/resources/customer-stories', title: 'Customer Stories', icon: Users },
    { to: '/resources/featured-videos', title: 'Featured Videos', icon: Video },
    { to: '/resources/academy', title: 'Academy', icon: GraduationCap },
  ],
  agenticAI: [
    { to: '/resources/agentic-ai-explained#what-is-agentic-ai', title: 'What is agentic AI', icon: Lightbulb },
    { to: '/resources/agentic-ai-explained#what-does-agentic-mean', title: 'What does agentic mean', icon: Sparkles },
    { to: '/resources/agentic-ai-explained#ai-vs-agentic-ai', title: 'AI Agent vs Agentic AI', icon: Cpu },
    { to: '/resources/agentic-ai-explained#how-to-build', title: 'How to build an AI Agent', icon: Wrench },
    { to: '/resources/agentic-ai-explained#tools', title: 'Agentic AI Tools', icon: Briefcase },
    { to: '/resources/agentic-ai-explained#frameworks', title: 'Agentic Frameworks', icon: Layers },
    { to: '/resources/agentic-ai-explained#use-cases', title: 'Business Use Cases', icon: BrainCircuit },
  ],
  support: [
    { to: '/resources/help-docs', title: 'Help Docs', icon: FileText },
    { to: '/resources/partners', title: 'Partners', icon: Handshake },
    { to: '/resources/community', title: 'Community', icon: Users },
    { to: '/contact', title: 'Support', icon: LifeBuoy },
  ]
};

const ListItem = React.forwardRef(({ className, title, to, children, ...props }, ref) => {
  return (
    <li>
      <NavigationMenuLink asChild>
        <Link
          to={to}
          ref={ref}
          className={cn(
            "block select-none space-y-1 rounded-md p-3 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground",
            className
          )}
          {...props}
        >
          <div className="text-sm font-medium leading-none">{title}</div>
          <p className="line-clamp-2 text-sm leading-snug text-muted-foreground">
            {children}
          </p>
        </Link>
      </NavigationMenuLink>
    </li>
  );
});
ListItem.displayName = "ListItem";

const ResourceListItem = ({ to, title, icon: Icon }) => {
    const { toast } = useToast();
    const navigate = useNavigate();
    const isPlaceholder = to.startsWith('/resources/') && !to.includes('agentic-ai-explained') && to !== '/blog';

    const handleClick = (e) => {
        if (isPlaceholder) {
            e.preventDefault();
            toast({
                title: "🚧 Coming Soon!",
                description: "This resource page is under construction. Check back soon!",
            });
        } else if (to.includes('#')) {
            e.preventDefault();
            const [path, hash] = to.split('#');
            navigate(path);
            setTimeout(() => {
                const element = document.getElementById(hash);
                if (element) {
                    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 100); // Small delay to allow page navigation
        } else {
            // Default navigation for links like /blog
        }
    };

    return (
        <Link
            to={to.split('#')[0]} // Navigate to path without hash for router
            onClick={handleClick}
            className="flex items-center gap-3 rounded-md p-2 text-sm transition-colors hover:bg-accent"
        >
            <Icon className="h-4 w-4 text-muted-foreground" />
            <span>{title}</span>
        </Link>
    );
};


const NavItem = ({ to, label, onClick, isHome = false }) => {
  return (
    <NavLink
      to={to}
      end={isHome}
      onClick={onClick}
      className="relative text-lg md:text-base font-medium text-foreground transition-colors duration-300 hover:text-primary group"
    >
      {({ isActive }) => (
        <>
          <span>{label}</span>
          {isActive ? (
            <motion.div
              className="absolute bottom-[-4px] left-0 right-0 h-0.5 bg-primary"
              layoutId="underline"
              initial={false}
            />
          ) : (
            <div className="absolute bottom-[-4-px] left-0 right-0 h-0.5 bg-primary origin-center scale-x-0 transition-transform duration-300 group-hover:scale-x-100" />
          )}
        </>
      )}
    </NavLink>
  );
};

const Header = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [companyUser, setCompanyUser] = useState(() => getCompanyUser());

  const navLinks = [
    { to: '/', label: t('nav_home', 'Home'), isHome: true },
    { to: '/how-it-works', label: t('nav_how_it_works') },
    { to: '/pricing', label: t('nav_pricing', 'Pricing') },
    { to: '/contact', label: t('nav_contact') },
  ];

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Keep the login/profile state in sync if auth changes in another tab or
  // when the user returns to this tab (e.g. after logging in elsewhere).
  useEffect(() => {
    const refreshUser = () => setCompanyUser(getCompanyUser());
    window.addEventListener('storage', refreshUser);
    window.addEventListener('focus', refreshUser);
    return () => {
      window.removeEventListener('storage', refreshUser);
      window.removeEventListener('focus', refreshUser);
    };
  }, []);

  const handleLogout = async () => {
    await logoutCompany();
    setCompanyUser(null);
    setIsOpen(false);
    navigate('/company/login');
  };

  return (
    <header className={`sticky top-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-background/80 backdrop-blur-xl border-b' : 'bg-transparent'}`}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-20 items-center justify-between">
          <Link to="/" onClick={() => setIsOpen(false)} className="-ml-2 sm:-ml-4">
            <Logo imgClassName="h-11 w-11" textSizeClassName="text-xl" className="gap-3" />
          </Link>
          <nav className="hidden md:block">
            <NavigationMenu>
              <NavigationMenuList>
                {navLinks.map((link) => (
                  <NavigationMenuItem key={link.to}>
                    <Link to={link.to}>
                      <NavigationMenuLink className={navigationMenuTriggerStyle()}>
                        {link.label}
                      </NavigationMenuLink>
                    </Link>
                  </NavigationMenuItem>
                ))}
                <NavigationMenuItem>
                  <NavigationMenuTrigger>{t('nav_industries', 'Industries')}</NavigationMenuTrigger>
                  <NavigationMenuContent>
                    <div className="grid w-[600px] grid-cols-3 gap-4 p-4">
                      <div className="col-span-1 flex flex-col justify-between">
                        <div>
                          <h3 className="font-heading text-lg font-semibold text-primary">{t('nav_industries', 'Industries')}</h3>
                          <p className="mt-2 text-sm text-muted-foreground">
                            {t('industries_dropdown_desc', 'Specialized solutions for your sector. Experience we have.')}
                          </p>
                        </div>
                        <Button asChild variant="ghost" className="justify-start p-0 h-auto">
                          <Link to="/industries" className="text-sm font-semibold text-primary hover:underline">
                            {t('industries_dropdown_all', 'All Industries')} <ArrowRight className="ml-1 h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                      <ul className="col-span-2 grid grid-cols-2 gap-2">
                        {industries.slice(0, 16).map((industry) => (
                          <ListItem
                            key={industry.name}
                            title={t(`industry_${industry.slug}`, industry.name)}
                            to={`/industries/${industry.slug}`}
                          />
                        ))}
                      </ul>
                    </div>
                  </NavigationMenuContent>
                </NavigationMenuItem>
                <NavigationMenuItem>
                  <NavigationMenuTrigger>{t('nav_solutions', 'Solutions')}</NavigationMenuTrigger>
                  <NavigationMenuContent>
                    <ul className="grid w-[400px] gap-3 p-4 md:w-[500px] md:grid-cols-2 lg:w-[600px] ">
                      {solutions.map((solution) => (
                        <ListItem key={solution.to} to={solution.to} title={t(solution.title, solution.default)} />
                      ))}
                    </ul>
                  </NavigationMenuContent>
                </NavigationMenuItem>
                <NavigationMenuItem>
                  <NavigationMenuTrigger>Resources</NavigationMenuTrigger>
                  <NavigationMenuContent>
                    <div className="grid w-[650px] grid-cols-3 gap-6 p-6">
                      <div className="flex flex-col gap-4">
                        <h3 className="text-sm font-semibold text-foreground">Learn</h3>
                        {resources.learn.map(item => <ResourceListItem key={item.title} {...item} />)}
                      </div>
                      <div className="flex flex-col gap-4">
                        <h3 className="text-sm font-semibold text-foreground">Agentic AI</h3>
                        {resources.agenticAI.map(item => <ResourceListItem key={item.title} {...item} />)}
                      </div>
                      <div className="flex flex-col gap-4">
                        <h3 className="text-sm font-semibold text-foreground">Connect</h3>
                        {resources.support.map(item => <ResourceListItem key={item.title} {...item} />)}
                      </div>
                    </div>
                  </NavigationMenuContent>
                </NavigationMenuItem>
              </NavigationMenuList>
            </NavigationMenu>
          </nav>
          <div className="hidden md:flex items-center gap-2">
            <Button variant="ghost" asChild>
                <Link to="/apply-for-projects">
                  Apply for Projects
                </Link>
            </Button>
            <Button asChild>
              <Link to="/start-project">
                 <Rocket className="mr-2 h-4 w-4" />
                {t('nav_post_project_cta', 'Post Project')}
              </Link>
            </Button>
            <LanguageSwitcher />
          </div>
          <div className="md:hidden flex items-center gap-2">
            <LanguageSwitcher />
            <button onClick={() => setIsOpen(!isOpen)} className="text-foreground">
              {isOpen ? <X size={28} /> : <Menu size={28} />}
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden overflow-hidden bg-background/95 backdrop-blur-lg border-b"
          >
            <div className="px-4 pb-8 pt-4">
              <nav>
                <ul className="flex flex-col items-center space-y-6">
                  {navLinks.map((link) => (
                    <li key={link.to}>
                      <NavItem to={link.to} label={link.label} onClick={() => setIsOpen(false)} isHome={link.isHome} />
                    </li>
                  ))}
                   <li>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="flex items-center text-lg md:text-base font-medium text-foreground transition-colors duration-300 hover:text-primary group">
                        {t('nav_industries', 'Industries')} <ChevronDown className="ml-1 h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="w-56">
                        <DropdownMenuItem asChild>
                          <Link to="/industries" onClick={() => setIsOpen(false)}>
                            {t('industries_dropdown_all', 'All Industries')}
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        {industries.slice(0, 5).map((industry) => (
                           <DropdownMenuItem asChild key={industry.slug}>
                            <Link to={`/industries/${industry.slug}`} onClick={() => setIsOpen(false)}>
                              {t(`industry_${industry.slug}`, industry.name)}
                            </Link>
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </li>
                  <li>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="flex items-center text-lg md:text-base font-medium text-foreground transition-colors duration-300 hover:text-primary group">
                        {t('nav_solutions', 'Solutions')} <ChevronDown className="ml-1 h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="w-56">
                        {solutions.map((solution) => (
                           <DropdownMenuItem asChild key={solution.to}>
                            <Link to={solution.to} onClick={() => setIsOpen(false)}>
                              {t(solution.title, solution.default)}
                            </Link>
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </li>
                  <li>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="flex items-center text-lg md:text-base font-medium text-foreground transition-colors duration-300 hover:text-primary group">
                        Resources <ChevronDown className="ml-1 h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="w-64">
                        <DropdownMenuLabel>Learn</DropdownMenuLabel>
                        {resources.learn.map(item => (
                          <DropdownMenuItem asChild key={item.title}>
                            <ResourceListItem {...item} />
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel>Agentic AI</DropdownMenuLabel>
                        {resources.agenticAI.map(item => (
                          <DropdownMenuItem asChild key={item.title}>
                           <ResourceListItem {...item} />
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel>Connect</DropdownMenuLabel>
                        {resources.support.map(item => (
                          <DropdownMenuItem asChild key={item.title}>
                            <ResourceListItem {...item} />
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </li>
                </ul>
              </nav>
              <div className="mt-8 flex flex-col items-center gap-4">
                 <Button asChild className="w-full max-w-xs">
                    <Link to="/start-project" onClick={() => setIsOpen(false)}>
                      <Rocket className="mr-2 h-4 w-4" />
                      {t('nav_post_project_cta', 'Post Project')}
                    </Link>
                  </Button>
                  <Button variant="outline" asChild className="w-full max-w-xs">
                    <Link to="/apply-for-projects" onClick={() => setIsOpen(false)}>
                      <Briefcase className="mr-2 h-4 w-4" />
                      Apply for Projects
                    </Link>
                  </Button>
                  {companyUser ? (
                    <>
                      {companyUser.email && (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground max-w-xs w-full justify-center">
                          <User className="h-4 w-4 shrink-0" />
                          <span className="truncate">{companyUser.email}</span>
                        </div>
                      )}
                      <Button variant="outline" asChild className="w-full max-w-xs">
                        <Link to="/company/dashboard" onClick={() => setIsOpen(false)}>
                          <LayoutDashboard className="mr-2 h-4 w-4" />
                          Dashboard
                        </Link>
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleLogout}
                        className="w-full max-w-xs text-red-500 hover:text-red-500"
                      >
                        <LogOut className="mr-2 h-4 w-4" />
                        Logout
                      </Button>
                    </>
                  ) : (
                    <Button variant="outline" asChild className="w-full max-w-xs">
                      <Link to="/company/login" onClick={() => setIsOpen(false)}>
                        <LogIn className="mr-2 h-4 w-4" />
                        Company Login
                      </Link>
                    </Button>
                  )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
};

export default Header;