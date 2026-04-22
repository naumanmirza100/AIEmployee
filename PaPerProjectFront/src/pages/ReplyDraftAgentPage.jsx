import React, { useState, useEffect, useCallback } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { checkModuleAccess } from '@/services/modulePurchaseService';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getAgentNavItems } from '@/utils/agentNavItems';
import { Reply, Loader2, Lock, Send, RefreshCw, X, Check, Edit3, Inbox } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  listPendingReplies,
  listDrafts,
  generateDraft,
  regenerateDraft,
  approveDraft,
  rejectDraft,
  sendDraft,
} from '@/services/replyDraftService';

const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly',     label: 'Friendly' },
  { value: 'formal',       label: 'Formal' },
  { value: 'casual',       label: 'Casual' },
  { value: 'apologetic',   label: 'Apologetic' },
  { value: 'confident',    label: 'Confident' },
  { value: 'empathetic',   label: 'Empathetic' },
];

const ReplyDraftAgentPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [companyUser, setCompanyUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasAccess, setHasAccess] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(true);
  const [activeSection] = useState('reply-draft');
  const { purchasedModules, modulesLoaded } = usePurchasedModules();

  const [pendingReplies, setPendingReplies] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [selectedReply, setSelectedReply] = useState(null);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [tone, setTone] = useState('professional');
  const [userContext, setUserContext] = useState('');
  const [editedSubject, setEditedSubject] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState('inbox'); // inbox | drafts

  useEffect(() => {
    const companyUserStr = localStorage.getItem('company_user');
    if (!companyUserStr) {
      toast({ title: 'Not logged in', description: 'Please log in to access the reply draft agent', variant: 'destructive' });
      navigate('/company/login');
      return;
    }
    try {
      setCompanyUser(JSON.parse(companyUserStr));
      (async () => {
        try {
          const res = await checkModuleAccess('reply_draft_agent');
          if (res.status === 'success') setHasAccess(res.has_access);
        } catch {
          setHasAccess(true);
        } finally {
          setCheckingAccess(false);
          setLoading(false);
        }
      })();
    } catch {
      localStorage.removeItem('company_user');
      navigate('/company/login');
    }
  }, [navigate, toast]);

  const refreshInbox = useCallback(async () => {
    try {
      const res = await listPendingReplies();
      setPendingReplies(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load inbox', description: e.message, variant: 'destructive' });
    }
  }, [toast]);

  const refreshDrafts = useCallback(async () => {
    try {
      const res = await listDrafts();
      setDrafts(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load drafts', description: e.message, variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => {
    if (hasAccess) {
      refreshInbox();
      refreshDrafts();
    }
  }, [hasAccess, refreshInbox, refreshDrafts]);

  const handleLogout = () => {
    localStorage.removeItem('company_auth_token');
    localStorage.removeItem('company_user');
    localStorage.removeItem('company_purchased_modules');
    navigate('/company/login');
  };

  const handleGenerate = async () => {
    if (!selectedReply) return;
    setBusy(true);
    try {
      const res = await generateDraft({
        originalEmailId: selectedReply.id,
        userContext,
        tone,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Draft generated' });
        setEditedSubject(d.subject);
        setEditedBody(d.body);
        setSelectedDraft({
          id: d.draft_id,
          status: 'pending',
          subject: d.subject,
          body: d.body,
          tone,
          ai_notes: d.reasoning,
        });
        refreshInbox();
        refreshDrafts();
      }
    } catch (e) {
      toast({ title: 'Generation failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      const res = await regenerateDraft(selectedDraft.id, {
        newInstructions: userContext,
        tone,
      });
      const d = res?.data;
      if (d?.draft_id) {
        toast({ title: 'Regenerated' });
        setEditedSubject(d.subject);
        setEditedBody(d.body);
        setSelectedDraft({ ...selectedDraft, id: d.draft_id, subject: d.subject, body: d.body, ai_notes: d.reasoning });
        refreshDrafts();
      }
    } catch (e) {
      toast({ title: 'Regeneration failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleApproveAndSend = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      const ap = await approveDraft(selectedDraft.id, {
        editedSubject,
        editedBody,
      });
      if (ap.status !== 'success') throw new Error(ap.message || 'Approve failed');
      const sent = await sendDraft(selectedDraft.id);
      if (sent.status === 'success') {
        toast({ title: 'Reply sent' });
        setSelectedDraft(null);
        setSelectedReply(null);
        setEditedSubject('');
        setEditedBody('');
        setUserContext('');
        refreshInbox();
        refreshDrafts();
      } else {
        throw new Error(sent.message || 'Send failed');
      }
    } catch (e) {
      toast({ title: 'Send failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!selectedDraft) return;
    setBusy(true);
    try {
      await rejectDraft(selectedDraft.id);
      toast({ title: 'Draft rejected' });
      setSelectedDraft(null);
      refreshDrafts();
    } catch (e) {
      toast({ title: 'Reject failed', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  if (loading || checkingAccess || !modulesLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!companyUser) return null;

  if (!hasAccess) {
    return (
      <>
        <Helmet><title>Access Denied | Reply Draft Agent</title></Helmet>
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <div className="flex items-center justify-center mb-4">
                <Lock className="h-12 w-12 text-muted-foreground" />
              </div>
              <CardTitle className="text-center">Module Not Purchased</CardTitle>
              <CardDescription className="text-center">
                You need to purchase the Reply Draft Agent module to access this dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button onClick={() => navigate('/')} className="w-full">Go to Home to Purchase</Button>
              <Button onClick={() => navigate('/company/dashboard')} variant="outline" className="w-full">Back to Dashboard</Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Helmet><title>Reply Draft Agent | Pay Per Project</title></Helmet>
      <div
        className="min-h-screen"
        style={{ background: 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)' }}
      >
        <DashboardNavbar
          icon={Reply}
          title={companyUser.companyName || 'Reply Draft Agent'}
          subtitle={companyUser.fullName}
          user={companyUser}
          userRole="Company User"
          showNavTabs={true}
          activeSection={activeSection}
          onLogout={handleLogout}
          navItems={getAgentNavItems(purchasedModules, 'reply-draft', navigate)}
        />

        <div className="container mx-auto px-3 sm:px-4 py-4 max-w-full overflow-x-hidden">
          <div className="grid grid-cols-12 gap-4">
            {/* Left: Inbox + Drafts list */}
            <div className="col-span-12 md:col-span-4">
              <Card className="bg-black/40 border-white/10 text-white">
                <CardHeader className="pb-2">
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant={activeTab === 'inbox' ? 'default' : 'outline'}
                      onClick={() => setActiveTab('inbox')}
                    >
                      <Inbox className="h-4 w-4 mr-1" />
                      Inbox ({pendingReplies.length})
                    </Button>
                    <Button
                      size="sm"
                      variant={activeTab === 'drafts' ? 'default' : 'outline'}
                      onClick={() => setActiveTab('drafts')}
                    >
                      <Edit3 className="h-4 w-4 mr-1" />
                      Drafts ({drafts.length})
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 max-h-[70vh] overflow-y-auto">
                  {activeTab === 'inbox' && pendingReplies.map((r) => (
                    <div
                      key={r.id}
                      onClick={() => { setSelectedReply(r); setSelectedDraft(null); setEditedBody(''); setEditedSubject(''); setUserContext(''); }}
                      className={`p-2 rounded border cursor-pointer hover:bg-white/5 ${selectedReply?.id === r.id ? 'border-cyan-500 bg-white/5' : 'border-white/10'}`}
                    >
                      <div className="text-sm font-medium truncate">{r.from}</div>
                      <div className="text-xs text-gray-400 truncate">{r.subject}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {r.interest_level && <span className="inline-block px-1 rounded bg-cyan-500/20 text-cyan-300 text-[10px] uppercase mr-1">{r.interest_level}</span>}
                        <span>{r.replied_at ? new Date(r.replied_at).toLocaleString() : ''}</span>
                      </div>
                    </div>
                  ))}
                  {activeTab === 'inbox' && pendingReplies.length === 0 && (
                    <div className="text-sm text-gray-400 p-4 text-center">No pending replies</div>
                  )}
                  {activeTab === 'drafts' && drafts.map((d) => (
                    <div
                      key={d.id}
                      onClick={() => { setSelectedDraft(d); setSelectedReply(null); setEditedSubject(d.subject); setEditedBody(d.body); }}
                      className={`p-2 rounded border cursor-pointer hover:bg-white/5 ${selectedDraft?.id === d.id ? 'border-cyan-500 bg-white/5' : 'border-white/10'}`}
                    >
                      <div className="text-sm font-medium truncate">{d.to}</div>
                      <div className="text-xs text-gray-400 truncate">{d.subject}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        <span className="inline-block px-1 rounded bg-white/10 text-[10px] uppercase mr-1">{d.status}</span>
                        <span>{d.tone}</span>
                      </div>
                    </div>
                  ))}
                  {activeTab === 'drafts' && drafts.length === 0 && (
                    <div className="text-sm text-gray-400 p-4 text-center">No drafts yet</div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Right: Editor */}
            <div className="col-span-12 md:col-span-8">
              <Card className="bg-black/40 border-white/10 text-white">
                <CardHeader>
                  <CardTitle className="text-lg">
                    {selectedReply ? 'Draft a Reply' : selectedDraft ? 'Review Draft' : 'Select a reply or draft'}
                  </CardTitle>
                  {selectedReply && (
                    <CardDescription className="text-gray-400">
                      From: <span className="text-white">{selectedReply.from}</span><br />
                      Subject: <span className="text-white">{selectedReply.subject}</span>
                      {selectedReply.preview && (
                        <div className="mt-2 p-2 bg-white/5 rounded text-xs text-gray-300">
                          {selectedReply.preview}
                        </div>
                      )}
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent className="space-y-3">
                  {(selectedReply || selectedDraft) && (
                    <>
                      <div className="flex gap-2 items-center">
                        <label className="text-xs text-gray-400 w-20">Tone</label>
                        <select
                          className="bg-black/60 border border-white/10 rounded px-2 py-1 text-sm"
                          value={tone}
                          onChange={(e) => setTone(e.target.value)}
                          disabled={busy}
                        >
                          {TONES.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Instructions for AI (optional)</label>
                        <textarea
                          className="w-full bg-black/60 border border-white/10 rounded p-2 text-sm"
                          rows={2}
                          placeholder="e.g. keep it short, mention pricing, schedule a demo..."
                          value={userContext}
                          onChange={(e) => setUserContext(e.target.value)}
                          disabled={busy}
                        />
                      </div>
                      {selectedReply && !selectedDraft && (
                        <Button onClick={handleGenerate} disabled={busy} className="w-full">
                          {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Edit3 className="h-4 w-4 mr-2" />}
                          Generate Draft
                        </Button>
                      )}
                    </>
                  )}

                  {selectedDraft && (
                    <>
                      <div>
                        <label className="text-xs text-gray-400">Subject</label>
                        <input
                          className="w-full bg-black/60 border border-white/10 rounded p-2 text-sm"
                          value={editedSubject}
                          onChange={(e) => setEditedSubject(e.target.value)}
                          disabled={busy || selectedDraft.status === 'sent'}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Body</label>
                        <textarea
                          className="w-full bg-black/60 border border-white/10 rounded p-2 text-sm"
                          rows={12}
                          value={editedBody}
                          onChange={(e) => setEditedBody(e.target.value)}
                          disabled={busy || selectedDraft.status === 'sent'}
                        />
                      </div>
                      {selectedDraft.ai_notes && (
                        <div className="text-xs text-gray-400 italic p-2 bg-white/5 rounded">
                          AI notes: {selectedDraft.ai_notes}
                        </div>
                      )}
                      {selectedDraft.status !== 'sent' && (
                        <div className="flex gap-2 flex-wrap">
                          <Button onClick={handleRegenerate} disabled={busy} variant="outline">
                            {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                            Regenerate
                          </Button>
                          <Button onClick={handleApproveAndSend} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700">
                            {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                            Approve & Send
                          </Button>
                          <Button onClick={handleReject} disabled={busy} variant="outline" className="text-red-400 border-red-400/40">
                            <X className="h-4 w-4 mr-2" />
                            Discard
                          </Button>
                        </div>
                      )}
                      {selectedDraft.status === 'sent' && (
                        <div className="flex items-center gap-2 p-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-emerald-300 text-sm">
                          <Check className="h-4 w-4" />
                          Sent on {selectedDraft.sent_at ? new Date(selectedDraft.sent_at).toLocaleString() : '—'}
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default ReplyDraftAgentPage;
