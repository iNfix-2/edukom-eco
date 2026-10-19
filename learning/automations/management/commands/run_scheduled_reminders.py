from django.core.management.base import BaseCommand
from automations.services import ReminderScheduler


class Command(BaseCommand):
    help = 'Runs the automated class reminder engine to trigger 24h, 1h, and 10m WhatsApp and email alerts.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Executing Edukom Class Reminder Automation..."))
        scheduler = ReminderScheduler()
        counts = scheduler.dispatch_all_due_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Reminders completed successfully! 24-Hour: {counts['24h']}, 1-Hour: {counts['1h']}, 10-Min: {counts['10m']}, Skipped (idempotent): {counts['skipped']}"
        ))
