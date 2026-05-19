"""
Document Authoring Agent
Creates structured marketing documents such as strategies, proposals, reports, presentations, and campaign briefs.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional
from marketing_agent.models import Campaign, MarketingDocument, CampaignPerformance, Lead, EmailSendHistory, Reply
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DocumentAuthoringAgent(MarketingBaseAgent):
    """
    Document Authoring Agent
    
    This agent:
    - Creates structured marketing documents
    - Generates strategies, proposals, reports, presentations, and campaign briefs
    - Uses AI to write professional marketing content
    - Saves documents to the database
    
    In simple words:
    "AI that writes marketing documents instead of humans doing it manually."
    """
    
    def __init__(self):
        super().__init__()
        self.agent_name = "DocumentAuthoringAgent"
        self.system_prompt = """You are a Document Authoring Agent for a marketing system.
        Create professional marketing documents (Strategies, Proposals, Reports, Briefs, Presentations).
        Use provided campaign data for accurate, relevant content with clear sections and actionable insights.

        KEY RULES:
        1. NEVER repeat content—each data point, table, section appears ONCE only.
        2. Documents end at their designated final section. STOP writing after it.
        3. Conclusion: summarize in NEW words—never copy earlier tables/lists.
        
        Focus on writing concise, unique, high-value content. Quality over quantity. No filler."""
    
    def process(self, action: str, user_id: int, document_type: str, document_data: Optional[Dict] = None, campaign_id: Optional[int] = None, document_id: Optional[int] = None, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point for document actions
        
        Args:
            action (str): Action to perform ('create', 'generate', 'update')
            user_id (int): User ID creating the document
            document_type (str): Type of document ('strategy', 'proposal', 'report', 'brief', 'presentation')
            document_data (Dict): Document data (title, requirements, key_points, etc.)
            campaign_id (int): Optional campaign ID to associate with document
            document_id (int): Optional document ID for updates
            context (Dict): Optional additional context
            
        Returns:
            Dict: Processing results
        """
        self.log_action(f"Processing {action} action", {
            "document_type": document_type,
            "campaign_id": campaign_id
        })
        
        try:
            if action == 'create' or action == 'generate':
                return self._create_or_generate_document(
                    action=action,
                    user_id=user_id,
                    document_type=document_type,
                    document_data=document_data or {},
                    campaign_id=campaign_id,
                    context=context or {}
                )
            elif action == 'update':
                if not document_id:
                    return {'success': False, 'error': 'document_id is required for update action'}
                return self._update_document(
                    document_id=document_id,
                    user_id=user_id,
                    document_data=document_data or {},
                    context=context or {}
                )
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        except Exception as e:
            from core.api_key_service import QuotaExhausted, NoKeyAvailable
            if isinstance(e, (QuotaExhausted, NoKeyAvailable)):
                raise
            logger.error(f"Error in DocumentAuthoringAgent.process: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _create_or_generate_document(self, action: str, user_id: int, document_type: str, document_data: Dict, campaign_id: Optional[int], context: Dict) -> Dict:
        """Create or generate a document"""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return {'success': False, 'error': 'User not found'}
        
        # Require campaign for Performance Report and Campaign Brief
        if document_type in ['report', 'brief']:
            if not campaign_id:
                return {
                    'success': False, 
                    'error': f'A campaign must be selected to create a {document_type.title()} document. Please select a campaign first.'
                }
        
        # Get campaign if provided
        campaign = None
        if campaign_id:
            try:
                campaign = Campaign.objects.get(id=campaign_id, owner=user)
            except Campaign.DoesNotExist:
                return {'success': False, 'error': 'Campaign not found'}
        
        # Generate document content
        content = self._generate_document_content(document_type, document_data, campaign, context)
        
        # If action is 'generate', just return preview
        if action == 'generate':
            return {
                'success': True,
                'title': document_data.get('title', f'{document_type.title()} Document'),
                'document_type': document_type,
                'content': content,
                'message': 'Document generated successfully (preview only, not saved)'
            }
        
        # If action is 'create', save to database
        title = document_data.get('title', f'{document_type.title()} Document')
        
        document = MarketingDocument.objects.create(
            document_type=document_type,
            title=title,
            content=content,
            campaign=campaign,
            created_by=user,
            status='completed'
        )
        
        return {
            'success': True,
            'document_id': document.id,
            'title': document.title,
            'document_type': document.document_type,
            'content': content,
            'message': f'Document "{document.title}" created successfully'
        }
    
    def _generate_document_content(self, document_type: str, document_data: Dict, campaign: Optional[Campaign], context: Dict) -> str:
        """Generate document content using AI"""
        prompt = self._build_document_prompt(document_type, document_data, campaign, context)

        def generate_once(gen_prompt: str, temperature: float = 0.35) -> str:
            raw = self._call_llm_for_writing(
                prompt=gen_prompt,
                system_prompt=self.system_prompt,
                temperature=temperature,
                max_tokens=16384
            )
            return self._post_process_document_content(raw, document_type, campaign)

        content = generate_once(prompt, temperature=0.35)

        # Guardrail: report/brief output can occasionally be malformed due to model variability.
        # If structure is invalid, regenerate once with stricter corrective instructions.
        if document_type in ('report', 'brief') and not self._is_document_structure_valid(content, document_type):
            correction = (
                "\n\nRETRY INSTRUCTION (MANDATORY): Re-write the entire document from scratch with strict section order and clean markdown headings only. "
                "Do NOT include duplicate sections, do NOT place any content after the final section, and do NOT repeat metrics/tables."
            )
            content = generate_once(prompt + correction, temperature=0.2)

        return content

    def _post_process_document_content(self, content: str, document_type: str, campaign: Optional[Campaign]) -> str:
        """Run all post-processing steps in a single place for consistency across retries."""
        if not content:
            return content

        # Remove duplicate paragraphs and content blocks
        content = self._remove_duplicate_paragraphs(content)

        # Ensure Phase 2 is never missing in timeline sections (strategy and brief)
        if document_type == 'strategy':
            content = self._fix_timeline_phase2(content, document_type='strategy', campaign=None)
            content = self._strip_strategy_duplicate_sections(content)
        elif document_type == 'brief':
            content = self._fix_timeline_phase2(content, document_type='brief', campaign=campaign)

        # Remove duplicate sections that the model often adds after ending sections
        if document_type in ('brief', 'report'):
            content = self._strip_duplicate_sections_after_end(content, document_type)
            content = self._fix_chart_values_numeric(content)

        # Clean markdown headings (no **## or **Strategy Document**)
        return self._clean_markdown_headings(content)

    def _is_document_structure_valid(self, content: str, document_type: str) -> bool:
        """Validate required section order and ending for key document types."""
        if not content or document_type not in ('report', 'brief'):
            return True

        normalized = content.lower()
        required_sections = {
            'report': [
                'campaign overview',
                'performance metrics',
                'lead details',
                'key achievements',
                'challenges and issues',
                'analysis and insights',
                'recommendations',
                'conclusion',
                'future outlook',
            ],
            'brief': [
                'campaign overview',
                'objectives and goals',
                'target audience',
                'key messaging',
                'campaign timeline',
                'success criteria',
                'email campaign performance',
                'lead engagement data',
                'issues / challenges',
                'improvements / recommendations',
                'conclusion',
            ],
        }

        positions = []
        for section in required_sections[document_type]:
            pos = normalized.find(section)
            if pos == -1:
                return False
            positions.append(pos)

        # Required sections must appear in sequence
        if positions != sorted(positions):
            return False

        # Enforce terminal section rule: no new section headings after the final section.
        final_section = 'future outlook' if document_type == 'report' else 'conclusion'
        final_pos = normalized.rfind(final_section)
        if final_pos == -1:
            return False

        tail = normalized[final_pos:]
        heading_count = len(re.findall(r'\n\s*(##\s+|\*\*[^*]+\*\*\s*$)', tail, flags=re.IGNORECASE | re.MULTILINE))
        return heading_count <= 2
    
    def _remove_duplicate_paragraphs(self, content: str) -> str:
        """Remove duplicate paragraphs, bullet points, and content blocks that appear multiple times."""
        if not content or not content.strip():
            return content
        
        lines = content.split('\n')
        seen_content = set()
        output_lines = []
        current_block = []
        
        def normalize_text(text):
            """Normalize text for comparison (lowercase, remove extra spaces, strip punctuation)."""
            return re.sub(r'[^\w\s]', '', text.lower()).strip()
        
        def is_significant(text):
            """Check if text block is significant enough to check for duplicates (> 20 chars)."""
            return len(text.strip()) > 20
        
        for line in lines:
            stripped = line.strip()
            
            # Headers and empty lines always go through
            if stripped.startswith('##') or stripped.startswith('[CHART') or not stripped:
                # Process accumulated block
                if current_block:
                    block_text = ' '.join(current_block)
                    if is_significant(block_text):
                        normalized = normalize_text(block_text)
                        if normalized not in seen_content:
                            output_lines.extend(current_block)
                            seen_content.add(normalized)
                    else:
                        output_lines.extend(current_block)
                    current_block = []
                output_lines.append(line)
                continue
            
            # Accumulate content lines into blocks (paragraphs/bullets)
            current_block.append(line)
            
            # If line ends a paragraph (not a bullet start and previous was content), process block
            if not stripped.startswith(('*', '-', '•', '|')) and current_block:
                block_text = ' '.join(current_block)
                if is_significant(block_text):
                    normalized = normalize_text(block_text)
                    if normalized not in seen_content:
                        output_lines.extend(current_block)
                        seen_content.add(normalized)
                    # If duplicate, skip it
                else:
                    output_lines.extend(current_block)
                current_block = []
        
        # Process any remaining block
        if current_block:
            block_text = ' '.join(current_block)
            if is_significant(block_text):
                normalized = normalize_text(block_text)
                if normalized not in seen_content:
                    output_lines.extend(current_block)
            else:
                output_lines.extend(current_block)
        
        return '\n'.join(output_lines)
    
    def _clean_markdown_headings(self, content: str) -> str:
        """Remove bold around section headings and strip leading document-type title lines like **Strategy Document**."""
        if not content or not content.strip():
            return content
        lines = content.split('\n')
        out = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip leading document-type title only (e.g. "**Strategy Document**"), not "**## Section**"
            if i < 3 and stripped and not stripped.startswith('##') and not stripped.startswith('['):
                if re.match(r'^\*\*(?!##)[^*]+\*\*\s*$', stripped) and len(stripped) < 80:
                    continue
            # Fix "**## Section Name**" or "## **Section Name**" -> "## Section Name"
            if '**##' in line or stripped.startswith('## **'):
                line = re.sub(r'^\s*\*\*+', '', line)
                line = re.sub(r'\*\*+\s*$', '', line)
                line = re.sub(r'^(\s*)##\s+\*\*+', r'\1## ', line)
                line = re.sub(r'\*\*+(\s*)$', r'\1', line)
            out.append(line)
        return '\n'.join(out).strip()

    def _fix_chart_values_numeric(self, content: str) -> str:
        """Strip % from values: lines inside [CHART]...[/CHART] so values are numbers only."""
        if not content or '[CHART]' not in content:
            return content

        def fix_block(block):
            return re.sub(
                r'(values:\s*[^\n]+)',
                lambda m: re.sub(r'%', '', m.group(1)),
                block,
                flags=re.IGNORECASE
            )

        return re.sub(
            r'(\[\s*CHART\s*\].*?\[\s*/\s*CHART\s*\])',
            lambda m: fix_block(m.group(0)),
            content,
            flags=re.IGNORECASE | re.DOTALL
        )

    def _strip_duplicate_sections_after_end(self, content: str, document_type: str) -> str:
        """Remove duplicate tables/sections that appear after Conclusion (brief) or Future Outlook (report)."""
        if not content or document_type not in ('brief', 'report'):
            return content
        # Reports/briefs often use **Section** instead of ## Section; find end of "real" content
        if document_type == 'brief':
            end_marker_re = re.compile(r'\n(##\s+Conclusion|\*\*Conclusion\*\*)\b', re.IGNORECASE)
            dup_patterns = [
                r'\n\s*\*\*Lead Details Table\*\*',
                r'\n\s*\*\*Lead Details\*\*\s*(\n|$)',
                r'\n\s*\*\*Email Campaign Performance Metrics Table\*\*',
                r'\n\s*\*\*Email Campaign Performance Metrics\*\*\s*(\n|$)',
                # Table-style duplicates (model often repeats as markdown table after Conclusion)
                r'\n\s*\|\s*\*\*Email Campaign Performance Metrics\*\*',
                r'\n\s*\|\s*\*\*Lead Engagement Metrics\*\*',
                r'\n\s*\|\s*\*\*Objectives\*\*',
                r'\n\s*\*\*Timeline\*\*\s*(\n|$)',
                r'\n\s*\*\*Target Audience Table\*\*',
                r'\n\s*\*\*Target Audience\*\*\s*(\n|$)',
                r'\n\s*\*\*Target Leads and Conversions Table\*\*',
                r'\n\s*\*\*Target Leads and Conversions\*\*\s*(\n|$)',
                r'\n\s*###\s*Lead Details Table',
                r'\n\s*###\s*Email Campaign Performance Metrics Table',
                r'\n\s*###\s*Target Audience Table',
                r'\n\s*###\s*Target Leads and Conversions Table',
                # Duplicate full-section blocks (same as report: catch when brief is output twice)
                r'\n\s*\*\*Campaign Overview\*\*',
                r'\n\s*\*\*Objectives and Goals\*\*',
                r'\n\s*\*\*Target Audience\*\*',
                r'\n\s*\*\*Key Messaging\*\*',
                r'\n\s*\*\*Campaign Timeline\*\*',
                r'\n\s*\*\*Timeline\*\*\s*(\n|$)',
                r'\n\s*\*\*Success Criteria\*\*',
                r'\n\s*\*\*Email Campaign Performance\*\*',
                r'\n\s*\*\*Lead Engagement Data\*\*',
                r'\n\s*\*\*Issues\s*/\s*Challenges\*\*',
                r'\n\s*\*\*Improvements\s*/\s*Recommendations\*\*',
                r'\n\s*\*\*Recommendations\*\*\s*(\n|$)',  # duplicate often uses just "Recommendations"
            ]
        else:
            # Report: end after **Future Outlook** or ## Future Outlook (then allow [CHART])
            end_marker_re = re.compile(r'(\n\*\*Future Outlook\*\*|\n##\s+Future Outlook\b)', re.IGNORECASE)
            dup_patterns = [
                r'\n\s*\*\*Lead Details Table\*\*',
                r'\n\s*\*\*Performance Metrics Table\*\*',
                r'\n\s*###\s*Lead Details Table',
                r'\n\s*###\s*Performance Metrics Table',
                r'\n\s*\*\*Performance Metrics and KPIs\*\*',
                r'\n\s*\*\*Lead Details\*\*',
                r'\n\s*\*\*Key Achievements\*\*',
                r'\n\s*\*\*Challenges and Issues\*\*',
                r'\n\s*\*\*Analysis and Insights\*\*',
                r'\n\s*\*\*Recommendations\*\*',
                r'\n\s*\*\*Conclusion\*\*',
                r'\n\s*\*\*Call to Action\*\*',
            ]
        m_end = end_marker_re.search(content)
        if not m_end:
            if document_type == 'brief':
                return content
            # Try alternate: find **Conclusion** for report (wrong but sometimes present)
            m_end = re.search(r'\n\*\*Conclusion\*\*', content, re.IGNORECASE)
            if not m_end:
                return content
        search_start = m_end.start()
        after = content[search_start:]
        first_dup = -1
        for pattern in dup_patterns:
            match = re.search(pattern, after, re.IGNORECASE)
            if match and (first_dup == -1 or match.start() < first_dup):
                first_dup = match.start()
        # Fallback for brief: strip any repeat section or table header after Conclusion (match at line start)
        if document_type == 'brief' and first_dup == -1:
            for needle in (
                '\n**Lead Details Table**',
                '\n**Lead Details**',
                '\n**Email Campaign Performance Metrics Table**',
                '\n**Email Campaign Performance Metrics**',
                '\n| **Email Campaign Performance Metrics**',
                '\n| **Lead Engagement Metrics**',
                '\n| **Objectives**',
                '\n**Timeline**',
                '\n**Target Audience Table**',
                '\n**Target Audience**',
                '\n**Target Leads and Conversions Table**',
                '\n**Target Leads and Conversions**',
                '\n**Success Criteria**',
                '\n**Key Messaging**',
                '\n**Campaign Timeline**',
                '\n**Recommendations**',
            ):
                i = after.find(needle)
                if i != -1 and (first_dup == -1 or i < first_dup):
                    first_dup = i
        if first_dup != -1:
            content = content[: search_start + first_dup].rstrip()
        # Fallback for brief: strip any "Lead Details" or "The following leads" block after Conclusion
        if document_type == 'brief' and content:
            concl_re = re.compile(r'\n(##\s+Conclusion|\*\*Conclusion\*\*)\b', re.IGNORECASE)
            m = concl_re.search(content)
            if m:
                after_concl = content[m.start():]
                # Match "**Lead Details**" or "## Lead Details" or common phrase "The following leads have been"
                lead_detail_re = re.compile(
                    r'\n\s*(##\s*Lead\s+Details|\*\*Lead\s+Details\*\*|The\s+following\s+leads\s+have\s+been)',
                    re.IGNORECASE
                )
                lead_match = lead_detail_re.search(after_concl)
                if lead_match:
                    # Cut from this point in the full content
                    cut_at = m.start() + lead_match.start()
                    content = content[:cut_at].rstrip()
        return content

    def _strip_strategy_duplicate_sections(self, content: str) -> str:
        """Remove duplicate sections that appear after Conclusion and Next Steps in Marketing Strategy.
        The model sometimes adds Lead Details, Email Performance Metrics, Lead Engagement, or duplicate
        Timeline/Success Metrics after Conclusion—strip everything after the Conclusion section."""
        if not content:
            return content
        # Find Conclusion and Next Steps (either ## or **bold**)
        conclusion_m = re.search(
            r'\n(##\s+Conclusion\s+and\s+Next\s+Steps\b|\*\*Conclusion\s+and\s+Next\s+Steps\*\*)',
            content,
            re.IGNORECASE
        )
        if not conclusion_m:
            return content
        # Everything after the conclusion section is suspect; find first duplicate section header
        after_start = conclusion_m.start()
        after_content = content[after_start:]
        dup_patterns = [
            r'\n\*\*Lead\s+Details\*\*',
            r'\n\*\*Email\s+Performance\s+Metrics\*\*',
            r'\n\*\*Lead\s+Engagement\*\*',
            r'\n\*\*Timeline\s+and\s+Milestones\*\*',
            r'\n##\s+Timeline\s+and\s+Milestones\b',
            r'\n##\s+Success\s+Metrics\b',
            r'\n##\s+[^\n*]+',  # any ## section after conclusion
        ]
        first_dup = -1
        for pattern in dup_patterns:
            m = re.search(pattern, after_content[1:], re.IGNORECASE)  # skip first char
            if m and (first_dup == -1 or m.start() < first_dup):
                first_dup = m.start()
        if first_dup != -1:
            content = content[: after_start + 1 + first_dup].rstrip()
        return content

    def _fix_timeline_phase2(self, content: str, document_type: str = 'strategy', campaign: Optional[Campaign] = None) -> str:
        """If content has Phase 1 and Phase 3 but no Phase 2, insert Phase 2 before Phase 3."""
        if not content or 'Phase 2' in content:
            return content
        # Case-insensitive check for Phase 1 and Phase 3
        content_lower = content.lower()
        if 'phase 1' not in content_lower or 'phase 3' not in content_lower:
            return content
        if document_type == 'strategy':
            phase2_line = '• Phase 2: Month 3-4: Launch and execute marketing campaigns, including email via Pay Per Project, social media, and content distribution; monitor early metrics and engagement.'
        else:
            # brief: use campaign dates if available to compute Phase 2 date range
            phase2_line = self._get_brief_phase2_line(campaign, content)
        # Try multiple patterns (bullet format, then fallback without bullet)
        patterns = [
            (r'(\n\s*[•\-*]\s*)(Phase 3:.*?)(\n|$)', r'\n' + phase2_line + r'\n\1\2\3'),
            (r'(\n\s*)(Phase 3:.*?)(\n|$)', r'\n' + phase2_line + r'\n\1\2\3'),
        ]
        for pattern, replacement in patterns:
            content, n = re.subn(pattern, replacement, content, count=1, flags=re.IGNORECASE)
            if n > 0:
                break
        return content

    def _get_brief_phase2_line(self, campaign: Optional[Campaign], content: str) -> str:
        """Build Phase 2 line for Campaign Brief, using campaign dates when available."""
        phase2_desc = 'Execute email sequences, monitor engagement, and nurture leads.'
        if campaign and getattr(campaign, 'start_date', None) and getattr(campaign, 'end_date', None):
            try:
                start = campaign.start_date
                end = campaign.end_date
                # Normalize to date (Django DateField returns date; handle datetime or string)
                if isinstance(start, datetime):
                    start = start.date()
                if isinstance(end, datetime):
                    end = end.date()
                if isinstance(start, str):
                    start = datetime.strptime(start[:10], '%Y-%m-%d').date()
                if isinstance(end, str):
                    end = datetime.strptime(end[:10], '%Y-%m-%d').date()
                total_days = (end - start).days
                if total_days >= 4:
                    # Split into 3 equal phases: Phase 2 = middle third
                    segment = total_days // 3
                    p2_start = start + timedelta(days=segment)
                    p2_end = start + timedelta(days=2 * segment)
                    if p2_end > end:
                        p2_end = end
                    start_str = p2_start.strftime('%B %d, %Y')
                    end_str = p2_end.strftime('%B %d, %Y')
                    return f'• Phase 2: {start_str} to {end_str}: {phase2_desc}'
            except (ValueError, TypeError):
                pass
        return f'• Phase 2: Mid-campaign: {phase2_desc} (within the campaign start–end date range above).'
    
    def _build_document_prompt(self, document_type: str, document_data: Dict, campaign: Optional[Campaign], context: Dict) -> str:
        """Build the prompt for document generation"""
        title = document_data.get('title', f'{document_type.title()} Document')
        # Frontend sends 'notes'; also support 'requirements' and 'key_points'
        requirements = document_data.get('requirements') or document_data.get('notes', '')
        key_points = document_data.get('key_points') or document_data.get('notes', '')
        # Tables and charts - user-controlled (pages removed - AI decides natural length)
        target_tables = max(0, int(document_data.get('tables', 3)))
        target_charts = max(0, int(document_data.get('charts', 1))) if document_type == 'report' else 0
        chart_type = (document_data.get('chart_type') or 'bar').lower()
        if chart_type not in ('bar', 'pie', 'line'):
            chart_type = 'bar'
        table_types_str = (document_data.get('table_types') or 'metrics, timeline, lead details').strip()
        
        # Get campaign data if available
        campaign_data = {}
        if campaign:
            campaign_data = self._get_campaign_data_for_document(campaign, document_type)
        
        # Build document type specific instructions (pass target_tables for report conditional)
        doc_instructions = self._get_document_type_instructions(document_type, target_tables)
        
        user_notes = (requirements or '').strip() or (key_points or '').strip()

        # --- Document end markers (stated once, referenced everywhere) ---
        end_markers = {
            'strategy': '## Conclusion and Next Steps',
            'proposal': '## Next Steps',
            'report': '## Future Outlook',
            'brief': '## Conclusion',
            'presentation': 'Conclusion/Next Steps slide',
        }
        final_section = end_markers.get(document_type, '## Conclusion')

        prompt = f"""Create a professional {document_type} document.

DOCUMENT TITLE: {title}

REQUIREMENTS: {requirements if requirements else 'Create a comprehensive, professional document.'}
KEY POINTS: {key_points if key_points else 'None provided'}

CORE RULES:
1. Document ENDS at {final_section}. No content after that.
2. NO duplication: each piece of data appears ONCE in ONE format. No repeated sections, tables, or metrics.
3. Use REAL data only—no placeholders like [insert date]. Write "Not specified" for missing data.
4. Use ## for section headings (no ### or ####). No bold around headings (write "## Section" not "**## Section**").
5. Write detailed, in-depth analysis with specific numbers and metrics. Every sentence adds value.
6. Conclusion: summarize in NEW words (2-3 paragraphs)—never copy-paste earlier tables/lists.
7. Phases must be sequential (Phase 1, Phase 2, Phase 3—never skip Phase 2).

TABLES: {"ZERO tables. Use bullet lists and paragraphs only—no | column | format." if target_tables == 0 else f"Include exactly {target_tables} markdown table(s) ({table_types_str}) in | col | col | format."}
{f'''CHARTS (MANDATORY): Include exactly {target_charts} chart(s). Format:
[CHART]
type: {chart_type if chart_type in ("bar", "pie") else "bar"}
title: [descriptive title]
labels: [comma-separated labels from campaign data]
values: [comma-separated NUMBERS ONLY—no % signs, e.g. 50 not 50%]
[/CHART]
Use REAL campaign data only. Place inside Performance Metrics section.''' if target_charts > 0 and document_type == 'report' else ''}

"""
        if user_notes:
            if document_type in ('brief', 'report'):
                prompt += f'USER REQUEST: "{user_notes}"\nAddress this while using campaign data and full structure.\n\n'
            else:
                prompt += f"""USER PROMPT: "{user_notes}"
Incorporate in the document: use as theme/focus, place specific details in relevant sections (budget→Resource Breakdown, timeline→Timeline, audience→Target Audience, channels→Tactics). Keep full professional structure.

"""

        # Add campaign data if available
        if campaign_data:
            has_email_data = campaign_data.get('emails_sent') is not None or campaign_data.get('emails_sent') == 0
            has_lead_data = (campaign_data.get('leads_count') or 0) > 0 or (campaign_data.get('leads') or [])
            sparse_hint = ''
            if document_type in ('report', 'brief'):
                if not has_email_data and not campaign_data.get('open_rate') is not None:
                    sparse_hint = 'NOTE: No email activity yet. State "Email campaign not yet launched" in Email Performance section. Do NOT invent metrics.\n'
                elif not has_lead_data:
                    sparse_hint = 'NOTE: No leads yet. State "No leads added yet" in Lead section. Do NOT invent leads.\n'
            strategy_hint = ''
            if document_type == 'strategy':
                strategy_hint = 'STRATEGY: Use campaign data for context/targets only. No Lead Details, Email Metrics, or Lead Engagement sections.\n'
            prompt += f"""CAMPAIGN DATA (REAL - USE ALL):
{self._format_campaign_data(campaign_data)}

Include campaign status in Campaign Overview/Executive Summary.
{sparse_hint}{strategy_hint}"""

            if document_type in ('report', 'brief'):
                prompt += f"""
BRIEF/REPORT RULES:
- Lead table (| Email | Name | Company | Status |) appears ONCE only.
- Email metrics appear ONCE only.
- Include Email Performance section (sent, open/click/reply/bounce rates with analysis).
- Include Lead Engagement section (count, details table, status breakdown).
- {"Use bullet lists for all data—no tables." if target_tables == 0 else f"Include {target_tables} tables with header rows."}
- Use ## only (no ###). Include Key Achievements and Challenges with detailed paragraphs.
{"- Report: include ## Call to Action and ## Future Outlook." if document_type == 'report' else ""}
"""
        else:
            prompt += """NO CAMPAIGN LINKED: Create a full professional document with standard sections.
Use DOCUMENT TITLE and KEY POINTS as theme. Place user details in relevant sections.
"""

        prompt += f"""
{doc_instructions}

FORMATTING:
- Headings: "## Section Name" only. No bold wrapping. No "**Strategy Document**" title line.
- Use **bold** for sub-items within paragraphs only.
{f'- Include {target_charts} [CHART] block(s) with REAL campaign data in Performance Metrics section.' if target_charts > 0 else ''}

Write a detailed, professional, data-driven document. End at {final_section}—nothing after it:"""
        
        return prompt
    
    def _get_campaign_data_for_document(self, campaign: Campaign, document_type: str) -> Dict:
        """Get relevant campaign data for document generation"""
        data = {
            'name': campaign.name,
            'description': campaign.description,
            'status': campaign.get_status_display(),
            'start_date': str(campaign.start_date) if campaign.start_date else None,
            'end_date': str(campaign.end_date) if campaign.end_date else None,
            'target_leads': campaign.target_leads,
            'target_conversions': campaign.target_conversions,
        }
        # Include goals and target_audience so brief/strategy/proposal use real data
        if getattr(campaign, 'goals', None) and campaign.goals:
            data['goals'] = campaign.goals
        if getattr(campaign, 'target_audience', None) and campaign.target_audience:
            data['target_audience'] = campaign.target_audience
        
        # Get performance metrics
        performance = self._get_campaign_performance_data(campaign)
        if performance:
            data['performance'] = performance
        
        # Get leads data (more leads for report so the document includes full lead list)
        leads_count = campaign.leads.count()
        if leads_count > 0:
            data['leads_count'] = leads_count
            max_leads = 50 if document_type == 'report' else 10
            data['leads'] = list(campaign.leads.values('email', 'first_name', 'last_name', 'company', 'status')[:max_leads])
        
        # Get email sending data from database (same logic as dashboard/email status)
        email_sends = EmailSendHistory.objects.filter(campaign=campaign)
        total_sent = email_sends.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count()
        total_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
        total_clicked = email_sends.filter(status='clicked').count()
        total_bounced = email_sends.filter(status='bounced').count()
        total_replied = Reply.objects.filter(campaign=campaign).count()

        if total_sent > 0 or total_replied > 0 or total_bounced > 0:
            data['emails_sent'] = total_sent
            data['emails_opened'] = total_opened
            data['emails_clicked'] = total_clicked
            data['emails_replied'] = total_replied
            data['emails_bounced'] = total_bounced
            if total_sent > 0:
                data['open_rate'] = round((total_opened / total_sent) * 100, 2)
                data['click_rate'] = round((total_clicked / total_sent) * 100, 2)
                data['reply_rate'] = round((total_replied / total_sent) * 100, 2)
                data['bounce_rate'] = round((total_bounced / total_sent) * 100, 2)
        
        # Filter out None values for cleaner output
        return {k: v for k, v in data.items() if v is not None}
    
    def _get_campaign_performance_data(self, campaign: Campaign) -> Optional[Dict]:
        """Get campaign performance metrics from CampaignPerformance model (metric_name/metric_value structure)"""
        try:
            # CampaignPerformance uses metric_name/metric_value structure, not separate columns
            from django.db.models import Q
            
            metrics = CampaignPerformance.objects.filter(campaign=campaign).values('metric_name', 'metric_value', 'actual_value')
            if not metrics.exists():
                return None
            
            # Build dict from metric_name -> metric_value or actual_value
            result = {}
            for m in metrics:
                name = m.get('metric_name')
                value = m.get('metric_value') or m.get('actual_value')
                if name and value is not None:
                    result[name] = float(value) if isinstance(value, (int, float, str)) else value
            
            return result if result else None
        except Exception as e:
            logger.warning(f"Error getting performance data: {e}")
            return None
    
    def _format_campaign_data(self, campaign_data: Dict) -> str:
        """Format campaign data for prompt in a clear, detailed way"""
        def _human_date(d):
            """Convert YYYY-MM-DD to 'February 20, 2026' for document output."""
            if not d:
                return None
            s = str(d)[:10]
            try:
                dt = datetime.strptime(s, '%Y-%m-%d')
                return dt.strftime('%B %d, %Y')
            except (ValueError, TypeError):
                return s

        lines = []
        lines.append("=== CAMPAIGN INFORMATION ===")
        
        # Basic campaign info (use human-readable dates so document says "February 20, 2026" not "2026-02-20")
        if 'name' in campaign_data:
            lines.append(f"Campaign Name: {campaign_data['name']}")
        if 'description' in campaign_data:
            lines.append(f"Description: {campaign_data['description']}")
        if 'status' in campaign_data:
            lines.append(f"Status: {campaign_data['status']}")
        if 'start_date' in campaign_data:
            lines.append(f"Start Date: {_human_date(campaign_data['start_date']) or campaign_data['start_date']} (use this exact format in document)")
        else:
            lines.append("Start Date: Not set (use 'Not specified' in document - NEVER use [insert date])")
        if 'end_date' in campaign_data:
            lines.append(f"End Date: {_human_date(campaign_data['end_date']) or campaign_data['end_date']} (use this exact format in document)")
        else:
            lines.append("End Date: Not set (use 'Not specified' in document - NEVER use [insert date])")
        
        if 'target_audience' in campaign_data and campaign_data['target_audience']:
            lines.append("")
            lines.append("=== TARGET AUDIENCE (USE THIS EXACT DATA) ===")
            aud = campaign_data['target_audience']
            if isinstance(aud, dict):
                for k, v in aud.items():
                    lines.append(f"{k.replace('_', ' ').title()}: {v}")
            else:
                lines.append(str(aud))
        if 'goals' in campaign_data and campaign_data['goals']:
            lines.append("")
            lines.append("=== GOALS / OBJECTIVES (USE THIS EXACT DATA) ===")
            goals = campaign_data['goals']
            if isinstance(goals, dict):
                for k, v in goals.items():
                    lines.append(f"{k.replace('_', ' ').title()}: {v}")
            else:
                lines.append(str(goals))
        
        lines.append("")
        lines.append("=== TARGETS ===")
        if 'target_leads' in campaign_data:
            lines.append(f"Target Leads: {campaign_data['target_leads']}")
        if 'target_conversions' in campaign_data:
            lines.append(f"Target Conversions: {campaign_data['target_conversions']}")
        
        # Performance metrics
        if 'performance' in campaign_data:
            lines.append("")
            lines.append("=== PERFORMANCE METRICS ===")
            perf = campaign_data['performance']
            for key, value in perf.items():
                if isinstance(value, float):
                    lines.append(f"{key.replace('_', ' ').title()}: {value:,.2f}")
                else:
                    lines.append(f"{key.replace('_', ' ').title()}: {value}")
        
        # Email metrics (explicit: use these exact numbers only)
        if 'emails_sent' in campaign_data:
            lines.append("")
            lines.append("=== EMAIL CAMPAIGN METRICS (USE THESE EXACT NUMBERS ONLY - DO NOT CHANGE OR ROUND) ===")
            lines.append(f"Total Emails Sent: {campaign_data['emails_sent']}")
            if 'emails_opened' in campaign_data:
                lines.append(f"Emails Opened: {campaign_data['emails_opened']}")
            if 'emails_clicked' in campaign_data:
                lines.append(f"Emails Clicked: {campaign_data['emails_clicked']}")
            if 'emails_replied' in campaign_data:
                lines.append(f"Emails Replied: {campaign_data['emails_replied']}")
            if 'emails_bounced' in campaign_data:
                lines.append(f"Emails Bounced: {campaign_data['emails_bounced']}")
            if 'open_rate' in campaign_data:
                lines.append(f"Open Rate: {campaign_data['open_rate']}%")
            if 'click_rate' in campaign_data:
                lines.append(f"Click Rate: {campaign_data['click_rate']}%")
            if 'reply_rate' in campaign_data:
                lines.append(f"Reply Rate: {campaign_data['reply_rate']}%")
            if 'bounce_rate' in campaign_data:
                lines.append(f"Bounce Rate: {campaign_data['bounce_rate']}%")
            lines.append("(In the document, copy these numbers exactly. Do not substitute different values.)")
        
        # Lead data
        if 'leads_count' in campaign_data:
            lines.append("")
            lines.append("=== LEAD DATA (MUST INCLUDE IN DOCUMENT - LIST EACH LEAD BELOW IN A 'LEAD DETAILS' SECTION) ===")
            lines.append(f"Total Leads: {campaign_data['leads_count']}")
            if 'leads' in campaign_data and campaign_data['leads']:
                lines.append("List of leads (include EVERY lead below in the report with email, name, company, status):")
                for i, lead in enumerate(campaign_data['leads'], 1):
                    lead_str = f"  {i}. Email: {lead.get('email', 'N/A')}"
                    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                    if name:
                        lead_str += f" | Name: {name}"
                    if lead.get('company'):
                        lead_str += f" | Company: {lead.get('company')}"
                    if lead.get('status'):
                        lead_str += f" | Status: {lead.get('status')}"
                    lines.append(lead_str)
                lines.append("(Performance Report and Campaign Brief: present leads in a markdown table with header row | Email | Name | Company | Status | and one row per lead—do NOT use '1. Email: ... Name: ...' format.)")
        
        # ——— TARGET vs ACTUAL COMPARISON (pre-computed for brief/report) ———
        target_leads = campaign_data.get('target_leads')
        target_conversions = campaign_data.get('target_conversions')
        actual_leads = campaign_data.get('leads_count', 0)
        emails_sent = campaign_data.get('emails_sent', 0)
        status = campaign_data.get('status', '')

        has_any_email_activity = emails_sent > 0
        has_any_leads = actual_leads > 0

        lines.append("")
        lines.append("=== TARGET vs ACTUAL COMPARISON (USE THIS IN BRIEF/REPORT TO COMPARE PERFORMANCE AGAINST GOALS) ===")
        if target_leads is not None:
            pct = round((actual_leads / target_leads) * 100, 1) if target_leads > 0 else 0
            lines.append(f"Target Leads: {target_leads} | Actual Leads: {actual_leads} | Achievement: {pct}%")
        if target_conversions is not None:
            # Conversions = leads with status 'converted' (approximate from lead data)
            converted = 0
            for lead in (campaign_data.get('leads') or []):
                if (lead.get('status') or '').lower() in ('converted', 'won', 'closed', 'customer'):
                    converted += 1
            conv_pct = round((converted / target_conversions) * 100, 1) if target_conversions > 0 else 0
            lines.append(f"Target Conversions: {target_conversions} | Actual Conversions: {converted} | Achievement: {conv_pct}%")
        if not has_any_email_activity:
            lines.append("Email Activity: NONE — no emails have been sent yet. State this clearly in the document.")
        if not has_any_leads:
            lines.append("Lead Activity: NONE — no leads have been added yet. State this clearly in the document.")

        # Overall campaign health hint
        lines.append("")
        lines.append("=== CAMPAIGN HEALTH ASSESSMENT (USE THIS TO DETERMINE ACHIEVEMENTS AND ISSUES) ===")
        health_issues = []
        health_achievements = []

        if status.lower() in ('paused', 'draft', 'cancelled'):
            health_issues.append(f"Campaign is currently {status} — not actively running")
        if not has_any_email_activity:
            health_issues.append("No emails sent — email campaign has not been executed")
        if has_any_email_activity:
            open_rate = campaign_data.get('open_rate', 0)
            click_rate = campaign_data.get('click_rate', 0)
            reply_rate = campaign_data.get('reply_rate', 0)
            bounce_rate = campaign_data.get('bounce_rate', 0)
            if open_rate > 0:
                health_achievements.append(f"Emails opened — open rate {open_rate}%")
            if open_rate == 0 and emails_sent > 0:
                health_issues.append(f"Zero open rate despite {emails_sent} emails sent")
            if click_rate > 0:
                health_achievements.append(f"Click engagement — click rate {click_rate}%")
            if click_rate == 0 and emails_sent > 0:
                health_issues.append("No clicks on emails sent")
            if reply_rate > 0:
                health_achievements.append(f"Replies received — reply rate {reply_rate}%")
            if bounce_rate > 10:
                health_issues.append(f"High bounce rate: {bounce_rate}%")
        if has_any_leads:
            health_achievements.append(f"{actual_leads} leads generated")
            if target_leads and actual_leads < target_leads:
                pct = round((actual_leads / target_leads) * 100, 1)
                health_issues.append(f"Only {pct}% of target leads achieved ({actual_leads}/{target_leads})")
        if not has_any_leads:
            health_issues.append("No leads generated yet")
        if target_conversions and target_conversions > 0:
            converted_count = 0
            for lead in (campaign_data.get('leads') or []):
                if (lead.get('status') or '').lower() in ('converted', 'won', 'closed', 'customer'):
                    converted_count += 1
            if converted_count == 0:
                health_issues.append(f"Zero conversions achieved (target: {target_conversions})")
            elif converted_count > 0:
                health_achievements.append(f"{converted_count} conversions achieved")

        if health_achievements:
            lines.append("REAL ACHIEVEMENTS (only list these if they exist):")
            for a in health_achievements:
                lines.append(f"  + {a}")
        else:
            lines.append("REAL ACHIEVEMENTS: NONE — No significant achievements yet. In the document, state clearly: 'No significant achievements have been recorded for this campaign yet.' Do NOT fabricate achievements.")

        if health_issues:
            lines.append("REAL ISSUES (discuss these specifically in Issues/Challenges):")
            for issue in health_issues:
                lines.append(f"  - {issue}")
        else:
            lines.append("REAL ISSUES: No major issues identified based on the data.")

        lines.append("(In Key Achievements and Issues/Challenges sections, use ONLY the items listed above. Do NOT invent achievements or issues that are not supported by the data.)")

        # Handle nested dicts
        for key, value in campaign_data.items():
            if isinstance(value, dict) and key != 'performance':
                lines.append("")
                lines.append(f"=== {key.upper().replace('_', ' ')} ===")
                for sub_key, sub_value in value.items():
                    lines.append(f"{sub_key.replace('_', ' ').title()}: {sub_value}")

        return "\n".join(lines)
    
    def _get_document_type_instructions(self, document_type: str, target_tables: int = 3) -> str:
        """Get document type specific instructions. target_tables=0 means no tables, use lists only."""
        instructions = {
            'strategy': """
STRUCTURE OVERRIDES LENGTH: This document ENDS at ## Conclusion and Next Steps. Do NOT add any section after that. Expand only within the sections below when more depth is needed. No Performance Metrics and Analysis, Lead Details, or Email Performance sections—those belong in reports only.

Create a LONG, comprehensive Marketing Strategy document—like a consultant's full deliverable (8–12+ pages when rendered). Use ## for main sections only; do NOT use ### or ####. Use **bold** subheads or bullet points followed by full paragraphs. Every section must have substantial content (multiple paragraphs or bullets with explanation).

USER THEME: The DOCUMENT TITLE and ADDITIONAL KEY POINTS define the strategy's focus (e.g. "Overcome Other Tech Companies", "B2B SaaS lead generation", "UK market expansion"). Weave this theme into the ENTIRE document—Executive Summary, Market Analysis, Competitor Analysis, Objectives, Tactics, and Conclusion. Do not write a generic strategy; make it specific to what the user asked for.

Sections (each as ## Section Name)—write LONG, detailed content in each:

## Executive Summary
2–4 full paragraphs. Summarise the strategy's purpose, key objectives, main channels (including use of Pay Per Project for email), target audience, and expected outcomes. State clearly how this strategy addresses the user's theme (e.g. overcoming competitors, entering a market, scaling lead gen).

## Market Analysis
Multiple full paragraphs. **Competitor Analysis**: 2+ paragraphs naming and analysing 2–4 competitors (strengths, weaknesses, market position). **Industry Trends and Opportunities**: 2+ paragraphs on relevant trends (e.g. digital transformation, AI/ML, cloud adoption), growth projections, and concrete opportunities for the organisation. Use illustrative data or industry benchmarks where helpful. Tie trends to the user's theme.

## Target Audience Analysis
2–3 full paragraphs. Demographics (age, role, company size, geography). **Pain Points and Needs**: bullet list with a short paragraph for each. **Buyer Personas**: if useful, 1–2 short persona descriptions. Align audience with the DOCUMENT TITLE and user's focus (e.g. "B2B decision-makers in tech" for "Overcome Other Tech Companies").

## Marketing Objectives and Goals
For each objective use: **Objective Name**: One-line goal. Then a bullet (•) and a full paragraph explaining how you will achieve it and how it supports the overall theme. Include at least: Brand Awareness, Lead Generation, Conversion (or Revenue). Add 1–2 more if relevant (e.g. Customer Retention, Market Penetration). Minimum 3 objectives, each with a full paragraph.

## Marketing Channels and Tactics
Intro paragraph on multi-channel approach. Then **bold** sub-heads with 3–5 bullets each and short paragraphs where needed:
**Email Marketing** • Use the platform's email marketing agent, Pay Per Project, for targeted email campaigns, automation, and measurement. • [2–3 more specific tactics]
**Content Marketing** • [bullets + short paragraph]
**Social Media** • [bullets + short paragraph]
**Other channels** (e.g. SEO, events, partnerships) as relevant. Ensure Pay Per Project is clearly mentioned under Email Marketing.

## Resource Allocation
2+ full paragraphs. **Budget**: state total and breakdown (e.g. by channel or by month). **Technology**: mention Pay Per Project and any other tools. **People/Team**: roles and time allocation. Use a compact markdown table if helpful (e.g. Category | Allocation). If the user provided a budget or cost in their notes, use it here.

## Timeline and Milestones
2+ full paragraphs describing the rollout. Then a phased timeline.

CRITICAL - DO NOT SKIP PHASES: You MUST list phases in strict numerical order with NO gaps. If you have Phase 1 and Phase 3, you MUST also write Phase 2 (Month 3–4). Never output "Phase 1" followed by "Phase 3" without Phase 2 in between. Minimum three phases: Phase 1, Phase 2, Phase 3. Prefer 4–6 phases (e.g. Phase 1: Month 1–2, Phase 2: Month 3–4, Phase 3: Month 5–6, Phase 4: Month 7–8 if needed). Example structure:
• Phase 1: Month 1–2: [deliverables]
• Phase 2: Month 3–4: [deliverables—e.g. launch campaigns, execute email via Pay Per Project]
• Phase 3: Month 5–6: [deliverables—e.g. analyze results, optimize]
Use at least 4–6 time buckets or 4–6 phases with clear deliverables for each. A compact markdown table is recommended: Phase | Timeframe | Key Deliverables.

## Success Metrics and KPIs
2+ full paragraphs. List specific KPIs (e.g. Email Open Rate, Click Rate, Lead Count, Conversion Rate, Revenue) with target numbers. Use **bold** for each KPI name and a short explanation. If the user gave targets in their notes, use them here.

## Risk Assessment
2+ full paragraphs. Identify 3–5 risks (e.g. competition, technology dependency, resource constraints, market shifts). For each: **Risk**: short description. • Mitigation: one or two sentences. Do not leave as one-line bullets only.

## Conclusion and Next Steps
2–4 full paragraphs. Summarise the strategy, strategic priorities, implementation roadmap, and expected outcomes. List 4–6 concrete next steps (e.g. establish team, finalise budget, launch Phase 1, set up Pay Per Project campaigns). End with a strong closing that ties back to the user's theme (e.g. how this positions the organisation to overcome competitors or achieve the stated goal).

ONE FORMAT ONLY—NO DUPLICATION: Do NOT present the same information in paragraph form and then repeat it in a table or list. Each section and each data type (objectives, timeline, success metrics, audience, resources) appears ONCE only. CRITICAL - NO DUPLICATE SECTIONS: The strategy document has each section ONCE only. Do NOT add "Performance Metrics and Analysis", "Email Campaign Performance", "Lead Engagement", "Lead Details", or "Email Performance Metrics" as sections or tables—those belong in Performance Reports only. Do NOT include a lead list table or email metrics table (even if campaign data is provided): in Success Metrics and KPIs you may cite target numbers only (e.g. 100 leads, 10 conversions, 20% open rate). Do NOT repeat "Timeline and Milestones" or "Success Metrics and KPIs" anywhere. The document MUST END with ## Conclusion and Next Steps—output nothing after that section (no Lead Details, no Email Performance Metrics, no Lead Engagement, no duplicate Timeline, no summary tables that repeat earlier content).

LENGTH AND QUALITY: Aim for a document that would be 8–12+ pages when rendered. Every section must have multiple paragraphs or detailed bullets with explanation. Do not produce a short or generic strategy—match the depth of a professional consultant deliverable.

TIMELINE RULE: In ## Timeline and Milestones you MUST include Phase 2 (and every phase in order). Never write only Phase 1 and Phase 3—always Phase 1, then Phase 2, then Phase 3 (and more if needed). Skipping Phase 2 is forbidden.
""",
            'proposal': """
STRUCTURE OVERRIDES LENGTH: This document ENDS at ## Next Steps. Do NOT add any section or table after that. Expand only within the sections below when more depth is needed. Do NOT add report-style sections (Performance Metrics, Lead Engagement, Appendices).

Create a LONG, comprehensive Campaign Proposal (full paragraphs and tables—like a professional client-ready document). Use ## for main sections only; NEVER use ### or ####. Use **bold** only for sub-sections (e.g. **Email Marketing** under Campaign Strategy)—never # or ## for those.

ONE FORMAT ONLY—NO DUPLICATION: Do NOT present the same information in paragraph form and then repeat it in a table or list. Each piece of information (objectives, audience, timeline, resources, expected results) appears in one place only. Do not write the same content in prose and then add a summary table or repeat section (e.g. do not list objectives in ## Objectives and Goals and then add an "Objectives" table at the end). The document ends after ## Next Steps—no summary tables or repeat sections after that.

CRITICAL - PROPOSAL ONLY (do NOT add report-style sections):
Do NOT include in a Campaign Proposal: "Performance Metrics and Analysis", "Email Campaign Performance", "Lead Engagement Metrics", "Brand Awareness Metrics", "Appendices", or any section that reports or analyzes actual campaign performance. Those belong in a Performance Report. A proposal is a plan to get approval—not a report on results.

Tables: Use at most 3–4 compact tables (e.g. Resource Breakdown, Timeline). Keep tables to 3–4 columns max and short cell text. Do not add many tables.

Structure (proposal sections only):

## Executive Summary
2–3 full paragraphs: outline the strategic plan (brand awareness, lead generation, conversion), mention multi-channel efforts and Pay Per Project for email execution, and state expected outcomes.

## Campaign Overview
2+ full paragraphs: how the campaign will be executed (email, social media, content, SEO), target audience segmentation, and how objectives will be measured (open rates, click-through rates, conversion, ROI).

## Objectives and Goals
For each objective use **bold** for the name only (do NOT use ### or ####). Format: **Objective Name**: One-line goal. Then a bullet (•) and a full paragraph explaining how you will achieve it.
Example: **Conversion**: Convert a minimum of 20% of leads into paying customers. • [Full paragraph on lead nurturing, content, trust, etc.]
Do this for Conversion, Lead Generation, Brand Awareness (or as many as relevant). Use **Conversion**, **Lead Generation**, **Brand Awareness**—not ## or ### subheadings.

## Target Audience
Paragraph on how audience will be identified (market research, buyer personas). Then a markdown table: Segment | Description | Demographics (e.g. Decision-Makers, Influencers, Users with descriptions and age/role).

## Campaign Strategy and Tactics
ONE section only—do NOT split into "Campaign Strategy" and "Tactics and Channels". Use a single ## Campaign Strategy and Tactics with **bold** sub-heads for each channel. Each channel appears ONCE with one set of bullets (approach + tactics together). Do NOT repeat the same channel (e.g. Email Marketing) under two different ## headings.
Intro paragraph: strong online presence, lead nurturing, mention Pay Per Project for email execution. Then **bold** sub-heads with 3–5 bullets each (mix of approach and specific tactics):
**Email Marketing** • Utilize Pay Per Project for email execution. • [2–3 more bullets: list building, sequences, measurement—do not repeat this channel elsewhere]
**Content Marketing** • [3–4 bullets only here—do not repeat under another heading]
**Social Media Advertising** • [3–4 bullets only here—do not repeat under another heading]
NO DUPLICATION: Do NOT add a separate "Tactics and Channels" section. Do NOT use ### or ####—only ## and **bold** for sub-heads.

## Resource Breakdown
One compact table only: Resource / Item | Allocation / Cost (3–4 rows + Total). Short labels and numbers so it fits on one page.

## Timeline
One compact table only: Phase | Dates | Deliverables (4–5 rows). Short cell text so it fits on one page.

## Expected Results
Short bullet list or one short table of TARGETS only (e.g. Open Rate: 20%; Total Leads: 500). Do NOT add performance analysis, "actual" metrics, engagement analysis, or industry-average commentary. Just state what we expect to achieve.

## Conclusion
2–3 full paragraphs: summarize the plan, channels, resource breakdown, timeline; state expected outcomes; recommend approving and implementing the campaign.

## Recommendations
Bullet list (e.g. Approve and implement; Monitor and analyze performance).

## Next Steps
Bullet list (e.g. Schedule meeting with marketing team; Monitor performance; make adjustments).

End the proposal here. Do NOT add Performance Metrics and Analysis, Email Campaign Performance, Lead Engagement Metrics, Appendices, or any report-style sections. Do NOT add a separate "Tactics and Channels" section—channels are covered once under ## Campaign Strategy and Tactics. Always produce a LONG, detailed proposal with full paragraphs in Executive Summary, Campaign Overview, Objectives, Target Audience, Campaign Strategy and Tactics, and Conclusion. Use at most 3–4 compact tables. NEVER use ### or ####—only ## and **bold** for sub-heads.
""",
            'report': """
STRUCTURE OVERRIDES LENGTH: This document ENDS at ## Future Outlook. Do NOT add any section, table, or list after Future Outlook. Expand only within the sections below—more paragraphs, deeper analysis, more context in each heading. Never duplicate content across sections.

DETAIL REQUIRED—EVERY HEADING RICH IN CONTENT: Write a LONG, detailed Performance Report. Every section must have substantial content: multiple full paragraphs or multiple **bold** points each with a full paragraph (4–6 sentences). Do NOT write one-line bullets or single short paragraphs per section. To add depth: explain what the numbers mean, why they matter, how they compare to targets, what drives them, and what the implications are. Each piece of data (metrics, leads, achievements, challenges) appears in exactly ONE section—never repeat the same facts in another heading.

ONE FORMAT ONLY—NO DUPLICATION: Do NOT present the same information in paragraph form and then repeat it in a table or list elsewhere. (1) Lead Details (email, name, company, status) in exactly ONE place—the Lead Details section only; do NOT repeat the lead table in Conclusion, Call to Action, or Future Outlook. (2) Email/performance metrics in exactly ONE place—Performance Metrics and KPIs only; do NOT repeat the same metrics elsewhere. (3) Do NOT add a repeat "Lead Details Table" or "Performance Metrics Table" at the end. (4) Conclusion: 2–3 paragraphs in your own words—do NOT re-list metrics, lead table, achievements, or challenges. Call to Action: concrete next steps only—do NOT repeat Recommendations. Future Outlook: forward-looking only—do NOT re-copy Conclusion or re-show tables. (5) To add length, add NEW unique analysis and context within each section—never duplicate or rephrase the same points.

Sections (each must have multiple paragraphs or multiple bold items with full paragraphs):
- Executive Summary: 3–4 full paragraphs. The FIRST paragraph must cover only: timeline (launch date, end date, current status), objectives (target leads, target conversions, goals from the data), and purpose (what the campaign was for—e.g. summer sales, lead generation). Do NOT mention email metrics (open rate, click rate, reply rate, emails sent) or lead details (lead count, individual emails) in the first paragraph—those belong in Performance Metrics and KPIs and Lead Details. Paragraphs 2–4: then summarise key metrics, main achievements, main challenges, and overall takeaway with real detail.
- Campaign Overview: 3–4 full paragraphs. Paragraph 1: campaign name, status, dates, description, and objectives from the data. Paragraph 2: target audience and goals (target leads, target conversions). Paragraph 3: how the campaign was executed (email, sequences, etc.) and current state. Paragraph 4: short summary of how this report is structured. Do NOT use ### under Campaign Overview.
- Performance Metrics and KPIs: 3+ full paragraphs. Present campaign metrics (Total Emails Sent, Open Rate, Click Rate, Reply Rate, Bounce Rate, Total Leads) as a markdown table ONLY if user requested tables; otherwise use bullet list. Then write multiple paragraphs: what each metric means, how it compares to targets or benchmarks, what is working and what is not, and why. Use REAL data only. If charts are requested, place [CHART] blocks here.
- Lead Details: table only (see below). Then 2–3 paragraphs: who the leads are, status mix, engagement level, and what it means for the campaign. Table: | Email | Name | Company | Status |, separator row, one row per lead. Do NOT use "1. Email: ..." format.
- Key Achievements: Base ONLY on the REAL ACHIEVEMENTS listed in the CAMPAIGN HEALTH ASSESSMENT data. If "REAL ACHIEVEMENTS: NONE", write 1–2 paragraphs clearly stating "No significant achievements have been recorded for this campaign yet" with explanation. Otherwise, 3–5 achievements with **Bold name** plus a FULL paragraph (4–6 sentences) explaining what was achieved, citing exact numbers, comparing against targets (e.g. "3 leads vs 100 target = 3%"), and why it matters. Do NOT fabricate achievements. No one-line bullets.
- Challenges and Issues: ALWAYS include. Base ONLY on the REAL ISSUES from CAMPAIGN HEALTH ASSESSMENT data. For each: **Bold issue name** plus a FULL paragraph (4–6 sentences) with impact analysis and comparison against targets. If the campaign is paused/not running, discuss this explicitly. If no emails sent, discuss this as a critical gap. Do NOT invent issues not supported by data. If genuinely no issues, state "No major issues identified" with brief explanation. No one-line bullets.
- Analysis and Insights: 3–5 full paragraphs. Deep analysis of performance: what the data shows, patterns, causes, implications for next steps. Use REAL data only. If there are opportunities, expand on them here with detail.
- Recommendations: ALWAYS include. 3–5 recommendations. For each: **Bold recommendation name** plus a FULL paragraph (4–6 sentences): what to do, why it helps, how to implement, and expected impact. No one-line bullets.
- Conclusion: 3 full paragraphs. Summarise key takeaways, overall assessment, and priority actions in your own words. Do NOT re-list metrics, lead table, achievements, or challenges.
- Call to Action: 1–2 full paragraphs. Concrete next steps: who, what, when. Do NOT repeat Recommendations verbatim.
- Future Outlook: 2–3 full paragraphs. Expected trends, risks, opportunities, next quarter. Do NOT re-copy Conclusion or re-show any table.

MANDATORY:
1. Executive Summary first paragraph: timeline (dates, status), objectives (target leads, target conversions), and purpose only—do NOT include email metrics or lead details in that paragraph.
2. Campaign metrics (Total Emails Sent, Open Rate, Click Rate, Reply Rate, Bounce Rate, Total Leads) in one place only (Performance Metrics and KPIs). Table format only if user requested tables; else bullet list.
3. Lead Details: every lead in a markdown table | Email | Name | Company | Status |, one row per lead. Then 2–3 paragraphs of context. Do NOT repeat this table elsewhere.
4. Use ## for main sections only; **bold** or bullets + full paragraphs for sub-content. No ###.
5. Charts: add [CHART] blocks when requested; place inside Performance Metrics and KPIs only. Values NUMBERS ONLY; labels/values from CAMPAIGN DATA.
6. Every section must have substantial length: multiple paragraphs or multiple bold items each with a full paragraph. No duplication across sections.
""",
            'brief': """
CAMPAIGN BRIEF - ALLOWED SECTIONS ONLY (in this order). Do NOT add any section that is not in this list. The LAST section is ## Conclusion; after Conclusion you output NOTHING.

DETAIL REQUIRED—EVERY HEADING RICH IN CONTENT: Create a DETAILED Campaign Brief. Every section must have substantial content: multiple full paragraphs (3–5 sentences each) or multiple **bold** points each with a full paragraph. Do NOT write one-line bullets or single short paragraphs per section. Use ONLY the campaign data provided; to add depth, explain context, implications, and what the data means within each section. Each piece of data (campaign info, metrics, leads, achievements, issues) appears in exactly ONE section—never repeat the same facts under another heading.

CRITICAL - LEAD LIST IN ONE PLACE ONLY: The lead list appears ONLY inside ## Lead Engagement Data as a markdown table (| Email | Name | Company | Status |, separator, one row per lead). Do NOT add "Lead Details" elsewhere. Document ENDS at ## Conclusion; output nothing after it.

NO DUPLICATION: (1) Lead list only in ## Lead Engagement Data. (2) Email metrics only in ## Email Campaign Performance. (3) Do NOT repeat Campaign Overview, Objectives, Timeline, or Recommendations after ## Conclusion. (4) To add length, expand WITHIN each section with more paragraphs and analysis—never add new sections or repeat data.

Sections (use ONLY these—in this order; each section must have multiple paragraphs or multiple bold items with full paragraphs):

## Campaign Overview
3–4 full paragraphs. Paragraph 1: **Campaign name**, **status** (Active, Paused, Draft), **start date**, **end date**, and **description** from the data—with a sentence or two on what the campaign is for. Paragraph 2: **Objectives and targets** (target leads, target conversions, goals)—explain what success looks like and how the campaign is set up to achieve it. Paragraph 3: Current state (e.g. paused, active), what has been done so far, and how it is positioned to meet goals. Paragraph 4: Brief summary of audience and key messaging focus. Use exact data from CAMPAIGN INFORMATION and TARGETS/GOALS; do not write "no data available" when the data is in the prompt.

## Objectives and Goals
For each target from the data (Target Leads, Target Conversions, and any goals): **Target name**: value. Then a FULL paragraph (4–5 sentences) explaining what it means, why it matters, and how the campaign will achieve it. CRITICALLY: Use the TARGET vs ACTUAL COMPARISON data to show progress — e.g. "Target Leads: 100 | Current Progress: 3 leads (3% achieved)" or "Target Conversions: 10 | Current Progress: 0 conversions (0% achieved)." Show both the goal AND current progress toward that goal clearly. Do not write one-line bullets—each objective needs real context with actual progress data.

## Target Audience
2–3 paragraphs. Use ONLY the TARGET AUDIENCE data from CAMPAIGN DATA. If the data has demographics, age, location, industry, interests, or company size, describe them in detail across 2–3 paragraphs. If no target audience data, write 1–2 paragraphs stating "Not specified" and why defining audience would help—do NOT invent demographics.

## Key Messaging
2–3 full paragraphs. What will the campaign communicate? Value proposition, key themes, and how messaging supports the objectives. Derive from campaign description and goals; add context and implications. Use the data.

## Campaign Timeline
2–3 paragraphs. Use ONLY the campaign Start Date and End Date. Describe phases within this period (e.g. Phase 1: launch; Phase 2: execution; Phase 3: review) with dates. For short windows (e.g. Feb 20–21), use 1–2 phases within those dates only. Then a short paragraph on what each phase delivers. If dates "Not set", write "Not specified" in 1–2 sentences.

## Success Criteria
2–3 full paragraphs. Use targets from the data exactly ("Target conversions" = the number, e.g. 10, not a percentage). Paragraph 1: How success will be measured (leads, conversions, open/click rates if relevant) with the exact target numbers. Paragraph 2: CURRENT PROGRESS vs targets — use the TARGET vs ACTUAL COMPARISON data to show where the campaign stands (e.g. "Currently, 3 out of 100 target leads have been generated (3%), and 0 out of 10 target conversions have been achieved (0%)"). Paragraph 3: What good looks like, what needs to happen to close the gap, and how the team will track progress going forward.

## Email Campaign Performance
2–3 full paragraphs. Use exact EMAIL CAMPAIGN METRICS from the data: Total Emails Sent, Open Rate, Click Rate, Reply Rate, Bounce Rate—exact numbers. Paragraph 1: Present the metrics clearly (table or bullets) with the exact values. Paragraph 2: COMPARE each metric against campaign targets/goals and industry benchmarks (e.g. "The open rate of X% is above/below the target of Y%" or "compared to the industry average of ~20%"). Paragraph 3: What is working well or not, why, and what it means for campaign success. Use correct tense (e.g. "The campaign has sent X emails"). If no email metrics in the data (no emails sent), write 1–2 paragraphs: "No emails have been sent yet — the email campaign has not been launched" and explain what metrics will be tracked once launched. Do NOT fabricate email metrics when none exist.

## Lead Engagement Data
State total lead count. Present EVERY lead in a markdown table: | Email | Name | Company | Status |, separator, one row per lead. Then 2–3 full paragraphs: how leads are progressing, status mix, engagement level, and what it means for the campaign. Do NOT add a "Lead Details" section later; do NOT repeat the lead list after ## Conclusion.

## Key Achievements
ALWAYS include. Base ONLY on the REAL ACHIEVEMENTS listed in the CAMPAIGN HEALTH ASSESSMENT section of the data. Do NOT fabricate or invent achievements.
- If the CAMPAIGN HEALTH ASSESSMENT shows "REAL ACHIEVEMENTS: NONE", write 1–2 paragraphs clearly stating: "No significant achievements have been recorded for this campaign yet." Explain why (e.g. campaign is paused, no emails sent, no conversions). Then briefly mention what achievements are expected once the campaign becomes active. Do NOT list generic achievements like "campaign was set up" or "objectives were defined" — those are not real achievements.
- If there ARE real achievements listed, write 3–5 **bold** points, each with a FULL paragraph (4–5 sentences). For each achievement, explain what was achieved, cite the exact numbers from the data, compare against targets (e.g. "3 leads generated out of the 100 target, representing 3% progress"), and explain why it matters. No one-line bullets.

## Issues / Challenges
ALWAYS include. Base ONLY on the REAL ISSUES listed in the CAMPAIGN HEALTH ASSESSMENT section of the data. Do NOT fabricate issues that the data does not support.
- Use the specific issues from the CAMPAIGN HEALTH ASSESSMENT (e.g. "Campaign is paused", "No emails sent", "Zero conversions", "Only X% of target leads achieved"). For each issue: **Bold issue name** plus a FULL PARAGRAPH (4–6 sentences) explaining the impact, root cause analysis, and what it means for campaign goals.
- COMPARE actual performance against targets: e.g. "The campaign has generated 3 leads against a target of 100 (3% achievement)" or "Zero conversions have been recorded against a target of 10."
- If the campaign is paused/draft/cancelled, explicitly discuss the impact of the campaign not being active.
- If no emails have been sent, discuss this as a critical issue — the email campaign has not been executed.
- If there are genuinely no issues (all targets met, campaign running well), write 1–2 paragraphs stating: "No major issues have been identified. The campaign is performing within expected parameters." Do NOT invent issues.
- No one-line bullets — each issue needs detailed analysis.

## Improvements / Recommendations
ALWAYS include. 3–5 recommendations that DIRECTLY address the specific REAL ISSUES identified in the Issues/Challenges section. For each: **Bold name** plus a FULL PARAGRAPH (4–6 sentences): what to do, why it helps (referencing specific metrics/issues from the data), how to implement, and expected impact on targets. For example, if the issue is "campaign is paused", recommend reactivating with a specific plan; if "no emails sent", recommend launching the email sequence with specific steps; if "low click rate", recommend content/subject line improvements. Each recommendation must tie back to a real issue or gap in the data — do NOT give generic marketing advice unrelated to this campaign's actual problems. No one-line bullets.

## Conclusion
3 full paragraphs: campaign status, readiness, and what is needed next (launch, optimization, follow-up). Do NOT repeat lead list, metrics table, or other section data. This is the LAST section—after ## Conclusion output NOTHING else.

CRITICAL: (1) Use ONLY numbers and dates from CAMPAIGN DATA. (2) Document ENDS at ## Conclusion. (3) Lead list ONLY in ## Lead Engagement Data. (4) "Target conversions" = the number (e.g. 10), not "10%". (5) Every section must have substantial content—multiple paragraphs or multiple bold items with full paragraphs. (6) NO DUPLICATION: After ## Conclusion output NOTHING. Do NOT add any table or section that repeats Email Campaign Performance Metrics, Lead Engagement Metrics, Timeline, Success Criteria, Objectives, Target Audience, Key Messaging, or Recommendations—each of these appears ONCE earlier in the document; repeating them after Conclusion is forbidden.
""",
            'presentation': """
STRUCTURE OVERRIDES LENGTH: End with the Conclusion/Next Steps slide. Do NOT add extra slides that repeat objectives, metrics, timeline, or recommendations already shown. Each topic appears on one slide only. To add content, expand within the listed slides—never duplicate a topic on another slide.

Create a presentation document with slides covering:
- Title Slide
- Agenda/Overview
- Campaign Overview
- Objectives and Goals
- Target Audience
- Strategy and Tactics
- Performance Metrics (use REAL data if provided)
- Key Insights (based on REAL campaign data)
- Recommendations
- Conclusion/Next Steps (MUST include a final slide with comprehensive summary and clear next steps)

NO DUPLICATION: Each topic or data type (objectives, audience, metrics, timeline, recommendations) appears on one slide only. Do NOT repeat the same information on multiple slides (e.g. do not show objectives in one slide and then again in a summary table on another). Conclusion/Next Steps should summarize and close—not re-list every metric or objective already shown.
""",
        }
        
        return instructions.get(document_type, "Create a well-structured, professional document.")
    
    def _update_document(self, document_id: int, user_id: int, document_data: Dict, context: Dict) -> Dict:
        """Update an existing document"""
        try:
            document = MarketingDocument.objects.get(id=document_id, created_by_id=user_id)
        except MarketingDocument.DoesNotExist:
            return {'success': False, 'error': 'Document not found'}
        
        # Update fields if provided
        if 'title' in document_data:
            document.title = document_data['title']
        if 'content' in document_data:
            document.content = document_data['content']
        
        document.save()
        
        return {
            'success': True,
            'document_id': document.id,
            'message': f'Document "{document.title}" updated successfully'
        }
