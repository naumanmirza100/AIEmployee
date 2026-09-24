
import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { BrainCircuit, Layers, Wrench, Briefcase, Cpu, Lightbulb, Sparkles, ArrowRight, ChevronRight, CheckCircle, GitBranch, Bot, Code, Database, Microscope, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";


const agenticAiTopics = [
    { id: 'what-is-agentic-ai', title: 'What is Agentic AI?', icon: Lightbulb },
    { id: 'what-does-agentic-mean', title: 'What Does "Agentic" Mean?', icon: Sparkles },
    { id: 'ai-vs-agentic-ai', title: 'AI Agent vs. Agentic AI', icon: Cpu },
    { id: 'how-to-build', title: 'How to Build an AI Agent', icon: Wrench },
    { id: 'tools', title: 'Agentic AI Tools', icon: Briefcase },
    { id: 'frameworks', title: 'Agentic Frameworks', icon: Layers },
    { id: 'use-cases', title: 'Business Use Cases', icon: BrainCircuit },
];

const frameworksData = {
    langchain: {
        name: "LangChain",
        description: "A comprehensive open-source framework with modular components for building and chaining together LLM-powered applications, including complex agents.",
        pros: ["Vast ecosystem of integrations", "Highly flexible and modular", "Large community support"],
    },
    crewai: {
        name: "CrewAI",
        description: "A framework focused on orchestrating role-playing, autonomous AI agents that collaborate to solve tasks. It emphasizes the concept of a 'crew' of specialized agents.",
        pros: ["Excellent for collaborative tasks", "Simple, intuitive API", "Promotes role-defined agents"],
    },
    autogen: {
        name: "AutoGen (Microsoft)",
        description: "A framework for creating applications with multiple, 'conversable' agents that can interact with each other to solve complex problems.",
        pros: ["Strong for multi-agent simulation", "Backed by Microsoft Research", "Highly customizable agent behaviors"],
    },
    llamaindex: {
        name: "LlamaIndex",
        description: "A data framework for LLM applications, specializing in connecting custom data sources to LLMs. It excels at creating powerful data-centric agents (RAG).",
        pros: ["Best-in-class for Retrieval-Augmented Generation", "Advanced data ingestion and indexing", "Optimized for query engines"],
    },
    phidata: {
        name: "PhiData",
        description: "A toolkit for building production-quality AI products. It simplifies the creation of agents by providing pre-built integrations for tools, data, and models.",
        pros: ["Production-focused features", "Easy-to-use abstractions", "Strong support for OpenAI Functions"],
    },
};

const ScrollLink = ({ to, children }) => {
    const handleClick = (e) => {
        e.preventDefault();
        const element = document.getElementById(to);
        if (element) {
            const offset = 100; // Header height
            const bodyRect = document.body.getBoundingClientRect().top;
            const elementRect = element.getBoundingClientRect().top;
            const elementPosition = elementRect - bodyRect;
            const offsetPosition = elementPosition - offset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }
    };
    return <a href={`#${to}`} onClick={handleClick}>{children}</a>;
};

const AgenticAiResourcePage = () => {

    const renderTwoColSection = ({id, title, icon, content, visual, layout = 'text-left'}) => (
        <motion.section
            id={id}
            className="py-16 sm:py-20 scroll-mt-24"
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.1 }}
            transition={{ duration: 0.6 }}
        >
             <div className="flex items-center gap-4 mb-8">
                {React.createElement(icon, { className: "h-8 w-8 text-primary" })}
                <h2 className="text-3xl md:text-4xl font-bold tracking-tight">{title}</h2>
            </div>
            <div className={`grid grid-cols-1 md:grid-cols-2 gap-12 items-center`}>
                <div className={`prose prose-lg lg:prose-xl max-w-none text-muted-foreground ${layout === 'text-right' ? 'md:order-2' : ''}`}>
                    {content}
                </div>
                <div className={`mt-8 md:mt-0 ${layout === 'text-right' ? 'md:order-1' : ''}`}>
                    {visual}
                </div>
            </div>
        </motion.section>
    );
    
    const renderFullWidthSection = ({id, title, icon, content}) => (
        <motion.section
            id={id}
            className="py-16 sm:py-20 scroll-mt-24"
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.1 }}
            transition={{ duration: 0.6 }}
        >
             <div className="flex items-center gap-4 mb-8">
                {React.createElement(icon, { className: "h-8 w-8 text-primary" })}
                <h2 className="text-3xl md:text-4xl font-bold tracking-tight">{title}</h2>
            </div>
            <div className="prose prose-lg lg:prose-xl max-w-none text-muted-foreground">
                {content}
            </div>
        </motion.section>
    );

    return (
        <>
            <Helmet>
                <title>Agentic AI Explained | Pay Per Project</title>
                <meta name="description" content="A complete guide to Agentic AI. Learn what it means, the tools and frameworks to use, and how it's revolutionizing business with real-world use cases." />
            </Helmet>
            <div className="bg-background text-foreground">
                <section className="relative isolate overflow-hidden bg-gradient-to-b from-primary/5 to-transparent pt-32 pb-20 md:pt-40 md:pb-28">
                    <div className="container mx-auto px-4 text-center">
                        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.1 }}>
                            <BrainCircuit className="mx-auto h-16 w-16 text-primary" />
                            <h1 className="mt-4 text-4xl md:text-6xl font-extrabold tracking-tight text-glow">
                                The World of Agentic AI
                            </h1>
                            <p className="mt-6 max-w-3xl mx-auto text-lg text-muted-foreground">
                                Your definitive guide to understanding Agentic AI. From core concepts to practical applications, explore how autonomous agents are reshaping the future of technology and business.
                            </p>
                        </motion.div>
                    </div>
                </section>

                <div className="container mx-auto px-4">
                    <div className="lg:grid lg:grid-cols-4 lg:gap-12">
                        <aside className="lg:col-span-1 lg:sticky top-24 self-start hidden lg:block py-8">
                            <h3 className="text-lg font-semibold mb-4">On this page</h3>
                            <ul className="space-y-3">
                                {agenticAiTopics.map(topic => (
                                    <li key={topic.id}>
                                        <ScrollLink to={topic.id}>
                                            <span className="flex items-center text-muted-foreground hover:text-primary transition-colors duration-200 group">
                                                <ChevronRight className="h-4 w-4 mr-2 opacity-0 group-hover:opacity-100 transition-opacity" />
                                                {topic.title}
                                            </span>
                                        </ScrollLink>
                                    </li>
                                ))}
                            </ul>
                        </aside>

                        <main className="lg:col-span-3 divide-y divide-border">
                            {renderTwoColSection({id: 'what-is-agentic-ai', title: 'What is Agentic AI?', icon: Lightbulb, layout: 'text-left',
                                content: <>
                                    <p><strong>Agentic AI</strong> represents a paradigm shift from instruction-following systems to goal-oriented partners. These are not just passive tools that await commands, but active, autonomous agents capable of independent thought and action.</p>
                                    <p>An agentic system can perceive its environment, create a plan, execute multi-step tasks, and adapt to new information—all to achieve a complex, high-level objective you've assigned. It's the difference between a spell-checker and an AI that can write, edit, and format an entire report based on a simple prompt.</p>
                                </>,
                                visual: <img className="rounded-lg shadow-2xl" alt="An abstract visualization of a glowing neural network, representing an AI's brain, forming new, complex connections." src="https://images.unsplash.com/photo-1700941019917-731dc64ce685" />
                            })}
                            
                            {renderTwoColSection({id: 'what-does-agentic-mean', title: 'What Does "Agentic" Mean?', icon: Sparkles, layout: 'text-right',
                                content: <>
                                    <p>The term <strong>"agentic"</strong> is derived from "agency"—the capacity of an entity to act independently and make its own choices in an environment. For an AI, this means it's more than just a complex algorithm; it's a digital entity with a degree of freedom.</p>
                                    <p>An agentic system possesses several key qualities:</p>
                                    <ul className="list-none space-y-3 !pl-0">
                                      <li className="flex items-start"><CheckCircle className="h-5 w-5 text-green-500 mr-3 mt-1 flex-shrink-0" /><span><strong>Autonomy:</strong> Operates without constant human oversight.</span></li>
                                      <li className="flex items-start"><CheckCircle className="h-5 w-5 text-green-500 mr-3 mt-1 flex-shrink-0" /><span><strong>Proactiveness:</strong> Takes initiative to achieve goals, not just react to inputs.</span></li>
                                      <li className="flex items-start"><CheckCircle className="h-5 w-5 text-green-500 mr-3 mt-1 flex-shrink-0" /><span><strong>Statefulness:</strong> Maintains memory of past interactions to inform future actions.</span></li>
                                      <li className="flex items-start"><CheckCircle className="h-5 w-5 text-green-500 mr-3 mt-1 flex-shrink-0" /><span><strong>Goal-Orientation:</strong> All actions are driven by a defined set of objectives.</span></li>
                                    </ul>
                                </>,
                                visual: <img className="rounded-lg shadow-2xl" alt="A sleek, modern robotic arm making a precise and independent decision, with light trails indicating its thought process." src="https://images.unsplash.com/photo-1572424319290-abdbc6c0b761" />
                            })}
                            
                            {renderTwoColSection({id: 'ai-vs-agentic-ai', title: 'AI Agent vs. Agentic AI', icon: Cpu, layout: 'text-left',
                                content: <>
                                    <p>While related, these terms describe different levels of complexity. An <strong>AI Agent</strong> is often a single program designed for a specific task (e.g., a customer service chatbot). <strong>Agentic AI</strong> refers to a more sophisticated architecture where agents can reason, plan, and use multiple tools to achieve broader goals.</p>
                                    <Card className="my-6 bg-secondary/30 border-l-4 border-primary">
                                        <CardContent className="p-6">
                                            <h4 className="font-bold text-lg mb-2 text-foreground">Analogy: The Kitchen Crew</h4>
                                            <p>An <strong>AI Agent</strong> is a single-purpose kitchen appliance, like a smart blender. It excels at one job: blending.</p>
                                            <p>An <strong>Agentic AI System</strong> is the entire kitchen crew. The head chef (main agent) takes the order ("make a healthy dinner"), then directs the sous-chef (sub-agent) to wash vegetables, another to operate the oven, and uses the blender itself. They work together, using multiple tools to complete a complex project.</p>
                                        </CardContent>
                                    </Card>
                                </>,
                                visual: <img className="rounded-lg shadow-2xl" alt="A diagram comparing a single AI agent (one icon) to an Agentic AI system (multiple interconnected icons collaborating)." src="https://images.unsplash.com/photo-1684369175809-f9642140a1bd" />
                            })}
                            
                            {renderTwoColSection({id: 'how-to-build', title: 'How to Build an AI Agent', icon: Wrench, layout: 'text-right',
                                content: <>
                                    <p>Building an agent involves a cycle of reasoning, action, and learning. The dominant architecture for this is the <strong>ReAct (Reason and Act)</strong> loop, which we can break down into more granular steps:</p>
                                    <ol className="list-decimal pl-6 space-y-4">
                                        <li><strong><Bot className="inline-block h-5 w-5 mr-2" />Objective & Constraints:</strong> Define a clear, measurable goal and set boundaries (e.g., budget, allowed tools, ethical guidelines).</li>
                                        <li><strong><BrainCircuit className="inline-block h-5 w-5 mr-2" />Model as a Brain:</strong> Select a powerful Large Language Model (LLM) capable of strong reasoning, like GPT-4, Claude 3, or Llama 3.</li>
                                        <li><strong><Wrench className="inline-block h-5 w-5 mr-2" />Tool Belt Creation:</strong> Grant the agent access to specific tools (functions or APIs). This can range from a simple web search to complex actions like executing code or accessing a proprietary database.</li>
                                        <li><strong><GitBranch className="inline-block h-5 w-5 mr-2" />The ReAct Loop in Action:</strong>
                                            <ul className="list-disc pl-6 my-2 space-y-2">
                                                <li><strong>Thought:</strong> The LLM analyzes the goal, current context, and memory, then forms a hypothesis and plan. E.g., "I need to find the current stock price of AAPL. I should use the `getStockPrice` tool."</li>
                                                <li><strong>Action:</strong> The agent executes the chosen tool with the necessary parameters (`getStockPrice(ticker='AAPL')`).</li>
                                                <li><strong>Observation:</strong> The agent receives the tool's output (e.g., "$175.30") and adds it to its working memory.</li>
                                                <li><strong>Self-Correction:</strong> The loop repeats. If an action fails or the result is unexpected, the LLM reasons about the failure and formulates a new plan.</li>
                                            </ul>
                                        </li>
                                        <li><strong><Database className="inline-block h-5 w-5 mr-2" />Memory Management:</strong> Implement both short-term "scratchpad" memory for the current task and long-term memory using vector databases for enduring context and learning.</li>
                                    </ol>
                                </>,
                                visual: <img className="rounded-lg shadow-2xl" alt="A clear, modern flowchart illustrating the cyclical Reason-Act-Observe loop with added steps for self-correction and memory." src="https://images.unsplash.com/photo-1611798416123-c1255cff2c0e" />
                            })}
                            
                            {renderFullWidthSection({id: 'tools', title: 'Agentic AI Tools', icon: Briefcase,
                                content: <>
                                    <p>A powerful ecosystem of tools has emerged to accelerate agent development, providing critical components for memory, action, and monitoring.</p>
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Tool Category</TableHead>
                                                <TableHead>Examples</TableHead>
                                                <TableHead>Purpose</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            <TableRow>
                                                <TableCell className="font-medium flex items-center"><Database className="h-4 w-4 mr-2" />Vector Databases</TableCell>
                                                <TableCell>Pinecone, Weaviate, Chroma, Qdrant</TableCell>
                                                <TableCell>Provides long-term, searchable memory.</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell className="font-medium flex items-center"><GitBranch className="h-4 w-4 mr-2" />API Integrators</TableCell>
                                                <TableCell>Zapier NLA, Make.com, Tavily AI</TableCell>
                                                <TableCell>Gives agents "hands" to use thousands of web apps.</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell className="font-medium flex items-center"><Code className="h-4 w-4 mr-2" />Code Execution</TableCell>
                                                <TableCell>E2B, CodeBox, Open Interpreter</TableCell>
                                                <TableCell>Secure sandboxes for agents to run and debug code.</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell className="font-medium flex items-center"><Microscope className="h-4 w-4 mr-2" />Observability</TableCell>
                                                <TableCell>LangSmith, Arize AI, Weights & Biases</TableCell>
                                                <TableCell>Debugs and traces an agent's thought process.</TableCell>
                                            </TableRow>
                                        </TableBody>
                                    </Table>
                                </>
                            })}
                            
                            {renderFullWidthSection({id: 'frameworks', title: 'Agentic Frameworks', icon: Layers,
                                content: <>
                                    <p>Frameworks provide the essential scaffolding to build and orchestrate agentic systems, managing the complex interactions between LLMs, tools, and memory.</p>
                                    <Tabs defaultValue="langchain" className="w-full mt-4">
                                        <TabsList className="grid w-full grid-cols-3 sm:grid-cols-5">
                                            {Object.keys(frameworksData).map(key => (
                                                <TabsTrigger key={key} value={key} className="text-xs sm:text-sm">{frameworksData[key].name}</TabsTrigger>
                                            ))}
                                        </TabsList>
                                        {Object.entries(frameworksData).map(([key, data]) => (
                                            <TabsContent value={key} key={key} className="mt-4">
                                                <Card>
                                                    <CardHeader>
                                                        <CardTitle>{data.name}</CardTitle>
                                                        <p className="text-sm text-muted-foreground pt-2">{data.description}</p>
                                                    </CardHeader>
                                                    <CardContent>
                                                        <h4 className="font-semibold mb-2">Best For:</h4>
                                                        <ul className="list-disc pl-5 text-sm text-muted-foreground space-y-1">
                                                            {data.pros.map(pro => <li key={pro}>{pro}</li>)}
                                                        </ul>
                                                    </CardContent>
                                                </Card>
                                            </TabsContent>
                                        ))}
                                    </Tabs>
                                </>
                            })}
                            
                           {renderFullWidthSection({id: 'use-cases', title: 'Exact Business Use Cases', icon: BrainCircuit,
                                content: <>
                                    <p>Agentic AI isn't theoretical; it's actively delivering value. Here are exact, real-world applications of agentic systems in business today:</p>
                                    <div className="space-y-8 mt-8">
                                        <Card className="bg-background">
                                            <CardHeader>
                                                <CardTitle className="flex items-center"><Bot className="mr-3 h-6 w-6 text-primary" /> The Autonomous SDR (Sales Development)</CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <p className="mb-4">An agent tasked with identifying and qualifying 100 new enterprise leads for a B2B SaaS product.</p>
                                                <ol className="list-decimal pl-5 space-y-2">
                                                    <li><strong>Research:</strong> Scans LinkedIn Sales Navigator and Apollo.io for profiles matching criteria (e.g., "Head of Product" at companies with 50-500 employees that recently raised a Series A).</li>
                                                    <li><strong>Enrichment & Personalization:</strong> Uses Clearbit to find emails, then scans company blogs to find a personalization hook for the outreach email.</li>
                                                    <li><strong>Action:</strong> Drafts and sends hyper-personalized emails via a HubSpot API.</li>
                                                    <li><strong>Follow-up:</strong> If no reply is received within 3 days, it sends a polite follow-up. When a lead replies, it hands the conversation over to a human sales rep.</li>
                                                </ol>
                                            </CardContent>
                                        </Card>
                                        <Card className="bg-background">
                                            <CardHeader>
                                                <CardTitle className="flex items-center"><GitBranch className="mr-3 h-6 w-6 text-primary" /> The Proactive Supply Chain Analyst</CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <p className="mb-4">An agent designed to prevent stockouts by monitoring global supply chain events.</p>
                                                <ol className="list-decimal pl-5 space-y-2">
                                                    <li><strong>Monitor:</strong> Continuously scans weather reports, news APIs, and shipping lane data for disruptions near key supplier locations.</li>
                                                    <li><strong>Analyze:</strong> Upon detecting a potential disruption (e.g., a port strike), it queries internal inventory levels and sales forecasts to calculate the risk of a stockout.</li>
                                                    <li><strong>Plan:</strong> Identifies alternative suppliers from a pre-vetted database and checks their current capacity and lead times via an API.</li>
                                                    <li><strong>Alert & Act:</strong> Generates a high-priority alert for the human logistics manager with a full report and a suggested purchase order, ready for one-click approval.</li>
                                                </ol>
                                            </CardContent>
                                        </Card>
                                        <Card className="bg-background">
                                            <CardHeader>
                                                <CardTitle className="flex items-center"><Code className="mr-3 h-6 w-6 text-primary" /> The AI Code Review & Refactor Agent</CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <p className="mb-4">An agent integrated into a GitHub repository to improve code quality and reduce technical debt.</p>
                                                <ol className="list-decimal pl-5 space-y-2">
                                                    <li><strong>Observe:</strong> Monitors for new pull requests.</li>
                                                    <li><strong>Review:</strong> Analyzes the submitted code for style guide violations, potential bugs (e.g., null pointer exceptions), and inefficiencies.</li>
                                                    <li><strong>Suggest:</strong> Posts comments directly on the pull request with specific, actionable code suggestions for improvement.</li>
                                                    <li><strong>Refactor:</strong> For common issues, it automatically creates and pushes a new commit with the refactored code, explaining its changes in the commit message for the developer to approve.</li>
                                                </ol>
                                            </CardContent>
                                        </Card>
                                    </div>
                                </>
                            })}
                            
                            <motion.section
                                className="py-20"
                                initial={{ opacity: 0 }}
                                whileInView={{ opacity: 1 }}
                                viewport={{ once: true }}
                                transition={{ duration: 0.8 }}
                            >
                                <div className="bg-gradient-to-r from-primary/90 to-purple-600 rounded-2xl p-8 md:p-12 text-center text-pure-white shadow-2xl relative overflow-hidden">
                                    <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to Deploy Agentic AI?</h2>
                                    <p className="max-w-2xl mx-auto text-lg text-primary-foreground/90 mb-8">
                                        Turn theory into practice. Our experts can help you design, build, and deploy a custom AI agent tailored to solve your most complex business challenges.
                                    </p>
                                    <Button asChild size="lg" variant="secondary" className="font-bold text-lg px-8 py-6 rounded-full shadow-lg transition-transform hover:scale-105">
                                        <Link to="/start-project">
                                            Start Your AI Project <ArrowRight className="ml-2 h-5 w-5" />
                                        </Link>
                                    </Button>
                                </div>
                            </motion.section>
                        </main>
                    </div>
                </div>
            </div>
        </>
    );
};

export default AgenticAiResourcePage;
