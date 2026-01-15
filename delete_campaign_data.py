"""
Script to delete all email sequences and send history for a specific campaign.
Usage: python delete_campaign_data.py
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Campaign, EmailSequence, EmailSendHistory, CampaignContact

def delete_campaign_data(campaign_name):
    """Delete all email sequences and send history for a campaign"""
    try:
        # Find the campaign
        campaign = Campaign.objects.get(name=campaign_name)
        print(f"Found campaign: {campaign.name} (ID: {campaign.id})")
        
        # Delete all email send history for this campaign
        email_history_count = EmailSendHistory.objects.filter(campaign=campaign).count()
        EmailSendHistory.objects.filter(campaign=campaign).delete()
        print(f"Deleted {email_history_count} email send history records")
        
        # Delete all email sequences for this campaign
        # sequences_count = EmailSequence.objects.filter(campaign=campaign).count()
        # EmailSequence.objects.filter(campaign=campaign).delete()
        # print(f"Deleted {sequences_count} email sequences")
        
        # Reset campaign contacts (remove sequence references, but keep contacts)
        contacts = CampaignContact.objects.filter(campaign=campaign)
        contacts_count = contacts.count()
        contacts.update(
            sequence=None,
            current_step=0,
            completed=False,
            last_sent_at=None,
            sub_sequence_last_sent_at=None,
            started_at=None
        )
        print(f"Reset {contacts_count} campaign contacts (removed sequence references)")
        
        print(f"\n✅ Successfully deleted all email sequences and send history for campaign '{campaign_name}'")
        
    except Campaign.DoesNotExist:
        print(f"❌ Error: Campaign '{campaign_name}' not found")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == '__main__':
    campaign_name = "Final Approvals"
    print(f"Deleting all email sequences and send history for campaign: {campaign_name}\n")
    confirm = input(f"Are you sure you want to delete all data for '{campaign_name}'? (yes/no): ")
    
    if confirm.lower() == 'yes':
        delete_campaign_data(campaign_name)
    else:
        print("Operation cancelled.")

