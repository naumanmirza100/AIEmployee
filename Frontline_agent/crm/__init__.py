"""CRM adapter layer. Each sub-module implements the same small push interface
so the Celery sync task does not need to know which provider it's talking to.

Today: HubSpot (private-app access token).
Future: Salesforce (OAuth), Pipedrive, Zoho.
"""
