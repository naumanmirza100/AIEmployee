
import React from 'react';
    import { BrowserRouter as Router, Routes, Route, useLocation, Navigate } from 'react-router-dom';
    import { AuthProvider } from '@/contexts/AuthContext';
    import { BackgroundUploadProvider } from '@/components/shared/BackgroundUploadManager';
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
import SuperAdminApiKeysPage from '@/pages/SuperAdminApiKeysPage';
import CompanyRegisterPage from '@/pages/CompanyRegisterPage';
import CompanyLoginPage from '@/pages/CompanyLoginPage';
import CompanySignupPage from '@/pages/CompanySignupPage';
import CompanyProfilePage from '@/pages/CompanyProfilePage';
import CompanyDashboardPage from '@/pages/CompanyDashboardPage';
import AgentKeysSettingsPage from '@/pages/AgentKeysSettingsPage';
import NotificationsPage from '@/pages/NotificationsPage';
import ProjectManagerDashboardPage from '@/pages/ProjectManagerDashboardPage';
import UserDashboardPage from '@/pages/UserDashboardPage';
import MarketingDashboard from '@/components/marketing/MarketingDashboard';
import CampaignDetail from '@/components/marketing/CampaignDetail';
import SequenceManagementPage from '@/components/marketing/SequenceManagementPage';
import EmailSendingStatusPage from '@/components/marketing/EmailSendingStatusPage';
import EmailAccountsPage from '@/components/marketing/EmailAccountsPage';
import CandidateDetailPage from '@/pages/CandidateDetailPage';
import FrontlineDashboard from '@/components/frontline/FrontlineDashboard';
import HRDashboard from '@/components/hr/HRDashboard';
import HRMyProfilePage from '@/components/hr/HRMyProfilePage';
import ReplyDraftAgentPage from '@/pages/ReplyDraftAgentPage';
import ExecMeetingDashboard from '@/components/exec-meeting/ExecMeetingDashboard';
import AgentLayout from '@/components/common/AgentLayout';
import SDRDashboard from '@/components/ai-sdr/SDRDashboard';
import RecruitmentDashboard from '@/components/recruitment/RecruitmentDashboard';
import OperationsDashboard from '@/components/operations/OperationsDashboard';
import JobApplicationPage from '@/pages/JobApplicationPage';
import ApplicationTrackerPage from '@/pages/ApplicationTrackerPage';
import CandidatePortalPage from '@/pages/CandidatePortalPage';
import DocumentDetailPage from '@/components/operations/DocumentDetailPage';
import FrontlineEmbedChatPage from '@/pages/FrontlineEmbedChatPage';
import FrontlineEmbedFormPage from '@/pages/FrontlineEmbedFormPage';
import FrontlineEmbedCsatPage from '@/pages/FrontlineEmbedCsatPage';
import ModulePurchaseSuccessPage from '@/pages/ModulePurchaseSuccessPage';
import MeetingBookingPage from '@/pages/MeetingBookingPage';
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
            <Route
              path="/admin/api-keys"
              element={
                <ProtectedRoute requireAdmin={true}>
                  <SuperAdminApiKeysPage />
                </ProtectedRoute>
              }
            />

            {/* User Dashboard (for company-created users) */}
            <Route 
              path="/user/dashboard" 
              element={
                <ProtectedRoute>
                  <UserDashboardPage />
                </ProtectedRoute>
              } 
            />
            
            {/* Company routes without header/footer */}
            <Route path="/company/register" element={<CompanyRegisterPage />} />
            <Route path="/company/login" element={<CompanyLoginPage />} />
            <Route path="/company/signup" element={<CompanySignupPage />} />
            <Route path="/company/dashboard" element={<CompanyDashboardPage />} />
            <Route path="/company/dashboard/:tab" element={<CompanyDashboardPage />} />
            <Route path="/company/settings/api-keys" element={<AgentKeysSettingsPage />} />
            {/* Full-detail notification list — the navbar dropdown links here */}
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/company/profile" element={<CompanyProfilePage />} />
            <Route path="/company/profile/:tab" element={<CompanyProfilePage />} />
            
            {/* Project Manager routes without header/footer */}
            <Route 
              path="/project-manager/dashboard" 
              element={
                <ProtectedRoute requireProjectManager={true}>
                  <ProjectManagerDashboardPage />
                </ProtectedRoute>
              } 
            />
            
            {/* Public job application (no auth) */}
            <Route path="/jobs/apply/:jobId" element={<JobApplicationPage />} />
            {/* Public application tracker — candidate tracks status via magic link */}
            <Route path="/track-application/:token" element={<ApplicationTrackerPage />} />
            {/* Candidate portal — view all applications (email login or token) */}
            <Route path="/candidate-portal" element={<CandidatePortalPage />} />
            <Route path="/candidate-portal/:token" element={<CandidatePortalPage />} />

            {/* Candidate detail is a standalone full page (outside the agent shell) */}
            <Route path="/recruitment/candidates/:id" element={<CandidateDetailPage />} />

            {/* ── Shared agent shell: navbar + left sidebar mount ONCE; only the
                 routed content below swaps when moving between agents. ── */}
            <Route element={<AgentLayout />}>
              {/* Marketing */}
              <Route path="/marketing" element={<Navigate to="/marketing/dashboard" replace />} />
              <Route path="/marketing/dashboard" element={<MarketingDashboard />} />
              <Route path="/marketing/dashboard/campaign/:id" element={<CampaignDetail />} />
              <Route path="/marketing/dashboard/campaign/:id/sequences" element={<SequenceManagementPage />} />
              <Route path="/marketing/dashboard/campaign/:id/email-status" element={<EmailSendingStatusPage />} />
              <Route path="/marketing/dashboard/email-accounts" element={<EmailAccountsPage />} />

              {/* Recruitment */}
              <Route path="/recruitment" element={<Navigate to="/recruitment/job-descriptions" replace />} />
              <Route path="/recruitment/dashboard" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/cvprocessing" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/analytics" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/ai-graphs" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/api-tester" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/ai-interview-questions" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/saved-prompts" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/job-descriptions" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/candidates" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/interviews" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/settings" element={<Navigate to="/recruitment/settings/email" replace />} />
              <Route path="/recruitment/settings/email" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/settings/interview" element={<RecruitmentDashboard />} />
              <Route path="/recruitment/settings/qualification" element={<RecruitmentDashboard />} />

              {/* Frontline */}
              <Route path="/frontline/dashboard" element={<FrontlineDashboard />} />

              {/* HR */}
              <Route path="/hr" element={<Navigate to="/hr/dashboard" replace />} />
              <Route path="/hr/dashboard" element={<HRDashboard />} />
              <Route path="/hr/me" element={<HRMyProfilePage />} />

              {/* Operations */}
              <Route path="/operations" element={<Navigate to="/operations/documents" replace />} />
              <Route path="/operations/dashboard" element={<OperationsDashboard />} />
              <Route path="/operations/documents" element={<OperationsDashboard />} />
              <Route path="/operations/documents/:id" element={<OperationsDashboard />} />
              <Route path="/operations/summarization" element={<OperationsDashboard />} />
              <Route path="/operations/summarization/:id" element={<OperationsDashboard />} />
              <Route path="/operations/analytics" element={<OperationsDashboard />} />
              <Route path="/operations/knowledge-qa" element={<OperationsDashboard />} />
              <Route path="/operations/authoring" element={<OperationsDashboard />} />
              <Route path="/operations/notifications" element={<OperationsDashboard />} />

              {/* AI SDR */}
              <Route path="/ai-sdr" element={<Navigate to="/ai-sdr/dashboard" replace />} />
              <Route path="/ai-sdr/dashboard" element={<SDRDashboard />} />
              <Route path="/ai-sdr/leads" element={<SDRDashboard />} />
              <Route path="/ai-sdr/outreach" element={<SDRDashboard />} />
              <Route path="/ai-sdr/meetings" element={<SDRDashboard />} />
              <Route path="/ai-sdr/analytics" element={<SDRDashboard />} />
              <Route path="/ai-sdr/email-assistant" element={<SDRDashboard />} />
              <Route path="/ai-sdr/crm-sync" element={<SDRDashboard />} />
              <Route path="/ai-sdr/settings" element={<SDRDashboard />} />

              {/* AI Executive Meeting Assistant */}
              <Route path="/exec-meeting" element={<Navigate to="/exec-meeting/dashboard" replace />} />
              <Route path="/exec-meeting/dashboard" element={<ExecMeetingDashboard />} />
            </Route>

            {/* Reply Draft keeps its own standalone shell for now (large stateful
                inline workspace); it still shows the same sidebar via DashboardNavbar. */}
            <Route path="/reply-draft" element={<Navigate to="/reply-draft/dashboard" replace />} />
            <Route path="/reply-draft/dashboard" element={<ReplyDraftAgentPage />} />

            {/* Embeddable chat widget & web form (public, no auth) */}
            <Route path="/embed/chat" element={<FrontlineEmbedChatPage />} />
            <Route path="/embed/form" element={<FrontlineEmbedFormPage />} />
            <Route path="/embed/csat" element={<FrontlineEmbedCsatPage />} />

            {/* Meeting self-scheduling page (public, no auth) */}
            <Route path="/book/:token" element={<MeetingBookingPage />} />
            
            {/* Module purchase Stripe success (public) */}
            <Route path="/module-purchase-success" element={<PublicLayout><ModulePurchaseSuccessPage /></PublicLayout>} />

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
            <BackgroundUploadProvider>
              <AppContent />
            </BackgroundUploadProvider>
          </Router>
        </AuthProvider>
      );
    }
    
    export default App;
