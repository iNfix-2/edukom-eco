from django.core.management.base import BaseCommand
from django.utils import timezone
from blog.models import Category, Tag, Post


class Command(BaseCommand):
    help = "Seed example categories, tags, and sample posts for the blog"

    def handle(self, *args, **options):
        cat_names = ["Recruitment", "Performance", "Training", "Strategy"]
        categories = {}
        for name in cat_names:
            categories[name], _ = Category.objects.get_or_create(name=name)

        tag_names = ["HR", "Nigeria", "Best Practices", "Leadership", "Compliance"]
        tags = {}
        for name in tag_names:
            tags[name], _ = Tag.objects.get_or_create(name=name)

        samples = [
            ("Hiring Right in 2025", "Recruitment", ["HR", "Best Practices"]),
            ("Boosting Team Performance", "Performance", ["Leadership", "Best Practices"]),
            ("Designing Effective Trainings", "Training", ["HR", "Nigeria"]),
        ]

        for title, cat, tag_list in samples:
            post, created = Post.objects.get_or_create(
                title=title,
                defaults={
                    'author': 'Edukom HR',
                    'content': (
                        f"This is a sample article on {title}. Replace this content with your own insights and case studies.\n\n"
                        "Edukom HR provides end-to-end HR solutions tailored to your organization."
                    ),
                    'published': True,
                    'created_at': timezone.now(),
                    'category': categories[cat],
                },
            )
            if created:
                post.tags.set([tags[n] for n in tag_list])

        self.stdout.write(self.style.SUCCESS("Blog seed complete."))

