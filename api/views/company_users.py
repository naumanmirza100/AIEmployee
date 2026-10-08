"""
Company User Management API Views
Allows company users to create and manage regular users (auth_user table)
"""

import re
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyAdmin, IsCompanyUserOnly
from core.models import CompanyUser, UserProfile, Company
from api.serializers.company_users import CompanyUserManagementSerializer, UserListSerializer


def _company_employee_logins(company_user):
    """Every employee login of the caller's company, switched off or not.

    The Users tab used to list only the logins this dashboard login had created
    itself, admins included, while every agent's people lists were
    company-wide: a colleague's employees showed up in HR and Recruitment but
    could not be seen, edited or switched off here by anyone else.
    The dashboard logins' own user records are not employees and stay out.
    """
    company = company_user.company
    if company is None:
        return User.objects.filter(profile__created_by_company_user=company_user)
    own_records = CompanyUser.objects.filter(company=company, login_user__isnull=False).values('login_user_id')
    return (User.objects
            .filter(Q(profile__company=company) | Q(profile__created_by_company_user__company=company))
            .exclude(id__in=own_records)
            .exclude(is_staff=True).exclude(is_superuser=True)
            .distinct())


def _refusal(user, company_user, *, changing):
    """None when the caller may see (or, with `changing`, change) this login;
    otherwise the response to send. Anyone in the company may see one. Its
    creator may change it, and so may an owner or admin; without that second
    rule widening the list would let any login reset any employee's password.
    """
    if not _company_employee_logins(company_user).filter(pk=user.pk).exists():
        return Response({
            'status': 'error',
            'message': 'User not found or access denied'
        }, status=status.HTTP_404_NOT_FOUND)
    if not changing:
        return None
    created_it = user.profile.created_by_company_user_id == company_user.id
    if created_it or company_user.role in IsCompanyAdmin.ADMIN_ROLES:
        return None
    return Response({
        'status': 'error',
        'message': 'Only an owner or admin of your company can change a login that someone else created.'
    }, status=status.HTTP_403_FORBIDDEN)


def _hr_record_of(user, company):
    """The HR record of an employee login. Every login has one, whether or not
    the company has bought HR; one from before that rule is made here."""
    from hr_agent.models import Employee
    record = Employee.objects.filter(user=user, company=company).first()
    if record is None and company is not None:
        from hr_agent.signals import _ensure_employee_for_user
        record = _ensure_employee_for_user(user, company)
    return record


def _audit(company_user, action, record, **after):
    from api.views.hr_agent import _write_audit_log
    _write_audit_log(company_user, company_user.company, action, 'employee', record.id,
                     after={**after, 'from': 'users_tab'})


def _hr_record_for_new_login(company_user, data):
    """(the HR record this login is being made for, a refusal): at most one is set.

    "Create login" on a person's HR record sends that record's id. Without it,
    a login made at a different address from the record's became a second HR
    record for the same person, and their onboarding started again.
    """
    raw = data.get('employee_id', data.get('employeeId'))
    if raw in (None, ''):
        return None, None
    from api.views.hr_agent import _is_hr_admin
    from hr_agent.models import Employee

    def refuse(message, code):
        return None, Response({'status': 'error', 'message': message}, status=code)

    if not _is_hr_admin(company_user):
        return refuse("Only an HR admin can create a login from a person's HR record.", status.HTTP_403_FORBIDDEN)
    record = (Employee.objects.filter(pk=raw, company=company_user.company).first()
              if str(raw).isdigit() else None)
    if record is None:
        return refuse('HR record not found.', status.HTTP_404_NOT_FOUND)
    if record.user_id:
        return refuse(f'{record.full_name} already has a login.', status.HTTP_400_BAD_REQUEST)
    if record.anonymized_at or record.employment_status == 'offboarded':
        return refuse(f'{record.full_name} has left. Reactivate their record before giving them a login.',
                      status.HTTP_400_BAD_REQUEST)
    return record, None


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_user(request):
    """
    Create a new user (auth_user) by company user
    POST /api/company/users/create

    With `employee_id`, the login is made for that HR record: the record is
    given the login and takes its address, so there is still one record.
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        data = request.data

        # Validate required fields
        email = (data.get('email') or '').strip().lower()
        password = data.get('password', '')
        username = data.get('username') or email.split('@')[0]  # Use email prefix as username if not provided
        role = data.get('role', 'team_member')
        full_name = (data.get('fullName') or data.get('full_name', '')).strip()
        phone_number = (data.get('phoneNumber') or data.get('phone_number', '')).strip()

        record, refusal = _hr_record_for_new_login(company_user, data)
        if refusal is not None:
            return refusal
        if record is not None:
            # HR already holds their name and number: neither is typed again, or checked again.
            full_name = record.full_name
            typed_phone, phone_number = phone_number, phone_number or (record.phone or '').strip()

        if not email or not password:
            return Response({
                'status': 'error',
                'message': 'Email and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not full_name:
            return Response({
                'status': 'error',
                'message': 'Full name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Full name: no digits allowed, only letters/spaces/dots/hyphens/apostrophes
        if record is None and re.search(r'[0-9]', full_name):
            return Response({
                'status': 'error',
                'message': 'Full name must not contain numbers.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if record is None and not re.match(r"^[a-zA-Z\s.'\-]+$", full_name):
            return Response({
                'status': 'error',
                'message': "Full name can only contain letters, spaces, dots, hyphens, and apostrophes."
            }, status=status.HTTP_400_BAD_REQUEST)
        alpha_count = sum(1 for c in full_name if c.isalpha())
        if record is None and alpha_count < 2:
            return Response({
                'status': 'error',
                'message': 'Full name must contain at least 2 alphabetic characters.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not phone_number and record is None:
            return Response({
                'status': 'error',
                'message': 'Phone number is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Phone number validation - at least 7 digits, allows +, spaces, hyphens, parentheses
        phone_digits = sum(1 for c in phone_number if c.isdigit())
        to_check = phone_number if record is None else typed_phone
        if to_check and (not re.match(r'^[+]?[\d\s\-()]{7,20}$', phone_number) or phone_digits < 7):
            return Response({
                'status': 'error',
                'message': 'Enter a valid phone number (at least 7 digits, e.g., +1234567890).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Strict email validation
        email_regex = r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return Response({
                'status': 'error',
                'message': 'Enter a valid email address (e.g., user@example.com).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Password strength validation: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
        if len(password) < 8:
            return Response({
                'status': 'error',
                'message': 'Password must be at least 8 characters long.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[A-Z]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one uppercase letter.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[a-z]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one lowercase letter.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[0-9]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one digit.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`]', password):
            return Response({
                'status': 'error',
                'message': 'Password must contain at least one special character (!@#$%^&* etc.).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Location validation (if provided)
        location = (data.get('location') or '').strip()
        if location:
            loc_alpha = sum(1 for c in location if c.isalpha())
            if loc_alpha < 2:
                return Response({
                    'status': 'error',
                    'message': 'Location must contain at least 2 alphabetic characters.'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Bio validation (if provided)
        bio = (data.get('bio') or '').strip()
        if bio:
            bio_alnum = sum(1 for c in bio if c.isalnum())
            if bio_alnum < 10:
                return Response({
                    'status': 'error',
                    'message': 'Bio must contain at least 10 alphanumeric characters.'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Validate role
        valid_roles = [choice[0] for choice in UserProfile.ROLE_CHOICES]
        if role not in valid_roles:
            return Response({
                'status': 'error',
                'message': f'Invalid role. Must be one of: {", ".join(valid_roles)}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if user already exists in auth_user
        if User.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'User with this email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if email is already used by a company
        from core.models import Company as CompanyModel
        if CompanyModel.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'This email is already registered as a company email'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if email is already used by a company user
        if CompanyUser.objects.filter(email__iexact=email).exists():
            return Response({
                'status': 'error',
                'message': 'This email is already registered as a company user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if record is not None:
            # Work email is unique in a company, and this record is about to take the login's.
            from hr_agent.models import Employee
            clash = (Employee.objects.filter(company=record.company, work_email__iexact=email)
                     .exclude(pk=record.pk).first())
            if clash is not None:
                return Response({
                    'status': 'error',
                    'message': f'Another HR record already uses {email}: {clash.full_name}. '
                               'Give the login a different address, or use that record.',
                }, status=status.HTTP_400_BAD_REQUEST)

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            # Append company user ID to make it unique
            username = f"{username}_{company_user.id}"
        
        # Get company from company_user
        company = company_user.company
        
        # Split full_name into first_name and last_name
        name_parts = full_name.split(maxsplit=1) if full_name else []
        first_name = name_parts[0] if len(name_parts) > 0 else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Create Django User
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=False,
            is_superuser=False
        )
        if record is not None:
            # Give the record its login before the profile below gets its company:
            # saving that profile is what makes HR look for the person's record.
            # It then finds this one instead of making a second, and brings the
            # record's work email into step with the login's.
            from hr_agent.models import Employee
            Employee.objects.filter(pk=record.pk).update(user=user)
        
        # Create or update UserProfile
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': role,
                'company': company,
                'created_by_company_user': company_user,
                'company_name': company.name if company else None,
                'phone_number': phone_number or None,
                'bio': data.get('bio'),
                'location': data.get('location'),
            }
        )
        
        # If profile already existed, update it
        if not created:
            profile.role = role
            profile.company = company
            profile.created_by_company_user = company_user
            if phone_number:
                profile.phone_number = phone_number
            if data.get('bio'):
                profile.bio = data.get('bio')
            if data.get('location'):
                profile.location = data.get('location')
            profile.save()
        
        # Generate token for the new user (optional - for auto-login)
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'message': 'User created successfully',
            'data': {
                'user': serializer.data,
                'token': token.key,  # Return token for potential auto-login
                'employee_id': record.id if record is not None else None,
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'status': 'error',
            'message': 'Failed to create user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_users(request):
    """
    List all users created by the company user
    GET /api/company/users
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        # Everyone's employee logins, not only the ones this login created.
        users = (_company_employee_logins(company_user)
                 .select_related('profile').prefetch_related('profile__created_by_company_user')
                 .order_by('-date_joined'))
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        
        total = users.count()
        total_pages = (total + limit - 1) // limit if limit > 0 else 1
        
        # Apply pagination
        start = (page - 1) * limit
        end = start + limit
        paginated_users = users[start:end]
        
        serializer = UserListSerializer(paginated_users, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in list_users: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'status': 'error',
            'message': 'Failed to fetch users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_user(request, userId):
    """
    Get user details
    GET /api/company/users/{userId}
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # Get user and verify it was created by this company user
        user = get_object_or_404(User, id=userId)
        
        # Check if user was created by this company user
        refused = _refusal(user, company_user, changing=False)
        if refused:
            return refused
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_user(request, userId):
    """
    Update user
    PUT/PATCH /api/company/users/{userId}
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        
        # Get user and verify it was created by this company user
        user = get_object_or_404(User, id=userId)
        
        refused = _refusal(user, company_user, changing=True)
        if refused:
            return refused
        
        data = request.data
        
        # Update user fields
        if 'email' in data:
            # Check if email is already taken by another user
            if User.objects.filter(email=data['email']).exclude(id=user.id).exists():
                return Response({
                    'status': 'error',
                    'message': 'Email already taken by another user'
                }, status=status.HTTP_400_BAD_REQUEST)
            user.email = data['email']

        if 'username' in data:
            new_username = (data.get('username') or '').strip()
            if not new_username:
                return Response({
                    'status': 'error',
                    'message': 'Username cannot be empty.',
                }, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                return Response({
                    'status': 'error',
                    'message': 'Username already taken by another user.',
                }, status=status.HTTP_400_BAD_REQUEST)
            user.username = new_username

        if 'fullName' in data or 'full_name' in data:
            full_name = data.get('fullName') or data.get('full_name', '')
            name_parts = full_name.split(maxsplit=1) if full_name else []
            user.first_name = name_parts[0] if len(name_parts) > 0 else ''
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if 'password' in data:
            user.set_password(data['password'])
        
        user.save()
        
        # Update profile
        profile = user.profile
        if 'role' in data:
            valid_roles = [choice[0] for choice in UserProfile.ROLE_CHOICES]
            if data['role'] in valid_roles:
                profile.role = data['role']
        
        if 'phoneNumber' in data or 'phone_number' in data:
            profile.phone_number = data.get('phoneNumber') or data.get('phone_number')
        
        if 'bio' in data:
            profile.bio = data['bio']
        
        if 'location' in data:
            profile.location = data['location']
        
        profile.save()
        
        serializer = UserListSerializer(user)
        
        return Response({
            'status': 'success',
            'message': 'User updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_user(request, userId):
    """
    Deactivate a user: the person has left.
    DELETE /api/company/users/{userId}

    This and HR's Deactivate used to be two switches that knew nothing of each
    other. This one switched the login off, moved no work and left the HR
    record active; HR's marked the record offboarded. Now this marks the
    record offboarded, and saving that is what switches the person's logins
    off (hr_agent.access), so either button does the same thing. The answer
    says which record, so the screen can offer to hand their work over.
    """
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user

        user = get_object_or_404(User, id=userId)

        refused = _refusal(user, company_user, changing=True)
        if refused:
            return refused

        from hr_agent import access as hr_access
        from hr_agent.handover import dashboard_login
        record = _hr_record_of(user, company_user.company)
        own_login = dashboard_login(record) if record is not None else None
        if own_login is not None and own_login.pk == company_user.pk:
            return Response({
                'status': 'error',
                'message': "This is your own employee login: deactivating it would switch off the login you "
                           "are using. Ask another admin to do it.",
            }, status=status.HTTP_400_BAD_REQUEST)
        if record is not None and record.employment_status != 'offboarded':
            previous = record.employment_status
            record.employment_status = 'offboarded'
            record.save(update_fields=['employment_status', 'updated_at'])
            record.refresh_from_db(fields=['access_ended'])
            _audit(company_user, 'employee.deactivate', record, employment_status='offboarded',
                   previous_status=previous, access=hr_access.summary(record))
        # With no record to speak for it, or one already offboarded, the login is switched off directly.
        if User.objects.filter(pk=user.pk, is_active=True).update(is_active=False):
            from rest_framework.authtoken.models import Token
            Token.objects.filter(user_id=user.pk).delete()

        return Response({
            'status': 'success',
            'message': 'User deactivated successfully',
            'data': {
                'employee_id': record.id if record is not None else None,
                'access': hr_access.summary(record) if record is not None else None,
            },
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to delete user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def reactivate_user(request, userId):
    """
    Reactivate a deactivated user
    POST /api/company/users/{userId}/reactivate
    """
    try:
        company_user = request.user

        user = get_object_or_404(User, id=userId)

        refused = _refusal(user, company_user, changing=True)
        if refused:
            return refused

        if user.is_active:
            return Response({
                'status': 'error',
                'message': 'User is already active'
            }, status=status.HTTP_400_BAD_REQUEST)

        # The other half of Deactivate: the HR record comes back from offboarded,
        # and saving it switches back on what offboarding switched off.
        record = _hr_record_of(user, company_user.company)
        if record is not None and record.anonymized_at:
            return Response({
                'status': 'error',
                'message': "This person's HR record was anonymised, so their login cannot be switched back on.",
            }, status=status.HTTP_400_BAD_REQUEST)
        if record is not None and record.employment_status == 'offboarded':
            record.employment_status = 'active'
            record.save(update_fields=['employment_status', 'updated_at'])
            _audit(company_user, 'employee.reactivate', record, employment_status='active')
        User.objects.filter(pk=user.pk, is_active=False).update(is_active=True)
        user.refresh_from_db()

        serializer = UserListSerializer(user)

        return Response({
            'status': 'success',
            'message': 'User reactivated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to reactivate user',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyAdmin])
def user_handover(request, userId):
    """
    Hand over a leaver's open work in every agent (hr_agent.handover).
    GET, POST /api/company/users/{userId}/handover

    The same form HR has, at an address that does not need the HR agent: a
    company without HR had no way at all to pass on a leaver's tasks, tickets,
    meetings and interviews. Owners and admins only. Without HR, the two
    groups that live on HR's screens (reports, leave to decide) are left out.
    """
    from core.modules import has_module
    from hr_agent import handover

    company_user = request.user
    user = get_object_or_404(User, id=userId)
    refused = _refusal(user, company_user, changing=False)
    if refused:
        return refused
    record = _hr_record_of(user, company_user.company)
    if record is None:
        return Response({'status': 'error', 'message': 'User not found or access denied'},
                        status=status.HTTP_404_NOT_FOUND)
    with_hr = has_module(company_user.company, 'hr_agent')

    if request.method == 'GET':
        return Response({'status': 'success', 'data': handover.summary(record, with_hr=with_hr)})

    assignments = (request.data or {}).get('assignments')
    if not isinstance(assignments, dict) or not assignments:
        return Response({'status': 'error', 'message': 'Choose who gets at least one group.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        results = handover.hand_over(record, assignments, company_user, with_hr=with_hr)
    except ValueError as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    _audit(company_user, 'employee.handover', record,
           **{key: {'moved': r['moved'], 'to': r['to']} for key, r in results.items()})
    return Response({'status': 'success', 'data': {'results': results,
                                                   'remaining': handover.summary(record, with_hr=with_hr)}})
