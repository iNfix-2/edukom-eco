from django.shortcuts import render, redirect, get_object_or_404
from . import forms
from . import models
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from edukom import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def homepage(request):
    # Fetch random or latest 5 testimonials to display on the homepage
    testimonials = models.Testimonial.objects.all().order_by('-date_created')[:5]
    # Update context to include testimonials
    return render(request, 'index.html', {'testimonials': testimonials}) 

def about(request):
    return render(request, 'about.html')

from .forms import ContactForm
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            data = form.save()
            subject = f'Message from {data.name}'
            html_message = render_to_string('emails/contact.html', {'data': data})
            from_email = settings.EMAIL_HOST_USER
            recipient_list = ['john@edukom.ng', 'ope.komolafe@edukom.ng']
            message = EmailMessage(subject, html_message, from_email, recipient_list)
            message.content_subtype = 'html'
            message.send()
            messages.success(request, 'You message has been sent to the support team we will contact you soon.')
            return redirect('contact')
    else:
        form = ContactForm()
    return render(request, 'contact.html', {'form':form})

def faq(request):
    return render(request, 'faq.html')

def blog_list(request):
    posts = models.Blog.objects.all().order_by('-date_created')
    return render(request, 'blog/blog_list.html', {'posts': posts})

def blog_detail(request, slug):
    post = get_object_or_404(models.Blog, slug=slug)
    
    # Increment views
    # Use session to prevent duplicate view counts per session if desired, 
    # but for simple "realtime" feeling, just incrementing is fine or check session.
    session_key = f'viewed_blog_{post.id}'
    if not request.session.get(session_key, False):
        post.views += 1
        post.save()
        request.session[session_key] = True

    recent_posts = models.Blog.objects.exclude(id=post.id).order_by('-date_created')[:3]
    comments = post.comments.all().order_by('-date_created')
    comment_form = forms.CommentForm()
    
    # Check if liked by current user/session
    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key
    if not session_id:
        request.session.save()
        session_id = request.session.session_key
        
    is_liked = False
    if user:
        is_liked = post.likes.filter(user=user).exists()
    else:
        is_liked = post.likes.filter(session_id=session_id).exists()

    context = {
        'post': post,
        'recent_posts': recent_posts,
        'comments': comments,
        'comment_form': comment_form,
        'likes_count': post.likes.count() if post.likes else 0,
        'is_liked': is_liked,
    }
    return render(request, 'blog/blog_detail.html', context)

def succes_form(request, uid):
    guardian = models.Guardian.objects.get(uid=uid)
    guardian.full_name = f"{guardian.last_name} {guardian.first_name}"
    subject = 'Welcome to Edukom'
    html_message = render_to_string('emails/gaurdian_sucess.html', {'guardian': guardian})
    from_email = settings.EMAIL_HOST_USER
    recipient_list = [guardian.email]
    message = EmailMessage(subject, html_message, from_email, recipient_list)
    message.content_subtype = 'html'

    admin_html_message = render_to_string('emails/guardiantoadmin.html', {'guardian': guardian})
    admin_from_email = settings.EMAIL_HOST_USER
    admin_recipient_list = ['john@edukom.ng', 'info@edukom.ng']
    admin_message = EmailMessage(subject, admin_html_message, admin_from_email, admin_recipient_list)
    admin_message.content_subtype = 'html'
    
    mail = models.GuardianEmail.objects.filter(guardian = guardian, sent = True)
    if mail:
        guardian.status = "Message has already been sent."
    else:
        guardian.status = "Message Sent."
        message.send()
        models.GuardianEmail.objects.create(guardian = guardian, sent = True)
        admin_message.send()
    return render(request, 'Forms/success.html', {'guardian':guardian})


def get_a_tutor(request):
    if request.method == "POST":
        Guform = forms.GuardianForm(request.POST)
        Abform = forms.AboutChildForm(request.POST)
        Loform = forms.LocationForm(request.POST)
        Leform = forms.LessonForm(request.POST)
        if Guform.is_valid() & Abform.is_valid() & Loform.is_valid() & Leform.is_valid():
            Guf = Guform.save(commit=False)
            Guf_data = Guform.save()
            Abf = Abform.save(commit=False)
            Abf.guardian = Guf_data
            Abf_data = Abform.save()
            Lof = Loform.save(commit=False)
            Lof.guardian = Guf_data
            Lof_data = Loform.save()
            Lef = Leform.save(commit=False)
            Lef.guardian = Guf_data
            Lef_data = Leform.save()
            return redirect('succes_form', uid= Guf_data.uid )
    else:
        Guform = forms.GuardianForm()
        Abform = forms.AboutChildForm()
        Loform = forms.LocationForm()
        Leform = forms.LessonForm()

    form_context = {
        'Guform':Guform,  
        'Abform':Abform,  
        'Loform':Loform,  
        'Leform':Leform,  
    }
    return render(request, 'Forms/GetATutor.html', form_context)

@login_required
def ViewGuardians(request):
    guardian = models.Guardian.objects.all().order_by('-date_joined')
    for g in guardian:
        g.full_name = f"{g.last_name} {g.first_name}"

    return render(request, 'gaurdians.html', {'guardian':guardian})


@login_required
def ViewGuardian(request, uid):
    guardian = models.Guardian.objects.get(uid=uid)
    guardian.full_name = f"{guardian.last_name} {guardian.first_name}"

@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Admins only.")
        return redirect('homepage')
        
    posts = models.Blog.objects.all().order_by('-date_created')
    
    # Calculate aggregate stats
    total_posts = posts.count()
    total_views = sum(post.views for post in posts)
    total_comments = models.Comment.objects.count()
    total_likes = models.Like.objects.count()
    
    # Prepare data for charts
    # Top 5 posts by views
    top_posts = posts.order_by('-views')[:5]
    chart_titles = [post.title[:20] + '...' if len(post.title) > 20 else post.title for post in top_posts]
    chart_views = [post.views for post in top_posts]
    
    # Engagement data
    chart_comments = [post.comments.count() for post in top_posts]
    chart_likes = [post.likes.count() for post in top_posts]
    
    import json
    context = {
        'posts': posts,
        'total_posts': total_posts,
        'total_views': total_views,
        'total_comments': total_comments,
        'total_likes': total_likes,
        'chart_titles': json.dumps(chart_titles),
        'chart_views': json.dumps(chart_views),
        'chart_comments': json.dumps(chart_comments),
        'chart_likes': json.dumps(chart_likes),
        'testimonial_form': forms.TestimonialForm(),
    }
    return render(request, 'blog/admin_dashboard.html', context)

@login_required
def add_testimonial(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect('homepage')
        
    if request.method == 'POST':
        form = forms.TestimonialForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Testimonial uploaded successfully!")
        else:
            messages.error(request, "Error uploading testimonial. Please check the form.")
    return redirect('admin_dashboard')

@login_required
def delete_blog(request, slug):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Admins only.")
        return redirect('homepage')
    
    post = get_object_or_404(models.Blog, slug=slug)
    post.delete()
    messages.success(request, "Post deleted successfully.")
    return redirect('admin_dashboard')

def add_comment(request, slug):
    post = get_object_or_404(models.Blog, slug=slug)
    if request.method == 'POST':
        form = forms.CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.blog = post
            comment.save()
            messages.success(request, "Comment added!")
    return redirect('blog_detail', slug=slug)

from django.http import JsonResponse

def toggle_like(request, slug):
    if request.method == 'POST':
        post = get_object_or_404(models.Blog, slug=slug)
        # Simple session-based like for now, or user-based if logged in
        # If user is logged in:
        user = request.user if request.user.is_authenticated else None
        session_id = request.session.session_key
        if not session_id:
            request.session.save()
            session_id = request.session.session_key
            
        # Check if already liked
        liked = False
        like_qs = models.Like.objects.filter(blog=post)
        if user:
            like_qs = like_qs.filter(user=user)
        else:
            like_qs = like_qs.filter(session_id=session_id)
        
        if like_qs.exists():
            like_qs.delete()
            liked = False
        else:
            models.Like.objects.create(blog=post, user=user, session_id=session_id)
            liked = True
            
        return JsonResponse({'liked': liked, 'count': post.likes.count()})
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def create_blog(request):
    if not request.user.is_staff:
        messages.error(request, "You do not have permission to create blog posts.")
        return redirect('homepage')
    
    if request.method == 'POST':
        form = forms.BlogForm(request.POST, request.FILES)
        if form.is_valid():
            blog = form.save(commit=False)
            # Slug generation (simple version, ideally should handle duplicates)
            from django.utils.text import slugify
            blog.slug = slugify(blog.title)
            # Ensure slug uniqueness
            if models.Blog.objects.filter(slug=blog.slug).exists():
                import uuid
                blog.slug = f"{blog.slug}-{uuid.uuid4().hex[:6]}"
            blog.save()
            messages.success(request, 'Blog post created successfully!')
            return redirect('blog_detail', slug=blog.slug)
    else:
        form = forms.BlogForm()
    
    return render(request, 'blog/create_blog.html', {'form': form, 'page_title': 'Write a New Post'})

@login_required
def edit_blog(request, slug):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to edit blog posts.")
        return redirect('homepage')
    
    post = get_object_or_404(models.Blog, slug=slug)
    
    if request.method == 'POST':
        form = forms.BlogForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            blog = form.save(commit=False)
            # Only update slug if title changed, or keep it stable? Usually better to keep stable to avoid broken links.
            # For simplicity, we won't regenerate slug on edit unless explicitly valid/desired.
            # blog.slug = slugify(blog.title) 
            blog.save()
            messages.success(request, 'Blog post updated successfully!')
            return redirect('blog_detail', slug=blog.slug)
    else:
        form = forms.BlogForm(instance=post)
    
    return render(request, 'blog/create_blog.html', {'form': form, 'page_title': 'Edit Blog Post', 'is_edit': True})

