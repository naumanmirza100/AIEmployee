from django.contrib import admin
from .models import SDRIcpProfile, SDRLead, SDRLeadResearchJob

@admin.register(SDRIcpProfile)
class SDRIcpProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'company_user', 'name', 'is_active', 'created_at']
    list_filter = ['is_active']

@admin.register(SDRLead)
class SDRLeadAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'company_name', 'job_title', 'score', 'temperature', 'status', 'source', 'created_at']
    list_filter = ['temperature', 'status', 'source']
    search_fields = ['full_name', 'email', 'company_name']

@admin.register(SDRLeadResearchJob)
class SDRLeadResearchJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'company_user', 'status', 'leads_created', 'leads_qualified', 'source', 'created_at']
    list_filter = ['status', 'source']
