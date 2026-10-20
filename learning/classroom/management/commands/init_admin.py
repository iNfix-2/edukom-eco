import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.management import call_command


class Command(BaseCommand):
    help = "Initializes or updates the administrative superuser from environment variables and seeds academic subjects."

    def handle(self, *args, **options):
        # 1. Seed standard academic classroom subjects
        try:
            call_command('seed_classroom')
            self.stdout.write(self.style.SUCCESS("Academic classroom subjects verified."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Subject seeding skipped: {e}"))

        # 2. Check for superuser credentials in environment variables
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '').strip()
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@edukom.ng').strip()

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                "DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD not configured. Skipping superuser provision."
            ))
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email, 'is_staff': True, 'is_superuser': True}
        )
        user.set_password(password)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.save()

        # Ensure user profile exists with ADMIN role
        profile = getattr(user, 'profile', None)
        if profile:
            profile.role = 'ADMIN'
            profile.save()

        action = "Created" if created else "Updated password for"
        self.stdout.write(self.style.SUCCESS(f"{action} superuser '{username}' successfully."))
