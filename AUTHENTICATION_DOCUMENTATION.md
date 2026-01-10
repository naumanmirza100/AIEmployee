# Authentication Documentation

This file documents the authentication setup for the API endpoints. **All authentication has been temporarily disabled for testing purposes.** This document serves as a reference to restore authentication later.

## Project Manager Agent Endpoints

All project manager agent endpoints were originally protected with `IsAuthenticated` and required project manager role verification.

### Endpoints:
1. `/api/project-manager/ai/project-pilot` - POST
2. `/api/project-manager/ai/task-prioritization` - POST
3. `/api/project-manager/ai/generate-subtasks` - POST
4. `/api/project-manager/ai/timeline-gantt` - POST
5. `/api/project-manager/ai/knowledge-qa` - POST

### Original Authentication:
- **Permission Class**: `IsAuthenticated`
- **Role Check**: `_ensure_project_manager(request.user)` function
  - Checks if user is superuser/staff OR has project manager role in profile
  - Returns 403 Forbidden if not a project manager

### Current Status (Temporarily Disabled):
- **Permission Class**: `AllowAny` (changed for testing)
- **Role Check**: Commented out
- **User Filtering**: Modified to work with or without authenticated user
  - If user is authenticated: filters by user's projects/tasks
  - If user is not authenticated: returns all projects/tasks (limited for safety)

### Files Modified:
- `api/views/pm_agent.py`
  - Changed all `@permission_classes([IsAuthenticated])` to `@permission_classes([AllowAny])`
  - Commented out all `_ensure_project_manager()` checks
  - Added user fallback logic: `user = getattr(request, 'user', None) if hasattr(request, 'user') and request.user.is_authenticated else None`
  - Modified project/task queries to work with or without user

## Projects Endpoint

### Endpoint:
- `/api/projects` - GET (list projects)

### Original Authentication:
- **Permission Class**: `IsAuthenticated`
- **Filtering**: 
  - Non-admin users: Only see their own projects (`owner=user` or `project_manager=user`)
  - Admin users: See all projects

### Current Status (Temporarily Disabled):
- **Permission Class**: `AllowAny` (changed for testing)
- **Filtering**: 
  - If user is authenticated and not admin: Filters by user's projects
  - If user is not authenticated: Returns all projects

### Files Modified:
- `api/views/project.py`
  - Changed `list_projects` from `IsAuthenticated` to `AllowAny`
  - Added user fallback logic

## How to Restore Authentication

### Step 1: Restore Permission Classes
In `api/views/pm_agent.py`, change all:
```python
@permission_classes([AllowAny])  # Temporarily changed from IsAuthenticated for testing
```
Back to:
```python
@permission_classes([IsAuthenticated])
```

### Step 2: Restore Role Checks
Uncomment all the `_ensure_project_manager()` checks:
```python
if not _ensure_project_manager(request.user):
    return Response(
        {"status": "error", "message": "Access denied (project manager only)."},
        status=status.HTTP_403_FORBIDDEN,
    )
```

### Step 3: Restore User Filtering
Remove the user fallback logic and restore original queries:
- Change `user = getattr(...)` back to using `request.user` directly
- Restore `Project.objects.filter(owner=request.user)` instead of conditional logic
- Restore `Task.objects.filter(project__owner=request.user)` instead of conditional logic

### Step 4: Restore Projects Endpoint
In `api/views/project.py`:
- Change `list_projects` back to `@permission_classes([IsAuthenticated])`
- Restore original user filtering logic

## Authentication Helper Function

### `_ensure_project_manager(user)`
Located in `api/views/pm_agent.py` (line ~18)

**Original Logic:**
```python
def _ensure_project_manager(user):
    """
    Enforce that only project managers (or staff/superusers) can use PM agent endpoints.
    """
    if user.is_superuser or user.is_staff:
        return True
    try:
        profile = user.profile
        return profile.is_project_manager()
    except Exception:
        return False
```

**Status**: Function is still present but all calls to it are commented out.

## Notes

- All changes are marked with comments indicating they are temporary for testing
- The authentication code is preserved (commented) so it can be easily restored
- User filtering has been modified to work without authentication, but this should be reverted for production
- Some queries now return limited results (e.g., `[:10]`, `[:50]`) when user is not authenticated to prevent performance issues

## Testing Status

✅ All authentication temporarily disabled
✅ All endpoints accessible without authentication
✅ Project manager agents can be tested without login
⚠️ **WARNING**: Do not deploy to production with these changes!

