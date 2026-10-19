from django.core.management.base import BaseCommand
from classroom.models import Subject


class Command(BaseCommand):
    help = "Seeds initial educational subjects for the Edukom LMS Classroom."

    def handle(self, *args, **options):
        initial_subjects = [
            ("Mathematics", "STEM", "Pure & applied mathematics, algebra, calculus, geometry"),
            ("Further Mathematics", "STEM", "Advanced mathematical analysis and mechanics"),
            ("Physics", "STEM", "Classical mechanics, electromagnetism, and modern physics"),
            ("Chemistry", "STEM", "Inorganic, organic, and physical chemistry"),
            ("Biology", "STEM", "Cell biology, physiology, genetics, and ecology"),
            ("Coding & Computer Science", "STEM", "Python, web development, algorithms, and computational thinking"),
            ("English Language", "Languages", "Grammar, comprehension, creative writing, and phonics"),
            ("Literature in English", "Languages", "Prose, poetry, drama, and critical analysis"),
            ("French", "Languages", "Conversational French, grammar, and DELF preparation"),
            ("Economics", "Commercial", "Microeconomics, macroeconomics, and market principles"),
            ("Accounting", "Commercial", "Financial accounting, bookkeeping, and balance sheets"),
            ("Business Studies", "Commercial", "Business operations, management, and marketing"),
            ("Government & Civic Education", "Humanities", "Political systems, governance, and civic responsibility"),
            ("History", "Humanities", "World history, African history, and colonial studies"),
            ("Geography", "Humanities", "Physical and human geography, environmental studies"),
            ("Phonics & Early Reading", "General", "Foundational literacy and phonics for early years"),
        ]

        created_count = 0
        for name, category, desc in initial_subjects:
            _, created = Subject.objects.get_or_create(
                name=name,
                defaults={'category': category, 'description': desc}
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {created_count} subjects for Edukom LMS."
        ))
