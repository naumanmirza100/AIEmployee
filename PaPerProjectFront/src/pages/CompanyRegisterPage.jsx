import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { companyAuthService } from '@/services';
import { Building2, Loader2, CheckCircle2 } from 'lucide-react';

const CompanyRegisterPage = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [companyData, setCompanyData] = useState(null);
  const [formData, setFormData] = useState({
    password: '',
    confirmPassword: '',
  });

  useEffect(() => {
    if (!token) {
      toast({
        title: 'Error',
        description: 'Invalid registration link. No token provided.',
        variant: 'destructive',
      });
      navigate('/');
      return;
    }

    verifyToken();
  }, [token]);

  const verifyToken = async () => {
    try {
      setLoading(true);
      console.log('Verifying token:', token);
      const response = await companyAuthService.verifyToken(token);
      console.log('Verify token response:', response);
      
      if (response.status === 'success' && response.data.valid) {
        // Backend returns companyName and companyId, not company object
        setCompanyData({
          name: response.data.companyName,
          id: response.data.companyId,
          email: response.data.companyEmail,
        });
      } else {
        throw new Error(response.message || 'Invalid token');
      }
    } catch (error) {
      console.error('Token verification error:', error);
      toast({
        title: 'Error',
        description: error.message || 'Invalid or expired registration token',
        variant: 'destructive',
      });
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (formData.password !== formData.confirmPassword) {
      toast({
        title: 'Error',
        description: 'Passwords do not match',
        variant: 'destructive',
      });
      return;
    }

    if (formData.password.length < 8) {
      toast({
        title: 'Error',
        description: 'Password must be at least 8 characters long',
        variant: 'destructive',
      });
      return;
    }

    try {
      setSubmitting(true);
      const response = await companyAuthService.registerCompany({
        token,
        password: formData.password,
        role: 'admin',
      });

      if (response.status === 'success') {
        // Store company user data and authentication token
        if (response.data.user) {
          localStorage.setItem('company_user', JSON.stringify(response.data.user));
        } else {
          // Fallback: if user data is at root level
          localStorage.setItem('company_user', JSON.stringify({
            id: response.data.id,
            email: response.data.email,
            companyId: response.data.companyId,
            companyName: response.data.companyName,
            fullName: response.data.fullName || '',
            role: response.data.role || 'admin',
          }));
        }
        
        // Store authentication token for API calls
        if (response.data.token) {
          localStorage.setItem('company_auth_token', response.data.token);
        }
        
        toast({
          title: 'Success!',
          description: 'Company account registered successfully',
        });
        
        // Redirect to company dashboard
        navigate('/company/dashboard');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to register account',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Invalid Link</CardTitle>
            <CardDescription>The registration link is invalid or expired</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <>
      <Helmet>
        <title>Register Company Account | Pay Per Project</title>
      </Helmet>
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          <Card>
            <CardHeader className="text-center">
              <Building2 className="h-12 w-12 mx-auto text-primary mb-4" />
              <CardTitle>Set your password</CardTitle>
              <CardDescription>
                Choose a password to finish setting up <strong>{companyData.name}</strong>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                {companyData.email && (
                  <div className="rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-sm">
                    <span className="text-muted-foreground">Account email: </span>
                    <span className="font-medium text-foreground">{companyData.email}</span>
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="password">New Password *</Label>
                  <Input
                    id="password"
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                    minLength={8}
                    placeholder="At least 8 characters"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm Password *</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    value={formData.confirmPassword}
                    onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                    required
                    placeholder="Confirm your password"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Registering...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                      Complete Registration
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </>
  );
};

export default CompanyRegisterPage;

