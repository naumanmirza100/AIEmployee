
import React from 'react';
import { Helmet } from 'react-helmet';
import HeroSection from '@/components/how-it-works/HeroSection';
import ProblemSection from '@/components/how-it-works/ProblemSection';
import HowItWorksProcess from '@/components/how-it-works/HowItWorksProcess';
import WhyItWorksSection from '@/components/how-it-works/WhyItWorksSection';
import ComparisonTable from '@/components/how-it-works/ComparisonTable';
import FaqSection from '@/components/how-it-works/FaqSection';
import FinalCTASection from '@/components/how-it-works/FinalCTASection';
import ResultsTeamSection from '@/components/how-it-works/ResultsTeamSection';
import { useTranslation } from 'react-i18next';

const HowItWorksPage = () => {
  const { t } = useTranslation();
  return (
    <div className="bg-background overflow-x-hidden">
      <Helmet>
        <title>{t('title_how_it_works', 'How It Works - From Idea to Invoice, We Handle It All')} | Pay Per Project</title>
        <meta name="description" content={t('meta_desc_how_it_works', 'Discover our streamlined process for turning your project ideas into reality. We manage everything from scope and pricing to team assignment and delivery, guaranteed.')} />
      </Helmet>
      
      <HeroSection />
      <ProblemSection />
      <HowItWorksProcess />
      <WhyItWorksSection />
      <ResultsTeamSection />
      <ComparisonTable />
      <FaqSection />
      <FinalCTASection />
    </div>
  );
};

export default HowItWorksPage;
