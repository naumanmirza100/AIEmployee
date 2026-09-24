import React from 'react';
    import { Helmet } from 'react-helmet';
    import { motion, useMotionValue, useTransform, useSpring } from 'framer-motion';
    import { Link } from 'react-router-dom';
    import { HeartHandshake as Handshake, ArrowRight, TrendingUp, ShieldCheck, Search, Gavel, Rocket, Sparkles, BarChart, Layers, Zap } from 'lucide-react';
    import { Button } from '@/components/ui/button';
    import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
    import { useToast } from "@/components/ui/use-toast";
    import Masonry from 'react-masonry-css';
    
    const containerVariants = {
      hidden: { opacity: 0 },
      visible: {
        opacity: 1,
        transition: { staggerChildren: 0.1, delayChildren: 0.2 },
      },
    };
    
    const itemVariants = {
      hidden: { opacity: 0, y: 30 },
      visible: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 100, damping: 15 } },
    };
    
    const ListingCard = ({ listing, onClick }) => {
      const x = useMotionValue(0);
      const y = useMotionValue(0);
    
      const mouseXSpring = useSpring(x);
      const mouseYSpring = useSpring(y);
    
      const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["12deg", "-12deg"]);
      const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-12deg", "12deg"]);
    
      const handleMouseMove = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
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
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={{
            rotateX,
            rotateY,
            transformStyle: "preserve-3d",
          }}
          variants={itemVariants}
          onClick={onClick}
          className="w-full"
        >
          <div style={{ transform: "translateZ(75px)", transformStyle: "preserve-3d" }} className="w-full">
            <Card className="overflow-hidden card-border-glow group cursor-pointer glassmorphism h-full flex flex-col">
              <div className="overflow-hidden h-48 relative">
                <motion.div
                  className="absolute inset-0"
                  style={{ transformStyle: "preserve-3d" }}
                  whileHover={{ scale: 1.1 }}
                  transition={{ type: 'spring', stiffness: 200, damping: 20 }}
                >
                  <img alt={listing.alt} className="w-full h-full object-cover" style={{ transform: "translateZ(20px) scale(1.1)" }} src="https://images.unsplash.com/photo-1595872018818-97555653a011" />
                </motion.div>
              </div>
              <CardContent className="p-6 flex-grow flex flex-col">
                <p className="text-sm font-semibold text-primary">{listing.category}</p>
                <h3 className="text-xl font-bold mt-1">{listing.name}</h3>
                <p className="text-muted-foreground mt-2 text-sm flex-grow">{listing.description}</p>
                <div className="flex justify-between items-center mt-4 text-muted-foreground border-t border-border/50 pt-4">
                  <div>
                    <p className="text-xs">Revenue</p>
                    <p className="font-semibold text-foreground">{listing.revenue}</p>
                  </div>
                  <div>
                    <p className="text-xs text-right">Asking Price</p>
                    <p className="font-semibold text-foreground">{listing.price}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      );
    };
    
    
    const SellBuyBusinessesPage = () => {
      const { toast } = useToast();
    
      const handleNotImplemented = () => {
        toast({
          title: "🚧 This feature isn't implemented yet—but don't worry! You can request it in your next prompt! 🚀",
        });
      };
    
      const features = [
        {
          icon: ShieldCheck,
          title: "Vetted Businesses",
          description: "Every listing is rigorously verified, ensuring you're browsing high-quality, legitimate businesses with transparent data.",
        },
        {
          icon: BarChart,
          title: "AI-Powered Valuation",
          description: "Get an accurate, data-driven valuation of your business using our proprietary AI models that analyze thousands of data points.",
        },
        {
          icon: Gavel,
          title: "Managed Due Diligence",
          description: "Our experts guide you through the legal and financial due diligence process, providing a clear path to a secure transaction.",
        },
        {
          icon: Rocket,
          title: "Seamless Technical Handover",
          description: "Pay Per Project's technical teams manage the entire migration and handover process for you, ensuring a smooth transition.",
        },
      ];
    
      const processSteps = [
        {
          for: "Sellers",
          icon: TrendingUp,
          steps: [
            { title: "List Your Business", description: "Submit your business details through our secure portal." },
            { title: "Get Valued", description: "Our AI and human experts provide a comprehensive valuation." },
            { title: "Connect with Buyers", description: "Receive offers from our network of vetted, serious buyers." },
            { title: "Close Securely", description: "We manage the escrow, legal paperwork, and final handover." },
          ],
        },
        {
          for: "Buyers",
          icon: Search,
          steps: [
            { title: "Browse Vetted Listings", description: "Explore a curated marketplace of profitable online businesses." },
            { title: "Perform Due Diligence", description: "Access verified data rooms and expert reports." },
            { title: "Make a Confident Offer", description: "Submit offers through our secure, transparent platform." },
            { title: "Acquire & Grow", description: "Benefit from a fully managed handover and post-acquisition support." },
          ],
        },
      ];
    
      const listings = [
        { 
          name: "Agentic AI Workflow Platform", 
          category: "AI / SaaS", 
          revenue: "$450k ARR", 
          price: "$2.5M", 
          alt: "Futuristic interface showing autonomous AI agents collaborating on a complex task",
          image: "Futuristic interface showing autonomous AI agents collaborating on a complex task",
          description: "A B2B SaaS platform where users can build, deploy, and manage teams of autonomous AI agents to automate complex business workflows." 
        },
        { 
          name: "AR Interior Design App", 
          category: "AR / Mobile", 
          revenue: "$300k/year", 
          price: "$1.1M", 
          alt: "Smartphone screen showing a living room being redecorated in real-time with augmented reality furniture",
          image: "Smartphone screen showing a living room being redecorated in real-time with augmented reality furniture",
          description: "A mobile app using ARKit/ARCore to let users visualize furniture and decor in their own homes, with a direct-to-consumer sales model." 
        },
        { 
          name: "Decentralized Creator Platform", 
          category: "Web3 / Social", 
          revenue: "$200k/year (protocol fees)", 
          price: "$950k", 
          alt: "A vibrant digital gallery of NFTs and token-gated content from various artists",
          image: "A vibrant digital gallery of NFTs and token-gated content from various artists",
          description: "A Web3 platform for artists and creators to monetize their work through NFTs, social tokens, and token-gated communities." 
        },
        { 
          name: "Hyper-Personalized Nutrition Service", 
          category: "HealthTech / E-commerce", 
          revenue: "$600k/year", 
          price: "$1.8M", 
          alt: "A sleek box of personalized daily vitamin packs, with a smartphone app showing health data",
          image: "A sleek box of personalized daily vitamin packs, with a smartphone app showing health data",
          description: "An AI-driven subscription service that delivers personalized supplements based on users' health data, lifestyle quizzes, and genetic markers." 
        },
        { 
          name: "AI-Native Code Generation Tool", 
          category: "Developer Tools / SaaS", 
          revenue: "$350k ARR", 
          price: "$2M", 
          alt: "A developer's computer screen with lines of code being written automatically by an AI assistant",
          image: "A developer's computer screen with lines of code being written automatically by an AI assistant",
          description: "A subscription-based tool for developers that uses LLMs to generate, debug, and optimize code, integrating directly into IDEs." 
        },
        { 
          name: "Sustainable Fashion Marketplace", 
          category: "E-commerce / Sustainability", 
          revenue: "$1.2M/year", 
          price: "$3M", 
          alt: "An online marketplace showcasing beautiful, ethically-made clothing from various independent designers",
          image: "An online marketplace showcasing beautiful, ethically-made clothing from various independent designers",
          description: "A curated marketplace for certified sustainable and ethical fashion brands, with a strong community and high customer loyalty." 
        },
        { 
          name: "VR Language Learning Experience", 
          category: "EdTech / VR", 
          revenue: "$180k/year", 
          price: "$700k", 
          alt: "A person wearing a VR headset, immersed in a virtual simulation of a Parisian cafe to learn French",
          image: "A person wearing a VR headset, immersed in a virtual simulation of a Parisian cafe to learn French",
          description: "An immersive VR application that teaches languages through realistic, AI-powered conversational scenarios in virtual environments." 
        },
        { 
          name: "Automated Financial Advisory AI", 
          category: "FinTech / AI", 
          revenue: "$500k ARR", 
          price: "$3.5M", 
          alt: "A clean, modern dashboard displaying personalized investment portfolios and financial forecasts",
          image: "A clean, modern dashboard displaying personalized investment portfolios and financial forecasts",
          description: "A robo-advisor SaaS that provides automated, AI-driven financial planning and investment management for the mass-affluent market." 
        },
      ];
    
      const breakpointColumnsObj = {
        default: 3,
        1100: 2,
        700: 1
      };
    
      return (
        <>
          <Helmet>
            <title>Sell & Buy Businesses | PayPerProject</title>
            <meta name="description" content="A curated marketplace for buying and selling high-quality online businesses, with expert valuation and managed handover." />
          </Helmet>
          <div className="bg-background text-foreground">
            <section className="relative isolate overflow-hidden pt-32 pb-24 md:pt-48 md:pb-32">
              <div className="absolute inset-0 -z-10 h-full w-full bg-background bg-[radial-gradient(#ffffff20_1px,transparent_1px)] [background-size:16px_16px]"></div>
              <div className="absolute inset-x-0 top-1/2 -z-10 -translate-y-1/2 transform-gpu overflow-hidden opacity-20 blur-3xl" aria-hidden="true">
                <div className="mx-auto aspect-[1155/678] w-[72.1875rem] bg-gradient-to-tr from-primary to-green-500" style={{ clipPath: 'polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)' }}></div>
              </div>
              <div className="container mx-auto px-4 text-center">
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.2 }}>
                  <div className="inline-flex items-center justify-center rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary mb-4">
                    <Handshake className="h-5 w-5 mr-2" />
                    The Future of Business Acquisitions
                  </div>
                  <h1 className="fluid-text-h1 font-extrabold tracking-tight text-glow">
                    The Marketplace for Digital Assets
                  </h1>
                  <p className="mt-6 max-w-3xl mx-auto text-lg text-muted-foreground">
                    A fully managed platform for buying and selling profitable online businesses. We handle the valuation, vetting, and technical handover, so you can focus on the deal.
                  </p>
                  <div className="mt-10 flex items-center justify-center gap-x-6">
                    <Button onClick={handleNotImplemented} size="lg" className="text-lg">
                      Sell Your Business
                      <ArrowRight className="ml-2 h-5 w-5" />
                    </Button>
                    <Button onClick={handleNotImplemented} size="lg" variant="outline" className="text-lg">
                      Browse Listings
                      <Search className="ml-2 h-5 w-5" />
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
                  <motion.h2 variants={itemVariants} className="fluid-text-h2 font-extrabold tracking-tight">A Better Way to Buy & Sell</motion.h2>
                  <motion.p variants={itemVariants} className="mt-4 max-w-3xl mx-auto text-lg text-muted-foreground">
                    We've removed the friction and risk from business acquisitions with a suite of powerful, managed services.
                  </motion.p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                  {features.map((feature, index) => (
                    <motion.div variants={itemVariants} key={index}>
                      <Card className="h-full text-center bg-card/50 backdrop-blur-sm border-border/50 p-6 card-border-glow glassmorphism">
                        <div className="mx-auto bg-primary/10 text-primary p-4 rounded-full mb-4 w-fit"><feature.icon className="h-8 w-8" /></div>
                        <h3 className="text-xl font-bold">{feature.title}</h3>
                        <p className="text-muted-foreground mt-2">{feature.description}</p>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.section>
    
            <section className="py-24">
              <div className="container mx-auto px-4">
                <div className="text-center mb-16">
                  <h2 className="fluid-text-h2 font-extrabold tracking-tight">The Acquisition Process, Perfected</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">
                    A clear, step-by-step process for both buyers and sellers, managed by our team of experts.
                  </p>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-stretch">
                  {processSteps.map((process) => (
                    <motion.div variants={itemVariants} key={process.for} className="h-full">
                      <Card className="bg-card/50 backdrop-blur-sm border-border/50 p-8 h-full glassmorphism">
                        <CardHeader className="p-0 mb-6">
                          <CardTitle className="text-2xl font-bold text-primary flex items-center gap-3">
                            <process.icon className="h-8 w-8" />
                            For {process.for}
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                          <ol className="space-y-6">
                            {process.steps.map((step, i) => (
                              <li key={i} className="flex items-start gap-4">
                                <motion.div 
                                  whileHover={{ scale: 1.1, rotate: 10 }}
                                  className="flex-shrink-0 h-10 w-10 bg-primary/10 text-primary rounded-full flex items-center justify-center font-bold text-lg">{i + 1}</motion.div>
                                <div>
                                  <h4 className="font-semibold text-lg text-foreground">{step.title}</h4>
                                  <p className="text-muted-foreground">{step.description}</p>
                                </div>
                              </li>
                            ))}
                          </ol>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              </div>
            </section>
    
            <section className="py-24 bg-secondary/40">
              <div className="container mx-auto px-4">
                <div className="text-center mb-16">
                  <h2 className="fluid-text-h2 font-extrabold tracking-tight">Featured Listings</h2>
                  <p className="mt-4 max-w-2xl mx-auto text-lg text-muted-foreground">
                    A selection of high-growth digital businesses currently available on our marketplace.
                  </p>
                </div>
                <motion.div variants={containerVariants} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.1 }}>
                  <Masonry
                    breakpointCols={breakpointColumnsObj}
                    className="my-masonry-grid"
                    columnClassName="my-masonry-grid_column"
                  >
                    {listings.map((listing, index) => (
                      <ListingCard key={index} listing={listing} onClick={handleNotImplemented} />
                    ))}
                  </Masonry>
                </motion.div>
                <div className="text-center mt-12">
                  <Button onClick={handleNotImplemented} size="lg" variant="outline">
                    View All Listings <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                </div>
              </div>
            </section>
    
            <section className="py-24">
              <div className="container mx-auto px-4">
                <div className="bg-gradient-to-r from-gray-900 to-black rounded-2xl p-8 md:p-16 text-center text-pure-white shadow-2xl relative overflow-hidden">
                  <div className="absolute inset-0 -z-10 opacity-10">
                    <img alt="Abstract network of interconnected nodes" className="w-full h-full object-cover" src="https://images.unsplash.com/photo-1700941019917-731dc64ce685" />
                  </div>
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.7 }}
                  >
                    <Sparkles className="h-16 w-16 mx-auto text-primary mb-6" />
                    <h2 className="fluid-text-h2 font-bold mb-4">Pitch for a Partnership</h2>
                    <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8">
                      Have a promising business but not ready to sell? Pitch your business to us. We invest in high-potential digital assets, offering capital and our managed project teams to fuel your growth in exchange for equity.
                    </p>
                    <Button onClick={handleNotImplemented} size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105">
                      Pitch Your Business <Layers className="ml-2 h-5 w-5" />
                    </Button>
                  </motion.div>
                </div>
              </div>
            </section>
          </div>
        </>
      );
    };
    
    export default SellBuyBusinessesPage;