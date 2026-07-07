import React, { useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { companyAuthService } from '@/services';
import { Building2, Loader2, UserPlus, MailCheck, ArrowLeft } from 'lucide-react';

const initialForm = {
  name: '',
  email: '',
  phone: '',
  address: '',
  website: '',
  industry: '',
  company_size: '',
  description: '',
};

const CompanySignupPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.phone) {
      toast({
        title: 'Missing fields',
        description: 'Company name, email, and phone are required.',
        variant: 'destructive',
      });
      return;
    }
    try {
      setLoading(true);
      const res = await companyAuthService.signupCompany(form);
      toast({
        title: 'Account created',
        description: res.message || 'Check your email for a setup link.',
      });
      setDone(true);
    } catch (error) {
      toast({
        title: 'Signup failed',
        description: error.message || 'Could not create your account',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Helmet>
        <title>Company Sign Up | Pay Per Project</title>
      </Helmet>
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-lg"
        >
          <Card>
            {done ? (
              <>
                <CardHeader className="text-center">
                  <MailCheck className="h-12 w-12 mx-auto text-primary mb-4" />
                  <CardTitle>Check your email</CardTitle>
                  <CardDescription>
                    We've sent a setup link to <span className="font-medium text-foreground">{form.email}</span>.
                    Open it to choose your password and get your login credentials.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button className="w-full" onClick={() => navigate('/company/login')}>
                    Go to Login
                  </Button>
                </CardContent>
              </>
            ) : (
              <>
                <CardHeader className="text-center">
                  <Building2 className="h-12 w-12 mx-auto text-primary mb-4" />
                  <CardTitle>Create your Company Account</CardTitle>
                  <CardDescription>
                    Fill in your company details. We'll email you a link to set your password.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="name">Company Name <span className="text-red-500">*</span></Label>
                        <Input id="name" value={form.name} onChange={setField('name')} required placeholder="Acme Inc." />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email">Email <span className="text-red-500">*</span></Label>
                        <Input id="email" type="email" value={form.email} onChange={setField('email')} required placeholder="company@example.com" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="phone">Phone <span className="text-red-500">*</span></Label>
                        <Input id="phone" value={form.phone} onChange={setField('phone')} required placeholder="+1 234 567 8900" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="website">Website</Label>
                        <Input id="website" value={form.website} onChange={setField('website')} placeholder="https://acme.com" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="industry">Industry</Label>
                        <Input id="industry" value={form.industry} onChange={setField('industry')} placeholder="Software" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="company_size">Company Size</Label>
                        <Input id="company_size" value={form.company_size} onChange={setField('company_size')} placeholder="50-100" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="address">Address</Label>
                      <Input id="address" value={form.address} onChange={setField('address')} placeholder="123 Main St, City" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="description">Description</Label>
                      <Input id="description" value={form.description} onChange={setField('description')} placeholder="What your company does" />
                    </div>

                    <Button type="submit" className="w-full" disabled={loading}>
                      {loading ? (
                        <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Creating account...</>
                      ) : (
                        <><UserPlus className="h-4 w-4 mr-2" />Sign Up</>
                      )}
                    </Button>
                  </form>

                  <Link
                    to="/company/login"
                    className="mt-4 flex items-center justify-center gap-1 w-full text-sm text-muted-foreground hover:text-primary"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Already have an account? Log in
                  </Link>
                </CardContent>
              </>
            )}
          </Card>
        </motion.div>
      </div>
    </>
  );
};

export default CompanySignupPage;
