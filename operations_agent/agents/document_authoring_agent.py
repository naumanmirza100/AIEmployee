"""
Operations Document Authoring Agent

Generates professional documents (reports, memos, proposals, analyses) from a
user prompt plus optional reference documents. Uses Groq for high-quality
markdown writing and stores the result in OperationsGeneratedDocument.
"""

import logging
from typing import Dict, List, Optional

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from operations_agent.models import OperationsDocument

logger = logging.getLogger(__name__)


TEMPLATE_GUIDES = {
    'weekly_report': {
        'name': 'Weekly Report',
        'outline': [
            '# {title}',
            '',
            '## Executive Summary',
            '## Key Accomplishments This Week',
            '## In-Progress Initiatives',
            '## Blockers & Risks',
            '## Metrics & KPIs',
            '## Plan for Next Week',
            '## Appendix / Supporting Data',
        ],
        'guidance': 'Cover the week\'s progress with specific metrics, named owners, and clear next steps. Use tables for metrics.',
    },
    'monthly_analysis': {
        'name': 'Monthly Analysis',
        'outline': [
            '# {title}',
            '',
            '## Overview',
            '## Performance Analysis',
            '## Trends & Insights',
            '## Risks & Mitigation',
            '## Opportunities',
            '## Recommendations',
            '## Conclusion',
        ],
        'guidance': 'Analytical tone. Support every claim with evidence from the reference documents. Include tables and breakdowns where data warrants.',
    },
    'executive_summary': {
        'name': 'Executive Summary',
        'outline': [
            '# {title}',
            '',
            '## TL;DR',
            '## Background',
            '## Findings',
            '## Impact & Implications',
            '## Recommendations',
            '## Next Steps',
        ],
        'guidance': 'Concise, executive-level. Lead every section with the bottom line. Avoid fluff. Max ~500 words unless data requires otherwise.',
    },
    'memo': {
        'name': 'Memo',
        'outline': [
            '**MEMORANDUM**',
            '',
            '**To:** [Recipient]',
            '**From:** [Author]',
            '**Date:** [Today]',
            '**Subject:** {title}',
            '',
            '---',
            '',
            '## Purpose',
            '## Background',
            '## Discussion',
            '## Recommendation',
            '## Action Required',
        ],
        'guidance': 'Formal memo style. Keep it direct. Recommendation section must be specific and actionable.',
    },
    'proposal': {
        'name': 'Proposal',
        'outline': [
            '# {title}',
            '',
            '## Executive Summary',
            '## Problem Statement',
            '## Proposed Solution',
            '## Scope & Deliverables',
            '## Timeline',
            '## Budget & Resources',
            '## Risks & Mitigations',
            '## Success Metrics',
            '## Conclusion',
        ],
        'guidance': 'Persuasive and structured. Quantify benefits. Include a timeline table and a budget table where applicable.',
    },
    'custom': {
        'name': 'Custom',
        'outline': None,
        'guidance': 'Follow the user\'s prompt exactly. Use clear headings and sub-headings, bullets, and tables where data is present.',
    },
}


TONE_GUIDES = {
    'formal': 'Formal, polished corporate tone. Use third person. Avoid contractions.',
    'concise': 'Concise and punchy. Short sentences. Prioritise bullet points and tables over prose.',
    'detailed': 'Detailed and thorough. Cover edge cases and assumptions. Include supporting evidence for each claim.',
    'technical': 'Technical and precise. Use industry terminology where appropriate. Include specifics (numbers, dates, named entities).',
}


BASE_SYSTEM = (
    "You are a senior operations analyst and professional writer. "
    "You produce publication-ready business documents in GitHub-flavored Markdown. "
    "You never invent data — if the reference excerpts don't contain a fact, either omit it "
    "or mark it as *[placeholder]* so the user can fill it in.\n\n"
    "FORMATTING RULES:\n"
    "1. Always start the document with an `# H1` title.\n"
    "2. Use `## H2` for main sections and `### H3` for sub-sections.\n"
    "3. Use **bold** for emphasis on key terms, numbers, names, and dates.\n"
    "4. Use bullet lists (`- item`) for enumerations and numbered lists for ordered steps.\n"
    "5. Use Markdown tables for any metric/numeric data.\n"
    "6. Separate major sections with blank lines. Keep paragraphs short (3-5 sentences).\n"
    "7. Close the document with a brief conclusion or action summary.\n\n"
    "QUALITY RULES:\n"
    "- Be specific: cite numbers, percentages, dates, and named entities from the reference material.\n"
    "- Be factual: every claim should be defensible from the references or the user's prompt.\n"
    "- Be coherent: sections should flow logically and reinforce one another.\n"
)


class DocumentAuthoringAgent(MarketingBaseAgent):
    """Generate professional documents using Groq + reference context."""

    MAX_REF_CHARS = 10000
    MAX_PER_REF_CHARS = 2500
    MAX_TOKENS = 4000

    def __init__(self):
        try:
            super().__init__(use_embeddings=False)
        except Exception as e:
            logger.error(f'DocumentAuthoringAgent init warning: {e}')
        self.agent_name = 'DocumentAuthoringAgent'

    # ──────────────────────────────────────────────
    def generate(
        self,
        company_id: int,
        prompt: str,
        template_type: str = 'custom',
        tone: str = 'formal',
        title: Optional[str] = None,
        reference_document_ids: Optional[List[int]] = None,
    ) -> Dict:
        """Return {success, title, content_markdown, references, word_count, tokens_used, error}."""
        try:
            prepared = self._prepare_prompt(
                company_id, prompt, template_type, tone, title, reference_document_ids,
            )
            if not prepared.get('ok'):
                return {'success': False, 'error': prepared.get('error', 'Invalid input')}

            llm = self._call_llm_for_reasoning(
                prompt=prepared['user_prompt'],
                system_prompt=BASE_SYSTEM,
                temperature=0.4,
                max_tokens=self.MAX_TOKENS,
            )

            content = ''
            if isinstance(llm, dict):
                content = (llm.get('content') or llm.get('text') or '').strip()
            elif isinstance(llm, str):
                content = llm.strip()

            if not content:
                return {'success': False, 'error': 'The AI returned an empty response. Please try again.'}

            if not content.lstrip().startswith('#'):
                content = f"# {prepared['resolved_title']}\n\n{content}"

            return {
                'success': True,
                'title': prepared['resolved_title'],
                'content_markdown': content,
                'references': prepared['refs'],
                'word_count': len(content.split()),
                'tokens_used': self._extract_token_usage(),
            }

        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'DocumentAuthoringAgent.generate error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    def generate_stream(
        self,
        company_id: int,
        prompt: str,
        template_type: str = 'custom',
        tone: str = 'formal',
        title: Optional[str] = None,
        reference_document_ids: Optional[List[int]] = None,
    ):
        """Generator that yields (event_type, payload) tuples:

            ('meta',  {'title': ...})              — emitted immediately with resolved title
            ('text',  delta_str)                   — emitted for each token chunk from the model
            ('done',  {'content_markdown': ...,    — emitted once at the end with the full doc
                       'word_count': ...,
                       'tokens_used': ...,
                       'references': ...})
            ('error', {'message': ...})            — on any failure, terminates the stream
        """
        try:
            prepared = self._prepare_prompt(
                company_id, prompt, template_type, tone, title, reference_document_ids,
            )
            if not prepared.get('ok'):
                yield ('error', {'message': prepared.get('error', 'Invalid input')})
                return

            if not getattr(self, 'groq_client', None):
                yield ('error', {'message': 'AI service is not configured. Please set GROQ_API_KEY.'})
                return

            yield ('meta', {
                'title': prepared['resolved_title'],
                'references': prepared['refs'],
            })

            messages = [
                {'role': 'system', 'content': BASE_SYSTEM},
                {'role': 'user', 'content': prepared['user_prompt']},
            ]

            # Groq chat streaming. Newer SDKs accept `stream_options={'include_usage': True}`
            # to get a final usage chunk, but older ones reject the kwarg — so we gracefully
            # fall back to character-based estimation if usage isn't provided.
            create_kwargs = dict(
                model=self.model,
                messages=messages,
                temperature=0.4,
                max_tokens=self.MAX_TOKENS,
                stream=True,
            )
            try:
                stream = self.groq_client.chat.completions.create(
                    **create_kwargs,
                    stream_options={'include_usage': True},
                )
            except TypeError:
                # SDK doesn't support stream_options — retry without it
                stream = self.groq_client.chat.completions.create(**create_kwargs)

            full_text = ''
            usage = None
            for chunk in stream:
                # usage arrives in the terminal chunk when include_usage=True
                chunk_usage = getattr(chunk, 'usage', None)
                if chunk_usage is not None:
                    usage = chunk_usage

                choices = getattr(chunk, 'choices', None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], 'delta', None)
                content_delta = getattr(delta, 'content', None) if delta else None
                if content_delta:
                    full_text += content_delta
                    yield ('text', content_delta)

            # Normalize result
            content = full_text.strip()
            if not content:
                yield ('error', {'message': 'The AI returned an empty response. Please try again.'})
                return

            if not content.lstrip().startswith('#'):
                content = f"# {prepared['resolved_title']}\n\n{content}"

            tokens_used = {}
            if usage:
                tokens_used = {
                    'provider': 'groq',
                    'model': self.model,
                    'prompt_tokens': getattr(usage, 'prompt_tokens', None),
                    'completion_tokens': getattr(usage, 'completion_tokens', None),
                    'total_tokens': getattr(usage, 'total_tokens', None),
                    'estimated': False,
                }
            else:
                # Fall back to character-based estimate
                est_prompt = max(1, int(len(prepared['user_prompt']) / 4))
                est_completion = max(1, int(len(content) / 4))
                tokens_used = {
                    'provider': 'groq',
                    'model': self.model,
                    'prompt_tokens': est_prompt,
                    'completion_tokens': est_completion,
                    'total_tokens': est_prompt + est_completion,
                    'estimated': True,
                }

            yield ('done', {
                'title': prepared['resolved_title'],
                'content_markdown': content,
                'references': prepared['refs'],
                'word_count': len(content.split()),
                'tokens_used': tokens_used,
            })

        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'DocumentAuthoringAgent.generate_stream error: {e}', exc_info=True)
            yield ('error', {'message': str(e)})

    # ──────────────────────────────────────────────
    # Internal helpers shared by generate + generate_stream
    # ──────────────────────────────────────────────
    def _prepare_prompt(
        self,
        company_id: int,
        prompt: str,
        template_type: str,
        tone: str,
        title: Optional[str],
        reference_document_ids: Optional[List[int]],
    ) -> Dict:
        prompt = (prompt or '').strip()
        if not prompt:
            return {'ok': False, 'error': 'Prompt is required.'}

        if not getattr(self, 'groq_client', None):
            return {'ok': False, 'error': 'AI service is not configured. Please set GROQ_API_KEY.'}

        template_info = TEMPLATE_GUIDES.get(template_type) or TEMPLATE_GUIDES['custom']
        tone_guide = TONE_GUIDES.get(tone, TONE_GUIDES['formal'])
        ref_block, refs = self._build_reference_block(company_id, reference_document_ids)

        resolved_title = (title or '').strip() or self._suggest_title(prompt, template_info['name'])

        outline_block = ''
        if template_info.get('outline'):
            outline = '\n'.join(template_info['outline']).replace('{title}', resolved_title)
            outline_block = (
                'SUGGESTED OUTLINE (use as a base; adapt as needed to fit the content):\n'
                f'```\n{outline}\n```\n\n'
            )

        user_prompt = (
            f"TEMPLATE: {template_info['name']}\n"
            f"TONE: {tone.capitalize()} — {tone_guide}\n"
            f"TITLE (use exactly): {resolved_title}\n\n"
            f"USER INSTRUCTIONS:\n{prompt}\n\n"
            f"{outline_block}"
            f"TEMPLATE-SPECIFIC GUIDANCE:\n{template_info['guidance']}\n\n"
            f"{ref_block}"
            f"TASK: Produce the full document in Markdown now. Start with the H1 title. "
            f"Do not add any preamble or explanation outside the document itself."
        )

        return {
            'ok': True,
            'user_prompt': user_prompt,
            'resolved_title': resolved_title,
            'refs': refs,
            'template_info': template_info,
        }

    def _extract_token_usage(self) -> Dict:
        """Read the token usage captured by the base class on the last LLM call."""
        usage = getattr(self, 'last_token_usage', None) or {}
        return {
            'provider': usage.get('provider', 'groq'),
            'model': usage.get('model', self.model),
            'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'total_tokens': usage.get('total_tokens'),
            'estimated': bool(usage.get('estimated')),
        }

    # ──────────────────────────────────────────────
    def _build_reference_block(
        self,
        company_id: int,
        reference_document_ids: Optional[List[int]],
    ):
        if not reference_document_ids:
            return 'REFERENCE MATERIAL: None provided. Base the document on the user instructions only.\n\n', []

        docs = list(
            OperationsDocument.objects.filter(
                company_id=company_id, id__in=reference_document_ids, is_processed=True,
            )
        )
        if not docs:
            return 'REFERENCE MATERIAL: (requested documents not found or not yet processed)\n\n', []

        parts = ['REFERENCE DOCUMENTS (use these facts as the source of truth):\n']
        refs = []
        total = 0
        for d in docs:
            text_source = (d.summary or d.parsed_text or '').strip()
            if not text_source:
                continue
            if len(text_source) > self.MAX_PER_REF_CHARS:
                text_source = text_source[: self.MAX_PER_REF_CHARS] + '…'
            header = f"### [{d.title or d.original_filename}]\n"
            block = header + text_source + '\n'
            if total + len(block) > self.MAX_REF_CHARS:
                break
            parts.append(block)
            total += len(block)
            refs.append({
                'id': d.id,
                'title': d.title or d.original_filename,
                'file_type': d.file_type,
            })
        parts.append('\n')
        return '\n'.join(parts), refs

    def _suggest_title(self, prompt: str, template_name: str) -> str:
        words = prompt.split()[:8]
        base = ' '.join(words).strip(' .,:;')
        if not base:
            return template_name
        return base[0].upper() + base[1:]
