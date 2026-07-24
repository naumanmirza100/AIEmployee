import React, { useState, useRef } from 'react';
import { Loader2, Upload, X, FileText, CheckCircle2, Link as LinkIcon } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const ApplicationForm = ({ position }) => {
  const { toast } = useToast();
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    current_location: '',
    salary_expectation: '',
    education: '',
    previous_company: '',
    previous_salary: '',
    linkedin_url: '',
    github_url: '',
    other_links: '',
    cover_letter: '',
  });
  const [cvFile, setCvFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState('');
  const [alreadyApplied, setAlreadyApplied] = useState(false);
  const [duplicateFields, setDuplicateFields] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const validate = (data = form) => {
    const e = {};
    if (!data.first_name.trim()) e.first_name = 'Required';
    if (!data.last_name.trim()) e.last_name = 'Required';
    if (!data.email.trim()) e.email = 'Required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) e.email = 'Invalid email';
    if (!data.phone.trim()) e.phone = 'Required';
    if (!data.education.trim()) e.education = 'Required';
    if (!data.salary_expectation.trim()) e.salary_expectation = 'Required';
    else if (!/^\d+$/.test(data.salary_expectation.trim())) e.salary_expectation = 'Numbers only';
    if (!data.previous_company.trim()) e.previous_company = 'Required';
    if (!data.previous_salary.trim()) e.previous_salary = 'Required';
    else if (!/^\d+$/.test(data.previous_salary.trim())) e.previous_salary = 'Numbers only';
    if (!cvFile) e.cv_file = 'Please upload your CV';
    return e;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    // Salary fields accept digits only
    const nextValue = (name === 'salary_expectation' || name === 'previous_salary')
      ? value.replace(/\D/g, '')
      : value;
    setForm((p) => ({ ...p, [name]: nextValue }));
    if (errors[name]) setErrors((p) => { const n = { ...p }; delete n[name]; return n; });
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setCvFile(file);
      if (errors.cv_file) setErrors((p) => { const n = { ...p }; delete n.cv_file; return n; });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitError('');
    setAlreadyApplied(false);
    setDuplicateFields([]);

    // Sync React state with actual DOM values so browser autofill is captured
    const domForm = e.target;
    const textFields = [
      'first_name','last_name','email','phone','current_location',
      'salary_expectation','education','previous_company','previous_salary',
      'linkedin_url','github_url','other_links','cover_letter',
    ];
    const syncedForm = { ...form };
    textFields.forEach((field) => {
      const el = domForm.elements[field];
      if (el) syncedForm[field] = el.value;
    });
    // Salary fields: strip non-digits (covers autofill)
    syncedForm.salary_expectation = (syncedForm.salary_expectation || '').replace(/\D/g, '');
    syncedForm.previous_salary = (syncedForm.previous_salary || '').replace(/\D/g, '');
    setForm(syncedForm);

    const errs = validate(syncedForm);
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    const fd = new FormData();
    Object.entries(syncedForm).forEach(([k, v]) => fd.append(k, v));
    if (cvFile) fd.append('cv_file', cvFile);

    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/public/jobs/${position.id}/apply/`, {
        method: 'POST',
        body: fd,
      });
      const data = await res.json();
      if (data.status === 'success') {
        setSubmitted(true);
        toast({
          title: 'Application Submitted!',
          description: `We've received your application for ${position?.title}.`,
        });
      } else {
        const msg = data.message || 'Submission failed. Please try again.';
        if (data.code === 'ALREADY_APPLIED') {
          setAlreadyApplied(true);
          setDuplicateFields(data.duplicate_fields || []);
        } else {
          setSubmitError(msg);
        }
        toast({ title: 'Error', description: msg, variant: 'destructive' });
      }
    } catch {
      const msg = 'Network error. Please check your connection and try again.';
      setSubmitError(msg);
      toast({ title: 'Network Error', description: msg, variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <Card className="w-full max-w-2xl mx-auto">
        <CardContent className="py-12 text-center">
          <CheckCircle2 className="h-12 w-12 mx-auto text-green-500 mb-4" />
          <h3 className="text-xl font-bold mb-2">Application Submitted!</h3>
          <p className="text-muted-foreground">
            Thank you, <span className="font-medium">{form.first_name}</span>! Your application for{' '}
            <span className="font-medium">{position?.title}</span> has been received. We'll be in touch soon.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-2xl mx-auto shadow-xl">
      <CardHeader className="bg-secondary/30">
        <CardTitle className="text-2xl font-bold">Apply for {position?.title || 'Position'}</CardTitle>
        <CardDescription>Fields marked with * are required.</CardDescription>
      </CardHeader>
      <CardContent className="p-6">
        <form onSubmit={handleSubmit} className="space-y-4">

          {/* Already applied banner */}
          {alreadyApplied && (
            <div className="rounded-md border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300 flex items-start gap-2">
              <span className="text-lg leading-none mt-0.5">⚠️</span>
              <div>
                <p className="font-semibold">
                  {duplicateFields.includes('email') && duplicateFields.includes('phone')
                    ? 'This email and phone are both already registered for this position.'
                    : duplicateFields.includes('email')
                    ? 'This email address is already registered for this position.'
                    : 'This phone number is already registered for this position.'}
                </p>
                <p className="text-xs mt-0.5 opacity-80">
                  {duplicateFields.includes('email') && duplicateFields.includes('phone')
                    ? 'To apply as a different person, use a different email address and phone number.'
                    : duplicateFields.includes('email')
                    ? 'To apply as a different person, use a different email address.'
                    : 'To apply as a different person, use a different phone number.'}
                </p>
              </div>
            </div>
          )}

          {/* General submit error */}
          {submitError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {submitError}
            </div>
          )}

          {/* Name */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="first_name">First Name <span className="text-destructive">*</span></Label>
              <Input
                id="first_name" name="first_name" value={form.first_name}
                onChange={handleChange} placeholder="John"
                className={errors.first_name ? 'border-destructive' : ''}
              />
              {errors.first_name && <p className="text-xs text-destructive">{errors.first_name}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="last_name">Last Name <span className="text-destructive">*</span></Label>
              <Input
                id="last_name" name="last_name" value={form.last_name}
                onChange={handleChange} placeholder="Doe"
                className={errors.last_name ? 'border-destructive' : ''}
              />
              {errors.last_name && <p className="text-xs text-destructive">{errors.last_name}</p>}
            </div>
          </div>

          {/* Email + Phone */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email Address <span className="text-destructive">*</span></Label>
              <Input
                id="email" name="email" type="email" value={form.email}
                onChange={handleChange} placeholder="john@example.com"
                className={errors.email ? 'border-destructive' : ''}
              />
              {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="phone">Phone Number <span className="text-destructive">*</span></Label>
              <Input
                id="phone" name="phone" type="tel" value={form.phone}
                onChange={handleChange} placeholder="+92 300 0000000"
                className={errors.phone ? 'border-destructive' : ''}
              />
              {errors.phone && <p className="text-xs text-destructive">{errors.phone}</p>}
            </div>
          </div>

          {/* Location + Salary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="current_location">Current Location <span className="text-muted-foreground font-normal text-xs">(optional)</span></Label>
              <Input
                id="current_location" name="current_location" value={form.current_location}
                onChange={handleChange} placeholder="City, Country"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="salary_expectation">Salary Expectation <span className="text-destructive">*</span></Label>
              <Input
                id="salary_expectation" name="salary_expectation" value={form.salary_expectation}
                onChange={handleChange} inputMode="numeric" pattern="[0-9]*" placeholder="e.g. 2000"
                className={errors.salary_expectation ? 'border-destructive' : ''}
              />
              {errors.salary_expectation && <p className="text-xs text-destructive">{errors.salary_expectation}</p>}
            </div>
          </div>

          {/* Education */}
          <div className="space-y-1.5">
            <Label htmlFor="education">Education <span className="text-destructive">*</span></Label>
            <textarea
              id="education" name="education" value={form.education}
              onChange={handleChange} rows={2}
              placeholder="e.g. BS Computer Science — FAST NUCES (2020)"
              className={`flex w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none ${errors.education ? 'border-destructive' : 'border-input'}`}
            />
            {errors.education && <p className="text-xs text-destructive">{errors.education}</p>}
          </div>

          {/* Previous company + salary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="previous_company">Previous Company <span className="text-destructive">*</span></Label>
              <Input
                id="previous_company" name="previous_company" value={form.previous_company}
                onChange={handleChange} placeholder="e.g. Google"
                className={errors.previous_company ? 'border-destructive' : ''}
              />
              {errors.previous_company && <p className="text-xs text-destructive">{errors.previous_company}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="previous_salary">Previous Salary <span className="text-destructive">*</span></Label>
              <Input
                id="previous_salary" name="previous_salary" value={form.previous_salary}
                onChange={handleChange} inputMode="numeric" pattern="[0-9]*" placeholder="e.g. 3000"
                className={errors.previous_salary ? 'border-destructive' : ''}
              />
              {errors.previous_salary && <p className="text-xs text-destructive">{errors.previous_salary}</p>}
            </div>
          </div>

          {/* LinkedIn + GitHub */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="linkedin_url">LinkedIn <span className="text-muted-foreground font-normal text-xs">(optional)</span></Label>
              <div className="relative">
                <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="linkedin_url" name="linkedin_url" type="url" value={form.linkedin_url}
                  onChange={handleChange} placeholder="https://linkedin.com/in/you" className="pl-9"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="github_url">GitHub <span className="text-muted-foreground font-normal text-xs">(optional)</span></Label>
              <div className="relative">
                <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="github_url" name="github_url" type="url" value={form.github_url}
                  onChange={handleChange} placeholder="https://github.com/you" className="pl-9"
                />
              </div>
            </div>
          </div>

          {/* Other links */}
          <div className="space-y-1.5">
            <Label htmlFor="other_links">Other Links <span className="text-muted-foreground font-normal text-xs">(optional — portfolio, Behance, etc.)</span></Label>
            <Input
              id="other_links" name="other_links" value={form.other_links}
              onChange={handleChange} placeholder="https://myportfolio.com"
            />
          </div>

          {/* CV Upload */}
          <div className="space-y-1.5">
            <Label>Upload CV <span className="text-destructive">*</span> <span className="text-muted-foreground font-normal text-xs">(PDF, DOC, DOCX)</span></Label>
            <input
              ref={fileInputRef} type="file" accept=".pdf,.doc,.docx"
              onChange={handleFileChange} className="hidden"
            />
            {cvFile ? (
              <div className="flex items-center gap-3 rounded-md border border-border bg-secondary/30 px-3 py-2.5">
                <FileText className="h-4 w-4 shrink-0 text-primary" />
                <span className="flex-1 text-sm truncate">{cvFile.name}</span>
                <Button
                  type="button" variant="ghost" size="icon" className="h-6 w-6"
                  onClick={() => { setCvFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={`w-full rounded-md border-2 border-dashed px-4 py-6 text-center transition-colors hover:border-primary/50 hover:bg-secondary/30 ${errors.cv_file ? 'border-destructive' : 'border-border'}`}
              >
                <Upload className="h-5 w-5 mx-auto text-muted-foreground mb-1.5" />
                <p className="text-sm text-muted-foreground">Click to upload your CV</p>
                <p className="text-xs text-muted-foreground/60 mt-0.5">PDF, DOC, DOCX up to 10MB</p>
              </button>
            )}
            {errors.cv_file && <p className="text-xs text-destructive">{errors.cv_file}</p>}
          </div>

          {/* Cover Letter */}
          <div className="space-y-1.5">
            <Label htmlFor="cover_letter">Cover Letter <span className="text-muted-foreground font-normal text-xs">(optional)</span></Label>
            <textarea
              id="cover_letter" name="cover_letter" value={form.cover_letter}
              onChange={handleChange} rows={4}
              placeholder="Tell us why you're a great fit for this role..."
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
            />
          </div>

          <Button type="submit" disabled={submitting} className="w-full font-semibold" size="lg">
            {submitting ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Submitting...</>
            ) : (
              'Submit Application'
            )}
          </Button>

          <p className="text-center text-xs text-muted-foreground">
            Your email and phone must be unique per position — you can only apply once per job.
          </p>
        </form>
      </CardContent>
    </Card>
  );
};

export default ApplicationForm;
