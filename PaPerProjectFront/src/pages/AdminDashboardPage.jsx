import React, { useState, useEffect, useCallback } from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { contactService, careerService, companyService } from '@/services';
import { aiPredictorService } from '@/services/aiPredictorService';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { 
  Search, 
  Mail, 
  Phone, 
  FileText, 
  Calendar, 
  Download,
  RefreshCw,
  Eye,
  Loader2,
  MessageSquare,
  User,
  BrainCircuit,
  DollarSign,
  Clock,
  Users as UsersIcon,
  TrendingUp,
  FileCheck,
  Briefcase,
  Building2,
  Link as LinkIcon,
  Copy,
  CheckCircle2,
  Plus
} from 'lucide-react';

const AdminDashboardPage = () => {
  const [activeTab, setActiveTab] = useState('contact');
  
  // Contact Messages State
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false); // Start as false, will be true when fetching
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedMessage, setSelectedMessage] = useState(null);
  
  // AI Predictions State
  const [predictions, setPredictions] = useState([]);
  const [predictionsLoading, setPredictionsLoading] = useState(true);
  const [predictionsPagination, setPredictionsPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [predictionsSearchTerm, setPredictionsSearchTerm] = useState('');
  const [selectedPrediction, setSelectedPrediction] = useState(null);
  
  // Career Applications State
  const [applications, setApplications] = useState([]);
  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [applicationsPagination, setApplicationsPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [applicationsSearchTerm, setApplicationsSearchTerm] = useState('');
  const [applicationsStatusFilter, setApplicationsStatusFilter] = useState('');
  const [selectedApplication, setSelectedApplication] = useState(null);
  
  // Companies State
  const [companies, setCompanies] = useState([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesPagination, setCompaniesPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [companiesSearchTerm, setCompaniesSearchTerm] = useState('');
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [showCreateCompanyModal, setShowCreateCompanyModal] = useState(false);
  const [copiedLink, setCopiedLink] = useState(null);
  const [companyForm, setCompanyForm] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    website: '',
    industry: '',
    companySize: '',
    description: '',
  });
  const [companySubmitting, setCompanySubmitting] = useState(false);

  // AI Agents State
  const [agents, setAgents] = useState([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsPagination, setAgentsPagination] = useState({ page: 1, limit: 20, total: 0, totalPages: 0 });
  const [agentsSearchTerm, setAgentsSearchTerm] = useState('');
  const [agentsStatusFilter, setAgentsStatusFilter] = useState('');
  const [agentsModuleFilter, setAgentsModuleFilter] = useState('');
  const [agentsStats, setAgentsStats] = useState({ total_purchases: 0, active_count: 0, cancelled_count: 0, expired_count: 0, trial_count: 0 });
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [togglingAgentId, setTogglingAgentId] = useState(null);
  const [confirmActivateAgent, setConfirmActivateAgent] = useState(null);

  const { logout, user } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();

  // Career Applications Functions
  const fetchApplications = useCallback(async () => {
    try {
      setApplicationsLoading(true);
      const params = {
        page: applicationsPagination.page,
        limit: applicationsPagination.limit,
      };
      
      if (applicationsStatusFilter) {
        params.status = applicationsStatusFilter;
      }
      
      if (applicationsSearchTerm) {
        params.search = applicationsSearchTerm;
      }

      console.log('Fetching applications with params:', params);
      const response = await careerService.getAllApplications(params);
      console.log('Applications response:', response);
      
      if (response.status === 'success') {
        setApplications(response.data || []);
        if (response.pagination) {
          setApplicationsPagination(response.pagination);
        } else {
          setApplicationsPagination({ 
            page: params.page || 1, 
            limit: params.limit || 20, 
            total: response.data?.length || 0, 
            totalPages: 1 
          });
        }
      } else {
        console.error('Unexpected response format:', response);
        setApplications([]);
      }
    } catch (error) {
      console.error('Error fetching applications:', error);
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to load career applications',
        variant: 'destructive',
      });
      setApplications([]);
    } finally {
      setApplicationsLoading(false);
    }
  }, [applicationsPagination.page, applicationsPagination.limit, applicationsStatusFilter, applicationsSearchTerm, toast]);

  // Companies Functions
  const fetchCompanies = useCallback(async () => {
    try {
      setCompaniesLoading(true);
      const params = {
        page: companiesPagination.page,
        limit: companiesPagination.limit,
      };
      
      if (companiesSearchTerm) {
        params.search = companiesSearchTerm;
      }

      const response = await companyService.getAllCompanies(params);
      
      console.log('Companies response:', response); // Debug log
      
      if (response.status === 'success') {
        setCompanies(response.data || []);
        if (response.pagination) {
          setCompaniesPagination(response.pagination);
        } else {
          setCompaniesPagination({ 
            page: params.page || 1, 
            limit: params.limit || 20, 
            total: response.data?.length || 0, 
            totalPages: 1 
          });
        }
      } else {
        console.error('Unexpected response format:', response);
        setCompanies([]);
      }
    } catch (error) {
      console.error('Error fetching companies:', error);
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to load companies',
        variant: 'destructive',
      });
      setCompanies([]);
    } finally {
      setCompaniesLoading(false);
    }
  }, [companiesPagination.page, companiesPagination.limit, companiesSearchTerm, toast]);

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    if (companySubmitting) return;

    // Validate required fields
    if (!companyForm.name || !companyForm.email) {
      toast({
        title: '❌ Validation Error',
        description: 'Name and Email are required fields',
        variant: 'destructive',
      });
      return;
    }

    // Validate company name - must have at least 2 alphanumeric characters
    const nameAlnumCount = (companyForm.name.match(/[a-zA-Z0-9]/g) || []).length;
    if (nameAlnumCount < 2) {
      toast({
        title: '❌ Validation Error',
        description: 'Company name must contain at least 2 alphanumeric characters.',
        variant: 'destructive',
      });
      return;
    }

    // Strict email validation
    const emailRegex = /^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    const trimmedEmail = companyForm.email.trim();
    if (!emailRegex.test(trimmedEmail)) {
      toast({
        title: '❌ Validation Error',
        description: 'Please enter a valid email address (e.g., company@example.com).',
        variant: 'destructive',
      });
      return;
    }

    // Phone validation (if provided)
    if (companyForm.phone?.trim()) {
      const phoneDigits = (companyForm.phone.match(/[0-9]/g) || []).length;
      const phoneRegex = /^[+]?[\d\s\-()]{7,20}$/;
      if (!phoneRegex.test(companyForm.phone.trim()) || phoneDigits < 7) {
        toast({ title: '❌ Validation Error', description: 'Enter a valid phone number (at least 7 digits, e.g., +1234567890).', variant: 'destructive' });
        return;
      }
    }

    // Address validation (if provided)
    if (companyForm.address?.trim()) {
      const addrAlnum = (companyForm.address.match(/[a-zA-Z0-9]/g) || []).length;
      if (addrAlnum < 3) {
        toast({ title: '❌ Validation Error', description: 'Address must contain at least 3 alphanumeric characters.', variant: 'destructive' });
        return;
      }
    }

    // Website validation (if provided)
    if (companyForm.website?.trim()) {
      const urlRegex = /^(https?:\/\/)?([\w.-]+)\.[a-zA-Z]{2,}(\/.*)?$/;
      if (!urlRegex.test(companyForm.website.trim())) {
        toast({ title: '❌ Validation Error', description: 'Enter a valid website URL (e.g., https://company.com).', variant: 'destructive' });
        return;
      }
    }

    // Industry validation (if provided)
    if (companyForm.industry?.trim()) {
      const indAlpha = (companyForm.industry.match(/[a-zA-Z]/g) || []).length;
      if (indAlpha < 2) {
        toast({ title: '❌ Validation Error', description: 'Industry must contain at least 2 alphabetic characters.', variant: 'destructive' });
        return;
      }
    }

    // Company Size validation (if provided) - only numbers allowed
    if (companyForm.companySize?.trim()) {
      if (!/^[\d\s\-+]+$/.test(companyForm.companySize.trim())) {
        toast({ title: '❌ Validation Error', description: 'Company size must contain only numbers (e.g., 50, 50-100, 200+).', variant: 'destructive' });
        return;
      }
    }

    // Description validation (if provided)
    if (companyForm.description?.trim()) {
      const descAlnum = (companyForm.description.match(/[a-zA-Z0-9]/g) || []).length;
      if (descAlnum < 10) {
        toast({ title: '❌ Validation Error', description: 'Description must contain at least 10 alphanumeric characters.', variant: 'destructive' });
        return;
      }
    }

    setCompanySubmitting(true);
    try {
      // Helper function to validate and format URL
      const formatWebsite = (url) => {
        if (!url || !url.trim()) return null;
        const trimmed = url.trim();
        // If it already starts with http:// or https://, return as is
        if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
          return trimmed;
        }
        // Otherwise, prepend https://
        return `https://${trimmed}`;
      };
      
      // Convert camelCase to snake_case for backend
      // Remove empty strings and convert to null
      const companyData = {
        name: companyForm.name.trim(),
        email: companyForm.email.trim(),
        phone: companyForm.phone?.trim() || null,
        address: companyForm.address?.trim() || null,
        website: formatWebsite(companyForm.website), // Format website URL
        industry: companyForm.industry?.trim() || null,
        company_size: companyForm.companySize?.trim() || null, // Convert camelCase to snake_case
        description: companyForm.description?.trim() || null,
      };
      
      // Remove null values for optional fields to avoid sending empty strings
      Object.keys(companyData).forEach(key => {
        if (companyData[key] === '' || companyData[key] === undefined) {
          companyData[key] = null;
        }
      });
      
      console.log('Sending company data:', companyData);
      
      const response = await companyService.createCompany(companyData);
      if (response.status === 'success') {
        toast({
          title: '✅ Success',
          description: 'Company created successfully! Registration link generated.',
        });
        setShowCreateCompanyModal(false);
        setCompanyForm({
          name: '', email: '', phone: '', address: '', website: '', industry: '', companySize: '', description: '',
        });
        fetchCompanies();
      }
    } catch (error) {
      console.error('Create company error:', error);
      console.error('Error response:', error.response);
      console.error('Error data:', error.data);
      console.error('Error status:', error.status);
      
      // Extract error message from different possible structures
      // Note: api.js sets error.data (not error.response.data)
      let errorMessage = 'Failed to create company';
      const errorData = error.data || error.response?.data;
      
      if (errorData) {
        if (errorData.errors) {
          // Format validation errors
          const errors = errorData.errors;
          const errorList = Object.entries(errors).map(([field, messages]) => {
            const msgArray = Array.isArray(messages) ? messages : [messages];
            return `${field}: ${msgArray.join(', ')}`;
          });
          errorMessage = errorList.join('\n');
        } else if (errorData.message) {
          errorMessage = errorData.message;
        } else if (typeof errorData === 'string') {
          errorMessage = errorData;
        }
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      toast({
        title: '❌ Error',
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setCompanySubmitting(false);
    }
  };

  const handleGenerateToken = async (companyId) => {
    try {
      const response = await companyService.generateToken(companyId);
      console.log('Generate token response:', response);
      
      if (response.status === 'success') {
        // Get the token from the response
        const token = response.data.token;
        console.log('Extracted token:', token);
        
        if (!token) {
          console.error('Token not found in response data:', response.data);
          toast({
            title: '❌ Error',
            description: 'Token not found in response',
            variant: 'destructive',
          });
          return;
        }
        
        // URL encode the token for the link
        const encodedToken = encodeURIComponent(token);
        
        // Construct the full registration link
        const registrationLink = `${window.location.origin}/company/register?token=${encodedToken}`;
        console.log('Generated registration link:', registrationLink);
        
        toast({
          title: '✅ Success',
          description: 'Registration link generated successfully!',
        });
        
        // Show the link and copy it to clipboard
        setCopiedLink(registrationLink);
        setTimeout(() => {
          navigator.clipboard.writeText(registrationLink);
          toast({
            title: '📋 Copied!',
            description: 'Registration link copied to clipboard',
          });
        }, 500);
        fetchCompanies();
      }
    } catch (error) {
      console.error('Generate token error:', error);
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to generate token',
        variant: 'destructive',
      });
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedLink(text);
    toast({
      title: '📋 Copied!',
      description: 'Link copied to clipboard',
    });
    setTimeout(() => setCopiedLink(null), 2000);
  };

  // AI Agents Functions
  const fetchAgents = useCallback(async () => {
    try {
      setAgentsLoading(true);
      const params = {
        page: agentsPagination.page,
        limit: agentsPagination.limit,
      };
      if (agentsSearchTerm) params.search = agentsSearchTerm;
      if (agentsStatusFilter) params.status = agentsStatusFilter;
      if (agentsModuleFilter) params.module = agentsModuleFilter;

      const response = await companyService.getCompanyAgents(params);
      if (response.status === 'success') {
        setAgents(response.data || []);
        if (response.stats) setAgentsStats(response.stats);
        if (response.pagination) {
          setAgentsPagination(response.pagination);
        }
      } else {
        setAgents([]);
      }
    } catch (error) {
      console.error('Error fetching agents:', error);
      toast({ title: 'Error', description: error.message || 'Failed to load AI agents', variant: 'destructive' });
      setAgents([]);
    } finally {
      setAgentsLoading(false);
    }
  }, [agentsPagination.page, agentsPagination.limit, agentsSearchTerm, agentsStatusFilter, agentsModuleFilter, toast]);

  const handleToggleAgentStatus = async (agent) => {
    const newStatus = agent.status === 'active' ? 'cancelled' : 'active';

    // Show confirmation modal when activating an expired agent
    if (agent.status === 'expired' && newStatus === 'active') {
      setConfirmActivateAgent(agent);
      return;
    }

    await performToggleAgentStatus(agent, newStatus);
  };

  const performToggleAgentStatus = async (agent, newStatus) => {
    setTogglingAgentId(agent.id);
    try {
      const response = await companyService.toggleCompanyAgentStatus(agent.id, newStatus);
      if (response.status === 'success') {
        toast({ title: 'Success', description: response.message });
        fetchAgents();
      }
    } catch (error) {
      toast({ title: 'Error', description: error.message || 'Failed to update agent status', variant: 'destructive' });
    } finally {
      setTogglingAgentId(null);
    }
  };

  useEffect(() => {
    if (activeTab === 'contact') {
      fetchMessages();
    } else if (activeTab === 'predictions') {
      fetchPredictions();
    } else if (activeTab === 'applications') {
      fetchApplications();
    } else if (activeTab === 'companies') {
      fetchCompanies();
    } else if (activeTab === 'agents') {
      fetchAgents();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, pagination.page, statusFilter, searchTerm, predictionsPagination.page, predictionsSearchTerm, applicationsPagination.page, applicationsSearchTerm, applicationsStatusFilter, companiesPagination.page, companiesSearchTerm, fetchCompanies, agentsPagination.page, agentsSearchTerm, agentsStatusFilter, agentsModuleFilter, fetchAgents]);

  // Debug modal state
  useEffect(() => {
    if (showCreateCompanyModal) {
      console.log('Create Company Modal is now visible');
    }
  }, [showCreateCompanyModal]);

  const fetchMessages = async () => {
    try {
      setLoading(true);
      const params = {
        page: pagination.page,
        limit: pagination.limit,
      };
      
      if (statusFilter) {
        params.status = statusFilter;
      }
      
      if (searchTerm) {
        params.search = searchTerm;
      }

      const response = await contactService.getAllContactMessages(params);
      
      console.log('Contact messages response:', response); // Debug log
      
      if (response.status === 'success') {
        setMessages(response.data || []);
        if (response.pagination) {
          setPagination(response.pagination);
        } else {
          // Fallback pagination if backend doesn't provide it
          setPagination({
            page: params.page || 1,
            limit: params.limit || 20,
            total: response.data?.length || 0,
            totalPages: 1
          });
        }
      } else {
        console.error('Unexpected response format:', response);
        setMessages([]);
      }
    } catch (error) {
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to load contact messages',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    setPagination(prev => ({ ...prev, page: 1 }));
    fetchMessages();
  };

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getFileUrl = (attachmentPath) => {
    if (!attachmentPath) return null;
    return `${API_BASE_URL.replace('/api', '')}/${attachmentPath}`;
  };

  // AI Predictions Functions
  const fetchPredictions = async () => {
    try {
      setPredictionsLoading(true);
      const params = {
        page: predictionsPagination.page,
        limit: predictionsPagination.limit,
      };
      
      if (predictionsSearchTerm) {
        params.search = predictionsSearchTerm;
      }

      const response = await aiPredictorService.getAllPredictions(params);
      
      console.log('Predictions response:', response); // Debug log
      
      if (response.status === 'success') {
        setPredictions(response.data || []);
        if (response.pagination) {
          setPredictionsPagination(response.pagination);
        } else {
          setPredictionsPagination({ 
            page: params.page || 1, 
            limit: params.limit || 20, 
            total: response.data?.length || 0, 
            totalPages: 1 
          });
        }
      } else {
        console.error('Unexpected response format:', response);
        setPredictions([]);
      }
    } catch (error) {
      console.error('Error fetching predictions:', error);
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to load AI predictions',
        variant: 'destructive',
      });
      setPredictions([]);
    } finally {
      setPredictionsLoading(false);
    }
  };

  const handlePredictionsSearch = () => {
    setPredictionsPagination(prev => ({ ...prev, page: 1 }));
    fetchPredictions();
  };
  
  const formatProjectType = (type) => {
    if (!type) return 'N/A';
    return type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };
  
  const formatDuration = (weeks) => {
    if (!weeks) return 'N/A';
    const weeksNum = parseInt(weeks);
    if (weeksNum === 0) return 'N/A';
    const months = Math.floor(weeksNum / 4);
    const remainingWeeks = weeksNum % 4;
    if (months > 0) {
      return `${months} month${months > 1 ? 's' : ''}${remainingWeeks > 0 ? ` ${remainingWeeks} week${remainingWeeks > 1 ? 's' : ''}` : ''}`;
    }
    return `${weeksNum} week${weeksNum !== 1 ? 's' : ''}`;
  };

  const handleApplicationsSearch = () => {
    setApplicationsPagination(prev => ({ ...prev, page: 1 }));
    fetchApplications();
  };

  const handleUpdateApplicationStatus = async (applicationId, newStatus) => {
    try {
      await careerService.updateApplicationStatus(applicationId, newStatus);
      toast({
        title: '✅ Success',
        description: 'Application status updated successfully',
      });
      fetchApplications();
      if (selectedApplication && selectedApplication.id === applicationId) {
        setSelectedApplication({ ...selectedApplication, status: newStatus });
      }
    } catch (error) {
      toast({
        title: '❌ Error',
        description: error.message || 'Failed to update application status',
        variant: 'destructive',
      });
    }
  };

  const getResumeUrl = (resumePath) => {
    if (!resumePath) return null;
    return `${API_BASE_URL.replace('/api', '')}/${resumePath}`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'reviewing':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'interview':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'accepted':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'rejected':
        return 'bg-red-100 text-red-800 border-red-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <>
      <Helmet>
        <title>Admin Dashboard - Contact Messages | Pay Per Project</title>
        <meta name="description" content="Admin dashboard to view all contact form submissions" />
      </Helmet>

      <div className="min-h-screen bg-background">
        {/* Header */}
        <DashboardNavbar
          icon={BrainCircuit}
          title="Admin Dashboard"
          subtitle="Manage submissions and predictions"
          user={user}
          userRole="Admin"
          showNavTabs={false}
          onLogout={handleLogout}
        />

        <div className="container mx-auto px-4 py-4 sm:py-6 lg:py-8">
          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 md:grid-cols-5 gap-2 mb-6 h-auto p-2">
              <TabsTrigger value="contact" className="flex items-center justify-center gap-2 py-2 sm:py-3">
                <MessageSquare className="h-4 w-4 shrink-0" />
                <span className="text-xs sm:text-sm truncate">Contact Messages</span>
              </TabsTrigger>
              <TabsTrigger value="predictions" className="flex items-center justify-center gap-2 py-2 sm:py-3">
                <BrainCircuit className="h-4 w-4 shrink-0" />
                <span className="text-xs sm:text-sm truncate">AI Predictions</span>
              </TabsTrigger>
              <TabsTrigger value="applications" className="flex items-center justify-center gap-2 py-2 sm:py-3">
                <FileCheck className="h-4 w-4 shrink-0" />
                <span className="text-xs sm:text-sm truncate">Career Applications</span>
              </TabsTrigger>
              <TabsTrigger value="companies" className="flex items-center justify-center gap-2 py-2 sm:py-3">
                <UsersIcon className="h-4 w-4 shrink-0" />
                <span className="text-xs sm:text-sm truncate">Companies</span>
              </TabsTrigger>
              <TabsTrigger value="agents" className="flex items-center justify-center gap-2 py-2 sm:py-3">
                <BrainCircuit className="h-4 w-4 shrink-0" />
                <span className="text-xs sm:text-sm truncate">AI Agents</span>
              </TabsTrigger>
            </TabsList>

            {/* Contact Messages Tab */}
            <TabsContent value="contact" className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Total Messages</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{pagination.total}</p>
                      </div>
                      <MessageSquare className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
            <Card>
              <CardContent className="pt-4 sm:pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">This Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{messages.length}</p>
                      </div>
                      <FileText className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Current Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{pagination.page}/{pagination.totalPages || 1}</p>
                      </div>
                      <Calendar className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">With Attachments</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">
                          {messages.filter(m => m.attachment_path).length}
                        </p>
                      </div>
                      <Download className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
          </div>

          {/* Filters */}
          <Card className="mb-4 sm:mb-6">
            <CardHeader className="pb-3 sm:pb-6">
              <CardTitle className="text-lg sm:text-xl">Filters & Search</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                <div className="relative sm:col-span-2 lg:col-span-1">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by name, email, or message..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                    className="pl-10"
                  />
                </div>
                <Select value={statusFilter || 'all'} onValueChange={(value) => setStatusFilter(value === 'all' ? '' : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Filter by status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="new">New</SelectItem>
                    <SelectItem value="read">Read</SelectItem>
                    <SelectItem value="replied">Replied</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex gap-2 sm:col-span-2 lg:col-span-1">
                  <Button onClick={handleSearch} className="flex-1">
                    <Search className="h-4 w-4 sm:mr-2" />
                    <span className="hidden sm:inline">Search</span>
                  </Button>
                  <Button variant="outline" onClick={fetchMessages} className="px-3">
                    <RefreshCw className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Messages List */}
          <Card>
            <CardHeader>
              <CardTitle>Contact Messages</CardTitle>
              <CardDescription>
                View and manage all contact form submissions
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : messages.length === 0 ? (
                <div className="text-center py-12">
                  <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-lg font-medium">No messages found</p>
                  <p className="text-sm text-muted-foreground">
                    {searchTerm || statusFilter 
                      ? 'Try adjusting your filters' 
                      : 'No contact form submissions yet'}
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((message) => (
                    <motion.div
                      key={message.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="border rounded-lg p-3 sm:p-4 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <User className="h-4 w-4 sm:h-5 sm:w-5 text-primary shrink-0" />
                            <h3 className="font-semibold text-base sm:text-lg truncate flex-1">{message.full_name}</h3>
                            {message.status && (
                              <Badge variant="outline" className="shrink-0 text-xs">{message.status}</Badge>
                            )}
                          </div>
                          
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
                            <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground">
                              <Mail className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                              <a href={`mailto:${message.email}`} className="hover:text-primary truncate">
                                {message.email}
                              </a>
                            </div>
                            {message.phone && (
                              <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground">
                                <Phone className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                                <a href={`tel:${message.phone}`} className="hover:text-primary truncate">
                                  {message.phone}
                                </a>
                              </div>
                            )}
                            <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground sm:col-span-2">
                              <Calendar className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                              <span className="truncate">{formatDate(message.created_at)}</span>
                            </div>
                          </div>

                          {message.project_title && (
                            <p className="text-xs sm:text-sm font-medium mb-2 truncate">
                              <span className="text-muted-foreground">Project:</span> {message.project_title}
                            </p>
                          )}

                          <p className="text-xs sm:text-sm text-muted-foreground mb-3 line-clamp-2">
                            {message.message}
                          </p>

                          {message.attachment_path && (
                            <div className="mt-2 sm:mt-3">
                              <a
                                href={getFileUrl(message.attachment_path)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 text-xs sm:text-sm text-primary hover:underline"
                              >
                                <Download className="h-3 w-3 sm:h-4 sm:w-4" />
                                View Attachment
                              </a>
                            </div>
                          )}
                        </div>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedMessage(message)}
                          className="w-full sm:w-auto shrink-0"
                        >
                          <Eye className="h-4 w-4 sm:mr-2" />
                          <span className="hidden sm:inline">View</span>
                        </Button>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}

              {/* Pagination */}
              {pagination.totalPages > 1 && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-0 mt-4 sm:mt-6">
                  <p className="text-xs sm:text-sm text-muted-foreground text-center sm:text-left">
                    Showing page {pagination.page} of {pagination.totalPages}
                  </p>
                  <div className="flex gap-2 w-full sm:w-auto">
                    <Button
                      variant="outline"
                      onClick={() => setPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                      disabled={pagination.page === 1 || loading}
                      className="flex-1 sm:flex-none"
                      size="sm"
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                      disabled={pagination.page >= pagination.totalPages || loading}
                      className="flex-1 sm:flex-none"
                      size="sm"
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
            </TabsContent>

            {/* AI Predictions Tab */}
            <TabsContent value="predictions" className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Total Predictions</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{predictionsPagination.total}</p>
                      </div>
                      <BrainCircuit className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">This Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{predictions.length}</p>
                      </div>
                      <FileText className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Current Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{predictionsPagination.page}/{predictionsPagination.totalPages || 1}</p>
                      </div>
                      <Calendar className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Avg Cost</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">
                          {predictions.length > 0 
                            ? `$${Math.round(predictions.reduce((sum, p) => sum + (p.predicted_cost || 0), 0) / predictions.length).toLocaleString()}`
                            : 'N/A'}
                        </p>
                      </div>
                      <DollarSign className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Filters */}
              <Card className="mb-4 sm:mb-6">
                <CardHeader className="pb-3 sm:pb-6">
                  <CardTitle className="text-lg sm:text-xl">Filters & Search</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                    <div className="relative sm:col-span-2 lg:col-span-2">
                      <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                      <Input
                        placeholder="Search by email or project type..."
                        value={predictionsSearchTerm}
                        onChange={(e) => setPredictionsSearchTerm(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handlePredictionsSearch()}
                        className="pl-10"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button onClick={handlePredictionsSearch} className="flex-1">
                        <Search className="h-4 w-4 sm:mr-2" />
                        <span className="hidden sm:inline">Search</span>
                      </Button>
                      <Button variant="outline" onClick={fetchPredictions} className="px-3">
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Predictions List */}
              <Card>
                <CardHeader>
                  <CardTitle>AI Predictions</CardTitle>
                  <CardDescription>
                    View all AI predictor submissions
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {predictionsLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                  ) : predictions.length === 0 ? (
                    <div className="text-center py-12">
                      <BrainCircuit className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-lg font-medium">No predictions found</p>
                      <p className="text-sm text-muted-foreground">
                        {predictionsSearchTerm 
                          ? 'Try adjusting your filters' 
                          : 'No AI predictions yet'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {predictions.map((prediction) => (
                        <motion.div
                          key={prediction.id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="border rounded-lg p-3 sm:p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-2">
                                <BrainCircuit className="h-4 w-4 sm:h-5 sm:w-5 text-primary shrink-0" />
                                <Badge variant="outline" className="shrink-0 text-xs">
                                  {formatProjectType(prediction.project_type)}
                                </Badge>
                                {prediction.email && !prediction.email.includes('anonymous') && (
                                  <Badge variant="secondary" className="shrink-0 text-xs">
                                    {prediction.email}
                                  </Badge>
                                )}
                              </div>
                              
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                                <div className="flex flex-col gap-1">
                                  <p className="text-xs text-muted-foreground">Cost</p>
                                  <p className="text-sm sm:text-base font-semibold text-blue-600 dark:text-blue-400">
                                    ${prediction.predicted_cost?.toLocaleString() || 'N/A'}
                                  </p>
                                </div>
                                <div className="flex flex-col gap-1">
                                  <p className="text-xs text-muted-foreground">Duration</p>
                                  <p className="text-sm sm:text-base font-semibold text-green-600 dark:text-green-400">
                                    {formatDuration(prediction.predicted_duration)}
                                  </p>
                                </div>
                                <div className="flex flex-col gap-1">
                                  <p className="text-xs text-muted-foreground">Team Size</p>
                                  <p className="text-sm sm:text-base font-semibold text-purple-600 dark:text-purple-400">
                                    {prediction.predicted_team_size || 'N/A'}
                                  </p>
                                </div>
                                <div className="flex flex-col gap-1">
                                  <p className="text-xs text-muted-foreground">Confidence</p>
                                  <p className="text-sm sm:text-base font-semibold text-orange-600 dark:text-orange-400">
                                    {prediction.prediction_confidence ? `${prediction.prediction_confidence}%` : 'N/A'}
                                  </p>
                                </div>
                              </div>

                              <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground">
                                <Calendar className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                                <span className="truncate">{formatDate(prediction.created_at)}</span>
                              </div>
                            </div>

                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setSelectedPrediction(prediction)}
                              className="w-full sm:w-auto shrink-0"
                            >
                              <Eye className="h-4 w-4 sm:mr-2" />
                              <span className="hidden sm:inline">View</span>
                            </Button>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                  {predictionsPagination.totalPages > 1 && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-0 mt-4 sm:mt-6">
                      <p className="text-xs sm:text-sm text-muted-foreground text-center sm:text-left">
                        Showing page {predictionsPagination.page} of {predictionsPagination.totalPages}
                      </p>
                      <div className="flex gap-2 w-full sm:w-auto">
                        <Button
                          variant="outline"
                          onClick={() => setPredictionsPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={predictionsPagination.page === 1 || predictionsLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setPredictionsPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={predictionsPagination.page >= predictionsPagination.totalPages || predictionsLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Career Applications Tab */}
            <TabsContent value="applications" className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Total Applications</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{applicationsPagination.total}</p>
                      </div>
                      <FileCheck className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">This Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{applications.length}</p>
                      </div>
                      <FileText className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Current Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{applicationsPagination.page}/{applicationsPagination.totalPages || 1}</p>
                      </div>
                      <Calendar className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">With Resumes</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">
                          {applications.filter(a => a.resume_path).length}
                        </p>
                      </div>
                      <Download className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Filters */}
              <Card className="mb-4 sm:mb-6">
                <CardHeader className="pb-3 sm:pb-6">
                  <CardTitle className="text-lg sm:text-xl">Filters & Search</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                    <div className="relative sm:col-span-2 lg:col-span-1">
                      <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                      <Input
                        placeholder="Search by name, email, or position..."
                        value={applicationsSearchTerm}
                        onChange={(e) => setApplicationsSearchTerm(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleApplicationsSearch()}
                        className="pl-10"
                      />
                    </div>
                    <Select value={applicationsStatusFilter || 'all'} onValueChange={(value) => setApplicationsStatusFilter(value === 'all' ? '' : value)}>
                      <SelectTrigger>
                        <SelectValue placeholder="Filter by status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Statuses</SelectItem>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="reviewing">Reviewing</SelectItem>
                        <SelectItem value="interview">Interview</SelectItem>
                        <SelectItem value="accepted">Accepted</SelectItem>
                        <SelectItem value="rejected">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="flex gap-2 sm:col-span-2 lg:col-span-1">
                      <Button onClick={handleApplicationsSearch} className="flex-1">
                        <Search className="h-4 w-4 sm:mr-2" />
                        <span className="hidden sm:inline">Search</span>
                      </Button>
                      <Button variant="outline" onClick={fetchApplications} className="px-3">
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Applications List */}
              <Card>
                <CardHeader>
                  <CardTitle>Career Applications</CardTitle>
                  <CardDescription>
                    View and manage all job applications
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {applicationsLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                  ) : applications.length === 0 ? (
                    <div className="text-center py-12">
                      <FileCheck className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-lg font-medium">No applications found</p>
                      <p className="text-sm text-muted-foreground">
                        {applicationsSearchTerm || applicationsStatusFilter 
                          ? 'Try adjusting your filters' 
                          : 'No career applications yet'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {applications.map((application) => (
                        <motion.div
                          key={application.id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="border rounded-lg p-3 sm:p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-2">
                                <Briefcase className="h-4 w-4 sm:h-5 sm:w-5 text-primary shrink-0" />
                                <h3 className="text-base sm:text-lg font-semibold text-foreground truncate">
                                  {application.position_title}
                                </h3>
                                <Badge className={`${getStatusColor(application.status)} border shrink-0 text-xs`}>
                                  {application.status}
                                </Badge>
                              </div>
                              
                              <div className="space-y-2 mb-3">
                                <div className="flex items-center gap-2 text-sm text-foreground">
                                  <User className="h-4 w-4 text-muted-foreground shrink-0" />
                                  <span className="truncate">{application.applicant_name}</span>
                                </div>
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <Mail className="h-4 w-4 shrink-0" />
                                  <span className="truncate">{application.email}</span>
                                </div>
                                {application.phone && (
                                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Phone className="h-4 w-4 shrink-0" />
                                    <span>{application.phone}</span>
                                  </div>
                                )}
                              </div>

                              <div className="flex items-center gap-2 text-xs sm:text-sm text-muted-foreground">
                                <Calendar className="h-3 w-3 sm:h-4 sm:w-4 shrink-0" />
                                <span className="truncate">{formatDate(application.created_at)}</span>
                              </div>
                            </div>

                            <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto shrink-0">
                              {application.resume_path && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => window.open(getResumeUrl(application.resume_path), '_blank')}
                                  className="w-full sm:w-auto"
                                >
                                  <Download className="h-4 w-4 sm:mr-2" />
                                  <span className="hidden sm:inline">Resume</span>
                                </Button>
                              )}
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setSelectedApplication(application)}
                                className="w-full sm:w-auto"
                              >
                                <Eye className="h-4 w-4 sm:mr-2" />
                                <span className="hidden sm:inline">View</span>
                              </Button>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                  {applicationsPagination.totalPages > 1 && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-0 mt-4 sm:mt-6">
                      <p className="text-xs sm:text-sm text-muted-foreground text-center sm:text-left">
                        Showing page {applicationsPagination.page} of {applicationsPagination.totalPages}
                      </p>
                      <div className="flex gap-2 w-full sm:w-auto">
                        <Button
                          variant="outline"
                          onClick={() => setApplicationsPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={applicationsPagination.page === 1 || applicationsLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setApplicationsPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={applicationsPagination.page >= applicationsPagination.totalPages || applicationsLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Companies Tab */}
            <TabsContent value="companies" className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Total Companies</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{companiesPagination.total}</p>
                      </div>
                      <Building2 className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">This Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{companies.length}</p>
                      </div>
                      <UsersIcon className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Current Page</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{companiesPagination.page}/{companiesPagination.totalPages || 1}</p>
                      </div>
                      <Calendar className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Active Companies</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">
                          {companies.filter(c => c.is_active).length}
                        </p>
                      </div>
                      <CheckCircle2 className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Actions */}
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                <div className="relative flex-1 max-w-md w-full">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search companies..."
                    value={companiesSearchTerm}
                    onChange={(e) => setCompaniesSearchTerm(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && fetchCompanies()}
                    className="pl-10"
                  />
                </div>
                <Button 
                  onClick={() => {
                    console.log('Create Company button clicked');
                    setShowCreateCompanyModal(true);
                  }} 
                  className="w-full sm:w-auto"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Create Company
                </Button>
              </div>

              {/* Companies List */}
              <Card>
                <CardHeader>
                  <CardTitle>Companies</CardTitle>
                  <CardDescription>Manage companies and registration links</CardDescription>
                </CardHeader>
                <CardContent>
                  {companiesLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                  ) : companies.length === 0 ? (
                    <div className="text-center py-12">
                      <Building2 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-lg font-medium">No companies found</p>
                      <p className="text-sm text-muted-foreground mt-2">
                        {companiesSearchTerm ? 'Try adjusting your search' : 'Create your first company to get started'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {companies.map((company) => (
                        <motion.div
                          key={company.id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="border rounded-lg p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                            <div className="flex-1">
                              <h3 className="text-lg font-semibold">{company.name}</h3>
                              <p className="text-sm text-muted-foreground">{company.email}</p>
                              <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
                                {company.industry && <span>Industry: {company.industry}</span>}
                                {company.company_size && <span>Size: {company.company_size}</span>}
                                <span>Users: {company.user_count || 0}</span>
                                <span>Jobs: {company.job_count || 0}</span>
                              </div>
                              <div className="mt-2">
                                <Badge variant={company.is_active ? 'default' : 'secondary'}>
                                  {company.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleGenerateToken(company.id)}
                              >
                                <LinkIcon className="h-4 w-4 mr-2" />
                                Generate Link
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setSelectedCompany(company)}
                              >
                                <Eye className="h-4 w-4 mr-2" />
                                View Details
                              </Button>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                  {companiesPagination.totalPages > 1 && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-0 mt-4 sm:mt-6">
                      <p className="text-xs sm:text-sm text-muted-foreground text-center sm:text-left">
                        Showing page {companiesPagination.page} of {companiesPagination.totalPages}
                      </p>
                      <div className="flex gap-2 w-full sm:w-auto">
                        <Button
                          variant="outline"
                          onClick={() => setCompaniesPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={companiesPagination.page === 1 || companiesLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setCompaniesPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={companiesPagination.page >= companiesPagination.totalPages || companiesLoading}
                          className="flex-1 sm:flex-none"
                          size="sm"
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* AI Agents Tab */}
            <TabsContent value="agents" className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Total Purchases</p>
                        <p className="text-xl sm:text-2xl font-bold text-foreground">{agentsStats.total_purchases}</p>
                      </div>
                      <BrainCircuit className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Active Agents</p>
                        <p className="text-xl sm:text-2xl font-bold text-green-600">{agentsStats.active_count}</p>
                      </div>
                      <CheckCircle2 className="h-6 w-6 sm:h-8 sm:w-8 text-green-600 shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Cancelled</p>
                        <p className="text-xl sm:text-2xl font-bold text-orange-500">{agentsStats.cancelled_count}</p>
                      </div>
                      <Clock className="h-6 w-6 sm:h-8 sm:w-8 text-orange-500 shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 sm:pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">Expired</p>
                        <p className="text-xl sm:text-2xl font-bold text-red-500">{agentsStats.expired_count}</p>
                      </div>
                      <Clock className="h-6 w-6 sm:h-8 sm:w-8 text-red-500 shrink-0 ml-2" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Filters */}
              <div className="flex flex-col sm:flex-row gap-3 mb-6">
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by company name, email, or module..."
                    value={agentsSearchTerm}
                    onChange={(e) => setAgentsSearchTerm(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && fetchAgents()}
                    className="pl-10"
                  />
                </div>
                <Select value={agentsStatusFilter} onValueChange={(val) => { setAgentsStatusFilter(val === 'all' ? '' : val); setAgentsPagination(prev => ({ ...prev, page: 1 })); }}>
                  <SelectTrigger className="w-full sm:w-[160px]">
                    <SelectValue placeholder="All Statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                    <SelectItem value="trial">Trial</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={agentsModuleFilter} onValueChange={(val) => { setAgentsModuleFilter(val === 'all' ? '' : val); setAgentsPagination(prev => ({ ...prev, page: 1 })); }}>
                  <SelectTrigger className="w-full sm:w-[200px]">
                    <SelectValue placeholder="All Modules" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Modules</SelectItem>
                    <SelectItem value="recruitment_agent">Recruitment Agent</SelectItem>
                    <SelectItem value="marketing_agent">Marketing Agent</SelectItem>
                    <SelectItem value="project_manager_agent">Project Manager Agent</SelectItem>
                    <SelectItem value="frontline_agent">Frontline Agent</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" onClick={fetchAgents} size="sm">
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>

              {/* Agents List */}
              <Card>
                <CardHeader>
                  <CardTitle>AI Agents Purchased by Companies</CardTitle>
                  <CardDescription>View and manage AI agent modules purchased by companies</CardDescription>
                </CardHeader>
                <CardContent>
                  {agentsLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                  ) : agents.length === 0 ? (
                    <div className="text-center py-12">
                      <BrainCircuit className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-lg font-medium">No AI agent purchases found</p>
                      <p className="text-sm text-muted-foreground mt-2">
                        {agentsSearchTerm || agentsStatusFilter || agentsModuleFilter ? 'Try adjusting your filters' : 'No companies have purchased any AI agents yet'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {agents.map((agent) => (
                        <motion.div
                          key={agent.id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="border rounded-lg p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-semibold">{agent.module_display_name}</h3>
                                <Badge variant={agent.status === 'active' ? 'default' : agent.status === 'expired' ? 'secondary' : 'secondary'} className={`font-normal ${agent.status === 'expired' ? 'bg-[hsl(0,55%,24%)] text-white border-[hsl(0,55%,24%)] hover:bg-[hsl(0,55%,24%)]' : agent.status === 'cancelled' ? 'bg-[#b7953c]/15 text-[#b7953c] border-[#b7953c]/40 hover:bg-[#b7953c]/15' : ''}`}>
                                  {agent.cancelled_reason === 'admin_deactivated' ? 'Deactivated by Admin' : agent.status === 'expired' ? 'Expired' : agent.status.charAt(0).toUpperCase() + agent.status.slice(1)}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
                                <span><Building2 className="h-3.5 w-3.5 inline mr-1" />{agent.company_name}</span>
                                <span className="text-xs">${agent.price_paid || 0}</span>
                                {agent.active_label && (
                                  <span className={`text-xs font-medium ${agent.status === 'active' ? 'text-blue-600' : 'text-muted-foreground'}`}>
                                    {agent.active_label}
                                    {agent.time_remaining && ` · ${agent.time_remaining}`}
                                    {agent.time_ended_ago && ` · ${agent.time_ended_ago}`}
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="flex gap-2 shrink-0">
                              <Button variant="outline" size="sm" onClick={() => setSelectedAgent(agent)}>
                                <Eye className="h-4 w-4 mr-1" /> Details
                              </Button>
                              <Button
                                variant={agent.status === 'active' ? 'destructive' : 'default'}
                                size="sm"
                                onClick={() => handleToggleAgentStatus(agent)}
                                disabled={togglingAgentId === agent.id}
                              >
                                {togglingAgentId === agent.id && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                                {agent.status === 'active' ? 'Deactivate' : 'Activate'}
                              </Button>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                  {agentsPagination.totalPages > 1 && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-0 mt-4 sm:mt-6">
                      <p className="text-xs sm:text-sm text-muted-foreground">
                        Showing page {agentsPagination.page} of {agentsPagination.totalPages} ({agentsPagination.total} total)
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          onClick={() => setAgentsPagination(prev => ({ ...prev, page: prev.page - 1 }))}
                          disabled={agentsPagination.page === 1 || agentsLoading}
                          size="sm"
                        >
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setAgentsPagination(prev => ({ ...prev, page: prev.page + 1 }))}
                          disabled={agentsPagination.page >= agentsPagination.totalPages || agentsLoading}
                          size="sm"
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Agent Detail Modal */}
        {selectedAgent && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
            onClick={() => setSelectedAgent(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto"
            >
              <div className="p-4 sm:p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">AI Agent Details</h2>
                  <Button variant="ghost" onClick={() => setSelectedAgent(null)} size="sm" className="shrink-0">
                    <span className="text-2xl">&times;</span>
                  </Button>
                </div>

                <div className="space-y-4">
                  {/* Module Info */}
                  <div className="bg-muted/50 rounded-lg p-4">
                    <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
                      <BrainCircuit className="h-5 w-5" />
                      {selectedAgent.module_display_name}
                    </h3>
                    <div className="flex items-center gap-2 flex-wrap mb-3">
                      <Badge variant={selectedAgent.status === 'active' ? 'default' : selectedAgent.status === 'expired' ? 'secondary' : 'secondary'} className={`font-normal ${selectedAgent.status === 'expired' ? 'bg-[hsl(0,55%,24%)] text-white border-[hsl(0,55%,24%)] hover:bg-[hsl(0,55%,24%)]' : selectedAgent.status === 'cancelled' ? 'bg-[#b7953c]/15 text-[#b7953c] border-[#b7953c]/40 hover:bg-[#b7953c]/15' : ''}`}>
                        {selectedAgent.cancelled_reason === 'admin_deactivated' ? 'Deactivated by Admin' : selectedAgent.status === 'expired' ? 'Expired' : selectedAgent.status.charAt(0).toUpperCase() + selectedAgent.status.slice(1)}
                      </Badge>
                      {selectedAgent.price_paid != null && (
                        <Badge variant="outline">${selectedAgent.price_paid}</Badge>
                      )}
                      {selectedAgent.active_label && (
                        <Badge variant="outline" className="text-blue-600 border-blue-500">
                          {selectedAgent.active_label}
                          {selectedAgent.time_remaining && ` \u00B7 ${selectedAgent.time_remaining}`}
                        </Badge>
                      )}
                      {selectedAgent.time_ended_ago && (
                        <Badge variant="outline" className="text-red-500 border-red-500">{selectedAgent.time_ended_ago}</Badge>
                      )}
                    </div>
                    {selectedAgent.is_expired && (
                      <div className="mt-2 p-2 rounded bg-yellow-500/10 border border-yellow-500/30 text-sm text-yellow-700">
                        <Clock className="h-4 w-4 inline mr-1" />
                        Agent subscription time has ended. The company needs to purchase again.
                      </div>
                    )}
                  </div>

                  {/* Company Info */}
                  <div>
                    <h4 className="text-sm font-semibold text-muted-foreground mb-2">Company Information</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-muted-foreground">Company Name</label>
                        <p className="font-medium">{selectedAgent.company_name}</p>
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">Company Email</label>
                        <p className="font-medium">{selectedAgent.company_email || 'N/A'}</p>
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">Industry</label>
                        <p className="font-medium">{selectedAgent.company_industry || 'N/A'}</p>
                      </div>
                      <div className='flex items-center gap-2'>
                        <label className="text-xs text-muted-foreground">Company Status</label>
                        <Badge variant={selectedAgent.company_is_active ? 'default' : 'secondary'}>
                          {selectedAgent.company_is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Purchase Timeline */}
                  <div>
                    <h4 className="text-sm font-semibold text-muted-foreground mb-2">Purchase Timeline</h4>
                    <div className="relative border-l-2 border-muted ml-3 pl-6 space-y-4">
                      <div className="relative">
                        <div className="absolute -left-[31px] top-1 w-4 h-4 rounded-full bg-green-500 border-2 border-background"></div>
                        <p className="text-sm font-medium">Purchased</p>
                        <p className="text-xs text-muted-foreground">{formatDate(selectedAgent.purchased_at)}</p>
                        {selectedAgent.purchased_by_name && (
                          <p className="text-xs text-muted-foreground">By: {selectedAgent.purchased_by_name} ({selectedAgent.purchased_by_email})</p>
                        )}
                        {selectedAgent.price_paid != null && (
                          <p className="text-xs text-muted-foreground">Amount: ${selectedAgent.price_paid}</p>
                        )}
                        {selectedAgent.active_label && (
                          <p className="text-xs text-blue-600 font-medium">
                            {selectedAgent.active_label}
                            {selectedAgent.time_remaining && ` \u00B7 ${selectedAgent.time_remaining}`}
                          </p>
                        )}
                      </div>
                      {selectedAgent.expires_at && (
                        <div className="relative">
                          <div className={`absolute -left-[31px] top-1 w-4 h-4 rounded-full border-2 border-background ${selectedAgent.is_expired ? 'bg-red-500' : 'bg-yellow-500'}`}></div>
                          <p className="text-sm font-medium">{selectedAgent.is_expired ? 'Subscription Ended' : 'Expiration Date'}</p>
                          <p className="text-xs text-muted-foreground">{formatDate(selectedAgent.expires_at)}</p>
                          {selectedAgent.time_remaining && (
                            <p className="text-xs text-green-600 font-medium mt-0.5">{selectedAgent.time_remaining}</p>
                          )}
                          {selectedAgent.time_ended_ago && (
                            <p className="text-xs text-red-500 font-medium mt-0.5">{selectedAgent.time_ended_ago}</p>
                          )}
                        </div>
                      )}
                      {selectedAgent.cancelled_at && (
                        <div className="relative">
                          <div className="absolute -left-[31px] top-1 w-4 h-4 rounded-full bg-red-500 border-2 border-background"></div>
                          <p className="text-sm font-medium">{selectedAgent.cancelled_reason === 'admin_deactivated' ? 'Deactivated by Admin' : 'Cancelled'}</p>
                          <p className="text-xs text-muted-foreground">{formatDate(selectedAgent.cancelled_at)}</p>
                        </div>
                      )}
                      <div className="relative flex items-center gap-2">
                        <div className={`absolute -left-[31px] top-1 w-4 h-4 rounded-full border-2 border-background ${selectedAgent.status === 'active' ? 'bg-green-500' : selectedAgent.is_expired ? 'bg-red-500' : 'bg-gray-400'}`}></div>
                        <p className="text-sm font-medium">Current Status</p>
                        <Badge variant={selectedAgent.status === 'active' ? 'default' : selectedAgent.status === 'expired' ? 'secondary' : 'secondary'} className={`font-normal ${selectedAgent.status === 'expired' ? 'bg-[hsl(0,55%,24%)] text-white border-[hsl(0,55%,24%)] hover:bg-[hsl(0,55%,24%)]' : selectedAgent.status === 'cancelled' ? 'bg-[#b7953c]/15 text-[#b7953c] border-[#b7953c]/40 hover:bg-[#b7953c]/15' : ''}`}>
                          {selectedAgent.cancelled_reason === 'admin_deactivated' ? 'Deactivated by Admin' : selectedAgent.status === 'expired' ? 'Expired - Time Ended' : selectedAgent.status.charAt(0).toUpperCase() + selectedAgent.status.slice(1)}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Action */}
                  <div className="flex gap-3 pt-2">
                    <Button
                      variant={selectedAgent.status === 'active' ? 'destructive' : 'default'}
                      onClick={() => { const a = selectedAgent; setSelectedAgent(null); handleToggleAgentStatus(a); }}
                      className="flex-1"
                    >
                      {selectedAgent.status === 'active' ? 'Deactivate Agent' : 'Activate Agent'}
                    </Button>
                    <Button variant="outline" onClick={() => setSelectedAgent(null)} className="flex-1">
                      Close
                    </Button>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Confirm Activate Expired Agent Modal */}
        {confirmActivateAgent && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
            onClick={() => setConfirmActivateAgent(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-md w-full"
            >
              <div className="p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 rounded-full bg-yellow-500/10">
                    <Clock className="h-6 w-6 text-yellow-500" />
                  </div>
                  <h3 className="text-lg font-semibold">Reactivate Expired Agent</h3>
                </div>

                <div className="space-y-3 mb-6">
                  <p className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">{confirmActivateAgent.module_display_name}</span> for <span className="font-medium text-foreground">{confirmActivateAgent.company_name}</span> has expired.
                  </p>
                  <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                    <p className="text-sm text-yellow-600 font-medium">
                      The company has not made a new payment for this agent.
                    </p>
                    <p className="text-xs text-yellow-600/70 mt-1">
                      Reactivating will grant a new 30-day subscription without payment.
                    </p>
                  </div>
                  {confirmActivateAgent.time_ended_ago && (
                    <p className="text-xs text-muted-foreground">
                      Subscription {confirmActivateAgent.time_ended_ago.toLowerCase()}
                    </p>
                  )}
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setConfirmActivateAgent(null)}
                  >
                    Cancel
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={() => {
                      performToggleAgentStatus(confirmActivateAgent, 'active');
                      setConfirmActivateAgent(null);
                    }}
                  >
                    Reactivate Anyway
                  </Button>
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Message Detail Modal/Dialog */}
        {selectedMessage && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
            onClick={() => setSelectedMessage(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto"
            >
              <div className="p-4 sm:p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">Message Details</h2>
                  <Button variant="ghost" onClick={() => setSelectedMessage(null)} size="sm" className="shrink-0">
                    <span className="text-2xl">×</span>
                  </Button>
                </div>

                <div className="space-y-3 sm:space-y-4">
                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Name</label>
                    <p className="text-base sm:text-lg break-words">{selectedMessage.full_name}</p>
                  </div>

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Email</label>
                    <p className="break-all">
                      <a href={`mailto:${selectedMessage.email}`} className="text-primary hover:underline text-sm sm:text-base">
                        {selectedMessage.email}
                      </a>
                    </p>
                  </div>

                  {selectedMessage.phone && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Phone</label>
                      <p>
                        <a href={`tel:${selectedMessage.phone}`} className="text-primary hover:underline text-sm sm:text-base">
                          {selectedMessage.phone}
                        </a>
                      </p>
                    </div>
                  )}

                  {selectedMessage.project_title && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Project Title</label>
                      <p className="text-sm sm:text-base break-words">{selectedMessage.project_title}</p>
                    </div>
                  )}

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Message</label>
                    <p className="whitespace-pre-wrap text-sm sm:text-base break-words">{selectedMessage.message}</p>
                  </div>

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Submitted</label>
                    <p className="text-sm sm:text-base">{formatDate(selectedMessage.created_at)}</p>
                  </div>

                  {selectedMessage.attachment_path && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Attachment</label>
                      <div className="mt-2">
                        <a
                          href={getFileUrl(selectedMessage.attachment_path)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 text-xs sm:text-sm text-primary hover:underline"
                        >
                          <Download className="h-4 w-4" />
                          Download File
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Prediction Detail Modal/Dialog */}
        {selectedPrediction && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
            onClick={() => setSelectedPrediction(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto"
            >
              <div className="p-4 sm:p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">AI Prediction Details</h2>
                  <Button variant="ghost" onClick={() => setSelectedPrediction(null)} size="sm" className="shrink-0">
                    <span className="text-2xl">×</span>
                  </Button>
                </div>

                <div className="space-y-3 sm:space-y-4">
                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Email</label>
                    <p className="text-sm sm:text-base break-all">
                      {selectedPrediction.email && !selectedPrediction.email.includes('anonymous') ? (
                        <a href={`mailto:${selectedPrediction.email}`} className="text-primary hover:underline">
                          {selectedPrediction.email}
                        </a>
                      ) : (
                        <span className="text-muted-foreground">Anonymous</span>
                      )}
                    </p>
                  </div>

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Project Type</label>
                    <p className="text-sm sm:text-base break-words">{formatProjectType(selectedPrediction.project_type)}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Predicted Cost</label>
                      <p className="text-base sm:text-lg font-semibold text-blue-600 dark:text-blue-400">
                        ${selectedPrediction.predicted_cost?.toLocaleString() || 'N/A'}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Duration</label>
                      <p className="text-base sm:text-lg font-semibold text-green-600 dark:text-green-400">
                        {formatDuration(selectedPrediction.predicted_duration)}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Team Size</label>
                      <p className="text-base sm:text-lg font-semibold text-purple-600 dark:text-purple-400">
                        {selectedPrediction.predicted_team_size || 'N/A'}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Confidence</label>
                      <p className="text-base sm:text-lg font-semibold text-orange-600 dark:text-orange-400">
                        {selectedPrediction.prediction_confidence ? `${selectedPrediction.prediction_confidence}%` : 'N/A'}
                      </p>
                    </div>
                  </div>

                  {selectedPrediction.project_data && typeof selectedPrediction.project_data === 'object' && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Project Details</label>
                      <div className="mt-2 p-3 bg-secondary rounded-lg space-y-2 text-xs sm:text-sm">
                        {selectedPrediction.project_data.goal && (
                          <div>
                            <span className="font-medium">Goal: </span>
                            <span>{selectedPrediction.project_data.goal}</span>
                          </div>
                        )}
                        {selectedPrediction.project_data.coreFunctionality && (
                          <div>
                            <span className="font-medium">Core Functionality: </span>
                            <span>{selectedPrediction.project_data.coreFunctionality}</span>
                          </div>
                        )}
                        {selectedPrediction.project_data.qualityPriorities && selectedPrediction.project_data.qualityPriorities.length > 0 && (
                          <div>
                            <span className="font-medium">Quality Priorities: </span>
                            <span>{selectedPrediction.project_data.qualityPriorities.join(', ')}</span>
                          </div>
                        )}
                        {selectedPrediction.project_data.integrations && selectedPrediction.project_data.integrations.length > 0 && (
                          <div>
                            <span className="font-medium">Integrations: </span>
                            <span>{selectedPrediction.project_data.integrations.join(', ')}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Submitted</label>
                    <p className="text-sm sm:text-base">{formatDate(selectedPrediction.created_at)}</p>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Application Detail Modal/Dialog */}
        {selectedApplication && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
            onClick={() => setSelectedApplication(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto"
            >
              <div className="p-4 sm:p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">Application Details</h2>
                  <Button variant="ghost" onClick={() => setSelectedApplication(null)} size="sm" className="shrink-0">
                    <span className="text-2xl">×</span>
                  </Button>
                </div>

                <div className="space-y-3 sm:space-y-4">
                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Position</label>
                    <p className="text-base sm:text-lg font-semibold break-words">{selectedApplication.position_title}</p>
                  </div>

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Applicant Name</label>
                    <p className="text-base sm:text-lg break-words">{selectedApplication.applicant_name}</p>
                  </div>

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Email</label>
                    <p className="break-all">
                      <a href={`mailto:${selectedApplication.email}`} className="text-primary hover:underline text-sm sm:text-base">
                        {selectedApplication.email}
                      </a>
                    </p>
                  </div>

                  {selectedApplication.phone && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Phone</label>
                      <p>
                        <a href={`tel:${selectedApplication.phone}`} className="text-primary hover:underline text-sm sm:text-base">
                          {selectedApplication.phone}
                        </a>
                      </p>
                    </div>
                  )}

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Status</label>
                    <div className="mt-2">
                      <Badge className={`${getStatusColor(selectedApplication.status)} border`}>
                        {selectedApplication.status}
                      </Badge>
                    </div>
                  </div>

                  {selectedApplication.cover_letter && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Cover Letter</label>
                      <p className="whitespace-pre-wrap text-sm sm:text-base break-words mt-2 p-3 bg-secondary rounded-lg">
                        {selectedApplication.cover_letter}
                      </p>
                    </div>
                  )}

                  {selectedApplication.resume_path && (
                    <div>
                      <label className="text-xs sm:text-sm font-medium text-muted-foreground">Resume</label>
                      <div className="mt-2">
                        <a
                          href={getResumeUrl(selectedApplication.resume_path)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 text-xs sm:text-sm text-primary hover:underline"
                        >
                          <Download className="h-4 w-4" />
                          Download Resume
                        </a>
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground">Submitted</label>
                    <p className="text-sm sm:text-base">{formatDate(selectedApplication.created_at)}</p>
                  </div>

                  <div className="pt-4 border-t">
                    <label className="text-xs sm:text-sm font-medium text-muted-foreground mb-2 block">Update Status</label>
                    <div className="flex flex-wrap gap-2">
                      {['pending', 'reviewing', 'interview', 'accepted', 'rejected'].map((status) => (
                        <Button
                          key={status}
                          variant={selectedApplication.status === status ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => handleUpdateApplicationStatus(selectedApplication.id, status)}
                          disabled={selectedApplication.status === status}
                          className="capitalize"
                        >
                          {status}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Create Company Modal */}
        {showCreateCompanyModal && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-[100] overflow-y-auto"
            onClick={() => {
              console.log('Modal backdrop clicked');
              setShowCreateCompanyModal(false);
            }}
            style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0 }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => {
                e.stopPropagation();
                console.log('Modal content clicked');
              }}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto shadow-xl"
              style={{ 
                backgroundColor: 'hsl(var(--card))', 
                zIndex: 101,
                position: 'relative',
                margin: 'auto'
              }}
            >
              <div className="p-4 sm:p-6" style={{ position: 'relative', zIndex: 102 }}>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">Create New Company</h2>
                  <Button variant="ghost" onClick={() => setShowCreateCompanyModal(false)} size="sm" className="shrink-0">
                    <span className="text-2xl">×</span>
                  </Button>
                </div>

                <form onSubmit={handleCreateCompany} className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="sm:col-span-2">
                      <label className="text-sm font-medium">Company Name *</label>
                      <Input
                        value={companyForm.name}
                        onChange={(e) => setCompanyForm({ ...companyForm, name: e.target.value })}
                        required
                        placeholder="e.g., Acme Corporation"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Email *</label>
                      <Input
                        type="email"
                        value={companyForm.email}
                        onChange={(e) => setCompanyForm({ ...companyForm, email: e.target.value })}
                        required
                        placeholder="e.g., contact@acmecorp.com"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Phone</label>
                      <Input
                        value={companyForm.phone}
                        onChange={(e) => setCompanyForm({ ...companyForm, phone: e.target.value })}
                        placeholder="e.g., +1 (555) 123-4567"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-sm font-medium">Address</label>
                      <Input
                        value={companyForm.address}
                        onChange={(e) => setCompanyForm({ ...companyForm, address: e.target.value })}
                        placeholder="e.g., 123 Main Street, Suite 400, New York, NY 10001"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Website</label>
                      <Input
                        value={companyForm.website}
                        onChange={(e) => setCompanyForm({ ...companyForm, website: e.target.value })}
                        placeholder="e.g., https://www.acmecorp.com"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Industry</label>
                      <Input
                        value={companyForm.industry}
                        onChange={(e) => setCompanyForm({ ...companyForm, industry: e.target.value })}
                        placeholder="e.g., Technology, Healthcare, Finance"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Company Size</label>
                      <Input
                        value={companyForm.companySize}
                        onChange={(e) => setCompanyForm({ ...companyForm, companySize: e.target.value })}
                        placeholder="e.g., 50, 50-100, 200+"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-sm font-medium">Description</label>
                      <Textarea
                        value={companyForm.description}
                        onChange={(e) => setCompanyForm({ ...companyForm, description: e.target.value })}
                        placeholder="e.g., Acme Corporation is a leading provider of innovative software solutions specializing in..."
                        className="min-h-[100px]"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2 pt-4">
                    <Button type="submit" className="flex-1" disabled={companySubmitting}>
                      {companySubmitting ? 'Creating...' : 'Create Company'}
                    </Button>
                    <Button type="button" variant="outline" onClick={() => setShowCreateCompanyModal(false)} disabled={companySubmitting}>
                      Cancel
                    </Button>
                  </div>
                </form>
              </div>
            </motion.div>
          </div>
        )}

        {/* Company Details Modal */}
        {selectedCompany && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-3 sm:p-4 z-50 overflow-y-auto"
            onClick={() => setSelectedCompany(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-card border rounded-lg max-w-2xl w-full max-h-[95vh] sm:max-h-[90vh] my-auto overflow-y-auto"
            >
              <div className="p-4 sm:p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl sm:text-2xl font-bold">{selectedCompany.name}</h2>
                  <Button variant="ghost" onClick={() => setSelectedCompany(null)} size="sm" className="shrink-0">
                    <span className="text-2xl">×</span>
                  </Button>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Email</label>
                    <p className="text-base">{selectedCompany.email}</p>
                  </div>
                  {selectedCompany.phone && (
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">Phone</label>
                      <p className="text-base">{selectedCompany.phone}</p>
                    </div>
                  )}
                  {selectedCompany.website && (
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">Website</label>
                      <p className="text-base">
                        <a href={selectedCompany.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                          {selectedCompany.website}
                        </a>
                      </p>
                    </div>
                  )}
                  {selectedCompany.industry && (
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">Industry</label>
                      <p className="text-base">{selectedCompany.industry}</p>
                    </div>
                  )}
                  <div className="flex gap-4">
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">Users</label>
                      <p className="text-base font-semibold">{selectedCompany.user_count || 0}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-muted-foreground">Jobs Posted</label>
                      <p className="text-base font-semibold">{selectedCompany.job_count || 0}</p>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </>
  );
};

export default AdminDashboardPage;

