
import React, { useState, useMemo, useRef } from 'react';
import { Helmet } from 'react-helmet';
import { motion, AnimatePresence, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { 
  Leaf, Car, Plane, Banknote, Construction, Clapperboard, Landmark, HeartPulse, 
  ShieldCheck, BarChart3, Fuel, Home, ShoppingCart, Network, Truck, Ship, 
  FlaskConical, Atom, Zap, School, Landmark as LandmarkIcon, Search, Cpu,
  Lightbulb, CheckCircle, Target, ArrowRight, Users, Briefcase
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';

const industryData = [
  { name: 'Agriculture', slug: 'agriculture', icon: Leaf, category: 'Primary Sectors', description: 'Innovative tech solutions for modern farming and sustainable agriculture.', image: 'A drone flying over a lush green field of crops' },
  { name: 'Automotive', slug: 'automotive', icon: Car, category: 'Manufacturing & Engineering', description: 'Driving the future with connected car technologies and manufacturing process optimization.', image: 'A futuristic electric car charging in a modern city' },
  { name: 'Aviation', slug: 'aviation', icon: Plane, category: 'Transportation & Logistics', description: 'Soaring to new heights with software for logistics, booking, and aircraft management.', image: 'A modern passenger airplane flying above the clouds at sunset' },
  { name: 'Banking', slug: 'banking', icon: Banknote, category: 'Finance & Legal', description: 'Secure and compliant digital solutions for the modern banking landscape.', image: 'A person using a mobile banking app on their smartphone with charts in the background' },
  { name: 'Biotechnology & Life Sciences', slug: 'biotechnology-life-sciences', icon: FlaskConical, category: 'Health & Science', description: 'Accelerating research and development with lab informatics and data analysis tools.', image: 'A scientist in a modern laboratory looking at a DNA helix on a screen' },
  { name: 'Construction', slug: 'construction', icon: Construction, category: 'Manufacturing & Engineering', description: 'Building the future with project management software and IoT for construction sites.', image: 'A construction site with a crane against a skyscraper background' },
  { name: 'Education & EdTech', slug: 'education-edtech', icon: School, category: 'Consumer & Services', description: 'Revolutionizing learning with online course platforms and virtual classrooms.', image: 'A student using a tablet for an interactive online lesson at home' },
  { name: 'Entertainment', slug: 'entertainment', icon: Clapperboard, category: 'Media & Communications', description: 'Engaging audiences with streaming platforms, content management, and interactive media.', image: 'A family watching a movie on a large screen in a cozy living room' },
  { name: 'Finance', slug: 'finance', icon: Landmark, category: 'Finance & Legal', description: 'High-performance systems for trading, asset management, and financial analytics.', image: 'A digital stock market graph on a computer screen in a dark room' },
  { name: 'Fintech', slug: 'fintech', icon: Cpu, category: 'Technology & Digital', description: 'Disrupting finance with blockchain, payment gateways, and peer-to-peer lending platforms.', image: 'Abstract visualization of blockchain technology with glowing nodes' },
  { name: 'Healthcare', slug: 'healthcare', icon: HeartPulse, category: 'Health & Science', description: 'Improving patient outcomes with telemedicine, EMR systems, and medical device software.', image: 'A doctor conducting a telemedicine call with a patient on a tablet' },
  { name: 'Insurance', slug: 'insurance', icon: ShieldCheck, category: 'Finance & Legal', description: 'Transforming the insurance industry with AI-powered claims processing and policy management.', image: 'A protective digital shield icon hovering over a family home' },
  { name: 'Martech', slug: 'martech', icon: BarChart3, category: 'Technology & Digital', description: 'Powering marketing success with automation platforms, analytics, and personalization engines.', image: 'A marketing dashboard showing analytics and customer engagement metrics' },
  { name: 'IT & Consulting Solutions', slug: 'it-consulting-solutions', icon: Users, category: 'Technology & Digital', description: 'Strategic IT consulting and bespoke software solutions to drive business transformation and efficiency.', image: 'A team of IT consultants collaborating in a modern office with whiteboards' },
  { name: 'Labor Market', slug: 'labor-market', icon: Briefcase, category: 'Consumer & Services', description: 'Data-driven insights and technology solutions to navigate the complexities of the modern labor market.', image: 'A diverse group of professionals collaborating in a modern, hybrid office environment' },
  { name: 'Oil and Gas', slug: 'oil-and-gas', icon: Fuel, category: 'Primary Sectors', description: 'Optimizing operations with data analytics, remote monitoring, and logistics solutions.', image: 'An offshore oil rig at sunset with calm seas' },
  { name: 'Pharmaceuticals', slug: 'pharmaceuticals', icon: Atom, category: 'Health & Science', description: 'Supporting drug discovery and clinical trials with compliant software solutions.', image: 'Automated robotic arms working in a pharmaceutical manufacturing facility' },
  { name: 'Public Sector & Government', slug: 'public-sector-government', icon: LandmarkIcon, category: 'Finance & Legal', description: 'Improving citizen services with digital transformation and data-driven policy making.', image: 'A modern government building with a large digital screen showing public data' },
  { name: 'Real Estate', slug: 'real-estate', icon: Home, category: 'Consumer & Services', description: 'Modernizing property management, sales, and rentals with digital platforms.', image: 'A modern house with a "For Sale" sign and a happy family' },
  { name: 'Research & Development (R&D)', slug: 'research-development', icon: Search, category: 'Technology & Digital', description: 'Fueling innovation with collaborative research platforms and knowledge management systems.', image: 'A team of researchers collaborating around a futuristic holographic holographic display' },
  { name: 'Retail', slug: 'retail', icon: ShoppingCart, category: 'Consumer & Services', description: 'Enhancing the shopping experience with e-commerce platforms, POS systems, and supply chain tech.', image: 'A person paying for a coffee using a contactless smartphone payment' },
  { name: 'Supply Chain', slug: 'supply-chain', icon: Truck, category: 'Transportation & Logistics', description: 'Creating transparent and efficient supply chains with blockchain and real-time tracking.', image: 'A fleet of autonomous delivery trucks on a highway' },
  { name: 'Telecommunications', slug: 'telecommunications', icon: Network, category: 'Media & Communications', description: 'Connecting the world with robust infrastructure management and customer service software.', image: 'A glowing 5G cell tower transmitting data signals over a city at night' },
  { name: 'Travel and Hospitality', slug: 'travel-and-hospitality', icon: Ship, category: 'Consumer & Services', description: 'Creating seamless travel experiences with booking engines and guest management systems.', image: 'A luxury hotel lobby with a view of a tropical beach' },
  { name: 'Utilities & Clean Energy', slug: 'utilities-clean-energy', icon: Zap, category: 'Primary Sectors', description: 'Powering a sustainable future with smart grid management and renewable energy platforms.', image: 'A field of solar panels under a bright blue sky' },
];

const categories = [
  'Technology & Digital',
  'Finance & Legal',
  'Health & Science',
  'Manufacturing & Engineering',
  'Transportation & Logistics',
  'Consumer & Services',
  'Media & Communications',
  'Primary Sectors'
];

const IndustryCard = ({ industry, t }) => {
  const ref = useRef(null);

  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const mouseXSpring = useSpring(x);
  const mouseYSpring = useSpring(y);

  const top = useTransform(mouseYSpring, [0.5, -0.5], ["40%", "60%"]);
  const left = useTransform(mouseXSpring, [0.5, -0.5], ["40%", "60%"]);

  const handleMouseMove = (e) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const xPct = mouseX / width - 0.5;
    const yPct = mouseY / height - 0.5;

    x.set(xPct);
    y.set(yPct);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      variants={{
        hidden: { y: 30, opacity: 0, scale: 0.9 },
        visible: { y: 0, opacity: 1, scale: 1, transition: { type: 'spring', stiffness: 100, damping: 15 } },
      }}
      style={{ transformStyle: "preserve-3d" }}
      className="h-full"
    >
      <Link to={`/industries/${industry.slug}`} className="block h-full">
        <Card 
          style={{ transform: "translateZ(75px)" }}
          className="h-full overflow-hidden group transition-all duration-300 flex flex-col bg-card/50 backdrop-blur-sm border-border/50 hover:border-primary/50 shadow-lg hover:shadow-primary/20"
        >
          <div className="relative overflow-hidden h-48">
            <motion.div
              style={{
                transform: "translateZ(50px)",
                transformStyle: "preserve-3d",
              }}
              className="absolute inset-0"
            >
              <img-replace alt={industry.image} class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 ease-in-out"/>
            </motion.div>
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent opacity-100 transition-opacity duration-300"></div>
            <motion.div
              style={{
                top,
                left,
                transform: "translateZ(25px) translateX(-50%) translateY(-50%)",
              }}
              className="absolute h-full w-full bg-gradient-to-r from-primary/20 via-primary/0 to-primary/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
            />
          </div>
          <CardContent className="p-6 flex flex-col flex-grow bg-card">
            <div className="flex items-start gap-4 mb-4">
              <div className="p-3 bg-primary/10 rounded-lg flex-shrink-0 border border-primary/20">
                <industry.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground leading-tight mt-1">{t(`industry_${industry.slug}`, industry.name)}</h3>
            </div>
            <p className="text-muted-foreground text-sm flex-grow">{t(`industry_desc_${industry.slug}`, industry.description)}</p>
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  );
};

const IndustriesPage = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');

  const sortedIndustryData = useMemo(() => [...industryData].sort((a, b) => a.name.localeCompare(b.name)), []);

  const filteredIndustries = useMemo(() => {
    if (!searchTerm) return sortedIndustryData;
    return sortedIndustryData.filter(industry =>
      industry.name.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [searchTerm, sortedIndustryData]);

  const groupedIndustries = useMemo(() => {
    return categories.map(category => ({
      name: category,
      items: filteredIndustries.filter(ind => ind.category === category)
    })).filter(group => group.items.length > 0);
  }, [filteredIndustries]);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
  };

  return (
    <>
      <Helmet>
        <title>{t('title_industries', 'Industries We Serve')} | Pay Per Project</title>
        <meta name="description" content={t('meta_desc_industries', 'Explore the wide range of industries we provide expert project-based solutions for, from technology and finance to healthcare and retail.')} />
      </Helmet>
      
      <div className="relative pt-24 pb-16 md:pt-32 md:pb-24 overflow-hidden bg-gradient-to-b from-secondary/50 to-background">
        <div className={`absolute inset-0 -z-10 h-full w-full bg-background bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#ffffff20_1px,transparent_1px)] [background-size:16px_16px]`}></div>
        <div className="container mx-auto px-4 md:px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          >
            <Badge variant="outline" className="text-primary border-primary mb-4">{t('industries_page_badge', 'Our Expertise')}</Badge>
            <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-foreground mb-4 font-heading text-gradient text-glow">
              {t('industries_title', 'Industries We Serve')}
            </h1>
            <p className="max-w-3xl mx-auto text-lg md:text-xl text-muted-foreground mb-8">
              {t('industries_subtitle', 'We provide bespoke digital solutions across a vast spectrum of industries, empowering businesses to innovate and excel.')}
            </p>
            <div className="max-w-xl mx-auto relative mb-12">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                type="text"
                placeholder={t('industries_search_placeholder', 'Search for your industry...')}
                className="w-full pl-12 pr-4 py-3 text-base rounded-full shadow-lg"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap justify-center gap-x-4 gap-y-2">
              {sortedIndustryData.map(industry => (
                <Button key={industry.slug} variant="link" asChild className="text-muted-foreground hover:text-primary">
                  <Link to={`/industries/${industry.slug}`}>{t(`industry_${industry.slug}`, industry.name)}</Link>
                </Button>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      <section className="py-16 md:py-24 bg-background">
        <div className="container mx-auto px-4 md:px-6">
          <AnimatePresence>
            {groupedIndustries.length > 0 ? (
              groupedIndustries.map(group => (
                <motion.div key={group.name} className="mb-16" initial="hidden" animate="visible" variants={containerVariants}>
                  <h2 className="text-3xl font-bold tracking-tight text-foreground mb-8 font-heading">{t(`industry_category_${group.name.toLowerCase().replace(/ & /g, '_')}`, group.name)}</h2>
                  <motion.div 
                    variants={containerVariants}
                    initial="hidden"
                    animate="visible"
                    className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8"
                    style={{ perspective: "1000px" }}
                  >
                    {group.items.map((industry) => (
                      <IndustryCard key={industry.name} industry={industry} t={t} />
                    ))}
                  </motion.div>
                </motion.div>
              ))
            ) : (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-16">
                <p className="text-xl text-muted-foreground">{t('industries_no_results', 'No industries found matching your search.')}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-secondary/40">
        <div className="container mx-auto px-4 md:px-6">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <motion.div initial={{ opacity: 0, x: -50 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.5 }} transition={{ duration: 0.7 }}>
              <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight text-foreground mb-4 font-heading">{t('industries_why_us_title', 'Your Industry, Our Expertise')}</h2>
              <p className="text-lg text-muted-foreground mb-6">{t('industries_why_us_subtitle', 'We don\'t just build software; we architect solutions that understand the nuances of your industry. Our pay-per-project model ensures you get specialized expertise focused on delivering results.')}</p>
              <div className="space-y-4">
                <div className="flex items-start gap-3"><CheckCircle className="h-6 w-6 text-primary mt-1 flex-shrink-0" /> <p><strong className="text-foreground">{t('industries_why_us_point1_title', 'Domain Knowledge:')}</strong> {t('industries_why_us_point1_desc', 'Access to professionals who speak your industry\'s language.')}</p></div>
                <div className="flex items-start gap-3"><Target className="h-6 w-6 text-primary mt-1 flex-shrink-0" /> <p><strong className="text-foreground">{t('industries_why_us_point2_title', 'Goal-Oriented Delivery:')}</strong> {t('industries_why_us_point2_desc', 'Projects are scoped and delivered to meet specific industry challenges and goals.')}</p></div>
                <div className="flex items-start gap-3"><Lightbulb className="h-6 w-6 text-primary mt-1 flex-shrink-0" /> <p><strong className="text-foreground">{t('industries_why_us_point3_title', 'Innovative Solutions:')}</strong> {t('industries_why_us_point3_desc', 'Leverage the latest technology to gain a competitive edge in your market.')}</p></div>
              </div>
            </motion.div>
            <motion.div initial={{ opacity: 0, scale: 0.8 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true, amount: 0.5 }} transition={{ duration: 0.7 }} className="relative h-96 rounded-2xl overflow-hidden shadow-2xl">
               <img-replace
                  alt="Team of experts collaborating"
                  class="w-full h-full object-cover"/>
                <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent"></div>
                <div className="absolute bottom-0 left-0 p-8 text-white">
                    <p className="text-5xl font-bold">10,000+</p>
                    <p className="text-xl font-medium">{t('industries_why_us_stat', 'Vetted Industry Experts')}</p>
                </div>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="container mx-auto px-4 md:px-6">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.5 }} transition={{ duration: 0.7 }} className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 md:p-12 text-center text-pure-white shadow-2xl">
            <h2 className="text-3xl font-bold mb-4">{t('industries_cta_title', 'Ready to Start Your Industry-Specific Project?')}</h2>
            <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8">{t('industries_cta_subtitle', 'Bring your vision to life with a team that understands your world. Get a fixed-price quote today.')}</p>
            <Button asChild size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105">
              <Link to="/start-project">{t('industries_cta_button', 'Post a Project for Free')} <ArrowRight className="ml-2 h-5 w-5" /></Link>
            </Button>
          </motion.div>
        </div>
      </section>
    </>
  );
};

export default IndustriesPage;
