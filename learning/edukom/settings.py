"""
Django settings for edukom project.
Enhanced with cybersecurity defenses, environment separation, and payment/payroll integration.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables securely from .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-$zl@s@t7bm8q-d(-0!!ewm#ap1s&tov%m0k^ai)_osyh0p$phr')

# DEBUG must be False in production
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

raw_allowed_hosts = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(',') if h.strip()]
if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')
if '.trycloudflare.com' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.trycloudflare.com')
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

raw_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', 'https://*.trycloudflare.com,http://127.0.0.1,http://localhost,http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:8005,http://localhost:8005')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in raw_csrf_origins.split(',') if o.strip()]
if DEBUG:
    import socket
    try:
        for _local_ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            CSRF_TRUSTED_ORIGINS.append(f'http://{_local_ip}:8000')
            CSRF_TRUSTED_ORIGINS.append(f'http://{_local_ip}:8005')
    except Exception:
        pass

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Render Cloud & Wildcard Host Support
RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    for scheme in ['https', 'http']:
        origin = f'{scheme}://{RENDER_EXTERNAL_HOSTNAME}'
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

for domain in ['onrender.com', 'edukom-lms.onrender.com']:
    if domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(domain)
    for scheme in ['https', 'http']:
        origin = f'{scheme}://{domain}'
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)
        wildcard = f'{scheme}://*.{domain}'
        if wildcard not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(wildcard)


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap4',
    'homepage.apps.HomepageConfig',
    'tutors.apps.TutorsConfig',
    'user.apps.UserConfig',
    'payments.apps.PaymentsConfig',
    'payroll.apps.PayrollConfig',
    'classroom.apps.ClassroomConfig',
    'videolibrary.apps.VideolibraryConfig',
    'automations.apps.AutomationsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'homepage.middleware.SiteTrafficMiddleware',
]

ROOT_URLCONF = 'edukom.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'temp'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'edukom.wsgi.application'


# Database: Production Cloud DB (DATABASE_URL) / PostgreSQL with SQLite fallback
import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL', '')
POSTGRES_DB = os.getenv('POSTGRES_DB', '')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.getenv('CONN_MAX_AGE', '600')),
        )
    }
elif POSTGRES_DB:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': POSTGRES_DB,
            'USER': os.getenv('POSTGRES_USER', 'edukom_user'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'db'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('CONN_MAX_AGE', '600')),
            'OPTIONS': {
                'sslmode': os.getenv('POSTGRES_SSLMODE', 'prefer'),
            }
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Cache: Redis in production with LocMem local fallback
REDIS_URL = os.getenv('REDIS_URL', '')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'edukom-locmem-cache',
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
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


CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'public/Assets',
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STATIC_URL = '/Assets/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = '/account/dashboard/'
LOGIN_URL = '/account/login/'
LOGOUT_REDIRECT_URL = '/'
LOGOUT_URL = '/account/logout/'

# Email backend configuration from environment variables
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'mail.edukom.ng')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'support@edukom.ng')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')

OFFICIAL_NOTIFICATION_EMAILS = [
    'ope.komolafe@edukom.ng',
    'hannahmembis@edukom.ng',
    'info@edukom.ng',
    'mary@edukom.ng',
    'marykobahkoate@edukom.ng',
    'support@edukom.ng'
]

# ==============================================================================
# PAYMENT GATEWAYS (PAYSTACK & FLUTTERWAVE)
# ==============================================================================
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '')
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '')
PAYSTACK_WEBHOOK_SECRET = os.getenv('PAYSTACK_WEBHOOK_SECRET', '')

FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY', '')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY', '')
FLUTTERWAVE_SECRET_HASH = os.getenv('FLUTTERWAVE_SECRET_HASH', '')

# Virtual Classroom Settings (Daily.co WebRTC)
DAILY_API_KEY = os.getenv('DAILY_API_KEY', '')
DAILY_DOMAIN = os.getenv('DAILY_DOMAIN', 'edukom')

# ==============================================================================
# PHASE 3: VIDEO DRM & WHATSAPP AUTOMATION
# ==============================================================================
DRM_MASTER_SECRET = os.getenv('DRM_MASTER_SECRET', 'edukom-drm-secure-master-secret-2026')
DRM_TOKEN_TTL_MINUTES = int(os.getenv('DRM_TOKEN_TTL_MINUTES', '120'))

# WhatsApp Business API (Twilio / Termii)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', '+14155238886')
TERMII_API_KEY = os.getenv('TERMII_API_KEY', '')
TERMII_SENDER_ID = os.getenv('TERMII_SENDER_ID', 'Edukom')
AUTOMATIONS_CRON_SECRET = os.getenv('AUTOMATIONS_CRON_SECRET', 'edukom-auto-cron-secret-change-me')

# ==============================================================================
# CYBERSECURITY & HARDENING CONFIGURATION
# ==============================================================================
# Prevent MIME sniffing (X-Content-Type-Options: nosniff)
SECURE_CONTENT_TYPE_NOSNIFF = True

# Browser XSS Filtering (X-XSS-Protection: 1; mode=block)
SECURE_BROWSER_XSS_FILTER = True

# Prevent Clickjacking (X-Frame-Options: DENY)
X_FRAME_OPTIONS = 'DENY'

# Session & Cookie Security (Defense against Session Hijacking and XSS cookie theft)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = os.getenv('CSRF_COOKIE_HTTPONLY', 'False').lower() in ('true', '1', 't')
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 86400  # 24 hours max session duration

# SSL/TLS Enforcement in Staging/Production
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 't')
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', str(not DEBUG)).lower() in ('true', '1', 't')
CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', str(not DEBUG)).lower() in ('true', '1', 't')
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

if not DEBUG and SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ==============================================================================
# SENTRY ERROR TRACKING & APM WITH NDPR PII SANITIZATION
# ==============================================================================
SENTRY_DSN = os.getenv('SENTRY_DSN', '')

def sanitize_sentry_pii(event, hint):
    """
    NDPR/GDPR Compliance: Scrubs sensitive customer and student PII
    (bank accounts, passwords, credit card digits, auth tokens)
    before telemetry is transmitted off-server to Sentry.
    """
    sensitive_keys = {
        'password', 'secret', 'token', 'authorization', 'card', 
        'cvv', 'account_number', 'bvn', 'key', 'hash'
    }
    if 'request' in event and 'headers' in event['request']:
        for h in list(event['request']['headers'].keys()):
            if h.lower() in ('authorization', 'x-edukom-webhook-secret', 'cookie'):
                event['request']['headers'][h] = '[FILTERED]'
    if 'request' in event and 'data' in event['request'] and isinstance(event['request']['data'], dict):
        for k in event['request']['data']:
            if any(sk in k.lower() for sk in sensitive_keys):
                event['request']['data'][k] = '[FILTERED]'
    return event

if SENTRY_DSN and not DEBUG:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration()
            ],
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            send_default_pii=False,
            before_send=sanitize_sentry_pii,
            environment=os.getenv('ENVIRONMENT', 'production'),
            release=os.getenv('APP_VERSION', '2.0.0')
        )
    except ImportError:
        pass

# ==============================================================================
# STRUCTURED AUDIT LOGGING & DISK PROTECTION (ROTATING FILE HANDLERS)
# ==============================================================================
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{name}:{lineno}] {message}',
            'style': '{',
        },
        'security': {
            'format': '[{asctime}] [SECURITY_AUDIT] [{levelname}] [{name}] {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'app_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'edukom.log',
            'maxBytes': 15 * 1024 * 1024,  # 15 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security_audit.log',
            'maxBytes': 15 * 1024 * 1024,  # 15 MB
            'backupCount': 10,
            'formatter': 'security',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'edukom': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'edukom.security': {
            'handlers': ['console', 'security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'payments': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'videolibrary': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'automations': {
            'handlers': ['console', 'app_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}