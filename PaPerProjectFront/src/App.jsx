
import React from 'react';
    import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
    import { AuthProvider } from '@/contexts/AuthContext';
    import HomePage from '@/pages/HomePage';
    import HowItWorksPage from '@/pages/HowItWorksPage';
    import ReviewsPage from '@/pages/ReviewsPage';
    import IndustriesPage from '@/pages/IndustriesPage';
    import IndustryDetailPage from '@/pages/IndustryDetailPage';
    import ContactPage from '@/pages/ContactPage';
    import ConsultationPage from '@/pages/ConsultationPage';
    import FeaturesPage from '@/pages/FeaturesPage';
    import PricingPage from '@/pages/PricingPage';
    import HireTalentPage from '@/pages/HireTalentPage';
    import PostProjectPage from '@/pages/PostProjectPage';
    import StartProjectPage from '@/pages/StartProjectPage';
    import WhiteLabelPage from '@/pages/WhiteLabelPage';
    import ExpertAdvicePage from '@/pages/ExpertAdvicePage';
    import QuizPage from '@/pages/QuizPage';
    import PaymentOptionsPage from '@/pages/PaymentOptionsPage';
    import BlogPage from '@/pages/BlogPage';
    import BlogPostPage from '@/pages/BlogPostPage';
    import ResourcesPage from '@/pages/ResourcesPage';
    import AiAutomationsPage from '@/pages/AiAutomationsPage';
    import N8nAutomationsPage from '@/pages/N8nAutomationsPage';
    import ItSolutionsPage from '@/pages/ItSolutionsPage';
    import CareersPage from '@/pages/CareersPage';
    import AiPredictorPage from '@/pages/AiPredictorPage';
    import SellBuyBusinessesPage from '@/pages/SellBuyBusinessesPage';
    import StartupsPage from '@/pages/StartupsPage';
    import ReferralsPage from '@/pages/ReferralsPage';
    import ValueAndPricingPage from '@/pages/ValueAndPricingPage';
    import AgenticAiModelsPage from '@/pages/AgenticAiModelsPage';
    import AgenticAiResourcePage from '@/pages/AgenticAiResourcePage';
import ApplyForProjectsPage from '@/pages/ApplyForProjectsPage';
import LoginPage from '@/pages/LoginPage';
import AdminDashboardPage from '@/pages/AdminDashboardPage';
import CompanyRegisterPage from '@/pages/CompanyRegisterPage';
import CompanyLoginPage from '@/pages/CompanyLoginPage';
import CompanyDashboardPage from '@/pages/CompanyDashboardPage';
import ProjectManagerDashboardPage from '@/pages/ProjectManagerDashboardPage';
import MarketingAgentPage from '@/pages/MarketingAgentPage';
import RecruitmentAgentPage from '@/pages/RecruitmentAgentPage';
import ProtectedRoute from '@/components/common/ProtectedRoute';
import PublicLayout from '@/components/layout/PublicLayout';
import ScrollToTop from '@/components/layout/ScrollToTop';
import { Toaster } from "@/components/ui/toaster";
import { useTranslation } from 'react-i18next';
    
    const AppContent = () => {
      const { i18n } = useTranslation();
      const location = useLocation();
    
      React.useEffect(() => {
        document.documentElement.lang = i18n.language;
        document.documentElement.dir = i18n.dir(i18n.language);
      }, [i18n, i18n.language]);
    
      return (
        <>
          <ScrollToTop />
          <Routes location={location}>
            {/* Admin routes without header/footer */}
            <Route path="/login" element={<LoginPage />} />
            <Route 
              path="/admin/dashboard" 
              element={
                <ProtectedRoute requireAdmin={true}>
                  <AdminDashboardPage />
                </ProtectedRoute>
              } 
            />
            
            {/* Company routes without header/footer */}
            <Route path="/company/register" element={<CompanyRegisterPage />} />
            <Route path="/company/login" element={<CompanyLoginPage />} />
            <Route path="/company/dashboard" element={<CompanyDashboardPage />} />
            
            {/* Project Manager routes without header/footer */}
            <Route 
              path="/project-manager/dashboard" 
              element={
                <ProtectedRoute requireProjectManager={true}>
                  <ProjectManagerDashboardPage />
                </ProtectedRoute>
              } 
            />
            
            {/* Marketing Agent routes without header/footer */}
            <Route path="/marketing/dashboard" element={<MarketingAgentPage />} />
            
            {/* Recruitment Agent routes without header/footer */}
            <Route path="/recruitment/dashboard" element={<RecruitmentAgentPage />} />
            
            {/* Public routes with header/footer */}
            <Route path="/" element={<PublicLayout><HomePage /></PublicLayout>} />
            <Route path="/how-it-works" element={<PublicLayout><HowItWorksPage /></PublicLayout>} />
            <Route path="/industries" element={<PublicLayout><IndustriesPage /></PublicLayout>} />
            <Route path="/industries/:slug" element={<PublicLayout><IndustryDetailPage /></PublicLayout>} />
            <Route path="/reviews" element={<PublicLayout><ReviewsPage /></PublicLayout>} />
            <Route path="/contact" element={<PublicLayout><ContactPage /></PublicLayout>} />
            <Route path="/consultation" element={<PublicLayout><ConsultationPage /></PublicLayout>} />
            <Route path="/features" element={<PublicLayout><FeaturesPage /></PublicLayout>} />
            <Route path="/pricing" element={<PublicLayout><PricingPage /></PublicLayout>} />
            <Route path="/hire-talent" element={<PublicLayout><HireTalentPage /></PublicLayout>} />
            <Route path="/hire-talent/request" element={<PublicLayout><HireTalentPage scrollToForm={true} /></PublicLayout>} />
            <Route path="/post-project" element={<PublicLayout><PostProjectPage /></PublicLayout>} />
            <Route path="/start-project" element={<PublicLayout><StartProjectPage /></PublicLayout>} />
            <Route path="/white-label-products" element={<PublicLayout><WhiteLabelPage /></PublicLayout>} />
            <Route path="/expert-advice" element={<PublicLayout><ExpertAdvicePage /></PublicLayout>} />
            <Route path="/quiz" element={<PublicLayout><QuizPage /></PublicLayout>} />
            <Route path="/payment-options" element={<PublicLayout><PaymentOptionsPage /></PublicLayout>} />
            <Route path="/resources" element={<PublicLayout><ResourcesPage /></PublicLayout>} />
            <Route path="/blog" element={<PublicLayout><BlogPage /></PublicLayout>} />
            <Route path="/blog/:slug" element={<PublicLayout><BlogPostPage /></PublicLayout>} />
            <Route path="/solutions/ai-automations" element={<PublicLayout><AiAutomationsPage /></PublicLayout>} />
            <Route path="/solutions/n8n-automations" element={<PublicLayout><N8nAutomationsPage /></PublicLayout>} />
            <Route path="/solutions/it-consulting-solutions" element={<PublicLayout><ItSolutionsPage /></PublicLayout>} />
            <Route path="/solutions/sell-buy-businesses" element={<PublicLayout><SellBuyBusinessesPage /></PublicLayout>} />
            <Route path="/careers" element={<PublicLayout><CareersPage /></PublicLayout>} />
            <Route path="/careers/apply" element={<PublicLayout><CareersPage scrollToJobs={true} /></PublicLayout>} />
            <Route path="/ai-predictor" element={<PublicLayout><AiPredictorPage /></PublicLayout>} />
            <Route path="/startups" element={<PublicLayout><StartupsPage /></PublicLayout>} />
            <Route path="/referrals" element={<PublicLayout><ReferralsPage /></PublicLayout>} />
            <Route path="/value-and-pricing" element={<PublicLayout><ValueAndPricingPage /></PublicLayout>} />
            <Route path="/agentic-ai-models" element={<PublicLayout><AgenticAiModelsPage /></PublicLayout>} />
            <Route path="/resources/agentic-ai-explained" element={<PublicLayout><AgenticAiResourcePage /></PublicLayout>} />
            <Route path="/apply-for-projects" element={<PublicLayout><ApplyForProjectsPage /></PublicLayout>} />
          </Routes>
          <Toaster />
        </>
      );
    }
    
    function App() {
      return (
        <AuthProvider>
          <Router>
            <AppContent />
          </Router>
        </AuthProvider>
      );
    }
    
    export default App;
