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
    
    // Validate required fields
    if (!companyForm.name || !companyForm.email) {
      toast({
        title: '❌ Validation Error',
        description: 'Name and Email are required fields',
        variant: 'destructive',
      });
      return;
    }
    
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

  useEffect(() => {
    if (activeTab === 'contact') {
      fetchMessages();
    } else if (activeTab === 'predictions') {
      fetchPredictions();
    } else if (activeTab === 'applications') {
      fetchApplications();
    } else if (activeTab === 'companies') {
      fetchCompanies();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, pagination.page, statusFilter, searchTerm, predictionsPagination.page, predictionsSearchTerm, applicationsPagination.page, applicationsSearchTerm, applicationsStatusFilter, companiesPagination.page, companiesSearchTerm, fetchCompanies]);

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
    const apiBaseUrl = import.meta.env.VITE_API_URL || 'https://aiemployeemine.onrender.com/api';
    return `${apiBaseUrl.replace('/api', '')}/${attachmentPath}`;
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
    const apiBaseUrl = import.meta.env.VITE_API_URL || 'https://aiemployeemine.onrender.com';
    return `${apiBaseUrl.replace('/api', '')}/${resumePath}`;
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
            <TabsList className="grid w-full grid-cols-2 md:grid-cols-4 gap-2 mb-6 h-auto p-2">
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
          </Tabs>
        </div>

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
                        placeholder="Enter company name"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Email *</label>
                      <Input
                        type="email"
                        value={companyForm.email}
                        onChange={(e) => setCompanyForm({ ...companyForm, email: e.target.value })}
                        required
                        placeholder="company@example.com"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Phone</label>
                      <Input
                        value={companyForm.phone}
                        onChange={(e) => setCompanyForm({ ...companyForm, phone: e.target.value })}
                        placeholder="+1234567890"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-sm font-medium">Address</label>
                      <Input
                        value={companyForm.address}
                        onChange={(e) => setCompanyForm({ ...companyForm, address: e.target.value })}
                        placeholder="Company address"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Website</label>
                      <Input
                        value={companyForm.website}
                        onChange={(e) => setCompanyForm({ ...companyForm, website: e.target.value })}
                        placeholder="https://company.com"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Industry</label>
                      <Input
                        value={companyForm.industry}
                        onChange={(e) => setCompanyForm({ ...companyForm, industry: e.target.value })}
                        placeholder="e.g., Technology"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Company Size</label>
                      <Input
                        value={companyForm.companySize}
                        onChange={(e) => setCompanyForm({ ...companyForm, companySize: e.target.value })}
                        placeholder="e.g., 50-100"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-sm font-medium">Description</label>
                      <Textarea
                        value={companyForm.description}
                        onChange={(e) => setCompanyForm({ ...companyForm, description: e.target.value })}
                        placeholder="Company description"
                        className="min-h-[100px]"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2 pt-4">
                    <Button type="submit" className="flex-1">
                      Create Company
                    </Button>
                    <Button type="button" variant="outline" onClick={() => setShowCreateCompanyModal(false)}>
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

