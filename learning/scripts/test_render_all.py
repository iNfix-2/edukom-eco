import os, sys, django
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edukom.settings')
django.setup()

from django.template.loader import render_to_string
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from homepage.models import Blog, Guardian
from classroom.models import Student, TutorProfile, ClassBooking, ClassSession
from videolibrary.models import VideoCourse, VideoLesson
from payroll.models import PayrollRun
from payments.models import Invoice

User = get_user_model()
rf = RequestFactory()
req = rf.get('/')
user = User.objects.first()
req.user = user

template_dir = Path('temp')
errors = []

for root, _, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            rel = Path(root).relative_to(template_dir) / f
            t_name = str(rel).replace('\\', '/')
            # Skip email templates or partials if they require specific context
            try:
                render_to_string(t_name, {
                    'request': req,
                    'user': user,
                    'profile': getattr(user, 'profile', None),
                    'post': Blog.objects.first(),
                    'posts': Blog.objects.all(),
                    'guardian': Guardian.objects.first(),
                    'student': Student.objects.first(),
                    'tutor': TutorProfile.objects.first(),
                    'session': ClassSession.objects.first(),
                    'course': VideoCourse.objects.first(),
                    'lesson': VideoLesson.objects.first(),
                    'invoice': Invoice.objects.first(),
                    'run': PayrollRun.objects.first(),
                })
            except Exception as e:
                errors.append((t_name, type(e).__name__, str(e)))

print("=== TEMPLATE RENDERING RESULTS ===")
for t, err_type, err_msg in errors:
    print(f"[{err_type}] {t} -> {err_msg}")
if not errors:
    print("All templates rendered cleanly!")
