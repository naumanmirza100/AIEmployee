
import React, { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Helmet } from 'react-helmet';
import Hero from '@/components/home/Hero';
import TrustBadges from '@/components/home/TrustBadges';
import KeyFeatures from '@/components/home/KeyFeatures';
import SocialProof from '@/components/home/SocialProof';
import Faq from '@/components/home/Faq';
import { useTranslation } from 'react-i18next';
import ZeroFees from '@/components/home/ZeroFees';
import CompanyPitch from '@/components/home/CompanyPitch';
import BenchmarkSlider from '@/components/home/BenchmarkSlider';
import ReferralProgram from '@/components/home/ReferralProgram';
import QuickValueGrid from '@/components/home/QuickValueGrid';
import UniqueBenefits from '@/components/home/UniqueBenefits';
import HowItWorksSection from '@/components/home/HowItWorksSection';
import SolutionsShowcase from '@/components/home/SolutionsShowcase';
import AiPredictorCta from '@/components/home/AiPredictorCta';
import ModuleCardsSection from '@/components/home/ModuleCardsSection';

const HomePage = () => {
  const { t } = useTranslation();
  const { hash } = useLocation();

  useEffect(() => {
    if (!hash) return;
    // The hash can carry a query string (e.g. "#ai-modules?agent=exec_meeting_agent").
    // Strip anything after the id and look up by id, so an invalid CSS selector
    // like "#ai-modules?agent=..." doesn't throw and blank the whole page.
    const id = hash.replace(/^#/, '').split(/[?&]/)[0];
    if (!id) return;
    const el = document.getElementById(id);
    if (el) {
      // Delay so the section is mounted before scroll
      setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, [hash]);

  return (
    <>
      <Helmet>
        <title>{t('home_page_title', 'Pay Per Project | Fully Managed Project Delivery')}</title>
        <meta name="description" content={t('home_page_meta_description', 'The world\'s first fully managed project delivery platform. We scope, assign, and deliver your project with a dedicated team and project manager.')} />
      </Helmet>
      <div className="flex flex-col">
        <Hero />
        <QuickValueGrid />
        <HowItWorksSection />
        <TrustBadges />
        <CompanyPitch />
        <KeyFeatures />
        <UniqueBenefits />
        <ModuleCardsSection />
        <SolutionsShowcase />
        <BenchmarkSlider />
        <AiPredictorCta />
        <SocialProof />
        <ZeroFees />
        <ReferralProgram />
        <Faq />
      </div>
    </>
  );
};

export default HomePage;
