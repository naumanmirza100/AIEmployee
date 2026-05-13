# Frontline Agent - Enterprise Support System

## Overview

The Frontline Agent is an enterprise-level AI support system for PayPerProject that provides intelligent ticket management, knowledge base queries, and automated issue resolution. The system follows clean architecture principles and ensures all responses are based solely on verified information from the PayPerProject database.

## Architecture

### Clean Architecture Layers

```
core/Fronline_agent/
├── database_service.py    # Data access layer (read-only)
├── rules.py               # Business logic layer (classification rules)
├── services.py            # Service layer (knowledge & ticket automation)
├── prompts.py             # Presentation layer (AI prompts)
├── frontline_agent.py     # Agent implementation
├── views.py               # API endpoints
├── urls.py                # URL routing
└── logging_config.py      # Logging configuration
```

### Key Principles

1. **No Direct SQL Access**: All database access goes through the `PayPerProjectDatabaseService`
2. **Read-Only Operations**: Database service only allows SELECT queries
3. **Rule-Based Classification**: Ticket classification uses deterministic rules, not AI
4. **Verified Information Only**: Agent never guesses - only uses data from knowledge base
5. **Comprehensive Logging**: All actions are logged for audit and debugging

## Components

### 1. Database Service (`database_service.py`)

Read-only service for accessing PayPerProject database:
- `get_faqs()` - Retrieve FAQs
- `get_policies()` - Retrieve policies
- `get_manuals()` - Retrieve documentation/manuals
- `get_tickets()` - Retrieve tickets (read-only)

**Security**: Only SELECT queries are allowed. All queries are parameterized to prevent SQL injection.

### 2. Classification Rules (`rules.py`)

Rule-based engine for ticket classification:
- Category classification (Technical, Billing, Account, etc.)
- Priority classification (Low, Medium, High, Urgent)
- Auto-resolvability detection
- Escalation determination

**Pattern Matching**: Uses regex patterns and keyword matching for deterministic classification.

### 3. Knowledge Service (`services.py`)

Service for knowledge base operations:
- `search_knowledge()` - Search FAQs, policies, and manuals
- `get_answer()` - Get answer to a specific question

**Fallback**: If PayPerProject tables don't exist, falls back to local `KnowledgeBase` model.

### 4. Ticket Automation Service (`services.py`)

Service for ticket processing:
- `classify_ticket()` - Classify ticket using rules
- `find_solution()` - Search knowledge base for solutions
- `auto_resolve_ticket()` - Attempt auto-resolution
- `process_ticket()` - Complete ticket processing workflow

**Auto-Resolution Criteria**:
- Low complexity issues only
- Solution must exist in knowledge base
- Cannot be urgent or require escalation
- High confidence classification

### 5. Frontline Agent (`frontline_agent.py`)

Main AI agent implementation:
- `answer_question()` - Answer questions using verified knowledge
- `process_ticket()` - Process support tickets
- `search_knowledge()` - Search knowledge base

**Strict Rules**:
- Never guesses or assumes
- Only uses verified database information
- Escalates when no verified info exists

### 6. API Endpoints (`views.py`)

RESTful API endpoints:
- `GET /api/frontline/knowledge/` - Answer questions
- `GET /api/frontline/knowledge/search/` - Search knowledge base
- `POST /api/frontline/ticket/` - Create and process tickets
- `GET /api/frontline/ticket/classify/` - Classify tickets

**Authentication**: All endpoints require user authentication (`@login_required`).

## API Usage

### Answer Question

```http
GET /api/frontline/knowledge/?q=How do I reset my password?
```

**Response**:
```json
{
  "success": true,
  "answer": "To reset your password...",
  "has_verified_info": true,
  "source": "PayPerProject Database",
  "type": "faq"
}
```

### Create Ticket

```http
POST /api/frontline/ticket/
Content-Type: application/json

{
  "title": "Cannot login",
  "description": "I forgot my password and cannot access my account"
}
```

**Response**:
```json
{
  "success": true,
  "ticket_id": 123,
  "ticket_status": "auto_resolved",
  "resolved": true,
  "response": "Password reset instructions have been sent...",
  "classification": {
    "category": "account",
    "priority": "medium",
    "auto_resolvable": true
  }
}
```

### Search Knowledge

```http
GET /api/frontline/knowledge/search/?q=payment&max_results=5
```

## Database Schema

The system expects the following tables in PayPerProject database:

### FAQs Table
```sql
CREATE TABLE dbo.FAQs (
    id INT PRIMARY KEY,
    question NVARCHAR(MAX),
    answer NVARCHAR(MAX),
    category NVARCHAR(100),
    created_at DATETIME,
    updated_at DATETIME,
    is_active BIT
);
```

### Policies Table
```sql
CREATE TABLE dbo.Policies (
    id INT PRIMARY KEY,
    title NVARCHAR(MAX),
    content NVARCHAR(MAX),
    policy_type NVARCHAR(100),
    version NVARCHAR(50),
    effective_date DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    is_active BIT
);
```

### Manuals Table
```sql
CREATE TABLE dbo.Manuals (
    id INT PRIMARY KEY,
    title NVARCHAR(MAX),
    content NVARCHAR(MAX),
    manual_type NVARCHAR(100),
    section NVARCHAR(100),
    created_at DATETIME,
    updated_at DATETIME,
    is_active BIT
);
```

**Note**: If these tables don't exist, the system falls back to the local `KnowledgeBase` model.

## Logging

All agent actions are logged to `logs/frontline_agent.log`:

- Knowledge base queries
- Ticket classifications
- Auto-resolution attempts
- API requests and responses
- Errors and exceptions

**Log Format**:
```
2025-12-24 10:30:45 - frontline_agent - INFO - answer_question:45 - Processing question: How do I reset...
```

## Security

1. **Read-Only Database Access**: Only SELECT queries allowed
2. **Parameterized Queries**: All queries use parameters to prevent SQL injection
3. **Authentication Required**: All API endpoints require login
4. **No Direct SQL**: No raw SQL queries - all through service layer
5. **Input Validation**: All inputs are validated and sanitized

## Error Handling

The system handles errors gracefully:

- Database connection failures → Fallback to local models
- Missing knowledge base data → Escalate to human agents
- Classification failures → Default to safe values (Other category, Medium priority)
- API errors → Return error responses with appropriate HTTP status codes

## Testing

To test the system:

1. **Test Knowledge API**:
   ```bash
   curl -H "Authorization: Bearer <token>" \
        "http://localhost:8000/api/frontline/knowledge/?q=password"
   ```

2. **Test Ticket Creation**:
   ```bash
   curl -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer <token>" \
        -d '{"title":"Test","description":"I need help"}' \
        "http://localhost:8000/api/frontline/ticket/"
   ```

## Configuration

No additional configuration required. The system uses:
- Django database settings for PayPerProject connection
- Groq API settings for AI agent (from `.env`)
- Default logging configuration

## Maintenance

### Adding New Classification Rules

Edit `core/Fronline_agent/rules.py`:
- Add patterns to `CATEGORY_PATTERNS`
- Add keywords to `PRIORITY_KEYWORDS`
- Add patterns to `AUTO_RESOLVABLE_PATTERNS`

### Adding New Knowledge Sources

Edit `core/Fronline_agent/database_service.py`:
- Add new `get_*()` method
- Implement fallback to local model if needed

## Best Practices

1. **Never modify other modules** - All changes are isolated to `core/Fronline_agent/`
2. **Always use services** - Don't access database directly
3. **Log everything** - All actions should be logged
4. **Never guess** - Only use verified information
5. **Test thoroughly** - Test all classification rules and edge cases

