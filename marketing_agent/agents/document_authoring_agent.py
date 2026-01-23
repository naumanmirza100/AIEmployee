"""
Document Authoring Agent
Creates structured marketing documents such as strategies, proposals, reports, presentations, and campaign briefs.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional
from marketing_agent.models import Campaign, MarketingDocument, CampaignPerformance, Lead, EmailSendHistory
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
import logging

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
        Use the provided campaign data and context to create accurate, relevant documents."""
    
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
        # Increased max_tokens for more detailed documents
        content = self._call_llm_for_writing(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=0.7,
            max_tokens=8000  # Increased for detailed documents
        )
        
        return content
    
    def _build_document_prompt(self, document_type: str, document_data: Dict, campaign: Optional[Campaign], context: Dict) -> str:
        """Build the prompt for document generation"""
        title = document_data.get('title', f'{document_type.title()} Document')
        requirements = document_data.get('requirements', '')
        key_points = document_data.get('key_points', '')
        
        # Get campaign data if available
        campaign_data = {}
        if campaign:
            campaign_data = self._get_campaign_data_for_document(campaign, document_type)
        
        # Build document type specific instructions
        doc_instructions = self._get_document_type_instructions(document_type)
        
        prompt = f"""Create a professional {document_type} document.

DOCUMENT TITLE: {title}

DOCUMENT REQUIREMENTS:
{requirements if requirements else 'Create a comprehensive, professional document.'}

ADDITIONAL KEY POINTS:
{key_points if key_points else 'None provided'}

"""
        
        # Add campaign data if available
        if campaign_data:
            prompt += f"""
═══════════════════════════════════════════════════════════════
CAMPAIGN DATA (REAL DATA FROM DATABASE - USE ALL OF THIS):
═══════════════════════════════════════════════════════════════
{self._format_campaign_data(campaign_data)}
═══════════════════════════════════════════════════════════════

CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:
1. ALL data above is REAL data fetched from the database for this specific campaign
2. You MUST include ALL performance metrics, statistics, and data points provided above
3. DO NOT skip or omit any metrics - include emails_sent, emails_opened, emails_clicked, open_rate, click_rate, reply_rate, bounce_rate, leads_count, etc.
4. Create DETAILED sections with actual numbers, percentages, and specific data points
5. Use the actual values provided above - do NOT use placeholder, generic, or "Not specified" data
6. If a field is missing from the data above, you can mention it's not available, but DO NOT make up values
7. Base ALL analysis, metrics, and recommendations on the REAL campaign data provided
8. For email campaigns: Create a detailed "Email Performance Metrics" section with:
   - Total emails sent (actual number)
   - Open rate (actual percentage)
   - Click rate (actual percentage)
   - Reply rate (actual percentage)
   - Bounce rate (actual percentage)
   - Analysis of what these metrics mean
9. For leads: Create a detailed "Lead Engagement" section with:
   - Total leads count (actual number)
   - Lead details and status breakdown
   - Engagement analysis
10. Make the document VERY DETAILED and SPECIFIC to this campaign using ALL the real data above
11. Include tables, charts descriptions, and detailed breakdowns where appropriate
12. Write in-depth analysis, not just surface-level information
"""
        else:
            prompt += """
NOTE: No campaign data is associated with this document. Create a general document based on the requirements provided.
"""
        
        prompt += f"""

{doc_instructions}

DOCUMENT STRUCTURE REQUIREMENTS:
- Clear sections and headings (use ## for main sections, ### for subsections)
- Professional language and tone throughout
- VERY DETAILED content - write comprehensive, in-depth sections
- Include ALL performance metrics, statistics, and data points provided
- Create detailed tables or formatted lists for metrics when appropriate
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
7. Make the document comprehensive and thorough - aim for 2000+ words if data is available

PERFORMANCE METRICS SECTION REQUIREMENTS:
If campaign data includes performance metrics, you MUST create a detailed section like:

## Performance Metrics and Analysis

### Email Campaign Performance
- **Total Emails Sent**: [actual number from data]
- **Open Rate**: [actual percentage]% - [analysis of what this means]
- **Click Rate**: [actual percentage]% - [analysis of what this means]
- **Reply Rate**: [actual percentage]% - [analysis of what this means]
- **Bounce Rate**: [actual percentage]% - [analysis of what this means]

[Detailed paragraph analyzing these metrics, comparing to industry standards, identifying trends, etc.]

### Lead Engagement Metrics
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

Begin writing the document now. 
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
        
        # Get performance metrics
        performance = self._get_campaign_performance_data(campaign)
        if performance:
            data['performance'] = performance
        
        # Get leads data
        leads_count = campaign.leads.count()
        if leads_count > 0:
            data['leads_count'] = leads_count
            data['leads'] = list(campaign.leads.values('email', 'first_name', 'last_name', 'company', 'status')[:10])
        
        # Get email sending data from database
        email_sends = EmailSendHistory.objects.filter(campaign=campaign)
        if email_sends.exists():
            total_sent = email_sends.count()
            total_opened = email_sends.filter(status='opened').count()
            total_clicked = email_sends.filter(status='clicked').count()
            total_replied = email_sends.filter(status='replied').count()
            total_bounced = email_sends.filter(status='bounced').count()
            
            data['emails_sent'] = total_sent
            data['emails_opened'] = total_opened
            data['emails_clicked'] = total_clicked
            data['emails_replied'] = total_replied
            data['emails_bounced'] = total_bounced
            
            # Calculate rates
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
        lines = []
        lines.append("=== CAMPAIGN INFORMATION ===")
        
        # Basic campaign info
        if 'name' in campaign_data:
            lines.append(f"Campaign Name: {campaign_data['name']}")
        if 'description' in campaign_data:
            lines.append(f"Description: {campaign_data['description']}")
        if 'status' in campaign_data:
            lines.append(f"Status: {campaign_data['status']}")
        if 'start_date' in campaign_data:
            lines.append(f"Start Date: {campaign_data['start_date']}")
        if 'end_date' in campaign_data:
            lines.append(f"End Date: {campaign_data['end_date']}")
        
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
        
        # Email metrics
        if 'emails_sent' in campaign_data:
            lines.append("")
            lines.append("=== EMAIL CAMPAIGN METRICS (MUST INCLUDE IN DOCUMENT) ===")
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
        
        # Lead data
        if 'leads_count' in campaign_data:
            lines.append("")
            lines.append("=== LEAD DATA (MUST INCLUDE IN DOCUMENT) ===")
            lines.append(f"Total Leads: {campaign_data['leads_count']}")
            if 'leads' in campaign_data and campaign_data['leads']:
                lines.append(f"Sample Leads (showing up to 10):")
                for lead in campaign_data['leads'][:10]:
                    lead_str = f"  - {lead.get('email', 'N/A')}"
                    if lead.get('first_name') or lead.get('last_name'):
                        lead_str += f" ({lead.get('first_name', '')} {lead.get('last_name', '')})".strip()
                    if lead.get('company'):
                        lead_str += f" - {lead.get('company')}"
                    if lead.get('status'):
                        lead_str += f" [Status: {lead.get('status')}]"
                    lines.append(lead_str)
        
        # Handle nested dicts
        for key, value in campaign_data.items():
            if isinstance(value, dict) and key != 'performance':
                lines.append("")
                lines.append(f"=== {key.upper().replace('_', ' ')} ===")
                for sub_key, sub_value in value.items():
                    lines.append(f"{sub_key.replace('_', ' ').title()}: {sub_value}")
        
        return "\n".join(lines)
    
    def _get_document_type_instructions(self, document_type: str) -> str:
        """Get document type specific instructions"""
        instructions = {
            'strategy': """
Create a comprehensive Marketing Strategy document with:
- Executive Summary
- Market Analysis
- Target Audience Analysis
- Marketing Objectives and Goals
- Marketing Channels and Tactics
- Resource Allocation
- Timeline and Milestones
- Success Metrics and KPIs
- Risk Assessment
- Conclusion and Next Steps (MUST include a detailed conclusion summarizing strategic priorities, implementation roadmap, and expected outcomes)
""",
            'proposal': """
Create a professional Campaign Proposal document with:
- Executive Summary
- Campaign Overview
- Objectives and Goals
- Target Audience
- Campaign Strategy
- Tactics and Channels
- Resource Breakdown
- Timeline
- Expected Results
- Conclusion (MUST include a compelling summary, call to action, and clear next steps for approval/implementation)
""",
            'report': """
Create a detailed Performance Report document with:
- Executive Summary
- Campaign Overview
- Performance Metrics and KPIs (use REAL data from campaign if provided)
- Key Achievements
- Challenges and Issues
- Analysis and Insights (based on REAL performance data)
- Recommendations (data-driven recommendations)
- Conclusion (MUST include a comprehensive summary of performance, key takeaways, and future outlook)
""",
            'brief': """
Create a comprehensive Campaign Brief document with:
- Campaign Overview
- Objectives and Goals
- Target Audience
- Key Messaging
- Campaign Timeline
- Success Criteria
- Email Campaign Performance (MUST use REAL email sending data if provided: emails sent, opened, clicked rates)
- Lead Engagement Data (MUST use REAL lead data if provided: number of leads, lead details, engagement metrics)
- Conclusion (MUST include a summary of campaign readiness, launch recommendations, and expected outcomes based on REAL data)
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
