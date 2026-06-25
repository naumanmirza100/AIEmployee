import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, Briefcase, MapPin, Building2, Clock, CheckCircle2, Upload, X, FileText, Ban, CalendarClock } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const JobApplicationPage = () => {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [jobLoading, setJobLoading] = useState(true);
  const [jobError, setJobError] = useState(null); // { code, message }
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [alreadyApplied, setAlreadyApplied] = useState(false);
  const [duplicateFields, setDuplicateFields] = useState([]);
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

  useEffect(() => {
    fetch(`${API_BASE}/public/jobs/${jobId}/`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((data) => {
        if (data.status === 'success') setJob(data.data);
        else setJobError({ code: data.code || 'ERROR', message: data.message || 'Job not found.' });
      })
      .catch(() => setJobError({ code: 'NETWORK', message: 'Failed to load job. Please check your connection.' }))
      .finally(() => setJobLoading(false));
  }, [jobId]);

  const validate = (data = form) => {
    const e = {};
    if (!data.first_name.trim()) e.first_name = 'Required';
    if (!data.last_name.trim()) e.last_name = 'Required';
    if (!data.email.trim()) e.email = 'Required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) e.email = 'Invalid email';
    if (!data.phone.trim()) e.phone = 'Required';
    if (!data.education.trim()) e.education = 'Required';
    if (!data.salary_expectation.trim()) e.salary_expectation = 'Required';
    if (!data.previous_company.trim()) e.previous_company = 'Required';
    if (!data.previous_salary.trim()) e.previous_salary = 'Required';
    if (!cvFile) e.cv_file = 'Please upload your CV';
    return e;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));
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
    setForm(syncedForm);

    const errs = validate(syncedForm);
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    const fd = new FormData();
    Object.entries(syncedForm).forEach(([k, v]) => fd.append(k, v));
    if (cvFile) fd.append('cv_file', cvFile);

    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/public/jobs/${jobId}/apply/`, {
        method: 'POST',
        body: fd,
      });
      const data = await res.json();
      if (data.status === 'success') {
        setSubmitted(true);
      } else if (data.code === 'ALREADY_APPLIED') {
        setAlreadyApplied(true);
        setDuplicateFields(data.duplicate_fields || []);
      } else {
        setSubmitError(data.message || 'Submission failed. Please try again.');
      }
    } catch {
      setSubmitError('Network error. Please check your connection and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (jobLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#020308' }}>
        <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
      </div>
    );
  }

  if (jobError) {
    const isNotYetOpen = jobError.code === 'NOT_YET_OPEN';
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'linear-gradient(135deg, #020308 0%, #0a1628 100%)' }}>
        <div
          className="w-full max-w-md rounded-2xl p-8 text-center"
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: `1px solid ${isNotYetOpen ? 'rgba(251,191,36,0.25)' : 'rgba(239,68,68,0.25)'}`,
          }}
        >
          <div
            className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full"
            style={{ background: isNotYetOpen ? 'rgba(251,191,36,0.12)' : 'rgba(239,68,68,0.12)' }}
          >
            {isNotYetOpen
              ? <CalendarClock className="h-8 w-8 text-amber-400" />
              : <Ban className="h-8 w-8 text-red-400" />
            }
          </div>
          <h2 className="text-xl font-bold text-white mb-2">
            {isNotYetOpen ? 'Applications Not Open Yet' : 'Position Closed'}
          </h2>
          <p className="text-sm text-white/55 leading-relaxed">{jobError.message}</p>
          <p className="mt-4 text-xs text-white/30">
            If you believe this is an error, please contact the company directly.
          </p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#020308' }}>
        <div
          className="w-full max-w-md rounded-2xl p-8 text-center"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(52,211,153,0.25)' }}
        >
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full" style={{ background: 'rgba(52,211,153,0.15)' }}>
            <CheckCircle2 className="h-8 w-8 text-emerald-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Application Submitted!</h2>
          <p className="text-white/60 text-sm mb-1">
            Thank you, <span className="text-white font-medium">{form.first_name}</span>!
          </p>
          <p className="text-white/50 text-sm">
            Your application for <span className="text-violet-300 font-medium">{job.title}</span> has been received. We'll be in touch soon.
          </p>
        </div>
      </div>
    );
  }

  const inputCls = (field) =>
    `w-full rounded-lg px-3 py-2.5 text-sm text-white placeholder-white/30 outline-none transition-colors ${
      errors[field]
        ? 'border border-red-500/60 bg-red-500/05'
        : 'border border-white/10 bg-white/[0.04] focus:border-violet-500/60'
    }`;

  return (
    <div className="min-h-screen py-10 px-4" style={{ background: 'linear-gradient(135deg, #020308 0%, #0a1628 100%)' }}>
      <div className="mx-auto max-w-2xl">

        {/* Job header card */}
        <div
          className="rounded-2xl p-6 mb-6"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(167,139,250,0.2)' }}
        >
          <div className="flex items-start gap-4">
            <div className="shrink-0 rounded-xl p-3" style={{ background: 'rgba(167,139,250,0.15)' }}>
              <Briefcase className="h-6 w-6 text-violet-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold text-white leading-tight">{job.title}</h1>
              {job.company_name && (
                <p className="text-sm text-violet-300 mt-0.5 flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5" />{job.company_name}
                </p>
              )}
              <div className="flex flex-wrap gap-3 mt-2">
                {job.location && (
                  <span className="flex items-center gap-1 text-xs text-white/50">
                    <MapPin className="h-3 w-3" />{job.location}
                  </span>
                )}
                {job.type && (
                  <span className="flex items-center gap-1 text-xs text-white/50">
                    <Clock className="h-3 w-3" />{job.type}
                  </span>
                )}
                {job.department && (
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(167,139,250,0.12)', color: '#c4b5fd', border: '1px solid rgba(167,139,250,0.2)' }}>
                    {job.department}
                  </span>
                )}
              </div>
            </div>
          </div>

          {job.description && (
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">About the Role</p>
              <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line line-clamp-6">{job.description}</p>
            </div>
          )}
          {job.requirements && (
            <div className="mt-3">
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Requirements</p>
              <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line line-clamp-4">{job.requirements}</p>
            </div>
          )}
        </div>

        {/* Application form */}
        <div
          className="rounded-2xl p-6"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <h2 className="text-lg font-bold text-white mb-5">Apply for this Position</h2>

          {alreadyApplied && (
            <div className="mb-4 rounded-lg px-4 py-4 text-sm" style={{ background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)' }}>
              <p className="font-semibold text-amber-300 flex items-center gap-2">
                ⚠️{' '}
                {duplicateFields.includes('email') && duplicateFields.includes('phone')
                  ? 'This email and phone are both already registered for this position.'
                  : duplicateFields.includes('email')
                  ? 'This email address is already registered for this position.'
                  : 'This phone number is already registered for this position.'}
              </p>
              <p className="text-amber-300/70 text-xs mt-1">
                {duplicateFields.includes('email') && duplicateFields.includes('phone')
                  ? 'To apply as a different person, use a different email address and phone number.'
                  : duplicateFields.includes('email')
                  ? 'To apply as a different person, use a different email address.'
                  : 'To apply as a different person, use a different phone number.'}
              </p>
            </div>
          )}

          {submitError && (
            <div className="mb-4 rounded-lg px-4 py-3 text-sm text-red-300" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)' }}>
              {submitError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">First Name <span className="text-red-400">*</span></label>
                <input name="first_name" value={form.first_name} onChange={handleChange} placeholder="John" className={inputCls('first_name')} />
                {errors.first_name && <p className="mt-1 text-xs text-red-400">{errors.first_name}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Last Name <span className="text-red-400">*</span></label>
                <input name="last_name" value={form.last_name} onChange={handleChange} placeholder="Doe" className={inputCls('last_name')} />
                {errors.last_name && <p className="mt-1 text-xs text-red-400">{errors.last_name}</p>}
              </div>
            </div>

            {/* Email + Phone */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Email Address <span className="text-red-400">*</span></label>
                <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="john@example.com" className={inputCls('email')} />
                {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Phone Number <span className="text-red-400">*</span></label>
                <input name="phone" type="tel" value={form.phone} onChange={handleChange} placeholder="+92 300 0000000" className={inputCls('phone')} />
                {errors.phone && <p className="mt-1 text-xs text-red-400">{errors.phone}</p>}
              </div>
            </div>

            {/* Location + Salary */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Current Location</label>
                <input name="current_location" value={form.current_location} onChange={handleChange} placeholder="City, Country" className={inputCls('current_location')} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Salary Expectation <span className="text-red-400">*</span></label>
                <input name="salary_expectation" value={form.salary_expectation} onChange={handleChange} placeholder="e.g. $2,000/month" className={inputCls('salary_expectation')} />
                {errors.salary_expectation && <p className="mt-1 text-xs text-red-400">{errors.salary_expectation}</p>}
              </div>
            </div>

            {/* Education */}
            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">Education <span className="text-red-400">*</span></label>
              <textarea
                name="education"
                value={form.education}
                onChange={handleChange}
                rows={2}
                placeholder="e.g. BS Computer Science — FAST NUCES (2020)"
                className={`w-full rounded-lg px-3 py-2.5 text-sm text-white placeholder-white/30 outline-none transition-colors resize-none ${errors.education ? 'border border-red-500/60 bg-red-500/05' : 'border border-white/10 bg-white/[0.04] focus:border-violet-500/60'}`}
              />
              {errors.education && <p className="mt-1 text-xs text-red-400">{errors.education}</p>}
            </div>

            {/* Previous company + salary */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Previous Company <span className="text-red-400">*</span></label>
                <input name="previous_company" value={form.previous_company} onChange={handleChange} placeholder="e.g. Google" className={inputCls('previous_company')} />
                {errors.previous_company && <p className="mt-1 text-xs text-red-400">{errors.previous_company}</p>}
              </div>
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">Previous Salary <span className="text-red-400">*</span></label>
                <input name="previous_salary" value={form.previous_salary} onChange={handleChange} placeholder="e.g. $3,000/month" className={inputCls('previous_salary')} />
                {errors.previous_salary && <p className="mt-1 text-xs text-red-400">{errors.previous_salary}</p>}
              </div>
            </div>

            {/* Social / portfolio links */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">LinkedIn <span className="text-white/30 font-normal">(optional)</span></label>
                <input name="linkedin_url" type="url" value={form.linkedin_url} onChange={handleChange} placeholder="https://linkedin.com/in/you" className={inputCls('linkedin_url')} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">GitHub <span className="text-white/30 font-normal">(optional)</span></label>
                <input name="github_url" type="url" value={form.github_url} onChange={handleChange} placeholder="https://github.com/you" className={inputCls('github_url')} />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">Other Links <span className="text-white/30 font-normal">(optional — portfolio, Behance, etc.)</span></label>
              <input name="other_links" value={form.other_links} onChange={handleChange} placeholder="https://myportfolio.com" className={inputCls('other_links')} />
            </div>

            {/* CV Upload */}
            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">
                Upload CV <span className="text-red-400">*</span>
                <span className="ml-1 font-normal text-white/30">(PDF, DOC, DOCX)</span>
              </label>
              <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx" onChange={handleFileChange} className="hidden" />
              {cvFile ? (
                <div
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5"
                  style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.25)' }}
                >
                  <FileText className="h-4 w-4 shrink-0 text-violet-400" />
                  <span className="flex-1 text-sm text-white/80 truncate">{cvFile.name}</span>
                  <button type="button" onClick={() => { setCvFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }} className="text-white/30 hover:text-white/60 transition-colors">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full rounded-lg px-3 py-6 text-center border-2 border-dashed transition-colors"
                  style={{ borderColor: errors.cv_file ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.12)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(167,139,250,0.4)'; e.currentTarget.style.background = 'rgba(167,139,250,0.05)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = errors.cv_file ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.12)'; e.currentTarget.style.background = ''; }}
                >
                  <Upload className="h-5 w-5 mx-auto text-white/30 mb-1.5" />
                  <p className="text-sm text-white/50">Click to upload your CV</p>
                  <p className="text-xs text-white/30 mt-0.5">PDF, DOC, DOCX up to 10MB</p>
                </button>
              )}
              {errors.cv_file && <p className="mt-1 text-xs text-red-400">{errors.cv_file}</p>}
            </div>

            {/* Cover Letter */}
            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">
                Cover Letter <span className="text-white/30 font-normal">(optional)</span>
              </label>
              <textarea
                name="cover_letter"
                value={form.cover_letter}
                onChange={handleChange}
                rows={4}
                placeholder="Tell us why you're a great fit for this role..."
                className="w-full rounded-lg px-3 py-2.5 text-sm text-white placeholder-white/30 outline-none transition-colors border border-white/10 bg-white/[0.04] focus:border-violet-500/60 resize-none"
              />
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg py-3 text-sm font-semibold text-white transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ background: submitting ? 'rgba(124,58,237,0.5)' : 'linear-gradient(90deg, #7c3aed 0%, #a259ff 100%)' }}
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Submitting...
                </span>
              ) : (
                'Submit Application'
              )}
            </button>

            <p className="text-center text-xs text-white/30">
              Your email and phone must be unique per position — you can only apply once per job.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
};

export default JobApplicationPage;
