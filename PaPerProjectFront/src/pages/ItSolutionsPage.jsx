
import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Cloud,
  Code,
  BrainCircuit,
  Map,
  Users,
  Rocket,
  BarChart,
  Target,
  Gem,
  Workflow,
  Search,
  Lock,
  Briefcase,
  Gavel,
  ArrowRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";


const ItSolutionsPage = () => {
  const { t } = useTranslation();

  const services = [
    {
      icon: Map,
      title: "Digital Transformation Strategy",
      description: "We develop comprehensive roadmaps for modernizing legacy systems, adopting new technologies, and aligning your IT with strategic business goals."
    },
    {
      icon: Cloud,
      title: "Cloud Migration & Optimization",
      description: "Expertly managing the migration to cloud platforms (AWS, Azure, GCP), optimizing cloud spending, and ensuring a secure, scalable architecture."
    },
    {
      icon: Code,
      title: "Custom Software Development",
      description: "Building bespoke software solutions tailored to your unique business processes and challenges, from web applications to enterprise-grade systems."
    },
    {
      icon: BrainCircuit,
      title: "Data & Analytics Services",
      description: "Implementing data warehouses, analytics platforms, and AI models to turn your data into actionable insights that drive business growth."
    }
  ];

  const marketTrends = [
    { icon: Target, title: "Outcome-Based Consulting", description: "Moving away from hourly billing to models where fees are tied to achieving specific business outcomes." },
    { icon: Gem, title: "Specialized Boutique Firms", description: "Growth of smaller, highly specialized consulting firms that focus on niche technologies or industries." },
    { icon: Code, title: "Low-Code/No-Code Platforms", description: "Consultants using low-code platforms to rapidly build and deploy solutions for clients." },
  ];

  const techInnovations = [
    { icon: BrainCircuit, title: "AI-Powered Consulting Tools", description: "Using AI to automate data analysis, generate insights, and even draft reports for consultants." },
    { icon: Search, title: "Process Mining", description: "Software that analyzes event logs to discover, monitor, and improve real business processes." },
    { icon: Workflow, title: "Value Stream Management", description: "Platforms that provide visibility into the entire software delivery lifecycle to identify bottlenecks." },
  ];
  
  const regulatoryLandscape = [
    { icon: Lock, title: "Data Privacy & Security Compliance", description: "Consultants must be experts in regulations like GDPR, CCPA, and HIPAA to advise clients properly." },
    { icon: Briefcase, title: "Independent Contractor Laws", description: "Evolving laws that affect the classification and use of freelance consultants." },
    { icon: Gavel, title: "Cybersecurity Liability", description: "Increased legal and financial liability for consulting firms in the event of a data breach." },
  ];

  return (
    <>
      <Helmet>
        <title>{t('it_solutions_title', 'IT & Consulting Solutions')} | Pay Per Project</title>
        <meta name="description" content={t('it_solutions_meta_description', 'Strategic IT & Consulting services to drive your digital transformation. From cloud migration to custom software development, we deliver results.')} />
      </Helmet>

      <div className="relative isolate overflow-hidden pt-24 pb-16 md:pt-40 md:pb-24">
        <div className="absolute inset-0 -z-10 h-full w-full bg-secondary">
          <div className="absolute bottom-0 left-[-20%] right-0 top-[-10%] h-[500px] w-[500px] rounded-full bg-gradient-to-tr from-primary/20 to-primary/10 blur-3xl" />
          <div className="absolute bottom-0 right-[-20%] top-[-10%] h-[500px] w-[500px] rounded-full bg-gradient-to-tr from-primary/20 to-primary/5 blur-3xl" />
        </div>
        
        <div className="container mx-auto px-4 md:px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          >
            <Users className="h-16 w-16 text-primary mx-auto mb-6" />
            <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight mb-4 font-heading text-foreground text-glow">
              {t('it_solutions_h1', 'IT & Consulting Solutions')}
            </h1>
            <p className="max-w-3xl mx-auto text-lg md:text-xl text-muted-foreground">
              {t('it_solutions_description', 'Strategic guidance and technology implementation to help businesses navigate digital transformation and achieve their goals.')}
            </p>
          </motion.div>
        </div>
      </div>

      <motion.section 
        className="py-16 md:py-24"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        variants={{
          visible: { transition: { staggerChildren: 0.1 } }
        }}
      >
        <div className="container mx-auto px-4 md:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Our Core Services</h2>
            <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Delivering excellence across the IT consulting spectrum.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {services.map((service, index) => (
              <motion.div
                key={index}
                variants={{
                  hidden: { opacity: 0, y: 30 },
                  visible: { opacity: 1, y: 0 }
                }}
              >
                <Card className="h-full text-center p-6 card-border-glow hover:bg-secondary/30 transition-colors">
                  <div className="mb-4 inline-block p-4 bg-primary/10 text-primary rounded-xl">
                    <service.icon className="h-10 w-10" />
                  </div>
                  <h3 className="text-xl font-bold mb-2">{service.title}</h3>
                  <p className="text-muted-foreground">{service.description}</p>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </motion.section>

      <motion.section 
        className="py-16 md:py-24 bg-secondary/40"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        variants={{
          visible: { transition: { staggerChildren: 0.2 } }
        }}
      >
        <div className="container mx-auto px-4 md:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Navigating the Landscape</h2>
            <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Understanding the trends, innovations, and rules that define the IT consulting industry.</p>
          </div>
          <Tabs defaultValue="trends" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="trends">Market Trends</TabsTrigger>
              <TabsTrigger value="innovations">Tech Innovations</TabsTrigger>
              <TabsTrigger value="regulatory">Regulatory Landscape</TabsTrigger>
            </TabsList>
            <TabsContent value="trends" className="pt-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {marketTrends.map((item, index) => (
                  <Card key={index} className="card-border-glow">
                    <CardHeader className="flex flex-row items-center gap-4">
                      <div className="p-3 bg-primary/10 rounded-lg"><item.icon className="h-6 w-6 text-primary" /></div>
                      <CardTitle>{item.title}</CardTitle>
                    </CardHeader>
                    <CardContent><p className="text-muted-foreground">{item.description}</p></CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
            <TabsContent value="innovations" className="pt-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {techInnovations.map((item, index) => (
                  <Card key={index} className="card-border-glow">
                    <CardHeader className="flex flex-row items-center gap-4">
                      <div className="p-3 bg-primary/10 rounded-lg"><item.icon className="h-6 w-6 text-primary" /></div>
                      <CardTitle>{item.title}</CardTitle>
                    </CardHeader>
                    <CardContent><p className="text-muted-foreground">{item.description}</p></CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
            <TabsContent value="regulatory" className="pt-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {regulatoryLandscape.map((item, index) => (
                  <Card key={index} className="card-border-glow">
                    <CardHeader className="flex flex-row items-center gap-4">
                      <div className="p-3 bg-primary/10 rounded-lg"><item.icon className="h-6 w-6 text-primary" /></div>
                      <CardTitle>{item.title}</CardTitle>
                    </CardHeader>
                    <CardContent><p className="text-muted-foreground">{item.description}</p></CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </motion.section>

      <section className="py-16 md:py-24">
        <div className="container mx-auto px-4 md:px-6">
          <div className="bg-gradient-to-r from-gray-900 to-black rounded-2xl p-8 md:p-12 text-center text-pure-white shadow-2xl relative overflow-hidden">
            <div className="absolute -right-1/4 -bottom-1/2 opacity-10">
                <Users className="w-[500px] h-[500px] text-primary/50" />
            </div>
            <h2 className="text-3xl font-bold mb-4 relative z-10">{t('it_solutions_cta_title', 'Ready to Transform Your Business?')}</h2>
            <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8 relative z-10">{t('it_solutions_cta_subtitle', 'Let our experts guide your next technology initiative. Get a fixed-price quote for a project that delivers real business value.')}</p>
            <Button asChild size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105 relative z-10">
              <Link to="/start-project">{t('it_solutions_cta_button', 'Start a Project')} <ArrowRight className="ml-2 h-5 w-5" /></Link>
            </Button>
          </div>
        </div>
      </section>

    </>
  );
};

export default ItSolutionsPage;
