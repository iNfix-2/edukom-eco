from django.db import models

from django.db import models
import uuid
from django.utils import timezone

cc= (
    ('Reception Class','Reception Class'),
    ('year 1','year 1'),
    ('year 2','year 2'),
    ('year 3','year 3'),
    ('year 4','year 4'),
    ('year 5','year 5'),
    ('year 6','year 6'),
    ('year 7','year 7'),
    ('year 8','year 8'),
    ('year 9','year 9'),
    ('year 10','year 10'),
    ('year 11','year 11'),
    ('A levels','A levels'),
    
    ('WAEC/GCSE CLASS','WAEC/GCSE CLASS'),

)
lesson_choices = (
    ('Physical lessons', 'Physical lessons'),
    ('Online lessons', 'Online lessons'),
)

goals = (
    ('Improve phonics, reading and writing', 'Improve phonics, reading and writing'),
    ('Help with assignments and school work', 'Help with assignments and school work'),
    ('Bulid foundation and confidence','Bulid foundation and confidence'),
    ('Home schooling','Home schooling'),
    ('Special needs support','Special needs support'),
)
Curriculums = (
    ('Nigerian', 'Nigerian'),
    ('British', 'British'),
    ('American', 'American'),
    ('IPC', 'IPC'),
    ('Not sure', 'Not sure'),
)
tutor_gender = (
    ('Any gender is fine','Any gender is fine'),
    ('Male','Male'),
    ('Female','Female'),

)

subjects = (
    ('Math','Math'),
    ('English','English'),
    ('Physics','Physics'),
    ('Lit','Lit'),
    ('Chemistry','Chemistry'),
    ('History','History'),
    ('ICT','ICT'),
    ('French','French'),
    ('Government','Government'),
    ('Civic','Civic'),
    ('Business','Business'),
    ('Verbal','Verbal'),
    ('Geography','Geography'),
    ('Coding','Coding'),
    ('commercial','commercial'),
)
days = (
    ('Monday','Monday'),
    ('Tuesday','Tuesday'),
    ('Wednesday','Wednesday'),
    ('Thursday','Thursday'),
    ('Friday','Friday'),
    ('Saturday','Saturday'),
    ('Sunday','Sunday'),
)

class Tutor(models.Model):
    uid = models.UUIDField( default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=255)    
    last_name = models.CharField(max_length=255)
    email = models.EmailField( verbose_name="Active Email")
    phone = models.CharField(verbose_name="Phone Number", max_length=255)
    hear = models.CharField(verbose_name="How did you hear about us", max_length=255)

    lesson_type = models.CharField(max_length=255, choices=lesson_choices, verbose_name="Do you prefer inlesson or online lesson?")
    date_joined = models.DateTimeField(default=timezone.now)
    curriculum = models.CharField(max_length=255)  

    def __str__(self):
        return f'{self.uid}'

class AboutTutor(models.Model):
    tutor = models.OneToOneField(Tutor, on_delete=models.CASCADE, related_name="AboutTutor")
    teacher_class = models.CharField(max_length=255, choices=cc, verbose_name="What class can you teach")
    goal = models.CharField(max_length=255, choices=goals)
    subject = models.CharField(max_length=255)
    about = models.TextField(verbose_name="Tell how you can achieve your goal with the child")
    date_joined = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.tutor}'

class Location(models.Model):
    tutor = models.OneToOneField(Tutor, on_delete=models.CASCADE, related_name="Location")
    state = models.CharField(max_length=100)
    street_address = models.CharField(max_length=255)

    def __str__(self):
        return f'{self.tutor}'

class Lesson(models.Model):
    tutor = models.OneToOneField(Tutor, on_delete=models.CASCADE, related_name="Lesson")
    days = models.CharField(max_length=255, verbose_name="What days do you want the lesson to hold?")
    weeks = models.IntegerField(verbose_name="how many weeks in the month?")
    hour_per_day = models.IntegerField(verbose_name="How many hours per day?")
    start_time = models.TimeField( verbose_name="from what time?")

    def __str__(self):
        return f'{self.tutor}'

class TutorEmail(models.Model):
    tutor = models.OneToOneField(Tutor, on_delete=models.CASCADE, related_name="TutorEmail")
    sent = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.tutor}'
