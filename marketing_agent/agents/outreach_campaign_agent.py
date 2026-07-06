"""
Outreach & Campaign Agent
Designs, launches, and manages multi-channel marketing campaigns across email, 
social, paid ads, and partnerships, ensuring consistent messaging and timely execution.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, Lead, EmailSendHistory, Reply, EmailAccount
from marketing_agent.performance_sync import sync_campaign_performance
from django.contrib.auth.models import User
from datetime import datetime, timedelta
import json
import re


class OutreachCampaignAgent(MarketingBaseAgent):
    """
    Outreach & Campaign Agent
    
    This agent:
    - Designs multi-channel marketing campaigns
    - Launches campaigns across email, social, paid ads, and partnerships
    - Manages campaign execution and ensures timely delivery
    - Ensures consistent messaging across all channels
    - Tracks campaign performance and optimizes in real-time
    - Coordinates multi-channel campaign workflows
    
    Capabilities:
    - Campaign strategy design
    - Multi-channel campaign planning
    - Content and messaging consistency
    - Campaign launch and scheduling
    - Performance monitoring and optimization
    - Cross-channel coordination
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are an Outreach & Campaign Agent for a marketing system.
        Your role is to:
        1. Design comprehensive multi-channel marketing campaigns
        2. Launch campaigns across email, social media, paid advertising, and partnerships
        3. Ensure consistent messaging and branding across all channels
        4. Manage campaign execution and ensure timely delivery
        5. Coordinate campaign workflows and schedules
        6. Monitor campaign performance and optimize in real-time
        7. Provide campaign recommendations and best practices
        
        You are an expert in:
        - Multi-channel campaign strategy
        - Email marketing campaigns
        - Social media campaign management
        - Paid advertising (PPC, display, etc.)
        - Partnership and affiliate campaigns
        - Campaign messaging and content consistency
        - Campaign scheduling and automation
        - Performance tracking and optimization
        
        Always provide actionable, strategic campaign plans with clear timelines, 
        messaging guidelines, and performance metrics."""
    
    def process(self, action: str, user_id: int, campaign_data: Optional[Dict] = None,
                campaign_id: Optional[int] = None, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - handles various campaign actions
        
        Args:
            action (str): Action to perform (design, launch, manage, optimize, schedule)
            user_id (int): User ID for campaign ownership
            campaign_data (Dict): Campaign data for design/creation
            campaign_id (int): Existing campaign ID for management actions
            context (Dict): Additional context (research, goals, etc.)
            
        Returns:
            Dict: Action results with campaign information
        """
        self.log_action(f"Processing campaign action: {action}", {
            "user_id": user_id,
            "campaign_id": campaign_id
        })
        
        if action == 'design':
            return self.design_campaign(user_id, campaign_data, context)
        elif action == 'auto_fill':
            return self.auto_fill_campaign(user_id, campaign_data, context)
        elif action == 'launch':
            return self.launch_campaign(campaign_id, user_id, campaign_data, context)
        elif action == 'manage':
            return self.manage_campaign(campaign_id, user_id, context)
        elif action == 'optimize':
            return self.optimize_campaign(campaign_id, user_id, context)
        elif action == 'schedule':
            return self.schedule_campaign(campaign_id, user_id, campaign_data)
        elif action == 'create_multi_channel':
            return self.create_multi_channel_campaign(user_id, campaign_data, context)
        else:
            return {
                'success': False,
                'error': f'Unknown action: {action}. Supported actions: design, auto_fill, launch, manage, optimize, schedule, create_multi_channel'
            }
    
    def design_campaign(self, user_id: int, campaign_data: Optional[Dict] = None,
                       context: Optional[Dict] = None) -> Dict:
        """
        Design an email-only marketing campaign
        
        Args:
            user_id (int): User ID
            campaign_data (Dict): Campaign requirements (name, goals, target_audience, etc.)
            context (Dict): Additional context (market research, competitor data, etc.)
            
        Returns:
            Dict: Email campaign design with strategy, messaging, and timeline
        """
        self.log_action("Designing campaign", {"user_id": user_id})
        
        # Get relevant market research for context
        research_context = self._get_research_context(user_id)
        
        # Build comprehensive context
        full_context = self._build_design_context(campaign_data, context, research_context)
        
        # Generate campaign design using AI
        campaign_design = self._generate_campaign_design(full_context)
        
        # Parse and structure the design
        structured_design = self._parse_campaign_design(campaign_design, campaign_data)
        
        return {
            'success': True,
            'action': 'design',
            'campaign_design': structured_design,
            'raw_design': campaign_design,
            'recommendations': structured_design.get('recommendations', [])
        }
    
    def auto_fill_campaign(self, user_id: int, campaign_data: Optional[Dict] = None,
                           context: Optional[Dict] = None) -> Dict:
        """
        Given just a campaign name, description, and duration, ask the AI to infer
        the rest of the targeting fields (target leads, target conversions, audience
        demographics) so the user can review/edit them before creating the campaign.

        Args:
            user_id (int): User ID
            campaign_data (Dict): Must include 'name', 'description'; may include
                'start_date', 'end_date' (duration already resolved by the caller)
            context (Dict): Additional context (unused for now, kept for parity)

        Returns:
            Dict: Suggested field values (editable by the user before creation)
        """
        campaign_data = campaign_data or {}
        name = (campaign_data.get('name') or '').strip() or 'New Campaign'
        description = (campaign_data.get('description') or '').strip()
        start_date = campaign_data.get('start_date') or ''
        end_date = campaign_data.get('end_date') or ''

        self.log_action("Auto-filling campaign fields", {"user_id": user_id})

        prompt = f"""Based on this email marketing campaign, infer reasonable targeting values.

Campaign name: {name}
Description: {description or 'Not provided'}
Duration: {start_date or 'Not specified'} to {end_date or 'Not specified'}

Respond with ONLY a single JSON object (no markdown, no commentary) with exactly these keys:
{{
  "target_leads": <integer, realistic number of qualified leads for this duration>,
  "target_conversions": <integer, realistic number of conversions, smaller than target_leads>,
  "age_range": "<e.g. 25-45, or empty string if not applicable>",
  "location": "<likely target location, or empty string>",
  "industry": "<likely target industry, or empty string>",
  "company_size": "<one of: 1-10, 11-50, 51-200, 201-1000, 1001-5000, 5000+, or empty string>",
  "interests": "<comma-separated interests relevant to the audience, or empty string>",
  "language": "<primary language, e.g. English, or empty string>"
}}"""

        try:
            raw = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.4,
                max_tokens=400
            )
            fields = self._parse_auto_fill_json(raw)
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error auto-filling campaign fields", {"error": str(e)})
            return {'success': False, 'error': str(e)}

        return {
            'success': True,
            'action': 'auto_fill',
            'suggested_fields': fields
        }

    def _parse_auto_fill_json(self, raw_text: str) -> Dict:
        """Parse the LLM's JSON response for auto_fill_campaign, tolerating stray text/markdown fences."""
        defaults = {
            'target_leads': None,
            'target_conversions': None,
            'age_range': '',
            'location': '',
            'industry': '',
            'company_size': '',
            'interests': '',
            'language': '',
        }
        if not raw_text:
            return defaults
        text = raw_text.strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lower().startswith('json'):
                text = text[4:]
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return defaults
        try:
            parsed = json.loads(match.group(0))
        except (ValueError, TypeError):
            return defaults
        result = dict(defaults)
        for key in defaults:
            if key in parsed and parsed[key] is not None:
                result[key] = parsed[key]
        for int_key in ('target_leads', 'target_conversions'):
            try:
                result[int_key] = int(result[int_key]) if result[int_key] not in (None, '') else None
            except (ValueError, TypeError):
                result[int_key] = None
        for str_key in ('age_range', 'location', 'industry', 'company_size', 'interests', 'language'):
            result[str_key] = str(result[str_key]).strip() if result[str_key] else ''
        return result

    def generate_template_content(self, name: str, description: str, company_name: str = '') -> Dict:
        """
        Generate an email template's subject line and HTML (+ plain-text) body from
        just a name and a short description of what the email should say — the user
        reviews/edits the result before saving, same pattern as auto_fill_campaign.

        Args:
            name (str): Template name (context only, not shown in the email)
            description (str): What the email should say — goals, tone, key points
            company_name (str): Sender's company name, signed at the email's close

        Returns:
            Dict: { success, subject, html_content, text_content }
        """
        self.log_action("Generating template content", {"name": name})

        sign_off = f'"Best regards,\\n{company_name}"' if company_name else '"Best regards,\\n[Sender\'s company name]"'
        prompt = f"""Write a marketing email for the following. Output EXACTLY two sections, in this order, with no extra commentary:

SUBJECT: <the email subject line, one line only>
BODY:
<the email body as clean semantic HTML>

Template name: {name or 'Untitled'}
What the email should say: {description or 'Not provided'}

Rules:
- The BODY must be plain semantic HTML (e.g. <p>, <a>, <strong> tags) — no <html>/<head>/<body> wrapper, no inline <style> blocks, no markdown asterisks, no code fences.
- Use merge-field placeholders where natural: {{{{first_name}}}}, {{{{last_name}}}}, {{{{company}}}}, {{{{job_title}}}}. Always greet with {{{{first_name}}}}.
- End the email with a sign-off closing as {sign_off} — sign with the company name, not a person's name, and never leave a "[Your Name]"-style placeholder.
- Keep the body concise: a greeting, 2-4 short paragraphs or a short list, and a clear call to action.
- Professional but warm tone unless the description says otherwise.
- The SUBJECT line must be plain text (no HTML, no quotes around it)."""

        try:
            raw = self._call_llm_for_writing(
                prompt,
                self.system_prompt,
                temperature=0.7,
                max_tokens=1200
            )
            subject, html_content = self._parse_template_generation(raw)
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating template content", {"error": str(e)})
            return {'success': False, 'error': str(e)}

        text_content = re.sub(r'<[^>]+>', '', html_content).strip()

        return {
            'success': True,
            'subject': subject,
            'html_content': html_content,
            'text_content': text_content,
        }

    def _parse_template_generation(self, raw_text: str):
        """
        Split the LLM's response into (subject, html_content). Tolerant of the model
        skipping the 'BODY:' label, wrapping the subject onto a second line, or
        wrapping the whole thing in a code fence — only 'SUBJECT:' is load-bearing.
        """
        text = (raw_text or '').strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
            text = re.sub(r'\n?```$', '', text).strip()

        subject_match = re.search(r'SUBJECT:\s*(.*)', text, re.IGNORECASE)
        if not subject_match:
            # No recognizable structure at all — treat the whole thing as body.
            return '', text.strip()

        after_subject = text[subject_match.end():]
        # Subject ends at "BODY:" if present, otherwise at the first blank line,
        # otherwise at the first HTML tag (model went straight into markup).
        body_label = re.search(r'\n\s*BODY:\s*', after_subject, re.IGNORECASE)
        if body_label:
            subject_tail = after_subject[:body_label.start()]
            html_content = after_subject[body_label.end():]
        else:
            blank_line = re.search(r'\n\s*\n', after_subject)
            tag_start = re.search(r'<[a-zA-Z]', after_subject)
            cut = min([p.start() for p in (blank_line, tag_start) if p] or [len(after_subject)])
            subject_tail = after_subject[:cut]
            html_content = after_subject[cut:]

        subject = (subject_match.group(1) + subject_tail).replace('\n', ' ').strip()
        subject = subject.strip('"').strip("'").strip()
        html_content = html_content.strip()
        if html_content.startswith('```'):
            html_content = re.sub(r'^```[a-zA-Z]*\n?', '', html_content)
            html_content = re.sub(r'\n?```$', '', html_content).strip()
        return subject, html_content

    # Valid interest_level values a sub-sequence can be routed by — must match
    # the frontend's INTEREST_LEVEL_OPTIONS and the reply-classification logic
    # elsewhere in the reply-processing pipeline.
    INTEREST_LEVELS = ['any', 'positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']

    def classify_interest_level(self, description: str) -> Dict:
        """
        Map a free-form description of a reply scenario (e.g. "when the lead
        says they're not interested right now") to the closest matching
        interest_level(s), so the user doesn't have to pick from the dropdown
        manually when creating a sub-sequence.

        A description can legitimately name more than one category at once
        (e.g. "email for interested leads and email for negative leads") —
        since one sub-sequence can only route on one interest_level, this
        returns ALL categories detected so the caller can offer to create one
        sub-sequence per category instead of collapsing them to "any".

        Args:
            description (str): Free-form text describing the reply scenario

        Returns:
            Dict: { success, interest_level, interest_levels }
                  interest_level is the first/primary match (back-compat);
                  interest_levels is the full ordered list of distinct matches.
        """
        self.log_action("Classifying interest level", {"description": description[:100]})

        prompt = f"""Classify the following description of a lead's email reply into ONE OR MORE of these categories. The description may name more than one category — if so, list ALL of them. Respond with ONLY comma-separated category keys, nothing else — no punctuation besides commas, no explanation.

Categories:
- any: catches any/all replies regardless of sentiment (use ONLY if no specific category applies)
- positive: the lead is interested / responded positively
- negative: the lead is not interested / declined
- neutral: a neutral acknowledgment with no clear sentiment
- requested_info: the lead asked for more information or details
- objection: the lead raised an objection, concern, or pushback
- unsubscribe: the lead asked to stop receiving emails / unsubscribe

Description: {description}

Respond with comma-separated category keys only (from: any, positive, negative, neutral, requested_info, objection, unsubscribe). Example for a description naming two categories: "positive,negative"."""

        try:
            raw = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.0,
                max_tokens=40
            )
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error classifying interest level", {"error": str(e)})
            return {'success': False, 'error': str(e)}

        cleaned = (raw or '').strip().lower()
        # Tolerate the model wrapping keys in a short sentence or extra
        # punctuation — scan for every known category mentioned, in the order
        # they first appear, and dedupe.
        matched = []
        for part in re.split(r'[,\n]', cleaned):
            part = part.strip().strip('.').strip('"').strip("'")
            lvl = next((lvl for lvl in self.INTEREST_LEVELS if lvl == part or lvl in part), None)
            if lvl and lvl not in matched:
                matched.append(lvl)
        # Fallback: scan the whole cleaned string in case comma-splitting
        # didn't line up with how the model actually responded.
        if not matched:
            for lvl in self.INTEREST_LEVELS:
                if lvl in cleaned and lvl not in matched:
                    matched.append(lvl)
        # If "any" was matched alongside specific categories, the specific
        # categories are more useful — drop "any" unless it's the only match.
        if len(matched) > 1 and 'any' in matched:
            matched = [lvl for lvl in matched if lvl != 'any']
        if not matched:
            matched = ['any']

        return {'success': True, 'interest_level': matched[0], 'interest_levels': matched}

    def create_multi_channel_campaign(self, user_id: int, campaign_data: Dict,
                                      context: Optional[Dict] = None, leads_file=None) -> Dict:
        """
        Create and save a multi-channel campaign to database
        Direct creation without AI - just save the campaign data
        
        Args:
            user_id (int): User ID
            campaign_data (Dict): Campaign data (name, goals, channels, etc.)
            context (Dict): Additional context
            
        Returns:
            Dict: Created campaign information
        """
        self.log_action("Creating multi-channel campaign", {"user_id": user_id})
        
        try:
            user = User.objects.get(id=user_id)
            
            # Extract goals data - can come from direct fields or goals dict
            goals = campaign_data.get('goals', {})
            target_audience = campaign_data.get('target_audience', {})
            
            # Extract individual goal fields (from direct fields or goals dict)
            target_leads = campaign_data.get('target_leads') or (goals.get('leads') if isinstance(goals, dict) else None)
            target_conversions = campaign_data.get('target_conversions') or (goals.get('conversions') if isinstance(goals, dict) else None)
            
            # Extract individual target audience fields (from direct fields or target_audience dict)
            age_range = campaign_data.get('age_range') or (target_audience.get('age_range') if isinstance(target_audience, dict) else None)
            location = campaign_data.get('location') or (target_audience.get('location') if isinstance(target_audience, dict) else None)
            industry = campaign_data.get('industry') or (target_audience.get('industry') if isinstance(target_audience, dict) else None)
            interests = campaign_data.get('interests')
            if not interests and isinstance(target_audience, dict):
                interests_list = target_audience.get('interests', [])
                if isinstance(interests_list, list):
                    interests = ', '.join(str(i) for i in interests_list)
                else:
                    interests = target_audience.get('interests')
            company_size = campaign_data.get('company_size') or (target_audience.get('company_size') if isinstance(target_audience, dict) else None)
            language = campaign_data.get('language') or (target_audience.get('language') if isinstance(target_audience, dict) else None)
            
            # Parse date strings if provided as strings
            start_date = campaign_data.get('start_date')
            if start_date and isinstance(start_date, str):
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    start_date = None
            
            end_date = campaign_data.get('end_date')
            if end_date and isinstance(end_date, str):
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    end_date = None
            
            campaign_name = (campaign_data.get('name') or 'New Campaign').strip() or 'New Campaign'
            if Campaign.objects.filter(owner_id=user_id, name__iexact=campaign_name).exists():
                return {
                    'success': False,
                    'error': 'A campaign with this name already exists. Please choose a different name.',
                }

            email_account = None
            email_account_id = campaign_data.get('email_account_id')
            if email_account_id:
                try:
                    email_account = EmailAccount.objects.get(id=email_account_id, owner=user)
                except EmailAccount.DoesNotExist:
                    return {
                        'success': False,
                        'error': 'Email account not found or not owned by you.',
                    }

            # Create campaign in database with all fields
            campaign = Campaign.objects.create(
                name=campaign_name,
                description=campaign_data.get('description', ''),
                campaign_type=campaign_data.get('campaign_type', 'email'),  # Email-only campaigns
                status='draft',
                start_date=start_date,
                end_date=end_date,
                # Individual goal fields
                target_leads=target_leads,  # This is target QUALIFIED/interested leads, not total uploaded
                target_conversions=target_conversions,
                # Individual target audience fields
                age_range=age_range or '',
                location=location or '',
                industry=industry or '',
                interests=interests or '',
                company_size=company_size or '',
                language=language or '',
                # JSON fields for backward compatibility
                target_audience=campaign_data.get('target_audience', {}),
                goals=campaign_data.get('goals', {}),
                channels=campaign_data.get('channels', ['email']),
                email_account=email_account,
                owner=user
            )
            
            # Process leads file if provided
            leads_count = 0
            if leads_file:
                try:
                    leads_count = self._process_leads_file(leads_file, campaign, user_id)
                except Exception as e:
                    self.log_action("Error processing leads file", {"error": str(e)})
                    # Don't fail campaign creation if leads upload fails
                    leads_count = 0
            
            message = f'Campaign "{campaign.name}" created successfully'
            if leads_count > 0:
                message += f' with {leads_count} leads uploaded'
            
            return {
                'success': True,
                'action': 'create_multi_channel',
                'campaign_id': campaign.id,
                'campaign_name': campaign.name,
                'status': campaign.status,
                'channels': campaign.channels,
                'leads_uploaded': leads_count,
                'message': message
            }
        except User.DoesNotExist:
            return {'success': False, 'error': 'User not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error creating campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def _process_leads_file(self, leads_file, campaign: Campaign, user_id: int) -> int:
        """
        Process uploaded leads file and associate leads with campaign
        
        Args:
            leads_file: Uploaded file object
            campaign: Campaign instance to associate leads with
            user_id: User ID
            
        Returns:
            int: Number of leads successfully processed
        """
        import pandas as pd
        from marketing_agent.models import Lead
        from django.contrib.auth.models import User
        
        user = User.objects.get(id=user_id)
        file_extension = leads_file.name.split('.')[-1].lower()
        
        if file_extension not in ['csv', 'xlsx', 'xls']:
            raise ValueError('Invalid file format. Please upload CSV, XLSX, or XLS files.')
        
        # Reset file pointer to beginning (in case it was read before)
        if hasattr(leads_file, 'seek'):
            leads_file.seek(0)
        
        # Read the file - handle Django uploaded files properly
        try:
            if file_extension == 'csv':
                # For CSV files, read content and parse
                import io
                content = leads_file.read()
                # Reset again after reading
                if hasattr(leads_file, 'seek'):
                    leads_file.seek(0)
                # Handle both text and bytes
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
                df = pd.read_csv(io.StringIO(content))
            else:
                # For Excel files, pandas can read from file object directly
                if hasattr(leads_file, 'seek'):
                    leads_file.seek(0)
                df = pd.read_excel(leads_file)
        except Exception as e:
            self.log_action("Error reading leads file", {
                "error": str(e),
                "file_name": leads_file.name,
                "file_extension": file_extension
            })
            import traceback
            print(f"Error reading leads file: {str(e)}")
            print(traceback.format_exc())
            raise ValueError(f'Error reading file: {str(e)}. Please ensure the file is a valid CSV or Excel file.')
        
        if df.empty:
            raise ValueError('File is empty')
        
        # Normalize column names (lowercase, strip spaces)
        df.columns = df.columns.str.lower().str.strip()
        
        # Required: email
        if 'email' not in df.columns:
            raise ValueError('Email column is required in the file')
        
        # Process leads
        created_count = 0
        
        for index, row in df.iterrows():
            try:
                email = str(row['email']).strip().lower()
                if not email or pd.isna(row['email']):
                    continue

                first_name = str(row.get('first_name', '')).strip() if pd.notna(row.get('first_name')) else ''
                last_name = str(row.get('last_name', '')).strip() if pd.notna(row.get('last_name')) else ''
                # First and last name are required — a row with neither is skipped,
                # same as a missing email, so personalization tokens are never
                # silently blank.
                if not first_name and not last_name:
                    continue

                # Get or create lead
                lead, created = Lead.objects.get_or_create(
                    email=email,
                    owner=user,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'phone': str(row.get('phone', '')).strip() if pd.notna(row.get('phone')) else '',
                        'company': str(row.get('company', '')).strip() if pd.notna(row.get('company')) else '',
                        'job_title': str(row.get('job_title', '')).strip() if pd.notna(row.get('job_title')) else '',
                        'source': str(row.get('source', 'campaign_upload')).strip() if pd.notna(row.get('source')) else 'campaign_upload',
                    }
                )
                
                # Update existing lead if new data provided
                if not created:
                    if pd.notna(row.get('first_name')):
                        lead.first_name = str(row.get('first_name', '')).strip()
                    if pd.notna(row.get('last_name')):
                        lead.last_name = str(row.get('last_name', '')).strip()
                    if pd.notna(row.get('phone')):
                        lead.phone = str(row.get('phone', '')).strip()
                    if pd.notna(row.get('company')):
                        lead.company = str(row.get('company', '')).strip()
                    if pd.notna(row.get('job_title')):
                        lead.job_title = str(row.get('job_title', '')).strip()
                    lead.save()
                
                # Associate lead with campaign
                campaign.leads.add(lead)
                created_count += 1
                
            except Exception as e:
                self.log_action("Error processing lead row", {"error": str(e), "row_index": index})
                import traceback
                print(f"Error processing lead row {index}: {str(e)}")
                print(traceback.format_exc())
                continue
        
        # Log final count for debugging
        final_count = campaign.leads.count()
        self.log_action("Leads file processing complete", {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "leads_processed": created_count,
            "total_leads_in_campaign": final_count
        })
        print(f"Processed {created_count} leads. Campaign now has {final_count} total leads.")
        
        return created_count
    
    def generate_leads(self, user_id: int, campaign_data: Dict, campaign_design: Optional[Dict] = None) -> Dict:
        """
        Generate authentic leads based on campaign requirements using AI
        
        Args:
            user_id (int): User ID
            campaign_data (Dict): Campaign requirements (target_audience, industry, location, etc.)
            campaign_design (Dict): Optional campaign design context
            
        Returns:
            Dict: Generated leads information
        """
        self.log_action("Generating leads", {"user_id": user_id})
        
        try:
            # Determine number of leads to generate (from target_leads or default)
            num_leads = campaign_data.get('target_leads') or 10
            
            # Generate leads in batches of 50 for better AI performance
            # For 100 leads, it will generate 2 batches of 50 each
            leads_list = []
            if num_leads <= 50:
                # Generate all at once for small requests (≤50 leads)
                prompt = self._build_lead_generation_prompt(campaign_data, num_leads, campaign_design)
                max_tokens = min(8000, 4000 + (num_leads * 50))
                leads_response = self._call_llm_for_reasoning(
                    prompt,
                    self.system_prompt,
                    temperature=0.7,
                    max_tokens=max_tokens
                )
                leads_list = self._parse_generated_leads(leads_response)
            else:
                # Generate in batches of 50 for larger requests
                # Example: 100 leads = 2 batches of 50, 150 leads = 3 batches of 50
                remaining = num_leads
                batch_num = 1
                max_batches = 20  # Safety limit (max 1000 leads = 20 batches)
                
                while remaining > 0 and batch_num <= max_batches:
                    batch_size = min(50, remaining)
                    prompt = self._build_lead_generation_prompt(campaign_data, batch_size, campaign_design)
                    
                    batch_response = self._call_llm_for_reasoning(
                        prompt,
                        self.system_prompt,
                        temperature=0.7,
                        max_tokens=4000
                    )
                    batch_leads = self._parse_generated_leads(batch_response)
                    leads_list.extend(batch_leads)
                    remaining -= len(batch_leads)
                    batch_num += 1
                    
                    # If batch generated fewer than requested, continue with remaining
                    if len(batch_leads) < batch_size:
                        remaining = max(0, remaining - (batch_size - len(batch_leads)))
            
            # Limit to requested number (in case we generated extra)
            leads_list = leads_list[:num_leads]
            
            return {
                'success': True,
                'count': len(leads_list),
                'leads': leads_list
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating leads", {"error": str(e)})
            return {
                'success': False,
                'count': 0,
                'leads': [],
                'error': str(e)
            }
    
    def generate_leads_for_campaign(self, user_id: int, campaign: Campaign, campaign_data: Optional[Dict] = None) -> Dict:
        """
        Generate leads and save them to database, associating with campaign
        
        Args:
            user_id (int): User ID
            campaign (Campaign): Campaign object
            campaign_data (Dict): Optional campaign data
            
        Returns:
            Dict: Results with count of leads created
        """
        try:
            user = User.objects.get(id=user_id)
            
            # Prepare campaign data for lead generation
            if not campaign_data:
                campaign_data = {
                    'name': campaign.name,
                    'description': campaign.description,
                    'target_audience': {
                        'age_range': campaign.age_range,
                        'location': campaign.location,
                        'industry': campaign.industry,
                        'interests': campaign.interests.split(',') if campaign.interests else [],
                        'company_size': campaign.company_size,
                        'language': campaign.language,
                    },
                    'target_leads': campaign.target_leads or 10,
                    'industry': campaign.industry,
                    'location': campaign.location,
                }
            
            # Generate leads using AI
            leads_result = self.generate_leads(user_id, campaign_data)
            
            if not leads_result.get('success') or not leads_result.get('leads'):
                return {'count': 0, 'leads': []}
            
            # Create Lead objects and associate with campaign
            created_count = 0
            leads_list = leads_result.get('leads', [])
            
            for lead_data in leads_list:
                try:
                    email = lead_data.get('email', '').strip().lower()
                    if not email:
                        continue
                    
                    # Create or get lead
                    lead, created = Lead.objects.get_or_create(
                        email=email,
                        owner=user,
                        defaults={
                            'first_name': lead_data.get('first_name', '').strip(),
                            'last_name': lead_data.get('last_name', '').strip(),
                            'phone': lead_data.get('phone', '').strip(),
                            'company': lead_data.get('company', '').strip(),
                            'job_title': lead_data.get('job_title', '').strip(),
                            'source': 'AI Generated',
                            'status': 'new',
                        }
                    )
                    
                    # Update fields if lead already existed
                    if not created:
                        if not lead.first_name and lead_data.get('first_name'):
                            lead.first_name = lead_data.get('first_name', '').strip()
                        if not lead.last_name and lead_data.get('last_name'):
                            lead.last_name = lead_data.get('last_name', '').strip()
                        if not lead.phone and lead_data.get('phone'):
                            lead.phone = lead_data.get('phone', '').strip()
                        if not lead.company and lead_data.get('company'):
                            lead.company = lead_data.get('company', '').strip()
                        if not lead.job_title and lead_data.get('job_title'):
                            lead.job_title = lead_data.get('job_title', '').strip()
                        lead.save()
                    
                    # Associate with campaign
                    if campaign not in lead.campaigns.all():
                        campaign.leads.add(lead)
                    
                    if created:
                        created_count += 1
                        
                except Exception as e:
                    self.log_action("Error creating lead", {"error": str(e), "lead_data": lead_data})
                    continue
            
            return {
                'count': created_count,
                'leads': leads_list[:created_count]
            }
            
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating leads for campaign", {"error": str(e)})
            return {'count': 0, 'leads': []}
    
    def _build_lead_generation_prompt(self, campaign_data: Dict, num_leads: int, campaign_design: Optional[Dict] = None) -> str:
        """Build prompt for AI lead generation"""
        target_audience = campaign_data.get('target_audience', {})
        industry = campaign_data.get('industry') or target_audience.get('industry', '')
        location = campaign_data.get('location') or target_audience.get('location', '')
        age_range = campaign_data.get('age_range') or target_audience.get('age_range', '')
        interests = campaign_data.get('interests') or target_audience.get('interests', [])
        company_size = campaign_data.get('company_size') or target_audience.get('company_size', '')
        
        if isinstance(interests, list):
            interests_str = ', '.join(str(i) for i in interests)
        else:
            interests_str = str(interests) if interests else ''
        
        prompt = f"""Generate {num_leads} authentic, realistic lead contacts for a marketing campaign.

CAMPAIGN REQUIREMENTS:
- Industry: {industry or 'General'}
- Location: {location or 'Any'}
- Age Range: {age_range or 'Any'}
- Interests: {interests_str or 'General'}
- Company Size: {company_size or 'Any'}
- Campaign Name: {campaign_data.get('name', 'Marketing Campaign')}
- Campaign Description: {campaign_data.get('description', '')}

IMPORTANT REQUIREMENTS:
1. Generate REALISTIC and AUTHENTIC lead information
2. Use proper email formats (e.g., firstname.lastname@company.com, name@domain.com)
3. Ensure emails are unique and professional
4. Include realistic first names, last names, phone numbers, companies, and job titles
5. Match leads to the industry and location specified
6. Make job titles relevant to the industry
7. Use appropriate company names for the industry
8. Ensure phone numbers are in valid formats (include country code if specified location requires it)
9. Generate diverse names (various ethnicities and backgrounds)
10. Make all information consistent and believable

OUTPUT FORMAT - Return ONLY a valid JSON array (no markdown, no explanations, just JSON):
[
    {{
        "email": "realistic.email@company.com",
        "first_name": "Realistic",
        "last_name": "Name",
        "phone": "+1-555-123-4567",
        "company": "Company Name Inc.",
        "job_title": "Relevant Job Title"
    }},
    ...
]

Generate exactly {num_leads} leads in this JSON format. Ensure all data is realistic and matches the campaign requirements."""
        
        return prompt
    
    def _parse_generated_leads(self, response_text: str) -> List[Dict]:
        """Parse leads from AI response"""
        leads_list = []
        
        try:
            # Try to extract JSON from response (may be wrapped in markdown code blocks)
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]
            
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Parse JSON
            leads_list = json.loads(response_text)
            
            # Validate and clean leads
            valid_leads = []
            for lead in leads_list:
                if isinstance(lead, dict) and lead.get('email'):
                    # Ensure email is lowercase and valid format
                    email = lead.get('email', '').strip().lower()
                    if '@' in email and '.' in email.split('@')[1]:
                        valid_leads.append({
                            'email': email,
                            'first_name': lead.get('first_name', '').strip(),
                            'last_name': lead.get('last_name', '').strip(),
                            'phone': lead.get('phone', '').strip(),
                            'company': lead.get('company', '').strip(),
                            'job_title': lead.get('job_title', '').strip(),
                        })
            
            return valid_leads
            
        except json.JSONDecodeError as e:
            self.log_action("Error parsing leads JSON", {"error": str(e), "response": response_text[:500]})
            # Try to extract emails from text if JSON parsing fails
            import re
            emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', response_text)
            # Return empty list if we can't parse properly
            return []
        except Exception as e:
            self.log_action("Error parsing leads", {"error": str(e)})
            return []
    
    def launch_campaign(self, campaign_id: int, user_id: int,
                      campaign_data: Optional[Dict] = None, context: Optional[Dict] = None, leads_file=None) -> Dict:
        """
        Launch a campaign across all specified channels
        
        Args:
            campaign_id (int): Campaign ID to launch
            user_id (int): User ID for access control
            campaign_data (Dict): Optional campaign data with start_date and end_date
            context (Dict): Launch context (scheduling, automation, etc.)
            
        Returns:
            Dict: Launch results and status
        """
        self.log_action("Launching campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Update campaign dates if provided in campaign_data
            if campaign_data:
                if 'start_date' in campaign_data and campaign_data['start_date']:
                    start_date = campaign_data['start_date']
                    if isinstance(start_date, str):
                        try:
                            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                            campaign.start_date = start_date
                        except (ValueError, TypeError):
                            pass
                    elif start_date:
                        campaign.start_date = start_date
                
                if 'end_date' in campaign_data and campaign_data['end_date']:
                    end_date = campaign_data['end_date']
                    if isinstance(end_date, str):
                        try:
                            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                            campaign.end_date = end_date
                        except (ValueError, TypeError):
                            pass
                    elif end_date:
                        campaign.end_date = end_date

            # Validate dates: no past dates when launching (use today as minimum)
            today = datetime.now().date()
            if campaign.start_date and campaign.start_date < today:
                return {
                    'success': False,
                    'error': 'Start date cannot be in the past. Please set start date to today or a future date.'
                }
            if campaign.end_date and campaign.end_date < today:
                return {
                    'success': False,
                    'error': 'End date cannot be in the past. Please set end date to today or a future date.'
                }
            # End date must be >= start date if both set
            if campaign.start_date and campaign.end_date and campaign.end_date < campaign.start_date:
                return {
                    'success': False,
                    'error': 'End date must be on or after start date. Please correct the dates and try again.'
                }

            # Check if campaign has at least one email sequence with steps (active or inactive; launching will reactivate them)
            from marketing_agent.models import EmailTemplate, EmailSequence
            all_sequences = EmailSequence.objects.filter(campaign=campaign)
            has_sequence_with_steps = False
            for seq in all_sequences:
                if seq.steps.exists():
                    has_sequence_with_steps = True
                    break
            if not has_sequence_with_steps:
                return {
                    'success': False,
                    'error': 'No email sequences found. Please create at least one email sequence with steps before launching. Go to Sequence Management to add sequences.'
                }

            # Check for at least one email template (active or inactive)
            email_templates = EmailTemplate.objects.filter(campaign=campaign)
            if not email_templates.exists():
                return {
                    'success': False,
                    'error': 'No email templates found. Please create at least one email template before launching the campaign.'
                }

            # Require an email account on the campaign (or every sequence overriding
            # one). Otherwise sends would silently fall back to whichever active
            # account the owner happens to have first — surprising behavior at best.
            campaign_has_account = bool(campaign.email_account_id)
            if not campaign_has_account:
                seqs_without_account = list(
                    EmailSequence.objects.filter(campaign=campaign, email_account__isnull=True)
                    .values_list('id', flat=True)
                )
                if seqs_without_account:
                    return {
                        'success': False,
                        'error': (
                            'No sending account is set for this campaign. Click '
                            '"Set sending account" on the campaign and pick the email '
                            'account you want to send from before launching.'
                        ),
                        'error_code': 'no_email_account',
                    }

            # Update campaign status and reactivate sequences (and templates) so launch works after a pause
            campaign.status = 'active'
            if not campaign.start_date:
                campaign.start_date = datetime.now().date()
            campaign.save()

            # Reactivate all email sequences for this campaign (they may have been inactive due to pause)
            EmailSequence.objects.filter(campaign=campaign).update(is_active=True)
            # Reactivate all email templates for this campaign
            EmailTemplate.objects.filter(campaign=campaign).update(is_active=True)
            
            # Create initial performance tracking entries
            self._initialize_performance_tracking(campaign)
            
            # Process leads file if provided
            leads_count = 0
            if leads_file:
                try:
                    leads_count = self._process_leads_file(leads_file, campaign, user_id)
                except Exception as e:
                    self.log_action("Error processing leads file during launch", {"error": str(e)})
                    # Don't fail campaign launch if leads upload fails
                    leads_count = 0
            
            # Note: Emails are ONLY sent through sequences, not individually
            # Sequence emails will be sent automatically by the send_sequence_emails management command
            # based on the delays configured in each sequence step
            
            message = f'Campaign "{campaign.name}" launched successfully'
            if leads_count > 0:
                message += f' with {leads_count} leads uploaded'
            message += f'\n\nEmails will be sent automatically through active email sequences.'
            message += f'\nCheck the "Email Sending Status" page to monitor email sending activity.'
            
            return {
                'success': True,
                'action': 'launch',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'status': campaign.status,
                'channels': campaign.channels,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'leads_uploaded': leads_count,
                'emails_sent': 0,  # Emails are sent through sequences, not during launch
                'emails_failed': 0,  # Emails are sent through sequences, not during launch
                'message': message
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error launching campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def manage_campaign(self, campaign_id: int, user_id: int,
                       context: Optional[Dict] = None) -> Dict:
        """
        Manage an active campaign - monitor, adjust, and coordinate
        
        Args:
            campaign_id (int): Campaign ID to manage
            user_id (int): User ID for access control
            context (Dict): Management context (actions, adjustments, etc.)
            
        Returns:
            Dict: Management results and recommendations
        """
        self.log_action("Managing campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Get current performance (no AI call)
            performance = self._get_campaign_performance(campaign)
            
            # Check timing and scheduling (no AI call)
            timing_check = self._check_campaign_timing(campaign)
            
            return {
                'success': True,
                'action': 'manage',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'current_status': campaign.status,
                'performance': performance,
                'timing_check': timing_check,
                'message': f'Campaign "{campaign.name}" management data retrieved successfully'
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error managing campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def optimize_campaign(self, campaign_id: int, user_id: int,
                         context: Optional[Dict] = None) -> Dict:
        """
        Optimize campaign performance based on current metrics
        
        Args:
            campaign_id (int): Campaign ID to optimize
            user_id (int): User ID for access control
            context (Dict): Optimization context (focus areas, constraints, etc.)
            
        Returns:
            Dict: Optimization recommendations and actions
        """
        self.log_action("Optimizing campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Get performance data
            performance = self._get_campaign_performance(campaign)
            
            # Generate optimization recommendations
            optimization_plan = self._generate_optimization_plan(campaign, performance, context)
            
            return {
                'success': True,
                'action': 'optimize',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'current_performance': performance,
                'optimization_plan': optimization_plan,
                'recommendations': optimization_plan.get('recommendations', []),
                'priority_actions': optimization_plan.get('priority_actions', [])
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error optimizing campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}

    def schedule_campaign(self, campaign_id: int, user_id: int,
                        schedule_data: Optional[Dict] = None) -> Dict:
        """
        Schedule campaign launch and channel-specific activities
        
        Args:
            campaign_id (int): Campaign ID to schedule
            user_id (int): User ID for access control
            schedule_data (Dict): Scheduling data (dates, times, channels, etc.)
            
        Returns:
            Dict: Schedule information and timeline
        """
        self.log_action("Scheduling campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Update campaign dates directly (no AI call)
            if schedule_data:
                if 'start_date' in schedule_data:
                    start_date = schedule_data['start_date']
                    if isinstance(start_date, str):
                        try:
                            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass
                    campaign.start_date = start_date
                if 'end_date' in schedule_data:
                    end_date = schedule_data['end_date']
                    if isinstance(end_date, str):
                        try:
                            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass
                    campaign.end_date = end_date
                campaign.status = 'scheduled'
                campaign.save()
            
            return {
                'success': True,
                'action': 'schedule',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'status': campaign.status,
                'message': f'Campaign "{campaign.name}" scheduled successfully'
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error scheduling campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    # Helper methods
    
    def _get_research_context(self, user_id: int) -> Dict:
        """Get relevant market research for campaign context"""
        research = MarketResearch.objects.filter(created_by_id=user_id).order_by('-created_at')[:5]
        return {
            'recent_research': [
                {
                    'type': r.research_type,
                    'topic': r.topic,
                    'insights': r.insights[:500] if r.insights else '',
                    'findings': r.findings
                }
                for r in research
            ]
        }
    
    def _build_design_context(self, campaign_data: Optional[Dict],
                             additional_context: Optional[Dict],
                             research_context: Dict) -> str:
        """Build comprehensive context for campaign design"""
        context = "CAMPAIGN DESIGN CONTEXT:\n\n"
        
        if campaign_data:
            context += "CAMPAIGN REQUIREMENTS:\n"
            context += f"- Name: {campaign_data.get('name', 'New Campaign')}\n"
            context += f"- Goals: {json.dumps(campaign_data.get('goals', {}), indent=2)}\n"
            context += f"- Target Audience: {json.dumps(campaign_data.get('target_audience', {}), indent=2)}\n"
            context += f"- Preferred Channels: {', '.join(campaign_data.get('channels', []))}\n"
            context += f"- Timeline: {campaign_data.get('timeline', 'Not specified')}\n\n"
        
        if research_context.get('recent_research'):
            context += "MARKET RESEARCH INSIGHTS:\n"
            for r in research_context['recent_research'][:3]:
                context += f"- {r['type']}: {r['topic']}\n"
                if r.get('insights'):
                    context += f"  Insights: {r['insights'][:200]}...\n"
            context += "\n"
        
        if additional_context:
            context += f"ADDITIONAL CONTEXT:\n{json.dumps(additional_context, indent=2)}\n\n"
        
        return context
    
    def _generate_campaign_design(self, context: str) -> str:
        """Generate email-only campaign design using AI — brief and to the point."""
        prompt = f"""Design an EMAIL-ONLY marketing campaign based on the following. Keep the design BRIEF and TO THE POINT: short bullet points, 1–2 lines per item, no long paragraphs.

{context}

Output a concise design with these sections (2–4 bullets per section max):

## CAMPAIGN STRATEGY
- Name, positioning, objectives, target audience, key message (one line each).

## EMAIL CAMPAIGN PLAN
- Email type and goals; content themes; send schedule and frequency; segmentation in 1–2 bullets each.

## MESSAGING FRAMEWORK
- Core message, brand voice, email tone (brief).

## TIMELINE & EXECUTION
- Pre-launch, launch, post-launch in 2–3 bullets; key milestones only.

## PERFORMANCE METRICS
- KPIs (open rate, CTR, conversion); success criteria (2–3 bullets).

## RECOMMENDATIONS
- 3–5 actionable bullets (content, segmentation, send time, A/B tests, deliverability).

RULES: EMAIL-ONLY. No social, paid ads, or other channels. Be concise—short bullets only. No long paragraphs or repetition. Do NOT use ** or * in the output; use plain text only (e.g. write "Content:" not "Content:**", and no bold/italic markdown)."""
        
        try:
            design = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.7,  # Creative but structured
                max_tokens=1800   # Keep design brief
            )
            return design
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating campaign design", {"error": str(e)})
            return f"Error generating campaign design: {str(e)}"
    
    def _parse_campaign_design(self, design_text: str, campaign_data: Optional[Dict]) -> Dict:
        """Parse AI-generated design into structured format"""
        return {
            'campaign_name': campaign_data.get('name', 'New Campaign') if campaign_data else 'New Campaign',
            'description': design_text[:500] if design_text else '',
            'raw_design': design_text,
            'channels': ['email'],  # Email-only campaigns
            'target_audience': campaign_data.get('target_audience', {}) if campaign_data else {},
            'goals': campaign_data.get('goals', {}) if campaign_data else {},
            'recommendations': self._extract_recommendations(design_text)
        }
    
    def _extract_recommendations(self, design_text: str) -> List[str]:
        """Extract key recommendations from design text"""
        recommendations = []
        lines = design_text.split('\n')
        in_recommendations_section = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Check if we're entering a recommendations section
            if any(marker in line_lower for marker in ['recommendation', 'suggestions', 'key takeaways', 'best practices', 'tips', 'guidelines']):
                in_recommendations_section = True
                continue
            
            # If in recommendations section, collect bullet points and numbered items
            if in_recommendations_section:
                # Look for bullet points, numbered items, or key recommendations
                if (line.strip().startswith(('-', '•', '*', '+', '✓', '→')) or 
                    (line.strip() and line.strip()[0].isdigit() and '.' in line.strip()[:3])):
                    cleaned = line.strip().lstrip('- •*+✓→0123456789. ').strip()
                    if cleaned and len(cleaned) > 15:  # Minimum length
                        recommendations.append(cleaned)
                # Stop if we hit another major section
                elif line.strip() and line.strip().startswith('##'):
                    break
            
            # Also look for standalone recommendation keywords in any line
            elif any(keyword in line_lower for keyword in ['recommend', 'suggest', 'should', 'consider', 'priority', 'important', 'best practice', 'tip']):
                cleaned = line.strip().lstrip('- •*+✓→0123456789. ').strip()
                if cleaned and len(cleaned) > 20:
                    # Avoid duplicates
                    if cleaned not in recommendations:
                        recommendations.append(cleaned)
        
        # If no recommendations found, generate some generic ones
        if not recommendations:
            recommendations = [
                "Focus on personalization and segmentation to improve email engagement",
                "Monitor open rates and click-through rates regularly to optimize performance",
                "A/B test subject lines and email content to improve conversion rates",
                "Ensure email content is mobile-responsive for better user experience",
                "Maintain a consistent sending schedule to build subscriber expectations"
            ]
        
        return recommendations[:10]  # Top 10 recommendations
    
    def _generate_launch_plan(self, campaign: Campaign, context: Optional[Dict]) -> Dict:
        """Generate launch plan for email campaign"""
        prompt = f"""Create a detailed launch plan for this EMAIL campaign:

Campaign: {campaign.name}
Type: Email Campaign
Goals: {json.dumps(campaign.goals, indent=2)}

Provide an email campaign launch plan that includes:
1. Pre-launch checklist for email campaign
2. Email launch sequence and timing
3. Email scheduling and automation setup
4. Email monitoring and tracking setup
5. Success criteria for email metrics

Focus ONLY on email marketing launch activities."""
        
        try:
            launch_plan_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'launch_sequence': self._extract_launch_sequence(launch_plan_text),
                'checklist': self._extract_checklist(launch_plan_text),
                'full_plan': launch_plan_text
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'error': str(e), 'full_plan': 'Error generating launch plan'}
    
    def _extract_launch_sequence(self, text: str) -> List[Dict]:
        """Extract launch sequence from text"""
        # Simple extraction - can be enhanced
        sequence = []
        lines = text.split('\n')
        current_channel = None
        for line in lines:
            line_lower = line.lower()
            if any(channel in line_lower for channel in ['email', 'social', 'paid', 'partnership']):
                current_channel = line.strip()
            elif 'step' in line_lower or 'day' in line_lower or 'phase' in line_lower:
                if current_channel:
                    sequence.append({
                        'channel': current_channel,
                        'step': line.strip()
                    })
        return sequence if sequence else [
            {'channel': 'All', 'step': 'Launch campaign across all channels'}
        ]
    
    def _extract_checklist(self, text: str) -> List[str]:
        """Extract checklist items from text"""
        checklist = []
        lines = text.split('\n')
        for line in lines:
            if any(marker in line for marker in ['-', '•', '*', '✓', '☐', '[]']):
                item = line.strip().lstrip('- •*✓☐[]').strip()
                if item and len(item) > 10:
                    checklist.append(item)
        return checklist[:15]  # Top 15 items
    
    def _initialize_performance_tracking(self, campaign: Campaign):
        """Sync CampaignPerformance table with live data from EmailSendHistory & Reply.

        Uses the same formulas as the frontend dashboard (_build_campaign_detail)
        so that the table always matches what the user sees.
        """
        sync_campaign_performance(campaign)
    
    def _get_campaign_performance(self, campaign: Campaign) -> Dict:
        """Get current campaign performance metrics"""
        metrics = CampaignPerformance.objects.filter(campaign=campaign)
        
        performance = {
            'total_impressions': 0,
            'total_clicks': 0,
            'total_conversions': 0,
            'total_engagement': 0,
            'by_channel': {}
        }
        
        for metric in metrics:
            value = float(metric.metric_value)
            metric_name = metric.metric_name
            channel = metric.channel or 'all'
            
            if metric_name == 'impressions':
                performance['total_impressions'] += value
            elif metric_name == 'clicks':
                performance['total_clicks'] += value
            elif metric_name == 'conversions':
                performance['total_conversions'] += value
            elif metric_name == 'engagement':
                performance['total_engagement'] += value
            
            if channel not in performance['by_channel']:
                performance['by_channel'][channel] = {}
            performance['by_channel'][channel][metric_name] = value
        
        # Calculate rates
        if performance['total_impressions'] > 0:
            performance['ctr'] = (performance['total_clicks'] / performance['total_impressions']) * 100
        else:
            performance['ctr'] = 0
        
        if performance['total_clicks'] > 0:
            performance['conversion_rate'] = (performance['total_conversions'] / performance['total_clicks']) * 100
        else:
            performance['conversion_rate'] = 0
        
        return performance
    
    def _generate_management_plan(self, campaign: Campaign, performance: Dict,
                                  context: Optional[Dict]) -> Dict:
        """Generate campaign management recommendations"""
        prompt = f"""Analyze this campaign and provide management recommendations:

Campaign: {campaign.name}
Status: {campaign.status}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Performance:
- Impressions: {performance.get('total_impressions', 0):,.0f}
- Clicks: {performance.get('total_clicks', 0):,.0f}
- Conversions: {performance.get('total_conversions', 0):,.0f}
- CTR: {performance.get('ctr', 0):.2f}%
- Conversion Rate: {performance.get('conversion_rate', 0):.2f}%

Provide:
1. Performance assessment
2. Channel-specific recommendations
3. Messaging consistency check
4. Timing and scheduling adjustments
5. Priority actions"""
        
        try:
            management_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'assessment': management_text,
                'recommendations': self._extract_recommendations(management_text),
                'priority_actions': self._extract_priority_actions(management_text)
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'error': str(e), 'recommendations': []}
    
    def _extract_priority_actions(self, text: str) -> List[str]:
        """Extract priority actions from text"""
        actions = []
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['priority', 'urgent', 'immediate', 'action']):
                if len(line.strip()) > 20:
                    actions.append(line.strip())
        return actions[:5]  # Top 5 priority actions
    
    def _check_messaging_consistency(self, campaign: Campaign) -> Dict:
        """Check messaging consistency across channels"""
        prompt = f"""Review this campaign for messaging consistency:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Goals: {json.dumps(campaign.goals, indent=2)}
Target Audience: {json.dumps(campaign.target_audience, indent=2)}

Assess:
1. Message consistency across channels
2. Brand voice alignment
3. Value proposition clarity
4. Call-to-action consistency
5. Recommendations for improvement"""
        
        try:
            consistency_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.4,
                max_tokens=1500
            )
            
            return {
                'assessment': consistency_text,
                'is_consistent': 'consistent' in consistency_text.lower() or 'aligned' in consistency_text.lower(),
                'recommendations': self._extract_recommendations(consistency_text)
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'error': str(e), 'is_consistent': True}
    
    def _check_campaign_timing(self, campaign: Campaign) -> Dict:
        """Check campaign timing and scheduling"""
        timing_issues = []
        
        if campaign.start_date and campaign.end_date:
            if campaign.end_date < campaign.start_date:
                timing_issues.append("End date is before start date")
            
            duration = (campaign.end_date - campaign.start_date).days
            if duration < 0:
                timing_issues.append("Invalid campaign duration")
        
        if campaign.status == 'active' and not campaign.start_date:
            timing_issues.append("Active campaign missing start date")
        
        return {
            'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
            'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
            'issues': timing_issues,
            'is_on_schedule': len(timing_issues) == 0
        }
    
    def _generate_optimization_plan(self, campaign: Campaign, performance: Dict,
                                    context: Optional[Dict]) -> Dict:
        """Generate optimization recommendations"""
        prompt = f"""Optimize this campaign based on current performance:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Current Performance:
- Impressions: {performance.get('total_impressions', 0):,.0f}
- Clicks: {performance.get('total_clicks', 0):,.0f}
- Conversions: {performance.get('total_conversions', 0):,.0f}
- CTR: {performance.get('ctr', 0):.2f}%
- Conversion Rate: {performance.get('conversion_rate', 0):.2f}%

Provide optimization recommendations:
1. Performance improvements by channel
2. Targeting optimizations
3. Creative and messaging improvements
4. Timing and scheduling optimizations
5. A/B testing opportunities
6. Priority actions with expected impact"""
        
        try:
            optimization_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'optimization_plan': optimization_text,
                'recommendations': self._extract_recommendations(optimization_text),
                'priority_actions': self._extract_priority_actions(optimization_text)
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'error': str(e), 'recommendations': []}
    
    def _generate_campaign_schedule(self, campaign: Campaign,
                                   schedule_data: Optional[Dict]) -> Dict:
        """Generate campaign schedule"""
        prompt = f"""Create a detailed schedule for this campaign:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Start Date: {schedule_data.get('start_date') if schedule_data else 'Not set'}
End Date: {schedule_data.get('end_date') if schedule_data else 'Not set'}

Create a schedule that includes:
1. Pre-launch activities (by date)
2. Channel launch sequence and timing
3. Ongoing activities and frequency
4. Key milestones and deadlines
5. Post-launch activities
6. Reporting and review dates

Ensure all channels are properly coordinated and timed."""
        
        try:
            schedule_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'schedule': schedule_text,
                'timeline': self._extract_timeline(schedule_text),
                'milestones': self._extract_milestones(schedule_text)
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'error': str(e), 'schedule': 'Error generating schedule'}
    
    def _extract_timeline(self, text: str) -> List[Dict]:
        """Extract timeline from schedule text"""
        timeline = []
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['day', 'week', 'date', 'launch', 'phase']):
                if len(line.strip()) > 15:
                    timeline.append({'event': line.strip()})
        return timeline[:10]  # Top 10 timeline items
    
    def _extract_milestones(self, text: str) -> List[str]:
        """Extract milestones from schedule text"""
        milestones = []
        lines = text.split('\n')
        for line in lines:
            if 'milestone' in line.lower() or 'deadline' in line.lower():
                if len(line.strip()) > 15:
                    milestones.append(line.strip())
        return milestones[:5]  # Top 5 milestones

