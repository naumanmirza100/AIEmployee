import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Helmet } from 'react-helmet';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Briefcase, MapPin, BrainCircuit, Users, Sparkles, ArrowRight,
  Search, UploadCloud, Star, Bot, CalendarDays, BarChart, ShieldCheck,
  FileText, ChevronsDown, Loader2, Building2, ChevronLeft, ChevronRight,
  ChevronsLeft, ChevronsRight, X, Filter, Clock, Copy, Link2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from '@/components/ui/use-toast';
import ApplicationForm from '@/components/careers/ApplicationForm';
import { careerService } from '@/services';

// ─── animation helpers ────────────────────────────────────────────────────────
const fade = {
  hidden: { opacity: 0, y: 20 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.45, delay: i * 0.06, ease: 'easeOut' } }),
};

// ─── static content ───────────────────────────────────────────────────────────
const benefits = [
  { icon: MapPin,       title: 'Work From Anywhere',        description: 'We are a remote-first company. Enjoy the flexibility to work from wherever you are most productive and creative.' },
  { icon: BrainCircuit, title: 'Solve Challenging Problems', description: 'Work on cutting-edge projects for industry-leading clients. Your code will make a real-world impact.' },
  { icon: Users,        title: 'Collaborate with the Best',  description: 'Join a team of top 1% global talent. Learn from and grow with the most brilliant minds in the industry.' },
  { icon: Sparkles,     title: 'Competitive Compensation',   description: 'We offer top-tier compensation packages to attract and retain the best talent in the world.' },
];

const aiFeatures = [
  { icon: UploadCloud, title: '1-Click Profile Import',       description: 'Auto-ingest your CV and links (LinkedIn, GitHub). We extract and normalise your skills for better matches, saving you time on forms.' },
  { icon: Star,        title: "Instant 'Best-Fit' Matches",   description: 'The moment a job is posted, see your match score and plain-English reasons why you\'re a great fit, based on your unique skills.' },
  { icon: FileText,    title: 'AI Resume & Profile Coach',    description: 'Get AI-powered suggestions to rewrite bullets, quantify your impact, and tailor your profile to specific job postings.' },
  { icon: Bot,         title: 'Conversational AI Concierge',  description: 'Our AI assistant answers your questions, pre-screens, and books interviews via chat, SMS, or WhatsApp, reducing drop-off.' },
  { icon: CalendarDays,title: 'Auto-Scheduling Across TZs',   description: 'No more back-and-forth. Simply pick an available slot, and our system handles all interview scheduling automatically.' },
  { icon: BarChart,    title: 'Skills Assessments',           description: 'Take coding or simulation tests that feed into your match score. Instantly see your strengths and get improvement tips.' },
  { icon: ShieldCheck, title: 'Trust & Fraud Protection',     description: 'We use liveness/ID checks and provide warnings about deepfake job scams to keep your application process safe.' },
];

const JOB_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship'];
const PAGE_SIZE_OPTIONS = [5, 10, 25];

// ─── helper ───────────────────────────────────────────────────────────────────
function useDebounce(value, delay = 400) {
  const [dv, setDv] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDv(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return dv;
}

// ─── type badge colour ────────────────────────────────────────────────────────
const TYPE_COLORS = {
  'Full-time':  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  'Part-time':  'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  'Contract':   'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  'Internship': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
};

// ─── component ────────────────────────────────────────────────────────────────
const CareersPage = ({ scrollToJobs = false }) => {
  const { t } = useTranslation();
  const jobsRef = useRef(null);

  const [selectedPosition, setSelectedPosition] = useState(null);
  const [positions, setPositions]               = useState([]);
  const [companies, setCompanies]               = useState([]);
  const [pagination, setPagination]             = useState({ page: 1, page_size: 10, total_count: 0, total_pages: 1, has_next: false, has_prev: false });
  const [loading, setLoading]                   = useState(true);

  const [searchRaw,  setSearchRaw]  = useState('');
  const [filterCo,   setFilterCo]   = useState('');
  const [filterType, setFilterType] = useState('');
  const [page,       setPage]       = useState(1);
  const [pageSize,   setPageSize]   = useState(10);

  const search = useDebounce(searchRaw, 400);

  // ── fetch ──────────────────────────────────────────────────────────────────
  const fetchPositions = useCallback(async (opts = {}) => {
    setLoading(true);
    try {
      const res = await careerService.getPositions({
        search:     opts.search     ?? search,
        company_id: opts.company_id ?? filterCo,
        type:       opts.type       ?? filterType,
        page:       opts.page       ?? page,
        page_size:  opts.page_size  ?? pageSize,
      });

      // api.get returns the raw parsed JSON:
      // { status: 'success', data: [...], pagination: {...}, companies: [...] }
      if (res?.status === 'success') {
        setPositions(res.data ?? []);
        setPagination(res.pagination ?? { page: 1, page_size: pageSize, total_count: (res.data ?? []).length, total_pages: 1, has_next: false, has_prev: false });
        if (res.companies?.length) setCompanies(res.companies);
      } else {
        setPositions([]);
      }
    } catch (err) {
      console.error('Careers fetch error:', err);
      toast({ title: 'Error', description: 'Failed to load job positions. Please try again later.', variant: 'destructive' });
      setPositions([]);
    } finally {
      setLoading(false);
    }
  }, [search, filterCo, filterType, page, pageSize]);

  // initial load
  useEffect(() => { fetchPositions(); }, []);

  // re-fetch when filters / pagination change
  useEffect(() => {
    setPage(1);
    fetchPositions({ search, company_id: filterCo, type: filterType, page: 1, page_size: pageSize });
  }, [search, filterCo, filterType, pageSize]);

  const goToPage = (p) => {
    setPage(p);
    fetchPositions({ page: p });
    jobsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  useEffect(() => {
    if (scrollToJobs) jobsRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [scrollToJobs]);

  const handleApply = (position) => {
    setSelectedPosition(position);
    setTimeout(() => {
      document.getElementById('application-form-section')?.scrollIntoView({ behavior: 'smooth' });
    }, 150);
  };

  const clearFilters = () => {
    setSearchRaw('');
    setFilterCo('');
    setFilterType('');
  };

  const handleCopyLink = (pos) => {
    const url = `${window.location.origin}/jobs/apply/${pos.id}`;
    navigator.clipboard.writeText(url).then(() => {
      toast({ title: 'Link copied!', description: `Application link for "${pos.title}" copied to clipboard.` });
    }).catch(() => {
      toast({ title: 'Error', description: 'Could not copy link. Try again.', variant: 'destructive' });
    });
  };

  const activeFilters = [filterCo, filterType, searchRaw].filter(Boolean).length;

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <>
      <Helmet>
        <title>Careers & Open Positions | Pay Per Project</title>
        <meta name="description" content="Explore job openings from companies on PayPerProject. Browse by company, role, or type and apply directly." />
      </Helmet>

      <div className="bg-background">

        {/* ── Hero ─────────────────────────────────────────────────────────── */}
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}>
              <Briefcase className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-foreground sm:text-6xl">Build the Future With Us</h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                Browse open positions from companies using Pay Per Project. Find a role that fits your skills and ambitions.
              </p>
              <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
                <Button size="lg" onClick={() => jobsRef.current?.scrollIntoView({ behavior: 'smooth' })}>
                  Browse Open Positions <ChevronsDown className="ml-2 h-5 w-5" />
                </Button>
                {pagination.total_count > 0 && (
                  <span className="text-muted-foreground text-base">{pagination.total_count} open position{pagination.total_count !== 1 ? 's' : ''}</span>
                )}
              </div>
            </motion.div>
          </div>
        </div>

        {/* ── AI Features ──────────────────────────────────────────────────── */}
        <section className="py-16 sm:py-20 bg-background">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">An Application Experience Built for You</h2>
              <p className="mt-4 max-w-3xl mx-auto text-lg text-muted-foreground">We use cutting-edge AI to make your job search faster, smarter, and more transparent.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {aiFeatures.map((f, i) => (
                <motion.div key={i} custom={i} variants={fade} initial="hidden" whileInView="visible" viewport={{ once: true }}>
                  <Card className="p-6 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col rounded-2xl">
                    <div className="flex items-center gap-4 mb-4">
                      <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                        <f.icon className="h-6 w-6 text-primary" />
                      </div>
                      <CardTitle className="text-lg font-bold text-foreground">{f.title}</CardTitle>
                    </div>
                    <CardContent className="p-0 flex-grow">
                      <p className="text-muted-foreground text-base leading-relaxed">{f.description}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Benefits ─────────────────────────────────────────────────────── */}
        <section className="py-16 sm:py-20 bg-secondary/40">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Why Join PayPerProject?</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">We've created an environment where elite talent can thrive.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
              {benefits.map((b, i) => (
                <motion.div key={i} custom={i} variants={fade} initial="hidden" whileInView="visible" viewport={{ once: true }}>
                  <Card className="text-center p-6 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col items-center rounded-2xl">
                    <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                      <b.icon className="h-8 w-8 text-primary" />
                    </div>
                    <CardHeader className="p-0 pb-2">
                      <CardTitle className="text-xl font-bold text-foreground">{b.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <p className="text-muted-foreground text-base leading-relaxed">{b.description}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Open Positions ───────────────────────────────────────────────── */}
        <section id="open-positions" ref={jobsRef} className="py-16 sm:py-20 bg-background">
          <div className="mx-auto max-w-5xl px-6 lg:px-8">

            <div className="text-center mb-10">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Open Positions</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Find your next challenge. Your journey to making an impact starts here.</p>
            </div>

            {/* ── Filter bar ───────────────────────────────────────────────── */}
            <div className="bg-card border rounded-2xl p-5 mb-8 shadow-sm">
              <div className="flex flex-wrap gap-3 items-center">

                {/* Search */}
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                  <Input
                    type="search"
                    placeholder="Search role, skill, department…"
                    className="pl-9 pr-8"
                    value={searchRaw}
                    onChange={e => setSearchRaw(e.target.value)}
                  />
                  {searchRaw && (
                    <button onClick={() => setSearchRaw('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>

                {/* Company filter */}
                {companies.length > 0 && (
                  <div className="relative min-w-[160px]">
                    <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <select
                      value={filterCo}
                      onChange={e => setFilterCo(e.target.value)}
                      className="w-full pl-9 pr-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary appearance-none cursor-pointer"
                    >
                      <option value="">All Companies</option>
                      {companies.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Job type filter */}
                <div className="relative min-w-[150px]">
                  <Clock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                  <select
                    value={filterType}
                    onChange={e => setFilterType(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary appearance-none cursor-pointer"
                  >
                    <option value="">All Types</option>
                    {JOB_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                {/* Page size */}
                <div className="flex items-center gap-2 text-sm text-muted-foreground ml-auto">
                  <span className="whitespace-nowrap hidden sm:inline">Show</span>
                  <select
                    value={pageSize}
                    onChange={e => setPageSize(Number(e.target.value))}
                    className="px-2 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
                  >
                    {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n} / page</option>)}
                  </select>
                </div>

                {/* Clear */}
                {activeFilters > 0 && (
                  <button
                    onClick={clearFilters}
                    className="flex items-center gap-1.5 text-sm text-destructive hover:text-destructive/80 border border-destructive/30 rounded-md px-3 py-2 transition-colors"
                  >
                    <X className="h-3.5 w-3.5" /> Clear ({activeFilters})
                  </button>
                )}
              </div>

              {/* Results summary */}
              <div className="mt-3 text-sm text-muted-foreground">
                {loading ? (
                  <span className="flex items-center gap-1.5"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…</span>
                ) : (
                  <span>
                    Showing <strong className="text-foreground">
                      {pagination.total_count === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1}–{Math.min(pagination.page * pagination.page_size, pagination.total_count)}
                    </strong> of <strong className="text-foreground">{pagination.total_count}</strong> position{pagination.total_count !== 1 ? 's' : ''}
                    {activeFilters > 0 && <span className="ml-2 text-primary">(filtered)</span>}
                  </span>
                )}
              </div>
            </div>

            {/* ── Job cards ────────────────────────────────────────────────── */}
            <div className="space-y-4">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  <span className="ml-3 text-muted-foreground">Loading positions…</span>
                </div>
              ) : positions.length === 0 ? (
                <Card className="p-12 text-center">
                  <Briefcase className="mx-auto h-10 w-10 text-muted-foreground/30 mb-4" />
                  <p className="text-muted-foreground text-lg font-medium">
                    {activeFilters > 0 ? 'No positions match your filters.' : 'No open positions at the moment.'}
                  </p>
                  {activeFilters > 0 && (
                    <button onClick={clearFilters} className="mt-4 text-sm text-primary underline underline-offset-2">Clear filters</button>
                  )}
                </Card>
              ) : (
                positions.map((pos, i) => (
                  <motion.div
                    key={pos.id}
                    custom={i}
                    variants={fade}
                    initial="hidden"
                    animate="visible"
                  >
                    <Card className="hover:shadow-lg hover:border-primary/30 transition-all duration-300 overflow-hidden">
                      <div className="p-6">
                        <div className="flex flex-col sm:flex-row sm:items-start gap-4 justify-between">

                          {/* Left — job info */}
                          <div className="flex-1 min-w-0">
                            {/* Company + badges row */}
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {pos.company_name && (
                                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary/80 bg-primary/8 border border-primary/20 rounded-full px-2.5 py-0.5">
                                  <Building2 className="h-3 w-3" />
                                  {pos.company_name}
                                </span>
                              )}
                              {pos.type && (
                                <span className={`inline-flex items-center text-xs font-semibold rounded-full px-2.5 py-0.5 ${TYPE_COLORS[pos.type] || 'bg-secondary text-secondary-foreground'}`}>
                                  {pos.type}
                                </span>
                              )}
                            </div>

                            {/* Title */}
                            <h3 className="text-xl font-bold text-foreground leading-snug">{pos.title}</h3>

                            {/* Meta row */}
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground text-sm mt-2">
                              {pos.department && (
                                <span className="flex items-center gap-1.5">
                                  <Briefcase className="h-3.5 w-3.5" /> {pos.department}
                                </span>
                              )}
                              {pos.location && (
                                <span className="flex items-center gap-1.5">
                                  <MapPin className="h-3.5 w-3.5" /> {pos.location}
                                </span>
                              )}
                            </div>

                            {/* Description preview */}
                            {pos.description && (
                              <p className="text-muted-foreground text-sm mt-3 line-clamp-2 leading-relaxed">
                                {pos.description}
                              </p>
                            )}
                          </div>

                          {/* Right — CTA */}
                          <div className="flex-shrink-0 flex sm:flex-col items-center gap-2 sm:items-end">
                            <div className="flex items-center gap-2">
                              <Button
                                onClick={() => handleApply(pos)}
                                className="whitespace-nowrap"
                              >
                                Apply Now <ArrowRight className="ml-2 h-4 w-4" />
                              </Button>
                              <button
                                onClick={() => handleCopyLink(pos)}
                                title="Copy application link"
                                className="p-2 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                              >
                                <Copy className="h-4 w-4" />
                              </button>
                            </div>
                            {selectedPosition?.id === pos.id && (
                              <span className="text-xs text-primary font-medium">Form below ↓</span>
                            )}
                          </div>
                        </div>

                        {/* Requirements snippet */}
                        {pos.requirements && (
                          <div className="mt-4 pt-4 border-t border-border/60">
                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Requirements</p>
                            <p className="text-sm text-muted-foreground line-clamp-2">{pos.requirements}</p>
                          </div>
                        )}
                      </div>
                    </Card>
                  </motion.div>
                ))
              )}
            </div>

            {/* ── Pagination ───────────────────────────────────────────────── */}
            {pagination.total_pages > 1 && !loading && (
              <div className="mt-8 flex items-center justify-between flex-wrap gap-4">
                <span className="text-sm text-muted-foreground">
                  Page <strong className="text-foreground">{pagination.page}</strong> of <strong className="text-foreground">{pagination.total_pages}</strong>
                </span>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => goToPage(1)}
                    disabled={!pagination.has_prev}
                    className="p-2 rounded-md border border-border hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="First page"
                  >
                    <ChevronsLeft className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => goToPage(pagination.page - 1)}
                    disabled={!pagination.has_prev}
                    className="p-2 rounded-md border border-border hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>

                  {/* Page number pills */}
                  {Array.from({ length: pagination.total_pages }, (_, i) => i + 1)
                    .filter(p => p === 1 || p === pagination.total_pages || Math.abs(p - pagination.page) <= 2)
                    .reduce((acc, p, idx, arr) => {
                      if (idx > 0 && p - arr[idx - 1] > 1) acc.push('…');
                      acc.push(p);
                      return acc;
                    }, [])
                    .map((p, i) =>
                      p === '…' ? (
                        <span key={`e-${i}`} className="px-1 text-muted-foreground select-none">…</span>
                      ) : (
                        <button
                          key={p}
                          onClick={() => goToPage(p)}
                          className={`min-w-[36px] h-9 px-2 rounded-md border text-sm font-medium transition-colors ${
                            p === pagination.page
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-border hover:bg-accent'
                          }`}
                        >
                          {p}
                        </button>
                      )
                    )}

                  <button
                    onClick={() => goToPage(pagination.page + 1)}
                    disabled={!pagination.has_next}
                    className="p-2 rounded-md border border-border hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="Next page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => goToPage(pagination.total_pages)}
                    disabled={!pagination.has_next}
                    className="p-2 rounded-md border border-border hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="Last page"
                  >
                    <ChevronsRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── Application Form ─────────────────────────────────────────────── */}
        <AnimatePresence>
          {selectedPosition && (
            <motion.section
              id="application-form-section"
              className="py-16 sm:py-20 bg-secondary/20"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.45, ease: 'easeInOut' }}
            >
              <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="flex items-center justify-between mb-6 max-w-2xl mx-auto">
                  <div>
                    <p className="text-sm text-muted-foreground">Applying for</p>
                    <h3 className="text-xl font-bold text-foreground">{selectedPosition.title}</h3>
                    {selectedPosition.company_name && (
                      <p className="text-sm text-primary">{selectedPosition.company_name}</p>
                    )}
                  </div>
                  <button
                    onClick={() => setSelectedPosition(null)}
                    className="p-2 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                    title="Close form"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <ApplicationForm key={selectedPosition.id} position={selectedPosition} positionTitle={selectedPosition?.title} />
              </div>
            </motion.section>
          )}
        </AnimatePresence>

      </div>
    </>
  );
};

export default CareersPage;
