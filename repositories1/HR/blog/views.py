from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from .models import Post, Category, Tag
from .forms import PostForm, CategoryForm, TagForm
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import redirect
from django.db.models import Q


def post_list(request, category_slug=None, tag_slug=None):
    posts_qs = Post.objects.filter(published=True)
    current_category = None
    current_tag = None

    if category_slug:
        current_category = get_object_or_404(Category, slug=category_slug)
        posts_qs = posts_qs.filter(category=current_category)

    if tag_slug:
        current_tag = get_object_or_404(Tag, slug=tag_slug)
        posts_qs = posts_qs.filter(tags=current_tag)

    paginator = Paginator(posts_qs, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'posts': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'current_category': current_category,
        'current_tag': current_tag,
        'categories': Category.objects.all(),
        'tags': Tag.objects.all(),
    }
    return render(request, 'blog/post_list.html', context)


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, published=True)
    return render(request, 'blog/post_detail.html', {'post': post})


@login_required
@user_passes_test(lambda u: u.is_staff)
def post_create(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save()
            return redirect(post.get_absolute_url())
    else:
        form = PostForm()
    return render(request, 'blog/post_form.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.is_staff)
def post_manage_list(request):
    posts = Post.objects.all().order_by('-created_at')

    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    category_slug = (request.GET.get('category') or '').strip()

    if q:
        posts = posts.filter(Q(title__icontains=q) | Q(content__icontains=q) | Q(author__icontains=q))
    if status == 'published':
        posts = posts.filter(published=True)
    elif status == 'draft':
        posts = posts.filter(published=False)
    if category_slug:
        try:
            cat = Category.objects.get(slug=category_slug)
            posts = posts.filter(category=cat)
        except Category.DoesNotExist:
            pass

    context = {
        'posts': posts,
        'categories': Category.objects.all(),
    }
    return render(request, 'blog/post_manage_list.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def category_manage(request):
    cat_form = CategoryForm(prefix='cat')
    tag_form = TagForm(prefix='tag')

    if request.method == 'POST':
        # Determine which form was submitted by prefix field name
        if any(k.startswith('cat-') for k in request.POST.keys()):
            cat_form = CategoryForm(request.POST, prefix='cat')
            if cat_form.is_valid():
                cat_form.save()
                return redirect('blog_categories')
        elif any(k.startswith('tag-') for k in request.POST.keys()):
            tag_form = TagForm(request.POST, prefix='tag')
            if tag_form.is_valid():
                tag_form.save()
                return redirect('blog_categories')

    categories = Category.objects.all()
    tags = Tag.objects.all()
    return render(request, 'blog/category_manage.html', {
        'form': cat_form,
        'tag_form': tag_form,
        'categories': categories,
        'tags': tags,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def category_delete(request, slug):
    cat = get_object_or_404(Category, slug=slug)
    if request.method == 'POST':
        cat.delete()
        return redirect('blog_categories')
    # simple safe redirect if GET
    return redirect('blog_categories')


@login_required
@user_passes_test(lambda u: u.is_staff)
def tag_delete(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    if request.method == 'POST':
        tag.delete()
        return redirect('blog_categories')
    return redirect('blog_categories')


@login_required
@user_passes_test(lambda u: u.is_staff)
def post_edit(request, slug):
    post = get_object_or_404(Post, slug=slug)
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save()
            return redirect(post.get_absolute_url())
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/post_form.html', {'form': form, 'post': post})


@login_required
@user_passes_test(lambda u: u.is_staff)
def post_delete(request, slug):
    post = get_object_or_404(Post, slug=slug)
    if request.method == 'POST':
        post.delete()
        return redirect('blog_manage')
    return render(request, 'blog/post_confirm_delete.html', {'post': post})
