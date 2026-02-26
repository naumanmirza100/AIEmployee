import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/use-toast';
import { 
  Loader2, 
  ArrowLeft, 
  Mail, 
  Plus, 
  Pencil, 
  Trash2, 
  Send,
  CheckCircle2,
  XCircle,
  AlertCircle,
  MoreVertical,
  Shield,
  Server,
  Lock,
  Globe,
  RefreshCw,
  CheckCheck,
  Eye,
  EyeOff,
  Copy,
  Settings,
  Inbox,
  MailCheck,
  MailWarning,
  Clock,
  Sparkles
} from 'lucide-react';
import {
  listEmailAccounts,
  createEmailAccount,
  getEmailAccount,
  updateEmailAccount,
  deleteEmailAccount,
  testEmailAccount,
} from '@/services/marketingAgentService';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

const ACCOUNT_TYPES = [
  { value: 'gmail', label: 'Gmail', icon: Mail, color: 'text-red-500', bgColor: 'bg-red-500/10' },
  { value: 'outlook', label: 'Outlook', icon: Mail, color: 'text-blue-500', bgColor: 'bg-blue-500/10' },
  { value: 'hostinger', label: 'Hostinger', icon: Server, color: 'text-purple-500', bgColor: 'bg-purple-500/10' },
  { value: 'smtp', label: 'Custom SMTP', icon: Settings, color: 'text-slate-500', bgColor: 'bg-slate-500/10' },
];

const SMTP_DEFAULTS = {
  gmail: { host: 'smtp.gmail.com', port: 587, useTLS: true, useSSL: false },
  outlook: { host: 'smtp-mail.outlook.com', port: 587, useTLS: true, useSSL: false },
  hostinger: { host: 'smtp.hostinger.com', port: 587, useTLS: true, useSSL: false },
  smtp: { host: '', port: 587, useTLS: true, useSSL: false },
};

const defaultForm = () => ({
  name: '',
  account_type: 'smtp',
  email: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  use_tls: true,
  use_ssl: false,
  is_gmail_app_password: false,
  is_active: true,
  is_default: false,
  enable_imap_sync: false,
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
});

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  }
};

const tableRowVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: {
    opacity: 1,
    x: 0,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  },
  hover: {
    scale: 1.01,
    backgroundColor: "rgba(var(--primary), 0.02)",
    transition: { duration: 0.2 }
  }
};

const EmailAccountsPage = () => {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(defaultForm());
  const [actionLoading, setActionLoading] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [testAccountId, setTestAccountId] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [showImap, setShowImap] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [activeTab, setActiveTab] = useState('all');

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listEmailAccounts();
      if (res?.status === 'success' && res?.data) {
        setAccounts(res.data);
      } else {
        setError(res?.message || 'Failed to load accounts');
      }
    } catch (e) {
      setError(e?.message || 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const applyTypeDefaults = (accountType) => {
    const d = SMTP_DEFAULTS[accountType] || SMTP_DEFAULTS.smtp;
    setForm((prev) => ({
      ...prev,
      account_type: accountType,
      smtp_host: d.host,
      smtp_port: d.port,
      use_tls: d.useTLS,
      use_ssl: d.useSSL,
      is_gmail_app_password: accountType === 'gmail',
    }));
  };

  const openAdd = () => {
    setEditingId(null);
    setForm(defaultForm());
    applyTypeDefaults('smtp');
    setShowImap(false);
    setModalOpen(true);
  };

  const openEdit = async (id) => {
    setEditingId(id);
    setModalOpen(true);
    try {
      const res = await getEmailAccount(id);
      if (res?.status === 'success' && res?.data) {
        const d = res.data;
        setForm({
          name: d.name || '',
          account_type: d.account_type || 'smtp',
          email: d.email || '',
          smtp_host: d.smtp_host || '',
          smtp_port: d.smtp_port ?? 587,
          smtp_username: d.smtp_username || '',
          smtp_password: '',
          use_tls: d.use_tls ?? true,
          use_ssl: d.use_ssl ?? false,
          is_gmail_app_password: d.is_gmail_app_password ?? false,
          is_active: d.is_active ?? true,
          is_default: d.is_default ?? false,
          enable_imap_sync: d.enable_imap_sync ?? false,
          imap_host: d.imap_host || '',
          imap_port: d.imap_port ?? 993,
          imap_username: d.imap_username || '',
          imap_password: '',
          imap_use_ssl: d.imap_use_ssl ?? true,
        });
        setShowImap(d.enable_imap_sync ?? false);
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Failed to load account', variant: 'destructive' });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name?.trim()) {
      toast({ title: 'Validation', description: 'Account name is required.', variant: 'destructive' });
      return;
    }
    if (!form.email?.trim()) {
      toast({ title: 'Validation', description: 'Email is required.', variant: 'destructive' });
      return;
    }
    if (!form.smtp_host?.trim()) {
      toast({ title: 'Validation', description: 'SMTP host is required.', variant: 'destructive' });
      return;
    }
    if (!editingId && !form.smtp_password) {
      toast({ title: 'Validation', description: 'SMTP password is required for new account.', variant: 'destructive' });
      return;
    }
    setActionLoading(true);
    try {
      const payload = {
        name: form.name.trim(),
        account_type: form.account_type,
        email: form.email.trim(),
        smtp_host: form.smtp_host.trim(),
        smtp_port: Number(form.smtp_port) || 587,
        smtp_username: (form.smtp_username || '').trim() || form.email.trim(),
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
        is_gmail_app_password: form.is_gmail_app_password,
        is_active: form.is_active,
        is_default: form.is_default,
        enable_imap_sync: form.enable_imap_sync,
        imap_host: form.imap_host || '',
        imap_port: form.imap_port ? Number(form.imap_port) : null,
        imap_username: form.imap_username || '',
        imap_use_ssl: form.imap_use_ssl,
      };
      if (form.smtp_password) payload.smtp_password = form.smtp_password;
      if (form.imap_password) payload.imap_password = form.imap_password;

      if (editingId) {
        const res = await updateEmailAccount(editingId, payload);
        if (res?.status === 'success') {
          toast({ 
            title: '✅ Account updated', 
            description: res?.data?.message || 'Account updated successfully.' 
          });
          setModalOpen(false);
          fetchAccounts();
        } else {
          toast({ title: 'Error', description: res?.message || 'Update failed.', variant: 'destructive' });
        }
      } else {
        const res = await createEmailAccount(payload);
        if (res?.status === 'success') {
          toast({ 
            title: '✅ Account created', 
            description: res?.data?.message || 'Account created successfully.' 
          });
          setModalOpen(false);
          fetchAccounts();
        } else {
          toast({ title: 'Error', description: res?.message || 'Create failed.', variant: 'destructive' });
        }
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Request failed.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (id, name) => {
    setActionLoading(true);
    try {
      const res = await deleteEmailAccount(id);
      if (res?.status === 'success') {
        toast({ 
          title: '✅ Account deleted', 
          description: res?.data?.message || 'Account deleted successfully.' 
        });
        setDeleteConfirm(null);
        fetchAccounts();
      } else {
        toast({ title: 'Error', description: res?.message || 'Delete failed.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e?.message || 'Delete failed.', variant: 'destructive' });
    } finally {
      setActionLoading(false);
    }
  };

  const openTest = (account) => {
    setTestAccountId(account.id);
    setTestEmail(account.email || '');
    setTestModalOpen(true);
  };

  const handleTest = async () => {
    const email = (testEmail || '').trim();
    if (!email) {
      toast({ title: 'Validation', description: 'Enter test email address.', variant: 'destructive' });
      return;
    }
    setTestLoading(true);
    try {
      const res = await testEmailAccount(testAccountId, email);
      if (res?.status === 'success') {
        toast({ 
          title: '✅ Test successful', 
          description: res?.data?.message || 'Test email sent successfully.' 
        });
        setTestModalOpen(false);
        fetchAccounts();
      } else {
        toast({ title: 'Test failed', description: res?.message || 'Could not send test email.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Test failed', description: e?.message || e?.data?.message || 'Could not send test email.', variant: 'destructive' });
    } finally {
      setTestLoading(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast({ 
      title: 'Copied!', 
      description: 'Email address copied to clipboard.' 
    });
  };

  const accountTypeLabel = (type) => ACCOUNT_TYPES.find((t) => t.value === type)?.label || type;
  
  const getAccountIcon = (type) => {
    const found = ACCOUNT_TYPES.find(t => t.value === type);
    return found ? found.icon : Mail;
  };

  const getTestStatusIcon = (status) => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
      case 'failed':
        return <XCircle className="h-3.5 w-3.5 text-rose-500" />;
      default:
        return <Clock className="h-3.5 w-3.5 text-slate-400" />;
    }
  };

  const filteredAccounts = accounts.filter(account => {
    if (activeTab === 'all') return true;
    if (activeTab === 'active') return account.is_active;
    if (activeTab === 'inactive') return !account.is_active;
    if (activeTab === 'default') return account.is_default;
    return true;
  });

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        >
          <Loader2 className="h-12 w-12 text-primary" />
        </motion.div>
        <p className="mt-4 text-sm text-muted-foreground">Loading email accounts...</p>
      </div>
    );
  }

  return (
    <motion.div 
      className="space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Header with gradient */}
      <motion.div 
        variants={itemVariants}
        className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary/10 via-primary/5 to-background p-6"
      >
        <div className="relative z-10">
          <Button variant="ghost" size="sm" asChild className="mb-4 hover:bg-primary/10">
            <Link to="/marketing/dashboard" className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back to dashboard
            </Link>
          </Button>
          
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <motion.div 
                whileHover={{ rotate: 15, scale: 1.1 }}
                className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/20"
              >
                <Mail className="h-7 w-7 text-primary" />
              </motion.div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-foreground">Email Accounts</h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Manage SMTP accounts for sending campaign emails and tracking replies
                </p>
              </div>
            </div>
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Button onClick={openAdd} size="lg" className="gap-2 bg-primary hover:bg-primary/90">
                <Plus className="h-4 w-4" />
                {/* Add Email Account */}
              </Button>
            </motion.div>
          </div>
        </div>
        <div className="absolute inset-0 bg-grid-white/5 [mask-image:radial-gradient(ellipse_at_center,white,transparent)]" />
      </motion.div>

      {error && (
        <motion.div variants={itemVariants}>
          <Card className="border-destructive/50 bg-destructive/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3 text-destructive">
                <AlertCircle className="h-5 w-5" />
                <p className="text-sm">{error}</p>
                <Button variant="outline" size="sm" onClick={fetchAccounts} className="ml-auto">
                  <RefreshCw className="h-3 w-3 mr-2" />
                  Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {accounts.length === 0 && !error ? (
        <motion.div variants={itemVariants}>
          <Card className="border-0 shadow-lg overflow-hidden">
            <CardContent className="pt-12 pb-12">
              <div className="text-center max-w-md mx-auto">
                <motion.div
                  animate={{
                    scale: [1, 1.1, 1],
                    rotate: [0, 5, -5, 0]
                  }}
                  transition={{
                    duration: 3,
                    repeat: Infinity,
                    repeatType: "reverse"
                  }}
                  className="mb-6"
                >
                  <div className="flex justify-center">
                    <Mail className="h-16 w-16 text-muted-foreground/30" />
                  </div>
                </motion.div>
                <h3 className="text-xl font-semibold mb-2">No email accounts yet</h3>
                <p className="text-muted-foreground mb-6">
                  Add your first email account to start sending campaigns and tracking performance.
                </p>
                <Button onClick={openAdd} size="lg" className="gap-2">
                  <Plus className="h-4 w-4" />
                  {/* Add Email Account */}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ) : (
        <motion.div variants={itemVariants}>
          <Card className="overflow-hidden border-0 shadow-lg">
            <CardHeader className="bg-gradient-to-r from-primary/5 via-transparent to-transparent border-b pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <MailCheck className="h-5 w-5 text-primary" />
                    Configured Accounts
                  </CardTitle>
                  <CardDescription>
                    {accounts.length} account{accounts.length !== 1 ? 's' : ''} configured
                  </CardDescription>
                </div>
                
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full sm:w-auto">
                  <TabsList className="grid grid-cols-4 w-full sm:w-[400px]">
                    <TabsTrigger value="all" className="text-xs sm:text-sm">All</TabsTrigger>
                    <TabsTrigger value="active" className="text-xs sm:text-sm">Active</TabsTrigger>
                    <TabsTrigger value="inactive" className="text-xs sm:text-sm">Inactive</TabsTrigger>
                    <TabsTrigger value="default" className="text-xs sm:text-sm">Default</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left font-semibold p-4 text-muted-foreground">Account</th>
                      <th className="text-left font-semibold p-4 text-muted-foreground">Type</th>
                      <th className="text-center font-semibold p-4 text-muted-foreground">Status</th>
                      <th className="text-center font-semibold p-4 text-muted-foreground">Test</th>
                      <th className="text-center font-semibold p-4 text-muted-foreground">Default</th>
                      <th className="text-right font-semibold p-4 text-muted-foreground">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence>
                      {filteredAccounts.map((account, index) => {
                        const Icon = getAccountIcon(account.account_type);
                        const typeConfig = ACCOUNT_TYPES.find(t => t.value === account.account_type);
                        
                        return (
                          <motion.tr
                            key={account.id}
                            variants={tableRowVariants}
                            initial="hidden"
                            animate="visible"
                            whileHover="hover"
                            exit={{ opacity: 0, x: -20 }}
                            transition={{ delay: index * 0.05 }}
                            className="border-b last:border-0 group"
                          >
                            <td className="p-4">
                              <div className="flex items-center gap-3">
                                <div className={cn(
                                  "rounded-lg p-2",
                                  typeConfig?.bgColor || 'bg-muted'
                                )}>
                                  <Icon className={cn("h-4 w-4", typeConfig?.color)} />
                                </div>
                                <div>
                                  <p className="font-medium text-foreground">{account.name}</p>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className="text-xs text-muted-foreground">{account.email}</span>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity"
                                      onClick={() => copyToClipboard(account.email)}
                                    >
                                      <Copy className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            </td>
                            
                            <td className="p-4">
                              <Badge variant="outline" className={cn(
                                "font-medium",
                                typeConfig?.bgColor,
                                typeConfig?.color
                              )}>
                                {accountTypeLabel(account.account_type)}
                              </Badge>
                            </td>
                            
                            <td className="p-4 text-center">
                              <Badge 
                                variant={account.is_active ? 'default' : 'secondary'}
                                className={cn(
                                  "gap-1",
                                  account.is_active ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800' : ''
                                )}
                              >
                                {account.is_active ? (
                                  <CheckCircle2 className="h-3 w-3" />
                                ) : (
                                  <XCircle className="h-3 w-3" />
                                )}
                                {account.is_active ? 'Active' : 'Inactive'}
                              </Badge>
                            </td>
                            
                            <td className="p-4 text-center">
                              <div className="flex items-center justify-center gap-2">
                                {getTestStatusIcon(account.test_status)}
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "font-medium",
                                    account.test_status === 'success' && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
                                    account.test_status === 'failed' && 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800'
                                  )}
                                >
                                  {account.test_status === 'success' ? 'Success' : 
                                   account.test_status === 'failed' ? 'Failed' : 'Not tested'}
                                </Badge>
                              </div>
                            </td>
                            
                            <td className="p-4 text-center">
                              {account.is_default ? (
                                <Badge variant="default" className="gap-1 bg-primary/10 text-primary border-primary/20">
                                  <CheckCheck className="h-3 w-3" />
                                  Default
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground text-xs">—</span>
                              )}
                            </td>
                            
                            <td className="p-4 text-right">
                              <div className="flex justify-end gap-2">
                                <Button 
                                  variant="outline" 
                                  size="sm" 
                                  onClick={() => openTest(account)}
                                  className="gap-1.5"
                                >
                                  <Send className="h-3.5 w-3.5" />
                                  <span className="hidden sm:inline">Test</span>
                                </Button>
                                
                                <Button 
                                  variant="outline" 
                                  size="sm" 
                                  onClick={() => openEdit(account.id)}
                                  className="gap-1.5"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                  <span className="hidden sm:inline">Edit</span>
                                </Button>
                                
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="outline" size="sm" className="px-2">
                                      <MoreVertical className="h-4 w-4" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuItem 
                                      onClick={() => openTest(account)}
                                      className="gap-2"
                                    >
                                      <Send className="h-4 w-4" />
                                      Send Test
                                    </DropdownMenuItem>
                                    <DropdownMenuItem 
                                      onClick={() => openEdit(account.id)}
                                      className="gap-2"
                                    >
                                      <Pencil className="h-4 w-4" />
                                      Edit Account
                                    </DropdownMenuItem>
                                    <DropdownMenuItem 
                                      onClick={() => setDeleteConfirm({ id: account.id, name: account.name })}
                                      className="gap-2 text-destructive focus:text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                      Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Add/Edit modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto p-0">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <DialogHeader className="px-6 pt-6 pb-2 bg-gradient-to-r from-primary/5 via-transparent to-transparent">
              <DialogTitle className="text-xl flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  {editingId ? <Pencil className="h-4 w-4 text-primary" /> : <Plus className="h-4 w-4 text-primary" />}
                </div>
                {editingId ? 'Edit Email Account' : 'Add Email Account'}
              </DialogTitle>
              <DialogDescription>
                {editingId 
                  ? 'Update your SMTP settings. Leave password blank to keep existing.'
                  : 'Configure SMTP settings for sending campaign emails.'}
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="px-6 py-4">
              <div className="space-y-5">
                {/* Basic Information */}
                <div className="space-y-4">
                  <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                    <Mail className="h-4 w-4" />
                    Basic Information
                  </h3>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Account Name *</Label>
                      <Input
                        value={form.name}
                        onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                        placeholder="e.g. Main Gmail"
                        className="h-10"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Account Type</Label>
                      <Select value={form.account_type} onValueChange={applyTypeDefaults}>
                        <SelectTrigger className="h-10">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ACCOUNT_TYPES.map((t) => (
                            <SelectItem key={t.value} value={t.value}>
                              <div className="flex items-center gap-2">
                                <t.icon className={cn("h-4 w-4", t.color)} />
                                <span>{t.label}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Email Address *</Label>
                    <Input
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
                      placeholder="your@email.com"
                      className="h-10"
                    />
                  </div>
                </div>

                {/* SMTP Settings */}
                <div className="space-y-4 pt-2 border-t">
                  <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                    <Server className="h-4 w-4" />
                    SMTP Settings
                  </h3>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>SMTP Host *</Label>
                      <Input
                        value={form.smtp_host}
                        onChange={(e) => setForm((p) => ({ ...p, smtp_host: e.target.value }))}
                        placeholder="smtp.gmail.com"
                        className="h-10"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>SMTP Port</Label>
                      <Input
                        type="number"
                        min={1}
                        max={65535}
                        value={form.smtp_port}
                        onChange={(e) => setForm((p) => ({ ...p, smtp_port: e.target.value }))}
                        className="h-10"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>SMTP Username *</Label>
                      <Input
                        value={form.smtp_username}
                        onChange={(e) => setForm((p) => ({ ...p, smtp_username: e.target.value }))}
                        placeholder="Usually same as email"
                        className="h-10"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>SMTP Password * {editingId && '(leave blank to keep)'}</Label>
                      <div className="relative">
                        <Input
                          type={showPassword ? 'text' : 'password'}
                          value={form.smtp_password}
                          onChange={(e) => setForm((p) => ({ ...p, smtp_password: e.target.value }))}
                          placeholder="••••••••"
                          className="h-10 pr-10"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
                          onClick={() => setShowPassword(!showPassword)}
                        >
                          {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-6 pt-2">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={form.use_tls}
                        onCheckedChange={(checked) => setForm((p) => ({ ...p, use_tls: checked }))}
                        id="use-tls"
                      />
                      <Label htmlFor="use-tls" className="text-sm cursor-pointer">Use TLS</Label>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={form.use_ssl}
                        onCheckedChange={(checked) => setForm((p) => ({ ...p, use_ssl: checked }))}
                        id="use-ssl"
                      />
                      <Label htmlFor="use-ssl" className="text-sm cursor-pointer">Use SSL</Label>
                    </div>
                    
                    {form.account_type === 'gmail' && (
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={form.is_gmail_app_password}
                          onCheckedChange={(checked) => setForm((p) => ({ ...p, is_gmail_app_password: checked }))}
                          id="app-password"
                        />
                        <Label htmlFor="app-password" className="text-sm cursor-pointer flex items-center gap-1">
                          <Lock className="h-3 w-3" />
                          Gmail App Password
                        </Label>
                      </div>
                    )}
                  </div>
                </div>

                {/* Account Status */}
                <div className="space-y-4 pt-2 border-t">
                  <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                    <Shield className="h-4 w-4" />
                    Account Status
                  </h3>

                  <div className="flex flex-wrap gap-6">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={form.is_active}
                        onCheckedChange={(checked) => setForm((p) => ({ ...p, is_active: checked }))}
                        id="is-active"
                      />
                      <Label htmlFor="is-active" className="text-sm cursor-pointer">Active (can send emails)</Label>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={form.is_default}
                        onCheckedChange={(checked) => setForm((p) => ({ ...p, is_default: checked }))}
                        id="is-default"
                      />
                      <Label htmlFor="is-default" className="text-sm cursor-pointer">Default account</Label>
                    </div>
                  </div>
                </div>

                {/* IMAP Settings */}
                <div className="space-y-4 pt-2 border-t">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold flex items-center gap-2 text-muted-foreground">
                      <Inbox className="h-4 w-4" />
                      IMAP Settings (for reply detection)
                    </h3>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={form.enable_imap_sync}
                        onCheckedChange={(checked) => {
                          setForm((p) => ({ ...p, enable_imap_sync: checked }));
                          setShowImap(checked);
                        }}
                        id="enable-imap"
                      />
                      <Label htmlFor="enable-imap" className="text-sm cursor-pointer">Enable</Label>
                    </div>
                  </div>

                  <AnimatePresence>
                    {showImap && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="space-y-4 overflow-hidden"
                      >
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label>IMAP Host</Label>
                            <Input
                              placeholder="imap.gmail.com"
                              value={form.imap_host}
                              onChange={(e) => setForm((p) => ({ ...p, imap_host: e.target.value }))}
                              className="h-10"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>IMAP Port</Label>
                            <Input
                              type="number"
                              placeholder="993"
                              value={form.imap_port}
                              onChange={(e) => setForm((p) => ({ ...p, imap_port: e.target.value }))}
                              className="h-10"
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label>IMAP Username</Label>
                            <Input
                              placeholder="Usually same as email"
                              value={form.imap_username}
                              onChange={(e) => setForm((p) => ({ ...p, imap_username: e.target.value }))}
                              className="h-10"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label>IMAP Password</Label>
                            <Input
                              type="password"
                              placeholder="••••••••"
                              value={form.imap_password}
                              onChange={(e) => setForm((p) => ({ ...p, imap_password: e.target.value }))}
                              className="h-10"
                            />
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <Switch
                            checked={form.imap_use_ssl}
                            onCheckedChange={(checked) => setForm((p) => ({ ...p, imap_use_ssl: checked }))}
                            id="imap-ssl"
                          />
                          <Label htmlFor="imap-ssl" className="text-sm cursor-pointer">IMAP use SSL</Label>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              <DialogFooter className="mt-6 pt-4 border-t">
                <Button type="button" variant="outline" onClick={() => setModalOpen(false)} className="gap-2">
                  Cancel
                </Button>
                <Button type="submit" disabled={actionLoading} className="gap-2 min-w-[100px]">
                  {actionLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : editingId ? (
                    <>
                      <Pencil className="h-4 w-4" />
                      Save Changes
                    </>
                  ) : (
                    <>
                      <Plus className="h-4 w-4" />
                      Create Account
                    </>
                  )}
                </Button>
              </DialogFooter>
            </form>
          </motion.div>
        </DialogContent>
      </Dialog>

      {/* Test modal */}
      <Dialog open={testModalOpen} onOpenChange={setTestModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-5 w-5 text-primary" />
              Send Test Email
            </DialogTitle>
            <DialogDescription>
              Enter the recipient address to verify this account is working correctly.
            </DialogDescription>
          </DialogHeader>
          
          <div className="py-4">
            <Label>Test Email Address</Label>
            <Input
              type="email"
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="recipient@example.com"
              className="mt-1.5"
            />
            <p className="text-xs text-muted-foreground mt-2">
              A test email will be sent to verify SMTP configuration.
            </p>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setTestModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleTest} disabled={testLoading} className="gap-2">
              {testLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Send Test
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm modal */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="h-5 w-5" />
              Delete Email Account?
            </DialogTitle>
            <DialogDescription>
              This will permanently delete <span className="font-semibold text-foreground">&quot;{deleteConfirm?.name}&quot;</span>. 
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          
          <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <p>All campaigns using this account will need to be reconfigured with a different email account.</p>
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={actionLoading}
              onClick={() => deleteConfirm && handleDelete(deleteConfirm.id, deleteConfirm.name)}
              className="gap-2"
            >
              {actionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  Delete Account
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};

export default EmailAccountsPage;