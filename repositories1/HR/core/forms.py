from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(max_length=200)
    email = forms.EmailField()
    subject = forms.CharField(max_length=200, required=False)
    message = forms.CharField(widget=forms.Textarea, max_length=5000)
    # Honeypot
    website = forms.CharField(required=False, widget=forms.HiddenInput)

