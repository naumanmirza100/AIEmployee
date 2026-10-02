import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import ChatMarkdown from '@/components/shared/ChatMarkdown';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import FrontlineInsightsPanel from './FrontlineInsightsPanel';
// FrontlineSidebar removed — its navigation now lives in the global app sidebar.
import FrontlineDocumentsTab from './FrontlineDocumentsTab';
import FrontlineKnowledgeQATab from './FrontlineKnowledgeQATab';
import KnowledgeView from './KnowledgeView';
import QueueView from './QueueView';
import InsightsView from './InsightsView';
import AutomationView from './AutomationView';
import SettingsView from './SettingsView';
import TicketTaskDialog from './TicketTaskDialog';
import { RetriageReviewDialog, TicketSuggestionDialog } from './AiSuggestionDialogs';
import { labelOf } from '@/utils/labels';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { 
  Loader2, 
  FileText, 
  Upload, 
  MessageSquare,
  Ticket,
  Search,
  Trash2,
  Headphones,
  CheckCircle2,
  XCircle,
  Send,
  Plus,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Bell,
  GitBranch,
  BarChart3,
  FileSearch,
  ListChecks,
  MoreHorizontal,
  StickyNote,
  ClipboardList,
  PauseCircle,
  PlayCircle,
  Moon,
  Sun,
  RefreshCw,
  Menu,
  Check,
  LayoutDashboard,
  Monitor,
  Copy,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Bot,
  Maximize2,
  User,
  CheckSquare,
  Square,
  X as XIcon,
} from 'lucide-react';
import FrontlineAIGraphs from './FrontlineAIGraphs';
import FrontlineTutorial, { resetTutorial } from './FrontlineTutorial';
import { TAB_TOURS, HINTS } from './frontlineTutorialSteps';
import InfoHint, { HintsProvider, useHints } from './InfoHint';
import { ElapsedTimer } from './chatShellUtils';
import { useBackgroundUpload } from '@/components/shared/BackgroundUploadManager';
import FrontlineFloatingChat from './FrontlineFloatingChat';
import { trackRecentlyViewed } from './frontlineLocalStore';
import {
  useTutorialNudge,
  tourAvailable, makeHoverLaunchHandlers,
} from './tourUtils';
import { GraduationCap, Eye, EyeOff } from 'lucide-react';
import frontlineAgentService from '@/services/frontlineAgentService';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import { renderChart } from '@/components/common/ChartRenderer';
import { FrontlineNotificationsTab } from './FrontlineNotificationsTab';
import { FrontlineWorkflowsTab } from './FrontlineWorkflowsTab';
import { HandoffQueueTab } from './HandoffQueueTab';
import { FrontlineAnalyticsTab } from './FrontlineAnalyticsTab';

// Document types for Q&A scope (must match backend Document.DOCUMENT_TYPE_CHOICES)
const DOCUMENT_TYPE_OPTIONS = [
  { value: 'knowledge_base', label: 'Knowledge Base' },
  { value: 'policy', label: 'Policy' },
  { value: 'procedure', label: 'Procedure' },
  { value: 'report', label: 'Report' },
  { value: 'ticket_attachment', label: 'Ticket Attachment' },
  { value: 'other', label: 'Other' },
];

// Tab bar restructure (FRONTLINE_AGENT_UX_REDESIGN.md):
//   * Visible surface = 6 tabs — Queue (agent day-to-day), Knowledge
//     (Documents + QA), Insights (Overview + Analytics + AI Graphs),
//     Automation (Workflows + notification templates), Settings (Widget +
//     preferences), plus Overview kept as its own tab for now until we
//     verify Insights covers what admins actually watch.
//   * `hidden: true` tabs are FILTERED out of the visible tab bar (both
//     desktop and mobile hamburger) but their TabsContent is still
//     rendered, so `?tab=qa` deep-links / bookmarks still work.
//   * Un-hiding a tab is a one-line flip. That's why we hide instead of
//     delete during the rollout — nothing is destroyed.
const FRONTLINE_TAB_ITEMS = [
  // Visible — the new 6-tab shape
  { value: 'queue', label: 'Queue', icon: Headphones },
  { value: 'knowledge', label: 'Knowledge', icon: FileText },
  { value: 'insights', label: 'Insights', icon: BarChart3 },
  { value: 'automation', label: 'Automation', icon: GitBranch },
  { value: 'settings', label: 'Settings', icon: Monitor },
  { value: 'overview', label: 'Overview', icon: LayoutDashboard },

  // Hidden — content still renders on direct URL navigation. Do NOT
  // reorder — visible tabs come first so the bar reads left-to-right in
  // intended priority.
  { value: 'documents', label: 'Documents', icon: FileText, hidden: true },
  { value: 'qa', label: 'Knowledge Q&A', icon: MessageSquare, hidden: true },
  { value: 'widget', label: 'Chat widget', icon: Monitor, hidden: true },
  { value: 'tickets', label: 'Tickets', icon: Ticket, hidden: true },
  { value: 'handoffs', label: 'Hand-offs', icon: Headphones, hidden: true },
  { value: 'notifications', label: 'Notifications', icon: Bell, hidden: true },
  { value: 'workflows', label: 'Workflows', icon: GitBranch, hidden: true },
  { value: 'analytics', label: 'Analytics', icon: BarChart3, hidden: true },
  { value: 'ai-graphs', label: 'AI Graphs', icon: Sparkles, hidden: true },
];

const FrontlineDashboard = () => {
  const { toast } = useToast();
  const { startUpload: startBackgroundUpload } = useBackgroundUpload();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  // Tab state lives in the URL as `?tab=...` so browser reload keeps you on
  // the tab you were on. Falls back to 'queue' (agent's day-to-day work) when
  // the param is missing or references an unknown tab — Overview is a menu,
  // Queue is where support agents actually work.
  const [searchParams, setSearchParams] = useSearchParams();
  const validTabValues = React.useMemo(() => FRONTLINE_TAB_ITEMS.map((t) => t.value), []);
  const rawTab = searchParams.get('tab');
  const activeTab = validTabValues.includes(rawTab) ? rawTab : 'queue';
  const setActiveTab = React.useCallback((v) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', v);
      // Switching top-level tab clears any nested sub-tab — otherwise
      // ?sub=tickets set on Queue would leak into Knowledge (which has
      // its own sub-tabs) and render a blank panel.
      next.delete('sub');
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  // Sub-tab state — Queue/Knowledge/Insights/Automation/Settings each have
  // nested sub-tabs. Same URL-based approach as PM: `?tab=X&sub=Y`. Sub-views
  // read `activeSubTab` and fall back to their own default when it's unset.
  const rawSubTab = searchParams.get('sub');
  const activeSubTab = rawSubTab || null;
  const setSubTab = React.useCallback((tabValue, subValue) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', tabValue);
      if (subValue) next.set('sub', subValue);
      else next.delete('sub');
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  // Hidden-tab set — filters tour steps and (later) drives the sidebar's
  // visible-items list.
  const hiddenTabValues = React.useMemo(
    () => new Set(FRONTLINE_TAB_ITEMS.filter((t) => t.hidden).map((t) => t.value)),
    []
  );

  // Sidebar collapsed state — persisted per browser so the user's preference
  // survives reloads. Read once on init (localStorage is sync).
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('frontline_sidebar_collapsed_v1') === '1'; }
    catch (_) { return false; }
  });
  const toggleSidebar = React.useCallback(() => {
    setSidebarCollapsed((v) => {
      const next = !v;
      try { localStorage.setItem('frontline_sidebar_collapsed_v1', next ? '1' : '0'); }
      catch (_) { /* ignore */ }
      return next;
    });
  }, []);

  // Sidebar items — top-level tabs with nested sub-items pointing to the
  // (currently hidden) legacy tabs that own the actual content. Once Chunks
  // B–F extract that content into the new views, sub-item values will move
  // from legacy hidden values (e.g. 'handoffs') to `?sub=handoffs` on the
  // parent — that swap is a one-liner per sub-item.
  const sidebarItems = React.useMemo(() => [
    {
      value: 'queue',
      label: 'Queue',
      icon: Headphones,
      subItems: [
        { value: 'handoffs', label: 'Hand-offs', icon: Headphones },
        { value: 'tickets',  label: 'Tickets',   icon: Ticket },
      ],
    },
    {
      value: 'knowledge',
      label: 'Knowledge',
      icon: FileText,
      subItems: [
        { value: 'documents', label: 'Documents',     icon: FileText },
        { value: 'qa',        label: 'Knowledge Q&A', icon: MessageSquare },
      ],
    },
    {
      value: 'insights',
      label: 'Insights',
      icon: BarChart3,
      subItems: [
        { value: 'analytics', label: 'Analytics', icon: BarChart3 },
        { value: 'ai-graphs', label: 'AI Graphs', icon: Sparkles },
      ],
    },
    {
      value: 'automation',
      label: 'Automation',
      icon: GitBranch,
      subItems: [
        { value: 'workflows',     label: 'Workflows',     icon: GitBranch },
        { value: 'notifications', label: 'Notifications', icon: Bell },
      ],
    },
    {
      value: 'settings',
      label: 'Settings',
      icon: Monitor,
      subItems: [
        { value: 'widget', label: 'Chat widget', icon: Monitor },
      ],
    },
    {
      value: 'overview',
      label: 'Overview',
      icon: LayoutDashboard,
    },
  ], []);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  // Which per-tab tour is currently open (null when none). Value = tab key.
  const [activeTabTour, setActiveTabTour] = useState(null);

  // First-login nudge: instead of auto-launching the tour (which overwhelms
  // new users), the "Take the Tour" header button flickers with a persistent
  // glow and a short-lived tooltip until the user takes the tour themselves.
  const { glow: spotlightTour, tooltip: spotlightTooltip, dismiss: dismissNudge } = useTutorialNudge();

  const handleReplayTutorial = () => {
    dismissNudge();
    resetTutorial();
    setTutorialOpen(true);
  };

  // Sibling tab-tour keys for the "skip all" checkbox in every tour instance.
  const flTabTourKeys = React.useMemo(() => Object.values(TAB_TOURS).map((t) => t.key), []);

  // Per-tab tours are no longer auto-launched. Each TabTourButton glows on
  // first visit to that tab until the user takes it.

  const handleReplayTabTour = (tabKey) => {
    const tour = TAB_TOURS[tabKey];
    if (!tour) return;
    resetTutorial(tour.key);
    setActiveTabTour(tabKey);
  };

  // Small button rendered inside each TabsContent header. Glows on first
  // visit to a tab whose tour hasn't been taken yet.
  const TabTourButton = ({ tabKey }) => {
    const tour = TAB_TOURS[tabKey];
    const { glow, dismiss } = useTutorialNudge(tour?.key);
    return (
      <button
        type="button"
        onClick={() => { dismiss(); handleReplayTabTour(tabKey); }}
        title={`Take a guided tour of the ${tour?.label || 'this'} tab`}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 text-amber-300 text-xs font-semibold hover:bg-amber-400/20 hover:text-amber-200 transition ${glow ? 'flt-tab-spotlight' : ''}`}
      >
        <GraduationCap className="h-3.5 w-3.5" />
        Tour this tab
      </button>
    );
  };

  // Toggle for showing/hiding all "!" InfoHint icons across the dashboard.
  // Reads from the same context every InfoHint consumes, so flipping this
  // state hides / re-shows every hint icon instantly and persistently.
  const HintsToggleButton = () => {
    const { enabled, toggle } = useHints();
    return (
      <button
        type="button"
        onClick={toggle}
        aria-pressed={enabled}
        title={enabled ? 'Hide the ! help icons on every element' : 'Show the ! help icons on every element'}
        className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold transition border ${
          enabled
            ? 'border-amber-400/40 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 hover:text-amber-200'
            : 'border-white/10 bg-white/[0.03] text-white/50 hover:bg-white/[0.06] hover:text-white/70'
        }`}
      >
        {enabled ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        <span>Hints: {enabled ? 'On' : 'Off'}</span>
      </button>
    );
  };
  
  // Document upload — progress state lives in the global BackgroundUpload
  // manager now, so this component only holds the dialog inputs.
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  
  // Knowledge Q&A (chat-based)
  const [chats, setChats] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [question, setQuestion] = useState('');
  const [answering, setAnswering] = useState(false);
  // Timestamp when the current Q&A request started, so the loading indicator
  // can render a live elapsed-time clock. Null when idle.
  const [answeringStartedAt, setAnsweringStartedAt] = useState(null);
  const [loadingChats, setLoadingChats] = useState(false);

  const INPUT_MODE_OPTIONS = [
    {
      value: 'search',
      label: 'Search',
      placeholder: 'Ask a question...',
      icon: Search,
    },
    {
      value: 'graph',
      label: 'Graph',
      placeholder: 'Describe the support graph you want to generate…',
      icon: BarChart3,
    },
  ];

  const [inputMode, setInputMode] = useState('search');
  const [expandedGraph, setExpandedGraph] = useState(null); // { chart, chartTitle }
  const selectedMode = INPUT_MODE_OPTIONS.find((m) => m.value === inputMode) || INPUT_MODE_OPTIONS[0];
  const SelectedModeIcon = selectedMode.icon;

  const [showSidebarSearch, setShowSidebarSearch] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [showChatHistory, setShowChatHistory] = useState(true);
  const messagesEndRef = useRef(null);
  // Q&A scope: restrict answers to document type(s) or specific documents
  const [qaScopeMode, setQaScopeMode] = useState('all'); // 'all' | 'type' | 'documents'
  const [qaScopeDocumentTypes, setQaScopeDocumentTypes] = useState([]); // e.g. ['policy', 'knowledge_base']
  const [qaScopeDocumentIds, setQaScopeDocumentIds] = useState([]);
  const [qaDocumentsList, setQaDocumentsList] = useState([]); // full list for "Specific documents" selector
  const [qaDocumentsLoading, setQaDocumentsLoading] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState({}); // { 'chatId-messageIndex': true } to avoid double submit
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  // Chat widget tab
  const [widgetKey, setWidgetKey] = useState('');
  const [widgetConfigLoading, setWidgetConfigLoading] = useState(false);
  const [allowedOrigins, setAllowedOrigins] = useState('');
  const [allowedOriginsSaving, setAllowedOriginsSaving] = useState(false);
  // Extra theming knobs (EW1). When all are blank/null, the widget JS uses its
  // built-in defaults — these are purely additive customisations.
  const [widgetTheme, setWidgetTheme] = useState({
    primary_color: '', font_family: '', border_radius: '',
    header_bg: '', header_text_color: '',
    bubble_bg_user: '', bubble_bg_agent: '',
    css_overrides: '',
  });
  const [themeSaving, setThemeSaving] = useState(false);
  
  // Ticket creation
  const [showTicketDialog, setShowTicketDialog] = useState(false);
  // The AI's suggestions, waiting for a person: a new ticket's knowledge-base
  // answer, and a Re-triage proposal.
  const [ticketSuggestion, setTicketSuggestion] = useState(null);
  const [retriageProposal, setRetriageProposal] = useState(null);
  const [suggestionBusy, setSuggestionBusy] = useState(false);
  const [ticketTitle, setTicketTitle] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [creatingTicket, setCreatingTicket] = useState(false);

  // Document processing result (summarize / extract)
  const [docResultDialog, setDocResultDialog] = useState({ open: false, type: null, title: '', content: null, loading: false });
  // Per-doc inline summary cache + expand toggle for the redesigned card grid.
  // Shape: { [docId]: { summary, loading, expanded, error } }
  const [docSummaries, setDocSummaries] = useState({});

  // Tickets list (filter + pagination)
  const [ticketsList, setTicketsList] = useState([]);
  // The ticket being turned into a project task (dialog open), or null.
  const [taskDialogTicket, setTaskDialogTicket] = useState(null);
  const [ticketsLoading, setTicketsLoading] = useState(false);

  // Ticket lifecycle: notes dialog + per-row busy flag
  const [notesDialog, setNotesDialog] = useState({ open: false, ticketId: null, ticketTitle: '', notes: [], loading: false });
  const [noteDraft, setNoteDraft] = useState('');
  const [ticketBusyId, setTicketBusyId] = useState(null);
  // Customer 360 panel — shows contact info, prior ticket count, and recent tickets for the ticket's customer
  const [customerDialog, setCustomerDialog] = useState({
    open: false, ticketId: null, ticketTitle: '',
    loading: false, contact: null, stats: null,
  });
  const [ticketFilters, setTicketFilters] = useState({ status: '', priority: '', category: '', date_from: '', date_to: '' });
  const [ticketsPagination, setTicketsPagination] = useState({ page: 1, limit: 20, total: 0, total_pages: 1 });
  const [ticketsAging, setTicketsAging] = useState(null); // { breached: [], at_risk: [], count_breached, count_at_risk }
  // Bulk-update selection state. Set of ticket IDs. Cleared when filters change
  // so a selection from a previous page can't accidentally be applied to a
  // different list.
  const [selectedTicketIds, setSelectedTicketIds] = useState(new Set());
  const [bulkActionDialog, setBulkActionDialog] = useState({ open: false, field: null, value: '' });
  const [bulkApplying, setBulkApplying] = useState(false);
  const toggleTicketSelected = (id) => {
    setSelectedTicketIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAllTicketsOnPage = () => {
    setSelectedTicketIds((prev) => {
      const allOnPage = ticketsList.every((t) => prev.has(t.id));
      if (allOnPage) {
        const next = new Set(prev);
        ticketsList.forEach((t) => next.delete(t.id));
        return next;
      }
      const next = new Set(prev);
      ticketsList.forEach((t) => next.add(t.id));
      return next;
    });
  };
  const clearTicketSelection = () => setSelectedTicketIds(new Set());
  const handleBulkApply = async () => {
    const ids = Array.from(selectedTicketIds);
    const { field, value } = bulkActionDialog;
    if (!ids.length || !field || !value) return;
    setBulkApplying(true);
    try {
      const payload = { ids };
      if (field === 'status') payload.status = value;
      else if (field === 'priority') payload.priority = value;
      else if (field === 'category') payload.category = value;
      const res = await frontlineAgentService.bulkUpdateTickets(payload);
      const data = res?.data || {};
      const updated = data.updated || [];
      const skipped = data.skipped || [];
      toast({
        title: `Bulk update: ${updated.length} updated`,
        description: skipped.length
          ? `${skipped.length} skipped — see console for details.`
          : (data.not_found?.length ? `${data.not_found.length} not found.` : 'All matching tickets updated.'),
      });
      if (skipped.length) console.warn('Bulk update skipped:', skipped);
      // Refresh list so badges reflect new state.
      loadTickets?.();
      clearTicketSelection();
      setBulkActionDialog({ open: false, field: null, value: '' });
    } catch (e) {
      toast({ title: 'Bulk update failed', description: e.message, variant: 'destructive' });
    } finally {
      setBulkApplying(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
    
    // Check for dark mode
    const checkDarkMode = () => {
      setIsDarkMode(
        document.documentElement.classList.contains('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches
      );
    };
    
    checkDarkMode();
    
    // Watch for dark mode changes
    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    });
    
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', checkDarkMode);
    
    return () => {
      observer.disconnect();
      mediaQuery.removeEventListener('change', checkDarkMode);
    };
  }, []);

  // Load widget config when Chat widget tab is selected
  useEffect(() => {
    if (activeTab !== 'widget') return;
    let cancelled = false;
    setWidgetConfigLoading(true);
    frontlineAgentService.getFrontlineWidgetConfig()
      .then((res) => {
        if (cancelled || res?.status !== 'success') return;
        if (res?.data?.widget_key) setWidgetKey(res.data.widget_key);
        setAllowedOrigins(res?.data?.allowed_origins || '');
        const theme = res?.data?.config?.theme || {};
        setWidgetTheme({
          primary_color: theme.primary_color || '',
          font_family: theme.font_family || '',
          border_radius: theme.border_radius || '',
          header_bg: theme.header_bg || '',
          header_text_color: theme.header_text_color || '',
          bubble_bg_user: theme.bubble_bg_user || '',
          bubble_bg_agent: theme.bubble_bg_agent || '',
          css_overrides: theme.css_overrides || '',
        });
      })
      .catch(() => { if (!cancelled) { setWidgetKey(''); setAllowedOrigins(''); } })
      .finally(() => { if (!cancelled) setWidgetConfigLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab]);

  const handleSaveAllowedOrigins = async () => {
    setAllowedOriginsSaving(true);
    try {
      const res = await frontlineAgentService.updateFrontlineWidgetConfig({
        allowedOrigins: allowedOrigins.trim(),
      });
      if (res?.status === 'success') {
        setAllowedOrigins(res?.data?.allowed_origins ?? allowedOrigins.trim());
        toast({ title: 'Allowed origins saved' });
      } else {
        throw new Error(res?.message || 'Save failed');
      }
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setAllowedOriginsSaving(false);
    }
  };

  const handleSaveTheme = async () => {
    setThemeSaving(true);
    try {
      // Only send non-empty values so blank inputs fall back to backend defaults.
      const themePatch = Object.fromEntries(
        Object.entries(widgetTheme).filter(([, v]) => v !== '' && v != null),
      );
      const res = await frontlineAgentService.updateFrontlineWidgetConfig({
        config: { theme: themePatch },
      });
      if (res?.status === 'success') {
        toast({ title: 'Theme saved', description: 'Embed widget will pick up new colours on next load.' });
      } else {
        throw new Error(res?.message || 'Save failed');
      }
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    } finally {
      setThemeSaving(false);
    }
  };

  // Load the document list eagerly when the Q&A tab is opened, and cache it.
  // Previously we only fetched after the user switched to "Specific documents"
  // mode, which produced a noticeable cold-start delay in the dropdown.
  useEffect(() => {
    if (activeTab !== 'qa') return;
    // Already loaded? Skip — the list rarely changes within a session, and
    // any doc uploaded during the session bumps `documents` state which we
    // include below.
    if (qaDocumentsList.length > 0) return;
    let cancelled = false;
    (async () => {
      setQaDocumentsLoading(true);
      try {
        const res = await frontlineAgentService.listDocuments({ limit: 200 });
        const list = res?.data?.documents ?? (Array.isArray(res?.data) ? res.data : []);
        if (!cancelled) setQaDocumentsList(list);
      } catch {
        if (!cancelled) setQaDocumentsList([]);
      } finally {
        if (!cancelled) setQaDocumentsLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Refresh the doc list when the top-level `documents` state changes
  // (e.g. after upload), so newly-added docs appear in the scope dropdown.
  useEffect(() => {
    if (activeTab !== 'qa') return;
    if (!documents || documents.length === 0) return;
    // Merge: existing list stays, new ones are added by id.
    setQaDocumentsList((prev) => {
      const seen = new Set(prev.map((d) => d.id));
      const additions = documents.filter((d) => !seen.has(d.id));
      return additions.length ? [...additions, ...prev] : prev;
    });
  }, [documents, activeTab]);

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const response = await frontlineAgentService.getFrontlineDashboard();
      if (response.status === 'success') {
        setStats(response.data.stats);
        setDocuments(response.data.recent_documents || []);
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to load dashboard',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Enqueue the upload with the global BackgroundUploadManager. The dialog
  // closes immediately; the bottom-right floating pill shows progress and
  // the user can navigate away or upload more files without blocking.
  const handleFileUpload = () => {
    if (!uploadFile) {
      toast({
        title: 'Error',
        description: 'Please select a file to upload',
        variant: 'destructive',
      });
      return;
    }
    const file = uploadFile;
    const title = uploadTitle || file.name;
    const description = uploadDescription;

    startBackgroundUpload({
      title,
      agent: 'frontline',
      upload: (onProgress) => frontlineAgentService.uploadDocument(
        file, title, description, 'knowledge_base', { onProgress },
      ),
      poll: (documentId) => frontlineAgentService.getDocumentStatus(documentId),
      onDone: () => fetchDashboard(),
    });

    setShowUploadDialog(false);
    setUploadFile(null);
    setUploadTitle('');
    setUploadDescription('');
  };

  // Process a failed document again (including one the server marked failed
  // after it got stuck). Same background pill and polling as an upload.
  const handleRetryDocument = (doc) => {
    setDocuments((prev) => prev.map((d) => (d.id === doc.id
      ? { ...d, processing_status: 'pending', processing_error: null } : d)));
    startBackgroundUpload({
      title: `Retry: ${doc.title}`,
      agent: 'frontline',
      upload: () => frontlineAgentService.reingestDocument(doc.id),
      poll: (documentId) => frontlineAgentService.getDocumentStatus(documentId),
      onDone: () => fetchDashboard(),
    });
  };

  const handleDeleteDocument = async (documentId) => {
    if (!confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      const response = await frontlineAgentService.deleteDocument(documentId);
      if (response.status === 'success') {
        toast({
          title: 'Success!',
          description: 'Document deleted successfully',
        });
        fetchDashboard();
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to delete document',
        variant: 'destructive',
      });
    }
  };

  const handleSummarizeDocument = async (doc) => {
    trackRecentlyViewed({ kind: 'document', id: doc.id, title: doc.title || `Document #${doc.id}` });
    setDocResultDialog({ open: true, type: 'summary', title: `Summary: ${doc.title}`, content: null, loading: true });
    try {
      const response = await frontlineAgentService.summarizeDocument(doc.id, {});
      const summary = response?.data?.summary ?? response?.summary;
      setDocResultDialog((prev) => ({ ...prev, content: summary || 'No summary generated.', loading: false }));
    } catch (error) {
      setDocResultDialog((prev) => ({ ...prev, content: `Error: ${error.message || 'Summarization failed'}`, loading: false }));
    }
  };

  const handleExtractDocument = async (doc) => {
    setDocResultDialog({ open: true, type: 'extract', title: `Extracted data: ${doc.title}`, content: null, loading: true });
    try {
      const response = await frontlineAgentService.extractDocument(doc.id, {});
      const extracted = response?.data?.extracted ?? response?.extracted;
      const content = typeof extracted === 'object' ? JSON.stringify(extracted, null, 2) : (extracted || 'No data extracted.');
      setDocResultDialog((prev) => ({ ...prev, content, loading: false }));
    } catch (error) {
      setDocResultDialog((prev) => ({ ...prev, content: apiErrorMessage(error, 'Extraction failed'), loading: false }));
    }
  };

  const handleToggleDocOutdated = async (doc, makeOutdated) => {
    try {
      if (makeOutdated) {
        await frontlineAgentService.markFrontlineDocumentOutdated(doc.id);
        toast({ title: 'Document marked outdated', description: 'Excluded from knowledge retrieval until restored.' });
      } else {
        await frontlineAgentService.unmarkFrontlineDocumentOutdated(doc.id);
        toast({ title: 'Document restored', description: 'Back in knowledge retrieval.' });
      }
      setDocuments((arr) => arr.map((x) => x.id === doc.id ? { ...x, is_outdated: makeOutdated } : x));
    } catch (e) {
      toast({
        title: makeOutdated ? 'Mark-outdated failed' : 'Restore failed',
        description: e.message,
        variant: 'destructive',
      });
    }
  };

  /** Inline summary toggle for the Documents card grid.
   *  First click on a card fetches the summary (short — 3 sentences) and expands.
   *  Subsequent clicks just flip expanded without re-fetching. */
  const toggleDocSummary = async (doc) => {
    const cur = docSummaries[doc.id];
    if (cur?.summary) {
      setDocSummaries((m) => ({ ...m, [doc.id]: { ...cur, expanded: !cur.expanded } }));
      return;
    }
    setDocSummaries((m) => ({ ...m, [doc.id]: { summary: null, loading: true, expanded: true, error: null } }));
    try {
      const response = await frontlineAgentService.summarizeDocument(doc.id, { max_sentences: 3 });
      const summary = response?.data?.summary ?? response?.summary ?? '';
      setDocSummaries((m) => ({ ...m, [doc.id]: { summary, loading: false, expanded: true, error: null } }));
    } catch (error) {
      setDocSummaries((m) => ({
        ...m,
        [doc.id]: { summary: null, loading: false, expanded: true, error: error.message || 'Failed to summarize' },
      }));
    }
  };

  /** Normalize chat from API shape to component shape */
  const normalizeChat = (chat) => {
    if (!chat) return chat;
    return {
      ...chat,
      id: String(chat.id),
      title: chat.title || 'Chat',
      messages: chat.messages || [],
      updatedAt: chat.updatedAt || chat.timestamp,
      timestamp: chat.updatedAt || chat.timestamp,
    };
  };

  const loadChatsFromApi = async () => {
    try {
      setLoadingChats(true);
      const res = await frontlineAgentService.listQAChats();
      if (res.status === 'success' && res.data) {
        setChats((res.data || []).map(normalizeChat));
      } else {
        setChats([]);
      }
    } catch (err) {
      console.error('Load QA chats error:', err);
      setChats([]);
    } finally {
      setLoadingChats(false);
    }
  };

  const loadTickets = async () => {
    try {
      setTicketsLoading(true);
      const params = { page: ticketsPagination.page, limit: ticketsPagination.limit };
      if (ticketFilters.status) params.status = ticketFilters.status;
      if (ticketFilters.priority) params.priority = ticketFilters.priority;
      if (ticketFilters.category) params.category = ticketFilters.category;
      if (ticketFilters.date_from) params.date_from = ticketFilters.date_from;
      if (ticketFilters.date_to) params.date_to = ticketFilters.date_to;
      const res = await frontlineAgentService.listTickets(params);
      if (res.status === 'success') {
        setTicketsList(res.data || []);
        if (res.pagination) setTicketsPagination(res.pagination);
      } else {
        setTicketsList([]);
      }
    } catch (err) {
      console.error('Load tickets error:', err);
      setTicketsList([]);
      toast({ title: 'Error', description: err.message || 'Failed to load tickets', variant: 'destructive' });
    } finally {
      setTicketsLoading(false);
    }
  };

  const loadTicketsAging = async () => {
    try {
      const res = await frontlineAgentService.listTicketsAging();
      if (res.status === 'success' && res.data) setTicketsAging(res.data);
      else setTicketsAging(null);
    } catch {
      setTicketsAging(null);
    }
  };

  useEffect(() => {
    if (activeTab === 'qa') {
      loadChatsFromApi();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'tickets') {
      loadTickets();
      loadTicketsAging();
    }
  }, [activeTab, ticketFilters.status, ticketFilters.priority, ticketFilters.category, ticketFilters.date_from, ticketFilters.date_to, ticketsPagination.page]);

  // ---------- Ticket lifecycle handlers (notes / snooze / SLA / re-triage) ----------
  const openNotesDialog = async (ticket) => {
    setNotesDialog({ open: true, ticketId: ticket.id, ticketTitle: ticket.title, notes: [], loading: true });
    setNoteDraft('');
    try {
      const res = await frontlineAgentService.listTicketNotes(ticket.id);
      setNotesDialog((prev) => ({ ...prev, notes: res?.data || [], loading: false }));
    } catch (err) {
      console.error('Load notes failed', err);
      setNotesDialog((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load notes', variant: 'destructive' });
    }
  };

  const submitNote = async () => {
    const body = noteDraft.trim();
    if (!body || !notesDialog.ticketId) return;
    try {
      const res = await frontlineAgentService.createTicketNote(notesDialog.ticketId, body, true);
      setNotesDialog((prev) => ({ ...prev, notes: [...prev.notes, res.data] }));
      setNoteDraft('');
      // Bump the row's notes_count in the table
      setTicketsList((list) => list.map((t) => (t.id === notesDialog.ticketId
        ? { ...t, notes_count: (t.notes_count || 0) + 1 }
        : t)));
    } catch (err) {
      console.error('Add note failed', err);
      toast({ title: 'Failed to add note', variant: 'destructive' });
    }
  };

  const deleteNote = async (noteId) => {
    try {
      await frontlineAgentService.deleteTicketNote(notesDialog.ticketId, noteId);
      setNotesDialog((prev) => ({ ...prev, notes: prev.notes.filter((n) => n.id !== noteId) }));
      setTicketsList((list) => list.map((t) => (t.id === notesDialog.ticketId
        ? { ...t, notes_count: Math.max(0, (t.notes_count || 0) - 1) }
        : t)));
    } catch (err) {
      console.error('Delete note failed', err);
      toast({ title: 'Failed to delete note', variant: 'destructive' });
    }
  };

  // Delete the contact currently shown in the Customer-360 dialog. Tickets
  // that reference this contact stay (the FK is set null on delete); the
  // contact's notes cascade away. Confirmation is delegated to a custom
  // dialog instead of window.confirm to match the rest of the dashboard UX.
  const [deleteContactConfirm, setDeleteContactConfirm] = useState({ open: false, busy: false });
  const handleDeleteContact = async () => {
    const contact = customerDialog.contact;
    if (!contact) return;
    setDeleteContactConfirm((d) => ({ ...d, busy: true }));
    try {
      await frontlineAgentService.deleteContact(contact.id);
      toast({ title: 'Contact deleted', description: contact.email });
      setDeleteContactConfirm({ open: false, busy: false });
      setCustomerDialog((prev) => ({ ...prev, open: false, contact: null }));
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message || 'Unknown error', variant: 'destructive' });
      setDeleteContactConfirm((d) => ({ ...d, busy: false }));
    }
  };

  // Customer 360: fetch contact + stats for a ticket; backend 404s if ticket has no contact yet.
  const openCustomerDialog = async (ticket) => {
    setCustomerDialog({
      open: true, ticketId: ticket.id, ticketTitle: ticket.title,
      loading: true, contact: null, stats: null,
    });
    try {
      const res = await frontlineAgentService.getTicketContext(ticket.id);
      const data = res?.data || {};
      setCustomerDialog((prev) => ({
        ...prev,
        loading: false,
        contact: data.contact || null,
        stats: data.stats || null,
      }));
    } catch (err) {
      console.error('Load customer context failed', err);
      setCustomerDialog((prev) => ({ ...prev, loading: false }));
      toast({ title: 'Failed to load customer context', variant: 'destructive' });
    }
  };

  const handleSnooze = async (ticket, hours) => {
    setTicketBusyId(ticket.id);
    try {
      const res = await frontlineAgentService.snoozeTicket(ticket.id, { hours });
      setTicketsList((list) => list.map((t) => (t.id === ticket.id
        ? { ...t, snoozed_until: res.data.snoozed_until, is_snoozed: true }
        : t)));
      toast({ title: `Ticket snoozed for ${hours}h` });
    } catch (err) {
      toast({ title: 'Snooze failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const handleUnsnooze = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      await frontlineAgentService.unsnoozeTicket(ticket.id);
      setTicketsList((list) => list.map((t) => (t.id === ticket.id
        ? { ...t, snoozed_until: null, is_snoozed: false }
        : t)));
      toast({ title: 'Ticket unsnoozed' });
    } catch (err) {
      toast({ title: 'Unsnooze failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const handleToggleSlaPause = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      const fn = ticket.is_sla_paused ? frontlineAgentService.resumeTicketSla : frontlineAgentService.pauseTicketSla;
      const res = await fn(ticket.id);
      setTicketsList((list) => list.map((t) => (t.id === ticket.id ? {
        ...t,
        sla_paused_at: res.data.sla_paused_at || null,
        is_sla_paused: !!res.data.sla_paused_at,
        sla_due_at: res.data.sla_due_at ?? t.sla_due_at,
      } : t)));
      toast({ title: ticket.is_sla_paused ? 'SLA resumed' : 'SLA paused' });
    } catch (err) {
      toast({ title: 'SLA toggle failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  // Re-triage asks the AI, then shows what it suggests; nothing changes
  // until "Apply changes".
  const handleRetriage = async (ticket) => {
    setTicketBusyId(ticket.id);
    try {
      const res = await frontlineAgentService.retriageTicket(ticket.id);
      setRetriageProposal({ ticket, data: res.data || {} });
    } catch (err) {
      toast({ title: 'Re-triage failed', variant: 'destructive' });
    } finally {
      setTicketBusyId(null);
    }
  };

  const applyRetriage = async () => {
    const { ticket, data } = retriageProposal;
    setSuggestionBusy(true);
    try {
      const res = await frontlineAgentService.applyRetriage(ticket.id, data);
      const saved = res.data || {};
      setTicketsList((list) => list.map((t) => (t.id === ticket.id ? {
        ...t,
        category: saved.new_category ?? t.category,
        priority: saved.new_priority ?? t.priority,
        last_triaged_at: saved.last_triaged_at ?? t.last_triaged_at,
      } : t)));
      setRetriageProposal(null);
      toast({ title: 'Re-triage applied', description: `#${ticket.id} updated.` });
    } catch (err) {
      toast({ title: 'Could not apply the re-triage', description: err.message, variant: 'destructive' });
    } finally {
      setSuggestionBusy(false);
    }
  };

  const resolveWithSuggestion = async () => {
    setSuggestionBusy(true);
    try {
      await frontlineAgentService.updateTicket(ticketSuggestion.ticketId,
        { status: 'resolved', resolution: ticketSuggestion.text });
      toast({ title: 'Ticket resolved', description: `#${ticketSuggestion.ticketId} resolved with the suggested answer.` });
      setTicketSuggestion(null);
      fetchDashboard();
      if (activeTab === 'tickets') { loadTickets(); loadTicketsAging(); }
    } catch (err) {
      toast({ title: 'Could not resolve the ticket', description: err.message, variant: 'destructive' });
    } finally {
      setSuggestionBusy(false);
    }
  };

  const selectedChat = chats.find((c) => c.id === selectedChatId);
  const currentMessages = selectedChat?.messages ?? [];
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  const currentTab = FRONTLINE_TAB_ITEMS.find((item) => item.value === activeTab) || FRONTLINE_TAB_ITEMS[0];

  const newChat = () => {
    setSelectedChatId(null);
    setQuestion('');
  };

  const deleteChat = async (e, chatId) => {
    e.stopPropagation();
    // UX-13: confirm before wiping a Q&A chat thread — the trash icon
    // used to delete silently on the first click.
    const chat = chats.find((c) => c.id === chatId);
    const label = chat?.title ? `"${chat.title}"` : 'this chat';
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;
    try {
      const res = await frontlineAgentService.deleteQAChat(chatId);
      if (res.status === 'success') {
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (selectedChatId === chatId) setSelectedChatId(null);
        toast({ title: 'Chat deleted' });
      } else {
        throw new Error(res.message || 'Failed to delete chat');
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Could not delete chat', variant: 'destructive' });
    }
  };

  const handleAskQuestion = async (e) => {
    e?.preventDefault?.();
    if (!question.trim()) {
      toast({ title: 'Error', description: 'Please enter a question', variant: 'destructive' });
      return;
    }
    const q = question.trim();
    const scopeOptions = {};
    if (qaScopeMode === 'type' && qaScopeDocumentTypes.length > 0) scopeOptions.scope_document_type = qaScopeDocumentTypes;
    if (qaScopeMode === 'documents' && qaScopeDocumentIds.length > 0) scopeOptions.scope_document_ids = qaScopeDocumentIds;
    try {
      setAnswering(true);
      // Measure round-trip latency so the UI can render "answered in X.Xs".
      // Uses performance.now() for millisecond precision. We also mirror the
      // start into React state so the live thinking-clock can tick against it.
      const startedAt = (typeof performance !== 'undefined' && performance.now)
        ? performance.now() : Date.now();
      setAnsweringStartedAt(startedAt);
      const userMsg = { role: 'user', content: q };
      let assistantMsg;

      if (inputMode === 'graph') {
        const graphRes = await frontlineAgentService.generateFrontlineGraph(q);
        if (graphRes.status === 'success' && graphRes.data) {
          const { chart, insights } = graphRes.data;
          assistantMsg = {
            role: 'assistant',
            content: chart?.title ? `**${chart.title}**` : 'Chart generated',
            responseData: {
              isGraph: true,
              chart,
              insights,
              chartTitle: chart?.title,
              chartType: chart?.type,
            },
          };
        } else {
          throw new Error(graphRes.message || 'Failed to generate graph');
        }
      } else {
        // Streaming path — insert a placeholder assistant message into the
        // current chat, mutate its `.content` as tokens arrive, then persist
        // to backend after the stream completes. This gives sub-second time
        // to first visible token instead of 5-10s waiting for a full reply.
        const placeholder = {
          role: 'assistant',
          content: '',
          streaming: true,
          responseData: {},
        };
        // Show placeholder in the currently-selected chat so tokens render live.
        const streamChatId = selectedChatId;
        if (streamChatId) {
          setChats((prev) => prev.map((c) => (
            c.id === streamChatId
              ? { ...c, messages: [...(c.messages || []), userMsg, placeholder] }
              : c
          )));
        }
        const patchStreamingMsg = (updater) => {
          if (!streamChatId) return;
          setChats((prev) => prev.map((c) => {
            if (c.id !== streamChatId) return c;
            const msgs = c.messages ? c.messages.slice() : [];
            const lastIdx = msgs.length - 1;
            if (lastIdx < 0) return c;
            msgs[lastIdx] = updater(msgs[lastIdx]);
            return { ...c, messages: msgs };
          }));
        };

        let accumulated = '';
        let metaEvent = null;
        let doneEvent = null;
        try {
          await frontlineAgentService.knowledgeQAStream(q, {
            ...scopeOptions,
            onMeta: (meta) => {
              metaEvent = meta;
              patchStreamingMsg((m) => ({
                ...m,
                responseData: {
                  ...(m.responseData || {}),
                  has_verified_info: meta.has_verified_info,
                  source: meta.source || 'Knowledge Base',
                  type: meta.type_hint || 'general',
                  document_id: meta.document_id ?? null,
                  citations: meta.citations || [],
                  cache_hit: !!meta.cache_hit,
                },
              }));
            },
            onToken: (piece) => {
              accumulated += (piece || '');
              patchStreamingMsg((m) => ({ ...m, content: accumulated }));
            },
            onDone: (done) => { doneEvent = done; },
          });
        } catch (streamErr) {
          throw streamErr;
        }
        const answerText = (doneEvent && doneEvent.answer) || accumulated || 'No answer available.';
        assistantMsg = {
          role: 'assistant',
          content: answerText,
          responseData: {
            answer: answerText,
            has_verified_info: metaEvent?.has_verified_info || false,
            source: metaEvent?.source || 'Knowledge Base',
            type: metaEvent?.type_hint || 'general',
            document_id: metaEvent?.document_id ?? null,
            citations: metaEvent?.citations || [],
            cache_hit: !!(doneEvent?.cache_hit),
            timing_ms: doneEvent?.timing_ms || null,
          },
        };
        // Flip the placeholder out of streaming mode so the badge renders
        // instead of the blinking cursor. The persist step just below will
        // replace this chat's messages with server-normalised data anyway,
        // but this makes the transition smoother.
        patchStreamingMsg(() => ({ ...assistantMsg }));
      }

      const endedAt = (typeof performance !== 'undefined' && performance.now)
        ? performance.now() : Date.now();
      if (assistantMsg) {
        assistantMsg.responseData = {
          ...(assistantMsg.responseData || {}),
          responseTimeMs: Math.round(endedAt - startedAt),
        };
      }

      const title = q.slice(0, 40);
      if (selectedChatId) {
        const existing = chats.find((c) => c.id === selectedChatId);
        if (existing) {
          const updRes = await frontlineAgentService.updateQAChat(selectedChatId, {
            messages: [userMsg, assistantMsg],
            title: existing.title || title,
          });
          if (updRes.status === 'success' && updRes.data) {
            const updatedChat = normalizeChat(updRes.data);
            setChats((prev) => [updatedChat, ...prev.filter((c) => c.id !== selectedChatId)]);
          } else throw new Error(updRes.message || 'Failed to save chat');
        } else {
          const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
          if (createRes.status === 'success' && createRes.data) {
            const newChatData = normalizeChat(createRes.data);
            setChats((prev) => [newChatData, ...prev]);
            setSelectedChatId(newChatData.id);
          } else throw new Error(createRes.message || 'Failed to create chat');
        }
      } else {
        const createRes = await frontlineAgentService.createQAChat({ title, messages: [userMsg, assistantMsg] });
        if (createRes.status === 'success' && createRes.data) {
          const newChatData = normalizeChat(createRes.data);
          setChats((prev) => [newChatData, ...prev]);
          setSelectedChatId(newChatData.id);
        } else throw new Error(createRes.message || 'Failed to create chat');
      }
      setQuestion('');
      setTimeout(scrollToBottom, 100);
    } catch (error) {
      toast({ title: 'Error', description: apiErrorMessage(error, 'Failed to get answer'), variant: 'destructive' });
    } finally {
      setAnswering(false);
      setAnsweringStartedAt(null);
    }
  };

  const truncate = (s, n = 50) => (s.length <= n ? s : s.slice(0, n) + '…');
  const formatDate = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const handleCreateTicket = async () => {
    if (!ticketDescription.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a description',
        variant: 'destructive',
      });
      return;
    }

    try {
      setCreatingTicket(true);
      const response = await frontlineAgentService.createTicket(
        ticketTitle || 'Support Request',
        ticketDescription
      );

      if (response.status === 'success' && response.data) {
        const created = response.data;
        if (created.suggested_resolution) {
          // The ticket is open; offer the knowledge base's answer.
          setTicketSuggestion({ ticketId: created.ticket_id, text: created.suggested_resolution });
        } else {
          toast({ title: 'Ticket created', description: `#${created.ticket_id} is open.` });
        }
        setShowTicketDialog(false);
        setTicketTitle('');
        setTicketDescription('');
        fetchDashboard();
        if (activeTab === 'tickets') { loadTickets(); loadTicketsAging(); }
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to create ticket',
        variant: 'destructive',
      });
    } finally {
      setCreatingTicket(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  // Prop-bundle for the extracted FrontlineKnowledgeQATab. Bundled here so
  // the two mount points (KnowledgeView's Q&A sub-tab AND the hidden legacy
  // `?tab=qa` TabsContent) stay identical — one change fixes both places.
  // Deliberately NOT memoised: React only re-renders the QA tree when the
  // parent re-renders anyway, and the bundle object is cheap to build.
  const qaProps = {
    chats, selectedChatId, question, answering, answeringStartedAt, loadingChats,
    inputMode, expandedGraph, showSidebarSearch, sidebarSearch, showChatHistory,
    qaScopeMode, qaScopeDocumentTypes, qaScopeDocumentIds,
    qaDocumentsList, qaDocumentsLoading, feedbackSent, feedbackSubmitting,
    documents,
    setSelectedChatId, setQuestion, setInputMode, setExpandedGraph,
    setShowSidebarSearch, setSidebarSearch, setShowChatHistory,
    setQaScopeMode, setQaScopeDocumentTypes, setQaScopeDocumentIds,
    setFeedbackSent, setFeedbackSubmitting,
    onNewChat: newChat,
    onDeleteChat: deleteChat,
    onAskQuestion: handleAskQuestion,
    messagesEndRef,
  };

  return (
    <HintsProvider>
    <div className="w-full">
      {/* The inner Frontline sidebar has been folded into the global app
          sidebar (each parent tab + its sub-items are nested there). A hidden
          anchor keeps any tour selector targeting [data-tour-fl="tabs"] valid. */}
      <div data-tour-fl="tabs" className="hidden" />

    <div
      className="flex-1 min-w-0 w-full rounded-2xl border border-white/[0.06] p-0"
      style={{ background: 'var(--app-hero-bg)' }}
    >
    <div className="space-y-6 w-full max-w-full overflow-x-hidden p-4 md:p-6 lg:p-8">
      {/* Take the Tour + Hints toggle */}
      <div className="flex justify-end items-center gap-2 relative">
        <HintsToggleButton />
        <button
          type="button"
          onClick={handleReplayTutorial}
          data-tour="replay"
          title="Replay the onboarding tutorial"
          className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-amber-400/40 bg-amber-400/10 text-amber-300 text-sm font-semibold hover:bg-amber-400/20 hover:text-amber-200 transition ${spotlightTour ? 'flt-spotlight' : ''}`}
        >
          <GraduationCap className="h-4 w-4" />
          Take the Tour
        </button>
        {spotlightTooltip && (
          <div className="absolute -bottom-12 right-0 z-10 rounded-md border border-amber-400/40 bg-[var(--panel-4)] px-2.5 py-1.5 text-xs text-white/90 shadow-lg pointer-events-none whitespace-nowrap flt-spotlight-tip">
            👋 Take the tour anytime from here
            <span className="absolute -top-1 right-6 h-2 w-2 bg-[var(--panel-4)] border-t border-l border-amber-400/40 rotate-45" />
          </div>
        )}
      </div>
      <style>{`
        @keyframes fltSpotlight {
          0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4), 0 0 0 0 rgba(245, 158, 11, 0.2); }
          50%      { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0.15), 0 0 0 12px rgba(245, 158, 11, 0.08); }
        }
        .flt-spotlight { animation: fltSpotlight 1.6s ease-in-out infinite; }
        @keyframes fltTabSpotlight {
          0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.35), 0 0 0 0 rgba(245, 158, 11, 0.18); }
          50%      { box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.14), 0 0 0 8px rgba(245, 158, 11, 0.07); }
        }
        .flt-tab-spotlight { animation: fltTabSpotlight 1.6s ease-in-out infinite; }
        @keyframes fltDotPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%      { transform: scale(1.3); opacity: 0.7; }
        }
      `}</style>

      {/* Stats Overview */}
      <div data-tour="stats" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 sm:mb-8 w-full">
        {[
          {
            label: 'Total Documents',
            value: stats?.total_documents || 0,
            sub: `${stats?.indexed_documents || 0} indexed`,
            icon: FileText,
            color: '#a78bfa',
            bgColor: 'rgba(167,139,250,0.2)',
            borderColor: 'rgba(167,139,250,0.2)',
            gradientFrom: 'rgba(167,139,250,0.2)',
            gradientTo: 'rgba(147,51,234,0.1)',
          },
          {
            label: 'Total Tickets',
            value: stats?.total_tickets || 0,
            sub: `${stats?.open_tickets || 0} open`,
            icon: Ticket,
            color: '#34d399',
            bgColor: 'rgba(52,211,153,0.2)',
            borderColor: 'rgba(52,211,153,0.2)',
            gradientFrom: 'rgba(52,211,153,0.2)',
            gradientTo: 'rgba(22,163,74,0.1)',
          },
          {
            label: 'Resolved',
            value: stats?.resolved_tickets || 0,
            sub: 'Successfully resolved',
            icon: CheckCircle2,
            color: '#fbbf24',
            bgColor: 'rgba(251,191,36,0.2)',
            borderColor: 'rgba(251,191,36,0.2)',
            gradientFrom: 'rgba(251,191,36,0.15)',
            gradientTo: 'rgba(245,158,11,0.08)',
          },
          {
            label: 'Auto-Resolved',
            value: stats?.auto_resolved_tickets || 0,
            sub: 'Resolved automatically',
            icon: Sparkles,
            color: '#60a5fa',
            bgColor: 'rgba(96,165,250,0.2)',
            borderColor: 'rgba(96,165,250,0.2)',
            gradientFrom: 'rgba(96,165,250,0.2)',
            gradientTo: 'rgba(34,211,238,0.1)',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="relative group w-full min-w-0 rounded-xl backdrop-blur-sm p-5 transition-all duration-300 hover:scale-[1.02] hover:shadow-lg"
            style={{
              border: `1px solid ${card.borderColor}`,
              background: `linear-gradient(135deg, ${card.gradientFrom} 0%, ${card.gradientTo} 100%)`,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                <card.icon className="h-5 w-5" style={{ color: card.color }} />
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-white/50 tracking-wide">{card.label}</p>
              <p className="text-3xl font-bold text-white tracking-tight">{card.value}</p>
              <p className="text-xs text-white/40">{card.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full space-y-4">
        {/* Mobile & Tablet: Hamburger menu (below lg) */}
        <div className="lg:hidden w-full mb-4">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="w-full justify-between h-11 border-[var(--line-2)] bg-[var(--panel-1)] text-white/80 hover:bg-[var(--sfc-231845)] hover:text-white">
                <div className="flex items-center gap-2 min-w-0">
                  <currentTab.icon className="h-4 w-4 shrink-0 text-violet-400" />
                  <span className="font-medium truncate">{currentTab.label}</span>
                </div>
                <Menu className="h-5 w-5 text-white/40 shrink-0" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[calc(100vw-2rem)] max-w-sm max-h-[60vh] overflow-y-auto border-[var(--line-2)] bg-[var(--panel-4)]">
              {FRONTLINE_TAB_ITEMS.filter((t) => !t.hidden).map((item) => {
                const isActive = item.value === activeTab;
                const ItemIcon = item.icon;
                return (
                  <DropdownMenuItem
                    key={item.value}
                    onClick={() => setActiveTab(item.value)}
                    className={`flex items-center justify-between py-3 cursor-pointer ${isActive ? 'bg-violet-600/20' : 'hover:bg-white/5'}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <ItemIcon className={`h-4 w-4 shrink-0 ${isActive ? 'text-violet-400' : 'text-white/40'}`} />
                      <span className={isActive ? 'font-medium text-violet-300' : 'text-white/70'}>{item.label}</span>
                    </div>
                    {isActive && <Check className="h-4 w-4 text-violet-400 shrink-0" />}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Desktop tab bar replaced by FrontlineSidebar (outside main flow).
            Kept in DOM but permanently hidden so any existing tour selectors
            targeting `[data-tour="tabs"]` still resolve without visual junk.
            Mobile users continue using the hamburger dropdown above. */}
        <div data-tour="tabs" className="hidden">
          <TabsList
            className="inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[var(--panel-1)] border border-[var(--line-2)]"
            style={{ boxShadow: '0 2px 12px 0 hsl(var(--brand-accent) / 0.04)' }}
          >
            {FRONTLINE_TAB_ITEMS.filter((t) => !t.hidden).map((item) => {
              const TabIcon = item.icon;
              const tour = TAB_TOURS[item.value];
              const showBadge = tour && tourAvailable(tour.key);
              const hoverHandlers = tour ? makeHoverLaunchHandlers({
                tourStorageKey: tour.key,
                onLaunch: () => setActiveTabTour(item.value),
              }) : {};
              return (
                <TabsTrigger
                  key={item.value}
                  value={item.value}
                  data-tour-tab={item.value}
                  {...hoverHandlers}
                  className="relative whitespace-nowrap shrink-0 px-4 py-2 text-sm font-medium rounded-md border transition-all duration-150"
                  style={activeTab === item.value
                    ? {
                        background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                        color: '#fff',
                        border: '1.5px solid #f59e0b',
                        boxShadow: '0 0 8px 0 #f59e0b55',
                      }
                    : {
                        background: 'hsl(var(--sfr-3c1e5a) / 0.22)',
                        color: '#cfc6e6',
                        border: '1.5px solid var(--line-3)',
                        boxShadow: 'none',
                      }
                  }
                >
                  <TabIcon className="h-4 w-4 mr-2" />
                  {item.label}
                  {showBadge && (
                    <span
                      title="Tour available — hover to launch or click 'Tour this tab' inside"
                      className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-amber-400 ring-2 ring-[var(--panel-1)]"
                      style={{ animation: 'fltDotPulse 2s ease-in-out infinite' }}
                    />
                  )}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </div>

        {/* ── NEW consolidated tabs (Chunk A of FRONTLINE_AGENT_UX_REDESIGN.md).
              Each renders FrontlinePlaceholderView with click-to-open cards
              that navigate to the hidden legacy tab where the actual feature
              lives. Chunks B–F extract the legacy content into these views
              as proper nested sub-tabs. Until then, sub-tab feel = one click
              away, not zero — but nothing is broken or unreachable. */}
        <TabsContent value="queue" className="mt-6">
          <div className="flex justify-end mb-3"><TabTourButton tabKey="queue" /></div>
          <QueueView
            activeSubTab={activeSubTab}
            onSubTabChange={(sub) => setSubTab('queue', sub)}
            onNavigateToTab={setActiveTab}
          />
        </TabsContent>

        <TabsContent value="knowledge" className="mt-6">
          <div className="flex justify-end mb-3"><TabTourButton tabKey="knowledge" /></div>
          <KnowledgeView
            documents={documents}
            docSummaries={docSummaries}
            onOpenUpload={() => setShowUploadDialog(true)}
            onToggleSummary={toggleDocSummary}
            onSummarize={handleSummarizeDocument}
            onExtract={handleExtractDocument}
            onToggleOutdated={handleToggleDocOutdated}
            onDelete={handleDeleteDocument}
            onRetry={handleRetryDocument}
            qa={qaProps}
            onNavigateToTab={setActiveTab}
            activeSubTab={activeSubTab}
            onSubTabChange={(sub) => setSubTab('knowledge', sub)}
          />
        </TabsContent>

        <TabsContent value="insights" className="mt-6">
          <div className="flex justify-end mb-3"><TabTourButton tabKey="insights" /></div>
          <InsightsView
            activeSubTab={activeSubTab}
            onSubTabChange={(sub) => setSubTab('insights', sub)}
          />
        </TabsContent>

        <TabsContent value="automation" className="mt-6">
          <div className="flex justify-end mb-3"><TabTourButton tabKey="automation" /></div>
          <AutomationView
            activeSubTab={activeSubTab}
            onSubTabChange={(sub) => setSubTab('automation', sub)}
          />
        </TabsContent>

        <TabsContent value="settings" className="mt-6">
          <div className="flex justify-end mb-3"><TabTourButton tabKey="settings" /></div>
          <SettingsView
            activeSubTab={activeSubTab}
            onSubTabChange={(sub) => setSubTab('settings', sub)}
            onNavigateToTab={setActiveTab}
          />
        </TabsContent>

        {/* Overview Tab */}
        <TabsContent value="overview" className="mt-6">
          <ErrorBoundary>
          <div className="flex justify-end mb-3"><TabTourButton tabKey="overview" /></div>
          {/* Admin insights — SLA / KB / DLQ / audit log tiles. Lazy-fetched. */}
          <div data-tour-ov="insights" className="mb-5 relative">
            <div className="absolute -top-1 right-1 z-10"><InfoHint {...HINTS.ovInsights} /></div>
            <FrontlineInsightsPanel onNavigateToTab={setActiveTab} />
          </div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs uppercase tracking-wider text-white/40 font-semibold">Quick jump</span>
            <InfoHint {...HINTS.ovQuicknav} />
          </div>
          <div data-tour-ov="quicknav" className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full min-w-0">
            {[
              {
                title: 'Documents',
                desc: 'Upload and manage knowledge base documents for AI-powered answers',
                icon: FileText,
                tab: 'documents',
                color: '#a78bfa',
                bgColor: 'rgba(167,139,250,0.15)',
                borderHover: 'rgba(167,139,250,0.4)',
              },
              {
                title: 'Knowledge Q&A',
                desc: 'Ask questions and get AI-powered answers from your knowledge base',
                icon: MessageSquare,
                tab: 'qa',
                color: '#34d399',
                bgColor: 'rgba(52,211,153,0.15)',
                borderHover: 'rgba(52,211,153,0.4)',
              },
              {
                title: 'Tickets',
                desc: 'Manage support tickets with AI auto-resolution and prioritization',
                icon: Ticket,
                tab: 'tickets',
                color: '#60a5fa',
                bgColor: 'rgba(96,165,250,0.15)',
                borderHover: 'rgba(96,165,250,0.4)',
              },
              {
                title: 'Chat Widget',
                desc: 'Configure and embed a customer-facing chat widget on your site',
                icon: Monitor,
                tab: 'widget',
                color: '#fbbf24',
                bgColor: 'rgba(251,191,36,0.15)',
                borderHover: 'rgba(251,191,36,0.4)',
              },
              {
                title: 'Workflows',
                desc: 'Set up automated workflows for ticket routing and notifications',
                icon: GitBranch,
                tab: 'workflows',
                color: '#2dd4bf',
                bgColor: 'rgba(45,212,191,0.15)',
                borderHover: 'rgba(45,212,191,0.4)',
              },
              {
                title: 'Analytics',
                desc: 'View ticket trends, performance metrics, and AI-generated graphs',
                icon: BarChart3,
                tab: 'analytics',
                color: '#f472b6',
                bgColor: 'rgba(244,114,182,0.15)',
                borderHover: 'rgba(244,114,182,0.4)',
              },
              {
                title: 'Hand-offs',
                desc: 'Reply to tickets escalated to human agents with AI-drafted responses',
                icon: Headphones,
                tab: 'handoffs',
                color: '#fb923c',
                bgColor: 'rgba(251,146,60,0.15)',
                borderHover: 'rgba(251,146,60,0.4)',
              },
              {
                title: 'Notifications',
                desc: 'Manage notification preferences, templates, and scheduled alerts',
                icon: Bell,
                tab: 'notifications',
                color: '#22d3ee',
                bgColor: 'rgba(34,211,238,0.15)',
                borderHover: 'rgba(34,211,238,0.4)',
              },
              {
                title: 'AI Graphs',
                desc: 'Generate charts from natural-language prompts and save your favourites',
                icon: Sparkles,
                tab: 'ai-graphs',
                color: '#c084fc',
                bgColor: 'rgba(192,132,252,0.15)',
                borderHover: 'rgba(192,132,252,0.4)',
              },
            ].map((card) => (
              <button
                key={card.title}
                onClick={() => setActiveTab(card.tab)}
                className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer w-full min-w-0"
                onMouseEnter={(e) => e.currentTarget.style.borderColor = card.borderHover}
                onMouseLeave={(e) => e.currentTarget.style.borderColor = ''}
              >
                <div className="rounded-lg p-2.5" style={{ backgroundColor: card.bgColor }}>
                  <card.icon className="h-5 w-5" style={{ color: card.color }} />
                </div>
                <div>
                  <p className="font-semibold text-sm text-white group-hover:text-white transition-colors">{card.title}</p>
                  <p className="text-xs text-white/40 mt-1 leading-relaxed">{card.desc}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Recent Documents */}
          {documents.length > 0 && (
            <div className="mt-6 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5">
              <h3 className="text-sm font-semibold text-white mb-3">Recent Documents</h3>
              <div className="space-y-2">
                {documents.slice(0, 5).map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between p-2 rounded-lg border border-white/[0.06] bg-white/[0.02]">
                    <div className="flex items-center space-x-2 min-w-0">
                      <FileText className="h-4 w-4 text-white/40 shrink-0" />
                      <span className="text-sm text-white/70 truncate">{doc.title}</span>
                      {doc.is_indexed && (
                        <span className="text-xs text-emerald-400">Indexed</span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-white/30 hover:text-white/60 shrink-0"
                      onClick={() => handleDeleteDocument(doc.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
          </ErrorBoundary>
        </TabsContent>

        {/* Documents Tab — legacy standalone URL (?tab=documents). Content
            extracted to FrontlineDocumentsTab; also rendered inside the
            new KnowledgeView. Kept here so bookmarks still work. */}
        <TabsContent value="documents" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div className="flex justify-end"><TabTourButton tabKey="documents" /></div>
          <FrontlineDocumentsTab
            documents={documents}
            docSummaries={docSummaries}
            onOpenUpload={() => setShowUploadDialog(true)}
            onToggleSummary={toggleDocSummary}
            onSummarize={handleSummarizeDocument}
            onExtract={handleExtractDocument}
            onToggleOutdated={handleToggleDocOutdated}
            onDelete={handleDeleteDocument}
            onRetry={handleRetryDocument}
          />
          </ErrorBoundary>
        </TabsContent>

        {/* — DEAD CODE below (kept until we verify extraction, then delete
            in a cleanup pass). Original inline JSX removed to avoid double
            render. — */}
        <div className="hidden">
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <CardTitle>Documents</CardTitle>
                  <InfoHint {...HINTS.docsGrid} />
                </div>
                <CardDescription>Upload and manage knowledge base documents</CardDescription>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
                <Button data-tour-docs="upload" onClick={() => setShowUploadDialog(true)} className="w-full sm:w-auto">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Document
                </Button>
                <InfoHint {...HINTS.docsUpload} />
              </div>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
                    <FileText className="h-7 w-7 text-violet-400" />
                  </div>
                  <div className="font-medium mb-1">No documents yet</div>
                  <div className="text-sm text-muted-foreground max-w-sm">
                    Upload a document to give the knowledge agent something to answer from.
                  </div>
                </div>
              ) : (
                <div data-tour-docs="grid" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {documents.map((doc) => {
                    const fmt = (doc.file_format || 'other').toLowerCase();
                    const fmtColor = {
                      pdf: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
                      docx: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      doc: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      txt: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
                      md: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
                      html: 'bg-amber-500/15 text-amber-400 border-amber-400/30',
                    }[fmt] || 'bg-violet-500/15 text-violet-400 border-violet-400/30';
                    const sizeKB = doc.file_size ? Math.max(1, Math.round(doc.file_size / 1024)) : null;
                    const sizeDisplay = sizeKB && sizeKB >= 1024
                      ? `${(sizeKB / 1024).toFixed(1)} MB`
                      : (sizeKB ? `${sizeKB} KB` : null);
                    const summaryState = docSummaries[doc.id];
                    const procStatus = doc.processing_status || (doc.is_indexed ? 'ready' : 'pending');
                    const procLabel = {
                      ready: 'Indexed',
                      processing: 'Processing',
                      pending: 'Queued',
                      failed: 'Failed',
                    }[procStatus] || procStatus;
                    const procColor = {
                      ready: 'bg-emerald-500/15 text-emerald-400 border-emerald-400/30',
                      processing: 'bg-violet-500/15 text-violet-400 border-violet-400/30',
                      pending: 'bg-white/[0.04] text-white/55 border-white/[0.08]',
                      failed: 'bg-rose-500/15 text-rose-400 border-rose-400/30',
                    }[procStatus] || 'bg-white/[0.04] text-white/55 border-white/[0.08]';

                    return (
                      <div
                        key={doc.id}
                        className="group flex flex-col rounded-xl border border-white/[0.08] bg-gradient-to-br from-white/[0.04] to-white/[0.01] hover:border-violet-400/40 hover:shadow-[0_0_0_1px_rgba(139,92,246,0.15),0_8px_32px_-8px_rgba(139,92,246,0.25)] transition-all duration-200 overflow-hidden"
                      >
                        {/* Header row: format badge + title + status */}
                        <div className="p-4 pb-3">
                          <div className="flex items-start gap-3">
                            <div className={`shrink-0 h-10 w-10 rounded-lg border flex items-center justify-center ${fmtColor}`}>
                              <FileText className="h-5 w-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="font-medium truncate text-sm" title={doc.title}>{doc.title}</div>
                              <div className="mt-0.5 text-xs text-muted-foreground truncate">
                                {fmt.toUpperCase()}
                                {doc.document_type ? ` • ${doc.document_type.replace(/_/g, ' ')}` : ''}
                                {sizeDisplay ? ` • ${sizeDisplay}` : ''}
                              </div>
                            </div>
                          </div>
                          <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                            <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${procColor}`}>
                              {procLabel}
                            </Badge>
                            {doc.is_outdated && (
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-rose-500/10 text-rose-300 border-rose-400/30">
                                outdated
                              </Badge>
                            )}
                            {doc.created_at && (
                              <span className="text-[10px] text-muted-foreground">
                                {new Date(doc.created_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Expandable summary area */}
                        <div className="px-4 pb-3 flex-1">
                          {summaryState?.expanded ? (
                            <div className="rounded-md bg-black/20 border border-white/[0.06] p-3 text-xs text-white/80 space-y-2">
                              {summaryState.loading ? (
                                <div className="flex items-center gap-2 text-muted-foreground">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  <span>Generating summary...</span>
                                </div>
                              ) : summaryState.error ? (
                                <div className="text-rose-400">{summaryState.error}</div>
                              ) : (
                                <div className="whitespace-pre-wrap break-words leading-relaxed">
                                  {summaryState.summary || 'No summary available.'}
                                </div>
                              )}
                              <button
                                onClick={() => toggleDocSummary(doc)}
                                disabled={summaryState.loading}
                                className="text-violet-400 hover:text-violet-300 text-[11px] font-medium flex items-center gap-0.5"
                              >
                                Show less <ChevronUp className="h-3 w-3" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => toggleDocSummary(doc)}
                              className="text-violet-400 hover:text-violet-300 text-xs font-medium flex items-center gap-0.5"
                            >
                              Show summary <ChevronDown className="h-3 w-3" />
                            </button>
                          )}
                        </div>

                        {/* Action bar */}
                        <div data-tour-docs="card-actions" className="border-t border-white/[0.06] px-2 py-1.5 flex items-center justify-between bg-black/10">
                          <div className="flex items-center">
                            <InfoHint {...HINTS.docsCardActions} className="ml-1 mr-2" />
                            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => handleSummarizeDocument(doc)} title="Full summary">
                              <FileSearch className="h-3.5 w-3.5 mr-1" /> Summarize
                            </Button>
                            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={() => handleExtractDocument(doc)} title="Extract structured data">
                              <ListChecks className="h-3.5 w-3.5 mr-1" /> Extract
                            </Button>
                            {doc.is_outdated ? (
                              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-emerald-400 hover:text-emerald-300"
                                onClick={() => handleToggleDocOutdated(doc, false)}
                                title="Restore — bring this doc back into retrieval">
                                Restore
                              </Button>
                            ) : (
                              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-amber-400 hover:text-amber-300"
                                onClick={() => handleToggleDocOutdated(doc, true)}
                                title="Mark outdated — excluded from knowledge retrieval until restored">
                                Outdated
                              </Button>
                            )}
                          </div>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-rose-400" onClick={() => handleDeleteDocument(doc.id)} title="Delete">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>{/* end DEAD CODE hidden wrapper */}

        {/* Knowledge Q&A Tab - Chat UI with sidebar */}
        {/* Knowledge Q&A Tab — legacy standalone URL (?tab=qa). Content
            extracted to FrontlineKnowledgeQATab; also rendered inside the
            new KnowledgeView. Kept here so bookmarks still work. */}
        <TabsContent value="qa" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div className="flex justify-end mb-2"><TabTourButton tabKey="qa" /></div>
          <FrontlineKnowledgeQATab {...qaProps} />
          </ErrorBoundary>
        </TabsContent>

        {/* — DEAD CODE below (kept until we verify QA extraction, then delete
            in a cleanup pass). Original 720-line inline JSX removed to avoid
            double render but preserved verbatim in this hidden wrapper. — */}
        <div className="hidden">
          <div
            className="w-full rounded-2xl border border-white/[0.06] p-0 overflow-hidden"
            style={{
              background:
                'var(--app-hero-bg)',
            }}
          >
            <div className="flex w-full max-w-full relative">
              <div
                data-tour-qa="sidebar"
                className={`shrink-0 rounded-xl border border-white/15 shadow-[0_2px_24px_0_hsl(var(--sfr-5024b4) / 0.18)] backdrop-blur-lg overflow-hidden transition-all duration-300 ease-in-out ${
                  showChatHistory ? 'w-64 opacity-100 mr-4' : 'w-0 opacity-0 border-0 mr-0'
                }`}
                style={{
                  minWidth: showChatHistory ? '16rem' : '0',
                  background: 'linear-gradient(90deg, rgba(139,92,246,0.13) 0%, hsl(var(--sfr-241236) / 0.18) 18%, var(--panel-3) 55%, var(--panel-3) 100%)',
                  borderRight: '1.5px solid hsl(var(--surface-invert) / 0.10)',
                  boxShadow: '0 2px 24px 0 hsl(var(--sfr-5024b4) / 0.18), 0 0 0 1.5px rgba(120, 80, 255, 0.10) inset',
                  borderTopLeftRadius: 16,
                  borderBottomLeftRadius: 16,
                  backdropFilter: 'blur(12px)',
                  WebkitBackdropFilter: 'blur(12px)',
                  overflow: 'hidden',
                }}
              >
                <div className="w-64">
                  <div
                    className="px-3 pt-3 pb-2 border-b border-white/15 flex flex-col gap-2"
                    style={{
                      background: 'linear-gradient(180deg, hsl(var(--sfr-3c1e5a) / 0.22) 0%, hsl(var(--sfr-241236) / 0.85) 100%)',
                      borderTopLeftRadius: 16,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-base font-semibold text-white/90 tracking-wide">Frontline</span>
                        <InfoHint {...HINTS.qaSidebar} />
                      </div>
                      <button
                        onClick={() => setShowChatHistory(false)}
                        title="Close sidebar"
                        className="h-8 w-8 flex items-center justify-center rounded-full border border-white/20 hover:border-violet-400/60 bg-black/30 hover:bg-violet-700/20 transition-all duration-150"
                        style={{ boxShadow: '0 0 0 2px rgba(139,92,246,0.10) inset' }}
                      >
                        <ChevronLeft className="h-4 w-4 text-white/80" />
                      </button>
                    </div>

                    {showSidebarSearch ? (
                      <div
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                        style={{
                          border: '1.5px solid rgba(139,92,246,0.22)',
                          background: 'linear-gradient(90deg, hsl(var(--sfr-5024b4) / 0.10) 0%, hsl(var(--sfr-241236) / 0.18) 100%)',
                          boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                          backdropFilter: 'blur(4px)',
                          WebkitBackdropFilter: 'blur(4px)',
                        }}
                      >
                        <input
                          autoFocus
                          value={sidebarSearch}
                          onChange={(e) => setSidebarSearch(e.target.value)}
                          placeholder="Search conversations..."
                          className="flex-1 bg-transparent outline-none border-0 text-white/90 text-sm px-2 py-1.5 placeholder-white/40"
                          style={{ minWidth: 0 }}
                        />
                        <button
                          title="Close search"
                          onClick={() => {
                            setSidebarSearch('');
                            setShowSidebarSearch(false);
                          }}
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <svg
                            width="16"
                            height="16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="text-white/70"
                          >
                            <line x1="4" y1="4" x2="12" y2="12" />
                            <line x1="12" y1="4" x2="4" y2="12" />
                          </svg>
                        </button>
                      </div>
                    ) : (
                      <div
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg w-full"
                        style={{
                          border: '1.5px solid rgba(139,92,246,0.22)',
                          background: 'linear-gradient(90deg, hsl(var(--sfr-5024b4) / 0.10) 0%, hsl(var(--sfr-241236) / 0.18) 100%)',
                          boxShadow: '0 1px 8px 0 rgba(139,92,246,0.08) inset',
                          backdropFilter: 'blur(4px)',
                          WebkitBackdropFilter: 'blur(4px)',
                        }}
                      >
                        <span className="text-sm font-medium text-white/80 flex-1">Conversation</span>
                        <button
                          title="Search"
                          onClick={() => setShowSidebarSearch(true)}
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <svg
                            width="16"
                            height="16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="text-white/70"
                          >
                            <circle cx="7" cy="7" r="5" />
                            <line x1="15" y1="15" x2="11" y2="11" />
                          </svg>
                        </button>
                        <button
                          data-tour-qa="new-chat"
                          onClick={newChat}
                          title="New chat"
                          className="h-7 w-7 flex items-center justify-center rounded-full border border-white/15 hover:border-violet-400/60 bg-black/20 hover:bg-violet-700/20 transition-all duration-150"
                        >
                          <Plus className="h-4 w-4 text-white/80" />
                        </button>
                        <InfoHint {...HINTS.qaNewChat} />
                      </div>
                    )}
                  </div>

                  <div>
                    {loadingChats ? (
                      <div className="p-4 flex justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : chats.length === 0 ? (
                      <div className="p-4 text-center text-sm text-muted-foreground">No conversations yet. Ask a question to start.</div>
                    ) : (
                      <div
                        className="p-2 space-y-1"
                        style={{
                          background: 'linear-gradient(180deg, hsl(var(--sfr-241236) / 0.10) 0%, hsl(var(--sfr-18122b) / 0.18) 100%)',
                          borderRadius: 12,
                        }}
                      >
                        {(() => {
                          const searchTerm = sidebarSearch.trim().toLowerCase();
                          const filteredChats = searchTerm
                            ? chats.filter((c) => {
                                const title = (c.title || c.messages?.[0]?.content || '').toLowerCase();
                                const messagesMatch = (c.messages || []).some((m) => (m.content || '').toLowerCase().includes(searchTerm));
                                return title.includes(searchTerm) || messagesMatch;
                              })
                            : chats;

                          if (searchTerm && filteredChats.length === 0) {
                            return <div className="p-4 text-center text-sm text-muted-foreground">No matching conversations found.</div>;
                          }

                          return filteredChats.map((c) => (
                            <div
                              key={c.id}
                              className={`flex items-center gap-1 rounded-lg border text-sm transition-all duration-200 ${
                                selectedChatId === c.id
                                  ? 'border-violet-500/60 bg-gradient-to-r from-violet-900/40 to-violet-700/20 shadow-[0_0_12px_rgba(139,92,246,0.18)]'
                                  : 'border-white/10 bg-white/2 hover:bg-white/5 hover:border-violet-400/20'
                              }`}
                              style={{
                                boxShadow:
                                  selectedChatId === c.id
                                    ? '0 0 12px 0 rgba(139,92,246,0.18), 0 1.5px 0 0 rgba(120,80,255,0.10) inset'
                                    : '0 1px 2px 0 hsl(var(--sfr-241236) / 0.08) inset',
                                borderWidth: 1.5,
                              }}
                            >
                              <button
                                type="button"
                                onClick={() => setSelectedChatId(c.id)}
                                className="flex-1 min-w-0 text-left p-3 rounded-lg"
                              >
                                <div className={`font-medium truncate ${selectedChatId === c.id ? 'text-violet-300' : ''}`}>
                                  {truncate(c.title || c.messages?.[0]?.content || 'Chat', 40)}
                                </div>
                                <div className={`text-xs mt-0.5 ${selectedChatId === c.id ? 'text-violet-400/70' : 'text-muted-foreground'}`}>
                                  {formatDate(c.updatedAt || c.timestamp)}
                                </div>
                              </button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 shrink-0 opacity-60 hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                                onClick={(e) => deleteChat(e, c.id)}
                                title="Delete chat"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ));
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <Card className="flex-1 min-w-0 flex flex-col max-h-[calc(100vh-40px)] border-0 shadow-none" style={{ background: 'transparent' }}>
                <CardHeader
                  className="shrink-0 flex flex-row items-start justify-between gap-3 border-b border-white/[0.07] px-0 py-4"
                  style={{ background: 'transparent' }}
                >
                  <div className="flex items-center gap-3 min-w-0 w-full">
                    <div
                      style={{
                        width: '7px',
                        height: '48px',
                        borderRadius: '8px',
                        background: 'linear-gradient(to bottom, hsl(var(--brand-accent)) 0%, #6a1b9a 60%, #18122B 100%)',
                        marginLeft: '24px',
                        marginRight: '18px',
                        boxShadow: '0 0 8px 2px hsl(var(--brand-accent) / 0.27)',
                      }}
                    />
                    <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'hsl(var(--brand-600) / 0.15)' }}>
                      <Bot className="h-5 w-5" style={{ color: 'hsl(var(--pt-a78bfa))' }} />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="flex items-center gap-2 truncate text-white text-lg">
                        Knowledge Q&A
                        <span
                          className="text-[10px] rounded-full px-2.5 py-0.5 font-medium"
                          style={{ background: 'hsl(var(--brand-600) / 0.15)', color: 'hsl(var(--pt-a78bfa))' }}
                        >
                          AI-Powered
                        </span>
                      </CardTitle>
                      <CardDescription className="text-white/50 text-sm mt-0.5">
                        Ask questions and get answers from your knowledge base and uploaded documents.
                      </CardDescription>
                    </div>
                    <InfoHint {...HINTS.qaMessages} />
                  </div>

                  <Button
                    variant={showChatHistory ? 'ghost' : 'outline'}
                    size="sm"
                    onClick={() => setShowChatHistory((v) => !v)}
                    title={showChatHistory ? 'Hide chat history' : 'Show chat history'}
                    className={`gap-1.5 transition-all duration-200 ${
                      !showChatHistory
                        ? 'bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary'
                        : 'hover:bg-muted'
                    }`}
                    style={{ marginRight: '24px' }}
                  >
                    {showChatHistory ? (
                      <>
                        <ChevronLeft className="h-4 w-4" />
                        <span className="text-xs hidden sm:inline">Hide</span>
                      </>
                    ) : (
                      <>
                        <ChevronRight className="h-4 w-4" />
                        <span className="text-xs hidden sm:inline">History</span>
                      </>
                    )}
                  </Button>
                </CardHeader>

                <CardContent className="p-0 flex flex-col flex-1 min-h-0">
                  <div data-tour-qa="messages" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
                  {!selectedChatId && chats.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Ask your first question</p>
                      <p className="text-sm">Type a question to get an answer from your knowledge base.</p>
                      {documents.length === 0 && (
                        <p className="text-xs mt-2 text-amber-600 dark:text-amber-400">💡 Tip: Upload documents in the Documents tab first</p>
                      )}
                    </div>
                  )}
                  {!selectedChatId && chats.length > 0 && (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                      <MessageCircle className="h-12 w-12 mb-4 opacity-50" />
                      <p className="font-medium">Select a conversation or ask a new question</p>
                      <p className="text-sm">Click a previous chat in the sidebar to view it.</p>
                    </div>
                  )}
                  {currentMessages.map((msg, i) => (
                    <div
                      key={i}
                      className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted border'
                        }`}
                      >
                        {msg.role === 'user' ? (
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        ) : msg.responseData?.isGraph ? (
                          <>
                            <div className="space-y-3">
                              {msg.responseData.chart && (
                                <div className="relative w-full rounded-xl border border-border bg-card p-2 shadow-sm">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="absolute top-1.5 right-1.5 h-7 w-7 rounded-md opacity-70 hover:opacity-100 text-muted-foreground hover:text-foreground"
                                    onClick={() => setExpandedGraph({ chart: msg.responseData.chart, chartTitle: msg.responseData.chartTitle })}
                                    title="Expand graph"
                                  >
                                    <Maximize2 className="h-3.5 w-3.5" />
                                  </Button>
                                  <div className="pr-8 w-full min-w-0">
                                    {renderChart(msg.responseData.chart)}
                                  </div>
                                </div>
                              )}
                              {msg.responseData?.insights && (
                                <div className="pt-2 border-t border-border/50">
                                  <p className="text-xs font-semibold mb-2">Insights</p>
                                  <p className="text-xs text-muted-foreground whitespace-pre-wrap">{msg.responseData.insights}</p>
                                </div>
                              )}
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="flex items-start gap-2">
                              {(msg.responseData?.has_verified_info) ? (
                                <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 mt-0.5 flex-shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                              )}
                              <div className="flex-1 min-w-0">
                                {msg.streaming ? (
                                  // While streaming, render as plain text with a
                                  // blinking cursor — markdown parsing on every
                                  // token would produce flicker on incomplete
                                  // headers/lists/bold. Flip to rendered markdown
                                  // once the stream completes.
                                  <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                                    {msg.content}
                                    {!msg.content && <span className="text-muted-foreground italic">Thinking…</span>}
                                    <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-primary/70 animate-pulse align-middle" />
                                  </div>
                                ) : (
                                  <ChatMarkdown className="text-sm text-foreground">
                                    {msg.responseData?.answer ?? msg.content ?? ''}
                                  </ChatMarkdown>
                                )}
                                {msg.responseData?.confidence === 'low' && (
                                  <div className="mt-2 text-xs rounded-md px-2 py-1 bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30">
                                    Low-confidence match{typeof msg.responseData?.best_score === 'number' ? ` (score ${msg.responseData.best_score})` : ''}. Consider escalating to a human agent.
                                  </div>
                                )}
                                {(() => {
                                  const t = msg.responseData?.responseTimeMs ?? msg.responseTimeMs;
                                  if (typeof t !== 'number') return null;
                                  const tm = msg.responseData?.timing_ms;
                                  const parts = [];
                                  if (tm && !tm.cache) {
                                    if (typeof tm.retrieval === 'number') parts.push(`retrieval ${(tm.retrieval / 1000).toFixed(1)}s`);
                                    if (typeof tm.llm === 'number') parts.push(`llm ${(tm.llm / 1000).toFixed(1)}s`);
                                    if (typeof tm.contextualise === 'number') parts.push(`ctx ${(tm.contextualise / 1000).toFixed(1)}s`);
                                  }
                                  // Retrieval sub-phase breakdown — shown when retrieval > 1s so we
                                  // can pinpoint WHICH phase (faiss build / json-scan / keyword / rerank).
                                  const rb = tm?.retrieval_breakdown;
                                  const rp = tm?.retrieval_path;
                                  const rbParts = [];
                                  if (rb && (tm?.retrieval || 0) > 1000) {
                                    const keys = ['query_embed', 'faiss_search', 'faiss_candidates', 'faiss_chunk_fetch', 'faiss_output_build', 'semantic', 'json_scan', 'keyword', 'rerank'];
                                    for (const k of keys) {
                                      if (typeof rb[k] === 'number' && rb[k] > 50) {
                                        rbParts.push(`${k}=${(rb[k] / 1000).toFixed(1)}s`);
                                      }
                                    }
                                    if (typeof rb.json_scan_chunks === 'number' && rb.json_scan_chunks > 0) {
                                      rbParts.push(`scanned=${rb.json_scan_chunks}`);
                                    }
                                  }
                                  return (
                                    <div className="mt-2 text-[10px] text-muted-foreground/70 space-y-0.5">
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        <span>⏱ Answered in {(t / 1000).toFixed(2)}s</span>
                                        {parts.length > 0 && (
                                          <span className="text-muted-foreground/50">({parts.join(' · ')})</span>
                                        )}
                                        {msg.responseData?.cache_hit && (
                                          <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-[9px] font-medium">
                                            cached
                                          </span>
                                        )}
                                      </div>
                                      {(rbParts.length > 0 || rp) && (
                                        <div className="text-[9px] text-muted-foreground/50 font-mono">
                                          {rp && <span>path: {rp} </span>}
                                          {rbParts.join(' · ')}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}
                                {msg.responseData?.rewritten_query && (
                                  <div className="mt-2 text-xs text-muted-foreground italic">
                                    Interpreted as: "{msg.responseData.rewritten_query}"
                                  </div>
                                )}
                                {msg.responseData?.citations?.length ? (
                                  <div className="mt-3 pt-2 border-t border-border/50 space-y-2">
                                    <p className="text-xs font-medium text-muted-foreground">Sources</p>
                                    <ol className="space-y-1.5 text-xs text-muted-foreground list-decimal list-inside">
                                      {msg.responseData.citations.map((c, idx) => (
                                        <li key={`${c.document_id || 'src'}-${c.chunk_id || idx}`} className="break-words">
                                          <span className="font-medium text-foreground">{c.title || c.source || 'Source'}</span>
                                          {typeof c.score === 'number' && (
                                            <span className="ml-1 text-[10px] opacity-70">({c.score})</span>
                                          )}
                                          {c.snippet && (
                                            <span className="block mt-0.5 opacity-80 whitespace-pre-wrap">{c.snippet}{c.snippet.length >= 200 ? '…' : ''}</span>
                                          )}
                                        </li>
                                      ))}
                                    </ol>
                                  </div>
                                ) : (msg.responseData?.source ? (
                                  <p className="text-xs text-muted-foreground mt-2">Source: {msg.responseData.source}</p>
                                ) : null)}
                                <div className="flex items-center gap-1 mt-2 pt-2 border-t border-border/50">
                                  <span className="text-xs text-muted-foreground mr-1">Was this helpful?</span>
                                  {feedbackSent[`${selectedChatId}-${i}`] ? (
                                    <span className="text-xs text-muted-foreground">Thank you for feedback.</span>
                                  ) : (
                                    <>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8"
                                        disabled={feedbackSubmitting}
                                        onClick={async () => {
                                          const questionText = currentMessages[i - 1]?.content || '';
                                          if (!questionText) return;
                                          setFeedbackSubmitting(true);
                                          try {
                                            await frontlineAgentService.submitKnowledgeFeedback({
                                              question: questionText,
                                              helpful: true,
                                              document_id: msg.responseData?.document_id ?? undefined,
                                            });
                                            setFeedbackSent((prev) => ({ ...prev, [`${selectedChatId}-${i}`]: true }));
                                          } catch {
                                            toast({ title: 'Error', description: 'Could not send feedback', variant: 'destructive' });
                                          } finally {
                                            setFeedbackSubmitting(false);
                                          }
                                        }}
                                        title="Yes, helpful"
                                      >
                                        <ThumbsUp className="h-4 w-4" />
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8"
                                        disabled={feedbackSubmitting}
                                        onClick={async () => {
                                          const questionText = currentMessages[i - 1]?.content || '';
                                          if (!questionText) return;
                                          setFeedbackSubmitting(true);
                                          try {
                                            await frontlineAgentService.submitKnowledgeFeedback({
                                              question: questionText,
                                              helpful: false,
                                              document_id: msg.responseData?.document_id ?? undefined,
                                            });
                                            setFeedbackSent((prev) => ({ ...prev, [`${selectedChatId}-${i}`]: true }));
                                          } catch {
                                            toast({ title: 'Error', description: 'Could not send feedback', variant: 'destructive' });
                                          } finally {
                                            setFeedbackSubmitting(false);
                                          }
                                        }}
                                        title="No, not helpful"
                                      >
                                        <ThumbsDown className="h-4 w-4" />
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                  {/* Suppress spinner when a streaming assistant message is
                      already visible — it has its own inline cursor. */}
                  {answering && !currentMessages.some((m) => m.streaming) && (
                    <div className="flex justify-start">
                      <div className="bg-muted border rounded-2xl px-4 py-3 flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span className="text-sm">Searching knowledge base…</span>
                        <span className="text-xs text-muted-foreground tabular-nums font-mono">
                          <ElapsedTimer since={answeringStartedAt} />
                        </span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                  </div>

                  <form
                    data-tour-qa="input"
                    onSubmit={handleAskQuestion}
                    className="shrink-0"
                    style={{
                      background: 'var(--panel-3)',
                      borderTop: '1px solid hsl(var(--surface-invert) / 0.08)',
                    }}
                  >
                    <div className="mx-4 my-4 space-y-3 rounded-2xl px-4 py-4" style={{ border: '1px solid hsl(var(--surface-invert) / 0.08)' }}>
                      <div className="space-y-2" data-tour-qa="scope">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-muted-foreground">Answer from:</span>
                          <InfoHint {...HINTS.qaScope} />
                          <Select
                            value={qaScopeMode}
                            onValueChange={(v) => {
                              setQaScopeMode(v);
                              if (v !== 'type') setQaScopeDocumentTypes([]);
                              if (v !== 'documents') setQaScopeDocumentIds([]);
                            }}
                          >
                            <SelectTrigger className="w-[180px] h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All documents</SelectItem>
                              <SelectItem value="type">By document type</SelectItem>
                              <SelectItem value="documents">Specific documents</SelectItem>
                            </SelectContent>
                          </Select>

                          {qaScopeMode === 'type' && (
                            <div className="flex flex-wrap items-center gap-2">
                              {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                                <label key={opt.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                                  <Checkbox
                                    checked={qaScopeDocumentTypes.includes(opt.value)}
                                    onCheckedChange={(checked) => {
                                      setQaScopeDocumentTypes((prev) =>
                                        checked ? [...prev, opt.value] : prev.filter((t) => t !== opt.value)
                                      );
                                    }}
                                  />
                                  <span>{opt.label}</span>
                                </label>
                              ))}
                            </div>
                          )}

                          {qaScopeMode === 'documents' && (
                            <Select
                              value="_add"
                              onValueChange={(v) => {
                                if (v === '_add' || v === '_none') return;
                                const id = Number(v);
                                if (!qaScopeDocumentIds.includes(id)) setQaScopeDocumentIds((prev) => [...prev, id]);
                              }}
                            >
                              <SelectTrigger className="w-[220px] h-8">
                                <SelectValue
                                  placeholder={qaDocumentsLoading
                                    ? 'Loading...'
                                    : qaScopeDocumentIds.length
                                      ? 'Add another document...'
                                      : 'Add document...'
                                  }
                                />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="_add">Add document...</SelectItem>
                                {!qaDocumentsLoading &&
                                  qaDocumentsList
                                    .filter((d) => !qaScopeDocumentIds.includes(d.id))
                                    .map((d) => {
                                      // Surface indexing state — a doc that's still
                                      // being processed can't be queried, and a very
                                      // large one just landed will show 'processing'
                                      // for a while. Marking it disabled prevents
                                      // the user from picking a doc that will hang.
                                      const status = d.processing_status || (d.is_indexed ? 'ready' : 'pending');
                                      const notReady = status !== 'ready';
                                      // FRONTLINE-BUG-07: outdated docs stayed
                                      // selectable, making Q&A a dead-end loop —
                                      // pick outdated doc, get outdated answer,
                                      // wonder why. Disable + tag them here.
                                      const outdated = !!d.is_outdated;
                                      const badge = outdated ? '⚠️ outdated' : {
                                        processing: '⏳ processing',
                                        pending:    '⏳ queued',
                                        failed:     '⚠️ failed',
                                      }[status];
                                      const disabled = notReady || outdated;
                                      return (
                                        <SelectItem
                                          key={d.id}
                                          value={String(d.id)}
                                          disabled={disabled}
                                        >
                                          <span className={disabled ? 'opacity-60' : ''}>
                                            {d.title || `Document ${d.id}`}
                                            {badge ? ` — ${badge}` : ''}
                                          </span>
                                        </SelectItem>
                                      );
                                    })}
                              </SelectContent>
                            </Select>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-muted-foreground">Mode:</span>
                          <Select value={inputMode} onValueChange={setInputMode}>
                            <SelectTrigger className="w-[180px] h-8">
                              <div className="flex items-center gap-2">
                                <SelectedModeIcon className="h-4 w-4" />
                                <SelectValue placeholder="Search" />
                              </div>
                            </SelectTrigger>
                            <SelectContent>
                              {INPUT_MODE_OPTIONS.map((mode) => {
                                const ModeIcon = mode.icon;
                                return (
                                  <SelectItem key={mode.value} value={mode.value}>
                                    <div className="flex items-center gap-2">
                                      <ModeIcon className="h-4 w-4" />
                                      <span>{mode.label}</span>
                                    </div>
                                  </SelectItem>
                                );
                              })}
                            </SelectContent>
                          </Select>
                        </div>

                        {qaScopeMode === 'documents' && qaScopeDocumentIds.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {qaScopeDocumentIds.map((id) => {
                              const doc = qaDocumentsList.find((d) => d.id === id);
                              return (
                                <Badge key={id} variant="secondary" className="gap-2">
                                  <span className="truncate max-w-[220px]">{doc?.title || `Document ${id}`}</span>
                                  <button
                                    type="button"
                                    className="opacity-70 hover:opacity-100"
                                    onClick={() => setQaScopeDocumentIds((prev) => prev.filter((x) => x !== id))}
                                    title="Remove"
                                  >
                                    ×
                                  </button>
                                </Badge>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      <div className="flex gap-2 items-start">
                        <div className="pt-2"><InfoHint {...HINTS.qaInput} /></div>
                        <Textarea
                          placeholder={selectedMode.placeholder}
                          value={question}
                          onChange={(e) => setQuestion(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              handleAskQuestion(e);
                            }
                          }}
                          rows={2}
                          disabled={answering}
                          className="min-h-[60px] resize-none flex-1"
                          style={{
                            background: 'var(--sfc-0e0e14)',
                            border: '1px solid hsl(var(--surface-invert) / 0.1)',
                            color: 'hsl(var(--pt-e2e2f0))',
                          }}
                        />
                        <Button type="submit" disabled={answering} size="icon" className="h-[60px] w-12 shrink-0">
                          {answering ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                        </Button>
                      </div>
                    </div>
                  </form>

                  <Dialog open={!!expandedGraph} onOpenChange={(open) => !open && setExpandedGraph(null)}>
                    <DialogContent className="max-w-[95vw] w-full max-h-[90vh] overflow-auto">
                      <DialogHeader className="shrink-0">
                        <DialogTitle>{expandedGraph?.chartTitle || 'Graph'}</DialogTitle>
                      </DialogHeader>
                      <div className="min-h-[400px] py-4">
                        {expandedGraph?.chart && renderChart(expandedGraph.chart)}
                      </div>
                    </DialogContent>
                  </Dialog>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>{/* end DEAD CODE hidden wrapper for QA */}

        {/* Chat widget tab */}
        <TabsContent value="widget" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div className="flex justify-end"><TabTourButton tabKey="widget" /></div>
          <Card className="w-full min-w-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Monitor className="h-5 w-5" />
                Chat widget &amp; web form
              </CardTitle>
              <CardDescription>
                Embed a chat widget or contact form on your website so visitors get support where they are. No login required.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {widgetConfigLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Loading...
                </div>
              ) : widgetKey ? (
                <>
                  <div data-tour-widget="key" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Your widget key</Label>
                      <InfoHint {...HINTS.widgetKey} />
                    </div>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 rounded bg-muted px-3 py-2 text-sm font-mono break-all">{widgetKey}</code>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => {
                          navigator.clipboard.writeText(widgetKey);
                          toast({ title: 'Copied', description: 'Widget key copied to clipboard' });
                        }}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div data-tour-widget="origins" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Allowed origins</Label>
                      <InfoHint {...HINTS.widgetOrigins} />
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">
                      Comma-separated list of domains permitted to use this widget key (e.g.
                      <code className="mx-1 px-1 rounded bg-muted text-[10px]">https://example.com,https://app.example.com</code>).
                      Leave blank to accept any origin — best for testing, risky for prod.
                      Requests from other origins are rejected with 403.
                    </p>
                    <div className="flex items-center gap-2">
                      <Input
                        value={allowedOrigins}
                        onChange={(e) => setAllowedOrigins(e.target.value)}
                        placeholder="https://example.com, https://app.example.com"
                        className="flex-1"
                      />
                      <Button onClick={handleSaveAllowedOrigins} disabled={allowedOriginsSaving}>
                        {allowedOriginsSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                        Save
                      </Button>
                    </div>
                  </div>

                  {/* Theming — pure customisation. Empty values use widget defaults. */}
                  <div data-tour-widget="theme" className="space-y-2 rounded-lg border border-white/[0.06] bg-black/20 p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Label className="text-muted-foreground">Theme & appearance</Label>
                        <InfoHint {...HINTS.widgetTheme} />
                      </div>
                      <Button size="sm" onClick={handleSaveTheme} disabled={themeSaving}>
                        {themeSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                        Save theme
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      All fields optional — blank inputs fall back to the widget's defaults.
                      Customers see these on the embedded chat. CSS overrides are an escape hatch
                      for white-label partners; powerful but unvalidated.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <div>
                        <Label className="text-xs">Primary colour</Label>
                        <Input placeholder="hsl(var(--brand-600))"
                          value={widgetTheme.primary_color}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, primary_color: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Font family</Label>
                        <Input placeholder='"Inter", system-ui, sans-serif'
                          value={widgetTheme.font_family}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, font_family: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Border radius</Label>
                        <Input placeholder="12px or 0.75rem"
                          value={widgetTheme.border_radius}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, border_radius: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Header background</Label>
                        <Input placeholder="defaults to primary colour"
                          value={widgetTheme.header_bg}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, header_bg: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Header text colour</Label>
                        <Input placeholder="#ffffff"
                          value={widgetTheme.header_text_color}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, header_text_color: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">User bubble bg</Label>
                        <Input placeholder="#eef2ff"
                          value={widgetTheme.bubble_bg_user}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, bubble_bg_user: e.target.value }))} />
                      </div>
                      <div>
                        <Label className="text-xs">Agent bubble bg</Label>
                        <Input placeholder="#f8fafc"
                          value={widgetTheme.bubble_bg_agent}
                          onChange={(e) => setWidgetTheme((s) => ({ ...s, bubble_bg_agent: e.target.value }))} />
                      </div>
                    </div>
                    <div>
                      <Label className="text-xs">Custom CSS overrides</Label>
                      <textarea
                        rows={3}
                        placeholder="/* injected into the widget's shadow DOM — use sparingly */"
                        value={widgetTheme.css_overrides}
                        onChange={(e) => setWidgetTheme((s) => ({ ...s, css_overrides: e.target.value }))}
                        className="w-full mt-1 rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs font-mono text-white/85 placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-400/50 resize-none"
                      />
                    </div>
                  </div>
                  <div data-tour-widget="embed" className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Label className="text-muted-foreground">Embed on your site (floating chat button)</Label>
                      <InfoHint {...HINTS.widgetEmbed} />
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">Add this script before &lt;/body&gt;. Replace the origin with your app URL if different.</p>
                    <pre className="rounded bg-muted p-3 text-xs overflow-x-auto relative">
                      <code>{`<script src="${typeof window !== 'undefined' ? window.location.origin : ''}/frontline-widget.js" data-key="${widgetKey}" data-base="${typeof window !== 'undefined' ? window.location.origin : ''}`}{'"></script>'}</code>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-2 right-2 h-8 w-8"
                        onClick={() => {
                          const origin = typeof window !== 'undefined' ? window.location.origin : '';
                          const snippet = `<script src="${origin}/frontline-widget.js" data-key="${widgetKey}" data-base="${origin}"></script>`;
                          navigator.clipboard.writeText(snippet);
                          toast({ title: 'Copied', description: 'Embed code copied to clipboard' });
                        }}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </pre>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Button variant="outline" size="sm" asChild>
                      <a href={`${typeof window !== 'undefined' ? window.location.origin : ''}/embed/chat?key=${widgetKey}`} target="_blank" rel="noopener noreferrer">
                        Open chat page
                      </a>
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <a href={`${typeof window !== 'undefined' ? window.location.origin : ''}/embed/form?key=${widgetKey}`} target="_blank" rel="noopener noreferrer">
                        Open web form
                      </a>
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Could not load widget key. Try again later.</p>
              )}
            </CardContent>
          </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* Tickets Tab */}
        <TabsContent value="tickets" className="space-y-4 mt-4">
          <ErrorBoundary>
          <div className="flex justify-end"><TabTourButton tabKey="tickets" /></div>
          <Card className="w-full min-w-0">
            <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <CardTitle>Support Tickets</CardTitle>
                  <InfoHint {...HINTS.ticketsTable} />
                </div>
                <CardDescription>Create and filter your support tickets</CardDescription>
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
                <Button data-tour-tickets="create" onClick={() => setShowTicketDialog(true)} className="w-full sm:w-auto">
                  <Ticket className="mr-2 h-4 w-4" />
                  Create Ticket
                </Button>
                <InfoHint {...HINTS.ticketsCreate} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4 overflow-x-hidden">
              {ticketsAging && (ticketsAging.count_breached > 0 || ticketsAging.count_at_risk > 0) && (
                <div className="rounded-lg border bg-destructive/10 border-destructive/30 p-3 flex flex-wrap items-center gap-3">
                  <span className="font-medium text-sm">SLA / aging alerts</span>
                  {ticketsAging.count_breached > 0 && (
                    <Badge variant="destructive">{ticketsAging.count_breached} breached</Badge>
                  )}
                  {ticketsAging.count_at_risk > 0 && (
                    <Badge variant="secondary" className="bg-amber-500/20 text-amber-700 dark:text-amber-400">{ticketsAging.count_at_risk} at risk</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">Tickets past due or due within 2 hours. Resolve or reassign to avoid missed SLAs.</span>
                </div>
              )}
              <div data-tour-tickets="filters" className="flex flex-wrap items-center gap-2">
                <InfoHint {...HINTS.ticketsFilters} />
                <Select value={ticketFilters.status || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, status: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[140px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="new">New</SelectItem>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                    <SelectItem value="auto_resolved">Auto Resolved</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={ticketFilters.priority || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, priority: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[120px]">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All priorities</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={ticketFilters.category || 'all'} onValueChange={(v) => { setTicketFilters((f) => ({ ...f, category: v === 'all' ? '' : v })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}>
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All categories</SelectItem>
                    <SelectItem value="technical">Technical</SelectItem>
                    <SelectItem value="billing">Billing</SelectItem>
                    <SelectItem value="account">Account</SelectItem>
                    <SelectItem value="feature_request">Feature Request</SelectItem>
                    <SelectItem value="bug">Bug</SelectItem>
                    <SelectItem value="knowledge_gap">Knowledge gap</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
                {/* FRONTLINE-BUG-08: same bounds as the Analytics tab. */}
                <Input
                  type="date"
                  placeholder="From"
                  className="w-[140px]"
                  value={ticketFilters.date_from}
                  max={ticketFilters.date_to || new Date().toISOString().slice(0, 10)}
                  onChange={(e) => { setTicketFilters((f) => ({ ...f, date_from: e.target.value })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}
                />
                <Input
                  type="date"
                  placeholder="To"
                  className="w-[140px]"
                  value={ticketFilters.date_to}
                  min={ticketFilters.date_from || undefined}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => { setTicketFilters((f) => ({ ...f, date_to: e.target.value })); setTicketsPagination((p) => ({ ...p, page: 1 })); }}
                />
                <Button variant="outline" size="sm" onClick={() => setTicketFilters({ status: '', priority: '', category: '', date_from: '', date_to: '' })}>Clear filters</Button>
              </div>
              {ticketsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : ticketsList.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No tickets found. Create a ticket to get started.
                </div>
              ) : (
                <>
                  {/* Bulk action bar — appears when at least one row is selected. */}
                  {selectedTicketIds.size > 0 && (
                    <div data-tour-tickets="bulk-hint" className="flex items-center gap-2 flex-wrap rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 mb-2">
                      <InfoHint {...HINTS.ticketsBulk} />
                      <span className="text-sm font-medium text-violet-200">
                        {selectedTicketIds.size} selected
                      </span>
                      <div className="flex items-center gap-1 ml-2 flex-wrap">
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'status', value: '' })}>
                          Change status…
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'priority', value: '' })}>
                          Change priority…
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => setBulkActionDialog({ open: true, field: 'category', value: '' })}>
                          Change category…
                        </Button>
                      </div>
                      <Button size="sm" variant="ghost" className="h-7 ml-auto text-xs"
                        onClick={clearTicketSelection}>
                        <XIcon className="h-3.5 w-3.5 mr-1" /> Clear
                      </Button>
                    </div>
                  )}
                  <div data-tour-tickets="table" className="overflow-x-auto -mx-2 sm:mx-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8">
                          <button onClick={toggleAllTicketsOnPage}
                            title={ticketsList.every((t) => selectedTicketIds.has(t.id))
                              ? 'Deselect all on page' : 'Select all on page'}
                            className="text-white/50 hover:text-white/90">
                            {ticketsList.every((t) => selectedTicketIds.has(t.id))
                              ? <CheckSquare className="h-4 w-4" />
                              : <Square className="h-4 w-4" />}
                          </button>
                        </TableHead>
                        <TableHead>Title</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Priority</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead className="whitespace-nowrap">SLA</TableHead>
                        <TableHead>Auto-resolved</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead className="text-right whitespace-nowrap">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ticketsList.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell className="w-8">
                            <button onClick={() => toggleTicketSelected(t.id)}
                              className="text-white/50 hover:text-white/90"
                              title={selectedTicketIds.has(t.id) ? 'Deselect' : 'Select'}>
                              {selectedTicketIds.has(t.id)
                                ? <CheckSquare className="h-4 w-4 text-violet-400" />
                                : <Square className="h-4 w-4" />}
                            </button>
                          </TableCell>
                          <TableCell>
                            <div>
                              <div className="font-medium flex items-center gap-2 flex-wrap">
                                <span>{t.title}</span>
                                {t.pm_task && (
                                  <Badge variant="outline" className="text-[10px] gap-1"
                                    title={`Project task in ${t.pm_task.project}: ${t.pm_task.title}`}>
                                    <ClipboardList className="h-3 w-3" /> Task: {t.pm_task.status_label}
                                  </Badge>
                                )}
                                {t.is_snoozed && (
                                  <Badge variant="outline" className="text-[10px] gap-1">
                                    <Moon className="h-3 w-3" /> Snoozed
                                  </Badge>
                                )}
                                {t.is_sla_paused && (
                                  <Badge variant="outline" className="text-[10px] gap-1 bg-amber-500/10">
                                    <PauseCircle className="h-3 w-3" /> SLA paused
                                  </Badge>
                                )}
                                {t.notes_count > 0 && (
                                  <Badge variant="outline" className="text-[10px] gap-1">
                                    <StickyNote className="h-3 w-3" /> {t.notes_count}
                                  </Badge>
                                )}
                              </div>
                              {t.description && <div className="text-xs text-muted-foreground line-clamp-1">{t.description}</div>}
                            </div>
                          </TableCell>
                          <TableCell><Badge variant="outline">{labelOf(t.status)}</Badge></TableCell>
                          <TableCell><Badge variant="secondary">{labelOf(t.priority)}</Badge></TableCell>
                          <TableCell>{labelOf(t.category)}</TableCell>
                          <TableCell className="text-sm">
                            {t.sla_due_at ? (
                              <span className="flex items-center gap-1 flex-wrap">
                                {t.sla_breached && <Badge variant="destructive" className="text-xs">Breached</Badge>}
                                {t.sla_at_risk && !t.sla_breached && <Badge variant="secondary" className="text-xs bg-amber-500/20 text-amber-700 dark:text-amber-400">At risk</Badge>}
                                <span className="text-muted-foreground">{new Date(t.sla_due_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}</span>
                              </span>
                            ) : '—'}
                          </TableCell>
                          <TableCell>{t.auto_resolved ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : '—'}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</TableCell>
                          <TableCell className="text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8" disabled={ticketBusyId === t.id}>
                                  {ticketBusyId === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <MoreHorizontal className="h-4 w-4" />}
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => openCustomerDialog(t)}>
                                  <User className="h-4 w-4 mr-2" /> View customer
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => openNotesDialog(t)}>
                                  <StickyNote className="h-4 w-4 mr-2" /> Notes{t.notes_count ? ` (${t.notes_count})` : ''}
                                </DropdownMenuItem>
                                {!t.pm_task && (
                                  <DropdownMenuItem onClick={() => setTaskDialogTicket(t)}>
                                    <ClipboardList className="h-4 w-4 mr-2" /> Create project task
                                  </DropdownMenuItem>
                                )}
                                {t.is_snoozed ? (
                                  <DropdownMenuItem onClick={() => handleUnsnooze(t)}>
                                    <Sun className="h-4 w-4 mr-2" /> Unsnooze
                                  </DropdownMenuItem>
                                ) : (
                                  <>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 1)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 1 hour
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 24)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 1 day
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => handleSnooze(t, 72)}>
                                      <Moon className="h-4 w-4 mr-2" /> Snooze 3 days
                                    </DropdownMenuItem>
                                  </>
                                )}
                                <DropdownMenuItem onClick={() => handleToggleSlaPause(t)}>
                                  {t.is_sla_paused ? (
                                    <><PlayCircle className="h-4 w-4 mr-2" /> Resume SLA</>
                                  ) : (
                                    <><PauseCircle className="h-4 w-4 mr-2" /> Pause SLA</>
                                  )}
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleRetriage(t)}>
                                  <RefreshCw className="h-4 w-4 mr-2" /> Re-triage
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  </div>
                  {ticketsPagination.total_pages > 1 && (
                    <div className="flex items-center justify-between pt-2">
                      <p className="text-sm text-muted-foreground">
                        Page {ticketsPagination.page} of {ticketsPagination.total_pages} ({ticketsPagination.total} tickets)
                      </p>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={ticketsPagination.page <= 1} onClick={() => setTicketsPagination((p) => ({ ...p, page: p.page - 1 }))}>
                          <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="sm" disabled={ticketsPagination.page >= ticketsPagination.total_pages} onClick={() => setTicketsPagination((p) => ({ ...p, page: p.page + 1 }))}>
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* Hand-offs Tab */}
        <TabsContent value="handoffs" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="handoffs" /></div>
          <ErrorBoundary><HandoffQueueTab /></ErrorBoundary>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="notifications" /></div>
          <ErrorBoundary><FrontlineNotificationsTab /></ErrorBoundary>
        </TabsContent>

        {/* Workflows Tab */}
        <TabsContent value="workflows" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="workflows" /></div>
          <ErrorBoundary><FrontlineWorkflowsTab /></ErrorBoundary>
        </TabsContent>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="analytics" /></div>
          <ErrorBoundary><FrontlineAnalyticsTab /></ErrorBoundary>
        </TabsContent>

        {/* AI Graphs Tab */}
        <TabsContent value="ai-graphs" className="space-y-4 mt-4">
          <div className="flex justify-end"><TabTourButton tabKey="ai-graphs" /></div>
          <ErrorBoundary><FrontlineAIGraphs /></ErrorBoundary>
        </TabsContent>
      </Tabs>

      {/* Ticket notes dialog (internal / private agent discussion) */}
      <TicketTaskDialog
        ticket={taskDialogTicket}
        open={!!taskDialogTicket}
        onOpenChange={(open) => { if (!open) setTaskDialogTicket(null); }}
        onDone={loadTickets}
      />

      <Dialog open={notesDialog.open} onOpenChange={(open) => setNotesDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Internal notes</DialogTitle>
            <DialogDescription className="line-clamp-1">Ticket: {notesDialog.ticketTitle}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-3 py-2 min-h-0">
            {notesDialog.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : notesDialog.notes.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-6">No notes yet.</div>
            ) : notesDialog.notes.map((n) => (
              <div key={n.id} className="rounded-md border border-border/50 p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {n.author_name || 'Agent'} · {new Date(n.created_at).toLocaleString()}
                  </span>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => deleteNote(n.id)} title="Delete note">
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="mt-1 whitespace-pre-wrap break-words">{n.body}</div>
              </div>
            ))}
          </div>
          <div className="space-y-2 pt-2 border-t border-border/50">
            <Textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              placeholder="Add an internal note (only visible to agents)..."
              rows={3}
            />
            <div className="flex justify-end">
              <Button onClick={submitNote} disabled={!noteDraft.trim()}>
                <Plus className="h-4 w-4 mr-1" /> Add note
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Customer 360 dialog — contact info + ticket history for the ticket's customer */}
      <Dialog open={customerDialog.open} onOpenChange={(open) => setCustomerDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Customer</DialogTitle>
            <DialogDescription className="line-clamp-1">Ticket: {customerDialog.ticketTitle}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto space-y-4 py-2 min-h-0">
            {customerDialog.loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !customerDialog.contact ? (
              <div className="text-center text-sm text-muted-foreground py-8">
                No customer record linked to this ticket yet.
                <div className="text-xs mt-1">Contacts are created automatically from inbound emails and widget submissions.</div>
              </div>
            ) : (
              <>
                {/* Contact header */}
                <div className="rounded-md border border-border/50 p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">
                        {customerDialog.contact.name || customerDialog.contact.email}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {customerDialog.contact.email}
                        {customerDialog.contact.phone ? ` · ${customerDialog.contact.phone}` : ''}
                      </div>
                    </div>
                    {/* Hard-delete the contact record. Tickets stay; their
                        contact reference is detached (FK null-on-delete). */}
                    <Button
                      variant="ghost" size="icon"
                      className="h-8 w-8 text-destructive hover:text-destructive shrink-0"
                      title="Delete contact"
                      onClick={() => setDeleteContactConfirm({ open: true, busy: false })}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  {(customerDialog.contact.tags || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {customerDialog.contact.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                    <div>
                      <div className="text-muted-foreground">First seen</div>
                      <div>{customerDialog.contact.first_seen_at
                        ? new Date(customerDialog.contact.first_seen_at).toLocaleDateString()
                        : '—'}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Last seen</div>
                      <div>{customerDialog.contact.last_seen_at
                        ? new Date(customerDialog.contact.last_seen_at).toLocaleDateString()
                        : '—'}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">External</div>
                      <div>{customerDialog.contact.external_source
                        ? `${customerDialog.contact.external_source} · ${customerDialog.contact.external_id}`
                        : '—'}</div>
                    </div>
                  </div>
                </div>

                {/* Stats */}
                {customerDialog.stats && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-md border border-border/50 p-3">
                      <div className="text-xs text-muted-foreground">Total tickets</div>
                      <div className="text-2xl font-semibold">{customerDialog.stats.total_tickets}</div>
                    </div>
                    <div className="rounded-md border border-border/50 p-3">
                      <div className="text-xs text-muted-foreground">Open now</div>
                      <div className="text-2xl font-semibold">{customerDialog.stats.open_tickets}</div>
                    </div>
                  </div>
                )}

                {/* Recent tickets */}
                {customerDialog.stats?.recent_tickets?.length > 0 && (
                  <div>
                    <div className="text-sm font-medium mb-2">Recent tickets</div>
                    <div className="space-y-1">
                      {customerDialog.stats.recent_tickets.map((t) => (
                        <div key={t.id} className="rounded border border-border/40 p-2 text-sm flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate">{t.title}</div>
                            <div className="text-xs text-muted-foreground">
                              #{t.id} · {t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <Badge variant="outline" className="text-xs">{labelOf(t.priority)}</Badge>
                            <Badge variant="secondary" className="text-xs">{labelOf(t.status)}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete-contact confirmation. Two-step on purpose because deleting a
          contact is destructive: it detaches them from any open tickets and
          drops their custom_fields/tags. */}
      <Dialog open={deleteContactConfirm.open} onOpenChange={(open) => !open && !deleteContactConfirm.busy && setDeleteContactConfirm({ open: false, busy: false })}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive flex items-center gap-2">
              <Trash2 className="h-4 w-4" /> Delete contact?
            </DialogTitle>
            <DialogDescription>
              Permanently removes <strong>{customerDialog.contact?.email}</strong>. Past tickets remain
              but lose the link to this contact record. Notes attached to the
              contact will be deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteContactConfirm({ open: false, busy: false })} disabled={deleteContactConfirm.busy}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteContact} disabled={deleteContactConfirm.busy}>
              {deleteContactConfirm.busy ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
              Delete contact
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Document result (summary / extract) dialog */}
      <Dialog open={docResultDialog.open} onOpenChange={(open) => setDocResultDialog((prev) => ({ ...prev, open }))}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{docResultDialog.title}</DialogTitle>
            <DialogDescription>
              {docResultDialog.type === 'summary' ? 'AI-generated summary of the document.' : 'Structured data extracted from the document.'}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto rounded border bg-muted/30 p-3">
            {docResultDialog.loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing...</span>
              </div>
            ) : (
              <pre className="text-sm whitespace-pre-wrap break-words font-sans">{docResultDialog.content}</pre>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDocResultDialog((prev) => ({ ...prev, open: false }))}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Document Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a document to add it to your knowledge base. Supported formats: PDF, DOCX, TXT, MD, HTML
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="file">File</Label>
              {/* FRONTLINE-BUG-11: without these `file:` classes the
                  Choose-File button rendered as dark grey on the dark
                  modal and was effectively invisible. Matches the
                  Operations tab's styling for consistency. */}
              <Input
                id="file"
                type="file"
                accept=".pdf,.docx,.doc,.txt,.md,.html"
                onChange={(e) => setUploadFile(e.target.files[0])}
                className="file:mr-3 file:rounded-md file:border file:border-input file:bg-primary file:px-3 file:py-1 file:text-primary-foreground file:font-medium file:cursor-pointer hover:file:bg-primary/90"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="title">Title (optional)</Label>
              <Input
                id="title"
                placeholder="Document title"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                placeholder="Document description"
                value={uploadDescription}
                onChange={(e) => setUploadDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleFileUpload} disabled={!uploadFile}>
              <Upload className="mr-2 h-4 w-4" />
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Ticket Dialog */}
      <TicketSuggestionDialog suggestion={ticketSuggestion} busy={suggestionBusy}
        onResolve={resolveWithSuggestion} onKeepOpen={() => setTicketSuggestion(null)} />
      <RetriageReviewDialog proposal={retriageProposal} busy={suggestionBusy}
        onApply={applyRetriage} onCancel={() => setRetriageProposal(null)} />
      <Dialog open={showTicketDialog} onOpenChange={setShowTicketDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Support Ticket</DialogTitle>
            <DialogDescription>
              Describe your issue and we'll help you resolve it
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ticket-title">Title (optional)</Label>
              <Input
                id="ticket-title"
                placeholder="Brief title for your issue"
                value={ticketTitle}
                onChange={(e) => setTicketTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ticket-description">Description</Label>
              <Textarea
                id="ticket-description"
                placeholder="Describe your issue in detail..."
                value={ticketDescription}
                onChange={(e) => setTicketDescription(e.target.value)}
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTicketDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateTicket} disabled={creatingTicket || !ticketDescription.trim()}>
              {creatingTicket ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  Create Ticket
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk ticket update dialog (#3). Reused across status / priority /
          category — the trigger button decides which field. */}
      <Dialog open={bulkActionDialog.open}
        onOpenChange={(o) => setBulkActionDialog((s) => ({ ...s, open: o }))}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {bulkActionDialog.field === 'status' && 'Change status'}
              {bulkActionDialog.field === 'priority' && 'Change priority'}
              {bulkActionDialog.field === 'category' && 'Change category'}
            </DialogTitle>
            <DialogDescription>
              Applies to {selectedTicketIds.size} selected ticket{selectedTicketIds.size === 1 ? '' : 's'}.
              {bulkActionDialog.field === 'status' && ' Illegal status transitions are skipped per ticket; you\'ll see the count in the result.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Label className="text-xs">New value</Label>
            {bulkActionDialog.field === 'status' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a status" /></SelectTrigger>
                <SelectContent>
                  {['open', 'in_progress', 'resolved', 'closed'].map((v) => <SelectItem key={v} value={v}>{labelOf(v)}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            {bulkActionDialog.field === 'priority' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a priority" /></SelectTrigger>
                <SelectContent>
                  {['low', 'medium', 'high', 'urgent'].map((v) => <SelectItem key={v} value={v}>{labelOf(v)}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            {bulkActionDialog.field === 'category' && (
              <Select value={bulkActionDialog.value}
                onValueChange={(v) => setBulkActionDialog((s) => ({ ...s, value: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a category" /></SelectTrigger>
                <SelectContent>
                  {['technical', 'billing', 'account', 'feature_request', 'bug', 'knowledge_gap', 'other'].map((v) => (
                    <SelectItem key={v} value={v}>{labelOf(v)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline"
              onClick={() => setBulkActionDialog({ open: false, field: null, value: '' })}
              disabled={bulkApplying}>Cancel</Button>
            <Button onClick={handleBulkApply}
              disabled={bulkApplying || !bulkActionDialog.value}>
              {bulkApplying ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Apply to {selectedTicketIds.size}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* First-time onboarding tutorial (main tour) */}
      <FrontlineTutorial
        open={tutorialOpen}
        onClose={() => setTutorialOpen(false)}
        setActiveTab={setActiveTab}
        siblingKeys={flTabTourKeys}
      />

      {/* Per-tab guided tour */}
      {activeTabTour && TAB_TOURS[activeTabTour] && (
        <FrontlineTutorial
          open={!!activeTabTour}
          onClose={() => setActiveTabTour(null)}
          steps={TAB_TOURS[activeTabTour].steps}
          storageKey={TAB_TOURS[activeTabTour].key}
          siblingKeys={flTabTourKeys.filter((k) => k !== TAB_TOURS[activeTabTour].key)}
        />
      )}
    </div>
    </div>
    </div>{/* flex row (sidebar + content) */}
    {/* Floating quick-chat launcher — pinned bottom-right of the viewport,
        rendered via portal so it stays put across every tab. */}
    <FrontlineFloatingChat />
    </HintsProvider>
  );
};

export default FrontlineDashboard;

