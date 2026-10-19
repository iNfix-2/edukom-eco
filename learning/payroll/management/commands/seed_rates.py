from decimal import Decimal
from django.core.management.base import BaseCommand
from payroll.models import TutorRateTier, TimezoneCategory
from tutors.models import cc as CLASS_CHOICES


class Command(BaseCommand):
    help = "Seeds initial baseline rates across class levels, delivery modes, and client timezones."

    def handle(self, *args, **options):
        # Base hourly rates in NGN for local WAT online
        base_rates = {
            'Reception Class': Decimal('4000.00'),
            'year 1': Decimal('4500.00'),
            'year 2': Decimal('4500.00'),
            'year 3': Decimal('5000.00'),
            'year 4': Decimal('5000.00'),
            'year 5': Decimal('5500.00'),
            'year 6': Decimal('5500.00'),
            'year 7': Decimal('6000.00'),
            'year 8': Decimal('6000.00'),
            'year 9': Decimal('6500.00'),
            'year 10': Decimal('7000.00'),
            'year 11': Decimal('7500.00'),
            'WAEC/GCSE CLASS': Decimal('8000.00'),
            'A levels': Decimal('9000.00'),
        }

        # Multipliers for timezones (e.g. teaching overseas diaspora students has a premium)
        tz_multipliers = {
            TimezoneCategory.LOCAL_WAT: Decimal('1.0'),
            TimezoneCategory.UK_EUROPE: Decimal('1.3'),
            TimezoneCategory.AMERICAS: Decimal('1.5'),
            TimezoneCategory.MIDDLE_EAST_ASIA: Decimal('1.4'),
            TimezoneCategory.OTHER: Decimal('1.2'),
        }

        created_count = 0
        updated_count = 0

        for choice_val, choice_label in CLASS_CHOICES:
            base_rate = base_rates.get(choice_val, Decimal('5000.00'))

            for mode in ['Online lessons', 'Physical lessons']:
                mode_mult = Decimal('1.2') if mode == 'Physical lessons' else Decimal('1.0')

                for tz_cat, tz_mult in tz_multipliers.items():
                    rate = (base_rate * mode_mult * tz_mult).quantize(Decimal('100.00'))

                    tier, created = TutorRateTier.objects.update_or_create(
                        class_level=choice_val,
                        delivery_mode=mode,
                        timezone_category=tz_cat,
                        currency='NGN',
                        defaults={'hourly_rate': rate, 'is_active': True}
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded rate matrix: {created_count} created, {updated_count} updated."
        ))
