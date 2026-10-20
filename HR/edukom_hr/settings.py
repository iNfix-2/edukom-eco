import os
from pathlib import Path
from urllib.parse import urlparse
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
BASE_DIR = Path(__file__).resolve().parent.parent

# --- .env loader (no external deps) ---
def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)

_load_dotenv(BASE_DIR / '.env')

def _get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

DEBUG = _get_bool('DJANGO_DEBUG', True)

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'blog',
] 

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'edukom_hr.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'edukom_hr.wsgi.application'


USE_SQLITE = _get_bool('USE_SQLITE', True)
if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('MYSQL_DATABASE', 'edukom_hr'),
            'USER': os.environ.get('MYSQL_USER', 'root'),
            'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
            'HOST': os.environ.get('MYSQL_HOST', 'localhost'),
            'PORT': os.environ.get('MYSQL_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator' },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator' },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator' },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator' },
]

LANGUAGE_CODE = os.environ.get('DJANGO_LANGUAGE_CODE', 'en-us')
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'Africa/Lagos')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
# Collect static from these folders during development/collectstatic
STATICFILES_DIRS = [
    BASE_DIR / 'static',               # for CSS/JS we add below
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Media (uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Email configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _get_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = _get_bool('EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@edukom.ng')
CONTACT_TO_EMAIL = os.environ.get('CONTACT_TO_EMAIL', 'info@edukom.ng')

# Security toggles
SECURE_SSL_REDIRECT = _get_bool('DJANGO_SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = _get_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = _get_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)

# CSRF trusted origins (comma-separated list like: https://example.com,https://www.example.com)
_csrf_trusted = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').strip()
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_trusted.split(',') if o.strip()]
CSRF_TRUSTED_ORIGINS.extend([
    'https://*.trycloudflare.com',
    'https://*.edukom.ng',
    'https://edukom.ng',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
])

# Email extras
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))
SERVER_EMAIL = os.environ.get('SERVER_EMAIL', DEFAULT_FROM_EMAIL)

# Auth redirects
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/blog/manage/'
LOGOUT_REDIRECT_URL = '/'

# Learning Platform Link
LEARNING_PLATFORM_URL = os.environ.get('LEARNING_PLATFORM_URL', 'https://learning.edukom.ng/')

# HSTS (recommended for production)
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _get_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = _get_bool('DJANGO_SECURE_HSTS_PRELOAD', not DEBUG)

# Optional AWS S3 storage (for media and/or static)
USE_S3 = _get_bool('USE_S3', False)
if USE_S3:
    try:
        import storages  # noqa: F401
        INSTALLED_APPS.append('storages')
        AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
        AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
        AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
        AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', '')
        AWS_S3_SIGNATURE_VERSION = os.environ.get('AWS_S3_SIGNATURE_VERSION', 's3v4')
        AWS_S3_FILE_OVERWRITE = False
        AWS_DEFAULT_ACL = None
        AWS_QUERYSTRING_AUTH = False

        USE_S3_FOR_STATIC = _get_bool('USE_S3_FOR_STATIC', False)
        USE_S3_FOR_MEDIA = _get_bool('USE_S3_FOR_MEDIA', True)

        if USE_S3_FOR_MEDIA:
            DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
            MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"

        if USE_S3_FOR_STATIC:
            STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
            STATIC_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/static/"
    except Exception:
        # If django-storages not installed, continue with local storage
        pass

# Edukom Learning Platform URL
LEARNING_PLATFORM_URL = os.environ.get('LEARNING_PLATFORM_URL', 'https://tension-detail-officers-insider.trycloudflare.com/')
