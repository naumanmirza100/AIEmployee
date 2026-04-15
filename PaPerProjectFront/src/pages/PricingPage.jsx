
import React from 'react';
import { Helmet } from 'react-helmet';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { CheckCircle2, XCircle, ArrowDown, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils.js';

const pricingData = {
  plans: [
    {
      name: 'Basic',
      price: '£0',
      frequency: '/ mo',
      description: 'New teams preparing',
      cta: 'Sign Up for Free',
      isFree: true,
      isFeatured: false,
    },
    {
      name: 'Standard',
      price: '£199',
      frequency: '/ mo',
      description: 'Teams OK with “still-open” work',
      cta: 'Choose Standard',
      isFree: false,
      isFeatured: false,
    },
    {
      name: 'Pro',
      price: '£699',
      frequency: '/ mo',
      description: 'Proven teams wanting newly posted pipeline',
      cta: 'Choose Pro',
      isFree: false,
      isFeatured: true,
    },
  ],
  features: [
    {
      category: 'Project Opportunities',
      items: [
        { name: 'Project access', values: ['Leftovers only (after Pro → Standard)', 'Still-open projects (after Pro’s first 12h)', 'Newly posted projects (first 12h)'] },
        { name: 'Apply / submit', values: ['Only when invited on leftovers', 'Sealed application allowed', 'Priority sealed application'] },
      ],
    },
    {
      category: 'Merit & Checks (all tiers)',
      items: [
        { name: 'Merit & checks', values: ['Must pass Quality, Experience, QA, Proposal hygiene', '+ stronger portfolio & QA certification', '+ higher on-time %, QA pass rate (dip → pause)'] },
      ],
    },
    {
      category: 'Platform Usage',
      items: [
        { name: 'Open projects / mo', values: ['0', '30', 'Unlimited*'] },
        { name: 'Apply / mo', values: ['0', '20', '50'] },
        { name: 'Ask pre-apply Qs / mo', values: ['0', '5', '15'] },
        { name: 'Boosts / mo', values: ['—', '2', '10'] },
      ],
    },
    {
      category: 'White-Label Product Listings (Partner Catalog)',
      items: [
        { name: 'White-Label product listings', values: ['Up to 2 SKUs live', 'Up to 10 SKUs live + category tag', 'Unlimited* SKUs + Featured placement'] },
        { name: 'White-Label badge on profile', values: ['—', 'Included', 'Enhanced (with delivery scorecard)'] },
        { name: 'Listing moderation SLA', values: ['Standard review', 'Priority review', 'Fast-track review'] },
      ],
    },
    {
      category: 'Extras',
      items: [
        { name: 'Extras', values: ['Portfolio + QA playbook', 'Shortlist Shield (Apply credit auto-return if project withdrawn)', 'Bid Coach + Analytics • Enterprise Spotlight'] },
        { name: 'Monthly credit-back', values: ['—', '15% of plan fee → platform Credits', '15% of plan fee → platform Credits'] },
      ],
    },
  ],
  featureExplanations: [
    {
      feature: 'Project access',
      description: 'Determines when you can see and bid on new projects. Pro members get exclusive first access for 12 hours before Standard members see them. Basic members can only access leftover projects they are specifically invited to.'
    },
    {
      feature: 'Apply / submit',
      description: 'Your ability to apply for projects. Pro members get priority consideration. Standard members can submit sealed applications (client can\'t see other bids). Basic members can only apply when invited.'
    },
    {
      feature: 'Merit & checks',
      description: 'All members must pass our baseline quality checks. Higher tiers require stronger portfolios, certifications, and a proven track record of on-time delivery and quality assurance.'
    },
    {
      feature: 'Open projects / mo',
      description: 'The number of projects you can have active at any given time. "Unlimited" is subject to our fair use policy to ensure quality.'
    },
    {
      feature: 'Boosts / mo',
      description: 'Use boosts to give your project applications higher visibility with clients, increasing your chances of getting noticed and hired.'
    },
    {
      feature: 'White-Label product listings',
      description: 'List your own pre-packaged services in our Partner Catalog. Higher tiers allow for more listings and better visibility, including "Featured" placements.'
    },
    {
      feature: 'Shortlist Shield',
      description: 'If you apply for a project and the client withdraws it before hiring anyone, we automatically refund your application credit. Exclusive to Standard and Pro tiers.'
    },
    {
      feature: 'Bid Coach + Analytics',
      description: 'Get AI-powered advice on how to improve your bids and access detailed analytics on your proposal performance. Exclusive to the Pro tier.'
    },
    {
      feature: 'Monthly credit-back',
      description: 'Receive 15% of your monthly plan fee back as platform credits, which you can use for boosts or other platform services. Available for Standard and Pro members.'
    }
  ]
};

const Check = () => <CheckCircle2 className="h-5 w-5 text-green-500" />;
const Cross = () => <XCircle className="h-5 w-5 text-muted-foreground/60" />;

const PricingPage = () => {
  const { t } = useTranslation();

  const scrollToFeatures = () => {
    document.getElementById('feature-details').scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      <Helmet>
        <title>{t('title_pricing', 'Membership Plans & Pricing')} | Pay Per Project</title>
        <meta name="description" content={t('meta_desc_pricing', 'Explore our membership plans. Choose the best plan for your team to access projects and grow your business.')} />
      </Helmet>
      
      <div className="bg-background">
        <div className="relative overflow-hidden">
          <div className="absolute inset-0 bg-grid-pattern opacity-50"></div>
          <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative py-16 md:py-20 text-center">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7 }}
            >
              <Badge variant="secondary" className="mb-4 text-sm bg-primary/10 text-primary border-primary/20">{t('pricing_badge', 'For Our Partners')}</Badge>
              <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight font-heading text-foreground">
                {t('pricing_title', 'Find the Perfect Plan')}
              </h1>
              <p className="mt-5 max-w-3xl mx-auto text-lg md:text-xl text-muted-foreground">
                {t('pricing_subtitle', 'Unlock your full potential with a plan that matches your team’s ambition and expertise. Get access to exclusive projects and powerful tools.')}
              </p>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 0.3 }}
                className="mt-8"
              >
                <Button onClick={scrollToFeatures} variant="outline" size="lg" className="group text-lg">
                  {t('pricing_cta_features', 'See feature details below')} <ArrowDown className="ml-2 h-5 w-5 transition-transform group-hover:translate-y-1" />
                </Button>
              </motion.div>
            </motion.div>
          </div>
        </div>

        <div id="feature-details" className="container mx-auto px-4 sm:px-6 lg:px-8 -mt-8 md:-mt-10 pb-20">
            <div className="hidden lg:block">
                <Table className="bg-card border rounded-2xl shadow-xl shadow-black/5 dark:shadow-black/10">
                    <TableHeader>
                        <TableRow className="border-b-0 hover:bg-transparent">
                            <TableHead className="w-1/4 p-6 text-xl font-bold rounded-tl-2xl align-bottom">{t('pricing_feature_header', 'Features')}</TableHead>
                            {pricingData.plans.map((plan, index) => (
                                <TableHead key={index} className={cn('w-1/4 p-6 text-center', plan.isFeatured ? 'bg-primary/5 rounded-t-2xl' : '')}>
                                    <h3 className="text-xl font-bold text-foreground">{t(plan.name)}</h3>
                                    <p className="text-sm text-muted-foreground h-10 flex items-center justify-center">{t(plan.description)}</p>
                                    <p className="text-3xl font-extrabold text-foreground mt-2">{t(plan.price)}<span className="text-base font-medium text-muted-foreground">{t(plan.frequency)}</span></p>
                                    <Button asChild className={cn('mt-4 w-full', plan.isFeatured ? '' : 'bg-primary/80 hover:bg-primary/90')}>
                                        <Link to="/contact">{t(plan.cta)}</Link>
                                    </Button>
                                </TableHead>
                            ))}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {pricingData.features.map((category, catIndex) => (
                            <React.Fragment key={catIndex}>
                                <TableRow className="hover:bg-transparent">
                                    <TableCell colSpan={4} className="p-3 bg-secondary/40">
                                        <h4 className="font-bold text-base text-foreground pl-3">{t(category.category)}</h4>
                                    </TableCell>
                                </TableRow>
                                {category.items.map((item, itemIndex) => (
                                    <TableRow key={itemIndex} className="border-t even:bg-secondary/20 hover:bg-secondary/40">
                                        <TableCell className="p-6 font-semibold text-muted-foreground">{t(item.name)}</TableCell>
                                        {item.values.map((value, valueIndex) => (
                                            <TableCell key={valueIndex} className={cn('p-6 text-center text-foreground', pricingData.plans[valueIndex].isFeatured ? 'bg-primary/5' : '')}>
                                                <div className="flex justify-center items-center h-full">
                                                    {value === '—' ? <Cross /> : value === 'Included' ? <Check/> : <span className="text-sm">{t(value)}</span>}
                                                </div>
                                            </TableCell>
                                        ))}
                                    </TableRow>
                                ))}
                            </React.Fragment>
                        ))}
                    </TableBody>
                </Table>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:hidden gap-8">
              {pricingData.plans.map((plan, index) => (
                <Card key={index} className={cn('flex flex-col rounded-2xl border shadow-lg transition-all duration-300', plan.isFeatured ? 'border-primary ring-2 ring-primary card-glow' : 'hover:shadow-2xl hover:-translate-y-1')}>
                    <CardHeader className="p-6 text-center relative">
                        {plan.isFeatured && <Badge className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2">Most Popular</Badge>}
                        <h3 className="text-2xl font-bold">{t(plan.name)}</h3>
                        <p className="text-muted-foreground text-sm mt-1">{t(plan.description)}</p>
                        <p className="text-4xl font-extrabold mt-4">{t(plan.price)}<span className="text-base font-normal text-muted-foreground">{t(plan.frequency)}</span></p>
                    </CardHeader>
                    <CardContent className="flex-grow p-6 pt-0">
                        <div className="space-y-6">
                            {pricingData.features.map((category, catIndex) => (
                                <div key={catIndex}>
                                    <h4 className="font-bold text-base text-foreground mb-3 border-b pb-2">{t(category.category)}</h4>
                                    <ul className="space-y-4">
                                        {category.items.map((feature, featureIndex) => (
                                            <li key={featureIndex} className="flex items-start gap-3">
                                                {feature.values[index] === '—' ? 
                                                    <Cross className="h-5 w-5 mt-0.5 flex-shrink-0" /> : 
                                                    <CheckCircle2 className="h-5 w-5 mt-0.5 text-primary flex-shrink-0" />
                                                }
                                                <span className="text-sm">
                                                    <span className="font-semibold text-foreground">{t(feature.name)}:</span>{' '}
                                                    <span className="text-muted-foreground">{feature.values[index] === 'Included' ? t('Included') : t(feature.values[index])}</span>
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                    <CardFooter className="p-6 mt-auto">
                        <Button asChild size="lg" className={cn('w-full', !plan.isFeatured && 'bg-primary/80 hover:bg-primary/90')}>
                            <Link to="/contact">{t(plan.cta)}</Link>
                        </Button>
                    </CardFooter>
                </Card>
              ))}
            </div>
        </div>

        <div className="container mx-auto px-4 sm:px-6 lg:px-8 pb-20">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl md:text-4xl font-extrabold font-heading text-foreground">
                {t('feature_explanations_title', 'Feature Explanations')}
              </h2>
              <p className="mt-4 text-lg text-muted-foreground">
                {t('feature_explanations_subtitle', 'Understand the details of what each feature offers.')}
              </p>
            </div>
            <Accordion type="single" collapsible className="w-full bg-card p-4 sm:p-6 rounded-2xl border">
              {pricingData.featureExplanations.map((feature, index) => (
                <AccordionItem key={index} value={`item-${index}`}>
                  <AccordionTrigger className="text-lg font-semibold hover:no-underline">
                    <div className="flex items-center gap-3">
                      <HelpCircle className="h-5 w-5 text-primary" />
                      {t(feature.feature)}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="text-base text-muted-foreground pt-2 pl-8">
                    {t(feature.description)}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </div>
        
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 pb-16 text-center text-sm text-muted-foreground">
            <p>* {t('pricing_unlimited_note', 'Unlimited is subject to fair use policy.')}</p>
            <p className="mt-4">{t('pricing_questions_prompt', 'Have questions?')} <Link to="/contact" className="text-primary font-semibold hover:underline">{t('pricing_contact_us', 'Contact us')}</Link></p>
        </div>
      </div>
    </>
  );
};

export default PricingPage;
