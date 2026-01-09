"""
Custom authentication for Company Users
"""
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from core.models import CompanyUser, Company
from django.contrib.auth.hashers import check_password


class CompanyUserAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication for CompanyUser using email and company_id
    """
    
    def authenticate(self, request):
        # Get company user credentials from headers
        company_user_id = request.META.get('HTTP_X_COMPANY_USER_ID')
        company_id = request.META.get('HTTP_X_COMPANY_ID')
        email = request.META.get('HTTP_X_COMPANY_EMAIL')
        
        # Alternative: Get from Authorization header as Bearer token
        # Format: "CompanyUser <company_user_id>:<company_id>"
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('CompanyUser '):
            try:
                token = auth_header.replace('CompanyUser ', '')
                parts = token.split(':')
                if len(parts) == 2:
                    company_user_id = parts[0]
                    company_id = parts[1]
            except:
                pass
        
        if not company_user_id or not company_id:
            return None
        
        try:
            company = Company.objects.get(id=company_id)
            company_user = CompanyUser.objects.get(id=company_user_id, company=company)
            
            if not company_user.is_active:
                raise AuthenticationFailed('Company user account is inactive')
            
            # Return a tuple (user, auth) where user is the company_user
            # We'll use a wrapper to make it work with the existing code
            return (company_user, None)
        except (CompanyUser.DoesNotExist, Company.DoesNotExist):
            raise AuthenticationFailed('Invalid company user credentials')
        except Exception as e:
            raise AuthenticationFailed(f'Authentication failed: {str(e)}')

