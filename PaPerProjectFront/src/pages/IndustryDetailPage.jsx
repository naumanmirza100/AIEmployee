
import React, { useState } from 'react';
    import { useParams, Link, Navigate } from 'react-router-dom';
    import { Helmet } from 'react-helmet';
    import { motion } from 'framer-motion';
    import { useTranslation } from 'react-i18next';
    import Masonry from 'react-masonry-css';
    import { 
      Leaf, Car, Plane, Banknote, Construction, Clapperboard, Landmark, HeartPulse, 
      ShieldCheck, BarChart3, Fuel, Home, ShoppingCart, Network, Truck, Ship, 
      FlaskConical, Atom, Zap, School, Landmark as LandmarkIcon, Search, Cpu,
      Lightbulb, ArrowRight, Users, ChevronRight, HelpCircle, TrendingDown, LayoutGrid, List
    } from 'lucide-react';
    import { Button } from '@/components/ui/button';
    import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
    import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
    import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
    import { industryChallenges } from '@/data/industryChallenges';
    
    const allIndustries = [
      { name: 'Agriculture', slug: 'agriculture', icon: Leaf },
      { name: 'Automotive', slug: 'automotive', icon: Car },
      { name: 'Aviation', slug: 'aviation', icon: Plane },
      { name: 'Banking', slug: 'banking', icon: Banknote },
      { name: 'Biotech & Life Sciences', slug: 'biotechnology-life-sciences', icon: FlaskConical },
      { name: 'Construction', slug: 'construction', icon: Construction },
      { name: 'Education & EdTech', slug: 'education-edtech', icon: School },
      { name: 'Entertainment', slug: 'entertainment', icon: Clapperboard },
      { name: 'Finance', slug: 'finance', icon: Landmark },
      { name: 'Fintech', slug: 'fintech', icon: Cpu },
      { name: 'Healthcare', slug: 'healthcare', icon: HeartPulse },
      { name: 'Insurance', slug: 'insurance', icon: ShieldCheck },
      { name: 'Martech', slug: 'martech', icon: BarChart3 },
      { name: 'IT & Consulting Solutions', slug: 'it-consulting-solutions', icon: Users },
      { name: 'Labor Market', slug: 'labor-market', icon: Users },
      { name: 'Oil & Gas', slug: 'oil-and-gas', icon: Fuel },
      { name: 'Pharmaceuticals', slug: 'pharmaceuticals', icon: Atom },
      { name: 'Public Sector & Government', slug: 'public-sector-government', icon: LandmarkIcon },
      { name: 'Real Estate', slug: 'real-estate', icon: Home },
      { name: 'Research & Development (R&D)', slug: 'research-development', icon: Search },
      { name: 'Retail', slug: 'retail', icon: ShoppingCart },
      { name: 'Supply Chain', slug: 'supply-chain', icon: Truck },
      { name: 'Telecommunications', slug: 'telecommunications', icon: Network },
      { name: 'Transportation & Logistics', slug: 'transportation-and-logistics', icon: Truck },
      { name: 'Travel & Hospitality', slug: 'travel-and-hospitality', icon: Ship },
      { name: 'Utilities & Clean Energy', slug: 'utilities-clean-energy', icon: Zap },
    ];
    
    const Section = ({ children, className = '', id = '' }) => (
      <motion.section 
        id={id}
        className={`py-16 md:py-24 ${className}`}
        variants={{
          hidden: { opacity: 0, y: 50 },
          visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: 'easeOut' } }
        }}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
      >
        {children}
      </motion.section>
    );
    
    const IndustryDetailPage = () => {
      const { slug } = useParams();
      const { t } = useTranslation();
      const [expandedChallenge, setExpandedChallenge] = useState(null);
      const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'list'
      
      const industryInfo = allIndustries.find(ind => ind.slug === slug);
      const details = industryChallenges[slug];
    
      if (!industryInfo || !details) {
        return <Navigate to="/industries" replace />;
      }
    
      const { name, icon: Icon } = industryInfo;

      // Helper function to find detailed info for a challenge
      const getChallengeDetails = (challengeName) => {
        return details.challengeDetails?.find(detail => detail.name === challengeName);
      };

      const handleChallengeClick = (challengeName) => {
        setExpandedChallenge(expandedChallenge === challengeName ? null : challengeName);
      };

      // Get the currently expanded challenge details
      const currentChallengeDetail = expandedChallenge && details.challengeDetails 
        ? details.challengeDetails.find(detail => detail.name === expandedChallenge)
        : null;
    
      const insights = [
        ...(details.marketTrends?.map(item => ({ ...item, type: 'Market Trend' })) || []),
        ...(details.techInnovations?.map(item => ({ ...item, type: 'Tech Innovation' })) || []),
        ...(details.regulatoryLandscape?.map(item => ({ ...item, type: 'Regulatory Update' })) || []),
      ];
    
      const breakpointColumnsObj = {
        default: 3,
        1100: 2,
        700: 1
      };
    
      return (
        <div className="bg-background">
          <Helmet>
            <title>{t(`industry_title_${slug}`, `${name} Solutions`)} | Pay Per Project</title>
            <meta name="description" content={t(`industry_meta_${slug}`, `Custom software development and project solutions for the ${name} industry.`)} />
          </Helmet>
    
          <div className="relative isolate overflow-hidden pt-24 pb-16 md:pt-40 md:pb-24">
            <img-replace src={details.image} alt={name} class="absolute inset-0 -z-10 h-full w-full object-cover" />
            <div className="absolute inset-0 -z-10 bg-gradient-to-t from-background via-background/80 to-transparent"></div>
            <div className="absolute inset-0 -z-10 bg-black/30"></div>
    
            <div className="container mx-auto px-4 md:px-6 text-center">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              >
                <div className="flex items-center justify-center gap-2 text-sm mb-4 text-white/80">
                  <Link to="/industries" className="hover:text-primary transition-colors">Industries</Link>
                  <ChevronRight className="h-4 w-4" />
                  <span>{name}</span>
                </div>
                <motion.div 
                  className="inline-block p-4 bg-white/10 rounded-2xl mb-6 border border-white/20 backdrop-blur-sm"
                  animate={{ scale: [1, 1.1, 1], transition: { duration: 2, repeat: Infinity, repeatType: 'mirror' }}}
                >
                  <Icon className="h-12 w-12 text-primary" />
                </motion.div>
                <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight mb-4 font-heading text-white text-glow">
                  {t(`industry_h1_${slug}`, `Navigating the ${name} Landscape`)}
                </h1>
                <p className="max-w-3xl mx-auto text-lg md:text-xl text-white/80">
                  {t(`industry_description_${slug}`, details.description)}
                </p>
              </motion.div>
            </div>
          </div>
          
          {/* Challenges Section with View Toggle */}
          {details.challenges && details.challenges.length > 0 && (
            <Section id="challenges" className="bg-secondary/40">
              <div className="container mx-auto px-4 md:px-6">
                <div className="text-center mb-8">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Key Industry Challenges</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Click on any challenge to explore detailed solutions and insights.</p>
                </div>
                
                {/* View Toggle Buttons */}
                <div className="flex justify-center mb-8">
                  <div className="inline-flex gap-2 p-1 bg-background rounded-lg border border-border shadow-sm">
                    <Button
                      variant={viewMode === 'grid' ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setViewMode('grid')}
                      className="flex items-center gap-2"
                    >
                      <LayoutGrid className="h-4 w-4" />
                      View Grid
                    </Button>
                    <Button
                      variant={viewMode === 'list' ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setViewMode('list')}
                      className="flex items-center gap-2"
                    >
                      <List className="h-4 w-4" />
                      View List
                    </Button>
                  </div>
                </div>

                {/* Grid View */}
                {viewMode === 'grid' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {details.challenges.map((item, index) => {
                      const challengeDetail = getChallengeDetails(item.name);
                      const isExpanded = expandedChallenge === item.name;
                      
                      return (
                        <motion.div
                          key={item.name}
                          initial={{ opacity: 0, y: 30 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: index * 0.1 }}
                          className="h-full"
                        >
                          <Card 
                            className={`p-6 text-center challenge-card h-full card-border-glow flex flex-col cursor-pointer transition-all duration-300 hover:shadow-xl hover:scale-105 ${
                              isExpanded ? 'shadow-2xl border-2 border-primary ring-2 ring-primary/50' : ''
                            }`}
                            onClick={() => handleChallengeClick(item.name)}
                          >
                            <div className={`inline-block p-4 bg-primary/10 text-primary rounded-xl mb-4 mx-auto transition-transform ${isExpanded ? 'scale-110' : ''}`}>
                              <item.icon className="h-10 w-10" />
                            </div>
                            <h3 className="text-xl font-bold mb-2">{item.name}</h3>
                            <p className="text-muted-foreground flex-grow">{item.description}</p>
                          </Card>
                        </motion.div>
                      );
                    })}
                  </div>
                )}

                {/* List View */}
                {viewMode === 'list' && details.challengeDetails && (
                  <div className="space-y-8">
                    {details.challengeDetails.map((challenge, index) => {
                      const isExpanded = expandedChallenge === challenge.name;
                      return (
                        <motion.div
                          key={challenge.name}
                          initial={{ opacity: 0, y: 50 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.5, delay: index * 0.1 }}
                        >
                          <Card className={`overflow-hidden shadow-xl transition-all duration-300 border-2 ${isExpanded ? 'border-primary shadow-2xl' : 'border-primary/20 hover:border-primary/40'}`}>
                            <CardHeader 
                              className="bg-gradient-to-r from-primary/10 via-primary/5 to-transparent pb-4 cursor-pointer"
                              onClick={() => handleChallengeClick(challenge.name)}
                            >
                              <div className="flex items-start gap-6 flex-wrap">
                                <div className="p-4 bg-primary/20 rounded-xl border border-primary/30">
                                  <challenge.icon className="h-10 w-10 text-primary" />
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                  <CardTitle className="text-2xl md:text-3xl mb-2 flex items-center gap-2">
                                    {challenge.name}
                                    <ChevronRight className={`h-5 w-5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                                  </CardTitle>
                                  <CardDescription className="text-base md:text-lg mt-2">{challenge.overview}</CardDescription>
                                </div>
                              </div>
                            </CardHeader>
                            
                            {isExpanded && (
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.3 }}
                                className="overflow-hidden"
                              >
                                <CardContent className="p-6 md:p-8">
                                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                                    {/* Impacts Section */}
                                    <div>
                                      <h4 className="text-xl font-bold mb-4 flex items-center gap-2">
                                        <TrendingDown className="h-5 w-5 text-red-500" />
                                        Key Impacts
                                      </h4>
                                      <ul className="space-y-3">
                                        {challenge.impacts.map((impact, idx) => (
                                          <li key={idx} className="flex items-start gap-3">
                                            <div className="mt-1.5 h-2 w-2 rounded-full bg-red-500 flex-shrink-0" />
                                            <span className="text-muted-foreground">{impact}</span>
                                          </li>
                                        ))}
                                      </ul>
                                    </div>

                                    {/* Technologies Section */}
                                    <div>
                                      <h4 className="text-xl font-bold mb-4 flex items-center gap-2">
                                        <Cpu className="h-5 w-5 text-blue-500" />
                                        Key Technologies
                                      </h4>
                                      <div className="flex flex-wrap gap-2">
                                        {challenge.technologies.map((tech, idx) => (
                                          <span
                                            key={idx}
                                            className="px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-sm font-medium border border-primary/20"
                                          >
                                            {tech}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  </div>

                                  {/* Solutions Section */}
                                  <div className="pt-8 border-t border-border">
                                    <h4 className="text-xl font-bold mb-6 flex items-center gap-2">
                                      <Lightbulb className="h-5 w-5 text-yellow-500" />
                                      Our Technology Solutions
                                    </h4>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                      {challenge.solutions.map((solution, idx) => (
                                        <Card key={idx} className="bg-secondary/30 border-primary/20 hover:border-primary/40 transition-colors">
                                          <CardHeader>
                                            <CardTitle className="text-lg">{solution.title}</CardTitle>
                                          </CardHeader>
                                          <CardContent>
                                            <p className="text-muted-foreground mb-4">{solution.description}</p>
                                            <div className="space-y-2">
                                              <p className="text-sm font-semibold text-primary">Key Benefits:</p>
                                              <ul className="space-y-1.5">
                                                {solution.benefits.map((benefit, benefitIdx) => (
                                                  <li key={benefitIdx} className="flex items-start gap-2 text-sm text-muted-foreground">
                                                    <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                                                    {benefit}
                                                  </li>
                                                ))}
                                              </ul>
                                            </div>
                                          </CardContent>
                                        </Card>
                                      ))}
                                    </div>
                                  </div>
                                </CardContent>
                              </motion.div>
                            )}
                          </Card>
                        </motion.div>
                      );
                    })}
                  </div>
                )}

                {/* Modal Dialog for Grid View Details */}
                {viewMode === 'grid' && (
                  <Dialog open={!!currentChallengeDetail} onOpenChange={(open) => !open && setExpandedChallenge(null)}>
                    <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
                      {currentChallengeDetail && (
                        <>
                          <DialogHeader>
                            <div className="flex items-start gap-4 mb-4">
                              <div className="p-3 bg-primary/20 rounded-xl border border-primary/30">
                                <currentChallengeDetail.icon className="h-8 w-8 text-primary" />
                              </div>
                              <div className="flex-1">
                                <DialogTitle className="text-2xl md:text-3xl mb-2">{currentChallengeDetail.name}</DialogTitle>
                                <DialogDescription className="text-base md:text-lg">{currentChallengeDetail.overview}</DialogDescription>
                              </div>
                            </div>
                          </DialogHeader>
                          
                          <div className="space-y-6">
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                              {/* Impacts Section */}
                              <div>
                                <h4 className="text-xl font-bold mb-4 flex items-center gap-2">
                                  <TrendingDown className="h-5 w-5 text-red-500" />
                                  Key Impacts
                                </h4>
                                <ul className="space-y-3">
                                  {currentChallengeDetail.impacts.map((impact, idx) => (
                                    <li key={idx} className="flex items-start gap-3">
                                      <div className="mt-1.5 h-2 w-2 rounded-full bg-red-500 flex-shrink-0" />
                                      <span className="text-muted-foreground">{impact}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Technologies Section */}
                              <div>
                                <h4 className="text-xl font-bold mb-4 flex items-center gap-2">
                                  <Cpu className="h-5 w-5 text-blue-500" />
                                  Key Technologies
                                </h4>
                                <div className="flex flex-wrap gap-2">
                                  {currentChallengeDetail.technologies.map((tech, idx) => (
                                    <span
                                      key={idx}
                                      className="px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-sm font-medium border border-primary/20"
                                    >
                                      {tech}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>

                            {/* Solutions Section */}
                            <div className="pt-6 border-t border-border">
                              <h4 className="text-xl font-bold mb-6 flex items-center gap-2">
                                <Lightbulb className="h-5 w-5 text-yellow-500" />
                                Our Technology Solutions
                              </h4>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {currentChallengeDetail.solutions.map((solution, idx) => (
                                  <Card key={idx} className="bg-secondary/30 border-primary/20 hover:border-primary/40 transition-colors">
                                    <CardHeader>
                                      <CardTitle className="text-lg">{solution.title}</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                      <p className="text-muted-foreground mb-4">{solution.description}</p>
                                      <div className="space-y-2">
                                        <p className="text-sm font-semibold text-primary">Key Benefits:</p>
                                        <ul className="space-y-1.5">
                                          {solution.benefits.map((benefit, benefitIdx) => (
                                            <li key={benefitIdx} className="flex items-start gap-2 text-sm text-muted-foreground">
                                              <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                                              {benefit}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    </CardContent>
                                  </Card>
                                ))}
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </DialogContent>
                  </Dialog>
                )}
              </div>
            </Section>
          )}
    
          {details.services && details.services.length > 0 && (
            <Section id="services">
              <div className="container mx-auto px-4 md:px-6">
                <div className="text-center mb-16">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Our {name} Solutions</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Full-width strips detailing how we empower leaders to overcome challenges and seize opportunities.</p>
                </div>
                <div className="space-y-8">
                  {details.services.map((service, index) => (
                    <motion.div
                      key={service.name}
                      initial={{ opacity: 0, x: index % 2 === 0 ? -50 : 50 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true, amount: 0.3 }}
                      transition={{ duration: 0.7 }}
                    >
                      <Card className={`overflow-hidden shadow-lg hover:shadow-primary/20 transition-shadow duration-300 flex flex-col ${index % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'}`}>
                        <div className="md:w-1/3 bg-secondary/50 flex items-center justify-center p-8">
                          <service.icon className="h-24 w-24 text-primary" />
                        </div>
                        <div className="md:w-2/3 p-8 flex flex-col">
                          <h3 className="text-2xl font-bold mb-3">{service.name}</h3>
                          <p className="text-muted-foreground mb-6 flex-grow">{service.description}</p>
                          <Button asChild className="self-start mt-auto">
                            <Link to="/start-project">
                              Develop Solution <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                          </Button>
                        </div>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              </div>
            </Section>
          )}
    
          {insights && insights.length > 0 && (
            <Section id="insights" className="bg-secondary/40">
              <div className="container mx-auto px-4 md:px-6">
                <div className="text-center mb-16">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Key Insights & Trends</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">A dynamic view of the market trends, technological innovations, and regulatory shifts shaping the {name} industry.</p>
                </div>
                <Masonry
                  breakpointCols={breakpointColumnsObj}
                  className="my-masonry-grid"
                  columnClassName="my-masonry-grid_column"
                >
                  {insights.map((item, index) => (
                    <motion.div key={index} variants={{ hidden: { opacity: 0, y: 50 }, visible: { opacity: 1, y: 0 } }} transition={{ delay: index * 0.05 }}>
                      <Card className="card-border-glow mb-8">
                        <CardHeader>
                          <div className="flex items-center gap-4">
                            <div className="p-3 bg-primary/10 rounded-lg">
                              <item.icon className="h-6 w-6 text-primary" />
                            </div>
                            <div>
                              <CardTitle>{item.name}</CardTitle>
                              <CardDescription>{item.type}</CardDescription>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <p className="text-muted-foreground">{item.description}</p>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </Masonry>
              </div>
            </Section>
          )}
    
          {details.faqs && details.faqs.length > 0 && (
            <Section id="faq">
              <div className="container mx-auto px-4 md:px-6">
                <div className="text-center mb-16">
                  <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight font-heading">Frequently Asked Questions</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">Answers to common questions about our work in the {name} industry.</p>
                </div>
                <div className="max-w-4xl mx-auto">
                  <Accordion type="single" collapsible className="w-full">
                    {details.faqs.map((faq, index) => (
                      <AccordionItem value={`item-${index}`} key={index} className="bg-secondary/30 rounded-lg mb-4 px-4">
                        <AccordionTrigger className="text-lg font-semibold text-left hover:no-underline">
                          <div className="flex items-start gap-4">
                            <HelpCircle className="h-6 w-6 text-primary mt-1 flex-shrink-0" />
                            {faq.q}
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="text-base text-muted-foreground pl-10">
                          {faq.a}
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </div>
              </div>
            </Section>
          )}
    
          <Section className="bg-background">
            <div className="container mx-auto px-4 md:px-6">
              <div className="bg-gradient-to-r from-gray-900 to-black rounded-2xl p-8 md:p-12 text-center text-pure-white shadow-2xl relative overflow-hidden">
                <div className="absolute -right-1/4 -bottom-1/2 opacity-10">
                    <Icon className="w-[500px] h-[500px] text-primary/50" />
                </div>
                <h2 className="text-3xl font-bold mb-4 relative z-10">{t('industry_cta_title', `Have a Project in the ${name} Industry?`)}</h2>
                <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8 relative z-10">{t('industry_cta_subtitle', 'Let our experts bring your vision to life. Get a fixed-price quote and a dedicated team that understands your needs.')}</p>
                <Button asChild size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105 relative z-10">
                  <Link to="/start-project">{t('industry_cta_button', 'Start Your Project Now')} <ArrowRight className="ml-2 h-5 w-5" /></Link>
                </Button>
              </div>
            </div>
          </Section>
        </div>
      );
    };
    
    export default IndustryDetailPage;
