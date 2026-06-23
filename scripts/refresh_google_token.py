"""
Run once to get a new Google refresh token.
Make sure http://localhost:8080 is added to Authorized redirect URIs in Google Console.
Then run:  C:\Python313\python.exe scripts\refresh_google_token.py
"""

import os, sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

CLIENT_ID     = os.getenv('GOOGLE_CLIENT_ID', '').strip()
CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not found in .env")
    sys.exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'google-auth-oauthlib'])
    from google_auth_oauthlib.flow import InstalledAppFlow

client_config = {
    "web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080"],
    }
}

print("Opening browser — log in with jeondavid00@gmail.com and click Allow...\n")

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=['https://www.googleapis.com/auth/calendar'],
)
creds = flow.run_local_server(
    port=8080,
    access_type='offline',
    prompt='consent',
)

print("\n" + "="*60)
print("SUCCESS! Paste this into your .env file:")
print("="*60)
print(f"\nGOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
print("Restart the Django server after saving .env")
