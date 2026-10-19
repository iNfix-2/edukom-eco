import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edukom_hr.settings')

application = get_wsgi_application()

