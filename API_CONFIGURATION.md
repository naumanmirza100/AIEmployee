# API Configuration - Centralized Setup

## Overview

All API URLs are now centralized in a single configuration file for easy management.

## Configuration File

**Location:** `PaPerProjectFront/src/config/apiConfig.js`

**Default API URL:** `http://localhost:8000/api`

## How to Change API URL

### Option 1: Change Default in Config File (Recommended for Development)

Edit `PaPerProjectFront/src/config/apiConfig.js`:

```javascript
const DEFAULT_API_URL = 'http://localhost:8000/api';  // Change this line
```

### Option 2: Use Environment Variable (Recommended for Production)

Create or edit `.env` file in `PaPerProjectFront/`:

```env
VITE_API_URL=http://localhost:8000/api
```

Or for production:
```env
VITE_API_URL=https://aiemployeemine.onrender.com/api
```

## Files Updated

All service files and components now import from the centralized config:

1. ✅ `src/services/api.js`
2. ✅ `src/services/companyAuthService.js`
3. ✅ `src/services/recruitmentAgentService.js`
4. ✅ `src/services/marketingAgentService.js`
5. ✅ `src/services/frontlineAgentService.js`
6. ✅ `src/services/pmAgentService.js`
7. ✅ `src/services/modulePurchaseService.js`
8. ✅ `src/services/companyUserManagementService.js`
9. ✅ `src/pages/CompanyDashboardPage.jsx`
10. ✅ `src/pages/AdminDashboardPage.jsx`
11. ✅ `src/components/pm-agent/ManualProjectCreation.jsx`
12. ✅ `src/components/marketing/CampaignDetail.jsx`

## Usage in New Files

When creating new service files, import the API URL like this:

```javascript
import { API_BASE_URL } from '@/config/apiConfig';

// Then use it:
const response = await fetch(`${API_BASE_URL}/your-endpoint`);
```

## Benefits

1. **Single Point of Configuration** - Change API URL in one place
2. **Easy Environment Switching** - Use .env for different environments
3. **Consistent Across All Files** - No more scattered hardcoded URLs
4. **Type Safety** - Centralized export ensures consistency

---

**Current Default:** `http://localhost:8000/api`
**Last Updated:** [Current Date]





