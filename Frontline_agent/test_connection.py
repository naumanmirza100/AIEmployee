"""
Quick test script to verify Frontline Agent setup
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.conf import settings
from Frontline_agent.database_service import PayPerProjectDatabaseService
from Frontline_agent.frontline_ai_orchestrator import FrontlineAICustomerSupport

print("=" * 70)
print("Testing Frontline Agent Setup")
print("=" * 70)

# Test 1: Check Groq API Key
print("\n1. Checking Groq API Key...")
api_key = getattr(settings, 'GROQ_API_KEY', None)
if api_key:
    print(f"   ✅ GROQ_API_KEY found: {api_key[:20]}...{api_key[-10:]}")
else:
    print("   ❌ GROQ_API_KEY not found")

# Test 2: Check Database Connection
print("\n2. Testing Database Connection...")
try:
    db_service = PayPerProjectDatabaseService()
    print("   ✅ Database connection successful")
    
    # Test getting tables
    tables = db_service.get_all_tables()
    print(f"   ✅ Found {len(tables)} tables")
    if tables:
        print(f"   Sample tables: {', '.join(tables[:5])}")
    
    # Test project statistics
    print("\n3. Testing Project Statistics...")
    stats = db_service.get_project_statistics()
    print(f"   Total Projects: {stats.get('total_projects', 0)}")
    print(f"   Running Projects: {stats.get('running_projects', 0)}")
    print(f"   Status Breakdown: {stats.get('by_status', {})}")
    
except Exception as e:
    print(f"   ❌ Database connection failed: {e}")

# Test 3: Test Frontline AI
print("\n4. Testing Frontline AI Orchestrator...")
try:
    from django.contrib.auth.models import User
    test_user = User.objects.first()
    if not test_user:
        print("   ⚠️ No test user found, creating one...")
        test_user = User.objects.create_user('test_user', 'test@test.com', 'testpass')
    
    frontline_ai = FrontlineAICustomerSupport()
    print("   ✅ Frontline AI initialized")
    
    # Test queries
    print("\n5. Testing Query Processing...")
    test_queries = [
        "what is payperproject?",
        "how many projects currently running?",
        "hi"
    ]
    
    for query in test_queries:
        print(f"\n   Testing: '{query}'")
        try:
            result = frontline_ai.process(test_user, query)
            if result.get('success'):
                answer = result.get('answer', result.get('message', ''))[:100]
                print(f"   ✅ Response: {answer}...")
            else:
                print(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
except Exception as e:
    print(f"   ❌ Frontline AI initialization failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Test Complete")
print("=" * 70)

