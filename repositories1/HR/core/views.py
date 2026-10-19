from urllib.parse import urlencode
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from .forms import ContactForm


@ensure_csrf_cookie
def home(request: HttpRequest) -> HttpResponse:
    return render(request, 'core/index.html')


def contact(request: HttpRequest) -> HttpResponse:
    if request.method != 'POST':
        return redirect('home')

    form = ContactForm(request.POST)
    if not form.is_valid():
        # mirror previous UX: ?sent=0 on failure
        query = urlencode({'sent': 0})
        return HttpResponseRedirect(f"{reverse('home')}?{query}#contact")

    if form.cleaned_data.get('website'):
        # Honeypot triggered, pretend success
        query = urlencode({'sent': 1})
        return HttpResponseRedirect(f"{reverse('home')}?{query}#contact")

    name = form.cleaned_data['name']
    email = form.cleaned_data['email']
    subject = form.cleaned_data.get('subject') or 'New Contact Form Submission'
    message = form.cleaned_data['message']

    body_html = (
        f"<p><strong>Name:</strong> {name}</p>"
        f"<p><strong>Email:</strong> {email}</p>"
        f"<p><strong>Message:</strong><br>{message}</p>"
    )
    body_text = f"Name: {name}\nEmail: {email}\nMessage:\n{message}"

    try:
        send_mail(
            subject,
            body_text,
            settings.DEFAULT_FROM_EMAIL,
            [getattr(settings, 'CONTACT_TO_EMAIL', settings.DEFAULT_FROM_EMAIL)],
            html_message=body_html,
            fail_silently=False,
        )
        query = urlencode({'sent': 1})
    except Exception:
        query = urlencode({'sent': 0})

    return HttpResponseRedirect(f"{reverse('home')}?{query}#contact")
