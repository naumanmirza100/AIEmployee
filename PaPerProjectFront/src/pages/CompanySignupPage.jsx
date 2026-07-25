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

const FieldError = ({ message }) =>
  message ? <p className="text-xs text-destructive">{message}</p> : null;

// Company size: a single count ("50") or a range ("50-100"). Every number in it
// must be positive, and a range must not run backwards.
const validateCompanySize = (raw) => {
  const value = (raw || '').trim();
  if (!value) return '';
  if (!/^\d+(\s*-\s*\d+)?$/.test(value)) {
    return 'Enter a positive number (e.g. 50) or a range (e.g. 50-100)';
  }
  const [from, to] = value.split('-').map((n) => parseInt(n, 10));
  if (from <= 0 || (to !== undefined && to <= 0)) {
    return 'Company size must be greater than 0';
  }
  if (to !== undefined && to <= from) {
    return 'The end of the range must be greater than the start';
  }
  return '';
};

// The https:// prefix is fixed in the UI, so the user types only the domain.
const validateWebsite = (raw) => {
  const value = (raw || '').trim();
  if (!value) return '';
  if (/^https?:\/\//i.test(value)) {
    return 'No need for https:// — just enter the domain (e.g. laskon.com)';
  }
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+(\/\S*)?$/i.test(value)) {
    return 'Enter a valid domain (e.g. laskon.com)';
  }
  return '';
};

const validateForm = (form) => {
  const errors = {};
  if (!form.name.trim()) errors.name = 'Company name is required';
  if (!form.email.trim()) errors.email = 'Email is required';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
    errors.email = 'Enter a valid email address (e.g. name@example.com)';
  }
  if (!form.phone.trim()) errors.phone = 'Phone is required';
  else if (form.phone.replace(/\D/g, '').length < 7) {
    errors.phone = 'Enter a valid phone number';
  }

  const websiteError = validateWebsite(form.website);
  if (websiteError) errors.website = websiteError;

  const sizeError = validateCompanySize(form.company_size);
  if (sizeError) errors.company_size = sizeError;

  return errors;
};

const CompanySignupPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const setField = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    // Clear the field's error as soon as the user starts correcting it.
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const nextErrors = validateForm(form);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    setErrors({});

    try {
      setLoading(true);
      // The input holds a bare domain; the backend's URLField needs a scheme.
      const payload = {
        ...form,
        website: form.website.trim() ? `https://${form.website.trim()}` : '',
      };
      const res = await companyAuthService.signupCompany(payload);
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
                        <Input
                          id="name" value={form.name} onChange={setField('name')} placeholder="Acme Inc."
                          aria-invalid={!!errors.name}
                          className={errors.name ? 'border-destructive focus-visible:ring-destructive' : ''}
                        />
                        <FieldError message={errors.name} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email">Email <span className="text-red-500">*</span></Label>
                        <Input
                          id="email" type="email" value={form.email} onChange={setField('email')} placeholder="company@example.com"
                          aria-invalid={!!errors.email}
                          className={errors.email ? 'border-destructive focus-visible:ring-destructive' : ''}
                        />
                        <FieldError message={errors.email} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="phone">Phone <span className="text-red-500">*</span></Label>
                        <Input
                          id="phone" value={form.phone} onChange={setField('phone')} placeholder="+1 234 567 8900"
                          aria-invalid={!!errors.phone}
                          className={errors.phone ? 'border-destructive focus-visible:ring-destructive' : ''}
                        />
                        <FieldError message={errors.phone} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="website">Website</Label>
                        <div
                          className={`flex h-10 w-full items-center rounded-md border bg-background text-sm ring-offset-background focus-within:ring-2 focus-within:ring-offset-2 ${
                            errors.website
                              ? 'border-destructive focus-within:ring-destructive'
                              : 'border-input focus-within:ring-ring'
                          }`}
                        >
                          <span className="select-none pl-3 pr-0.5 text-muted-foreground">https://</span>
                          <input
                            id="website"
                            value={form.website}
                            onChange={setField('website')}
                            placeholder="laskon.com"
                            aria-invalid={!!errors.website}
                            className="h-full flex-1 rounded-r-md bg-transparent pr-3 outline-none placeholder:text-muted-foreground"
                          />
                        </div>
                        <FieldError message={errors.website} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="industry">Industry</Label>
                        <Input id="industry" value={form.industry} onChange={setField('industry')} placeholder="Software" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="company_size">Company Size</Label>
                        <Input
                          id="company_size" value={form.company_size} onChange={setField('company_size')}
                          inputMode="numeric" placeholder="50 or 50-100"
                          aria-invalid={!!errors.company_size}
                          className={errors.company_size ? 'border-destructive focus-visible:ring-destructive' : ''}
                        />
                        <FieldError message={errors.company_size} />
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
