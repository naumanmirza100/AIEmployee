import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Loader2, Send, Sparkles } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import ChatMarkdown from '@/components/shared/ChatMarkdown';
import ChatShell from '@/components/shared/ChatShell';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import useQuickChatHistory from '@/hooks/useQuickChatHistory';
import { companyApi, getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { postNdjson } from '@/utils/ndjsonStream';
import { getAgentNavItems } from '@/utils/agentNavItems';

/**
 * /company/assistant — the Company Assistant (CO-18): one chat that asks across the agents a company has
 * (backend: core/assistant). It reads only; each answer lists the screens its facts came from. Its conversations
 * are kept on the server with the other Quick Chats. Laid out like the PM agent's chats since 14 Nov 2026
 * (components/shared/ChatShell): the chats on the left, the conversation and its composer on the right.
 */
const newId = () => `a${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
// The answer cites its facts as [3]; the sources are listed under it instead.
const clean = (text) => String(text || '').replace(/\s?\[\d+\]/g, '');

export default function CompanyAssistantPage() {
  const navigate = useNavigate();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const { history, refresh, save, remove } = useQuickChatHistory('assistant');

  const [status, setStatus] = useState(null);
  const [chat, setChat] = useState({ id: newId(), title: '', messages: [] });
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    companyApi.get('/company/assistant')
      .then((res) => setStatus(res?.data || { included: false }))
      .catch(() => setStatus({ included: false, failed: true }));
    refresh();
  }, [refresh]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [chat.messages, busy]);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  const ask = async (text) => {
    const q = (text ?? question).trim();
    if (!q || busy) return;
    setQuestion('');
    const turns = chat.messages.map((m) => ({ role: m.role, content: m.content }));
    const asked = { ...chat, title: chat.title || q.slice(0, 60), messages: [...chat.messages, { role: 'user', content: q }] };
    setChat(asked);
    setBusy(true);
    // The answer appears as it is written (company/assistant/ask-stream): its pieces go into the last message,
    // and the finished answer, with its sources and any flagged figure, replaces them at the end.
    const show = (reply) => setChat({ ...asked, messages: [...asked.messages, reply] });
    let reply = { role: 'assistant', content: '', streaming: true };
    try {
      await postNdjson('/company/assistant/ask-stream', { question: q, history: turns.slice(-8) }, {
        onEvent: (event) => {
          if (event.type === 'token') {
            reply = { ...reply, content: reply.content + event.value };
            show(reply);
          } else if (event.type === 'done') {
            reply = { role: 'assistant', content: event.answer || reply.content || '(no answer)',
              sources: event.sources || [], askedBack: !!event.asked_back };
          } else if (event.type === 'error') {
            reply = { role: 'assistant', content: event.message || 'The assistant could not answer just now.', error: true };
          }
        },
      });
      if (reply.streaming) reply = { ...reply, streaming: false, content: reply.content || '(no answer)' };
    } catch (e) {
      reply = { role: 'assistant', content: e?.message || 'The assistant could not answer just now.', error: true };
    }
    const done = { ...asked, messages: [...asked.messages, reply] };
    setChat(done);
    setBusy(false);
    save(done);
  };

  const writing = busy && chat.messages[chat.messages.length - 1]?.streaming;

  const open = (c) => setChat({ id: c.id, title: c.title, messages: c.messages || [] });
  const startNew = () => setChat({ id: newId(), title: '', messages: [] });

  const included = status?.included;

  return (
    <>
      <Helmet><title>Company Assistant | Pay Per Project</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={Sparkles}
          title="Company Assistant"
          subtitle="Ask across your agents"
          user={companyUser}
          userRole="Company User"
          onLogout={handleLogout}
          showNavTabs
          activeSection="dashboard"
          navItems={getAgentNavItems(purchasedModules, 'dashboard', navigate)}
          sidebarLoading={!modulesLoaded}
        />
        <div className="container mx-auto max-w-full px-3 py-4 sm:px-8 sm:py-6">
          {status === null ? (
            <div className="flex justify-center pt-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : !included ? (
            <div data-testid="assistant-not-included" className="mx-auto mt-10 max-w-md rounded-xl border border-border bg-[var(--panel-2)] p-6 text-center">
              <Sparkles className="mx-auto mb-3 h-10 w-10 text-violet-400" />
              <h1 className="text-lg font-semibold text-foreground">
                {status.failed ? 'The assistant could not be reached' : 'The Company Assistant comes with two agents or more'}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {status.failed ? 'Please try again in a minute.'
                  : 'It answers questions that need several agents at once, such as who is free next week or who is overloaded. This company has fewer than two agents.'}
              </p>
              {!status.failed && (
                <Button className="mt-4 w-full" onClick={() => navigate('/company/dashboard/ai-agents')}>See AI agents</Button>
              )}
            </div>
          ) : (
            <ChatShell
              icon={Sparkles} title="Company Assistant" badge="Reads only" testId="assistant"
              description={`Reads ${status.reads?.join(', ') || 'your agents'}.${status.not_yet?.length ? ` Not yet: ${status.not_yet.join(', ')}.` : ''} It never assigns, books or emails.`}
              chats={history.map((c) => ({ id: c.id, title: c.title, updatedAt: c.updated_at,
                detail: `${Math.ceil((c.messages?.length || 0) / 2)} question${(c.messages?.length || 0) > 2 ? 's' : ''}` }))}
              selectedId={chat.messages.length ? chat.id : null}
              onSelect={(c) => { if (!busy) open(history.find((h) => h.id === c.id) || c); }}
              onNew={() => { if (!busy) startNew(); }}
              onDelete={(c) => { remove(c.id); if (c.id === chat.id) startNew(); }}
              emptyChatsText="No chats yet. Ask a question to start one."
              composer={(
                <form className="mx-3 my-3 flex items-start gap-2 rounded-xl border border-border px-3 py-3 sm:mx-4"
                  onSubmit={(e) => { e.preventDefault(); ask(); }}>
                  <Textarea
                    data-testid="assistant-input"
                    rows={1}
                    className="min-h-[40px] flex-1 resize-none text-sm"
                    placeholder="Ask a question, e.g. Who is away next week?"
                    value={question}
                    maxLength={2000}
                    disabled={busy}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }}
                  />
                  <Button type="submit" size="icon" className="h-[40px] w-10 shrink-0" disabled={busy || !question.trim()} data-testid="assistant-send" title="Ask">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </form>
              )}
            >
              <span className="sr-only" data-testid="assistant-reads">Reads {status.reads?.join(', ')}.</span>
              {chat.messages.length === 0 && (
                <div className="pt-6 text-center">
                  <Sparkles className="mx-auto mb-2 h-8 w-8 text-violet-400" />
                  <p className="text-sm text-muted-foreground">Ask about your people, their time and their work, across your agents.</p>
                  <div className="mt-4 flex flex-wrap justify-center gap-2" data-testid="assistant-suggestions">
                    {(status.suggestions || []).map((s) => (
                      <button key={s} type="button" onClick={() => ask(s)}
                        className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-accent">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {chat.messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
                  {m.role === 'user' ? (
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-violet-600 px-4 py-2 text-sm text-pure-white">{m.content}</div>
                  ) : (
                    <div data-testid="assistant-answer" className={`max-w-[90%] rounded-2xl border px-4 py-2 text-sm ${m.error ? 'border-red-500/40 text-red-300' : 'border-border bg-[var(--panel-2)] text-foreground'}`}>
                      <ChatMarkdown>{clean(m.content)}</ChatMarkdown>
                      {m.sources?.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border pt-2" data-testid="assistant-sources">
                          <span className="text-[11px] text-muted-foreground">Sources:</span>
                          {m.sources.map((src) => (
                            src.link ? (
                              <button key={`${src.label}${src.link}`} type="button" onClick={() => navigate(src.link)}
                                className="inline-flex items-center gap-0.5 rounded-full border border-border px-2 py-0.5 text-[11px] text-violet-300 hover:bg-accent">
                                {src.label} <ArrowUpRight className="h-3 w-3" />
                              </button>
                            ) : (
                              <span key={`${src.label}`} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">{src.label}</span>
                            )
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {busy && !writing && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Looking it up…</div>
              )}
              <div ref={endRef} />
            </ChatShell>
          )}
        </div>
      </div>
    </>
  );
}
