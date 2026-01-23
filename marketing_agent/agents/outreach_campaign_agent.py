"""
Outreach & Campaign Agent
Designs, launches, and manages multi-channel marketing campaigns across email, 
social, paid ads, and partnerships, ensuring consistent messaging and timely execution.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, Lead
from django.contrib.auth.models import User
from datetime import datetime, timedelta
import json


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
                'error': f'Unknown action: {action}. Supported actions: design, launch, manage, optimize, schedule, create_multi_channel'
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
            
            # Create campaign in database with all fields
            campaign = Campaign.objects.create(
                name=campaign_data.get('name', 'New Campaign'),
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
                
                # Get or create lead
                lead, created = Lead.objects.get_or_create(
                    email=email,
                    owner=user,
                    defaults={
                        'first_name': str(row.get('first_name', '')).strip() if pd.notna(row.get('first_name')) else '',
                        'last_name': str(row.get('last_name', '')).strip() if pd.notna(row.get('last_name')) else '',
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
            
            # Check if email templates exist
            from marketing_agent.models import EmailTemplate
            email_templates = EmailTemplate.objects.filter(campaign=campaign, is_active=True)
            if not email_templates.exists():
                return {
                    'success': False,
                    'error': 'No active email templates found. Please create at least one email template before launching the campaign.'
                }
            
            # Update campaign status directly (no AI call)
            campaign.status = 'active'
            if not campaign.start_date:
                campaign.start_date = datetime.now().date()
            campaign.save()
            
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
        """Generate email-only campaign design using AI"""
        prompt = f"""Design a comprehensive EMAIL-ONLY marketing campaign based on the following requirements:

{context}

Create a detailed EMAIL campaign design that includes:

## CAMPAIGN STRATEGY
- Campaign name and positioning
- Primary objectives and KPIs
- Target audience personas
- Key messaging and value propositions

## EMAIL CAMPAIGN PLAN

### Email Campaign Strategy
- Email campaign type and goals
- Overall email marketing approach

### Content Themes and Messaging
- Email content themes
- Key messages and value propositions
- Email copy guidelines

### Send Schedule and Frequency
- Email sending schedule
- Frequency recommendations
- Best sending times

### Segmentation Approach
- Audience segmentation strategy
- Personalization approach
- List management

### Email Types and Sequences
- Welcome emails
- Promotional emails
- Newsletter emails
- Transactional emails
- Re-engagement campaigns

## MESSAGING FRAMEWORK
- Core messaging framework
- Brand voice guidelines
- Email-specific messaging style
- Consistency guidelines

## TIMELINE & EXECUTION
- Campaign timeline (pre-launch, launch, post-launch)
- Email sequence timing
- Key milestones
- Dependencies

## RESOURCE ALLOCATION
- Email campaign resources
- Cost estimates for email tools/services

## PERFORMANCE METRICS
- Email KPIs (open rate, click-through rate, conversion rate, etc.)
- Tracking and measurement plan
- Success criteria

## RECOMMENDATIONS
Provide 5-10 specific, actionable recommendations for:
- Email content optimization
- Segmentation strategies
- Send timing and frequency
- Personalization approaches
- A/B testing opportunities
- Best practices for email deliverability and engagement

Format recommendations as clear, actionable bullet points.

IMPORTANT: This is an EMAIL-ONLY campaign. Do NOT include social media, paid advertising, 
partnerships, or any other channels. Focus ONLY on email marketing strategy and execution.

Provide a comprehensive, actionable email campaign design with clear timelines, 
messaging guidelines, performance metrics, and specific recommendations."""
        
        try:
            design = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.7,  # Creative but structured
                max_tokens=3000
            )
            return design
        except Exception as e:
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
        """Initialize performance tracking metrics for campaign"""
        # Create placeholder metrics for tracking
        metrics = ['impressions', 'clicks', 'conversions', 'engagement']
        for metric in metrics:
            CampaignPerformance.objects.get_or_create(
                campaign=campaign,
                metric_name=metric,
                date=datetime.now().date(),
                channel='all',
                defaults={'metric_value': 0}
            )
    
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

