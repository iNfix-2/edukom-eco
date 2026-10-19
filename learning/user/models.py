import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

User = get_user_model()


class UserRole(models.TextChoices):
    STUDENT = 'STUDENT', 'Student'
    GUARDIAN = 'GUARDIAN', 'Parent / Guardian'
    TUTOR = 'TUTOR', 'Tutor'
    STAFF = 'STAFF', 'Staff / Coordinator'
    ADMIN = 'ADMIN', 'Admin / Executive'


class UserProfile(models.Model):
    """
    Unified User Profile supporting Role-Based Access Control (RBAC)
    across Students, Tutors, Operations Staff, and Platform Admins.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(
        max_length=20, 
        choices=UserRole.choices, 
        default=UserRole.STUDENT, 
        db_index=True
    )
    phone_number = models.CharField(max_length=35, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    headline = models.CharField(max_length=200, blank=True, help_text="e.g. Year 10 IGCSE Scholar or Lead Science Tutor")
    bio = models.TextField(blank=True)
    timezone = models.CharField(max_length=50, default='Africa/Lagos')
    student_grade = models.CharField(max_length=50, blank=True, help_text="Class / Year Level for students")
    curriculum = models.CharField(max_length=50, blank=True, default='British')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} [{self.get_role_display()}]"

    @property
    def is_student(self) -> bool:
        return self.role == UserRole.STUDENT

    @property
    def is_guardian(self) -> bool:
        return self.role == UserRole.GUARDIAN

    @property
    def is_tutor(self) -> bool:
        return self.role == UserRole.TUTOR

    @property
    def is_staff_member(self) -> bool:
        return self.role == UserRole.STAFF or self.user.is_staff

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN or self.user.is_superuser

    def get_dashboard_url(self) -> str:
        """Returns the appropriate role-based LMS dashboard URL."""
        if self.is_admin:
            return reverse('dashboard_admin')
        elif self.is_staff_member:
            return reverse('dashboard_staff')
        elif self.is_tutor:
            return reverse('dashboard_tutor')
        elif self.is_guardian:
            return reverse('dashboard_guardian')
        return reverse('dashboard_student')


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Automatically creates or syncs UserProfile upon User creation or save.
    Infers initial role if not already explicitly assigned.
    """
    profile = getattr(instance, 'profile', None)
    if not profile:
        initial_role = UserRole.STUDENT
        if instance.is_superuser:
            initial_role = UserRole.ADMIN
        elif instance.is_staff:
            initial_role = UserRole.STAFF
        elif hasattr(instance, 'tutor_profile'):
            initial_role = UserRole.TUTOR
        elif hasattr(instance, 'student_profile'):
            initial_role = UserRole.STUDENT

        UserProfile.objects.create(user=instance, role=initial_role)
    else:
        # Keep superuser/staff flags synchronized with profile roles
        if instance.is_superuser and profile.role != UserRole.ADMIN:
            profile.role = UserRole.ADMIN
            profile.save(update_fields=['role'])
        elif instance.is_staff and profile.role not in [UserRole.STAFF, UserRole.ADMIN]:
            profile.role = UserRole.STAFF
            profile.save(update_fields=['role'])
