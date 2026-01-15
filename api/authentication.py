"""
Custom authentication for Company Users
"""
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from core.models import CompanyUser, CompanyUserToken, Company


class CompanyUserTokenAuthentication(authentication.BaseAuthentication):
    """
    Token-based authentication for CompanyUser.
    Clients should authenticate by passing the token key in the "Authorization"
    HTTP header, prepended with the string "Token " or "Bearer ".
    For example: Authorization: Token 401f7ac837da42b97f613d789819ff93537bee6a
    """
    
    keyword = 'Token'
    
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header:
            return None
        
        # Support both "Token" and "Bearer" keywords
        keywords = ['Token', 'Bearer']
        token_key = None
        
        for keyword in keywords:
            if auth_header.startswith(f'{keyword} '):
                token_key = auth_header[len(f'{keyword} '):].strip()
                break
        
        if not token_key:
            return None
        
        try:
            token = CompanyUserToken.objects.select_related('company_user').get(key=token_key)
            company_user = token.company_user
            
            if not company_user.is_active:
                raise AuthenticationFailed('Company user account is inactive')
            
            # Return a tuple (user, auth) where user is the company_user
            return (company_user, token)
        except CompanyUserToken.DoesNotExist:
            raise AuthenticationFailed('Invalid token')
        except Exception as e:
            raise AuthenticationFailed(f'Authentication failed: {str(e)}')


# Keep old authentication class for backward compatibility (if needed)
class CompanyUserAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication for CompanyUser using email and company_id (deprecated - use CompanyUserTokenAuthentication)
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

