from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserProfile, PasswordResetRequest
from courses.models import Response, Topic, TopicProgress
from datetime import datetime,date
from django.utils import timezone
from django.views.decorators.http import require_POST
from functools import wraps
from django.db.models import Avg, Q, Count, Case, When, Value, CharField

def require_profile(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_profile = getattr(request.user, 'userprofile', None)
        if not user_profile:
            return redirect('courses:index')
        return view_func(request, *args, **kwargs)
    return wrapper

# Create your views here.
def index(request):
    return render(request, "courses/index.html", {
        "profile": "profile",
    })

def calculate_age(dob):
    """Calculates age from a date of birth (datetime.date object)."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def _build_profile_context(viewed_user, request_user):
    """Shared context builder for both own profile and admin user_detail."""
    viewed_profile = getattr(viewed_user, 'userprofile', None)

    # ── Age ───────────────────────────────────────────────────────────
    age = None
    if viewed_profile and viewed_profile.date_of_birth:
        from datetime import date
        today = date.today()
        dob = viewed_profile.date_of_birth
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    # ── Quiz stats ────────────────────────────────────────────────────
    responses = Response.objects.filter(user=viewed_user).order_by('-created_date_time')
    total_responses = responses.count()
    avg_result = responses.aggregate(avg=Avg('score'))
    avg_score  = round(avg_result['avg'] or 0)

    # Score distribution buckets
    score_a = responses.filter(score__gte=90).count()
    score_b = responses.filter(score__gte=70, score__lt=90).count()
    score_c = responses.filter(score__gte=50, score__lt=70).count()
    score_d = responses.filter(score__lt=50).count()

    # ── Topic progress ────────────────────────────────────────────────
    all_topics = Topic.objects.annotate(
        user_avg_score=Avg(
            'quiz__response__score', 
            filter=Q(quiz__response__user=viewed_user)
        )
    ).order_by('created_at')

    total_topics   = all_topics.count()
    user_progresses = TopicProgress.objects.filter(user=viewed_user)
    progress_map   = {p.topic_id: p for p in user_progresses}

    completed_topics   = user_progresses.filter(status='completed').count()
    in_progress_topics = user_progresses.filter(status='in_progress').count()

    overall_progress = 0
    if total_topics > 0:
        overall_progress = round(
            (completed_topics * 100 + in_progress_topics * 50) / total_topics
        )

    # Build per-topic progress list for the chart tab
    topic_scores = []
    topic_progress_data = []
    for topic in all_topics:
        prog = progress_map.get(topic.id)
        status = prog.status if prog else 'not_started'
        pct = 100 if status == 'completed' else (50 if status == 'in_progress' else 0)
        
        topic_progress_data.append({
            'title':  topic.title,
            'status': status,
            'pct':    pct,
        })
        score = round(topic.user_avg_score or 0)
        topic_scores.append(score)

    # ── Forum activity ────────────────────────────────────────────────
    from courses.models import ForumComment
    forum_comments = ForumComment.objects.filter(user=viewed_user).count()

    return {
        'viewed_user':          viewed_user,
        'viewed_profile':       viewed_profile,
        'age':                  age,
        'responses':            responses[:20],   # last 20 in table
        'total_responses':      total_responses,
        'avg_score':            avg_score,
        'score_a':              score_a,
        'score_b':              score_b,
        'score_c':              score_c,
        'score_d':              score_d,
        'total_topics':         total_topics,
        'completed_topics':     completed_topics,
        'overall_progress':     overall_progress,
        'topic_progress_data':  topic_progress_data,
        'forum_comments':       forum_comments,
        'topic_scores': topic_scores
    }


# ── Own profile ───────────────────────────────────────────────────────
@login_required(login_url='user:login')
@require_profile
def index(request):
    ctx = _build_profile_context(request.user, request.user)
    ctx['is_own_profile'] = True
    return render(request, 'user/profile.html', ctx)


# ── Admin: view any user ──────────────────────────────────────────────
@login_required(login_url='user:login')
@require_profile
def user_detail_view(request, user_id):
    # Only superadmin can view other profiles
    if request.user.userprofile.role != 'superadmin':
        return redirect('user:index')

    viewed_user = get_object_or_404(User, pk=user_id)
    ctx = _build_profile_context(viewed_user, request.user)
    ctx['is_own_profile'] = False

    return render(request, 'user/profile.html', ctx)

def register_view(request):
    # ------------------------------------------------------------------
    # 1. CHECK IF USER IS ALREADY LOGGED IN
    if request.user.is_authenticated:
        # Redirect authenticated users to the index page (or profile page)
        messages.info(request, "Siz allaqachon tizimga kirgansiz.") # You are already logged in.
        return redirect('user:index') # Use the correct URL name
    # ------------------------------------------------------------------

    if request.method == 'POST':
        # 2. Retrieve data from the form
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        gender = request.POST.get('gender') # '1' for Male, '0' for Female
        region = request.POST.get('region')
        otm = request.POST.get('otm')
        date_of_birth_str = request.POST.get('date_of_birth')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        # 3. Basic Validation
        if password != password2:
            messages.error(request, "Parollar bir xil emas!")
            # Note: You might want to pass context data back to the template 
            # (like the entered form data) to avoid the user having to re-enter everything.
            return render(request, "user/register.html")

        # 4. Email existence check (using filter and exists is generally preferred)
        if User.objects.filter(email=email.lower()).exists():
            messages.error(request, "Bu email avval ro'yxatdan o'tgan.")
            return render(request, "user/register.html")
        
        # 5. Convert date of birth string to a Python date object
        date_of_birth = None
        if date_of_birth_str:
            try:
                date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Tug'ilgan sana noto'g'ri formatda kiritilgan.")
                return render(request, "user/register.html")

        # 6. Create the built-in Django User
        try:
            user = User.objects.create_user(
                username=email.lower(),
                email=email.lower(),
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # 7. Create the linked UserProfile (Default role is 'student')
            UserProfile.objects.create(
                user=user,
                role='student',
                phone=phone_number,
                gender=int(gender) if gender in ['0', '1'] else None,
                region=region,
                otm=otm,
                date_of_birth=date_of_birth
            )

            # 8. Log the user in immediately after registration
            login(request, user)
            
            messages.success(request, "Muvaffaqiyatli ro'yxatdan o'tdingiz!")
            return redirect('user:index')

        except Exception as e:
            messages.error(request, f"Ro'yxatdan o'tishda xatolik yuz berdi: {e}")
            return render(request, "user/register.html")

    else: # If GET request, render the empty form
        return render(request, "user/register.html", {
            "profile": "profile",
        })
    

def login_view(request):
    # 1. Check if user is already logged in
    if request.user.is_authenticated:
        messages.info(request, "Siz allaqachon tizimga kirgansiz.")
        return redirect('user:index')

    if request.method == 'POST':
        # 2. Retrieve data from the form
        submitted_email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')
        
        try:
            # FIX: Find the user by email (case-insensitive)
            user_by_email = User.objects.get(email=submitted_email.lower())
            # Use the user's username (which is the email) for the authenticate function
            username_to_authenticate = user_by_email.username
            
            # 3. Authenticate using the retrieved username and submitted password
            user = authenticate(
                request, 
                username=username_to_authenticate, 
                password=password
            )
            
        except User.DoesNotExist:
            # If no user found with that email, 'user' remains None, which triggers the error message below
            messages.error(request, "Bunday email mavjud emas")
            return render(request, "user/login.html")
        
        # 4. Check authentication result
        if user is not None:
            # Login successful
            login(request, user)
            
            if not remember_me:
                request.session.set_expiry(0) 
            
            messages.success(request, f"Xush kelibsiz, {user.first_name}!")
            return redirect('user:index')

        else:
            # Authentication failed (incorrect email/password combo or user not found)
            messages.error(request, "Email yoki parol noto'g'ri. Iltimos, tekshirib ko'ring.")
            return render(request, "user/login.html")

    else: # GET request
        return render(request, "user/login.html")
    

def logout_view(request):
    # 1. Log the user out
    logout(request)
    
    # 2. Send a message
    messages.info(request, "Tizimdan muvaffaqiyatli chiqdingiz.")
    
    # 3. Redirect to the login page
    return redirect('user:login')

def forgot_password_view(request):
    if request.method == 'POST':
        # Get the input which could be email or phone number
        contact_input = request.POST.get('contact_input', '').strip()

        if not contact_input:
            messages.error(request, "Iltimos, email yoki telefon raqamingizni kiriting.")
            return render(request, "user/forgot_password.html")

        # Optional: Try to link the request to an existing user
        linked_user = None
        try:
            # Check by email or username (which is email)
            linked_user = User.objects.get(email__iexact=contact_input)
        except User.DoesNotExist:
            try:
                # Check if it's a phone number saved in UserProfile
                linked_user = User.objects.get(userprofile__phone=contact_input)
            except User.DoesNotExist:
                # User not found, but we still record the request
                pass

        # Save the request to the database
        PasswordResetRequest.objects.create(
            contact_input=contact_input,
            linked_user=linked_user
        )

        # Success Message
        messages.success(request, "Rahmat, so'rovingiz qabul qilindi. Administratorlarimiz tez orada parolingizni tiklab berishadi.")
        
        # Redirect back to the login page (or stay on the same page, but redirect is cleaner)
        return redirect('user:login')

    # GET request
    return render(request, "user/forgot_password.html")

# ===== VERSION 1: OPTIMIZED WITH ANNOTATIONS (RECOMMENDED) =====
@login_required(login_url='user:login')
@require_profile
def all_users_view(request):
    """
    ✅ OPTIMIZED: Uses database aggregations instead of Python loops
    - Single query with annotations
    - Counts performed at database level
    - No N+1 query problem
    """
    now = timezone.now()
    
    # ✅ Single query with aggregations
    user_stats = User.objects.select_related('userprofile').aggregate(
        total_count=Count('id'),
        student_count=Count(
            Case(When(userprofile__role='student', then=1), output_field=CharField())
        ),
        teacher_count=Count(
            Case(When(userprofile__role='teacher', then=1), output_field=CharField())
        ),
        new_this_month=Count(
            Case(
                When(
                    date_joined__year=now.year,
                    date_joined__month=now.month,
                    then=1
                ),
                output_field=CharField()
            )
        ),
    )

    # Get ordered users (separate query, but efficient)
    users = User.objects.select_related('userprofile').order_by('-date_joined')

    return render(request, 'user/all_users.html', {
        'users': users,
        'total_users': user_stats['total_count'],
        'student_count': user_stats['student_count'],
        'teacher_count': user_stats['teacher_count'],
        'new_this_month': user_stats['new_this_month'],
    })

@login_required(login_url='user:login')
@require_profile
@require_POST
def delete_user_view(request, user_id):
    user_to_delete = get_object_or_404(User, pk=user_id)
    if user_to_delete == request.user:
        messages.error(request, "O'z akkauntingizni o'chira olmaysiz!")
        return redirect('user:all_users')
    user_to_delete.delete()
    messages.success(request, f"Foydalanuvchi o'chirildi")
    return redirect('user:all_users')
