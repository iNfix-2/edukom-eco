from django.core.management.base import BaseCommand
from classroom.models import Subject
from videolibrary.models import VideoCourse, VideoLesson, DRMKey
from videolibrary.services import DRMService


class Command(BaseCommand):
    help = 'Seeds realistic DRM video courses and encrypted lessons for demonstration.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding DRM Video Library...")

        math_sub, _ = Subject.objects.get_or_create(name='Mathematics', defaults={'category': 'STEM'})
        chem_sub, _ = Subject.objects.get_or_create(name='Chemistry', defaults={'category': 'STEM'})
        eng_sub, _ = Subject.objects.get_or_create(name='English Language', defaults={'category': 'Languages'})

        courses_data = [
            {
                'title': 'IGCSE Mathematics: Core & Extended Masterclass',
                'description': 'Comprehensive masterclass covering quadratic equations, coordinate geometry, trigonometry, and probability with worked past exam walkthroughs.',
                'subject': math_sub,
                'class_level': 'year 10',
                'lessons': [
                    ('Factoring Quadratic Expressions & The Quadratic Formula', 3600),
                    ('Trigonometric Ratios, Sine & Cosine Rules', 4200),
                    ('Probability Trees & Conditional Events', 3300),
                ]
            },
            {
                'title': 'WAEC & GCSE Chemistry Intensive Revision',
                'description': 'Master chemical bonding, stoichiometry, acids & bases, and electrolysis with interactive lab walkthroughs.',
                'subject': chem_sub,
                'class_level': 'year 11',
                'lessons': [
                    ('Stoichiometry & Mole Concept Calculations', 3900),
                    ('Electrolysis of Molten & Aqueous Solutions', 4500),
                    ('Organic Chemistry: Hydrocarbons & Functional Groups', 4100),
                ]
            },
            {
                'title': 'KS3 English Literature: Critical Essay Analysis',
                'description': 'Structural mastery for textual analysis, themes, metaphor identification, and high-scoring literature essays.',
                'subject': eng_sub,
                'class_level': 'year 8',
                'lessons': [
                    ('Unlocking Shakespearean Themes & Dramatic Irony', 3000),
                    ('Structuring the High-Scoring Literature Essay', 2700),
                ]
            }
        ]

        total_lessons = 0
        for c_data in courses_data:
            course, _ = VideoCourse.objects.get_or_create(
                title=c_data['title'],
                defaults={
                    'description': c_data['description'],
                    'subject': c_data['subject'],
                    'class_level': c_data['class_level'],
                    'is_subscription_only': True
                }
            )

            for order, (lesson_title, duration) in enumerate(c_data['lessons'], start=1):
                lesson, created = VideoLesson.objects.get_or_create(
                    course=course,
                    title=lesson_title,
                    defaults={
                        'description': f"Comprehensive video instruction on {lesson_title}.",
                        'order': order,
                        'duration_seconds': duration,
                        'is_drm_protected': True,
                    }
                )
                DRMService.get_or_create_drm_key(lesson)
                if created:
                    total_lessons += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded video courses with {total_lessons} DRM-protected lessons & AES-128 keys!"
        ))
