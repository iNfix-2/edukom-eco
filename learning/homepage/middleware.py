from django.utils import timezone
from django.db.models import F
from .models import SiteTraffic

class SiteTrafficMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Track views for actual visitor pages, skip static/media/admin/health probes
        path = request.path_info
        if (not path.startswith('/admin/') and 
            not path.startswith('/media/') and 
            not path.startswith('/Assets/') and 
            not path.startswith('/static/') and
            not path.startswith('/healthz') and
            not path.startswith('/readyz')):
            try:
                today = timezone.now().date()
                obj, created = SiteTraffic.objects.get_or_create(date=today)
                if not created:
                    # Use F expression to avoid race conditions and safely increment
                    SiteTraffic.objects.filter(id=obj.id).update(views=F('views') + 1)
                else:
                    obj.views = 1
                    obj.save(update_fields=['views'])
            except Exception:
                # Analytics tracking should never crash requests if DB has a momentary blip
                pass
                
        response = self.get_response(request)
        return response
