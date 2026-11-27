
import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { BrainCircuit, Layers, Zap, ShieldCheck, Cpu, Bot, CheckCircle, GitBranch, Search, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';

const agentTypes = [
    {
        icon: SlidersHorizontal,
        name: "Master Planner Agents",
        description: "These agents are the architects of your project. They analyze your requirements, break down complex goals into actionable tasks, and create a strategic roadmap for the entire execution process."
    },
    {
        icon: Cpu,
        name: "Specialist Execution Agents",
        description: "A diverse team of AI agents with specialized skills (e.g., coding, design, data analysis) that work on the tasks defined by the Master Planner, ensuring expert-level output for each component."
    },
    {
        icon: GitBranch,
        name: "Integration & Orchestration Agents",
        description: "These agents act as project managers, ensuring all the different parts created by specialist agents fit together perfectly. They manage dependencies and streamline the workflow."
    },
    {
        icon: CheckCircle,
        name: "Quality Assurance (QA) Agents",
        description: "Dedicated agents that continuously test and review the work, identifying bugs, inconsistencies, and deviations from the project goals, ensuring a polished and reliable final product."
    },
    {
        icon: Search,
        name: "Research & Analysis Agents",
        description: "These agents constantly scan for the latest technologies, best practices, and potential challenges, feeding real-time insights back into the project to ensure cutting-edge results."
    },
    {
        icon: Bot,
        name: "Client Communication Agents",
        description: "Your dedicated AI liaison that provides real-time progress updates, answers your questions, and ensures you are always in the loop without needing to manage a human team."
    }
];

const AgenticAiModelsPage = () => {
    return (
        <>
            <Helmet>
                <title>AI-Driven Projects | Pay Per Project</title>
                <meta name="description" content="Discover how our proprietary Agentic AI models drive our projects, delivering unparalleled speed, efficiency, and quality. This is the engine behind our execution." />
            </Helmet>

            <div className="bg-background text-foreground">
                {/* Hero Section */}
                <div className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-24 sm:pt-32 pb-16">
                    <div className="mx-auto max-w-7xl px-6 lg:px-8 text-center">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ duration: 0.5 }}
                        >
                            <div className="relative inline-block">
                                <BrainCircuit className="mx-auto h-12 w-12 text-primary" />
                            </div>
                            <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-6xl font-heading">
                                Our Projects are AI-Driven
                            </h1>
                            <p className="mt-6 text-lg leading-8 text-muted-foreground max-w-3xl mx-auto">
                                We've moved beyond traditional development. Discover the powerful Agentic AI ecosystem that allows us to build faster, smarter, and more reliably than ever before.
                            </p>
                            <div className="mt-10">
                                <Button asChild size="lg">
                                    <Link to="/start-project">Start Your AI-Driven Project</Link>
                                </Button>
                            </div>
                        </motion.div>
                    </div>
                </div>

                {/* The Engine Section */}
                <section id="engine" className="py-16 sm:py-20 bg-secondary/40">
                    <div className="mx-auto max-w-7xl px-6 lg:px-8">
                        <div className="text-center mb-12">
                            <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">The Engine Behind Our Execution</h2>
                            <p className="mt-4 text-lg text-muted-foreground max-w-3xl mx-auto">
                                Our platform isn't just a marketplace; it's a sophisticated ecosystem where multiple AI agents collaborate to bring your project to life. This multi-agent system is our secret to delivering complex projects with superhuman speed and precision.
                            </p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                            {agentTypes.map((agent, index) => (
                                <motion.div
                                    key={index}
                                    initial={{ opacity: 0, y: 20 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true, amount: 0.3 }}
                                    transition={{ delay: index * 0.1, duration: 0.5 }}
                                >
                                    <div className="bg-card p-6 rounded-2xl shadow-lg h-full flex flex-col text-left border border-card-border hover:shadow-primary/20 hover:-translate-y-2 transition-all duration-300">
                                        <div className="mb-4 p-3 bg-primary/10 rounded-full w-fit">
                                            <agent.icon className="h-7 w-7 text-primary" />
                                        </div>
                                        <h3 className="text-xl font-bold mb-2 text-foreground font-heading">{agent.name}</h3>
                                        <p className="text-muted-foreground text-base leading-relaxed">{agent.description}</p>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </div>
                </section>

                {/* Why It Matters Section */}
                <section className="py-16 sm:py-20">
                    <div className="mx-auto max-w-7xl px-6 lg:px-8">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
                            <div className="text-left">
                                <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">Why Our AI-Driven Approach Wins</h2>
                                <p className="mt-4 text-lg text-muted-foreground">
                                    This isn't about replacing humans; it's about augmenting them. Our AI handles the heavy lifting, freeing up our human experts to focus on strategy, creativity, and client success.
                                </p>
                                <ul className="mt-8 space-y-4">
                                    <li className="flex items-start">
                                        <Zap className="h-6 w-6 text-primary flex-shrink-0 mr-4 mt-1" />
                                        <div>
                                            <h4 className="font-bold">Unmatched Speed</h4>
                                            <p className="text-muted-foreground">Our AI agents work 24/7, accelerating development timelines from months to weeks.</p>
                                        </div>
                                    </li>
                                    <li className="flex items-start">
                                        <ShieldCheck className="h-6 w-6 text-primary flex-shrink-0 mr-4 mt-1" />
                                        <div>
                                            <h4 className="font-bold">Superior Quality</h4>
                                            <p className="text-muted-foreground">Automated QA and continuous integration catch issues instantly, resulting in more robust and reliable products.</p>
                                        </div>
                                    </li>
                                    <li className="flex items-start">
                                        <Layers className="h-6 w-6 text-primary flex-shrink-0 mr-4 mt-1" />
                                        <div>
                                            <h4 className="font-bold">Radical Efficiency</h4>
                                            <p className="text-muted-foreground">By automating repetitive tasks, we reduce overhead and pass the cost savings directly on to you.</p>
                                        </div>
                                    </li>
                                </ul>
                            </div>
                            <motion.div
                                initial={{ opacity: 0, scale: 0.9 }}
                                whileInView={{ opacity: 1, scale: 1 }}
                                viewport={{ once: true }}
                                transition={{ duration: 0.5 }}
                                className="relative h-96"
                            >
                                <img alt="Abstract visualization of AI neural network" class="w-full h-full object-cover rounded-2xl shadow-2xl" src="https://images.unsplash.com/photo-1667371927761-8fa90f33a248" />
                            </motion.div>
                        </div>
                    </div>
                </section>
            </div>
        </>
    );
};

export default AgenticAiModelsPage;
