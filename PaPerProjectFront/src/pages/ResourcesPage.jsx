import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { Link, useNavigate } from 'react-router-dom';
import { BookOpen, Users, Video, GraduationCap, LifeBuoy, FileText, Sparkles, Cpu, Lightbulb, ArrowRight, Briefcase, Layers, Wrench, BrainCircuit, HeartHandshake as Handshake } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { useToast } from "@/components/ui/use-toast";

const resourceCategories = [
  {
    category: 'Learn',
    items: [
      { to: '/blog', title: 'Blog', icon: BookOpen, description: 'Insights, trends, and stories from our experts.' },
    ]
  },
  {
    category: 'Agentic AI',
    items: [
      { to: '/resources/agentic-ai-explained#what-is-agentic-ai', title: 'What is agentic AI', icon: Lightbulb, description: 'Understand the core concepts of autonomous AI.' },
      { to: '/resources/agentic-ai-explained#ai-vs-agentic-ai', title: 'AI Agent vs Agentic AI', icon: Cpu, description: 'Learn the key differences and capabilities.' },
      { to: '/resources/agentic-ai-explained#use-cases', title: 'Business Use Cases', icon: BrainCircuit, description: 'Explore real-world applications of Agentic AI.' },
      { to: '/resources/agentic-ai-explained#how-to-build', title: 'Build an AI Agent', icon: Wrench, description: 'A guide to creating your first autonomous agent.' },
    ]
  },
  {
    category: 'Connect',
    items: [
      { to: '/contact', title: 'Support', icon: LifeBuoy, description: 'Get in touch with our team for assistance.' },
    ]
  }
];

const ResourceCard = ({ to, title, icon: Icon, description }) => {
  const navigate = useNavigate();

  // Every card is a real page now (27 Nov 2026: six said "Coming Soon"). An article section opens the article,
  // then scrolls to the section, as the header's Resources menu does.
  const handleClick = (e) => {
    if (to.includes('#')) {
      e.preventDefault();
      const [path, hash] = to.split('#');
      navigate(path);
      setTimeout(() => document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 400);
    }
  };

  return (
    <Link to={to} onClick={handleClick} className="block group">
      <Card className="h-full hover:border-primary transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
        <CardHeader className="flex flex-row items-center gap-4">
          <div className="bg-primary/10 p-3 rounded-lg">
            <Icon className="h-6 w-6 text-primary" />
          </div>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription>{description}</CardDescription>
        </CardContent>
      </Card>
    </Link>
  );
};

const ResourcesPage = () => {
  return (
    <>
      <Helmet>
        <title>Resources | Guides, Tutorials, and Case Studies</title>
        <meta name="description" content="Explore our comprehensive resource hub. Find blog articles, customer stories, video tutorials, and in-depth guides on Agentic AI and more." />
      </Helmet>
      <div className="bg-background text-foreground">
        <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
          <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
            >
              <BookOpen className="mx-auto h-12 w-12 text-primary" />
              <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-6xl">
                Resource Hub
              </h1>
              <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                Your central place for knowledge, inspiration, and support. Dive into our articles, guides, and stories to build better, faster.
              </p>
            </motion.div>
          </div>
        </div>

        <div className="py-16 sm:py-20">
          <div className="mx-auto max-w-7xl px-6 lg:px-8">
            {resourceCategories.map((category, catIndex) => (
              <div key={category.category} className="mb-16">
                <motion.h2
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 0.5 }}
                  className="text-3xl font-bold tracking-tight mb-8"
                >
                  {category.category}
                </motion.h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
                  {category.items.map((item, itemIndex) => (
                    <motion.div
                      key={item.title}
                      initial={{ opacity: 0, y: 20 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.2 }}
                      transition={{ duration: 0.5, delay: itemIndex * 0.1 }}
                    >
                      <ResourceCard {...item} />
                    </motion.div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
};

export default ResourcesPage;