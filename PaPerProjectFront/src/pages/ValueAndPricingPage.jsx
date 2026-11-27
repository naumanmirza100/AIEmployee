import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { BadgePoundSterling, ArrowRight, Users, ShieldCheck, Clock, CheckCircle, Zap, TrendingUp, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Link } from 'react-router-dom';
import BenchmarkSlider from '@/components/home/BenchmarkSlider';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const ValueAndPricingPage = () => {

  const valueStack = [
    {
      icon: Users,
      title: "Elite Managed Teams",
      description: "You get a cohesive, managed team of vetted global talent. No hiring, no HR, no management overhead."
    },
    {
      icon: ShieldCheck,
      title: "Project Success Guarantee",
      description: "We are financially invested in your success. If deliverables aren't met, we fix it on our dime. This is accountability you can't buy."
    },
    {
      icon: Clock,
      title: "24/7 Productivity",
      description: "Our global, managed teams work around the clock, accelerating your timeline significantly compared to a local team."
    },
    {
        icon: Zap,
        title: "AI-Powered Efficiency",
        description: "Our agentic AI models assist in scoping, coding, and QA, reducing manual errors and delivering results faster."
    }
  ];

  const comparisonData = [
      { feature: 'Talent Quality', us: 'Vetted', agency: 'Variable', hiring: 'High Effort & Risk' },
      { feature: 'Management', us: 'Fully Included', agency: 'Extra Cost', hiring: 'Your Full-Time Job' },
      { feature: 'Speed', us: '24/7 Workflow', agency: 'Standard Hours', hiring: 'Standard Hours' },
      { feature: 'Accountability', us: 'Success Guarantee', agency: 'Best Effort', hiring: 'On You' },
      { feature: 'Cost Model', us: 'Fixed, Transparent', agency: 'Billable Hours', hiring: 'Salaries + Overheads' },
      { feature: 'AI Integration', us: 'Core to Process', agency: 'Add-on Service', hiring: 'DIY / Specialist' },
  ];


  const valueProps = [
    'Dedicated Project Manager', 'Vetted Global Talent', 'Full QA & Testing Team',
    '24/7 Operations & Support', 'IP & NDA Protection', 'Project Success Guarantee',
    'Scalable On-Demand Teams', 'Transparent Reporting'
  ];

  return (
    <>
      <Helmet>
        <title>Value & Pricing | Unbeatable ROI</title>
        <meta name="description" content="Discover how our managed model provides elite talent and guaranteed outcomes at a fraction of the cost of traditional agencies or hiring. Average cost: £9.50/hr." />
      </Helmet>
      <div className="bg-background text-foreground">
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
            >
              <BadgePoundSterling className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-6xl font-heading">
                More Value, Not Just a Lower Price
              </h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                Our average rate of £9.50/hr isn't just about being affordable. It's about delivering an unparalleled return on investment by combining elite talent, guaranteed outcomes, and radical efficiency.
              </p>
            </motion.div>
          </div>
        </div>

        <section className="py-16 sm:py-20">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="text-center mb-12">
                    <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">The Value Stack</h2>
                    <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                        Here’s what you get in every project, built-in.
                    </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                    {valueStack.map((item, index) => (
                         <motion.div
                            key={index}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true, amount: 0.3 }}
                            transition={{ delay: index * 0.1, duration: 0.5 }}
                        >
                        <Card className="h-full bg-card border shadow-lg hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300 rounded-2xl p-6 text-center">
                            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mb-6">
                                <item.icon className="h-8 w-8 text-primary"/>
                            </div>
                            <h3 className="text-xl font-bold mb-2">{item.title}</h3>
                            <p className="text-muted-foreground">{item.description}</p>
                        </Card>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>

        <section className="py-16 sm:py-20 bg-secondary/40">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="text-center mb-12">
                    <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">How We Compare</h2>
                    <p className="mt-4 max-w-2xl mx-auto text-lg leading-8 text-muted-foreground">
                        The smarter, faster, and safer way to build.
                    </p>
                </div>
                <Card className="shadow-2xl rounded-2xl overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow className="bg-card">
                                <TableHead className="font-bold text-foreground w-[25%]">Feature</TableHead>
                                <TableHead className="font-bold text-primary w-[25%] text-center">Our Platform</TableHead>
                                <TableHead className="font-bold text-muted-foreground w-[25%] text-center">Agency</TableHead>
                                <TableHead className="font-bold text-muted-foreground w-[25%] text-center">In-House Hiring</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {comparisonData.map((row) => (
                                <TableRow key={row.feature} className="transition-colors hover:bg-secondary/20">
                                    <TableCell className="font-semibold text-foreground">{row.feature}</TableCell>
                                    <TableCell className="font-bold text-primary text-center bg-primary/5">{row.us}</TableCell>
                                    <TableCell className="text-muted-foreground text-center">{row.agency}</TableCell>
                                    <TableCell className="text-muted-foreground text-center">{row.hiring}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Card>
            </div>
        </section>


        <BenchmarkSlider />

        <section className="py-16 sm:py-20 bg-secondary/40">
          <div className="mx-auto max-w-4xl px-6 lg:px-8 text-center">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">Ready to See the Difference?</h2>
            <p className="mt-4 text-lg leading-8 text-muted-foreground">
              Let's scope your project and show you how much more you can achieve with your budget.
            </p>
            <div className="mt-10">
              <Button asChild size="lg">
                <Link to="/start-project">
                  Start Your Project <ArrowRight className="ml-2 h-5 w-5" />
                </Link>
              </Button>
            </div>
          </div>
        </section>
      </div>
    </>
  );
};

export default ValueAndPricingPage;