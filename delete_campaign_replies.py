"""
Script to delete all reply data for a specific campaign.
Usage: python delete_campaign_replies.py
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Campaign, Reply, CampaignContact

def delete_campaign_replies(campaign_name):
    """Delete all reply data for a campaign"""
    try:
        # Find the campaign
        campaign = Campaign.objects.get(name=campaign_name)
        print(f"Found campaign: {campaign.name} (ID: {campaign.id})")
        
        # Delete all replies for this campaign
        replies_count = Reply.objects.filter(campaign=campaign).count()
        Reply.objects.filter(campaign=campaign).delete()
        print(f"Deleted {replies_count} reply records")
        
        # Reset campaign contacts reply status
        contacts = CampaignContact.objects.filter(campaign=campaign, replied=True)
        contacts_count = contacts.count()
        contacts.update(
            replied=False,
            replied_at=None,
            reply_subject='',
            reply_content='',
            reply_interest_level='',
            reply_analysis='',
            sub_sequence=None
        )
        print(f"Reset reply status for {contacts_count} campaign contacts")
        
        print(f"\n✅ Successfully deleted all reply data for campaign '{campaign_name}'")
        
    except Campaign.DoesNotExist:
        print(f"❌ Error: Campaign '{campaign_name}' not found")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == '__main__':
    campaign_name = "Email Sending2"
    print(f"Deleting all reply data for campaign: {campaign_name}\n")
    confirm = input(f"Are you sure you want to delete all replies for '{campaign_name}'? (yes/no): ")
    
    if confirm.lower() == 'yes':
        delete_campaign_replies(campaign_name)
    else:
        print("Operation cancelled.")


