
import React from 'react';
    import { Helmet } from 'react-helmet';
    import { motion } from 'framer-motion';
    import { 
        BrainCircuit, Zap, Bot, ArrowRight, CheckCircle, Target, Sparkles, Users,
        HeartPulse, Home, School, ShoppingCart,
        Headphones, Server, Truck, Scale, Plane, Landmark, HelpCircle, Workflow,
        TrendingDown, UserCog, DollarSign
    } from 'lucide-react';
    import { Button } from '@/components/ui/button';
    import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
    import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
    import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
    import { Link } from 'react-router-dom';
    
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

    const CaseStudy = ({ title, flow, outcome }) => (
      <div className="flex flex-col gap-4 p-4 rounded-lg bg-primary/10 border border-primary/20 h-full">
        <div className="flex items-center gap-3">
          <Bot className="h-6 w-6 text-primary flex-shrink-0" />
          <h5 className="font-bold text-lg text-foreground">{title}</h5>
        </div>
        <div className="pl-9 space-y-3 flex-grow">
          <p className="text-sm font-semibold text-muted-foreground flex items-center gap-2"><Workflow className="h-4 w-4" /> Automation Flow:</p>
          <ol className="relative border-l border-primary/30 space-y-4 pl-6">
            {flow.map((step, i) => (
              <li key={i} className="text-sm text-muted-foreground">
                <span className="absolute -left-2 flex h-4 w-4 items-center justify-center rounded-full bg-primary/20 text-primary ring-4 ring-background">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>
        <div className="pl-9 mt-2">
           <p className="text-sm font-semibold text-foreground flex items-center gap-2"><CheckCircle className="h-4 w-4 text-green-500" /> Outcome:</p>
           <p className="text-sm text-green-400 font-medium pl-6">{outcome}</p>
        </div>
      </div>
    );
    
    const IndustryTabContent = ({ title, description, challenges, solutions }) => (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8 items-stretch"
      >
        <Card className="bg-card/50 backdrop-blur-sm border-border/50 flex flex-col">
          <CardHeader>
            <CardTitle className="text-2xl font-bold text-foreground">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent className="flex-grow">
            <div className="space-y-6">
              <h3 className="text-xl font-bold text-foreground">Overcoming Industry-Specific Hurdles</h3>
              <p className="text-muted-foreground text-sm">
                Every industry faces unique operational bottlenecks and strategic challenges. Our Agentic AI solutions are precisely engineered to tackle these complex issues head-on, transforming obstacles into opportunities for growth and efficiency.
              </p>
              
              {Object.entries(challenges).map(([category, items]) => (
                <div key={category}>
                  <h4 className="font-semibold text-lg text-foreground flex items-center gap-2 mb-3">
                    {category === 'Operational Inefficiencies' && <TrendingDown className="h-5 w-5 text-destructive/70" />}
                    {category === 'Strategic Limitations' && <UserCog className="h-5 w-5 text-destructive/70" />}
                    {category === 'Financial Hurdles' && <DollarSign className="h-5 w-5 text-destructive/70" />}
                    {category}
                  </h4>
                  <ul className="space-y-3">
                    {items.map((challenge, i) => (
                      <li key={i} className="flex items-start gap-3">
                        <Target className="h-5 w-5 text-primary/50 mt-1 flex-shrink-0" />
                        <span className="text-muted-foreground">{challenge}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-primary/5 border-primary/20 flex flex-col">
          <CardHeader>
            <CardTitle className="text-2xl font-bold text-primary">Agentic AI Case Studies</CardTitle>
            <CardDescription>How our autonomous agents drive results.</CardDescription>
          </CardHeader>
          <CardContent className="flex-grow flex flex-col">
            <div className="space-y-6 flex-grow flex flex-col">
              {solutions.map((solution, i) => (
                <div key={i} className="flex-grow flex">
                  <CaseStudy {...solution} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
    
    const AiAutomationsPage = () => {
      const industries = [
        {
          id: 'customer-service',
          name: 'Customer Service',
          icon: Headphones,
          title: 'Autonomous Support & Proactive Engagement',
          description: 'Agentic AI transforms your support from reactive to predictive, resolving issues before they escalate.',
          challenges: {
            'Operational Inefficiencies': [
              'Inability to provide 24/7 instant support, causing customer frustration.',
              'Skilled agents are bogged down by repetitive, low-value queries.',
              'Slow response times during peak hours, leading to customer abandonment.',
              'Manual and time-consuming process for categorizing and routing support tickets.',
            ],
            'Strategic Limitations': [
              'Inconsistent service quality across different agents and channels.',
              'Lack of personalized customer interactions at scale, impacting loyalty.',
              'No actionable insights derived from vast amounts of customer interaction data.',
              'Difficulty in proactively identifying customer pain points before they complain.',
            ],
            'Financial Hurdles': [
              'High agent turnover and costly, repetitive training cycles.',
              'Difficulty in effectively identifying and acting on up-selling opportunities.',
              'High operational costs for maintaining a large, multi-lingual support team.',
              'Revenue loss from customers churning due to poor support experiences.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: AI Support Agent for "Where Is My Order?"', 
              flow: [
                'A customer emails: "where is my order #12345?".',
                'The AI Agent reads the email, identifies the intent, and extracts the order number.',
                'It connects to the Shopify API to get the order status and tracking number.',
                'It connects to the FedEx API to get the real-time shipping status.',
                'The agent composes and sends a detailed reply: "Hi Jane, your order #12345 is currently out for delivery and is expected today. You can track it here: [link]".'
              ],
              outcome: 'Automated 70% of all incoming support tickets, providing instant resolution 24/7 and freeing up agents for complex issues.'
            },
            {
              title: 'Case Study: Proactive Churn Prevention Agent',
              flow: [
                'AI Agent monitors user activity in a SaaS product, detecting a 50% drop in a user\'s engagement over 14 days.',
                'The agent analyzes the user\'s feature usage and identifies they haven\'t used a key new feature.',
                'It automatically sends a personalized email: "Hi John, I noticed you haven\'t tried our new reporting dashboard. Here\'s a 2-minute video on how it can save you time."',
                'If the user still doesn\'t engage, the agent creates and assigns a task for a human success manager to personally call them, providing full context.'
              ],
              outcome: 'Reduced customer churn by 15% by proactively re-engaging at-risk users with tailored content and interventions.'
            }
          ]
        },
        {
          id: 'dental',
          name: 'Dental & Healthcare',
          icon: HeartPulse,
          title: 'The Autonomous Medical Practice',
          description: 'Agentic AI streamlines patient management and administrative tasks, allowing practitioners to focus on care.',
          challenges: {
            'Operational Inefficiencies': [
              'High volume of appointment scheduling, rescheduling, and reminder calls.',
              'Time-consuming and inaccurate manual data entry from patient forms.',
              'Inefficient follow-up for post-treatment care and instructions.',
              'Managing inventory of dental supplies and ordering is a manual process.',
              'Coordinating with labs and specialists is often a manual, phone-based process.',
            ],
            'Strategic Limitations': [
              'Difficulty managing patient recall for routine check-ups and follow-ups.',
              'Ensuring strict HIPAA compliance across all patient communications.',
              'Lack of personalized patient education and communication at scale.',
              'Difficulty in analyzing patient population data for public health trends or practice growth.',
            ],
            'Financial Hurdles': [
              'Complex and error-prone insurance verification and billing processes.',
              'Significant revenue loss from patient no-shows and last-minute cancellations.',
              'Delayed revenue cycles due to slow claims processing and follow-up.',
              'Managing accounts receivable and chasing overdue patient payments is a drain on resources.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: AI Appointment Scheduler', 
              flow: [
                'Patient requests an appointment via web form, understanding natural language like "next Tuesday afternoon".',
                'AI Agent captures the request, understands intent (e.g., "cleaning", "toothache"), and accesses patient records for context.',
                'Agent connects to practice management software to find optimal slots based on procedure type, doctor availability, and room allocation.',
                'Agent proposes the 3 best slots to the patient via SMS/email.',
                'Patient confirms a slot by replying "1", "2", or "3". The agent books the appointment, sends confirmation, and updates all relevant calendars automatically.'
              ],
              outcome: 'Reduced front-desk workload by 60%, cut scheduling errors to zero, and decreased no-shows by 30% through automated reminders.'
            },
            { 
              title: 'Case Study: Automated Insurance Verification', 
              flow: [
                '72 hours before an appointment, the AI Agent is automatically triggered.',
                'It extracts patient and insurance details from the practice management system.',
                'The agent securely logs into the respective insurance provider\'s portal using stored credentials.',
                'It navigates the portal to verify coverage, co-pay, and deductible information in real-time.',
                'The agent updates the patient\'s file with the verification details and flags any issues (e.g., "coverage expired") for staff review, preventing billing surprises.'
              ],
              outcome: 'Eliminated 100% of manual verification tasks, saving 15+ staff hours per week and increasing upfront collections.'
            },
          ]
        },
        {
          id: 'education',
          name: 'Education',
          icon: School,
          title: 'The Personalized AI Tutor & Administrator',
          description: 'Agentic AI personalizes learning for every student and automates school administration for ultimate efficiency.',
          challenges: {
            'Operational Inefficiencies': [
              'High administrative burden on teachers and staff, taking time away from teaching.',
              'Manual grading of assignments is time-consuming and can be inconsistent.',
              'Managing admissions and enrollment processes is a heavy manual workload.',
              'Coordinating schedules for parent-teacher conferences is a logistical nightmare.',
            ],
            'Strategic Limitations': [
              'Inability to provide true one-on-one attention to every student.',
              'Difficulty tracking student progress in real-time and identifying at-risk students early.',
              'Generic, one-size-fits-all curriculum delivery fails to engage all students.',
              'Parent-teacher communication is often slow, inefficient, and lacks detail.',
            ],
            'Financial Hurdles': [
                'High cost of specialized tutoring services for students who need extra help.',
                'Budget constraints limiting the adoption of new educational technologies.',
                'Inefficient resource allocation and timetable planning leading to waste.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Personalized Learning Agent', 
              flow: [
                'A student completes a math quiz within the Learning Management System (LMS).',
                'The AI Agent analyzes their results, identifying a specific weakness in "long division with remainders".',
                'It automatically assigns a 5-minute explainer video, two practice exercises, and a gamified mini-challenge on that topic.',
                'If the student struggles, the agent notifies the teacher with a summary: "Maria is having trouble with step 3 of long division."',
                'Upon success, the agent unlocks the next topic and awards the student a badge.'
              ],
              outcome: 'Improved average test scores by 18% and increased student engagement by 45% with personalized, adaptive learning paths.'
            },
            { 
              title: 'Case Study: AI Admissions Officer', 
              flow: [
                'A prospective student asks a complex question on the university website: "What are the application deadlines for international students in engineering?".',
                'The AI Agent provides an instant, accurate answer by referencing a knowledge base of admissions information.',
                'It then prompts the user: "Would you like to book a virtual tour with an engineering faculty member?".',
                'If yes, the agent checks faculty calendars, presents available dates, books the tour, and sends a confirmation email with a video call link.'
              ],
              outcome: 'Handled 85% of inbound admission queries automatically, allowing staff to focus on high-value, personalized recruitment activities.'
            },
          ]
        },
        {
          id: 'finance-insurance',
          name: 'Finance & Insurance',
          icon: Landmark,
          title: 'Autonomous Finance & Risk Assessment',
          description: 'Agentic AI automates underwriting, claims processing, and financial analysis with superhuman speed and accuracy.',
          challenges: {
            'Operational Inefficiencies': [
              'Slow, manual, and potentially biased underwriting and loan approval processes.',
              'Extremely time-consuming manual financial reconciliation at month-end.',
              'Lengthy and expensive customer onboarding (KYC/AML) processes.',
              'Extracting meaningful insights from unstructured financial reports is a manual task.',
              'Generating and distributing periodic client reports is a manual, repetitive task.',
            ],
            'Strategic Limitations': [
              'Inaccurate risk modeling based on historical data alone.',
              'Struggle to ensure continuous compliance with rapidly changing global regulations.',
              'Manual portfolio management is slow and reactive, missing market opportunities.',
              'Inability to offer hyper-personalized financial products and advice at scale.',
              'Slow adaptation to new fintech innovations and customer expectations.',
            ],
            'Financial Hurdles': [
              'High incidence of sophisticated fraudulent claims and financial transactions.',
              'Significant costs associated with regulatory fines for non-compliance.',
              'Revenue leakage from inefficient collections and billing processes.',
              'High cost of capital due to inefficient risk assessment and management.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Autonomous Claims Adjuster', 
              flow: [
                'A policyholder submits a minor auto insurance claim via a mobile app, including photos of the damage.',
                'The AI Agent receives the claim, using computer vision to analyze photos, identify the damaged part (e.g., "cracked bumper"), and estimate repair costs from a parts database.',
                'It cross-references the policy to confirm coverage, checks for fraud indicators by analyzing claim history and photo metadata.',
                'Since the cost is below the $2,500 threshold for auto-approval, the agent approves the claim and initiates the payment to the policyholder, all within minutes.'
              ],
              outcome: 'Reduced claim processing time for minor incidents from 5 days to 5 minutes, cutting operational costs by 40%.'
            },
            {
              title: 'Case Study: AI Financial Reconciliation Agent',
              flow: [
                'At the end of each day, the AI Agent is triggered to perform reconciliation.',
                'It pulls transaction data from bank accounts, credit card statements, and payment gateways (Stripe, PayPal).',
                'The agent then fetches corresponding invoices and expense reports from the accounting software (QuickBooks).',
                'It intelligently matches transactions, flags discrepancies (e.g., amount mismatch), and categorizes expenses automatically based on learned patterns.',
                'A daily reconciliation report is generated and sent to the finance team for a 5-minute review and approval.'
              ],
              outcome: 'Reduced month-end closing time from 3 days to 4 hours and eliminated 99% of manual data entry errors.'
            }
          ]
        },
        {
          id: 'hr-recruiting',
          name: 'HR & Recruiting',
          icon: Users,
          title: 'The Autonomous HR Business Partner',
          description: 'Agentic AI handles the entire talent lifecycle, from sourcing candidates to managing employee development.',
          challenges: {
            'Operational Inefficiencies': [
              'Time-consuming screening of thousands of unqualified candidates for a single role.',
              'Inconsistent and impersonal onboarding experience for new hires.',
              'Answering repetitive HR policy questions from employees.',
              'Scheduling interviews across multiple calendars is a time-consuming effort.',
              'Manual tracking of employee time-off requests and approvals.',
            ],
            'Strategic Limitations': [
              'Pervasive unconscious bias in the resume screening and hiring process.',
              'Low employee engagement in internal training and development programs.',
              'Managing employee performance reviews and feedback cycles is a manual burden.',
              'Difficulty in identifying internal talent for promotion and new roles.',
              'Lack of data-driven insights into workforce planning and skill gaps.',
            ],
            'Financial Hurdles': [
              'High cost-per-hire and long time-to-fill roles, impacting business goals.',
              'High employee turnover rates due to poor onboarding and engagement.',
              'Costs associated with compliance reporting and maintaining employee records.',
              'Inefficient management of compensation and benefits administration.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: AI Recruiting Agent', 
              flow: [
                'A new "Senior Python Developer" role is opened in Greenhouse (ATS).',
                'The AI Agent reads the job description, understands the nuances, and creates a boolean search query for LinkedIn Recruiter.',
                'It identifies 50 top-tier potential candidates and sends personalized connection requests referencing their specific experience.',
                'For those who accept, it follows up with a message gauging interest and asking 3 key screening questions.',
                'Candidates who respond positively and pass the screeners are automatically added back into Greenhouse as prospects for the hiring manager to review.'
              ],
              outcome: 'Reduced time-to-source from 10+ hours per week to just 30 minutes of final review time, increasing candidate quality by 35%.'
            },
            {
              title: 'Case Study: Automated Onboarding Buddy',
              flow: [
                'A new hire\'s start date is entered into the HRIS (e.g., Workday).',
                'One week before start, the AI Agent provisions all necessary accounts (Email, Slack, Jira).',
                'On Day 1, it sends a welcome message on Slack, introducing the new hire to their team and sharing the week\'s personalized schedule.',
                'Each day for the first week, it sends a task, like "Complete your compliance training" with a direct link, and checks for completion.',
                'It also answers common questions like "Where can I find the company handbook?" or "How do I set up my benefits?".'
              ],
              outcome: 'Achieved a 98% new hire satisfaction rate with the onboarding process and saved 8 hours of HR/manager time per new hire.'
            }
          ]
        },
        {
          id: 'it-saas',
          name: 'IT & SaaS',
          icon: Server,
          title: 'Self-Healing Systems & Autonomous Operations',
          description: 'Our AI agents monitor, manage, and maintain your infrastructure, ensuring maximum uptime and security.',
          challenges: {
            'Operational Inefficiencies': [
              'Constant alert fatigue for DevOps teams, leading to slow incident response.',
              'Manual and error-prone system configuration and patch management.',
              'Lengthy root cause analysis (RCA) process after an incident.',
              'Managing user access and permissions across dozens of systems.',
              'Onboarding and offboarding users from multiple SaaS applications is a manual chore.',
            ],
            'Strategic Limitations': [
              'Difficulty scaling infrastructure efficiently to meet fluctuating demand.',
              'Documentation for systems and processes is often outdated or non-existent.',
              'Security vulnerabilities introduced by human error and misconfigurations.',
              'Inability to proactively detect and remediate security threats in real-time.',
              'Lack of visibility into SaaS license usage and optimization opportunities.',
            ],
            'Financial Hurdles': [
              'High and unpredictable cloud computing costs from inefficient resource allocation.',
              'Significant financial impact of system downtime and service outages.',
              'Cost of maintaining a large on-call team for 24/7 monitoring.',
              'Wasted spend on unused software licenses and subscriptions ("shelfware").',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Self-Healing Infrastructure Agent', 
              flow: [
                'Monitoring tool (Datadog) detects high CPU usage on a web server and sends an alert to the AI Agent.',
                'The agent SSHs into the server, runs `top` to identify the rogue process, and analyzes its nature.',
                'It determines the process is a non-critical logging script gone wild, not a core application process.',
                'The agent kills the process, CPU usage returns to normal, and it creates a ticket for the dev team to fix the script bug, attaching relevant logs.',
                'A summary of the incident and resolution is posted to the team\'s Slack channel.'
              ],
              outcome: 'Reduced Mean Time to Resolution (MTTR) for P2 incidents from 45 minutes to 90 seconds, preventing downtime.'
            },
            {
              title: 'Case Study: AI Cloud Cost Optimizer',
              flow: [
                'The AI Agent continuously analyzes AWS billing and usage data.',
                'It identifies an underutilized `m5.2xlarge` EC2 instance that has been running at 10% CPU for 30 days.',
                'The agent cross-references the instance tags to identify the owner and project.',
                'It automatically sends a Slack message to the project owner: "I noticed your server `proj-x-web-01` is underutilized. I recommend downsizing to an `m5.large` to save ~$250/month. Reply \'APPROVE\' to apply this change during the next maintenance window."',
                'Upon approval, the agent schedules the change in the AWS console.'
              ],
              outcome: 'Reduced monthly AWS bill by 25% without impacting performance through proactive, data-driven recommendations.'
            }
          ]
        },
        {
          id: 'legal-compliance',
          name: 'Legal & Compliance',
          icon: Scale,
          title: 'Autonomous GRC (Governance, Risk, & Compliance)',
          description: 'AI agents continuously monitor your organization, ensuring adherence to regulations and mitigating risk automatically.',
          challenges: {
            'Operational Inefficiencies': [
              'Manual, periodic compliance audits that miss real-time issues.',
              'Slow turnaround and complexity of senior-level contract review.',
              'Massively inefficient e-discovery and document review for litigation.',
              'Responding to regulatory inquiries is a slow, manual process.',
              'Tracking and managing policy attestations and employee training is manual.',
            ],
            'Strategic Limitations': [
              'Struggling to keep up with the ever-changing landscape of global regulations.',
              'Difficulty in enforcing internal policies consistently across the organization.',
              'Lack of a centralized, auditable trail for compliance activities.',
              'Inability to proactively identify and assess emerging legal risks.',
              'Difficulty in performing third-party vendor risk assessments at scale.',
            ],
            'Financial Hurdles': [
              'High cost of manual compliance and legal review processes.',
              'Significant risk of human error in critical due diligence processes.',
              'Potential for massive fines due to non-compliance.',
              'Expensive litigation costs driven by inefficient discovery processes.',
              'High insurance premiums due to perceived unmanaged risk.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Autonomous Contract Analysis Agent', 
              flow: [
                'A salesperson uploads a new client MSA (Master Service Agreement) to a shared drive.',
                'The AI Agent is triggered, opens the document, and digitizes its text.',
                'It compares every clause against the company\'s standard legal playbook, understanding the semantic meaning, not just keywords.',
                'It flags 3 non-standard clauses (e.g., "Unlimited Liability", "Non-standard payment terms").',
                'The agent generates a summary report for the legal team, highlighting the risks, suggesting approved alternative language, and assigning a risk score.'
              ],
              outcome: 'Reduced legal review time for standard contracts from 3 days to 4 hours, allowing legal team to focus on high-risk negotiations.'
            },
            {
              title: 'Case Study: Continuous Compliance Monitor',
              flow: [
                'The AI Agent is connected to the company\'s cloud environment (AWS, Azure).',
                'It continuously scans for configurations that violate compliance frameworks like SOC 2 or HIPAA (e.g., an S3 bucket is accidentally made public).',
                'Upon detecting a violation, the agent immediately reverts the setting to a secure state to stop data exposure.',
                'It then creates a high-priority ticket in Jira with details of the incident, the user who made the change, and the remediation action taken.',
                'An alert is sent to the security team\'s on-call channel with a full audit trail.'
              ],
              outcome: 'Prevented 100% of configuration-related compliance breaches in real-time, ensuring a constant state of audit-readiness.'
            }
          ]
        },
        {
          id: 'logistics',
          name: 'Logistics & Supply Chain',
          icon: Truck,
          title: 'The Self-Optimizing Supply Chain',
          description: 'Agentic AI creates a fully autonomous supply chain that predicts disruptions and optimizes routes in real-time.',
          challenges: {
            'Operational Inefficiencies': [
              'Unexpected delays from weather, port congestion, and other disruptions.',
              'Inefficient routing and carrier selection.',
              'Lack of real-time, end-to-end visibility into shipment status.',
              'Managing returns and reverse logistics is a costly and chaotic process.',
              'Manual processing of freight invoices and auditing for accuracy.',
            ],
            'Strategic Limitations': [
              'Inaccurate demand forecasting leading to stockouts or overstock.',
              'Complex and error-prone customs and trade compliance documentation.',
              'Optimizing warehouse inventory placement and picking routes.',
              'Inability to dynamically re-route shipments in response to real-time events.',
              'Difficulty in selecting suppliers based on performance, cost, and risk.',
            ],
            'Financial Hurdles': [
              'High operational costs from inefficient processes.',
              'High fuel costs due to unoptimized delivery routes.',
              'Revenue loss from delivery failures and delays.',
              'Penalties and fines from customs compliance errors.',
              'Capital tied up in excess inventory due to poor forecasting.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Predictive Logistics Agent', 
              flow: [
                'The AI Agent monitors a shipment\'s route from Shanghai to Los Angeles.',
                'It ingests real-time data: weather reports, port congestion data from LA, and the vessel\'s GPS location.',
                'The agent detects a new storm forming on the planned route and predicts a 3-day delay based on historical storm impact data.',
                'It automatically notifies the supply chain manager and the end customer of the potential delay.',
                'Simultaneously, it analyzes air freight costs as an alternative and presents the option to the manager: "Divert to air freight for $5k to ensure on-time delivery?".'
              ],
              outcome: 'Increased on-time delivery rate by 22% by proactively managing disruptions and providing actionable alternatives.'
            },
            {
              title: 'Case Study: Autonomous Freight Brokerage Agent',
              flow: [
                'A new shipment order is created in the Transportation Management System (TMS).',
                'The AI Agent analyzes the shipment details (origin, destination, weight, required delivery date).',
                'It queries multiple carrier portals and load boards via API to find available capacity in real-time.',
                'The agent negotiates rates with carriers\' automated systems based on historical data and current market rates to find the best price.',
                'It selects the optimal carrier based on a combined score of cost, transit time, and reliability, then books the shipment automatically.'
              ],
              outcome: 'Reduced freight costs by 8% and cut booking time from 2 hours to just 3 minutes per shipment.'
            }
          ]
        },
        {
          id: 'real-estate',
          name: 'Real Estate',
          icon: Home,
          title: 'The AI-Powered Real Estate Agency',
          description: 'Our agents automate lead qualification, client communication, and market analysis, helping you close deals faster.',
          challenges: {
            'Operational Inefficiencies': [
              'Agents wasting up to 50% of their time on unqualified leads.',
              'Manually scheduling and coordinating property viewings and follow-ups.',
              'Generating comparative market analysis (CMA) reports is a slow, manual task.',
              'Marketing listings across multiple social media platforms is time-consuming.',
            ],
            'Strategic Limitations': [
              'Struggling to write unique, compelling property descriptions for dozens of listings.',
              'Keeping up with fast-moving market trends and accurately pricing properties.',
              'Inability to provide instant, 24/7 responses to inquiries.',
              'Nurturing long-term leads effectively without a systematic process.',
            ],
            'Financial Hurdles': [
              'High cost of lead generation from multiple online portals.',
              'Lost commission from leads that are not followed up with quickly enough.',
              'Inaccurate property valuations leading to slow sales or leaving money on the table.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: AI Lead Qualification Agent', 
              flow: [
                'A new lead arrives from Zillow, Realtor.com, or your website.',
                'Within 30 seconds, the AI Agent engages the lead via SMS with a natural, conversational tone.',
                'It asks key qualifying questions: "Are you pre-approved?", "What\'s your ideal budget?", "When are you looking to move?".',
                'Based on responses, it categorizes the lead as "Hot", "Warm", or "Nurture" in your CRM.',
                'For "Hot" leads, it automatically offers to schedule a viewing and syncs with the agent\'s live calendar.'
              ],
              outcome: 'Increased agent response time by 95%, boosted qualified lead appointments by 40%, and allowed agents to focus only on ready-to-buy clients.'
            },
            { 
              title: 'Case Study: Generative Listing Creator', 
              flow: [
                'An agent uploads property photos and a few key details (beds, baths, sqft) to a simple form.',
                'The AI Agent analyzes the photos for key features (e.g., "granite countertops", "hardwood floors", "large backyard with a pool").',
                'It generates three distinct, captivating, and SEO-optimized listing descriptions in different tones (e.g., "Luxury", "Family-Friendly", "Modern").',
                'The agent chooses the best one, makes minor edits, and posts it directly to the MLS and social media.'
              ],
              outcome: 'Reduced time to write and post listings from 30 minutes to just 2 minutes per property, ensuring a consistent and high-quality brand voice.'
            },
          ]
        },
        {
          id: 'retail',
          name: 'Retail & E-commerce',
          icon: ShoppingCart,
          title: 'The Autonomous E-commerce Machine',
          description: 'From inventory management to customer service, our AI agents optimize every aspect of your retail operations.',
          challenges: {
            'Operational Inefficiencies': [
              'Inefficient inventory management leading to stockouts or overstock.',
              'Customer support teams being overwhelmed during peak seasons.',
              'Managing returns and exchanges (reverse logistics) is inefficient.',
              'Creating engaging marketing copy for thousands of products is not scalable.',
            ],
            'Strategic Limitations': [
              'Difficulty personalizing product recommendations beyond simple algorithms.',
              'Dynamic pricing to compete with other retailers is a manual, slow process.',
              'Detecting and preventing fraudulent orders without blocking legitimate customers.',
              'Inability to understand customer sentiment from product reviews at scale.',
            ],
            'Financial Hurdles': [
              'High rates of cart abandonment, often due to unexpected costs.',
              'Lost revenue from stockouts and poor inventory planning.',
              'High costs associated with managing a large customer support team.',
              'Decreasing margins due to competitive pricing pressures.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Autonomous Inventory Agent', 
              flow: [
                'The AI Agent monitors real-time sales data from Shopify and inventory levels in the warehouse system.',
                'It analyzes sales velocity, seasonality, and current stock levels for "Product X".',
                'When stock drops below a dynamic threshold (e.g., "2 weeks of supply remaining at current velocity"), the agent is triggered.',
                'It automatically generates a purchase order for the supplier based on lead times and optimal order quantity to minimize carrying costs.',
                'The PO is sent to the procurement manager for a one-click approval.'
              ],
              outcome: 'Reduced stockouts by 90% during peak season and improved inventory turnover by 25%, freeing up cash flow.'
            },
            { 
              title: 'Case Study: AI Shopping Assistant', 
              flow: [
                'A customer on a product page asks, "Does this jacket run large, and is it waterproof?".',
                'The AI Agent instantly analyzes all product reviews, Q&A data, and the product description for that specific jacket.',
                'It synthesizes the information and responds: "Most customers say this jacket fits true to size, but a few mention it\'s slightly snug in the shoulders. It is water-resistant, perfect for light rain, but not fully waterproof for a downpour."',
                'It then follows up: "Would you like to see the detailed size chart or our fully waterproof options?"'
              ],
              outcome: 'Increased conversion rate by 15% on product pages with the AI assistant and reduced support tickets for product questions by 60%.'
            },
          ]
        },
        {
          id: 'travel-hospitality',
          name: 'Travel & Hospitality',
          icon: Plane,
          title: 'The AI-Powered Concierge & Operations Manager',
          description: 'Agentic AI delivers hyper-personalized guest experiences and automates complex back-office operations.',
          challenges: {
            'Operational Inefficiencies': [
              'High operational costs from manual and inefficient staff scheduling.',
              'Inefficiently handling booking modifications, cancellations, and special requests.',
              'Coordinating housekeeping schedules with check-in/check-out times is complex.',
              'Manual processing of invoices and payments from vendors and partners.',
            ],
            'Strategic Limitations': [
              'Generic guest experiences that fail to build loyalty and repeat business.',
              'Difficulty managing guest feedback and online reputation across multiple platforms.',
              'Upselling ancillary services (e.g., spa, tours) is often missed.',
              'Language barriers with international guests leading to poor service.',
            ],
            'Financial Hurdles': [
              'Significant revenue loss from suboptimal pricing and low occupancy rates.',
              'Lost revenue from missed upselling opportunities.',
              'High costs associated with negative online reviews and reputation damage.',
              'Commission fees paid to online travel agencies (OTAs) eating into profits.',
            ],
          },
          solutions: [
            { 
              title: 'Case Study: Dynamic Pricing Agent', 
              flow: [
                'The AI Agent monitors hotel occupancy, competitor pricing (from Booking.com, Expedia), local events (e.g., "Major concert announced"), and flight booking trends in real-time.',
                'It detects a surge in demand for a weekend 3 months away.',
                'The agent automatically increases the room rates for that weekend by 15% across all booking channels to maximize revenue.',
                'Conversely, for a low-demand Tuesday next week, it creates a limited-time "20% off + free breakfast" promotion and pushes it to the email list of past guests.'
              ],
              outcome: 'Increased Revenue Per Available Room (RevPAR) by 12% and occupancy by 8% through intelligent, real-time price adjustments.'
            },
            {
              title: 'Case Study: AI Reputation Manager',
              flow: [
                'The AI Agent scans for new reviews about the hotel on Google, TripAdvisor, and Booking.com.',
                'It uses sentiment analysis to categorize reviews as positive, negative, or neutral.',
                'For positive reviews, it drafts a personalized "thank you" response referencing a detail from their review for the manager to approve.',
                'For negative reviews, it identifies the core complaint (e.g., "slow check-in"), creates a ticket for the relevant department, and drafts a compassionate response acknowledging the issue for the manager to customize and post.'
              ],
              outcome: 'Improved average review score from 4.2 to 4.6 stars in 6 months and ensured 100% of negative reviews were addressed within 2 hours.'
            }
          ]
        },
      ].sort((a, b) => a.name.localeCompare(b.name));
    
      const faqs = [
        { q: "What is Agentic AI and how is it different from regular automation?", a: "Agentic AI goes beyond simple automation. Instead of following pre-programmed rules, our AI 'agents' are autonomous systems that can perceive their environment, make decisions, and take actions to achieve specific goals. They can reason, learn, and adapt, solving problems they've never seen before." },
        { q: "Is this just another name for chatbots?", a: "No. While a chatbot is a simple form of AI, Agentic AI is far more advanced. A chatbot can answer questions. An AI Agent can understand a goal like 'reduce customer churn by 5%', then devise and execute a multi-step strategy across different systems to achieve it." },
        { q: "How do you ensure the AI agents are secure and don't make mistakes?", a: "Security is paramount. Our agents operate in a secure, sandboxed environment with strict permissions. We implement 'human-in-the-loop' protocols for critical decisions, where an agent must get human approval before taking a high-stakes action. They are trained with extensive guardrails to prevent undesirable outcomes." },
        { q: "What kind of ROI can we expect?", a: "Clients typically see significant ROI through three main areas: 1) Drastic reduction in manual labor costs (up to 70%), 2) Increased revenue through optimization and speed (e.g., faster sales cycles, better pricing), and 3) Risk mitigation by reducing human error in critical processes." },
        { q: "How long does it take to implement an AI agent?", a: "Implementation is faster than you might think. We start with a 'pilot' agent to solve a specific, high-impact problem, which can often be deployed in 4-6 weeks. From there, we can scale the solution across your organization." },
        { q: "Do we need a team of data scientists to use this?", a: "No. We provide a fully managed service. Our team of AI experts handles the entire process, from identifying use cases and training the agents to deployment and ongoing optimization. You get the benefits of AI without the overhead." },
        { q: "Can your AI agents integrate with our existing software?", a: "Yes. Our agents are designed to be 'API-first'. They can connect to and operate virtually any modern software with an API, from your CRM and ERP to custom internal tools. They act as a universal connector for your entire tech stack." },
        { q: "How is data privacy handled?", a: "We adhere to the strictest data privacy standards like GDPR and CCPA. Your data is never used to train models for other clients. For sensitive applications, we can deploy the entire AI system within your own private cloud or on-premise infrastructure." },
        { q: "What happens if the AI can't solve a problem?", a: "Our agents are designed with robust 'escalation paths'. When an agent encounters a novel problem it cannot solve, it automatically gathers all relevant context and escalates the issue to a designated human expert for a decision. It then learns from that interaction for the future." },
        { q: "How do you measure the success of an AI agent?", a: "Success is measured against clear, pre-defined KPIs that we establish with you at the start of the project. This could be 'reduce average ticket resolution time by 50%', 'increase sales qualified leads by 30%', or 'achieve 99.9% accuracy in compliance checks'." },
        { q: "What's the difference between your solution and using off-the-shelf AI tools?", a: "Off-the-shelf tools provide generic capabilities. We build custom, purpose-built AI agents that are tailored to your specific business logic, processes, and goals. This results in a much deeper level of integration and a significantly higher impact on your core operations." },
        { q: "How do we get started?", a: "It starts with a simple, no-obligation discovery call. We'll discuss your business challenges and identify the most impactful use case for a pilot AI agent. From there, we'll provide a clear proposal and roadmap for deployment." },
      ];
    
      const half = Math.ceil(faqs.length / 2);
      const firstHalf = faqs.slice(0, half);
      const secondHalf = faqs.slice(half);
    
      return (
        <>
          <Helmet>
            <title>Agentic AI & Automation | Pay Per Project</title>
            <meta name="description" content="Discover how our autonomous Agentic AI solutions are revolutionizing industries with an 89% success rate. We solve your biggest challenges." />
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
                    <Sparkles className="h-5 w-5 mr-2" />
                    The Future of Automation is Here
                  </div>
                  <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-glow">
                    Welcome to the Agentic AI Revolution
                  </h1>
                  <p className="mt-6 max-w-3xl mx-auto text-lg text-muted-foreground">
                    We build autonomous AI agents that go beyond simple automation. They think, learn, and execute complex tasks to solve your biggest business challenges, achieving an <strong className="text-primary font-bold">89% success rate</strong> in process optimization.
                  </p>
                  <div className="mt-10 flex items-center justify-center gap-x-6">
                    <Button asChild size="lg" className="text-lg">
                      <Link to="/start-project">
                        Deploy Your First AI Agent
                        <Bot className="ml-2 h-5 w-5" />
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
                  <motion.h2 variants={itemVariants} className="text-3xl md:text-4xl font-extrabold tracking-tight">Beyond Automation: The Power of Agentic AI</motion.h2>
                  <motion.p variants={itemVariants} className="mt-4 max-w-3xl mx-auto text-lg text-muted-foreground">
                    Traditional automation follows rules. Agentic AI makes the rules. Our autonomous agents can reason, plan, and execute complex workflows to achieve business goals with minimal human intervention.
                  </motion.p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><BrainCircuit className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Autonomous Problem-Solving</h3>
                      <p className="text-muted-foreground mt-2">Give an agent a goal, not a task list. It will analyze the situation, devise a plan, and execute it across multiple systems to achieve the desired outcome.</p>
                    </Card>
                  </motion.div>
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><Zap className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Continuous Learning & Adaptation</h3>
                      <p className="text-muted-foreground mt-2">Our AI agents learn from every interaction and outcome. They continuously refine their strategies, becoming more efficient and effective over time without needing constant reprogramming.</p>
                    </Card>
                  </motion.div>
                  <motion.div variants={itemVariants}>
                    <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6">
                      <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><Users className="h-8 w-8" /></div>
                      <h3 className="text-xl font-bold">Seamless Human Collaboration</h3>
                      <p className="text-muted-foreground mt-2">Agents act as super-powered team members. They can handle the grunt work, provide data-driven insights, and escalate complex decisions to human experts, augmenting your team's capabilities.</p>
                    </Card>
                  </motion.div>
                </div>
              </div>
            </motion.section>
    
            <section className="py-24">
              <div className="container mx-auto px-4">
                <div className="text-center mb-16">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">Industry Transformation in Action</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">
                    See how our custom Agentic AI solutions are delivering unprecedented efficiency and innovation across key sectors.
                  </p>
                </div>
                <Tabs defaultValue={industries[0].id} className="w-full">
                  <TabsList className="flex flex-wrap justify-center h-auto p-2">
                    {industries.map(industry => (
                      <TabsTrigger key={industry.id} value={industry.id} className="flex-col h-auto py-3 px-4 gap-2 flex-grow sm:flex-grow-0">
                        <industry.icon className="h-6 w-6" />
                        <span className="text-center text-xs sm:text-sm whitespace-nowrap">{industry.name}</span>
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
    
            <section className="py-20 md:py-28 bg-secondary/40">
              <div className="container mx-auto px-4 md:px-6">
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.3 }}
                  className="text-center mb-16 max-w-4xl mx-auto"
                >
                  <div className="inline-block bg-primary/10 text-primary p-3 rounded-full mb-4">
                    <HelpCircle className="h-8 w-8" />
                  </div>
                  <h2 className="text-4xl md:text-5xl font-bold text-foreground font-heading">
                    Your Agentic AI Questions, Answered
                  </h2>
                  <p className="max-w-3xl mx-auto mt-4 text-lg text-muted-foreground">
                    Everything you need to know about deploying autonomous AI agents in your business.
                  </p>
                </motion.div>
    
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.1 }}
                  className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-x-12"
                >
                  <div className="space-y-4">
                    <Accordion type="single" collapsible className="w-full">
                      {firstHalf.map((faq, index) => (
                        <AccordionItem value={`item-${index}`} key={index} className="bg-card border rounded-lg mb-4 px-4 shadow-sm hover:border-primary/50 transition-colors">
                          <AccordionTrigger className="text-lg font-semibold text-left hover:text-primary hover:no-underline">
                            {faq.q}
                          </AccordionTrigger>
                          <AccordionContent className="text-base text-muted-foreground leading-relaxed pt-2">
                            {faq.a}
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  </div>
                  <div className="space-y-4 mt-4 lg:mt-0">
                    <Accordion type="single" collapsible className="w-full">
                      {secondHalf.map((faq, index) => (
                         <AccordionItem value={`item-${index + half}`} key={index + half} className="bg-card border rounded-lg mb-4 px-4 shadow-sm hover:border-primary/50 transition-colors">
                          <AccordionTrigger className="text-lg font-semibold text-left hover:text-primary hover:no-underline">
                            {faq.q}
                          </AccordionTrigger>
                          <AccordionContent className="text-base text-muted-foreground leading-relaxed pt-2">
                            {faq.a}
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  </div>
                </motion.div>
              </div>
            </section>
    
            <section className="py-24">
              <div className="container mx-auto px-4">
                <div className="bg-gradient-to-r from-gray-900 to-black rounded-2xl p-8 md:p-16 text-center text-pure-white shadow-2xl relative overflow-hidden">
                    <div className="absolute inset-0 -z-10 opacity-10">
                        <img-replace alt="Abstract AI network visualization" className="w-full h-full object-cover" />
                    </div>
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.7 }}
                  >
                    <Sparkles className="h-16 w-16 mx-auto text-primary mb-6" />
                    <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to Deploy Your Autonomous Workforce?</h2>
                    <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8">
                      Stop managing tasks and start directing outcomes. Let our experts design and deploy the custom AI agents that will drive growth, efficiency, and innovation for your business.
                    </p>
                    <Button asChild size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105">
                      <Link to="/start-project">
                        Book Your AI Strategy Call <ArrowRight className="ml-2 h-5 w-5" />
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
    
    export default AiAutomationsPage;
