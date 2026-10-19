from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from homepage import models
from tutors import models as tmodels

@login_required
def GuardianListView(request):
    guardian = models.Guardian.objects.all()
    tutor = tmodels.Tutor.objects.all()
    context = {
        'guardian':guardian,
        'tutor':tutor
    }
    return render(request, 'Request/list.html', context)


@login_required
def GuardianDetailView(request, uid):
    guardian = models.Guardian.objects.get(uid=uid)
    context = {
        'guardian':guardian
    }
    return render(request, 'Request/details.html', context)



@login_required
def TutorDetailView(request, uid):
    tutor = tmodels.Tutor.objects.get(uid=uid)
    context = {
        'tutor':tutor
    }
    return render(request, 'Request/tutordetail.html', context)