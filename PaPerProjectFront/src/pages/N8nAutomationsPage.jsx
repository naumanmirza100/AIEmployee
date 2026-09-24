
import React from 'react';
    import { Helmet } from 'react-helmet';
    import { motion } from 'framer-motion';
    import { 
        BrainCircuit, Zap, Bot, ArrowRight, CheckCircle, Target, Sparkles, Users,
        HeartPulse, Home, School, ShoppingCart, BarChart3, Briefcase, DollarSign, Store,
        Headphones, Server, Truck, Scale, Plane, Landmark, Ship
    } from 'lucide-react';
    import { Button } from '@/components/ui/button';
    import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
    import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
    import { Link } from 'react-router-dom';
    import { useTranslation } from 'react-i18next';
    
    const containerVariants = {
      hidden: { opacity: 0 },
      visible: {
        opacity: 1,
        transition: { staggerChildren: 0.1, delayChildren: 0.2 },
      },
    };
    
    const itemVariants = {
      hidden: { opacity: 0, y: 20 },
      visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
    };
    
    const IndustryTabContent = ({ title, description, challenges, solutions }) => (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8"
      >
        <Card className="bg-card/50 backdrop-blur-sm border-border/50">
          <CardHeader>
            <CardTitle className="text-2xl font-bold text-foreground">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <h4 className="font-semibold text-lg text-foreground">Challenges Solved:</h4>
              <ul className="space-y-3">
                {challenges.map((challenge, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <CheckCircle className="h-5 w-5 text-primary mt-1 flex-shrink-0" />
                    <span className="text-muted-foreground">{challenge}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-primary/5 border-primary/20">
          <CardHeader>
            <CardTitle className="text-2xl font-bold text-primary">Our n8n-Powered Solutions</CardTitle>
            <CardDescription>How we deploy custom workflows to drive results.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {solutions.map((solution, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-primary/10">
                  <Zap className="h-5 w-5 text-primary mt-1 flex-shrink-0" />
                  <div>
                    <h5 className="font-semibold text-foreground">{solution.title}</h5>
                    <p className="text-sm text-muted-foreground">{solution.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
    
    const N8nAutomationsPage = () => {
      const { t } = useTranslation();
    
      const industries = [
        {
          id: 'customer-service',
          name: 'Customer Service',
          icon: Headphones,
          title: 'Automating Support & Enhancing CX',
          description: 'n8n workflows connect your helpdesk, CRM, and communication channels to deliver faster, smarter customer support.',
          challenges: [
            'High volume of repetitive support tickets.',
            'Slow response times and resolution rates.',
            'Difficulty routing tickets to the right agent.',
            'Lack of proactive customer communication.'
          ],
          solutions: [
            { title: 'AI-Powered Ticket Triage', desc: 'Automatically categorize, prioritize, and route incoming tickets using AI analysis.' },
            { title: 'Automated Status Updates', desc: 'Keep customers informed about their ticket status via email or SMS without agent intervention.' },
            { title: 'Self-Service Portals', desc: 'Build workflows that allow customers to find answers and resolve issues on their own.' }
          ]
        },
        {
          id: 'it-saas',
          name: 'IT & SaaS',
          icon: Server,
          title: 'Automating Operations for Tech Companies',
          description: 'From user provisioning to incident response, n8n automates critical IT and SaaS operations for ultimate efficiency.',
          challenges: [
            'Manual user account creation and permissions management.',
            'Delayed response to system alerts and incidents.',
            'Complexities in managing subscription billing and renewals.',
            'Time-consuming data migrations and system integrations.'
          ],
          solutions: [
            { title: 'Automated User Provisioning', desc: 'Instantly create accounts across all your apps for new users based on their role.' },
            { title: 'Incident Response Workflow', desc: 'Automatically create tickets, notify on-call engineers, and post updates to status pages when an alert is triggered.' },
            { title: 'Subscription Management', desc: 'Automate dunning emails for failed payments and manage subscription lifecycle events.' }
          ]
        },
        {
          id: 'logistics',
          name: 'Logistics & Supply Chain',
          icon: Truck,
          title: 'Optimizing Every Link in Your Supply Chain',
          description: 'n8n connects your WMS, TMS, and ERP systems to create end-to-end visibility and automation from warehouse to final delivery.',
          challenges: [
            'Lack of real-time shipment tracking and visibility.',
            'Manual coordination between suppliers, carriers, and warehouses.',
            'Inefficient inventory management and demand forecasting.',
            'Complex customs documentation and compliance.'
          ],
          solutions: [
            { title: 'Real-Time Shipment Tracking', desc: 'Aggregate tracking data from multiple carriers into a single dashboard and provide proactive customer updates.' },
            { title: 'Automated PO & ASN Processing', desc: 'Automatically process purchase orders and advance shipping notices to streamline receiving.' },
            { title: 'Inventory Sync & Forecasting', desc: 'Keep inventory levels accurate across all systems and use historical data to predict future demand.' }
          ]
        },
        {
          id: 'hr-recruiting',
          name: 'HR & Recruiting',
          icon: Users,
          title: 'Streamlining the Employee & Candidate Lifecycle',
          description: 'From onboarding to offboarding, n8n automates repetitive HR tasks, freeing up your team to focus on people, not paperwork.',
          challenges: [
            'Time-consuming and error-prone employee onboarding process.',
            'Manual tracking of leave requests and approvals.',
            'Inconsistent communication during recruitment.',
            'Difficulty gathering and analyzing employee feedback.'
          ],
          solutions: [
            { title: 'Zero-Touch Onboarding', desc: 'Automatically create user accounts, assign training, and schedule welcome meetings for new hires.' },
            { title: 'Automated Leave Management', desc: 'Allow employees to request leave via Slack, which is then automatically routed for approval and added to the company calendar.' },
            { title: 'Candidate Nurturing Workflows', desc: 'Keep candidates engaged with automated updates and interview scheduling.' }
          ]
        },
        {
          id: 'legal-compliance',
          name: 'Legal & Compliance',
          icon: Scale,
          title: 'Automating Legal Operations & Ensuring Compliance',
          description: 'n8n automates document generation, contract management, and compliance monitoring, reducing risk and manual effort.',
          challenges: [
            'Manual creation of standard legal documents like NDAs.',
            'Difficulty tracking contract renewal and expiration dates.',
            'Time-consuming due diligence and background checks.',
            'Ensuring consistent compliance across the organization.'
          ],
          solutions: [
            { title: 'Automated Document Generation', desc: 'Create and send customized legal agreements in seconds based on data from your CRM.' },
            { title: 'Contract Lifecycle Management', desc: 'Automatically track key dates, send renewal reminders, and manage contract approvals.' },
            { title: 'Compliance Monitoring', desc: 'Build workflows to automatically audit systems and processes for compliance with regulations like GDPR or SOC 2.' }
          ]
        },
        {
          id: 'travel-hospitality',
          name: 'Travel & Hospitality',
          icon: Plane,
          title: 'Creating Seamless Guest & Traveler Experiences',
          description: 'Automate bookings, guest communication, and operations to deliver 5-star service from check-in to check-out.',
          challenges: [
            'Manual booking confirmations and pre-arrival communication.',
            'Difficulty managing guest requests and housekeeping schedules.',
            'Inconsistent post-stay follow-up and review requests.',
            'Price and availability synchronization across multiple booking platforms.'
          ],
          solutions: [
            { title: 'Automated Guest Communication', desc: 'Send booking confirmations, pre-arrival guides, and check-in instructions automatically.' },
            { title: 'Operations Dashboard', desc: 'Coordinate housekeeping, maintenance, and guest requests from a single, automated dashboard.' },
            { title: 'Review Generation Engine', desc: 'Automatically send personalized requests for reviews on Google, TripAdvisor, and other platforms post-stay.' }
          ]
        },
        {
          id: 'finance-insurance',
          name: 'Finance & Insurance',
          icon: Landmark,
          title: 'Automating Financial & Insurance Processes',
          description: 'n8n connects your bank, accounting software, and core systems to automate claims, underwriting, and financial reporting.',
          challenges: [
            'Manual data entry for claims processing and underwriting.',
            'Delayed and inaccurate financial reporting and reconciliation.',
            'Chasing late payments and managing policy renewals.',
            'Complexities in ensuring regulatory compliance (KYC/AML).'
          ],
          solutions: [
            { title: 'Automated Claims Processing', desc: 'Extract data from first notice of loss (FNOL) forms, create a claim record, and assign it to an adjuster automatically.' },
            { title: 'Real-Time Financial Dashboards', desc: 'Aggregate data from all your financial tools into a live dashboard for instant insights.' },
            { title: 'Policy Renewal Automation', desc: 'Automatically notify clients of upcoming renewals and generate renewal documentation.' }
          ]
        },
        {
          id: 'ecommerce',
          name: 'E-commerce',
          icon: Store,
          title: 'Automating the Entire Customer Journey',
          description: 'n8n workflows connect your storefront, CRM, and marketing tools to create a seamless, automated e-commerce machine.',
          challenges: [
            'Manual order processing and fulfillment tracking.',
            'High rates of abandoned carts with no follow-up.',
            'Difficulty syncing inventory across multiple sales channels.',
            'Generic post-purchase communication.'
          ],
          solutions: [
            { title: 'Automated Order Fulfillment', desc: 'Instantly push new orders to your 3PL, update inventory, and notify customers at every step.' },
            { title: 'Abandoned Cart Recovery', desc: 'Trigger personalized email or SMS sequences to recover lost sales automatically.' },
            { title: 'Multi-Channel Inventory Sync', desc: 'Keep stock levels perfectly synchronized between Shopify, Amazon, and your warehouse.' }
          ]
        },
      ];
    
      return (
        <>
          <Helmet>
            <title>n8n & AI Automation Solutions | Pay Per Project</title>
            <meta name="description" content="Harness the power of n8n and AI to build powerful, custom workflow automations. We connect your apps and automate your business processes." />
          </Helmet>
          <div className="bg-background text-foreground">
            <section className="relative isolate overflow-hidden pt-32 pb-24 md:pt-48 md:pb-32">
              <div className="absolute inset-0 -z-10 h-full w-full bg-background bg-[radial-gradient(#ffffff20_1px,transparent_1px)] [background-size:16px_16px]"></div>
              <div className="absolute inset-x-0 top-1/2 -z-10 -translate-y-1/2 transform-gpu overflow-hidden opacity-20 blur-3xl" aria-hidden="true">
                <div className="mx-auto aspect-[1155/678] w-[72.1875rem] bg-gradient-to-tr from-primary to-purple-500" style={{ clipPath: 'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)' }}></div>
              </div>
              <div className="container mx-auto px-4 text-center">
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.2 }}>
                  <div className="inline-flex items-center justify-center rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary mb-4">
                    <img-replace alt="n8n logo" className="h-5 w-5 mr-2" />
                    Powered by n8n & AI
                  </div>
                  <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-glow">
                    Workflow Automation on Steroids
                  </h1>
                  <p className="mt-6 max-w-3xl mx-auto text-lg text-muted-foreground">
                    We use the limitless power of <strong className="text-primary font-bold">n8n</strong> and AI to connect all your apps and build custom workflows that put your business on autopilot.
                  </p>
                  <div className="mt-10 flex items-center justify-center gap-x-6">
                    <Button asChild size="lg" className="text-lg">
                      <Link to="/start-project">
                        Automate Your Business
                        <Zap className="ml-2 h-5 w-5" />
                      </Link>
                    </Button>
                  </div>
                </motion.div>
              </div>
            </section>
    
            <motion.section
              variants={containerVariants}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.1 }}
              className="py-24 bg-secondary/40"
            >
              <div className="container mx-auto px-4">
                <div className="text-center mb-16">
                  <motion.h2 variants={itemVariants} className="text-3xl md:text-4xl font-extrabold tracking-tight">The Ultimate Automation Engine: Why We Choose n8n</motion.h2>
                  <motion.p variants={itemVariants} className="mt-4 max-w-3xl mx-auto text-lg text-muted-foreground">
                    n8n is more than just a tool; it's a fair-code, source-available platform that gives us the power to build anything you can imagine, without limits.
                  </motion.p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><Zap className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Infinite Connectivity</h3>
                      <p className="text-muted-foreground mt-2">With 400+ native integrations and the ability to connect to any API, there's no system we can't automate. Your entire tech stack becomes one seamless machine.</p>
                    </Card>
                  </motion.div>
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><BrainCircuit className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Custom Logic & AI</h3>
                      <p className="text-muted-foreground mt-2">We go beyond simple "if-this-then-that". We build complex, multi-step workflows with custom logic and infuse them with AI for intelligent decision-making.</p>
                    </Card>
                  </motion.div>
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><Users className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Scalable & Secure</h3>
                      <p className="text-muted-foreground mt-2">Built for performance, n8n can handle enterprise-level volume. We can host it on your infrastructure, ensuring your data stays secure and compliant.</p>
                    </Card>
                  </motion.div>
                </div>
              </div>
            </motion.section>
    
            <section className="py-24">
              <div className="container mx-auto px-4">
                <div className="text-center mb-16">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">Industry Transformation with n8n</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">
                    See how our custom n8n workflows are delivering game-changing efficiency across key sectors.
                  </p>
                </div>
                <Tabs defaultValue={industries[0].id} className="w-full">
                  <TabsList className="grid w-full grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2 h-auto p-2">
                    {industries.map(industry => (
                      <TabsTrigger key={industry.id} value={industry.id} className="flex-col h-auto py-3 px-2 gap-2">
                        <industry.icon className="h-6 w-6" />
                        <span className="text-center text-xs sm:text-sm">{industry.name}</span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {industries.map(industry => (
                    <TabsContent key={industry.id} value={industry.id}>
                      <IndustryTabContent {...industry} />
                    </TabsContent>
                  ))}
                </Tabs>
              </div>
            </section>
    
            <section className="py-24 bg-secondary/40">
              <div className="container mx-auto px-4">
                <div className="bg-gradient-to-r from-gray-900 to-black rounded-2xl p-8 md:p-16 text-center text-pure-white shadow-2xl relative overflow-hidden">
                    <div className="absolute inset-0 -z-10 opacity-10">
                        <img-replace alt="Abstract workflow visualization" className="w-full h-full object-cover" />
                    </div>
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.7 }}
                  >
                    <Sparkles className="h-16 w-16 mx-auto text-primary mb-6" />
                    <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to Automate the Repetitive?</h2>
                    <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8">
                      Stop wasting time on tasks a machine can do. Let our n8n experts design and build the custom workflows that will free you up to focus on what truly matters.
                    </p>
                    <Button asChild size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105">
                      <Link to="/start-project">
                        Get Your Automation Roadmap <ArrowRight className="ml-2 h-5 w-5" />
                      </Link>
                    </Button>
                  </motion.div>
                </div>
              </div>
            </section>
          </div>
        </>
      );
    };
    
    export default N8nAutomationsPage;
