
import React, { useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { 
    Users, Briefcase, ShieldCheck, Zap, Search, Award, FileText, ArrowRight, Microscope, BrainCircuit, Star, Globe,
    MapPin, Clock, Wifi, ChevronsDown
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link, useLocation } from 'react-router-dom';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import TalentRequestForm from '@/components/hire-talent/TalentRequestForm';

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

const HowItWorksSection = () => {
  const steps = [
    { icon: FileText, title: "1. Define Your Vision", description: "Submit your project requirements, technical needs, and business goals. The more detailed your vision, the more precise our AI-powered matching will be." },
    { icon: Search, title: "2. AI-Powered Matching", description: "Our proprietary AI scans our elite network, matching your project with the perfect team based on skills, industry experience, and proven success. We find the needle in the haystack for you." },
    { icon: Zap, title: "3. Launch in 48 Hours", description: "We connect you with your handpicked team for a kickoff meeting. Forget lengthy onboarding; your project is live and making progress in just two business days." },
    { icon: Briefcase, title: "4. Flawless Execution", description: "A dedicated project manager ensures seamless execution, transparent communication, and adherence to the highest quality standards, guaranteeing a successful outcome." },
  ];
  return (
    <div className="py-16 sm:py-20 bg-secondary/40">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Your Path to Instant Progress</h2>
          <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
            Our streamlined 4-step process eliminates the friction of hiring and gets you results, fast.
          </p>
        </div>
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.1 }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8"
        >
          {steps.map((step, index) => (
            <motion.div key={index} variants={itemVariants}>
              <Card className="text-center p-6 bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 h-full flex flex-col items-center rounded-2xl">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                  <step.icon className="h-8 w-8 text-primary" />
                </div>
                <CardHeader className="p-0 pb-2">
                  <CardTitle className="text-xl font-bold text-foreground">{step.title}</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <p className="text-muted-foreground text-base leading-relaxed">{step.description}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
};

const SourcingModelsSection = () => {
  const models = [
    {
      icon: MapPin,
      title: "Onshore Teams",
      description: "Leverage top-tier talent located within your country. Ideal for projects requiring in-person collaboration, minimal cultural barriers, and adherence to specific national data regulations. Benefit from real-time communication and maximum convenience.",
      bgColor: "bg-blue-500/10",
      borderColor: "border-blue-500/50",
      textColor: "text-blue-400"
    },
    {
      icon: Clock,
      title: "Nearshore Teams",
      description: "Access elite teams in neighboring countries or similar time zones. Nearshore offers the perfect balance of cost-efficiency and seamless collaboration, with minimal time differences and strong cultural alignment. It's the sweet spot for agile development.",
      bgColor: "bg-green-500/10",
      borderColor: "border-green-500/50",
      textColor: "text-green-400"
    },
    {
      icon: Wifi,
      title: "Offshore Teams",
      description: "Tap into our global network of the world's best 1% talent for maximum cost-effectiveness and round-the-clock development cycles. Our managed offshore model eliminates communication gaps, ensuring your project progresses 24/7 with world-class experts.",
      bgColor: "bg-purple-500/10",
      borderColor: "border-purple-500/50",
      textColor: "text-purple-400"
    }
  ];

  return (
    <div className="py-16 sm:py-20">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Flexible Sourcing for Your Needs</h2>
          <p className="mt-4 max-w-3xl mx-auto text-lg leading-8 text-muted-foreground">
            We provide vetted talent, structured to fit your project's unique requirements for speed, budget, and collaboration.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {models.map((model, index) => (
            <motion.div
              key={index}
              variants={itemVariants}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.3 }}
              transition={{ delay: index * 0.1 }}
            >
              <Card className={`h-full flex flex-col text-center p-8 rounded-2xl border-2 transition-all duration-300 hover:shadow-2xl hover:border-primary/50 ${model.bgColor} ${model.borderColor}`}>
                <div className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full ${model.bgColor} mb-6`}>
                  <model.icon className={`h-8 w-8 ${model.textColor}`} />
                </div>
                <h3 className="text-2xl font-bold text-foreground mb-3">{model.title}</h3>
                <p className="text-muted-foreground leading-relaxed flex-grow">{model.description}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
};

const GlobalNetworkSection = () => {
    return (
        <div className="py-16 sm:py-20 bg-secondary/40">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
                    <motion.div
                        className="relative flex justify-center items-center"
                        initial={{ opacity: 0, scale: 0.8 }}
                        whileInView={{ opacity: 1, scale: 1 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                    >
                        <Globe className="w-64 h-64 text-primary/10" />
                        <motion.div 
                            className="absolute"
                            animate={{ rotate: 360 }}
                            transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
                        >
                            <img alt="Global network of dots" className="w-[400px] h-[400px] opacity-30" src="https://images.unsplash.com/photo-1679830238737-5bc41f101bbb" />
                        </motion.div>
                        <motion.div
                            className="absolute h-12 w-12 bg-primary rounded-full shadow-2xl shadow-primary/50"
                            animate={{
                                scale: [1, 1.2, 1],
                                opacity: [0.8, 1, 0.8],
                            }}
                            transition={{
                                duration: 2,
                                repeat: Infinity,
                                repeatType: "mirror"
                            }}
                        ></motion.div>
                    </motion.div>
                    <motion.div
                        initial={{ opacity: 0, x: 50 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.6 }}
                    >
                        <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Global Talent, Local Timezone</h2>
                        <p className="mt-6 text-lg leading-8 text-muted-foreground">
                            Stop juggling late-night calls and communication lags. Our globally distributed network allows us to assemble a world-class team that operates in your timezone, ensuring seamless collaboration and maximum productivity.
                        </p>
                        <div className="mt-8 space-y-6">
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
                                    <Users className="h-7 w-7" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-semibold text-foreground">Timezone-Aligned Teams</h3>
                                    <p className="mt-1 text-muted-foreground leading-relaxed">
                                        We guarantee a team with significant overlap in your working hours for real-time collaboration, agile sprints, and rapid feedback loops.
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
                                    <Award className="h-7 w-7" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-semibold text-foreground">Access to Untapped Talent Pools</h3>
                                    <p className="mt-1 text-muted-foreground leading-relaxed">
                                        Our global reach gives you access to elite experts in emerging tech hubs, providing a competitive edge that isn't available locally.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </div>
        </div>
    );
};


const VettingProcessSection = () => {
  const steps = [
    { icon: FileText, title: "1. Proven Track Record", description: "We start by analyzing a team's portfolio, client testimonials, and public reputation. Only teams with a history of delivering exceptional results and maintaining stellar client relationships proceed." },
    { icon: Microscope, title: "2. Elite Technical Assessment", description: "Candidates face rigorous, domain-specific tests and live problem-solving challenges designed by industry leaders. This validates their expertise and ensures they can handle complex, real-world scenarios." },
    { icon: BrainCircuit, title: "3. Architectural & Systems Design", description: "We assess their ability to design scalable, secure, and maintainable systems. This crucial step ensures the solutions they build are robust and future-proof, not just functional for today." },
    { icon: Users, title: "4. Professionalism & Communication", description: "Technical skill means nothing without clear communication. We conduct in-depth interviews to evaluate professionalism, proactivity, and collaborative mindset, ensuring they integrate seamlessly as part of your team." },
    { icon: Star, title: "5. Final Review", description: "Our most senior architects and project leads conduct a final, holistic review. Only teams demonstrating world-class excellence across all stages are invited to join our network." },
  ];

  return (
    <div className="py-16 sm:py-20">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Our Uncompromising 5-Step Vetting Process</h2>
          <p className="mt-4 max-w-3xl mx-auto text-lg leading-8 text-muted-foreground">
            We're obsessed with quality. This is how we ensure you only work with the absolute best.
          </p>
        </div>
        <div className="max-w-4xl mx-auto">
          {steps.map((step, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, amount: 0.5 }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="flex items-start gap-6 mb-8 last:mb-0"
            >
              <div className="flex-shrink-0 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
                <step.icon className="h-8 w-8" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-foreground">{step.title}</h3>
                <p className="mt-1 text-muted-foreground text-base leading-relaxed">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

const GuaranteeSection = () => {
  const guarantees = [
    { icon: Award, title: "The Quality Guarantee", description: "We are relentlessly selective: every team passes our 5-step vetting process. This means you are only working with the absolute best in the world, eliminating the risk of a bad hire." },
    { icon: ShieldCheck, title: "Project Success Guarantee", description: "We are so confident in our talent that we financially guarantee your project's success. If deliverables don't meet the agreed-upon standards, we will fix it on our dime. Your success is our only metric." },
    { icon: Users, title: "Seamless Integration", description: "Our teams are more than contractors; they are trained to be a seamless, accountable extension of your company. They adopt your tools, provide proactive updates, and take true ownership of the project's success." },
  ];
  return (
    <div className="py-16 sm:py-20 bg-secondary/40">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground">Our Unbreakable Guarantees</h2>
          <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
            We don't just connect you with talent; we deliver guaranteed outcomes.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 text-center">
          {guarantees.map((item, index) => (
             <motion.div
              key={index}
              initial={{ opacity: 0, y: 50 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
             >
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                  <item.icon className="h-8 w-8 text-primary" />
              </div>
              <h3 className="text-2xl font-bold tracking-tight text-foreground">{item.title}</h3>
              <p className="mt-4 text-muted-foreground leading-relaxed">{item.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
};

const FaqSection = () => {
  const faqs1 = [
    {
      question: "How do you vet your talent?",
      answer: "Our 5-step vetting process is exhaustive. It includes portfolio review, technical skill assessments, live coding challenges, system design interviews, and cultural fit evaluations. We only accept development agencies with a proven track record, which is why our acceptance rate is under 1%."
    },
    {
      question: "Can I hire experts from non-tech fields?",
      answer: "Yes! Our network includes vetted professionals from hundreds of fields, including doctors for MedTech, scientists for R&D, and educators for EdTech. We match you with the specific domain expertise your project requires."
    },
    {
      question: "What is the 'Project Success Guarantee'?",
      answer: "It means we are fully accountable for the outcome. If the delivered work doesn't meet the agreed-upon scope and quality standards, our team will work to fix it at no extra cost. Your success is our mission."
    },
    {
      question: "Can I hire an individual or only teams?",
      answer: "We specialize in providing cohesive, managed teams to ensure quality, accountability, and streamlined project execution. This model provides greater reliability and a broader skill set than hiring a single freelancer."
    },
  ];
  const faqs2 = [
    {
      question: "How quickly can my new team start?",
      answer: "In most cases, your new team can be assembled, briefed, and ready to start working within 48-72 hours after you approve the project scope and proposal."
    },
    {
      question: "How do you handle time zones?",
      answer: "We have a global network of over 200+ experts in each field, allowing us to assemble a team that has significant overlap with your working hours, ensuring smooth communication and collaboration."
    },
    {
      question: "Who owns the intellectual property (IP)?",
      answer: "You do. All intellectual property and work product created by the team for your project are 100% yours, contractually guaranteed."
    },
    {
      question: "What if I'm not happy with my team?",
      answer: "Your satisfaction is paramount. If there are any issues, your dedicated project manager will work to resolve them. If a resolution can't be found, we will replace the team at no additional cost to you, ensuring your project stays on track."
    },
  ];

  return (
    <div className="py-16 sm:py-20 bg-background">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground">Frequently Asked Questions</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12">
            <Accordion type="single" collapsible className="w-full">
              {faqs1.map((faq, index) => (
                <AccordionItem key={index} value={`item-${index}`}>
                  <AccordionTrigger className="text-lg font-semibold text-left py-4">{faq.question}</AccordionTrigger>
                  <AccordionContent className="text-base text-muted-foreground pb-4">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
            <Accordion type="single" collapsible className="w-full">
              {faqs2.map((faq, index) => (
                <AccordionItem key={index + faqs1.length} value={`item-${index + faqs1.length}`}>
                  <AccordionTrigger className="text-lg font-semibold text-left py-4">{faq.question}</AccordionTrigger>
                  <AccordionContent className="text-base text-muted-foreground pb-4">
                    {faq.answer}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
        </div>
      </div>
    </div>
  );
};

const HireTalentPage = ({ scrollToForm = false }) => {
  const { t } = useTranslation();
  const location = useLocation();

  useEffect(() => {
    if (location.hash === '#hire-form' || scrollToForm) {
      document.getElementById('hire-form')?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [location, scrollToForm]);

  const handleScrollToForm = () => {
    document.getElementById('hire-form')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      <Helmet>
        <title>Hire Vetted Talent & Teams | Pay Per Project</title>
        <meta name="description" content="Access pre-vetted development teams and industry experts. Onshore, nearshore, or offshore. Start building in 48 hours with our project success guarantee." />
      </Helmet>
      <div className="bg-background">
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
            >
              <Award className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-foreground sm:text-6xl">
                Hire Vetted Talent & Teams
              </h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                Stop searching, start building. We provide elite, managed teams and industry experts—vetted for excellence and ready to deliver from day one.
              </p>
              <div className="mt-10 flex items-center justify-center gap-x-6">
                <Button size="lg" onClick={handleScrollToForm} className="shadow-lg shadow-primary/20">
                  Request Talent Now <ChevronsDown className="ml-2 h-5 w-5" />
                </Button>
              </div>
            </motion.div>
          </div>
          <div className="absolute inset-x-0 top-[calc(100%-13rem)] -z-10 transform-gpu overflow-hidden blur-3xl sm:top-[calc(100%-30rem)]" aria-hidden="true">
            <div className="relative left-[calc(50%+3rem)] aspect-[1155/678] w-[36.125rem] -translate-x-1/2 bg-gradient-to-tr from-[#ff80b5] to-[#9089fc] opacity-30 sm:left-[calc(50%+36rem)] sm:w-[72.1875rem]" style={{ clipPath: 'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)' }}></div>
          </div>
        </div>

        <HowItWorksSection />
        <SourcingModelsSection />
        <GlobalNetworkSection />
        <VettingProcessSection />
        <GuaranteeSection />
        <FaqSection />

        <section id="hire-form" className="py-16 sm:py-20 bg-secondary/20">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            <TalentRequestForm />
          </div>
        </section>

      </div>
    </>
  );
};

export default HireTalentPage;
