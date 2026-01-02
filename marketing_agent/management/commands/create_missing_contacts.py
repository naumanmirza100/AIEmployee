"""
Django management command to create missing CampaignContact records.

This command finds all campaigns with leads that don't have CampaignContact records
and creates them. This is useful for campaigns that were created before the
automation system was implemented.

Usage:
    python manage.py create_missing_contacts
    python manage.py create_missing_contacts --campaign-id 3  # For specific campaign
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from marketing_agent.models import Campaign, Lead, CampaignContact, EmailSequence


class Command(BaseCommand):
    help = 'Create missing CampaignContact records for existing campaign leads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-id',
            type=int,
            help='Process only a specific campaign ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(self.style.SUCCESS('Finding campaigns with missing CampaignContact records...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No records will be created'))
        
        # Get campaigns to process
        if campaign_id:
            campaigns = Campaign.objects.filter(id=campaign_id)
            if not campaigns.exists():
                self.stdout.write(self.style.ERROR(f'Campaign with ID {campaign_id} not found'))
                return
        else:
            campaigns = Campaign.objects.all()
        
        total_created = 0
        total_existing = 0
        total_campaigns = 0
        
        for campaign in campaigns:
            total_campaigns += 1
            self.stdout.write(f'\nProcessing Campaign: {campaign.name} (ID: {campaign.id})')
            
            # Get all leads for this campaign
            leads = campaign.leads.all()
            lead_count = leads.count()
            
            if lead_count == 0:
                self.stdout.write(self.style.WARNING(f'  No leads found in campaign'))
                continue
            
            self.stdout.write(f'  Found {lead_count} lead(s)')
            
            # Get active sequences for this campaign
            active_sequence = campaign.email_sequences.filter(is_active=True).first()
            
            created_count = 0
            existing_count = 0
            
            for lead in leads:
                # Check if CampaignContact already exists
                contact_exists = CampaignContact.objects.filter(
                    campaign=campaign,
                    lead=lead
                ).exists()
                
                if contact_exists:
                    existing_count += 1
                    self.stdout.write(f'    [OK] Contact exists: {lead.email}')
                else:
                    if not dry_run:
                        # Create CampaignContact
                        contact = CampaignContact.objects.create(
                            campaign=campaign,
                            lead=lead,
                            sequence=active_sequence,
                            current_step=0,
                        )
                        created_count += 1
                        total_created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'    [CREATED] Contact: {lead.email}')
                        )
                    else:
                        created_count += 1
                        total_created += 1
                        self.stdout.write(
                            self.style.WARNING(f'    [DRY RUN] Would create contact: {lead.email}')
                        )
            
            total_existing += existing_count
            
            if created_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'  Created {created_count} contact(s) for this campaign')
                )
            else:
                self.stdout.write(f'  All contacts already exist')
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"="*60}\n'
                f'SUMMARY:\n'
                f'  Campaigns processed: {total_campaigns}\n'
                f'  Contacts created: {total_created}\n'
                f'  Contacts already existing: {total_existing}\n'
                f'{"="*60}'
            )
        )
        
        if total_created > 0 and not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSuccessfully created {total_created} CampaignContact record(s)!'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    'Now run: python manage.py send_sequence_emails'
                )
            )

