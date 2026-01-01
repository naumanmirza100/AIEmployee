import os                # ✅ required for os.getenv
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Groq API settings
# Check environment variable first, then use fallback API key
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API") 
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

 
"""  
from dotenv import load_dotenv
"""
import os

from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
from pathlib import Path

 bashi-sultan
# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'your-secret-key'

# SECURITY WARNING: don't run with debug turned on in production!

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-9hce6%w7!*)lb#$^6)gb8!h01#6t6y_85nn=exz82l4dj=6q45'
 main
DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
 bashi-sultan
    'Frontline_agent', 
    # Your apps
    'core',  # <-- add this

    
    # Third party apps
    'rest_framework',
    'rest_framework.authtoken',

    'core',
    'project_manager_agent',
    'recruitment_agent',
    'marketing_agent.apps.MarketingAgentConfig',  # Use app config for agent registration
    'Frontline_agent.apps.FrontlineAgentConfig',  # Frontline Agent app
    'api',  # API app
 main
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'recruitment_agent.middleware.AutoInterviewFollowupMiddleware',  # Auto follow-up email checking
]

ROOT_URLCONF = 'project_manager_ai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project_manager_ai.wsgi.application'

 bashi-sultan
# Database
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'payPerProject',
        'USER': 'Agent',
        'PASSWORD': 'Agent@766',
        'HOST': '127.0.0.1',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 18 for SQL Server',
            'extra_params': 'TrustServerCertificate=Yes;',  # ✅ important for SSL
            'MARS_Connection': True,                        # optional
        },
    }
}


# --------------------
# Database (SQL Server Express)
# --------------------
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': os.getenv('DB_NAME', 'project_manager_db'),
        'HOST': r'localhost',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'trusted_connection': 'yes',
        },
    }
}

# ⚠️ Notes:
# - No PORT (SQL Express uses dynamic ports)
# - No USER / PASSWORD (Windows Authentication)
# - No extra_params (causes invalid connection string errors)


# --------------------
 main
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
 bashi-sultan
STATICFILES_DIRS = [BASE_DIR / "static"]

STATICFILES_DIRS = [BASE_DIR / 'static']

# --------------------
# Media files (for file uploads)
# --------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

 main

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
 bashi-sultan



# --------------------
# Auth redirects
# --------------------
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/login/'


# --------------------
# AI / API Settings
# --------------------
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')
GROQ_REC_API_KEY = os.getenv('GROQ_REC_API_KEY', '')


# --------------------
# Email Configuration
# --------------------
# Check EMAIL_BACKEND from .env (remove quotes if present)
email_backend_env = os.getenv('EMAIL_BACKEND', '').strip().strip("'\"")
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '').strip()
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '').strip()

# Check if SMTP is requested (either full path or 'smtp' keyword)
if email_backend_env and ('smtp' in email_backend_env.lower() or 'EmailBackend' in email_backend_env):
    # SMTP Configuration for actual email sending
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com').strip()
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower().strip() == 'true'
    EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower().strip() == 'true'
    
    # Verify SMTP settings are configured
    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        print("\n" + "="*60)
        print("WARNING: SMTP backend requested but EMAIL_HOST_USER or EMAIL_HOST_PASSWORD not set!")
        print("Falling back to console backend (emails will print to terminal)")
        print("="*60 + "\n")
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    else:
        print("\n" + "="*60)
        print("EMAIL CONFIGURATION:")
        print(f"  Backend: SMTP")
        print(f"  Host: {EMAIL_HOST}")
        print(f"  Port: {EMAIL_PORT}")
        print(f"  From: {EMAIL_HOST_USER}")
        print("="*60 + "\n")
else:
    # Console backend (for development - emails print to terminal)
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    print("\n" + "="*60)
    print("INFO: Using console email backend (emails will print to terminal)")
    print("To send actual emails, set in .env:")
    print("  EMAIL_BACKEND=smtp")
    print("  EMAIL_HOST_USER=your-email@gmail.com")
    print("  EMAIL_HOST_PASSWORD=your-app-password")
    print("="*60 + "\n")

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER if EMAIL_HOST_USER else 'noreply@example.com').strip()
RECRUITER_EMAIL = os.getenv('RECRUITER_EMAIL', '').strip()


# --------------------
# REST Framework Configuration
# --------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}
 main
