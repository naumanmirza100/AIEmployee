
import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { Briefcase, MapPin, BrainCircuit, Users, Sparkles, ArrowRight, Search, UploadCloud, Star, Bot, CalendarDays, BarChart, ShieldCheck, FileText, ChevronsDown, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from '@/components/ui/use-toast';
import ApplicationForm from '@/components/careers/ApplicationForm';
import { careerService } from '@/services';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

const benefits = [
  {
    icon: MapPin,
    title: "Work From Anywhere",
    description: "We are a remote-first company. Enjoy the flexibility to work from wherever you are most productive and creative."
  },
  {
    icon: BrainCircuit,
    title: "Solve Challenging Problems",
    description: "Work on cutting-edge projects for industry-leading clients. Your code will make a real-world impact."
  },
  {
    icon: Users,
    title: "Collaborate with the Best",
    description: "Join a team of top 1% global talent. Learn from and grow with the most brilliant minds in the industry."
  },
  {
    icon: Sparkles,
    title: "Competitive Compensation",
    description: "We offer top-tier compensation and benefits packages to attract and retain the best talent in the world."
  }
];

const aiFeaturesForApplicants = [
  {
    icon: UploadCloud,
    title: "1-Click Profile Import & Parsing",
    description: "Auto-ingest your CV and links (LinkedIn, GitHub). We extract and normalize your skills for better matches, saving you time on forms."
  },
  {
    icon: Star,
    title: "Instant 'Best-Fit' Matches",
    description: "The moment a job is posted, see your match score and plain-English reasons why you're a great fit, based on your unique skills and experience."
  },
  {
    icon: FileText,
    title: "AI Resume & Profile Coach",
    description: "Get AI-powered suggestions to rewrite bullets, quantify your impact, and tailor your profile to specific job postings, boosting your chances."
  },
  {
    icon: Bot,
    title: "Conversational AI Concierge",
    description: "Our AI assistant answers your questions, pre-screens, and books interviews via site chat, SMS, or WhatsApp, reducing drop-off."
  },
  {
    icon: CalendarDays,
    title: "Auto-Scheduling Across Time Zones",
    description: "No more back-and-forth. Simply pick an available slot, and our system handles all interview scheduling and rescheduling automatically."
  },
  {
    icon: BarChart,
    title: "Skills Assessments with Instant Feedback",
    description: "Take coding or simulation tests that feed into your match score. Instantly see your strengths and get tips for improvement."
  },
  {
    icon: ShieldCheck,
    title: "Trust & Fraud Protection",
    description: "We use liveness/ID checks and provide warnings about deepfake job scams to ensure your application process is safe and secure."
  }
];

const CareersPage = ({ scrollToJobs = false }) => {
  const { t } = useTranslation();
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  // Fetch positions from API
  useEffect(() => {
    fetchPositions();
  }, []);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchPositions();
    }, 300);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  const fetchPositions = async () => {
    try {
      setLoading(true);
      const params = {};
      if (searchTerm.trim()) {
        params.search = searchTerm.trim();
      }
      
      const response = await careerService.getPositions(params);
      
      if (response.status === 'success' && response.data) {
        setPositions(response.data);
      } else {
        setPositions([]);
      }
    } catch (error) {
      console.error('Error fetching positions:', error);
      toast({
        title: "Error",
        description: "Failed to load job positions. Please try again later.",
        variant: "destructive",
      });
      setPositions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (scrollToJobs) {
      handleScrollToJobs();
    }
  }, [scrollToJobs]);

  const handleApplyClick = (position) => {
    setSelectedPosition(position);
    setTimeout(() => {
      document.getElementById('application-form-section')?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const handleScrollToJobs = () => {
    document.getElementById('open-positions')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      <Helmet>
        <title>{t('careers_title', 'Careers & Jobs | Join Our Elite Team')} | Pay Per Project</title>
        <meta name="description" content={t('careers_meta_description', 'Explore career opportunities at PayPerProject. We are hiring the top 1% of global talent to work on challenging projects. Apply today!')} />
      </Helmet>
      <div className="bg-background">
        {/* Hero Section */}
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
            >
              <Briefcase className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-foreground sm:text-6xl">
                {t('careers_h1', 'Build the Future With Us')}
              </h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                {t('careers_subtitle', 'We are a collective of the world\'s top 1% of engineers, designers, and innovators. If you are passionate about solving complex problems and building world-class products, you belong here.')}
              </p>
              <div className="mt-10">
                <Button size="lg" onClick={handleScrollToJobs}>
                  Apply for Jobs <ChevronsDown className="ml-2 h-5 w-5" />
                </Button>
              </div>
            </motion.div>
          </div>
        </div>

        {/* AI Features for Applicants Section */}
        <section className="py-16 sm:py-20 bg-background">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">An Application Experience Built for You</h2>
              <p className="mt-4 max-w-3xl mx-auto text-lg leading-8 text-muted-foreground">
                We use cutting-edge AI to make your job search faster, smarter, and more transparent.
              </p>
            </div>
            <motion.div
              variants={containerVariants}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.1 }}
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8"
            >
              {aiFeaturesForApplicants.map((feature, index) => (
                <motion.div key={index} variants={itemVariants}>
                  <Card className="p-6 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col rounded-2xl">
                    <div className="flex items-center gap-4 mb-4">
                      <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                        <feature.icon className="h-6 w-6 text-primary" />
                      </div>
                      <CardTitle className="text-lg font-bold text-foreground">{feature.title}</CardTitle>
                    </div>
                    <CardContent className="p-0 flex-grow">
                      <p className="text-muted-foreground text-base leading-relaxed">{feature.description}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </section>

        {/* Benefits Section */}
        <section className="py-16 sm:py-20 bg-secondary/40">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Why Join PayPerProject?</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                We've created an environment where elite talent can thrive.
              </p>
            </div>
            <motion.div
              variants={containerVariants}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.1 }}
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8"
            >
              {benefits.map((benefit, index) => (
                <motion.div key={index} variants={itemVariants}>
                  <Card className="text-center p-6 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col items-center rounded-2xl">
                    <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                      <benefit.icon className="h-8 w-8 text-primary" />
                    </div>
                    <CardHeader className="p-0 pb-2">
                      <CardTitle className="text-xl font-bold text-foreground">{benefit.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <p className="text-muted-foreground text-base leading-relaxed">{benefit.description}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </section>

        {/* Open Positions Section */}
        <section id="open-positions" className="py-16 sm:py-20 bg-background">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Open Positions</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                Find your next challenge. Your journey to making an impact starts here.
              </p>
              <div className="mt-6 max-w-lg mx-auto">
                <div className="relative">
                  <Input
                    type="search"
                    placeholder="Search for a role (e.g., 'React Engineer')"
                    className="w-full p-6 text-lg"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                  <Search className="absolute right-4 top-1/2 -translate-y-1/2 h-6 w-6 text-muted-foreground" />
                </div>
              </div>
            </div>

            <div className="space-y-4 max-w-4xl mx-auto">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  <span className="ml-3 text-muted-foreground">Loading positions...</span>
                </div>
              ) : positions.length === 0 ? (
                <Card className="p-12 text-center">
                  <p className="text-muted-foreground text-lg">
                    {searchTerm ? `No positions found matching "${searchTerm}"` : 'No open positions at the moment. Please check back later.'}
                  </p>
                </Card>
              ) : (
                positions.map((position, index) => (
                  <motion.div
                    key={position.id || index}
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, amount: 0.3 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <Card className="hover:shadow-lg transition-shadow duration-300">
                      <div className="p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                        <div className="flex-1">
                          <h3 className="text-xl font-bold text-primary">{position.title}</h3>
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground mt-2">
                            {(position.department || position.location) && (
                              <>
                                {position.department && (
                                  <span className="flex items-center gap-1.5"><Briefcase className="h-4 w-4" /> {position.department}</span>
                                )}
                                {position.location && (
                                  <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {position.location}</span>
                                )}
                              </>
                            )}
                            {position.type && (
                              <span className="flex items-center gap-1.5 text-sm bg-secondary px-2 py-1 rounded">
                                {position.type}
                              </span>
                            )}
                          </div>
                          {position.description && (
                            <p className="text-muted-foreground mt-3 line-clamp-2">{position.description}</p>
                          )}
                        </div>
                        <Button onClick={() => handleApplyClick(position)}>
                          Apply Now <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </div>
                    </Card>
                  </motion.div>
                ))
              )}
            </div>
          </div>
        </section>

        {/* Application Form Section */}
        <AnimatePresence>
          {selectedPosition && (
            <motion.section
              id="application-form-section"
              className="py-16 sm:py-20 bg-secondary/20"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.5, ease: 'easeInOut' }}
            >
              <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <ApplicationForm position={selectedPosition} positionTitle={selectedPosition?.title} />
              </div>
            </motion.section>
          )}
        </AnimatePresence>

      </div>
    </>
  );
};

export default CareersPage;
