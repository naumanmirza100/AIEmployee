// import React, { useState, useEffect, useRef } from 'react';
// import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
// import { Button } from '@/components/ui/button';
// import { Textarea } from '@/components/ui/textarea';
// import { Label } from '@/components/ui/label';
// import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
// import { useToast } from '@/components/ui/use-toast';
// import { Badge } from '@/components/ui/badge';
// import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
// import { Input } from '@/components/ui/input';
// import {
//   Loader2,
//   Send,
//   MessageSquare,
//   Plus,
//   Bot,
//   User,
//   Sparkles,
//   ChevronLeft,
//   ChevronRight,
//   ChevronUp,
//   ChevronDown,
//   X,
//   Lightbulb,
//   TrendingUp,
//   Target,
//   BarChart3,
//   BookOpen,
//   Award,
//   Zap,
//   Search,
//   BarChart2,
//   Maximize2,
//   Save,
//   LayoutDashboard,
//   PieChart,
//   Activity
// } from 'lucide-react';
// import marketingAgentService from '@/services/marketingAgentService';
// import { motion, AnimatePresence } from 'framer-motion';
// import { cn } from '@/lib/utils';

// const STORAGE_KEY = 'marketing_qa_chats';

// /** Normalize question for comparison: trim, lower, collapse spaces, remove trailing punctuation */
// function normalizeQuestion(text) {
//   if (!text || typeof text !== 'string') return '';
//   return text
//     .replace(/\u200B|\u200C|\u200D|\uFEFF/g, '')
//     .replace(/\s+/g, ' ')
//     .trim()
//     .toLowerCase()
//     .replace(/[?!.,;:]+\s*$/, '');
// }

// /** True if question is greeting/small talk – do not call API */
// function isGreetingOrSmallTalk(question) {
//   const t = normalizeQuestion(question);
//   if (!t) return true;
//   if (t.length > 40) return false;
//   const smallTalk = new Set([
//     'hi', 'hii', 'hello', 'hey', 'helo', 'yo', 'sup', 'thanks', 'thank you', 'thx',
//     'ok', 'okay', 'oky', 'okey', 'okie', 'k', 'kk', 'bye', 'goodbye', 'cya',
//     'good', 'great', 'nice', 'cool', 'alright', 'fine', 'got it', 'understood',
//     'perfect', 'sure', 'yeah', 'yep', 'yup', 'nope', 'no', 'yes',
//     'ok good', 'okay good', 'oky good', 'ok god', 'oky god', 'okay god',
//     'okya', 'okya good', 'okya god', 'okie good', 'gud', 'gud good',
//   ]);
//   if (smallTalk.has(t)) return true;
//   if (t.length <= 14 && /^ok[a-z]*\s*(good|god|gud)?$/.test(t)) return true;
//   return false;
// }

// /** True if question is meta (what can I ask) – do not call API. Platform/agent questions ("what is this platform", "how does this work") go to API. */
// function isMetaQuestion(question) {
//   const t = normalizeQuestion(question);
//   if (!t || t.length > 80) return false;
//   const metaPhrases = [
//     'what can i ask', 'what i can ask', 'how can you help', 'what do you do',
//     'what can you answer', 'what should i ask',
//     'example questions', 'give me examples', 'what to ask',
//   ];
//   return metaPhrases.some((p) => t.includes(p));
// }

// /** Markdown to HTML for Q&A answers - readable paragraphs, headings, bullets, tables */
// function markdownToHtml(markdown) {
//   if (!markdown || typeof markdown !== 'string') return '';

//   const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
//   const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-primary">$1</strong>');

//   const lines = markdown.split('\n');
//   const out = [];
//   let inList = false;
//   let i = 0;

//   while (i < lines.length) {
//     const line = lines[i];
//     const t = line.trim();

//     // Markdown table: | col | col |
//     if (t.startsWith('|') && t.endsWith('|')) {
//       if (inList) { out.push('</ul>'); inList = false; }

//       const tableRows = [];
//       let j = i;
//       while (j < lines.length && lines[j].trim().startsWith('|')) {
//         const cells = lines[j].trim().split('|').map(c => c.trim()).filter(Boolean);
//         if (cells.length > 0 && cells.every(c => /^[-:\s]+$/.test(c))) {
//           j++;
//           continue;
//         }
//         tableRows.push(cells);
//         j++;
//       }
//       i = j;

//       if (tableRows.length > 0) {
//         out.push('<div class="my-5 overflow-x-auto rounded-lg border border-border shadow-sm"><table class="w-full text-base">');
//         out.push('<thead><tr class="bg-gradient-to-r from-muted/80 to-muted/40">');
//         tableRows[0].forEach(cell => out.push(`<th class="px-4 py-3 text-left font-semibold text-foreground">${bold(escape(cell))}</th>`));
//         out.push('</tr></thead><tbody>');
//         tableRows.slice(1).forEach((row, idx) => {
//           out.push(`<tr class="${idx % 2 === 0 ? 'bg-gradient-to-r from-muted/20 to-transparent' : ''} hover:bg-muted/30 transition-colors">`);
//           row.forEach(cell => out.push(`<td class="px-4 py-3 border-t border-border text-base">${bold(escape(cell))}</td>`));
//           out.push('</tr>');
//         });
//         out.push('</tbody></table></div>');
//       }
//       continue;
//     }

//     if (/^---+$/.test(t)) {
//       if (inList) { out.push('</ul>'); inList = false; }
//       out.push('<hr class="my-5 border-border/50 bg-gradient-to-r from-transparent via-border to-transparent"/>');
//       i++; continue;
//     }

//     if (/^## /.test(t)) {
//       if (inList) { out.push('</ul>'); inList = false; }
//       out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2 bg-gradient-to-r from-primary/5 to-transparent p-2 rounded-lg">${bold(escape(t.slice(3)))}</h2>`);
//       i++; continue;
//     }

//     if (/^### /.test(t)) {
//       if (inList) { out.push('</ul>'); inList = false; }
//       out.push(`<h3 class="text-lg font-bold mt-4 mb-2 text-foreground bg-gradient-to-r from-muted/30 to-transparent p-2 rounded-lg">${bold(escape(t.slice(4)))}</h3>`);
//       i++; continue;
//     }

//     // Lines ending with : (like "Opportunities We're Missing:") treated as h2
//     if (t.endsWith(':') && t.length > 10 && !t.startsWith('-') && !t.startsWith('*')) {
//       if (inList) { out.push('</ul>'); inList = false; }
//       out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2 bg-gradient-to-r from-primary/5 to-transparent p-2 rounded-lg">${bold(escape(t))}</h2>`);
//       i++; continue;
//     }

//     if (/^[\s]*(?:•|-|\*|\d+\.)\s+/.test(t)) {
//       if (!inList) {
//         out.push('<ul class="list-disc pl-6 my-4 space-y-2 bg-gradient-to-r from-muted/10 to-transparent p-3 rounded-lg">');
//         inList = true;
//       }
//       const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
//       out.push(`<li class="text-base leading-relaxed hover:bg-muted/20 transition-colors rounded px-2">${bold(escape(content))}</li>`);
//       i++; continue;
//     }

//     if (t === '' && inList) {
//       out.push('</ul>');
//       inList = false;
//       i++; continue;
//     }

//     if (t && !t.startsWith('<')) {
//       if (inList) { out.push('</ul>'); inList = false; }
//       out.push(`<p class="my-4 text-base leading-relaxed bg-gradient-to-r from-muted/5 to-transparent p-2 rounded-lg">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
//     }
//     i++;
//   }

//   if (inList) out.push('</ul>');
//   return out.join('\n');
// }

// /** Suggested questions matching backend / agents_test.html Knowledge Q&A + Analytics */
// const SUGGESTED_QUESTIONS = [
//   {
//     group: '🚀 Platform & Getting Started',
//     icon: BookOpen,
//     color: 'text-blue-500',
//     bgColor: 'from-blue-500/10 to-blue-500/5',
//     borderColor: 'border-blue-500/20',
//     options: [
//       'What is this platform?',
//       'How does this platform work?',
//       'How do I run a campaign?',
//       'What is this agent?',
//     ]
//   },
//   {
//     group: '📊 Performance & Analytics',
//     icon: BarChart3,
//     color: 'text-emerald-500',
//     bgColor: 'from-emerald-500/10 to-emerald-500/5',
//     borderColor: 'border-emerald-500/20',
//     options: [
//       'What campaigns are performing best?',
//       'What is our conversion rate?',
//       'How are our campaigns performing this month?',
//       'What is our customer acquisition cost (CAC)?',
//     ]
//   },
//   {
//     group: '🔍 Analysis & Insights',
//     icon: TrendingUp,
//     color: 'text-purple-500',
//     bgColor: 'from-purple-500/10 to-purple-500/5',
//     borderColor: 'border-purple-500/20',
//     options: [
//       'Why are sales dropping?',
//       'What should we focus on to improve performance?',
//       'What are the key trends in our marketing data?',
//       'Which campaigns need optimization?',
//       'What are our top performing campaigns and why?',
//     ]
//   },
//   {
//     group: '🎯 Goals & Targets',
//     icon: Target,
//     color: 'text-amber-500',
//     bgColor: 'from-amber-500/10 to-amber-500/5',
//     borderColor: 'border-amber-500/20',
//     options: [
//       'How many leads have we generated this month?',
//       'What is our lead conversion rate?',
//       'Are we on track to meet our campaign goals?',
//     ]
//   },
//   {
//     group: '💡 Strategy & Recommendations',
//     icon: Lightbulb,
//     color: 'text-rose-500',
//     bgColor: 'from-rose-500/10 to-rose-500/5',
//     borderColor: 'border-rose-500/20',
//     options: [
//       'What marketing strategies should we implement?',
//       'What opportunities are we missing?',
//       'How can we improve our campaign performance?',
//       'What are the best practices for our industry?',
//     ]
//   },
// ];

// const SUGGESTED_GRAPH_QUESTIONS = [
//   { text: 'Show campaigns by status as a pie chart', icon: PieChart, color: 'text-blue-500' },
//   { text: 'Display open rate by campaign as a bar chart', icon: BarChart3, color: 'text-emerald-500' },
//   { text: 'Compare emails sent by campaign', icon: BarChart2, color: 'text-purple-500' },
//   { text: 'Show leads per campaign', icon: TrendingUp, color: 'text-amber-500' },
//   { text: 'Display replies by campaign as a bar chart', icon: Activity, color: 'text-rose-500' },
//   { text: 'Top 5 campaigns by emails sent', icon: Award, color: 'text-indigo-500' },
//   { text: 'Campaigns by status', icon: PieChart, color: 'text-cyan-500' },
//   { text: 'Open rate by campaign', icon: BarChart3, color: 'text-orange-500' },
// ];

// const SUGGESTED_SEARCH_QUESTIONS = [
//   { text: 'What campaigns are performing best?', icon: Award, color: 'text-emerald-500' },
//   // { text: 'What is our overall ROI?', icon: TrendingUp, color: 'text-blue-500' },
//   // { text: 'Which marketing channels are most effective?', icon: BarChart3, color: 'text-purple-500' },
//   { text: 'How are our campaigns performing this month?', icon: Activity, color: 'text-amber-500' },
//   { text: 'What should we focus on to improve performance?', icon: Target, color: 'text-rose-500' },
// ];

// // Chart components
// const SimpleBarChart = ({ data, colors, height = 250, title }) => {
//   if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
//   const maxValue = Math.max(...Object.values(data), 1);
//   const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
//   const chartColors = colors || defaultColors;
//   return (
//     <div className="space-y-3 p-4 rounded-xl bg-gradient-to-b from-muted/5 to-transparent" style={{ minHeight: `${height}px` }}>
//       {title && <h4 className="font-medium text-sm text-muted-foreground mb-4">{title}</h4>}
//       {Object.entries(data).map(([key, value], index) => (
//         <div key={key} className="group">
//           <div className="flex justify-between text-xs mb-1">
//             <span className="text-sm font-medium group-hover:text-primary transition-colors">{key}</span>
//             <span className="font-semibold bg-muted/30 px-2 py-0.5 rounded-full">{value}</span>
//           </div>
//           <div className="w-full bg-muted/30 rounded-full h-2.5 overflow-hidden">
//             <motion.div
//               initial={{ width: 0 }}
//               animate={{ width: `${(value / maxValue) * 100}%` }}
//               transition={{ duration: 0.5, delay: index * 0.1 }}
//               className="h-2.5 rounded-full transition-all relative"
//               style={{
//                 backgroundColor: chartColors[index % chartColors.length],
//               }}
//             >
//               <div className="absolute inset-0 bg-gradient-to-r from-white/20 to-transparent" />
//             </motion.div>
//           </div>
//         </div>
//       ))}
//     </div>
//   );
// };

// const SimplePieChart = ({ data, colors, title }) => {
//   if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
//   const total = Object.values(data).reduce((sum, val) => sum + val, 0);
//   if (total === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
//   const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
//   const chartColors = colors || defaultColors;
//   let currentAngle = 0;
//   const segments = Object.entries(data).map(([key, value], index) => {
//     const angle = (value / total) * 360;
//     const slice = { key, value, percentage: Math.round((value / total) * 100), color: chartColors[index % chartColors.length], angle, startAngle: currentAngle };
//     currentAngle += angle;
//     return slice;
//   });
//   return (
//     <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-gradient-to-b from-muted/5 to-transparent">
//       {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
//       <div className="relative w-48 h-48 sm:w-56 sm:h-56">
//         <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
//           {segments.map((segment, index) => {
//             const x1 = 100 + 100 * Math.cos((segment.startAngle * Math.PI) / 180);
//             const y1 = 100 + 100 * Math.sin((segment.startAngle * Math.PI) / 180);
//             const x2 = 100 + 100 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
//             const y2 = 100 + 100 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);
//             const largeArc = segment.angle > 180 ? 1 : 0;
//             return (
//               <motion.path
//                 key={index}
//                 initial={{ opacity: 0, scale: 0.8 }}
//                 animate={{ opacity: 1, scale: 1 }}
//                 transition={{ duration: 0.3, delay: index * 0.1 }}
//                 d={`M100,100 L${x1},${y1} A100,100 0 ${largeArc},1 ${x2},${y2} Z`}
//                 fill={segment.color}
//                 stroke="#000"
//                 strokeWidth="1"
//                 className="hover:opacity-80 transition-opacity cursor-pointer"
//               />
//             );
//           })}
//         </svg>
//         <div className="absolute inset-0 flex items-center justify-center">
//           <motion.div
//             initial={{ scale: 0 }}
//             animate={{ scale: 1 }}
//             transition={{ type: "spring", stiffness: 200, damping: 15 }}
//             className="text-center bg-background/80 backdrop-blur-sm rounded-full w-16 h-16 flex items-center justify-center shadow-lg"
//           >
//             <div>
//               <div className="text-xl font-bold">{total}</div>
//               <div className="text-[10px] text-muted-foreground">Total</div>
//             </div>
//           </motion.div>
//         </div>
//       </div>
//       <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
//         {segments.map((segment, index) => (
//           <motion.div
//             key={index}
//             initial={{ x: -10, opacity: 0 }}
//             animate={{ x: 0, opacity: 1 }}
//             transition={{ delay: index * 0.05 }}
//             className="flex items-center gap-2 text-xs sm:text-sm p-1.5 rounded-lg hover:bg-muted/30 transition-colors"
//           >
//             <div className="w-3 h-3 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: segment.color }} />
//             <span className="truncate flex-1 font-medium">{segment.key}</span>
//             <span className="font-semibold shrink-0 bg-muted/30 px-1.5 py-0.5 rounded-full text-[10px]">{segment.percentage}%</span>
//           </motion.div>
//         ))}
//       </div>
//     </div>
//   );
// };

// const SimpleLineChart = ({ data, color = '#3b82f6', height = 200, title }) => {
//   if (!data || data.length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
//   const values = data.map(d => d.value ?? d.count ?? 0);
//   const maxValue = Math.max(...values, 1);
//   const labels = data.map(d => d.label ?? d.date ?? d.month ?? '');
//   const points = values.map((value, index) => {
//     const x = (index / (values.length - 1 || 1)) * 100;
//     const y = 100 - (value / maxValue) * 100;
//     return `${x},${y}`;
//   }).join(' ');
//   const areaPoints = `0,100 ${points} 100,100`;
//   return (
//     <div className="space-y-2 p-4 rounded-xl bg-gradient-to-b from-muted/5 to-transparent">
//       {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
//       <div className="relative w-full" style={{ height: `${height}px` }}>
//         <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
//           <motion.polygon
//             initial={{ opacity: 0 }}
//             animate={{ opacity: 0.2 }}
//             transition={{ duration: 0.5 }}
//             points={areaPoints}
//             fill={`${color}20`}
//           />
//           <motion.polyline
//             initial={{ pathLength: 0, opacity: 0 }}
//             animate={{ pathLength: 1, opacity: 1 }}
//             transition={{ duration: 1, ease: "easeInOut" }}
//             points={points}
//             fill="none"
//             stroke={color}
//             strokeWidth="1.5"
//             strokeLinecap="round"
//             strokeLinejoin="round"
//           />
//           {values.map((value, index) => (
//             <motion.circle
//               key={index}
//               initial={{ scale: 0 }}
//               animate={{ scale: 1 }}
//               transition={{ delay: 0.8 + index * 0.1, type: "spring" }}
//               cx={(index / (values.length - 1 || 1)) * 100}
//               cy={100 - (value / maxValue) * 100}
//               r="1.5"
//               fill={color}
//               className="cursor-pointer hover:r-2 transition-all"
//             />
//           ))}
//         </svg>
//         <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-muted-foreground px-1 mt-2">
//           {labels.length <= 7 ? labels.map((label, i) => <span key={i} className="truncate font-medium">{label}</span>) : (
//             <><span className="font-medium">{labels[0]}</span><span className="font-medium">{labels[Math.floor(labels.length / 2)]}</span><span className="font-medium">{labels[labels.length - 1]}</span></>
//           )}
//         </div>
//       </div>
//     </div>
//   );
// };

// const renderChart = (chartData) => {
//   if (!chartData) return null;
//   const { type, data, title, color, colors } = chartData;
//   switch (type) {
//     case 'bar': return <SimpleBarChart data={data} colors={colors} title={title} />;
//     case 'pie': return <SimplePieChart data={data} colors={colors} title={title} />;
//     case 'line': return <SimpleLineChart data={data} color={color} title={title} />;
//     case 'area': return <SimpleLineChart data={data} color={color} title={title} />;
//     default: return <SimpleBarChart data={data} colors={colors} title={title} />;
//   }
// };

// /** Normalize chat to { id, messages: [{ role, content, responseData? }], timestamp } */
// function normalizeChat(c) {
//   if (c.messages && Array.isArray(c.messages)) return c;
//   if (c.question != null) {
//     return {
//       id: c.id,
//       messages: [
//         { role: 'user', content: c.question },
//         { role: 'assistant', content: c.response || '', responseData: c.responseData },
//       ],
//       timestamp: c.timestamp || new Date().toISOString(),
//     };
//   }
//   return { id: c.id || Date.now().toString(), messages: [], timestamp: c.timestamp || new Date().toISOString() };
// }

// function loadChats() {
//   try {
//     const raw = localStorage.getItem(STORAGE_KEY);
//     const list = raw ? JSON.parse(raw) : [];
//     return list.map(normalizeChat);
//   } catch {
//     return [];
//   }
// }

// function saveChats(chats) {
//   try {
//     localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(-50))); // Keep last 50
//   } catch { }
// }

// // Animation variants
// const containerVariants = {
//   hidden: { opacity: 0 },
//   visible: {
//     opacity: 1,
//     transition: {
//       staggerChildren: 0.1
//     }
//   }
// };

// const itemVariants = {
//   hidden: { y: 20, opacity: 0 },
//   visible: {
//     y: 0,
//     opacity: 1,
//     transition: {
//       type: "spring",
//       stiffness: 100,
//       damping: 12
//     }
//   }
// };

// const messageVariants = {
//   hidden: { scale: 0.8, opacity: 0, y: 20 },
//   visible: {
//     scale: 1,
//     opacity: 1,
//     y: 0,
//     transition: {
//       type: "spring",
//       stiffness: 100,
//       damping: 15
//     }
//   },
//   exit: {
//     scale: 0.8,
//     opacity: 0,
//     transition: { duration: 0.2 }
//   }
// };

// const sidebarItemVariants = {
//   hidden: { x: -20, opacity: 0 },
//   visible: {
//     x: 0,
//     opacity: 1,
//     transition: {
//       type: "spring",
//       stiffness: 100,
//       damping: 12
//     }
//   },
//   hover: {
//     scale: 1.02,
//     x: 5,
//     transition: { duration: 0.2 }
//   }
// };

// const MarketingQA = () => {
//   const { toast } = useToast();
//   const [chats, setChats] = useState([]);
//   const [selectedChatId, setSelectedChatId] = useState(null);
//   const [question, setQuestion] = useState('');
//   const [suggestedValue, setSuggestedValue] = useState('__none__');
//   const [loading, setLoading] = useState(false);
//   const [sidebarOpen, setSidebarOpen] = useState(true);
//   const [showSidebarSearch, setShowSidebarSearch] = useState(false);
//   const [sidebarSearch, setSidebarSearch] = useState('');
//   const [showSuggestions, setShowSuggestions] = useState(false);
//   const [inputMode, setInputMode] = useState('search');
//   const [expandedGraph, setExpandedGraph] = useState(null);
//   const [saveModalOpen, setSaveModalOpen] = useState(false);
//   const [saveTitle, setSaveTitle] = useState('');
//   const [saveTags, setSaveTags] = useState('');
//   const [saving, setSaving] = useState(false);
//   const [currentPromptData, setCurrentPromptData] = useState(null);
//   const [comparisonResults, setComparisonResults] = useState([]);

//   const messagesEndRef = useRef(null);
//   const textareaRef = useRef(null);

//   useEffect(() => {
//     setChats(loadChats());
//   }, []);



//   const selectedChat = chats.find((c) => c.id === selectedChatId);
//   const currentMessages = selectedChat?.messages ?? [];

//   const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

//   useEffect(() => {
//     scrollToBottom();
//   }, [currentMessages]);

//   // Load prompt from dashboard when clicking saved graph
//   useEffect(() => {
//     if (window.marketingQALoadPrompt) {
//       const { prompt, chartType } = window.marketingQALoadPrompt;
//       if (prompt) {
//         setQuestion(prompt);
//         setInputMode('graph');
//         textareaRef.current?.focus();
//         // Clear the flag
//         window.marketingQALoadPrompt = null;
//       }
//     }
//   }, []);

//   const fillFromSuggestion = (value) => {
//     const v = value || '__none__';
//     setSuggestedValue(v);
//     if (v !== '__none__') {
//       setQuestion(v);
//       textareaRef.current?.focus();
//     }
//   };

//   // Compare manual query with AI response
//   const compareResponses = async (query, inputMode) => {
//     try {
//       console.log('🔍 Starting comparison for query:', query);

//       // Manual API call
//       let manualResponse;
//       if (inputMode === 'graph') {
//         manualResponse = await marketingAgentService.generateGraph(query);
//       } else {
//         manualResponse = await marketingAgentService.marketingQA(query, []);
//       }

//       console.log('📊 Manual API Response:', manualResponse);

//       // Store comparison result
//       const comparisonData = {
//         query,
//         mode: inputMode,
//         timestamp: new Date().toISOString(),
//         manualResponse,
//         status: manualResponse?.status,
//         success: manualResponse?.status === 'success'
//       };

//       if (inputMode === 'graph') {
//         comparisonData.manualChart = manualResponse?.data?.chart;
//         comparisonData.manualTitle = manualResponse?.data?.title;
//         comparisonData.manualInsights = manualResponse?.data?.insights;
//       } else {
//         comparisonData.manualAnswer = manualResponse?.data?.answer;
//         comparisonData.manualInsights = manualResponse?.data?.insights;
//       }

//       // Add to comparison results
//       setComparisonResults(prev => [comparisonData, ...prev].slice(0, 20)); // Keep last 20

//       console.log('✅ Comparison Result:', comparisonData);
//       console.log('📈 All Comparisons:', [comparisonData, ...comparisonResults]);

//       return comparisonData;
//     } catch (error) {
//       const errorData = {
//         query,
//         mode: inputMode,
//         timestamp: new Date().toISOString(),
//         error: error?.message,
//         status: 'error',
//         success: false
//       };

//       console.error('❌ Comparison Error:', errorData);
//       setComparisonResults(prev => [errorData, ...prev].slice(0, 20));

//       return errorData;
//     }
//   };

//   const handleSubmit = async (e) => {
//     e.preventDefault();
//     if (!question.trim()) {
//       toast({
//         title: 'Error',
//         description: 'Please enter a question.',
//         variant: 'destructive'
//       });
//       return;
//     }

//     const q = question.trim();

//     // Check for special cases (only for search mode)
//     if (inputMode === 'search') {
//       if (isGreetingOrSmallTalk(q)) {
//         const response = {
//           answer: "👋 Hi there! I'm your Marketing Q&A Assistant. I can help you with:\n\n• **Campaign performance** metrics and insights\n• **ROI analysis** and optimization suggestions\n• **Lead generation** and conversion rates\n• **Channel effectiveness** comparisons\n• **Strategic recommendations** for improvement\n\nWhat would you like to know about your marketing data?",
//           insights: [],
//         };
//         const responseText = response.answer;
//         const userMsg = { role: 'user', content: q };
//         const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
//         handleResponse(q, userMsg, assistantMsg, response);
//         return;
//       }

//       if (isMetaQuestion(q)) {
//         const response = {
//           answer: "You can ask me about:\n\n**📈 Performance Metrics**\n• Campaign ROI, conversion rates, CAC\n• Channel effectiveness, lead generation\n\n**🔍 Analysis**\n• Why sales are dropping/rising\n• Which campaigns need optimization\n• Trends in your marketing data\n\n**💡 Recommendations**\n• Marketing strategies to implement\n• Opportunities you might be missing\n• Best practices for your industry\n\nPick a suggested question above or type your own!",
//           insights: [],
//         };
//         const responseText = response.answer;
//         const userMsg = { role: 'user', content: q };
//         const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
//         handleResponse(q, userMsg, assistantMsg, response);
//         return;
//       }
//     }

//     // Actual API call
//     try {
//       setLoading(true);

//       // Send last 6 Q&A pairs for context
//       const pairs = [];
//       const messages = currentMessages || [];
//       for (let i = 0; i < messages.length - 1; i++) {
//         if (messages[i].role === 'user' && messages[i + 1].role === 'assistant') {
//           const answer = messages[i + 1].responseData?.answer ?? messages[i + 1].content ?? '';
//           pairs.push({ question: messages[i].content, answer });
//         }
//       }
//       const conversationHistory = pairs.slice(-6);
//       const reducedConversationHistory = pairs.slice(-2);

//       let result;

//       if (inputMode === 'graph') {
//         // Call graph generation API
//         result = await marketingAgentService.generateGraph(q);
//       } else {
//         // Call QA API
//         result = await marketingAgentService.marketingQA(q, reducedConversationHistory);
//       }

//       if (result.status === 'success' && result.data) {
//         const response = result.data;

//         if (inputMode === 'graph') {
//           // Handle graph response
//           const userMsg = { role: 'user', content: q };
//           const assistantMsg = {
//             role: 'assistant',
//             content: q,
//             responseData: {
//               isGraph: true,
//               chart: response.chart,
//               chartTitle: response.title || 'Chart',
//               chartType: response.type,
//               insights: response.insights || []
//             }
//           };
//           handleResponse(q, userMsg, assistantMsg, response);
//         } else {
//           // Handle QA response
//           const answer = response.answer || 'No answer provided.';
//           const insights = response.insights || [];

//           let responseText = answer;
//           if (insights.length > 0) {
//             responseText += '\n\n**Key Insights & Metrics**\n';
//             insights.forEach((i) => {
//               responseText += `• **${i.title || 'N/A'}**: ${i.value || 'N/A'}\n`;
//             });
//           }

//           const userMsg = { role: 'user', content: q };
//           const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
//           handleResponse(q, userMsg, assistantMsg, response);
//         }
//       } else {
//         throw new Error(result.message || 'Failed to get response');
//       }

//       // Run comparison in background (no await - non-blocking)
//       compareResponses(q, inputMode).catch(err => console.error('Comparison failed:', err));
//     } catch (error) {
//       toast({
//         title: 'Warning',
//         description: 'Please try again.',
//         variant: 'default'
//       });
//     } finally {
//       setLoading(false);
//     }
//   };


//   const handleResponse = (q, userMsg, assistantMsg, response) => {
//     const now = new Date().toISOString();

//     if (selectedChatId) {
//       const chat = chats.find((c) => c.id === selectedChatId);
//       if (chat) {
//         const updatedChat = {
//           ...chat,
//           messages: [...(chat.messages || []), userMsg, assistantMsg],
//           timestamp: now,
//         };
//         const updated = chats.map((c) => (c.id === selectedChatId ? updatedChat : c));
//         setChats(updated);
//         saveChats(updated);
//       } else {
//         createNewChat(q, response, userMsg, assistantMsg, now);
//       }
//     } else {
//       createNewChat(q, response, userMsg, assistantMsg, now);
//     }

//     setQuestion('');
//     setSuggestedValue('__none__');
//     textareaRef.current?.focus();
//   };

//   const createNewChat = (q, response, userMsg, assistantMsg, now) => {
//     const newChat = {
//       id: Date.now().toString(),
//       messages: [userMsg, assistantMsg],
//       timestamp: now,
//     };
//     const updated = [newChat, ...chats];
//     setChats(updated);
//     saveChats(updated);
//     setSelectedChatId(newChat.id);
//   };

//   const newChat = () => {
//     setSelectedChatId(null);
//     setQuestion('');
//     setSuggestedValue('__none__');
//     textareaRef.current?.focus();
//   };

//   const deleteChat = (e, chatId) => {
//     e.stopPropagation();
//     const updated = chats.filter((c) => c.id !== chatId);
//     setChats(updated);
//     saveChats(updated);
//     if (selectedChatId === chatId) setSelectedChatId(null);
//     toast({
//       title: 'Deleted',
//       description: 'Conversation removed.'
//     });
//   };

//   const openSaveModal = (prompt, chartTitle, chartType, chart = null, insights = []) => {
//     setCurrentPromptData({ prompt, chartTitle, chartType, chart, insights });
//     setSaveTitle(chartTitle || '');
//     setSaveTags('');
//     setSaveModalOpen(true);
//   };

//   const handleSavePrompt = async () => {
//     if (!saveTitle.trim()) {
//       toast({
//         title: 'Error',
//         description: 'Please enter a title',
//         variant: 'destructive'
//       });
//       return;
//     }

//     try {
//       setSaving(true);
//       const promptData = {
//         title: saveTitle,
//         prompt: currentPromptData.prompt,
//         tags: saveTags.split(',').map(t => t.trim()).filter(t => t),
//         chart_type: currentPromptData.chartType,
//         chart_data: currentPromptData.chart || null,
//         insights: currentPromptData.insights || []
//       };

//       const saved = await marketingAgentService.saveGraphPrompt(promptData);

//       try {
//         const savedId = saved?.data?.id;
//         if (savedId && currentPromptData?.chart) {
//           const cacheKey = 'marketing_saved_graph_payloads';
//           const cached = JSON.parse(localStorage.getItem(cacheKey) || '{}');
//           cached[String(savedId)] = {
//             chart: currentPromptData.chart,
//             title: saveTitle || currentPromptData.chartTitle || 'Saved Graph',
//             insights: currentPromptData.insights || [],
//             prompt: currentPromptData.prompt,
//           };
//           localStorage.setItem(cacheKey, JSON.stringify(cached));
//         }
//       } catch { }

//       toast({
//         title: 'Success',
//         description: 'Prompt saved successfully'
//       });
//       setSaveModalOpen(false);
//       setSaveTitle('');
//       setSaveTags('');
//       setCurrentPromptData(null);
//     } catch (error) {
//       console.error('Save prompt error:', error);
//       toast({
//         title: 'Error',
//         description: error?.response?.data?.message || 'Failed to save prompt',
//         variant: 'destructive'
//       });
//     } finally {
//       setSaving(false);
//     }
//   };

//   const handleAddToDashboard = async (prompt, chartTitle, chartType, chart = null, insights = []) => {
//     try {
//       // First save the prompt
//       const promptData = {
//         title: chartTitle || 'Untitled Chart',
//         prompt: prompt,
//         tags: ['dashboard'],
//         chart_type: chartType,
//         chart_data: chart,
//         insights: insights || []
//       };

//       await marketingAgentService.saveGraphPrompt(promptData);

//       toast({
//         title: 'Success',
//         description: 'Chart added to dashboard'
//       });
//     } catch (error) {
//       console.error('Add to dashboard error:', error);
//       toast({
//         title: 'Error',
//         description: error?.response?.data?.message || 'Failed to add to dashboard',
//         variant: 'destructive'
//       });
//     }
//   };

//   // Expose comparison results to window for debugging
//   useEffect(() => {
//     window.marketingQAComparison = {
//       getComparisons: () => comparisonResults,
//       getLatestComparison: () => comparisonResults[0],
//       compareNow: (query, mode = 'search') => compareResponses(query, mode),
//       getAllComparisonStatus: () => ({
//         total: comparisonResults.length,
//         successful: comparisonResults.filter(c => c.success).length,
//         failed: comparisonResults.filter(c => !c.success).length,
//         byMode: {
//           search: comparisonResults.filter(c => c.mode === 'search').length,
//           graph: comparisonResults.filter(c => c.mode === 'graph').length
//         }
//       })
//     };

//     console.log('🎯 Marketing QA Comparison Tool Available');
//     console.log('Usage: window.marketingQAComparison.getComparisons()');

//     return () => {
//       delete window.marketingQAComparison;
//     };
//   }, [comparisonResults]);

//   const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');

//   const formatDate = (iso) => {
//     try {
//       const d = new Date(iso);
//       const now = new Date();
//       const diff = now - d;

//       if (diff < 86400000) { // Less than 24 hours
//         return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
//       } else if (diff < 604800000) { // Less than 7 days
//         return d.toLocaleDateString(undefined, { weekday: 'short' });
//       } else {
//         return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
//       }
//     } catch {
//       return '';
//     }
//   };

//   return (
//     <motion.div
//       className={cn('h-full min-h-0 flex', sidebarOpen ? 'gap-2' : 'gap-0')}
//       variants={containerVariants}
//       initial="hidden"
//       animate="visible"
//     >
//       {/* Sidebar - Previous chats */}
//       <motion.div
//         variants={itemVariants}
//         className={cn(
//           'shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_rgba(80,36,180,0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out',
//           sidebarOpen ? 'w-64 opacity-100 mr-2' : 'w-0 opacity-0 border-0 mr-0'
//         )}
//         style={{
//           minWidth: sidebarOpen ? '16rem' : '0',
//           background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, rgba(36,18,54,0.18) 18%, #0a0a0f 55%, #0a0a0f 100%)',
//           borderRight: '1.5px solid rgba(255,255,255,0.10)',
//           boxShadow: '0 2px 24px 0 rgba(80, 36, 180, 0.18), 0 0 0 1.5px rgba(120, 80, 255, 0.10) inset',
//           borderTopLeftRadius: 16,
//           borderBottomLeftRadius: 16,
//           backdropFilter: 'blur(12px)',
//           WebkitBackdropFilter: 'blur(12px)',
//         }}
//       >
//         <div className={cn('w-64 h-full flex flex-col', !sidebarOpen && 'pointer-events-none')}>
//           <div
//             className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2"
//             style={{
//               background: 'linear-gradient(180deg, rgba(60, 30, 90, 0.22) 0%, rgba(36, 18, 54, 0.85) 100%)',
//               borderTopLeftRadius: 16,
//             }}
//           >
//             <div className="flex items-center justify-between mb-1">
//               <span className="text-base font-semibold text-white/90 tracking-wide">Payper Project</span>
//               <button
//                 onClick={() => setSidebarOpen(false)}
//                 title="Close sidebar"
//                 className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
//                 style={{ boxShadow: '0 0 0 2px rgba(139,92,246,0.10) inset' }}
//               >
//                 <ChevronLeft className="h-4 w-4 text-white/80" />
//               </button>
//             </div>

//             {showSidebarSearch ? (
//               <div
//                 className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
//                 style={{
//                   border: '1.5px solid rgba(139,92,246,0.22)',
//                   background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
//                   boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
//                 }}
//               >
//                 <input
//                   autoFocus
//                   value={sidebarSearch}
//                   onChange={(e) => setSidebarSearch(e.target.value)}
//                   placeholder="Search conversations..."
//                   className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
//                   style={{ minWidth: 0 }}
//                 />
//                 <button
//                   title="Close search"
//                   onClick={() => {
//                     setSidebarSearch('');
//                     setShowSidebarSearch(false);
//                   }}
//                   className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
//                 >
//                   <X className="h-4 w-4 text-white/70" />
//                 </button>
//               </div>
//             ) : (
//               <div
//                 className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
//                 style={{
//                   border: '1.5px solid rgba(139,92,246,0.22)',
//                   background: 'linear-gradient(90deg, rgba(80,36,180,0.10) 0%, rgba(36,18,54,0.18) 100%)',
//                   boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
//                 }}
//               >
//                 <span className="text-sm font-medium text-white/80 flex-1">Conversation</span>
//                 <button
//                   title="Search"
//                   onClick={() => setShowSidebarSearch(true)}
//                   className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
//                 >
//                   <Search className="h-4 w-4 text-white/70" />
//                 </button>
//                 <button
//                   onClick={newChat}
//                   title="New chat"
//                   className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
//                 >
//                   <Plus className="h-4 w-4 text-white/80" />
//                 </button>
//               </div>
//             )}
//           </div>

//           <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin scrollbar-thumb-violet-500/30 scrollbar-track-transparent">
//             {chats.length === 0 ? (
//               <div className="p-4 text-center text-sm text-muted-foreground">
//                 No conversations yet. Ask a question to start.
//               </div>
//             ) : (
//               <div
//                 className="p-2 space-y-1"
//                 style={{
//                   background: 'linear-gradient(180deg, rgba(36, 18, 54, 0.10) 0%, rgba(24, 18, 43, 0.18) 100%)',
//                   borderRadius: 12,
//                 }}
//               >
//                 <AnimatePresence>
//                   {(() => {
//                     const searchTerm = sidebarSearch.trim().toLowerCase();
//                     const sortedChats = [...chats].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
//                     const filteredChats = searchTerm
//                       ? sortedChats.filter((c) => {
//                         const title = (c.messages?.find((m) => m.role === 'user')?.content || '').toLowerCase();
//                         const messagesMatch = (c.messages || []).some((m) => (m.content || '').toLowerCase().includes(searchTerm));
//                         return title.includes(searchTerm) || messagesMatch;
//                       })
//                       : sortedChats;

//                     if (searchTerm && filteredChats.length === 0) {
//                       return (
//                         <div className="p-4 text-center text-sm text-muted-foreground">
//                           No matching conversations found.
//                         </div>
//                       );
//                     }

//                     return filteredChats.map((c, index) => {
//                       const firstQuestion = c.messages?.find((m) => m.role === 'user')?.content || 'New chat';
//                       return (
//                         <motion.div
//                           key={c.id}
//                           variants={sidebarItemVariants}
//                           initial="hidden"
//                           animate="visible"
//                           exit={{ x: -20, opacity: 0 }}
//                           whileHover="hover"
//                           transition={{ delay: index * 0.04 }}
//                           className={cn(
//                             'group flex items-center gap-1 rounded-lg border text-sm transition-all duration-200',
//                             selectedChatId === c.id
//                               ? 'border-violet-500/60 bg-gradient-to-r from-violet-900/40 to-violet-700/20 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
//                               : 'border-white/10 bg-white/2 hover:bg-white/5 hover:border-violet-400/20'
//                           )}
//                           style={{
//                             boxShadow: selectedChatId === c.id
//                               ? '0 0 12px 0 rgba(139,92,246,0.18), 0 1.5px 0 0 rgba(120,80,255,0.10) inset'
//                               : '0 1px 2px 0 rgba(36,18,54,0.08) inset',
//                             borderWidth: 1.5,
//                           }}
//                         >
//                           <button
//                             type="button"
//                             onClick={() => setSelectedChatId(c.id)}
//                             className="flex-1 min-w-0 text-left p-3 rounded-lg"
//                           >
//                             <div className={cn('font-medium truncate', selectedChatId === c.id ? 'text-violet-300' : 'text-white/90')}>
//                               {truncate(firstQuestion, 40)}
//                             </div>
//                             <div className={cn('text-xs mt-0.5', selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground')}>
//                               {formatDate(c.timestamp)}
//                             </div>
//                           </button>
//                           <Button
//                             type="button"
//                             variant="ghost"
//                             size="icon"
//                             className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
//                             onClick={(e) => deleteChat(e, c.id)}
//                             title="Delete chat"
//                           >
//                             <X className="h-4 w-4" />
//                           </Button>
//                         </motion.div>
//                       );
//                     });
//                   })()}
//                 </AnimatePresence>
//               </div>
//             )}
//           </div>
//         </div>
//       </motion.div>

//       {/* Main chat area */}
//       <motion.div
//         variants={itemVariants}
//         className="flex-1 min-w-0 min-h-0"
//       >
//         <Card className="h-full flex flex-col overflow-hidden border-0 shadow-xl rounded-2xl bg-gradient-to-b from-background to-muted/10">
//           {/* Header */}
//           <CardHeader className="shrink-0 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent border-b pb-3 rounded-t-2xl">
//             <div className="flex items-center justify-between">
//               <div className="flex items-center gap-3">
//                 <motion.div
//                   whileHover={{ rotate: 360, scale: 1.1 }}
//                   transition={{ duration: 0.5 }}
//                   className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 shadow-md"
//                 >
//                   <Bot className="h-5 w-5 text-primary" />
//                 </motion.div>
//                 <div>
//                   <CardTitle className="flex items-center gap-2">
//                     Marketing Q&A Assistant
//                     <Badge variant="outline" className="bg-gradient-to-r from-primary/20 to-primary/5 gap-1 rounded-full border-primary/30">
//                       <Zap className="h-3 w-3 text-primary" />
//                       AI-Powered
//                     </Badge>
//                   </CardTitle>
//                   <CardDescription>
//                     Ask anything about your campaigns, performance, and marketing data
//                   </CardDescription>
//                 </div>
//               </div>
//               <div className="flex items-center gap-2">
//                 {selectedChat && (
//                   <Badge variant="secondary" className="gap-1 rounded-full bg-gradient-to-r from-muted to-muted/50">
//                     <MessageSquare className="h-3 w-3" />
//                     {currentMessages.filter(m => m.role === 'user').length} questions
//                   </Badge>
//                 )}
//                 <Button
//                   variant={sidebarOpen ? 'ghost' : 'outline'}
//                   size="sm"
//                   onClick={() => setSidebarOpen((v) => !v)}
//                   title={sidebarOpen ? 'Hide chat history' : 'Show chat history'}
//                   className={cn(
//                     'gap-1.5 transition-all duration-200',
//                     !sidebarOpen
//                       ? 'bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary'
//                       : 'hover:bg-muted'
//                   )}
//                 >
//                   {sidebarOpen ? (
//                     <>
//                       <ChevronLeft className="h-4 w-4" />
//                       <span className="text-xs hidden sm:inline">Hide</span>
//                     </>
//                   ) : (
//                     <>
//                       <ChevronRight className="h-4 w-4" />
//                       <span className="text-xs hidden sm:inline">History</span>
//                     </>
//                   )}
//                 </Button>
//               </div>
//             </div>
//           </CardHeader>

//           {/* Messages area */}
//           <CardContent className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent bg-gradient-to-b from-background via-background to-muted/10">
//             <AnimatePresence mode="popLayout">
//               {!selectedChatId ? (
//                 <motion.div
//                   key="welcome"
//                   variants={messageVariants}
//                   initial="hidden"
//                   animate="visible"
//                   exit="hidden"
//                   className="flex flex-col items-center justify-center h-full text-center"
//                 >
//                   <motion.div
//                     animate={{
//                       scale: [1, 1.1, 1],
//                       rotate: [0, 5, -5, 0]
//                     }}
//                     transition={{
//                       duration: 2,
//                       repeat: Infinity,
//                       repeatType: "reverse"
//                     }}
//                   >
//                     <div className="relative">
//                       <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full" />
//                       <Bot className="h-20 w-20 text-primary/40 relative z-10" />
//                     </div>
//                   </motion.div>
//                   <h3 className="text-xl font-semibold mb-2 bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Welcome to Marketing Q&A</h3>
//                   <p className="text-muted-foreground max-w-md mb-6">
//                     Ask me about campaign performance, ROI, conversion rates, and get data-driven insights
//                   </p>

//                   <div className="grid grid-cols-2 gap-3 max-w-lg">
//                     {[
//                       { icon: BarChart3, label: 'Campaign ROI', color: 'from-emerald-500/20 to-emerald-500/5' },
//                       { icon: Target, label: 'Conversion Rates', color: 'from-purple-500/20 to-purple-500/5' },
//                       { icon: TrendingUp, label: 'Channel Analysis', color: 'from-amber-500/20 to-amber-500/5' },
//                       { icon: Lightbulb, label: 'Recommendations', color: 'from-rose-500/20 to-rose-500/5' }
//                     ].map((item, i) => (
//                       <motion.div
//                         key={i}
//                         whileHover={{ scale: 1.05, y: -2 }}
//                         className={cn(
//                           "flex items-center gap-2 p-3 rounded-xl bg-gradient-to-r border shadow-sm",
//                           item.color
//                         )}
//                       >
//                         <item.icon className={cn("h-4 w-4", item.color.replace('/20', ''))} />
//                         <span className="text-sm font-medium">{item.label}</span>
//                       </motion.div>
//                     ))}
//                   </div>
//                 </motion.div>
//               ) : (
//                 <div className="space-y-4">
//                   <AnimatePresence>
//                     {currentMessages.map((msg, i) => (
//                       <motion.div
//                         key={i}
//                         variants={messageVariants}
//                         initial="hidden"
//                         animate="visible"
//                         exit="exit"
//                         className={cn(
//                           "flex",
//                           msg.role === 'user' ? 'justify-end' : 'justify-start'
//                         )}
//                       >
//                         <div className={cn(
//                           "max-w-[85%] rounded-2xl overflow-hidden shadow-md",
//                           msg.role === 'user'
//                             ? 'bg-gradient-to-r from-primary to-primary/90 text-primary-foreground'
//                             : 'bg-gradient-to-r from-muted/80 to-muted/40 border shadow-sm'
//                         )}>
//                           {msg.role === 'user' ? (
//                             <div className="px-4 py-3">
//                               <div className="flex items-center gap-2 mb-1">
//                                 <User className="h-3 w-3 opacity-70" />
//                                 <span className="text-xs opacity-70">You</span>
//                               </div>
//                               <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
//                             </div>
//                           ) : (
//                             <div className="px-5 py-4">
//                               <div className="flex items-center gap-2 mb-3">
//                                 <div className="rounded-full bg-primary/20 p-1">
//                                   <Bot className="h-3 w-3 text-primary" />
//                                 </div>
//                                 <span className="text-xs font-medium">Marketing Assistant</span>
//                                 {msg.responseData?.research_id && (
//                                   <Badge variant="outline" className="text-[10px] h-4 rounded-full bg-primary/10 border-primary/20">
//                                     ID: {msg.responseData.research_id.slice(0, 6)}
//                                   </Badge>
//                                 )}
//                               </div>

//                               {msg.responseData?.isGraph ? (
//                                 <>
//                                   <div className="space-y-3">
//                                     {msg.responseData.chart && (
//                                       <div className="relative w-full rounded-xl border border-border bg-gradient-to-b from-card to-muted/30 p-3 shadow-sm">
//                                         <Button
//                                           type="button"
//                                           variant="ghost"
//                                           size="icon"
//                                           className="absolute top-2 right-2 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground bg-background/50 backdrop-blur-sm"
//                                           onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
//                                           title="Expand graph"
//                                         >
//                                           <Maximize2 className="h-3.5 w-3.5" />
//                                         </Button>
//                                         <div className="pr-8">
//                                           {renderChart(msg.responseData.chart)}
//                                         </div>
//                                       </div>
//                                     )}
//                                     {Array.isArray(msg.responseData.insights) && msg.responseData.insights.length > 0 && (
//                                       <div className="pt-2 border-t border-border/50">
//                                         <p className="text-xs font-semibold mb-2 flex items-center gap-1">
//                                           <Sparkles className="h-3 w-3 text-amber-500" />
//                                           Insights
//                                         </p>
//                                         <table className="w-full text-xs">
//                                           <tbody>
//                                             {msg.responseData.insights.map((insight, j) => (
//                                               <tr key={j} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
//                                                 <td className="py-1 pr-2 font-medium">{insight.title || 'N/A'}</td>
//                                                 <td className="py-1 text-muted-foreground">{insight.value || 'N/A'}</td>
//                                               </tr>
//                                             ))}
//                                           </tbody>
//                                         </table>
//                                       </div>
//                                     )}
//                                     <div className="flex flex-wrap gap-2 pt-2">
//                                       <Button
//                                         type="button"
//                                         variant="outline"
//                                         className="rounded-xl text-xs gap-1 bg-background/50 backdrop-blur-sm hover:bg-primary/10 hover:text-primary transition-all"
//                                         size="sm"
//                                         onClick={() => openSaveModal(
//                                           currentMessages[currentMessages.indexOf(msg) - 1]?.content,
//                                           msg.responseData.chartTitle,
//                                           msg.responseData.chartType,
//                                           msg.responseData.chart,
//                                           msg.responseData.insights
//                                         )}
//                                       >
//                                         <Save className="h-3.5 w-3.5" />
//                                         Save Prompt
//                                       </Button>
//                                       <Button
//                                         type="button"
//                                         size="sm"
//                                         onClick={() => handleAddToDashboard(
//                                           currentMessages[currentMessages.indexOf(msg) - 1]?.content,
//                                           msg.responseData.chartTitle,
//                                           msg.responseData.chartType,
//                                           msg.responseData.chart,
//                                           msg.responseData.insights
//                                         )}
//                                         className="rounded-xl bg-gradient-to-r from-primary to-primary/80 text-primary-foreground text-xs gap-1 hover:from-primary/90 hover:to-primary/70 transition-all"
//                                       >
//                                         <LayoutDashboard className="h-3.5 w-3.5" />
//                                         Add to dashboard
//                                       </Button>
//                                     </div>
//                                   </div>
//                                 </>
//                               ) : (
//                                 <>
//                                   <div
//                                     className="prose prose-base max-w-none dark:prose-invert [&_h2]:text-primary [&_strong]:font-semibold"
//                                     dangerouslySetInnerHTML={{
//                                       __html: markdownToHtml(msg.responseData?.answer || msg.content)
//                                     }}
//                                   />

//                                   {msg.responseData?.insights?.length > 0 && (
//                                     <motion.div
//                                       initial={{ opacity: 0, y: 10 }}
//                                       animate={{ opacity: 1, y: 0 }}
//                                       className="mt-4 pt-4 border-t border-border/50"
//                                     >
//                                       <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
//                                         <Sparkles className="h-4 w-4 text-amber-500" />
//                                         Key Insights
//                                       </h4>
//                                       <div className="grid grid-cols-2 gap-2">
//                                         {msg.responseData.insights.map((insight, j) => (
//                                           <motion.div
//                                             key={j}
//                                             initial={{ scale: 0.9, opacity: 0 }}
//                                             animate={{ scale: 1, opacity: 1 }}
//                                             transition={{ delay: j * 0.1 }}
//                                             className="rounded-xl bg-gradient-to-br from-muted/50 to-muted/30 p-3 border shadow-sm hover:shadow-md transition-all"
//                                           >
//                                             <p className="text-xs font-medium text-muted-foreground mb-1">
//                                               {insight.title || 'Metric'}
//                                             </p>
//                                             <p className="text-sm font-semibold">
//                                               {insight.value || 'N/A'}
//                                             </p>
//                                           </motion.div>
//                                         ))}
//                                       </div>
//                                     </motion.div>
//                                   )}
//                                 </>
//                               )}
//                             </div>
//                           )}
//                         </div>
//                       </motion.div>
//                     ))}
//                   </AnimatePresence>

//                   {loading && (
//                     <motion.div
//                       initial={{ opacity: 0, y: 10 }}
//                       animate={{ opacity: 1, y: 0 }}
//                       className="flex justify-start"
//                     >
//                       <div className="bg-gradient-to-r from-muted to-muted/50 border rounded-2xl px-4 py-3 flex items-center gap-3 shadow-md">
//                         <motion.div
//                           animate={{ rotate: 360 }}
//                           transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
//                         >
//                           <Loader2 className="h-4 w-4 text-primary" />
//                         </motion.div>
//                         <span className="text-sm">Analyzing your data...</span>
//                       </div>
//                     </motion.div>
//                   )}

//                   <div ref={messagesEndRef} />
//                 </div>
//               )}
//             </AnimatePresence>
//           </CardContent>

//           {/* Input form */}
//           <div className="shrink-0   p-4 rounded-b-2xl">
//             <form onSubmit={handleSubmit} className="space-y-3">
//               <div className="relative">
//                 <div
//                   className="absolute inset-0 rounded-[28px] pointer-events-none"
//                   style={{
//                     // background: 'linear-gradient(90deg, transparent 60%, rgba(10,37,64,0.38) 90%, rgba(14,39,71,0.22) 100%)',
//                   }}
//                 />
//                 <div
//                   className="relative z-[1] rounded-[28px] px-2.5 py-2.5 space-y-3"
//                   style={{
//                     background: '#0a0a0f',
//                     border: '1.5px solid rgba(255,255,255,0.08)',
//                     boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
//                   }}
//                 >
//                   <div className="flex gap-2.5 items-center">
//                     <Select value={inputMode} onValueChange={setInputMode}>
//                       <SelectTrigger
//                         className="h-11 w-[145px] shrink-0 rounded-full text-sm font-medium focus:ring-0 focus:ring-offset-0 transition-all duration-200 px-4 gap-2 [&>svg]:opacity-70"
//                         style={{
//                           background: '#111118',
//                           border: '1.5px solid rgba(139, 92, 246, 0.55)',
//                           boxShadow: '0 0 16px rgba(139, 92, 246, 0.2), 0 0 4px rgba(139, 92, 246, 0.15)',
//                           color: '#e2e2f0',
//                         }}
//                       >
//                         {inputMode === 'search' ? (
//                           <>
//                             <Search className="h-4 w-4" style={{ color: '#a78bfa' }} />
//                             <span>Search</span>
//                           </>
//                         ) : (
//                           <>
//                             <BarChart2 className="h-4 w-4" style={{ color: '#a78bfa' }} />
//                             <span>Graph</span>
//                           </>
//                         )}
//                       </SelectTrigger>
//                       <SelectContent
//                         className="rounded-xl"
//                         style={{
//                           background: '#161630',
//                           border: '1px solid rgba(139, 92, 246, 0.25)',
//                           color: '#e2e2f0',
//                         }}
//                       >
//                         <SelectItem value="search" className="rounded-lg focus:bg-violet-600/20 focus:text-white">
//                           <div className="flex items-center gap-2">
//                             <Search className="h-4 w-4" />
//                             <span>Search QA</span>
//                           </div>
//                         </SelectItem>
//                         <SelectItem value="graph" className="rounded-lg focus:bg-violet-600/20 focus:text-white">
//                           <div className="flex items-center gap-2">
//                             <BarChart2 className="h-4 w-4" />
//                             <span>Generate Graph</span>
//                           </div>
//                         </SelectItem>
//                       </SelectContent>
//                     </Select>
//                     <div
//                       className="flex-1 min-w-0 rounded-full flex items-center overflow-hidden"
//                       style={{
//                         background: '#0e0e14',
//                         boxShadow: 'inset 2px 0 8px -2px rgba(139,92,246,0.35)',
//                         border: '1px solid rgba(255, 255, 255, 0.1)',
//                         borderLeftColor: 'rgba(139, 92, 246, 0.45)',
//                       }}
//                     >
//                       <Textarea
//                         ref={textareaRef}
//                         placeholder={inputMode === 'search' ? 'Ask about campaign performance, ROI, channels...' : 'Describe the chart you want...'}
//                         value={question}
//                         onChange={(e) => {
//                           setQuestion(e.target.value);
//                           setSuggestedValue('__none__');
//                         }}
//                         onKeyDown={(e) => {
//                           if (e.key === 'Enter' && !e.shiftKey) {
//                             e.preventDefault();
//                             handleSubmit(e);
//                           }
//                         }}
//                         rows={1}
//                         disabled={loading}
//                         className="flex-1 w-full min-h-[44px] h-11 max-h-32 resize-none border-0 bg-transparent text-sm py-3 px-4 text-white placeholder:text-white/30 focus-visible:ring-0 focus-visible:ring-offset-0"
//                       />
//                     </div>
//                     <motion.div
//                       whileHover={{ scale: 1.05 }}
//                       whileTap={{ scale: 0.95 }}
//                     >
//                       <Button
//                         type="submit"
//                         disabled={loading || !question.trim()}
//                         size="icon"
//                         className="h-11 w-11 shrink-0 rounded-full border-0 transition-all duration-200"
//                         style={{
//                           background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #5b21b6 100%)',
//                           boxShadow: '0 0 16px rgba(124, 58, 237, 0.35), 0 2px 8px rgba(0,0,0,0.3)',
//                           color: '#ffffff',
//                         }}
//                       >
//                         {loading ? (
//                           <Loader2 className="h-5 w-5 animate-spin" />
//                         ) : (
//                           <Send className="h-5 w-5" />
//                         )}
//                       </Button>
//                     </motion.div>
//                   </div>
//                   {/* Suggested questions */}
//                   <div className="space-y-3 w-full pt-1">
//                     <div className="flex items-center justify-between">
//                       <span className="text-xs text-white/80 font-medium flex items-center gap-1">
//                         <Sparkles className="h-3 w-3" style={{ color: '#a78bfa' }} />
//                         Try these examples
//                       </span>
//                       <Button
//                         type="button"
//                         variant="ghost"
//                         size="sm"
//                         onClick={() => setShowSuggestions(!showSuggestions)}
//                         className="h-7 w-7 p-0 rounded-full transition-all text-white/70 hover:text-white"
//                         style={{
//                           background: 'rgba(17,17,24,0.8)',
//                           border: '1px solid rgba(139, 92, 246, 0.30)',
//                           boxShadow: '0 0 12px rgba(139, 92, 246, 0.15)',
//                         }}
//                         title={showSuggestions ? 'Hide suggestions' : 'Show suggestions'}
//                       >
//                         {showSuggestions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
//                       </Button>
//                     </div>

//                     <AnimatePresence>
//                       {showSuggestions && (
//                         <motion.div
//                           initial={{ opacity: 0, height: 0 }}
//                           animate={{ opacity: 1, height: 'auto' }}
//                           exit={{ opacity: 0, height: 0 }}
//                           transition={{ duration: 0.2 }}
//                           className="overflow-hidden"
//                         >
//                           <div className="flex flex-wrap gap-2">
//                             {(inputMode === 'graph' ? SUGGESTED_GRAPH_QUESTIONS : SUGGESTED_SEARCH_QUESTIONS).map((item, index) => (
//                               <motion.button
//                                 key={item.text}
//                                 type="button"
//                                 initial={{ scale: 0.9, opacity: 0 }}
//                                 animate={{ scale: 1, opacity: 1 }}
//                                 transition={{ delay: index * 0.05 }}
//                                 whileHover={{ scale: 1.05, y: -2 }}
//                                 whileTap={{ scale: 0.95 }}
//                                 onClick={() => setQuestion(item.text)}
//                                 className={cn(
//                                   "text-xs text-white/90 rounded-xl px-3 py-1.5 text-left transition-all shadow-sm hover:shadow-md flex items-center gap-1.5 border",
//                                   item.color
//                                 )}
//                                 style={{
//                                   background: 'rgba(255,255,255,0.05)',
//                                   borderColor: 'rgba(255,255,255,0.10)',
//                                 }}
//                               >
//                                 <item.icon className={cn("h-3 w-3", item.color)} />
//                                 {item.text}
//                               </motion.button>
//                             ))}
//                           </div>
//                         </motion.div>
//                       )}
//                     </AnimatePresence>
//                   </div>
//                 </div>
//               </div>


//               {/* Quick action chips */}
//               {!selectedChatId && showSuggestions && (
//                 <motion.div
//                   initial={{ opacity: 0 }}
//                   animate={{ opacity: 1 }}
//                   className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2"
//                 >
//                   {SUGGESTED_QUESTIONS.slice(0, 2).map((group, groupIndex) => (
//                     <div
//                       key={groupIndex}
//                       className="space-y-1.5 rounded-xl p-2 border"
//                       style={{
//                         background: 'rgba(255,255,255,0.04)',
//                         borderColor: 'rgba(255,255,255,0.10)',
//                       }}
//                     >
//                       <p className={cn("text-xs font-medium flex items-center gap-1 text-white/85", group.color)}>
//                         <group.icon className="h-3 w-3" />
//                         {group.group}
//                       </p>
//                       {group.options.slice(0, 2).map((prompt, i) => (
//                         <Button
//                           key={i}
//                           variant="outline"
//                           size="sm"
//                           className={cn(
//                             "w-full text-xs h-8 justify-start rounded-xl transition-all text-white/90 border hover:text-white",
//                             group.color
//                           )}
//                           style={{
//                             background: 'rgba(17,17,24,0.9)',
//                             borderColor: 'rgba(139, 92, 246, 0.22)',
//                           }}
//                           onClick={() => setQuestion(prompt)}
//                         >
//                           {truncate(prompt, 20)}
//                         </Button>
//                       ))}
//                     </div>
//                   ))}
//                 </motion.div>
//               )}
//             </form>
//           </div>

//           {/* Expand graph dialog */}
//           <Dialog open={!!expandedGraph} onOpenChange={(open) => !open && setExpandedGraph(null)}>
//             <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-auto rounded-2xl">
//               <DialogHeader className="shrink-0">
//                 <DialogTitle className="text-xl bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
//                   {expandedGraph?.chartTitle || 'Graph'}
//                 </DialogTitle>
//               </DialogHeader>
//               <div className="min-h-[400px] py-4">
//                 {expandedGraph?.chart && renderChart(expandedGraph.chart)}
//               </div>
//             </DialogContent>
//           </Dialog>

//           {/* Save prompt dialog */}
//           <Dialog open={saveModalOpen} onOpenChange={(open) => {
//             if (!open) {
//               setSaveModalOpen(false);
//               setSaveTitle('');
//               setSaveTags('');
//               setCurrentPromptData(null);
//             }
//           }}>
//             <DialogContent className="max-w-md rounded-2xl">
//               <DialogHeader>
//                 <DialogTitle className="text-xl bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Save Prompt</DialogTitle>
//                 <DialogDescription>Save this graph prompt for quick access later.</DialogDescription>
//               </DialogHeader>
//               <div className="space-y-4 py-4">
//                 <div className="space-y-2">
//                   <Label htmlFor="save-title">Title</Label>
//                   <Input
//                     id="save-title"
//                     value={saveTitle}
//                     onChange={(e) => setSaveTitle(e.target.value)}
//                     placeholder="e.g. Monthly Campaign Performance"
//                     className="rounded-xl border-border focus:border-primary/50 transition-all"
//                   />
//                 </div>
//                 <div className="space-y-2">
//                   <Label htmlFor="save-tags">Tags (comma-separated)</Label>
//                   <Input
//                     id="save-tags"
//                     value={saveTags}
//                     onChange={(e) => setSaveTags(e.target.value)}
//                     placeholder="e.g. analytics, campaigns"
//                     className="rounded-xl border-border focus:border-primary/50 transition-all"
//                   />
//                 </div>
//               </div>
//               <DialogFooter>
//                 <Button variant="outline" onClick={() => setSaveModalOpen(false)} className="rounded-xl">Cancel</Button>
//                 <Button onClick={handleSavePrompt} disabled={saving} className="rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70">
//                   {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Prompt</>}
//                 </Button>
//               </DialogFooter>
//             </DialogContent>
//           </Dialog>
//         </Card>
//       </motion.div>
//     </motion.div>
//   );
// };

// export default MarketingQA;



import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Loader2,
  Send,
  MessageSquare,
  Plus,
  MessageCircle,
  Bot,
  User,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Clock,
  X,
  Lightbulb,
  TrendingUp,
  Target,
  BarChart3,
  BookOpen,
  Award,
  Zap,
  Search,
  BarChart2,
  Maximize2,
  Save,
  LayoutDashboard,
  PieChart,
  Activity
} from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'marketing_qa_chats'; // kept for one-time migration

/** Normalize question for comparison: trim, lower, collapse spaces, remove trailing punctuation */
function normalizeQuestion(text) {
  if (!text || typeof text !== 'string') return '';
  return text
    .replace(/\u200B|\u200C|\u200D|\uFEFF/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/[?!.,;:]+\s*$/, '');
}

/** True if question is greeting/small talk – do not call API */
function isGreetingOrSmallTalk(question) {
  const t = normalizeQuestion(question);
  if (!t) return true;
  if (t.length > 40) return false;
  const smallTalk = new Set([
    'hi', 'hii', 'hello', 'hey', 'helo', 'yo', 'sup', 'thanks', 'thank you', 'thx',
    'ok', 'okay', 'oky', 'okey', 'okie', 'k', 'kk', 'bye', 'goodbye', 'cya',
    'good', 'great', 'nice', 'cool', 'alright', 'fine', 'got it', 'understood',
    'perfect', 'sure', 'yeah', 'yep', 'yup', 'nope', 'no', 'yes',
    'ok good', 'okay good', 'oky good', 'ok god', 'oky god', 'okay god',
    'okya', 'okya good', 'okya god', 'okie good', 'gud', 'gud good',
  ]);
  if (smallTalk.has(t)) return true;
  if (t.length <= 14 && /^ok[a-z]*\s*(good|god|gud)?$/.test(t)) return true;
  return false;
}

/** True if question is meta (what can I ask) – do not call API. Platform/agent questions ("what is this platform", "how does this work") go to API. */
function isMetaQuestion(question) {
  const t = normalizeQuestion(question);
  if (!t || t.length > 80) return false;
  const metaPhrases = [
    'what can i ask', 'what i can ask', 'how can you help', 'what do you do',
    'what can you answer', 'what should i ask',
    'example questions', 'give me examples', 'what to ask',
  ];
  return metaPhrases.some((p) => t.includes(p));
}

/** Markdown to HTML for Q&A answers - readable paragraphs, headings, bullets, tables */
function markdownToHtml(markdown) {
  if (!markdown || typeof markdown !== 'string') return '';

  const escape = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-primary">$1</strong>');

  const lines = markdown.split('\n');
  const out = [];
  let inList = false;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    // Markdown table: | col | col |
    if (t.startsWith('|') && t.endsWith('|')) {
      if (inList) { out.push('</ul>'); inList = false; }

      const tableRows = [];
      let j = i;
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        const cells = lines[j].trim().split('|').map(c => c.trim()).filter(Boolean);
        if (cells.length > 0 && cells.every(c => /^[-:\s]+$/.test(c))) {
          j++;
          continue;
        }
        tableRows.push(cells);
        j++;
      }
      i = j;

      if (tableRows.length > 0) {
        out.push('<div class="my-5 overflow-x-auto rounded-lg border border-border shadow-sm"><table class="w-full text-base">');
        out.push('<thead><tr class="bg-gradient-to-r from-muted/80 to-muted/40">');
        tableRows[0].forEach(cell => out.push(`<th class="px-4 py-3 text-left font-semibold text-foreground">${bold(escape(cell))}</th>`));
        out.push('</tr></thead><tbody>');
        tableRows.slice(1).forEach((row, idx) => {
          out.push(`<tr class="${idx % 2 === 0 ? 'bg-gradient-to-r from-muted/20 to-transparent' : ''} hover:bg-muted/30 transition-colors">`);
          row.forEach(cell => out.push(`<td class="px-4 py-3 border-t border-border text-base">${bold(escape(cell))}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
      }
      continue;
    }

    if (/^---+$/.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr class="my-5 border-border/50 bg-gradient-to-r from-transparent via-border to-transparent"/>');
      i++; continue;
    }

    if (/^## /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2 bg-gradient-to-r from-primary/5 to-transparent p-2 rounded-lg">${bold(escape(t.slice(3)))}</h2>`);
      i++; continue;
    }

    if (/^### /.test(t)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3 class="text-lg font-bold mt-4 mb-2 text-foreground bg-gradient-to-r from-muted/30 to-transparent p-2 rounded-lg">${bold(escape(t.slice(4)))}</h3>`);
      i++; continue;
    }

    // Lines ending with : (like "Opportunities We're Missing:") treated as h2
    if (t.endsWith(':') && t.length > 10 && !t.startsWith('-') && !t.startsWith('*')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h2 class="text-xl font-bold mt-6 mb-3 text-primary border-b border-primary/20 pb-2 bg-gradient-to-r from-primary/5 to-transparent p-2 rounded-lg">${bold(escape(t))}</h2>`);
      i++; continue;
    }

    if (/^[\s]*(?:•|-|\*|\d+\.)\s+/.test(t)) {
      if (!inList) {
        out.push('<ul class="list-disc pl-6 my-4 space-y-2 bg-gradient-to-r from-muted/10 to-transparent p-3 rounded-lg">');
        inList = true;
      }
      const content = t.replace(/^[\s]*(?:•|-|\*|\d+\.)\s+/, '');
      out.push(`<li class="text-base leading-relaxed hover:bg-muted/20 transition-colors rounded px-2">${bold(escape(content))}</li>`);
      i++; continue;
    }

    if (t === '' && inList) {
      out.push('</ul>');
      inList = false;
      i++; continue;
    }

    if (t && !t.startsWith('<')) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<p class="my-4 text-base leading-relaxed bg-gradient-to-r from-muted/5 to-transparent p-2 rounded-lg">${bold(escape(t)).replace(/\n/g, '<br/>')}</p>`);
    }
    i++;
  }

  if (inList) out.push('</ul>');
  return out.join('\n');
}

/** Suggested questions matching backend / agents_test.html Knowledge Q&A + Analytics */
const SUGGESTED_QUESTIONS = [
  {
    group: '🚀 Platform & Getting Started',
    icon: BookOpen,
    color: 'text-blue-500',
    bgColor: 'from-blue-500/10 to-blue-500/5',
    borderColor: 'border-blue-500/20',
    options: [
      'What is this platform?',
      'How does this platform work?',
      'How do I run a campaign?',
      'What is this agent?',
    ]
  },
  {
    group: '📊 Performance & Analytics',
    icon: BarChart3,
    color: 'text-emerald-500',
    bgColor: 'from-emerald-500/10 to-emerald-500/5',
    borderColor: 'border-emerald-500/20',
    options: [
      'What campaigns are performing best?',
      'What is our conversion rate?',
      'How are our campaigns performing this month?',
      'What is our customer acquisition cost (CAC)?',
    ]
  },
  {
    group: '🔍 Analysis & Insights',
    icon: TrendingUp,
    color: 'text-purple-500',
    bgColor: 'from-purple-500/10 to-purple-500/5',
    borderColor: 'border-purple-500/20',
    options: [
      'Why are sales dropping?',
      'What should we focus on to improve performance?',
      'What are the key trends in our marketing data?',
      'Which campaigns need optimization?',
      'What are our top performing campaigns and why?',
    ]
  },
  {
    group: '🎯 Goals & Targets',
    icon: Target,
    color: 'text-amber-500',
    bgColor: 'from-amber-500/10 to-amber-500/5',
    borderColor: 'border-amber-500/20',
    options: [
      'How many leads have we generated this month?',
      'What is our lead conversion rate?',
      'Are we on track to meet our campaign goals?',
    ]
  },
  {
    group: '💡 Strategy & Recommendations',
    icon: Lightbulb,
    color: 'text-rose-500',
    bgColor: 'from-rose-500/10 to-rose-500/5',
    borderColor: 'border-rose-500/20',
    options: [
      'What marketing strategies should we implement?',
      'What opportunities are we missing?',
      'How can we improve our campaign performance?',
      'What are the best practices for our industry?',
    ]
  },
];

const SUGGESTED_GRAPH_QUESTIONS = [
  { text: 'Show campaigns by status as a pie chart', icon: PieChart, color: 'text-blue-500' },
  { text: 'Display open rate by campaign as a bar chart', icon: BarChart3, color: 'text-emerald-500' },
  { text: 'Compare emails sent by campaign', icon: BarChart2, color: 'text-purple-500' },
  { text: 'Show leads per campaign', icon: TrendingUp, color: 'text-amber-500' },
  { text: 'Display replies by campaign as a bar chart', icon: Activity, color: 'text-rose-500' },
  { text: 'Top 5 campaigns by emails sent', icon: Award, color: 'text-indigo-500' },
  { text: 'Campaigns by status', icon: PieChart, color: 'text-cyan-500' },
  { text: 'Open rate by campaign', icon: BarChart3, color: 'text-orange-500' },
];

const SUGGESTED_SEARCH_QUESTIONS = [
  { text: 'What campaigns are performing best?', icon: Award, color: 'text-emerald-500' },
  // { text: 'What is our overall ROI?', icon: TrendingUp, color: 'text-blue-500' },
  // { text: 'Which marketing channels are most effective?', icon: BarChart3, color: 'text-purple-500' },
  { text: 'How are our campaigns performing this month?', icon: Activity, color: 'text-amber-500' },
  { text: 'What should we focus on to improve performance?', icon: Target, color: 'text-rose-500' },
];

// Chart components
const SimpleBarChart = ({ data, colors, height = 250, title }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const entries = Object.entries(data).map(([key, value]) => [key, Number(value) || 0]);
  const maxValue = Math.max(...entries.map(([, value]) => value), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  const dynamicHeight = Math.max(140, Math.min(360, entries.length * 42 + 30));

  return (
    <div
      className="rounded-xl border border-white/10 bg-[#090c14] p-3 sm:p-4 shadow-[0_8px_30px_rgba(0,0,0,0.28)]"
      style={{ minHeight: `${Math.max(dynamicHeight, height * 0.6)}px` }}
    >
      {title && <h4 className="font-semibold text-sm text-white/90 mb-3">{title}</h4>}
      <div className="space-y-2.5" style={{ minHeight: `${dynamicHeight}px` }}>
        {entries.map(([key, value], index) => (
          <div key={key} className="grid grid-cols-[minmax(120px,1fr)_minmax(180px,4fr)_58px] items-center gap-3">
            <span className="text-xs sm:text-sm text-white/75 truncate" title={key}>{key}</span>
            <div className="w-full h-8 rounded-lg bg-white/10 border border-white/10 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${value > 0 ? Math.max((value / maxValue) * 100, 4) : 0}%` }}
                transition={{ duration: 0.55, delay: index * 0.08 }}
                className="h-full rounded-lg"
                style={{
                  backgroundColor: chartColors[index % chartColors.length],
                }}
              />
            </div>
            <span className="text-right text-sm font-semibold text-white/90">{Number.isInteger(value) ? value : value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const SimplePieChart = ({ data, colors, title }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const total = Object.values(data).reduce((sum, val) => sum + val, 0);
  if (total === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  let currentAngle = 0;
  const segments = Object.entries(data).map(([key, value], index) => {
    const angle = (value / total) * 360;
    const slice = { key, value, percentage: Math.round((value / total) * 100), color: chartColors[index % chartColors.length], angle, startAngle: currentAngle };
    currentAngle += angle;
    return slice;
  });
  return (
    <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-gradient-to-b from-muted/5 to-transparent">
      {title && <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>}
      <div className="relative w-48 h-48 sm:w-56 sm:h-56">
        <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
          {segments.map((segment, index) => {
            const x1 = 100 + 100 * Math.cos((segment.startAngle * Math.PI) / 180);
            const y1 = 100 + 100 * Math.sin((segment.startAngle * Math.PI) / 180);
            const x2 = 100 + 100 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const y2 = 100 + 100 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const largeArc = segment.angle > 180 ? 1 : 0;
            return (
              <motion.path
                key={index}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, delay: index * 0.1 }}
                d={`M100,100 L${x1},${y1} A100,100 0 ${largeArc},1 ${x2},${y2} Z`}
                fill={segment.color}
                stroke="#000"
                strokeWidth="1"
                className="hover:opacity-80 transition-opacity cursor-pointer"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200, damping: 15 }}
            className="text-center bg-background/80 backdrop-blur-sm rounded-full w-16 h-16 flex items-center justify-center shadow-lg"
          >
            <div>
              <div className="text-xl font-bold">{total}</div>
              <div className="text-[10px] text-muted-foreground">Total</div>
            </div>
          </motion.div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
        {segments.map((segment, index) => (
          <motion.div
            key={index}
            initial={{ x: -10, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ delay: index * 0.05 }}
            className="flex items-center gap-2 text-xs sm:text-sm p-1.5 rounded-lg hover:bg-muted/30 transition-colors"
          >
            <div className="w-3 h-3 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: segment.color }} />
            <span className="truncate flex-1 font-medium">{segment.key}</span>
            <span className="font-semibold shrink-0 bg-muted/30 px-1.5 py-0.5 rounded-full text-[10px]">{segment.percentage}%</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

const SimpleLineChart = ({ data, color = '#3b82f6', height = 280, title, variant = 'line' }) => {
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (!data || data.length === 0) return <div className="text-sm text-muted-foreground">No data available</div>;
  const isArea = variant === 'area';
  const values = data.map(d => Number(d.value ?? d.count ?? 0));
  const rawLabels = data.map(d => d.label ?? d.date ?? d.month ?? d.name ?? '');

  // Strict date pattern – only YYYY-MM-DD or ISO 8601 or MM/DD/YYYY
  const isDateString = (str) => {
    if (!str || typeof str !== 'string') return false;
    const s = str.trim();
    return /^\d{4}-\d{2}-\d{2}/.test(s) || /^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(s);
  };

  const formatDateShort = (str) => {
    if (!str) return '';
    const d = new Date(String(str).trim());
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const formatDateFull = (str) => {
    if (!str) return '';
    const d = new Date(String(str).trim());
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  // Check if ALL labels are pure dates (time-series axis)
  const allDates = rawLabels.length > 0 && rawLabels.every(l => isDateString(String(l).trim()));

  // Check if data points have campaign dates (start_date / end_date)
  const hasCampaignDates = data.some(d => d.start_date || d.end_date);

  // Short label for x-axis
  const formatLabel = (label) => {
    if (!label) return '';
    const str = String(label).trim();
    if (allDates && isDateString(str)) return formatDateShort(str);
    // Campaign name – truncate if long
    return str.length > 16 ? str.slice(0, 14) + '…' : str;
  };

  // Full label for tooltip
  const formatFullLabel = (label) => {
    if (!label) return '';
    const str = String(label).trim();
    if (allDates && isDateString(str)) return formatDateFull(str);
    return str;
  };

  // Build date range string for campaign (e.g. "Mar 5 – Mar 20")
  const getCampaignDateRange = (item) => {
    const s = item.start_date ? formatDateShort(item.start_date) : '';
    const e = item.end_date ? formatDateShort(item.end_date) : '';
    if (s && e) return `${s} – ${e}`;
    if (s) return `From ${s}`;
    if (e) return `Until ${e}`;
    return '';
  };

  const labels = rawLabels.map(formatLabel);
  const fullLabels = rawLabels.map(formatFullLabel);
  const dateRanges = data.map(d => hasCampaignDates ? getCampaignDateRange(d) : '');

  // Compute nice Y-axis range with padding
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const minValue = dataMin >= 0 ? 0 : dataMin;
  const maxValue = dataMax <= 0 ? 1 : dataMax + (dataMax - minValue) * 0.1;
  const range = maxValue - minValue || 1;

  const formatVal = (v) => {
    const n = Number(v);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    if (n === 0) return '0';
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  };

  // SVG dimensions (pixel-based for crisp rendering)
  const svgW = 600;
  const svgH = 260;
  const padTop = 20;
  const padBottom = 10;
  const padLeft = 55;
  const padRight = 20;
  const chartW = svgW - padLeft - padRight;
  const chartH = svgH - padTop - padBottom;

  // Y-axis ticks (5 values for cleaner grid)
  const yTickCount = 5;
  const yTicks = Array.from({ length: yTickCount }, (_, i) => {
    const val = minValue + (range * i) / (yTickCount - 1);
    const y = padTop + chartH - (chartH * i) / (yTickCount - 1);
    return { val, y };
  });

  // Data points in pixel coords
  const dataPoints = values.map((value, index) => ({
    x: padLeft + (index / (values.length - 1 || 1)) * chartW,
    y: padTop + chartH - ((value - minValue) / range) * chartH,
    value,
    label: labels[index],
    fullLabel: fullLabels[index],
    dateRange: dateRanges[index],
  }));

  const linePath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaPath = `${linePath} L${dataPoints[dataPoints.length - 1].x},${padTop + chartH} L${dataPoints[0].x},${padTop + chartH} Z`;

  // Pick which X labels to show (avoid overlap)
  const maxXLabels = Math.min(labels.length, 8);
  const xLabelStep = labels.length <= maxXLabels ? 1 : Math.ceil(labels.length / maxXLabels);
  const visibleXIndices = labels.map((_, i) => i).filter(i =>
    i === 0 || i === labels.length - 1 || i % xLabelStep === 0
  );

  return (
    <div className={cn(
      'space-y-3 p-4 rounded-xl border',
      isArea
        ? 'bg-gradient-to-b from-primary/10 via-primary/5 to-transparent border-primary/20'
        : 'bg-gradient-to-b from-muted/5 to-transparent border-white/10'
    )}>
      {title && (
        <h4 className={cn('font-semibold text-sm mb-1', isArea ? 'text-primary' : 'text-white/80')}>
          {title}
        </h4>
      )}
      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${svgW} ${svgH + (hasCampaignDates ? 55 : 40)}`}
          preserveAspectRatio="xMidYMid meet"
          className="overflow-visible"
          onMouseLeave={() => setHoveredIndex(null)}
        >
          {/* Horizontal grid lines */}
          {yTicks.map((tick, i) => (
            <g key={`y-${i}`}>
              <line
                x1={padLeft}
                y1={tick.y}
                x2={svgW - padRight}
                y2={tick.y}
                stroke="currentColor"
                strokeWidth="0.5"
                strokeDasharray={i === 0 ? 'none' : '4 3'}
                className="text-white/[0.08]"
              />
              <text
                x={padLeft - 10}
                y={tick.y + 4}
                textAnchor="end"
                className="fill-white/40"
                fontSize="11"
                fontFamily="inherit"
              >
                {formatVal(tick.val)}
              </text>
            </g>
          ))}

          {/* Area fill with gradient */}
          {isArea && (
            <>
              <defs>
                <linearGradient id={`area-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity="0.35" />
                  <stop offset="100%" stopColor={color} stopOpacity="0.03" />
                </linearGradient>
              </defs>
              <motion.path
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6 }}
                d={areaPath}
                fill={`url(#area-grad-${color.replace('#', '')})`}
              />
            </>
          )}

          {/* Line */}
          <motion.path
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            d={linePath}
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Data points */}
          {dataPoints.map((p, index) => (
            <motion.circle
              key={index}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.4 + index * 0.05, type: 'spring', stiffness: 200, damping: 15 }}
              cx={p.x}
              cy={p.y}
              r={hoveredIndex === index ? 6 : 4}
              fill={hoveredIndex === index ? '#ffffff' : color}
              stroke={hoveredIndex === index ? color : 'rgba(255,255,255,0.3)'}
              strokeWidth={hoveredIndex === index ? 2.5 : 1.5}
              className="cursor-pointer transition-all duration-150"
              onMouseEnter={() => setHoveredIndex(index)}
            />
          ))}

          {/* Hover vertical guide line */}
          {hoveredIndex !== null && dataPoints[hoveredIndex] && (
            <line
              x1={dataPoints[hoveredIndex].x}
              y1={padTop}
              x2={dataPoints[hoveredIndex].x}
              y2={padTop + chartH}
              stroke={color}
              strokeWidth="1"
              strokeDasharray="4 3"
              opacity="0.4"
            />
          )}

          {/* X-axis labels */}
          {visibleXIndices.map((i) => (
            <g key={`x-${i}`}>
              <text
                x={dataPoints[i].x}
                y={svgH + 14}
                textAnchor={allDates ? 'middle' : 'end'}
                transform={allDates ? undefined : `rotate(-30, ${dataPoints[i].x}, ${svgH + 14})`}
                className="fill-white/50"
                fontSize="11"
                fontWeight="500"
                fontFamily="inherit"
              >
                {labels[i]}
              </text>
              {/* Campaign date range below the name */}
              {!allDates && dataPoints[i].dateRange && (
                <text
                  x={dataPoints[i].x}
                  y={svgH + 28}
                  textAnchor={allDates ? 'middle' : 'end'}
                  transform={allDates ? undefined : `rotate(-30, ${dataPoints[i].x}, ${svgH + 28})`}
                  className="fill-white/30"
                  fontSize="9"
                  fontFamily="inherit"
                >
                  {dataPoints[i].dateRange}
                </text>
              )}
            </g>
          ))}
        </svg>

        {/* Tooltip */}
        {hoveredIndex !== null && dataPoints[hoveredIndex] && (
          <div
            className="absolute pointer-events-none z-10 px-3 py-2 rounded-lg border border-white/15 bg-black/90 backdrop-blur-md shadow-xl"
            style={{
              left: `${(dataPoints[hoveredIndex].x / svgW) * 100}%`,
              top: `${(dataPoints[hoveredIndex].y / (svgH + (hasCampaignDates ? 55 : 40))) * 100}%`,
              transform: 'translate(-50%, -120%)',
            }}
          >
            <p className="text-[11px] font-medium text-white/70 mb-0.5">{dataPoints[hoveredIndex].fullLabel}</p>
            {dataPoints[hoveredIndex].dateRange && (
              <p className="text-[10px] text-white/40 mb-0.5">{dataPoints[hoveredIndex].dateRange}</p>
            )}
            <p className="text-sm font-semibold" style={{ color }}>{formatVal(dataPoints[hoveredIndex].value)}</p>
          </div>
        )}
      </div>
    </div>
  );
};

const renderChart = (chartData) => {
  if (!chartData) return null;
  const { type, data, title, color, colors } = chartData;
  const normalizedType = String(type || '')
    .toLowerCase()
    .replace(/[_-]/g, ' ')
    .trim();

  const resolvedType = normalizedType.includes('line')
    ? 'line'
    : normalizedType.includes('area')
      ? 'area'
      : normalizedType.includes('pie') || normalizedType.includes('donut') || normalizedType.includes('doughnut')
        ? 'pie'
        : normalizedType.includes('bar') || normalizedType.includes('column')
          ? 'bar'
          : 'bar';

  const normalizedData =
    resolvedType === 'line' || resolvedType === 'area'
      ? (Array.isArray(data) ? data : Object.entries(data || {}).map(([label, value]) => ({ label, value })))
      : (Array.isArray(data) ? Object.fromEntries(data.map((d, i) => [d?.label ?? `Item ${i + 1}`, d?.value ?? 0])) : data);

  switch (resolvedType) {
    case 'bar': return <SimpleBarChart data={normalizedData} colors={colors} title={title} />;
    case 'pie': return <SimplePieChart data={normalizedData} colors={colors} title={title} />;
    case 'line': return <SimpleLineChart data={normalizedData} color={color} title={title} variant="line" />;
    case 'area': return <SimpleLineChart data={normalizedData} color={color} title={title} variant="area" />;
    default: return <SimpleBarChart data={normalizedData} colors={colors} title={title} />;
  }
};

/** Normalize chat to { id, messages: [{ role, content, responseData? }], timestamp } */
function normalizeChat(c) {
  if (c.messages && Array.isArray(c.messages)) {
    return { ...c, id: String(c.id), timestamp: c.timestamp || c.updatedAt || new Date().toISOString() };
  }
  if (c.question != null) {
    return {
      id: String(c.id),
      messages: [
        { role: 'user', content: c.question },
        { role: 'assistant', content: c.response || '', responseData: c.responseData },
      ],
      timestamp: c.timestamp || c.updatedAt || new Date().toISOString(),
    };
  }
  return { id: String(c.id || Date.now()), messages: [], timestamp: c.timestamp || c.updatedAt || new Date().toISOString() };
}

function loadChatsFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return list.map(normalizeChat);
  } catch {
    return [];
  }
}

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  }
};

const messageVariants = {
  hidden: { scale: 0.8, opacity: 0, y: 20 },
  visible: {
    scale: 1,
    opacity: 1,
    y: 0,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 15
    }
  },
  exit: {
    scale: 0.8,
    opacity: 0,
    transition: { duration: 0.2 }
  }
};

const sidebarItemVariants = {
  hidden: { x: -20, opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 12
    }
  },
  hover: {
    scale: 1.02,
    x: 5,
    transition: { duration: 0.2 }
  }
};

const MarketingQA = () => {
  const { toast } = useToast();
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [suggestedValue, setSuggestedValue] = useState('__none__');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [inputMode, setInputMode] = useState('search');
  const [expandedGraph, setExpandedGraph] = useState(null);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [currentPromptData, setCurrentPromptData] = useState(null);
  const [comparisonResults, setComparisonResults] = useState([]);

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Load chats from API on mount; migrate localStorage data if present
  useEffect(() => {
    const loadFromApi = async () => {
      try {
        const res = await marketingAgentService.listQAChats();
        if (res?.status === 'success' && Array.isArray(res.data)) {
          setChats(res.data.map(normalizeChat));

          // One-time migration: push any localStorage chats that aren't in the DB yet
          const localChats = loadChatsFromStorage();
          if (localChats.length > 0) {
            const dbIds = new Set(res.data.map((c) => String(c.id)));
            const toMigrate = localChats.filter((c) => !dbIds.has(String(c.id)));
            for (const lc of toMigrate) {
              try {
                const title = (lc.messages?.[0]?.content || 'Chat').slice(0, 100);
                await marketingAgentService.createQAChat({ title, messages: lc.messages || [] });
              } catch { /* skip failed migrations */ }
            }
            localStorage.removeItem(STORAGE_KEY);
            // Reload from API to get migrated chats
            if (toMigrate.length > 0) {
              const res2 = await marketingAgentService.listQAChats();
              if (res2?.status === 'success' && Array.isArray(res2.data)) {
                setChats(res2.data.map(normalizeChat));
              }
            }
          }
        }
      } catch {
        // Fallback to localStorage if API fails
        setChats(loadChatsFromStorage());
      }
    };
    loadFromApi();
  }, []);



  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]);

  // Load prompt from dashboard when clicking saved graph
  useEffect(() => {
    if (window.marketingQALoadPrompt) {
      const { prompt, chartType } = window.marketingQALoadPrompt;
      if (prompt) {
        setQuestion(prompt);
        setInputMode('graph');
        textareaRef.current?.focus();
        // Clear the flag
        window.marketingQALoadPrompt = null;
      }
    }
  }, []);

  const fillFromSuggestion = (value) => {
    const v = value || '__none__';
    setSuggestedValue(v);
    if (v !== '__none__') {
      setQuestion(v);
      textareaRef.current?.focus();
    }
  };

  // Compare manual query with AI response
  const compareResponses = async (query, inputMode) => {
    try {
      console.log('🔍 Starting comparison for query:', query);

      // Manual API call
      let manualResponse;
      if (inputMode === 'graph') {
        manualResponse = await marketingAgentService.generateGraph(query);
      } else {
        manualResponse = await marketingAgentService.marketingQA(query, []);
      }

      console.log('📊 Manual API Response:', manualResponse);

      // Store comparison result
      const comparisonData = {
        query,
        mode: inputMode,
        timestamp: new Date().toISOString(),
        manualResponse,
        status: manualResponse?.status,
        success: manualResponse?.status === 'success'
      };

      if (inputMode === 'graph') {
        comparisonData.manualChart = manualResponse?.data?.chart;
        comparisonData.manualTitle = manualResponse?.data?.title;
        comparisonData.manualInsights = manualResponse?.data?.insights;
      } else {
        comparisonData.manualAnswer = manualResponse?.data?.answer;
        comparisonData.manualInsights = manualResponse?.data?.insights;
      }

      // Add to comparison results
      setComparisonResults(prev => [comparisonData, ...prev].slice(0, 20)); // Keep last 20

      console.log('✅ Comparison Result:', comparisonData);
      console.log('📈 All Comparisons:', [comparisonData, ...comparisonResults]);

      return comparisonData;
    } catch (error) {
      const errorData = {
        query,
        mode: inputMode,
        timestamp: new Date().toISOString(),
        error: error?.message,
        status: 'error',
        success: false
      };

      console.error('❌ Comparison Error:', errorData);
      setComparisonResults(prev => [errorData, ...prev].slice(0, 20));

      return errorData;
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a question.',
        variant: 'destructive'
      });
      return;
    }

    const q = question.trim();

    // Check for special cases (only for search mode)
    if (inputMode === 'search') {
      if (isGreetingOrSmallTalk(q)) {
        const response = {
          answer: "👋 Hi there! I'm your Marketing Q&A Assistant. I can help you with:\n\n• **Campaign performance** metrics and insights\n• **ROI analysis** and optimization suggestions\n• **Lead generation** and conversion rates\n• **Channel effectiveness** comparisons\n• **Strategic recommendations** for improvement\n\nWhat would you like to know about your marketing data?",
          insights: [],
        };
        const responseText = response.answer;
        const userMsg = { role: 'user', content: q };
        const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
        handleResponse(q, userMsg, assistantMsg, response);
        return;
      }

      if (isMetaQuestion(q)) {
        const response = {
          answer: "You can ask me about:\n\n**📈 Performance Metrics**\n• Campaign ROI, conversion rates, CAC\n• Channel effectiveness, lead generation\n\n**🔍 Analysis**\n• Why sales are dropping/rising\n• Which campaigns need optimization\n• Trends in your marketing data\n\n**💡 Recommendations**\n• Marketing strategies to implement\n• Opportunities you might be missing\n• Best practices for your industry\n\nPick a suggested question above or type your own!",
          insights: [],
        };
        const responseText = response.answer;
        const userMsg = { role: 'user', content: q };
        const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
        handleResponse(q, userMsg, assistantMsg, response);
        return;
      }
    }

    // Actual API call
    try {
      setLoading(true);

      // Send last 6 Q&A pairs for context
      const pairs = [];
      const messages = currentMessages || [];
      for (let i = 0; i < messages.length - 1; i++) {
        if (messages[i].role === 'user' && messages[i + 1].role === 'assistant') {
          const answer = messages[i + 1].responseData?.answer ?? messages[i + 1].content ?? '';
          pairs.push({ question: messages[i].content, answer });
        }
      }
      const conversationHistory = pairs.slice(-6);
      const reducedConversationHistory = pairs.slice(-2);

      let result;

      if (inputMode === 'graph') {
        // Call graph generation API
        result = await marketingAgentService.generateGraph(q);
      } else {
        // Call QA API
        result = await marketingAgentService.marketingQA(q, reducedConversationHistory);
      }

      if (result.status === 'success' && result.data) {
        const response = result.data;

        if (inputMode === 'graph') {
          // Handle graph response
          const userMsg = { role: 'user', content: q };
          const assistantMsg = {
            role: 'assistant',
            content: q,
            responseData: {
              isGraph: true,
              chart: response.chart,
              chartTitle: response.chart?.title || response.title || 'Chart',
              chartType: response.chart?.type || 'bar',
              insights: response.insights || []
            }
          };
          handleResponse(q, userMsg, assistantMsg, response);
        } else {
          // Handle QA response
          const answer = response.answer || 'No answer provided.';
          const insights = response.insights || [];

          let responseText = answer;
          if (insights.length > 0) {
            responseText += '\n\n**Key Insights & Metrics**\n';
            insights.forEach((i) => {
              responseText += `• **${i.title || 'N/A'}**: ${i.value || 'N/A'}\n`;
            });
          }

          const userMsg = { role: 'user', content: q };
          const assistantMsg = { role: 'assistant', content: responseText, responseData: response };
          handleResponse(q, userMsg, assistantMsg, response);
        }
      } else {
        throw new Error(result.message || 'Failed to get response');
      }

      // Run comparison in background (no await - non-blocking)
      compareResponses(q, inputMode).catch(err => console.error('Comparison failed:', err));
    } catch (error) {
      toast({
        title: 'Warning',
        description: 'Please try again.',
        variant: 'default'
      });
    } finally {
      setLoading(false);
    }
  };


  const handleResponse = async (q, userMsg, assistantMsg, response) => {
    const newMessages = [userMsg, assistantMsg];

    if (selectedChatId) {
      const chat = chats.find((c) => c.id === selectedChatId);
      if (chat) {
        // Optimistic update
        const updatedChat = {
          ...chat,
          messages: [...(chat.messages || []), ...newMessages],
          timestamp: new Date().toISOString(),
        };
        setChats((prev) => prev.map((c) => (c.id === selectedChatId ? updatedChat : c)));
        // Persist to API
        try {
          await marketingAgentService.updateQAChat(selectedChatId, { messages: newMessages });
        } catch { /* optimistic update stays */ }
      } else {
        await createNewChat(q, response, userMsg, assistantMsg);
      }
    } else {
      await createNewChat(q, response, userMsg, assistantMsg);
    }

    setQuestion('');
    setSuggestedValue('__none__');
    textareaRef.current?.focus();
  };

  const createNewChat = async (q, response, userMsg, assistantMsg) => {
    const title = (q || 'Chat').slice(0, 100);
    const messages = [userMsg, assistantMsg];

    // Optimistic: show immediately with temp id
    const tempId = Date.now().toString();
    const tempChat = { id: tempId, messages, timestamp: new Date().toISOString() };
    setChats((prev) => [tempChat, ...prev]);
    setSelectedChatId(tempId);

    // Persist to API and replace temp with real id
    try {
      const res = await marketingAgentService.createQAChat({ title, messages });
      if (res?.status === 'success' && res.data) {
        const realChat = normalizeChat(res.data);
        setChats((prev) => prev.map((c) => (c.id === tempId ? realChat : c)));
        setSelectedChatId(realChat.id);
      }
    } catch { /* temp chat stays in state */ }
  };

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
    setSuggestedValue('__none__');
    textareaRef.current?.focus();
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    // Optimistic removal
    setChats((prev) => prev.filter((c) => c.id !== chatId));
    if (selectedChatId === chatId) setSelectedChatId(null);
    toast({
      title: 'Deleted',
      description: 'Conversation removed.'
    });
    // Persist to API
    try {
      await marketingAgentService.deleteQAChat(chatId);
    } catch { /* already removed from UI */ }
  };

  const openSaveModal = (prompt, chartTitle, chartType, chart = null, insights = []) => {
    setCurrentPromptData({ prompt, chartTitle, chartType, chart, insights });
    setSaveTitle(chartTitle || '');
    setSaveTags('');
    setSaveModalOpen(true);
  };

  const handleSavePrompt = async () => {
    if (!saveTitle.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a title',
        variant: 'destructive'
      });
      return;
    }

    try {
      setSaving(true);
      const promptData = {
        title: saveTitle,
        prompt: currentPromptData.prompt,
        tags: saveTags.split(',').map(t => t.trim()).filter(t => t),
        chart_type: currentPromptData.chartType,
        chart_data: currentPromptData.chart || null,
        insights: currentPromptData.insights || []
      };

      const saved = await marketingAgentService.saveGraphPrompt(promptData);

      try {
        const savedId = saved?.data?.id;
        if (savedId && currentPromptData?.chart) {
          const cacheKey = 'marketing_saved_graph_payloads';
          const cached = JSON.parse(localStorage.getItem(cacheKey) || '{}');
          cached[String(savedId)] = {
            chart: currentPromptData.chart,
            title: saveTitle || currentPromptData.chartTitle || 'Saved Graph',
            insights: currentPromptData.insights || [],
            prompt: currentPromptData.prompt,
          };
          localStorage.setItem(cacheKey, JSON.stringify(cached));
        }
      } catch { }

      toast({
        title: 'Success',
        description: 'Prompt saved successfully'
      });
      setSaveModalOpen(false);
      setSaveTitle('');
      setSaveTags('');
      setCurrentPromptData(null);
    } catch (error) {
      console.error('Save prompt error:', error);
      toast({
        title: 'Error',
        description: error?.response?.data?.message || 'Failed to save prompt',
        variant: 'destructive'
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddToDashboard = async (prompt, chartTitle, chartType, chart = null, insights = []) => {
    try {
      // First save the prompt
      const promptData = {
        title: chartTitle || 'Untitled Chart',
        prompt: prompt,
        tags: ['dashboard'],
        chart_type: chartType,
        chart_data: chart,
        insights: insights || []
      };

      await marketingAgentService.saveGraphPrompt(promptData);

      toast({
        title: 'Success',
        description: 'Chart added to dashboard'
      });
    } catch (error) {
      console.error('Add to dashboard error:', error);
      toast({
        title: 'Error',
        description: error?.response?.data?.message || 'Failed to add to dashboard',
        variant: 'destructive'
      });
    }
  };

  // Expose comparison results to window for debugging
  useEffect(() => {
    window.marketingQAComparison = {
      getComparisons: () => comparisonResults,
      getLatestComparison: () => comparisonResults[0],
      compareNow: (query, mode = 'search') => compareResponses(query, mode),
      getAllComparisonStatus: () => ({
        total: comparisonResults.length,
        successful: comparisonResults.filter(c => c.success).length,
        failed: comparisonResults.filter(c => !c.success).length,
        byMode: {
          search: comparisonResults.filter(c => c.mode === 'search').length,
          graph: comparisonResults.filter(c => c.mode === 'graph').length
        }
      })
    };

    console.log('🎯 Marketing QA Comparison Tool Available');
    console.log('Usage: window.marketingQAComparison.getComparisons()');

    return () => {
      delete window.marketingQAComparison;
    };
  }, [comparisonResults]);

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');

  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diff = now - d;

      if (diff < 86400000) { // Less than 24 hours
        return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      } else if (diff < 604800000) { // Less than 7 days
        return d.toLocaleDateString(undefined, { weekday: 'short' });
      } else {
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      }
    } catch {
      return '';
    }
  };

  return (
    <motion.div
      className="h-full min-h-0 flex gap-4"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Sidebar - Previous chats */}
      <motion.div
        variants={itemVariants}
        className={cn(
          "shrink-0 flex flex-col rounded-2xl border border-white/10 bg-black/20 backdrop-blur-sm overflow-hidden transition-all duration-300",
          sidebarOpen ? "w-80" : "w-16"
        )}
      >
        <div className="px-3 pt-3 pb-2 border-b border-violet-500/20 flex flex-col gap-2" style={{ background: 'linear-gradient(180deg, rgba(60,30,90,0.22) 0%, rgba(36,18,54,0.85) 100%)' }}>
          <div className="flex items-center justify-between">
            <AnimatePresence mode="wait">
              {sidebarOpen ? (
                <motion.span
                  key="title"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-sm font-semibold flex items-center gap-2 text-white/90"
                >
                  <MessageCircle className="h-4 w-4 text-violet-400" />
                  Conversations
                </motion.span>
              ) : (
                <motion.div
                  key="icon"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="w-full flex justify-center"
                >
                  <MessageCircle className="h-4 w-4 text-violet-400" />
                </motion.div>
              )}
            </AnimatePresence>
            <div className="flex items-center gap-1">
              {sidebarOpen && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => { setShowSidebarSearch(v => !v); setSidebarSearch(''); }}
                  title={showSidebarSearch ? 'Close search' : 'Search conversations'}
                  className="h-7 w-7 rounded-lg hover:bg-violet-500/20 hover:text-violet-300 transition-all"
                >
                  {showSidebarSearch ? <X className="h-3.5 w-3.5" /> : <Search className="h-3.5 w-3.5" />}
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="h-7 w-7 rounded-lg hover:bg-violet-500/20 hover:text-violet-300 transition-all"
              >
                {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={newChat}
                title="New conversation"
                className="h-7 w-7 rounded-lg hover:bg-violet-500/20 hover:text-violet-300 transition-all"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {sidebarOpen && showSidebarSearch && (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg" style={{ border: '1.5px solid rgba(139,92,246,0.30)', background: 'rgba(80,36,180,0.12)' }}>
              <Search className="h-3.5 w-3.5 text-violet-400 shrink-0" />
              <input
                autoFocus
                value={sidebarSearch}
                onChange={(e) => setSidebarSearch(e.target.value)}
                placeholder="Search conversations..."
                className="flex-1 bg-transparent outline-none border-0 text-white/90 text-xs px-1 placeholder-white/40"
              />
              {sidebarSearch && (
                <button onClick={() => setSidebarSearch('')} className="h-4 w-4 flex items-center justify-center rounded-full hover:bg-violet-500/30 transition-all">
                  <X className="h-3 w-3 text-white/60" />
                </button>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent">
          {chats.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-6 text-center"
            >
              {sidebarOpen ? (
                <>
                  <motion.div
                    animate={{
                      scale: [1, 1.1, 1],
                      rotate: [0, 5, -5, 0]
                    }}
                    transition={{
                      duration: 3,
                      repeat: Infinity,
                      repeatType: "reverse"
                    }}
                  >
                    <MessageCircle className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                  </motion.div>
                  <p className="text-sm text-muted-foreground">No conversations yet</p>
                  <p className="text-xs text-muted-foreground/70 mt-1">Ask a question to start</p>
                </>
              ) : (
                <MessageCircle className="h-5 w-5 mx-auto text-muted-foreground/50" />
              )}
            </motion.div>
          ) : (
            <div className="p-2 space-y-1">
              <AnimatePresence>
                {(() => {
                  const searchTerm = sidebarSearch.trim().toLowerCase();
                  const sorted = [...chats].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
                  const filtered = searchTerm
                    ? sorted.filter(c => (c.messages || []).some(m => (m.content || '').toLowerCase().includes(searchTerm)))
                    : sorted;
                  if (searchTerm && filtered.length === 0) {
                    return <div className="p-4 text-center text-xs text-muted-foreground">No matching conversations.</div>;
                  }
                  return filtered.map((c, index) => {
                    const firstQuestion = c.messages?.find(m => m.role === 'user')?.content || 'New chat';
                    const messageCount = c.messages?.filter(m => m.role === 'user').length || 0;

                    return (
                      <motion.div
                        key={c.id}
                        variants={sidebarItemVariants}
                        initial="hidden"
                        animate="visible"
                        exit={{ x: -20, opacity: 0 }}
                        whileHover="hover"
                        transition={{ delay: index * 0.05 }}
                        className={cn(
                          "group relative flex items-start gap-2 w-full p-3 rounded-xl text-sm transition-all cursor-pointer",
                          selectedChatId === c.id
                            ? 'bg-gradient-to-r from-violet-900/40 to-violet-700/20 border border-violet-500/40 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
                            : 'border border-transparent hover:bg-gradient-to-r hover:from-violet-900/30 hover:to-violet-700/10 hover:border-violet-500/30 hover:shadow-[0_0_8px_rgba(139,92,246,0.12)]'
                        )}
                        onClick={() => setSelectedChatId(c.id)}
                      >
                        <div className={cn(
                          "shrink-0 rounded-lg p-1.5 transition-all",
                          selectedChatId === c.id ? 'bg-violet-500/30' : 'bg-muted group-hover:bg-violet-500/20'
                        )}>
                          <MessageSquare className={cn(
                            "h-3.5 w-3.5",
                            selectedChatId === c.id ? 'text-violet-300' : 'text-muted-foreground group-hover:text-violet-400'
                          )} />
                        </div>

                        {sidebarOpen ? (
                          <>
                            <div className="flex-1 min-w-0">
                              <div className={cn("font-medium truncate flex items-center gap-1", selectedChatId === c.id ? 'text-violet-200' : 'text-white/90 group-hover:text-violet-200')}>
                                {truncate(firstQuestion, 25)}
                                {messageCount > 1 && (
                                  <Badge variant="outline" className="h-4 px-1 text-[10px] rounded-full bg-primary/10 border-primary/20">
                                    {messageCount}
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {formatDate(c.timestamp)}
                              </div>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 hover:bg-destructive/20 hover:text-destructive rounded-lg transition-all"
                              onClick={(e) => deleteChat(e, c.id)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <div className="absolute -top-1 -right-1">
                            <Badge variant="outline" className="h-3 px-1 text-[8px] rounded-full bg-primary/10 border-primary/20">
                              {messageCount}
                            </Badge>
                          </div>
                        )}
                      </motion.div>
                    );
                  });
                })()}
              </AnimatePresence>
            </div>
          )}
        </div>
      </motion.div>

      {/* Main chat area */}
      <motion.div
        variants={itemVariants}
        className="flex-1 min-w-0 min-h-0"
      >
        <Card className="h-full flex flex-col overflow-hidden border-white/10 bg-black/20 backdrop-blur-sm rounded-2xl">
          {/* Header */}
          <CardHeader className="shrink-0 border-b border-white/10 pb-3 rounded-t-2xl bg-white/[0.03]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <motion.div
                  whileHover={{ rotate: 360, scale: 1.1 }}
                  transition={{ duration: 0.5 }}
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/20"
                >
                  <Bot className="h-5 w-5 text-violet-400" />
                </motion.div>
                <div>
                  <CardTitle className="text-white flex items-center gap-2">
                    Marketing Q&A Assistant
                    <Badge variant="outline" className="bg-gradient-to-r from-primary/20 to-primary/5 gap-1 rounded-full border-primary/30">
                      <Zap className="h-3 w-3 text-primary" />
                      AI-Powered
                    </Badge>
                  </CardTitle>
                  <CardDescription className="text-white/60">
                    Ask anything about your campaigns, performance, and marketing data
                  </CardDescription>
                </div>
              </div>
              {selectedChat && (
                <Badge variant="secondary" className="gap-1 rounded-full bg-gradient-to-r from-muted to-muted/50">
                  <MessageSquare className="h-3 w-3" />
                  {currentMessages.filter(m => m.role === 'user').length} questions
                </Badge>
              )}
            </div>
          </CardHeader>

          {/* Messages area */}
          <CardContent className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-transparent">
            <AnimatePresence mode="popLayout">
              {!selectedChatId ? (
                <motion.div
                  key="welcome"
                  variants={messageVariants}
                  initial="hidden"
                  animate="visible"
                  exit="hidden"
                  className="flex flex-col items-center justify-center h-full text-center"
                >
                  <motion.div
                    animate={{
                      scale: [1, 1.1, 1],
                      rotate: [0, 5, -5, 0]
                    }}
                    transition={{
                      duration: 2,
                      repeat: Infinity,
                      repeatType: "reverse"
                    }}
                  >
                    <div className="relative">
                      <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full" />
                      <Bot className="h-20 w-20 text-primary/40 relative z-10" />
                    </div>
                  </motion.div>
                  <h3 className="text-xl font-semibold mb-2 bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Welcome to Marketing Q&A</h3>
                  <p className="text-muted-foreground max-w-md mb-6">
                    Ask me about campaign performance, ROI, conversion rates, and get data-driven insights
                  </p>

                  <div className="grid grid-cols-2 gap-3 max-w-lg">
                    {[
                      { icon: BarChart3, label: 'Campaign ROI', color: 'from-emerald-500/20 to-emerald-500/5' },
                      { icon: Target, label: 'Conversion Rates', color: 'from-purple-500/20 to-purple-500/5' },
                      { icon: TrendingUp, label: 'Channel Analysis', color: 'from-amber-500/20 to-amber-500/5' },
                      { icon: Lightbulb, label: 'Recommendations', color: 'from-rose-500/20 to-rose-500/5' }
                    ].map((item, i) => (
                      <motion.div
                        key={i}
                        whileHover={{ scale: 1.05, y: -2 }}
                        className={cn(
                          "flex items-center gap-2 p-3 rounded-xl bg-gradient-to-r border shadow-sm",
                          item.color
                        )}
                      >
                        <item.icon className={cn("h-4 w-4", item.color.replace('/20', ''))} />
                        <span className="text-sm font-medium">{item.label}</span>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              ) : (
                <div className="space-y-4">
                  <AnimatePresence>
                    {currentMessages.map((msg, i) => (
                      <motion.div
                        key={i}
                        variants={messageVariants}
                        initial="hidden"
                        animate="visible"
                        exit="exit"
                        className={cn(
                          "flex",
                          msg.role === 'user' ? 'justify-end' : 'justify-start'
                        )}
                      >
                        <div className={cn(
                          'rounded-2xl overflow-hidden shadow-md',
                          msg.role === 'user'
                            ? 'max-w-[85%] bg-gradient-to-r from-primary to-primary/90 text-primary-foreground'
                            : msg.responseData?.isGraph
                              ? 'w-full max-w-[980px] bg-gradient-to-r from-muted/80 to-muted/40 border shadow-sm'
                              : 'max-w-[85%] bg-gradient-to-r from-muted/80 to-muted/40 border shadow-sm'
                        )}>
                          {msg.role === 'user' ? (
                            <div className="px-4 py-3">
                              <div className="flex items-center gap-2 mb-1">
                                <User className="h-3 w-3 opacity-70" />
                                <span className="text-xs opacity-70">You</span>
                              </div>
                              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          ) : (
                            <div className="px-5 py-4">
                              <div className="flex items-center gap-2 mb-3">
                                <div className="rounded-full bg-primary/20 p-1">
                                  <Bot className="h-3 w-3 text-primary" />
                                </div>
                                <span className="text-xs font-medium">Marketing Assistant</span>
                                {msg.responseData?.research_id && (
                                  <Badge variant="outline" className="text-[10px] h-4 rounded-full bg-primary/10 border-primary/20">
                                    ID: {msg.responseData.research_id.slice(0, 6)}
                                  </Badge>
                                )}
                              </div>

                              {msg.responseData?.isGraph ? (
                                <>
                                  <div className="space-y-3">
                                    {msg.responseData.chart && (
                                      <div className="relative w-full rounded-xl border border-border bg-card p-2 shadow-sm overflow-x-auto">
                                        <Button
                                          type="button"
                                          variant="ghost"
                                          size="icon"
                                          className="absolute top-1.5 right-1.5 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground bg-background/50 backdrop-blur-sm"
                                          onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
                                          title="Expand graph"
                                        >
                                          <Maximize2 className="h-3.5 w-3.5" />
                                        </Button>
                                        <div className="pr-8 w-full min-w-[560px] sm:min-w-0">
                                          {renderChart(msg.responseData.chart)}
                                        </div>
                                      </div>
                                    )}
                                    {Array.isArray(msg.responseData.insights) && msg.responseData.insights.length > 0 && (
                                      <div className="pt-2 border-t border-border/50">
                                        <p className="text-xs font-semibold mb-2 flex items-center gap-1">
                                          <Sparkles className="h-3 w-3 text-amber-500" />
                                          Insights
                                        </p>
                                        <div className="overflow-x-auto rounded-lg border border-border/40 bg-background/30">
                                          <table className="w-full text-xs">
                                            <tbody>
                                              {msg.responseData.insights.map((insight, j) => (
                                                <tr key={j} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
                                                  <td className="py-1.5 px-2.5 pr-2 font-medium whitespace-nowrap">{insight.title || 'N/A'}</td>
                                                  <td className="py-1.5 px-2.5 text-muted-foreground">{insight.value || 'N/A'}</td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    )}
                                    <div className="flex flex-wrap gap-2 pt-2">
                                      <Button
                                        type="button"
                                        variant="outline"
                                        className="rounded-xl text-xs gap-1 bg-background/50 backdrop-blur-sm hover:bg-primary/10 hover:text-primary transition-all"
                                        size="sm"
                                        onClick={() => openSaveModal(
                                          currentMessages[currentMessages.indexOf(msg) - 1]?.content,
                                          msg.responseData.chartTitle,
                                          msg.responseData.chartType,
                                          msg.responseData.chart,
                                          msg.responseData.insights
                                        )}
                                      >
                                        <Save className="h-3.5 w-3.5" />
                                        Save Prompt
                                      </Button>
                                      <Button
                                        type="button"
                                        size="sm"
                                        onClick={() => handleAddToDashboard(
                                          currentMessages[currentMessages.indexOf(msg) - 1]?.content,
                                          msg.responseData.chartTitle,
                                          msg.responseData.chartType,
                                          msg.responseData.chart,
                                          msg.responseData.insights
                                        )}
                                        className="rounded-xl bg-gradient-to-r from-primary to-primary/80 text-primary-foreground text-xs gap-1 hover:from-primary/90 hover:to-primary/70 transition-all"
                                      >
                                        <LayoutDashboard className="h-3.5 w-3.5" />
                                        Add to dashboard
                                      </Button>
                                    </div>
                                  </div>
                                </>
                              ) : (
                                <>
                                  <div
                                    className="prose prose-base max-w-none dark:prose-invert [&_h2]:text-primary [&_strong]:font-semibold"
                                    dangerouslySetInnerHTML={{
                                      __html: markdownToHtml(msg.responseData?.answer || msg.content)
                                    }}
                                  />

                                  {msg.responseData?.insights?.length > 0 && (
                                    <motion.div
                                      initial={{ opacity: 0, y: 10 }}
                                      animate={{ opacity: 1, y: 0 }}
                                      className="mt-4 pt-4 border-t border-border/50"
                                    >
                                      <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                                        <Sparkles className="h-4 w-4 text-amber-500" />
                                        Key Insights
                                      </h4>
                                      <div className="grid grid-cols-2 gap-2">
                                        {msg.responseData.insights.map((insight, j) => (
                                          <motion.div
                                            key={j}
                                            initial={{ scale: 0.9, opacity: 0 }}
                                            animate={{ scale: 1, opacity: 1 }}
                                            transition={{ delay: j * 0.1 }}
                                            className="rounded-xl bg-gradient-to-br from-muted/50 to-muted/30 p-3 border shadow-sm hover:shadow-md transition-all"
                                          >
                                            <p className="text-xs font-medium text-muted-foreground mb-1">
                                              {insight.title || 'Metric'}
                                            </p>
                                            <p className="text-sm font-semibold">
                                              {insight.value || 'N/A'}
                                            </p>
                                          </motion.div>
                                        ))}
                                      </div>
                                    </motion.div>
                                  )}
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>

                  {loading && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex justify-start"
                    >
                      <div className="bg-gradient-to-r from-muted to-muted/50 border rounded-2xl px-4 py-3 flex items-center gap-3 shadow-md">
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                        >
                          <Loader2 className="h-4 w-4 text-primary" />
                        </motion.div>
                        <span className="text-sm">Analyzing your data...</span>
                      </div>
                    </motion.div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              )}
            </AnimatePresence>
          </CardContent>

          {/* Input form */}
          <div className="shrink-0   p-4 rounded-b-2xl">
            <form onSubmit={handleSubmit} className="space-y-3">
              <div className="relative">
                <div
                  className="absolute inset-0 rounded-[28px] pointer-events-none"
                  style={{
                    // background: 'linear-gradient(90deg, transparent 60%, rgba(10,37,64,0.38) 90%, rgba(14,39,71,0.22) 100%)',
                  }}
                />
                <div
                  className="relative z-[1] rounded-[28px] px-2.5 py-2.5 space-y-3"
                  style={{
                    background: '#0a0a0f',
                    border: '1.5px solid rgba(255,255,255,0.08)',
                    boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
                  }}
                >
                  <div className="flex gap-2.5 items-center">
                    <Select value={inputMode} onValueChange={setInputMode}>
                      <SelectTrigger
                        className="h-11 w-[145px] shrink-0 rounded-full text-sm font-medium focus:ring-0 focus:ring-offset-0 transition-all duration-200 px-4 gap-2 [&>svg]:opacity-70"
                        style={{
                          background: '#111118',
                          border: '1.5px solid rgba(139, 92, 246, 0.55)',
                          boxShadow: '0 0 16px rgba(139, 92, 246, 0.2), 0 0 4px rgba(139, 92, 246, 0.15)',
                          color: '#e2e2f0',
                        }}
                      >
                        {inputMode === 'search' ? (
                          <>
                            <Search className="h-4 w-4" style={{ color: '#a78bfa' }} />
                            <span>Search</span>
                          </>
                        ) : (
                          <>
                            <BarChart2 className="h-4 w-4" style={{ color: '#a78bfa' }} />
                            <span>Graph</span>
                          </>
                        )}
                      </SelectTrigger>
                      <SelectContent
                        className="rounded-xl"
                        style={{
                          background: '#161630',
                          border: '1px solid rgba(139, 92, 246, 0.25)',
                          color: '#e2e2f0',
                        }}
                      >
                        <SelectItem value="search" className="rounded-lg focus:bg-violet-600/20 focus:text-white">
                          <div className="flex items-center gap-2">
                            <Search className="h-4 w-4" />
                            <span>Search QA</span>
                          </div>
                        </SelectItem>
                        <SelectItem value="graph" className="rounded-lg focus:bg-violet-600/20 focus:text-white">
                          <div className="flex items-center gap-2">
                            <BarChart2 className="h-4 w-4" />
                            <span>Generate Graph</span>
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <div
                      className="flex-1 min-w-0 rounded-full flex items-center overflow-hidden"
                      style={{
                        background: '#0e0e14',
                        boxShadow: 'inset 2px 0 8px -2px rgba(139,92,246,0.35)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderLeftColor: 'rgba(139, 92, 246, 0.45)',
                      }}
                    >
                      <Textarea
                        ref={textareaRef}
                        placeholder={inputMode === 'search' ? 'Ask about campaign performance, ROI, channels...' : 'Describe the chart you want...'}
                        value={question}
                        onChange={(e) => {
                          setQuestion(e.target.value);
                          setSuggestedValue('__none__');
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit(e);
                          }
                        }}
                        rows={1}
                        disabled={loading}
                        className="flex-1 w-full min-h-[44px] h-11 max-h-32 resize-none border-0 bg-transparent text-sm py-3 px-4 text-white placeholder:text-white/30 focus-visible:ring-0 focus-visible:ring-offset-0"
                      />
                    </div>
                    <motion.div
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <Button
                        type="submit"
                        disabled={loading || !question.trim()}
                        size="icon"
                        className="h-11 w-11 shrink-0 rounded-full border-0 transition-all duration-200"
                        style={{
                          background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #5b21b6 100%)',
                          boxShadow: '0 0 16px rgba(124, 58, 237, 0.35), 0 2px 8px rgba(0,0,0,0.3)',
                          color: '#ffffff',
                        }}
                      >
                        {loading ? (
                          <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                          <Send className="h-5 w-5" />
                        )}
                      </Button>
                    </motion.div>
                  </div>
                  {/* Suggested questions */}
                  <div className="space-y-3 w-full pt-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-white/80 font-medium flex items-center gap-1">
                        <Sparkles className="h-3 w-3" style={{ color: '#a78bfa' }} />
                        Try these examples
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowSuggestions(!showSuggestions)}
                        className="h-7 w-7 p-0 rounded-full transition-all text-white/70 hover:text-white"
                        style={{
                          background: 'rgba(17,17,24,0.8)',
                          border: '1px solid rgba(139, 92, 246, 0.30)',
                          boxShadow: '0 0 12px rgba(139, 92, 246, 0.15)',
                        }}
                        title={showSuggestions ? 'Hide suggestions' : 'Show suggestions'}
                      >
                        {showSuggestions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </Button>
                    </div>

                    <AnimatePresence>
                      {showSuggestions && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="flex flex-wrap gap-2">
                            {(inputMode === 'graph' ? SUGGESTED_GRAPH_QUESTIONS : SUGGESTED_SEARCH_QUESTIONS).map((item, index) => (
                              <motion.button
                                key={item.text}
                                type="button"
                                initial={{ scale: 0.9, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                transition={{ delay: index * 0.05 }}
                                whileHover={{ scale: 1.05, y: -2 }}
                                whileTap={{ scale: 0.95 }}
                                onClick={() => setQuestion(item.text)}
                                className={cn(
                                  "text-xs text-white/90 rounded-xl px-3 py-1.5 text-left transition-all shadow-sm hover:shadow-md flex items-center gap-1.5 border",
                                  item.color
                                )}
                                style={{
                                  background: 'rgba(255,255,255,0.05)',
                                  borderColor: 'rgba(255,255,255,0.10)',
                                }}
                              >
                                <item.icon className={cn("h-3 w-3", item.color)} />
                                {item.text}
                              </motion.button>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </div>


              {/* Quick action chips */}
              {!selectedChatId && showSuggestions && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2"
                >
                  {SUGGESTED_QUESTIONS.slice(0, 2).map((group, groupIndex) => (
                    <div
                      key={groupIndex}
                      className="space-y-1.5 rounded-xl p-2 border"
                      style={{
                        background: 'rgba(255,255,255,0.04)',
                        borderColor: 'rgba(255,255,255,0.10)',
                      }}
                    >
                      <p className={cn("text-xs font-medium flex items-center gap-1 text-white/85", group.color)}>
                        <group.icon className="h-3 w-3" />
                        {group.group}
                      </p>
                      {group.options.slice(0, 2).map((prompt, i) => (
                        <Button
                          key={i}
                          variant="outline"
                          size="sm"
                          className={cn(
                            "w-full text-xs h-8 justify-start rounded-xl transition-all text-white/90 border hover:text-white",
                            group.color
                          )}
                          style={{
                            background: 'rgba(17,17,24,0.9)',
                            borderColor: 'rgba(139, 92, 246, 0.22)',
                          }}
                          onClick={() => setQuestion(prompt)}
                        >
                          {truncate(prompt, 20)}
                        </Button>
                      ))}
                    </div>
                  ))}
                </motion.div>
              )}
            </form>
          </div>

          {/* Expand graph dialog */}
          <Dialog open={!!expandedGraph} onOpenChange={(open) => !open && setExpandedGraph(null)}>
            <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-auto rounded-2xl">
              <DialogHeader className="shrink-0">
                <DialogTitle className="text-xl bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
                  {expandedGraph?.chartTitle || 'Graph'}
                </DialogTitle>
              </DialogHeader>
              <div className="min-h-[400px] py-4 overflow-x-auto">
                <div className="min-w-[720px] sm:min-w-0">
                  {expandedGraph?.chart && renderChart(expandedGraph.chart)}
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {/* Save prompt dialog */}
          <Dialog open={saveModalOpen} onOpenChange={(open) => {
            if (!open) {
              setSaveModalOpen(false);
              setSaveTitle('');
              setSaveTags('');
              setCurrentPromptData(null);
            }
          }}>
            <DialogContent className="max-w-md rounded-2xl">
              <DialogHeader>
                <DialogTitle className="text-xl bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">Save Prompt</DialogTitle>
                <DialogDescription>Save this graph prompt for quick access later.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="save-title">Title</Label>
                  <Input
                    id="save-title"
                    value={saveTitle}
                    onChange={(e) => setSaveTitle(e.target.value)}
                    placeholder="e.g. Monthly Campaign Performance"
                    className="rounded-xl border-border focus:border-primary/50 transition-all"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="save-tags">Tags (comma-separated)</Label>
                  <Input
                    id="save-tags"
                    value={saveTags}
                    onChange={(e) => setSaveTags(e.target.value)}
                    placeholder="e.g. analytics, campaigns"
                    className="rounded-xl border-border focus:border-primary/50 transition-all"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setSaveModalOpen(false)} className="rounded-xl">Cancel</Button>
                <Button onClick={handleSavePrompt} disabled={saving} className="rounded-xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70">
                  {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Prompt</>}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </Card>
      </motion.div>
    </motion.div>
  );
};

export default MarketingQA;