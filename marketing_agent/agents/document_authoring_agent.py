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
        Your role is to create professional, structured marketing documents including:
        1. Marketing Strategies
        2. Campaign Proposals
        3. Performance Reports
        4. Campaign Briefs
        5. Presentations
        
        Always create well-structured, professional documents with clear sections, proper formatting, and actionable insights.
        Use the provided campaign data and context to create accurate, relevant documents.
        
        CRITICAL - NO REPETITION: Never repeat the same sentences, bullet points, or paragraphs anywhere in the document. Each section must contain unique content. If you need to reach the required length, add NEW content only: different angles, implications, interpretations, recommendations, or analysis related to the campaign—never duplicate or rephrase the same points to fill space."""
    
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
            'status': document.status,
            'content': content,
            'message': f'Document "{document.title}" created successfully'
        }
    
    def _generate_document_content(self, document_type: str, document_data: Dict, campaign: Optional[Campaign], context: Dict) -> str:
        """Generate document content using AI"""
        prompt = self._build_document_prompt(document_type, document_data, campaign, context)
        
        # Use LLM for writing (OpenAI GPT-4 for better quality)
        # Lower temperature (0.35) for consistent output; higher max_tokens for long documents
        # Performance Report: default and minimum 6 pages (more than 5); other docs default 5
        default_pages = 6 if document_type == 'report' else 5
        min_pages = 6 if document_type == 'report' else 1
        target_pages = min(20, max(min_pages, int((document_data or {}).get('pages', default_pages))))
        min_words = target_pages * 450  # ~450 words per page
        max_tokens_needed = min(16384, (min_words * 2) // 3)  # ~1.35 tokens/word, with headroom
        content = self._call_llm_for_writing(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=0.35,  # Lower = more consistent, especially on retry
            max_tokens=max(max_tokens_needed, 16384)  # Allow long documents so content is not truncated
        )
        
        # Post-process: ensure Phase 2 is never missing in timeline sections (strategy and brief)
        if document_type == 'strategy':
            content = self._fix_timeline_phase2(content, document_type='strategy', campaign=None)
        elif document_type == 'brief':
            content = self._fix_timeline_phase2(content, document_type='brief', campaign=campaign)
        
        # Post-process: remove duplicate sections that the model often adds after Conclusion (brief) or Future Outlook (report)
        if document_type in ('brief', 'report'):
            content = self._strip_duplicate_sections_after_end(content, document_type)
        # Post-process: ensure [CHART] values are numbers only (no % sign) so chart renderer works
        if document_type in ('report', 'brief'):
            content = self._fix_chart_values_numeric(content)
        
        return content
    
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
                r'\n\s*\*\*Success Criteria\*\*',
                r'\n\s*\*\*Email Campaign Performance\*\*',
                r'\n\s*\*\*Lead Engagement Data\*\*',
                r'\n\s*\*\*Issues\s*/\s*Challenges\*\*',
                r'\n\s*\*\*Improvements\s*/\s*Recommendations\*\*',
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
        # Fallback for brief: strip any repeat section header after Conclusion (match at line start)
        if document_type == 'brief' and first_dup == -1:
            for needle in (
                '\n**Lead Details Table**',
                '\n**Lead Details**',
                '\n**Email Campaign Performance Metrics Table**',
                '\n**Email Campaign Performance Metrics**',
                '\n**Target Audience Table**',
                '\n**Target Audience**',
                '\n**Target Leads and Conversions Table**',
                '\n**Target Leads and Conversions**',
            ):
                i = after.find(needle)
                if i != -1 and (first_dup == -1 or i < first_dup):
                    first_dup = i
        if first_dup != -1:
            content = content[: search_start + first_dup].rstrip()
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
        # Pages (1-20), tables, charts - user-controlled. Performance Report: default and minimum 6 pages.
        default_pages = 6 if document_type == 'report' else 5
        min_pages = 6 if document_type == 'report' else 1
        target_pages = min(20, max(min_pages, int(document_data.get('pages', default_pages))))
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
        prompt = f"""Create a professional {document_type} document.

DOCUMENT TITLE (use this): {title}

DOCUMENT REQUIREMENTS:
{requirements if requirements else 'Create a comprehensive, professional document.'}

ADDITIONAL KEY POINTS (what the user wants in this document - YOU MUST ADDRESS THESE):
{key_points if key_points else 'None provided'}

LENGTH AND FORMAT REQUIREMENTS (USER-SPECIFIED - MANDATORY, NO EXCEPTIONS):

**PAGE COUNT (STRICT):** Target = {target_pages} page(s). One rendered page ≈ 450 words. Your output MUST be at least {target_pages * 450} words ({target_pages * 450} words minimum). Write detailed paragraphs—do NOT stop early. If you finish a section and are under the minimum, expand with NEW unique content only: additional analysis, implications, recommendations, or interpretations related to the campaign. NEVER fill space by repeating or rephrasing the same content—every paragraph and bullet must be unique.

**TABLES:** {"User requested ZERO tables. You MUST NOT include any markdown tables (no | column | format). Present ALL metrics, lead data, timelines, and information using bullet lists (•) or numbered lists or paragraphs ONLY. Do NOT use pipe characters (|) to create tables. This overrides any other instruction." if target_tables == 0 else f"Include exactly {target_tables} markdown table(s). Table types: {table_types_str}. Create tables in | col | col | format."}
{f'''- CHARTS (MANDATORY): Include exactly {target_charts} chart(s) using [CHART]...[/CHART] blocks. Chart type: {chart_type}. You MUST insert these chart blocks—do NOT skip them.
  Exact format for each chart block:
  [CHART]
  type: {chart_type if chart_type in ('bar', 'pie') else 'bar'}
  title: [Chart title, e.g. "Campaign Email Metrics"]
  labels: [comma-separated labels FROM CAMPAIGN DATA ONLY, e.g. Open Rate, Click Rate, Reply Rate, Bounce Rate]
  values: [comma-separated NUMBERS ONLY from campaign data—e.g. 50, 16.67, 50, 0. NO % sign or text; use raw numbers so 50% becomes 50]
  [/CHART]
  CRITICAL—CHARTS: (1) Use REAL data only from CAMPAIGN DATA above. (2) values: must be numbers only (e.g. 50, 16.67, 50, 0)—never "50.0%" or "50%"; use 50 not 50%. (3) No placeholder data (no Jan/Feb/Mar/Apr, no 25,30,28,32). Place chart inside Performance Metrics and KPIs. For "line" use "bar".''' if target_charts > 0 and document_type == 'report' else ''}

"""
        if user_notes:
            # For brief/report: user often asks for specific focus (issues, improvement, engagement) — address that.
            # For strategy/proposal: keep full professional structure; use title/notes as theme only.
            if document_type in ('brief', 'report'):
                prompt += f"""
USER REQUEST (for this brief/report): "{user_notes}"
Address what the user asked for (e.g. issues, improvement, engagement) while still using the campaign data and full structure.

"""
            else:
                prompt += f"""
USER PROMPT (incorporate in strategy/proposal): The user provided: "{user_notes}"

You MUST cater to this in the document:
- Use it as the theme/focus (e.g. "help in marketing", "lead generation") and weave it into the Executive Summary and relevant sections.
- If the user gave specific details, put them in the right sections: budget or cost → Resource Breakdown; timeline or dates → Timeline; target audience, industry, or geography → Target Audience and Campaign Strategy; product/campaign name → Campaign Overview; goals or metrics → Objectives and Goals; channels (e.g. "focus on email") → Tactics and Channels. Do not ignore or genericize what the user asked for.
- Keep the full, professional document structure with all standard sections—do not shorten or replace the structure. Just incorporate the user's details where they fit.

"""
        
        # Add campaign data if available
        if campaign_data:
            # Hint when campaign has no email/lead data so report/brief don't invent or look wrong
            has_email_data = campaign_data.get('emails_sent') is not None or campaign_data.get('emails_sent') == 0
            has_lead_data = (campaign_data.get('leads_count') or 0) > 0 or (campaign_data.get('leads') or [])
            sparse_hint = ''
            if document_type in ('report', 'brief'):
                if not has_email_data and not campaign_data.get('open_rate') is not None:
                    sparse_hint = '\nNOTE: This campaign has NO email sending activity in the database yet (no emails sent, no open/click rates). In the document, state that clearly (e.g. "Email campaign not yet launched" or "No email metrics available yet") in the Email Performance section and focus on campaign setup, targets, timeline, and recommendations for launch. Do NOT invent email metrics or fake numbers.\n'
                elif not has_lead_data:
                    sparse_hint = '\nNOTE: This campaign has NO leads in the database yet. In the document, state that clearly (e.g. "No leads added yet" or "Lead list pending") in the Lead section and focus on campaign objectives, target audience, and how to add leads. Do NOT invent or list fake leads.\n'
            prompt += f"""
═══════════════════════════════════════════════════════════════
CAMPAIGN DATA (REAL DATA FROM DATABASE - USE ALL OF THIS):
═══════════════════════════════════════════════════════════════
{self._format_campaign_data(campaign_data)}
═══════════════════════════════════════════════════════════════
{"ANTI-DUPLICATION RULE (BRIEF/REPORT): Lead list, email metrics table, and objectives/targets table each appear ONCE in their section. Do NOT add any repeat section or table after ## Conclusion (brief) or after ## Future Outlook (report). The document ends there." if document_type in ('brief', 'report') else ''}
{sparse_hint}
CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:
0. NO DUPLICATION OF SECTIONS OR DATA: For Campaign Brief and Performance Report ONLY: (a) Each piece of data must appear in exactly ONE place. Do NOT show Lead Details (email, name, company, status) in more than one section or table—include it ONCE only (e.g. in "Lead Details" or "Lead Engagement"). (b) Do NOT show Email Performance metrics (sent, open rate, click rate, reply rate, bounce rate) twice—include them ONCE (e.g. in "Email Campaign Performance" or "Performance Metrics"). (c) Do NOT add any extra section at the end such as "Lead Details Table", "Performance Metrics Table", "Summary Table", or similar—that would duplicate data already shown. The report must END after Future Outlook (and any chart that belongs in Performance Metrics). (d) Do NOT repeat Success Criteria, Objectives, or Timeline in another section or table. (e) Conclusion, Call to Action, and Future Outlook must each contain NEW content (different from each other and from Recommendations)—do NOT copy the same bullets or phrases into multiple sections. (f) To meet page minimum, add NEW unique content only—never duplicate or rephrase the same section, table, or list.
1. For briefs/reports: address what the user asked for (e.g. issues, improvement, engagement). For strategy/proposal: produce a full, professional document with all sections; if the user gave a title or notes (or specific details like budget, timeline, audience), incorporate those in the relevant sections—budget in Resource Breakdown, timeline in Timeline, audience/industry in Target Audience, etc. Do not ignore or genericize user-provided details.
2. ALL data above is REAL data fetched from the database for this specific campaign
3. You MUST include ALL performance metrics, statistics, and data points provided above
4. Create DETAILED sections with actual numbers, percentages, and specific data points
5. Use the actual values provided above - do NOT use placeholder, generic, or invented data
6. NEVER write [insert date], [insert duration], or any [insert ...] placeholder. If Start Date or End Date are "Not set" in the data, write "Not specified" or "To be determined"
7. If a field is missing from the data above, write "Not specified" or "Not available" - do NOT make up values or placeholders
8. Base ALL analysis, metrics, and recommendations on the REAL campaign data provided. For briefs/reports: "Target conversions" in the data means the number of conversions (e.g. 10), not a percentage—do not write "10% conversion rate" unless the data explicitly says so. If the data shows a lead count (e.g. 3 leads), say "the campaign has 3 leads" or "Total leads: 3"—do not say "has not yet generated any leads" when leads are present in the data.
9. For email campaigns: Create a detailed "Email Performance Metrics" section with:
   - Total emails sent (actual number)
   - Open rate (actual percentage)
   - Click rate (actual percentage)
   - Reply rate (actual percentage)
   - Bounce rate (actual percentage)
   - Analysis of what these metrics mean
10. For leads: Create a detailed "Lead Engagement" section with:
   - Total leads count (actual number)
   - Lead details: list or table of EVERY lead from the LEAD DATA section (email, name, company, status for each lead—do NOT omit any)
   - Lead status breakdown and engagement analysis
11. For Performance Reports: (a) {"Campaign metrics and Lead Details (every lead) as bullet lists—NO tables (user requested 0 tables)." if target_tables == 0 else f"Campaign metrics table and Lead Details table (every lead). Include {target_tables} tables total."} (b) Use ## for main sections only—do NOT use ### (H3). (c) Charts: you MUST add the chart(s) requested in LENGTH AND FORMAT REQUIREMENTS using [CHART]...[/CHART] blocks—do NOT omit them. (d) Key Achievements and Challenges and Issues: each point must have a full paragraph. (e) Always include ## Call to Action and ## Future Outlook. (f) Output MUST be at least {target_pages * 450} words ({target_pages} pages).
12. Make the document VERY DETAILED and SPECIFIC to this campaign using ALL the real data above
13. {"Do NOT use markdown tables. Use bullet lists and paragraphs for all data." if target_tables == 0 else f"Include {target_tables} markdown tables of the types specified."} Charts and detailed breakdowns where appropriate.
14. Write in-depth analysis, not just surface-level information
"""
        else:
            prompt += """
NO CAMPAIGN LINKED: This document is not tied to a specific campaign.
- Create a full, professional document with all standard sections (e.g. Executive Summary, Market Analysis, Target Audience, Objectives, Marketing Channels, Resource Allocation, Timeline, Success Metrics, Risk Assessment, Conclusion).
- Use the DOCUMENT TITLE and ADDITIONAL KEY POINTS as the theme/focus. If the user gave specific details (e.g. budget $10k, launch Q2, B2B SaaS, UK market, "focus on email"), incorporate them in the right sections: budget → Resource Breakdown; timeline → Timeline; audience/industry → Target Audience; channels → Tactics. Do not ignore user-provided details.
- You may use illustrative examples and typical industry metrics where helpful. Do not invent a specific campaign name; keep it general and reusable.
"""
        
        prompt += f"""

{doc_instructions}

FORMATTING: Use **text** for bold (e.g. **Brand Awareness**: description). For Performance Reports: {'You MUST include ' + str(target_charts) + ' chart(s) using [CHART] blocks. Each chart MUST use REAL data from CAMPAIGN DATA only (actual open rate, click rate, reply rate, bounce rate, or counts)—NO placeholder data (no Jan/Feb/Mar/Apr, no 25/30/28/32). Place charts inside Performance Metrics and KPIs.' if target_charts > 0 else 'Do NOT add [CHART] blocks—charts are not used in this report.'} For strategy/proposal/brief you may optionally include charts using [CHART] blocks.

DOCUMENT STRUCTURE REQUIREMENTS:
- Use ## for main sections only. Do NOT use ### or #### in any document (strategy, proposal, report, brief). Use **bold** subheads or bullet points followed by full paragraphs instead of ###/#### subsections.
- When listing numbered phases (Phase 1, Phase 2, Phase 3) or steps, do NOT skip numbers—include every phase in sequence (e.g. Phase 1, then Phase 2, then Phase 3; never Phase 1 then Phase 3). In Marketing Strategy Timeline and Milestones, you MUST include Phase 2 (e.g. Phase 2: Month 3–4); never output only Phase 1 and Phase 3.
- Professional language and tone throughout
- VERY DETAILED content - write comprehensive, in-depth sections
- Include ALL performance metrics, statistics, and data points provided
- {"Use bullet lists and paragraphs for metrics—NO markdown tables." if target_tables == 0 else f"Create {target_tables} detailed markdown tables (| col | format) for metrics, plus formatted lists where appropriate."}
- Actionable insights and recommendations based on REAL data
- Proper markdown formatting for structure
- A comprehensive, professional CONCLUSION section (see below)

DETAIL AND DEPTH REQUIREMENTS:
1. Write DETAILED paragraphs, not short bullet points
2. Include specific numbers, percentages, and metrics throughout
3. Provide in-depth analysis and explanations
4. Create dedicated sections for performance metrics with full breakdowns
5. Include multiple paragraphs per section explaining the data
6. Add context and interpretation for all metrics
7. Output MUST be at least {target_pages * 450} words ({target_pages} pages). Do not stop until you reach this minimum. Expand with NEW unique content only (e.g. extra analysis, implications, recommendations)—never repeat or rephrase the same content to fill space.

PERFORMANCE METRICS SECTION REQUIREMENTS:
If campaign data includes performance metrics, you MUST create a detailed section like:

## Performance Metrics and Analysis

**Email Campaign Performance**
- **Total Emails Sent**: [actual number from data]
- **Open Rate**: [actual percentage]% - [analysis of what this means]
- **Click Rate**: [actual percentage]% - [analysis of what this means]
- **Reply Rate**: [actual percentage]% - [analysis of what this means]
- **Bounce Rate**: [actual percentage]% - [analysis of what this means]

[Detailed paragraph analyzing these metrics, comparing to industry standards, identifying trends, etc.]

**Lead Engagement Metrics**
- **Total Leads**: [actual number]
- **Lead Status Breakdown**: [detailed breakdown]
- **Engagement Analysis**: [detailed analysis]

[Detailed paragraph analyzing lead engagement, conversion potential, etc.]

CONCLUSION SECTION REQUIREMENTS:
The conclusion MUST be a proper, professional ending that:
1. Summarizes ALL key points discussed in the document (at least 3-4 paragraphs)
2. Provides a comprehensive summary of findings, recommendations, or next steps
3. Includes specific metrics and data points from the campaign
4. Ends with a strong, professional closing statement
5. For reports: Include a detailed summary of performance, trends, and future outlook
6. For proposals: Include a compelling summary, call to action, and clear next steps
7. For briefs: Include a detailed summary of campaign readiness, launch recommendations, and expected outcomes
8. For strategies: Include a comprehensive summary of strategic priorities, implementation roadmap, and expected outcomes
9. DO NOT end abruptly - always provide a detailed, multi-paragraph conclusion

**FINAL REMINDERS BEFORE YOU WRITE:**
- Minimum length: {target_pages * 450} words ({target_pages} pages). Do not stop early.
- NO REPETITION: Every paragraph and bullet must be unique. To reach the minimum length, add NEW campaign-related content (e.g. more analysis, implications, recommendations)—never duplicate or rephrase existing content.
- Tables: {"ZERO. Use lists and paragraphs only—no | table | format." if target_tables == 0 else f"Exactly {target_tables} markdown tables."}
- Use ALL REAL campaign data provided above
- Write in DETAIL with comprehensive analysis
- Include ALL performance metrics in dedicated sections
- End with a proper, detailed conclusion
- Make it professional, thorough, and data-driven:"""
        
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
        """Get campaign performance metrics"""
        try:
            performance = CampaignPerformance.objects.filter(campaign=campaign).aggregate(
                total_impressions=Sum('impressions'),
                total_clicks=Sum('clicks'),
                total_conversions=Sum('conversions'),
                avg_ctr=Avg('ctr'),
                avg_conversion_rate=Avg('conversion_rate')
            )
            
            # Filter out None values
            return {k: float(v) if v is not None else 0 for k, v in performance.items() if v is not None}
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
                lines.append("(You MUST include a Lead Details section listing each lead above—as a table if user requested tables, otherwise as a numbered bullet list.)")
        
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

LENGTH AND QUALITY: Aim for a document that would be 8–12+ pages when rendered. Every section must have multiple paragraphs or detailed bullets with explanation. Do not produce a short or generic strategy—match the depth of a professional consultant deliverable.

TIMELINE RULE: In ## Timeline and Milestones you MUST include Phase 2 (and every phase in order). Never write only Phase 1 and Phase 3—always Phase 1, then Phase 2, then Phase 3 (and more if needed). Skipping Phase 2 is forbidden.
""",
            'proposal': """
Create a LONG, comprehensive Campaign Proposal (full paragraphs and tables—like a professional client-ready document). Use ## for main sections only; NEVER use ### or ####. Use **bold** only for sub-sections (e.g. **Email Marketing** under Campaign Strategy)—never # or ## for those.

CRITICAL - PROPOSAL ONLY (do NOT add report-style sections):
Do NOT include in a Campaign Proposal: "Performance Metrics and Analysis", "Email Campaign Performance", "Lead Engagement Metrics", "Brand Awareness Metrics", "Appendices", or any section that reports or analyzes actual campaign performance. Those belong in a Performance Report. A proposal is a plan to get approval—not a report on results.

Tables: Use at most 3–4 compact tables (e.g. Resource Breakdown, Timeline). Keep tables to 3–4 columns max and short cell text. Do not add many tables.

Structure (proposal sections only):

## Executive Summary
2–3 full paragraphs: outline the strategic plan (brand awareness, lead generation, conversion), mention multi-channel efforts and Pay Per Project for email execution, and state expected outcomes.

## Campaign Overview
2+ full paragraphs: how the campaign will be executed (email, social media, content, SEO), target audience segmentation, and how objectives will be measured (open rates, click-through rates, conversion, ROI).

## Objectives and Goals
For each objective use: **Objective Name**: One-line goal. Then a bullet (•) and a full paragraph explaining how you will achieve it.
Example: **Conversion**: Convert a minimum of 20% of leads into paying customers. • [Full paragraph on lead nurturing, content, trust, etc.]
Do this for Conversion, Lead Generation, Brand Awareness (or as many as relevant).

## Target Audience
Paragraph on how audience will be identified (market research, buyer personas). Then a markdown table: Segment | Description | Demographics (e.g. Decision-Makers, Influencers, Users with descriptions and age/role).

## Campaign Strategy
Intro paragraph (strong online presence, email marketing, lead nurturing; mention leveraging the platform's email marketing agent, Pay Per Project, for email execution). Then **bold** sub-heads with bullets and short text:
**Email Marketing** • [bullet points]
**Content Marketing** • [bullet points]
**Social Media Advertising** • [bullet points]

## Tactics and Channels
**Email Marketing** • Utilize Pay Per Project for email execution. • [1–2 more bullets]
**Content Marketing** • [bullets]
**Social Media Advertising** • [bullets]

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

End the proposal here. Do NOT add Performance Metrics and Analysis, Email Campaign Performance, Lead Engagement Metrics, Brand Awareness Metrics, Appendices, or any report-style sections. Always produce a LONG, detailed proposal with full paragraphs in Executive Summary, Campaign Overview, Objectives, Target Audience, Campaign Strategy, and Conclusion. Use at most 3–4 compact tables. NEVER use ### or ####—only ## and **bold**.
""",
            'report': """
Create a LONG, detailed Performance Report (full paragraphs throughout—not short bullets). Use ## for main sections only; do NOT use ### (H3) subsections—use **bold** labels or bullet points followed by full paragraphs.

NO DUPLICATION: (1) Lead Details (email, name, company, status) must appear in exactly ONE place—either one table OR one list; do NOT repeat the same lead list/table anywhere else. (2) Email/performance metrics (sent, open rate, click rate, reply rate, bounce rate) must appear in exactly ONE place—one table or one bullet list; do NOT repeat the same metrics in another section. (3) Do NOT add a "Lead Details Table", "Performance Metrics Table", or any summary/repeat section at the end—the report ends with ## Future Outlook (and charts go inside Performance Metrics and KPIs). (4) Do not repeat Success Criteria, Objectives, or Timeline in a second section or table. (5) Conclusion, Call to Action, and Future Outlook must each be distinct: do NOT copy Recommendations or the same bullets into these sections; write different, specific content for each. (6) If you need more length, add NEW unique analysis—never duplicate or rephrase existing content.

Sections:
- Executive Summary (2–3 full paragraphs)
- Campaign Overview: present campaign info, target audience, goals/targets in flowing prose and bullet lists where useful; then add a short paragraph summarizing the campaign. Do NOT use ### under Campaign Overview.
- Performance Metrics and KPIs: include campaign metrics and REAL data; write full paragraphs analyzing what the numbers mean. Present metrics as a markdown table ONLY if user requested tables; otherwise use bullet lists.
- Lead Details: list EVERY lead (Email, Name, Company, Status). Use a table ONLY if user requested tables; otherwise use a numbered bullet list.
- Key Achievements: each achievement as a bullet or bold point PLUS a full paragraph explaining it (do not just list one-line bullets). If there are positive opportunities (e.g. strong metrics, engaged leads, growth potential), include them here and make that part a bit long.
- Challenges and Issues: ALWAYS include this section. Keep it a bit long—each challenge as a **bold** label (e.g. **Low Email Open Rates**, **Limited Lead Engagement**) PLUS a full paragraph (3–5 sentences) explaining what it is, why it matters, and its impact. Do not use one-line bullets only.
- Analysis and Insights: 2–4 full paragraphs based on REAL performance data. If there are positive opportunities, mention them and make that part a bit long.
- Recommendations: ALWAYS include this section. Keep it a bit long—each recommendation as a **bold** label (e.g. **Gather Audience Data**, **Optimize Email Marketing**) PLUS a full paragraph (3–5 sentences) on what to do, why it helps, and how to implement. Do not use one-line bullets only.
- Conclusion: comprehensive summary and key takeaways (2–3 paragraphs).
- Call to Action: always include this section (## Call to Action) with clear, actionable next steps (e.g. what to do next week, who to follow up with, decisions needed).
- Future Outlook: always include this section (## Future Outlook) with outlook for the campaign (e.g. expected trends, risks, opportunities, next quarter).

MANDATORY:
1. Campaign metrics: Total Emails Sent, Open Rate, Click Rate, Reply Rate, Bounce Rate, Total Leads. Present as a markdown table (| Metric | Value |) ONLY if user requested tables; otherwise use bullet list.
2. Lead Details: every lead from the data (Email, Name, Company, Status). Use table format ONLY if user requested tables; otherwise use numbered bullet list.
3. Do NOT use ### (H3) headings—use ## for main sections and **bold** or bullets + paragraphs for sub-content.
4. Charts: you MUST add [CHART] blocks when user requested them. Use the exact format (type, title, labels, values). Values must be NUMBERS ONLY (e.g. 50, 16.67, 50, 0)—never include % in the values line (write 50 not 50%). Labels and values from CAMPAIGN DATA only. Place each chart inside "Performance Metrics and KPIs"—do NOT put charts after Future Outlook. Never omit requested charts.
5. Always include ## Call to Action and ## Future Outlook as separate section headings with full paragraphs.
6. Always write a LONG report: full paragraphs in every section, especially Achievements and Challenges (each point must have a paragraph). Aim for thorough, readable length.
7. ALWAYS include Challenges and Issues and Recommendations; keep both sections a bit long (full paragraphs per item). If there are positive opportunities (e.g. strong performance, upside potential), include them in Key Achievements or Analysis and make that part a bit long too.
""",
            'brief': """
Create a DETAILED Campaign Brief that reads like a proper campaign briefing. Use ONLY the campaign data provided above. Use ## for main sections only; do NOT use ### or ####. Every section MUST have substantive content (paragraphs or bullets with explanation)—do NOT leave sections empty or one-line.

NO DUPLICATION: (1) Lead list and Email metrics each appear in exactly ONE place: leads in "Lead Engagement Data", email metrics in "Email Campaign Performance". (2) The document MUST END with the Conclusion section. Do NOT add ANY section or table after Conclusion—no "Lead Details", no "Email Campaign Performance Metrics", no "Target Audience", no "Target Leads and Conversions" (with or without "Table"). Nothing after **Conclusion**. (3) Do NOT repeat Objectives/Success Criteria/Timeline elsewhere. (4) To add length, use NEW unique content only—never duplicate sections or tables.

Sections (use ONLY these—do NOT add "Performance Metrics and Analysis", "Lead Engagement Metrics", "Engagement Analysis", "Improvement Opportunities", or "Action Items" as extra ## sections):

## Campaign Overview
2–3 full paragraphs. Paragraph 1: Campaign name, description, status, start date, end date (from CAMPAIGN INFORMATION). Paragraph 2: Objectives (target leads, target conversions, goals from TARGETS/GOALS). Paragraph 3: Summary of target audience and focus. Use the exact data—do not write "no data available" if the data is in the prompt above.

## Objectives and Goals
List each target from the data (Target Leads, Target Conversions) and goals. For each: **Target name**: value. Then a short paragraph explaining what it means and how the campaign will achieve it. Do not write only one bullet with no context.

## Target Audience
Use ONLY the TARGET AUDIENCE section from the CAMPAIGN DATA above. If the data provides demographics, age, location, industry, interests, or company size, use them. If the campaign data has NO target audience or no demographics/interests/company size, write "Not specified" or "Target audience not defined in campaign data" in one short paragraph—do NOT invent demographics (e.g. no "18-35", "young adults", "summer sales interests") or company sizes unless they appear in the data.

## Key Messaging
1–2 paragraphs derived from the campaign description and goals. What will the campaign communicate? What value proposition? Use the data.

## Campaign Timeline
Use ONLY the campaign's Start Date and End Date from the data. Phases MUST fall strictly within this period—every phase start and end date must be on or between Start Date and End Date. If the campaign is Feb 20–Feb 21, do NOT add Phase 2 or Phase 3 ending on Feb 22 or later; use one or two phases within Feb 20–21 only (e.g. Phase 1: Feb 20, Phase 2: Feb 21). For longer campaigns, split into 2–4 phases with dates between start and end. NEVER use timeframes that extend beyond End Date. If dates are "Not set", write "Not specified".

## Success Criteria
Use the targets from the data exactly. "Target conversions" means the number of conversions (e.g. 10), not a percentage—do not write "10% conversion rate" unless the data explicitly says that. Full paragraph or bullets on how success will be measured.

## Email Campaign Performance
Use the exact EMAIL CAMPAIGN METRICS from the CAMPAIGN DATA above only. List: Total Emails Sent, Open Rate, Click Rate, Reply Rate, Bounce Rate—use the exact numbers from the prompt (e.g. if data says 10 sent, 30% open, write those numbers). Use correct tense: if the data shows emails already sent (e.g. Emails Sent: 10), write "The campaign has sent X emails" / "Total emails sent: X", not "will send". Do not invent metrics. If the prompt has no email metrics at all, write one short paragraph: "Email campaign not yet launched."

## Lead Engagement Data
Use the exact LEAD DATA from the data. State the total lead count from the data (e.g. "Total leads: 3" if the data says 3). List EVERY lead from the prompt (email, name, company, status for each). Then 1–2 paragraphs on engagement. Do NOT say "has not yet generated any leads" or "no leads" when the data shows a lead count greater than zero—use the actual number (e.g. "The campaign has 3 leads, all currently new.").

## Issues / Challenges
ALWAYS include this section. Keep it a bit long—each issue must have real detail. For each issue: **Bold issue name** (e.g. **Low Email Open Rates**, **Limited Lead Engagement**, **Missing Audience Data**) followed by a FULL PARAGRAPH (3–5 sentences) explaining: what the issue is, why it matters, cause/context from the campaign data, and impact on the campaign. Do NOT write only one-line bullets. Minimum 2–4 issues, each with a bold heading and a full paragraph. Base on actual data (open rate, click rate, lead count, audience fields, conversions).

## Improvements / Recommendations
ALWAYS include this section. Keep it a bit long—each recommendation must have real detail. For each: **Bold recommendation name** (e.g. **Gather Audience Data**, **Optimize Email Marketing**, **Develop Valuable Content**) followed by a FULL PARAGRAPH (3–5 sentences) explaining: what to do, why it will help, and how to implement it. Do NOT write only one-line bullets. Minimum 2–4 recommendations, each with a bold heading and a full paragraph. Examples: audience research, A/B testing subject lines, content calendar, lead nurturing, tracking setup.

If the campaign has positive opportunities (e.g. strong open rate, engaged leads, growth potential), mention them in the Conclusion or in a short paragraph—and make that part a bit long (2–4 sentences minimum).

## Conclusion
2–3 full paragraphs: campaign readiness, launch recommendations, expected outcomes. Summarize the brief and state whether the campaign is ready and what is needed.

CRITICAL: (1) Use ONLY the numbers and dates from the CAMPAIGN DATA above—Email Campaign Performance and Lead Engagement must use the exact values from "EMAIL CAMPAIGN METRICS" and "LEAD DATA" (do not change or round). (2) Use the Start Date and End Date format given (e.g. "February 20, 2026")—do not output raw dates like 2026-02-20. (3) The document MUST END with the Conclusion section. Do NOT add ANY content after Conclusion—no "Lead Details", "Email Campaign Performance Metrics", "Target Audience", or "Target Leads and Conversions" section or table after Conclusion. (4) Each piece of data (leads, email metrics, targets) appears in only one section. (5) Campaign Timeline: phase dates must be within Start and End date only. (6) "Target conversions" = the number (e.g. 10), not "10%". (7) Issues/Challenges and Improvements/Recommendations: both required; each item **bold** + full paragraph. (8) Campaign Brief only—do not change strategy, proposal, or report.
""",
            'presentation': """
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
