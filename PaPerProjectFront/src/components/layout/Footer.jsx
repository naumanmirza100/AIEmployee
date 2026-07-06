
import React from 'react';
import { Link } from 'react-router-dom';
import { Twitter, Github, Linkedin } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { useTranslation } from 'react-i18next';
import Logo from '@/components/layout/Logo';

const Footer = () => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const year = new Date().getFullYear();

  const handleSocialClick = () => {
    toast({
      title: "🚧 Feature in Progress!",
      description: "Our social media pages are coming soon. Follow us for updates! 🚀",
    });
  };

  return (
    <footer className="border-t bg-card">
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="flex flex-col items-center text-center lg:items-start lg:text-left">
            <Link to="/">
              <Logo imgClassName="h-11 w-11" textSizeClassName="text-xl" className="gap-3" />
            </Link>
            <p className="mt-4 max-w-xs text-muted-foreground">
              {t('footer_platform_description')}
            </p>
            <div className="mt-8 flex gap-6">
              <button onClick={handleSocialClick} className="text-muted-foreground transition hover:text-primary"><span className="sr-only">Twitter</span><Twitter className="h-6 w-6" /></button>
              <button onClick={handleSocialClick} className="text-muted-foreground transition hover:text-primary"><span className="sr-only">GitHub</span><Github className="h-6 w-6" /></button>
              <button onClick={handleSocialClick} className="text-muted-foreground transition hover:text-primary"><span className="sr-only">LinkedIn</span><Linkedin className="h-6 w-6" /></button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:col-span-2">
            <div className="text-center sm:text-left">
              <p className="text-lg font-medium text-foreground">{t('footer_product')}</p>
              <ul className="mt-8 space-y-4 text-sm">
                <li><Link to="/features" className="text-muted-foreground transition hover:text-primary">{t('footer_features')}</Link></li>
                <li><Link to="/how-it-works" className="text-muted-foreground transition hover:text-primary">{t('footer_how_it_works')}</Link></li>
                <li><Link to="/industries" className="text-muted-foreground transition hover:text-primary">{t('footer_industries', 'Industries')}</Link></li>
                <li><Link to="/pricing" className="text-muted-foreground transition hover:text-primary">{t('footer_pricing', 'Pricing')}</Link></li>
              </ul>
            </div>
            <div className="text-center sm:text-left">
              <p className="text-lg font-medium text-foreground">{t('footer_company')}</p>
              <ul className="mt-8 space-y-4 text-sm">
                <li><button onClick={() => toast({ title: 'Coming Soon!' })} className="text-muted-foreground transition hover:text-primary">{t('footer_about_us')}</button></li>
                <li><button onClick={() => toast({ title: 'Coming Soon!' })} className="text-muted-foreground transition hover:text-primary">{t('footer_careers')}</button></li>
                <li><Link to="/contact" className="text-muted-foreground transition hover:text-primary">{t('footer_contact')}</Link></li>
                <li><Link to="/blog" className="text-muted-foreground transition hover:text-primary">{t('footer_blog', 'Blog')}</Link></li>
                <li><Link to="/reviews" className="text-muted-foreground transition hover:text-primary">{t('footer_reviews', 'Reviews')}</Link></li>
              </ul>
            </div>
            <div className="text-center sm:text-left">
              <p className="text-lg font-medium text-foreground">{t('footer_legal')}</p>
              <ul className="mt-8 space-y-4 text-sm">
                <li>
                  <button
                    onClick={() => window.open('/PayPerProject_Documentation.html', '_blank')}
                    className="text-muted-foreground transition hover:text-primary"
                  >
                    {t('footer_terms')}
                  </button>
                </li>
                <li><button onClick={() => toast({ title: 'Coming Soon!' })} className="text-muted-foreground transition hover:text-primary">{t('footer_privacy')}</button></li>
                <li><button onClick={() => toast({ title: 'Coming Soon!' })} className="text-muted-foreground transition hover:text-primary">{t('footer_cookies')}</button></li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-12 border-t pt-8 flex flex-col sm:flex-row justify-between items-center text-center sm:text-left">
          <p className="text-sm text-muted-foreground">
            {t('footer_copyright', { year })}
          </p>
          <p className="text-sm text-muted-foreground mt-4 sm:mt-0">
            <Link to="https://www.laskontech.com/" target="_blank" rel="noopener noreferrer" className="hover:text-primary transition-colors">
              A product of Laskon Technologies
            </Link>
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
