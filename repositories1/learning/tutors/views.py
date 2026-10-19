from django.shortcuts import render, redirect
from . import forms
from . import models
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from edukom import settings


def community(request):
    return render(request, 'community.html')


def succes_form(request, uid):
    tutor = models.Tutor.objects.get(uid=uid)
    tutor.full_name = f"{tutor.last_name} {tutor.first_name}"
    subject = 'Welcome to Edukom'
    html_message = render_to_string('emails/tutorsucess.html', {'tutor': tutor})
    from_email = settings.EMAIL_HOST_USER
    recipient_list = [tutor.email]
    message = EmailMessage(subject, html_message, from_email, recipient_list)
    message.content_subtype = 'html'

    admin_html_message = render_to_string('emails/tutortoadmin.html', {'tutor': tutor})
    admin_from_email = settings.EMAIL_HOST_USER
    admin_recipient_list = ['john@edukom.ng', 'info@edukom.ng']
    admin_message = EmailMessage(subject, admin_html_message, admin_from_email, admin_recipient_list)
    admin_message.content_subtype = 'html'
    
    mail = models.TutorEmail.objects.filter(tutor = tutor, sent = True)
    if mail:
        tutor.status = "Message has already been sent."
    else:
        tutor.status = "Message Sent."
        message.send()
        models.TutorEmail.objects.create(tutor = tutor, sent = True)
        admin_message.send()
    return render(request, 'Forms/tutor_success.html', {'tutor':tutor})


def become_a_tutor(request):
    if request.method == "POST":
        Guform = forms.TutorForm(request.POST)
        Abform = forms.AboutTutorForm(request.POST)
        Loform = forms.LocationForm(request.POST)
        Leform = forms.LessonForm(request.POST)
        if Guform.is_valid() & Abform.is_valid() & Loform.is_valid() & Leform.is_valid():
            Guf = Guform.save(commit=False)
            Guf_data = Guform.save()
            Abf = Abform.save(commit=False)
            Abf.tutor = Guf_data
            Abf_data = Abform.save()
            Lof = Loform.save(commit=False)
            Lof.tutor = Guf_data
            Lof_data = Loform.save()
            Lef = Leform.save(commit=False)
            Lef.tutor = Guf_data
            Lef_data = Leform.save()
            return redirect('tutor_succes_form', uid= Guf_data.uid )
    else:
        Guform = forms.TutorForm()
        Abform = forms.AboutTutorForm()
        Loform = forms.LocationForm()
        Leform = forms.LessonForm()

    form_context = {
        'Guform':Guform,  
        'Abform':Abform,  
        'Loform':Loform,  
        'Leform':Leform,  
    }
    return render(request, 'Forms/becomeatutor.html', form_context)