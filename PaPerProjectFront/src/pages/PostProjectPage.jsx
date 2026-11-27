
import React from 'react';
import { Helmet } from 'react-helmet';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { 
    FileText, 
    Send, 
    CheckCircle, 
    ArrowRight, 
    Users, 
    Lightbulb, 
    Rocket,
    DollarSign,
    ShieldCheck,
    Clock
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

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

const PostProjectPage = () => {
  const { t } = useTranslation();

  const engagementModels = [
    {
      icon: Users,
      title: "Hire a Managed Team",
      description: "Ideal for complex, long-term projects. We provide a fully managed, cohesive team of experts led by a dedicated project manager to ensure flawless execution and delivery.",
      cta: "Build Your Team",
    },
    {
      icon: Lightbulb,
      title: "Book On-Demand Experts",
      description: "Need specialized skills for a short-term task or expert advice? Access individual top-tier professionals for consultations, code reviews, or specific feature development.",
      cta: "Find an Expert",
    },
    {
      icon: Rocket,
      title: "MVP Package for Startups",
      description: "A cost-effective, fixed-price package designed to get your idea off the ground. We build and launch your Minimum Viable Product quickly, setting you up for future growth.",
      cta: "Launch Your MVP",
    },
  ];

  const howItWorksSteps = [
    {
      icon: FileText,
      title: "1. Define Your Project",
      description: "Submit your project details through our simple form. The more information you provide, the better we can match you with the perfect talent.",
    },
    {
      icon: Send,
      title: "2. Get Matched in 24 Hours",
      description: "Our AI-powered system and expert team review your needs and match you with a pre-vetted, perfectly suited team or individual expert.",
    },
    {
      icon: Clock,
      title: "3. Review & Kick Off",
      description: "Meet your proposed team, review their profiles, and approve the project plan. We handle all contracts and onboarding so you can start in as little as 48 hours.",
    },
    {
      icon: CheckCircle,
      title: "4. Achieve Your Goals",
      description: "With a dedicated project manager and our success guarantee, your project is managed for quality and delivered on time, every time.",
    },
  ];
  
  const costSolutions = [
    {
      icon: DollarSign,
      title: "Fixed-Price Projects",
      description: "No surprises. We provide a clear, upfront quote for your entire project. You pay for the outcome, not the hours, making budgeting simple and predictable."
    },
    {
      icon: ShieldCheck,
      title: "Flexible Payment Options",
      description: "We partner with services like Klarna and Clearpay to offer flexible 'pay-later' options. Start your project with a small deposit and pay in comfortable installments."
    },
    {
      icon: Rocket,
      title: "Zero Commission or Hidden Fees",
      description: "Unlike freelance platforms that charge hefty commissions, our pricing is transparent. The price you see is the price you pay, ensuring maximum value for your investment."
    }
  ];

  return (
    <>
      <Helmet>
        <title>{t('title_post_project')} | Pay Per Project</title>
        <meta name="description" content={t('meta_desc_post_project')} />
      </Helmet>
      <div className="bg-background">
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
            >
              <FileText className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-foreground sm:text-6xl font-heading">
                How to Post a Project
              </h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                Tell us what you need. We'll connect you with vetted managed teams and experts to bring your vision to life—guaranteed.
              </p>
              <div className="mt-10 flex items-center justify-center gap-x-6">
                <Button size="lg" asChild>
                  <Link to="/start-project">
                    Get Started Now <ArrowRight className="ml-2 h-5 w-5" />
                  </Link>
                </Button>
              </div>
            </motion.div>
          </div>
          <div className="absolute inset-x-0 top-[calc(100%-13rem)] -z-10 transform-gpu overflow-hidden blur-3xl sm:top-[calc(100%-30rem)]" aria-hidden="true">
            <div className="relative left-[calc(50%+3rem)] aspect-[1155/678] w-[36.125rem] -translate-x-1/2 bg-gradient-to-tr from-[#ff80b5] to-[#9089fc] opacity-30 sm:left-[calc(50%+36rem)] sm:w-[72.1875rem]" style={{ clipPath: 'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)' }}></div>
          </div>
        </div>

        <section className="py-16 sm:py-24 bg-secondary/40">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground font-heading">Choose Your Path to Success</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                We offer flexible engagement models tailored to your specific project needs and goals.
              </p>
            </div>
            <motion.div 
              className="grid grid-cols-1 md:grid-cols-3 gap-8"
              variants={containerVariants}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.2 }}
            >
              {engagementModels.map((model, index) => (
                <motion.div key={index} variants={itemVariants}>
                  <Card className="text-center p-8 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col rounded-2xl">
                    <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                      <model.icon className="h-8 w-8 text-primary" />
                    </div>
                    <CardHeader className="p-0 pb-2">
                      <CardTitle className="text-xl font-bold text-foreground font-heading">{model.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0 flex-grow">
                      <p className="text-muted-foreground text-base leading-relaxed">{model.description}</p>
                    </CardContent>
                    <div className="mt-6">
                      <Button asChild variant="outline">
                        <Link to="/start-project">{model.cta}</Link>
                      </Button>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </section>

        <section className="py-16 sm:py-24">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground font-heading">Simple Steps to Success</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                Our process is designed for speed, quality, and peace of mind.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
              {howItWorksSteps.map((step, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: index * 0.1 }}
                  className="flex items-start gap-4"
                >
                  <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-xl font-heading">
                    {index + 1}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-foreground font-heading">{step.title}</h3>
                    <p className="mt-1 text-muted-foreground text-sm">{step.description}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>
        
        <section className="py-16 sm:py-24 bg-secondary/40">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground font-heading">Cost-Effective & Transparent Solutions</h2>
              <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                Get maximum value for your budget with our clear and flexible pricing.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {costSolutions.map((solution, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: index * 0.1 }}
                  className="flex flex-col items-center text-center p-6 bg-card rounded-2xl shadow-lg border"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 mb-4">
                    <solution.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="text-xl font-semibold text-foreground mb-2 font-heading">{solution.title}</h3>
                  <p className="text-muted-foreground">{solution.description}</p>
                </motion.div>
              ))}
            </div>
             <div className="mt-12 text-center">
              <Button asChild size="lg">
                <Link to="/payment-options">
                  Explore Payment Options <ArrowRight className="ml-2 h-5 w-5" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

      </div>
    </>
  );
};

export default PostProjectPage;
