import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { AlertTriangle, CheckCircle2, Clock, CreditCard, DollarSign, Inbox, Key, Send, ShieldCheck, XCircle } from 'lucide-react';

/**
 * Shared building blocks for the admin API-keys screens.
 *
 * These were defined inside SuperAdminApiKeysPage; the tab components now live
 * in their own files and several of them need the same styles, provider
 * metadata and formatters, so they are centralised here rather than duplicated.
 */

export const GRADIENT_BG = 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';
export const CARD_CLASS = 'bg-[#120d22] border border-[#2d2342]';
export const ROW_CLASS = 'bg-[#0f0a20] border border-[#2d2342] hover:border-violet-500/30 transition-colors';


export const ProviderLogo = ({ provider, size = 20 }) => {
  const s = size;
  switch (provider) {
    case 'groq': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#F55036"/>
        <path d="M44 26H36V38H44C44 38 48 38 48 32C48 26 44 26 44 26Z" fill="white"/>
        <path d="M20 26C20 26 16 26 16 32C16 38 20 38 20 38H32V32H24V30H32V26H20Z" fill="white"/>
      </svg>
    );
    case 'openai': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#10a37f"/>
        <path d="M46 28.5C46 22.7 41.3 18 35.5 18C32.4 18 29.6 19.3 27.6 21.4C26.7 21.1 25.7 21 24.7 21C19.7 21 15.7 25 15.7 30C15.7 30.9 15.8 31.8 16.1 32.6C14.8 33.9 14 35.7 14 37.7C14 41.7 17.3 45 21.3 45C22.3 45 23.2 44.8 24.1 44.4C25.8 45.4 27.7 46 29.8 46C33 46 35.9 44.6 37.9 42.4C38.4 42.5 38.9 42.5 39.4 42.5C44.1 42.5 48 38.6 48 33.9C48 31.9 47.3 30.1 46.1 28.7L46 28.5Z" fill="white" opacity="0.9"/>
      </svg>
    );
    case 'claude': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#CC785C"/>
        <text x="32" y="42" textAnchor="middle" fontSize="28" fontWeight="bold" fill="white" fontFamily="serif">A</text>
      </svg>
    );
    case 'gemini': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#1a73e8"/>
        <path d="M32 14C32 14 22 32 32 32C42 32 32 50 32 50C32 50 42 32 32 32C22 32 32 14 32 14Z" fill="white"/>
      </svg>
    );
    case 'grok': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#000"/>
        <text x="32" y="42" textAnchor="middle" fontSize="28" fontWeight="bold" fill="white" fontFamily="sans-serif">X</text>
      </svg>
    );
    default: return (
      <div style={{ width: s, height: s }} className="rounded-full bg-violet-500/30 flex items-center justify-center text-white text-xs font-bold">
        {provider[0]?.toUpperCase()}
      </div>
    );
  }
};


export const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq (Llama)' },
  { value: 'claude', label: 'Claude / Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'grok', label: 'xAI Grok' },
];

// Agent lists now come from the DB via useAgents() — see the hook for why.
// Nothing agent-specific should be hardcoded in this file.

export const formatTokens = (n) => {
  if (n == null) return '—';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};


export const StatCard = ({ icon: Icon, label, value, accent }) => (
  <div className={`${CARD_CLASS} rounded-xl p-4 hover:border-violet-500/30 transition-colors`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-white/40 mb-1">{label}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
  </div>
);

// -------------------- Platform Keys Tab --------------------
// Expected key prefixes per provider for frontend validation

export const PROVIDER_KEY_PREFIXES = {
  openai:  { prefixes: ['sk-'], hint: 'OpenAI keys start with sk-' },
  groq:    { prefixes: ['gsk_'], hint: 'Groq keys start with gsk_' },
  claude:  { prefixes: ['sk-ant-'], hint: 'Anthropic keys start with sk-ant-' },
  gemini:  { prefixes: ['AIza'], hint: 'Gemini keys start with AIza' },
  grok:    { prefixes: ['xai-'], hint: 'xAI Grok keys start with xai-' },
};


export const PROVIDER_LABELS = Object.fromEntries(PROVIDER_OPTIONS.map(p => [p.value, p.label]));

export const PROVIDER_ACCENT = {
  openai:  'text-green-300 bg-green-500/10 border-green-500/20',
  groq:    'text-violet-300 bg-violet-500/10 border-violet-500/20',
  claude:  'text-orange-300 bg-orange-500/10 border-orange-500/20',
  gemini:  'text-blue-300 bg-blue-500/10 border-blue-500/20',
  grok:    'text-red-300 bg-red-500/10 border-red-500/20',
};


export const REQUEST_STATUS_META = {
  pending:          { label: 'Pending',           cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30',     Icon: Clock },
  payment_pending:  { label: 'Payment Required',  cls: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', Icon: DollarSign },
  payment_received: { label: 'Payment Received',  cls: 'bg-blue-500/15 text-blue-300 border-blue-500/30',       Icon: CreditCard },
  key_assigned:     { label: 'Key Assigned',      cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', Icon: ShieldCheck },
  key_expired:      { label: 'Key Expired',       cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30',       Icon: Clock },
  approved:         { label: 'Approved',          cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', Icon: CheckCircle2 },
  rejected:         { label: 'Rejected',          cls: 'bg-red-500/15 text-red-300 border-red-500/30',           Icon: XCircle },
  revoked:          { label: 'Revoked',           cls: 'bg-orange-500/15 text-orange-300 border-orange-500/30',  Icon: XCircle },
};

// Single timeline entry for one KeyRequest record (or a synthetic revocation node)
