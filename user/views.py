import re
import secrets
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.grading import progress_percent
from courses.models import Forum, ForumComment, Response, Topic, TopicProgress

from . import ai
from .choices import OTMS, REGIONS
from .models import PasswordResetRequest, UserProfile
from .permissions import (
    NO_ACCESS_MESSAGE, admin_required, get_profile, is_admin, require_profile, safe_next_url,
)

LOGIN_URL = 'user:login'
AI_COOLDOWN = timedelta(hours=6)
TEMP_PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def calculate_age(dob):
    """Calculates age from a date of birth (datetime.date object)."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _short(title, limit=22):
    return title if len(title) <= limit else title[:limit - 1] + '…'


def _parse_birth_date(value, errors):
    if not value:
        return None
    try:
        dob = datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        errors.append("Tug'ilgan sana noto'g'ri formatda kiritilgan.")
        return None
    if dob > date.today() or dob.year < 1900:
        errors.append("Tug'ilgan sana noto'g'ri.")
        return None
    return dob


def _build_profile_context(viewed_user):
    """Shared context builder for both own profile and admin user_detail."""
    viewed_profile = getattr(viewed_user, 'userprofile', None)
    dob = viewed_profile.date_of_birth if viewed_profile else None

    # ── Quiz stats ────────────────────────────────────────────────────
    responses = (
        Response.objects.filter(user=viewed_user)
        .select_related('quiz', 'quiz__topic')
        .order_by('-created_date_time')
    )
    stats = responses.aggregate(
        total=Count('id'),
        avg=Avg('score'),
        a=Count('id', filter=Q(score__gte=90)),
        b=Count('id', filter=Q(score__gte=70, score__lt=90)),
        c=Count('id', filter=Q(score__gte=50, score__lt=70)),
        d=Count('id', filter=Q(score__lt=50)),
    )

    # ── Topic progress ────────────────────────────────────────────────
    topics = list(
        Topic.objects.annotate(
            user_avg=Avg('quiz__response__score', filter=Q(quiz__response__user=viewed_user)),
            platform_avg=Avg('quiz__response__score'),
            quiz_count=Count('quiz', distinct=True),
        ).order_by('created_at')
    )
    progress_map = {}
    for p in TopicProgress.objects.filter(user=viewed_user).order_by('id'):
        progress_map.setdefault(p.topic_id, p)

    total_topics = len(topics)
    completed_topics = sum(
        1 for t in topics if progress_map.get(t.id) and progress_map[t.id].status == 'completed'
    )
    overall_progress = (
        round(sum(progress_percent(progress_map.get(t.id)) for t in topics) / total_topics)
        if total_topics else 0
    )

    topic_progress_data = []
    chart = {'labels': [], 'user': [], 'platform': []}
    for topic in topics:
        prog = progress_map.get(topic.id)
        topic_progress_data.append({
            'title':        topic.title,
            'status':       prog.status if prog else 'not_started',
            'pct':          progress_percent(prog),
            'quiz_count':   topic.quiz_count,
            'user_avg':     round(topic.user_avg) if topic.user_avg is not None else None,
            'platform_avg': round(topic.platform_avg) if topic.platform_avg is not None else None,
        })
        if topic.quiz_count:  # only topics that can actually be scored
            chart['labels'].append(_short(topic.title))
            chart['user'].append(round(topic.user_avg or 0))
            chart['platform'].append(round(topic.platform_avg or 0))

    return {
        'viewed_user':          viewed_user,
        'viewed_profile':       viewed_profile,
        'age':                  calculate_age(dob) if dob else None,
        'responses':            list(responses[:20]),   # last 20 in table
        'total_responses':      stats['total'],
        'avg_score':            round(stats['avg'] or 0),
        'score_a':              stats['a'],
        'score_b':              stats['b'],
        'score_c':              stats['c'],
        'score_d':              stats['d'],
        'total_topics':         total_topics,
        'completed_topics':     completed_topics,
        'overall_progress':     overall_progress,
        'topic_progress_data':  topic_progress_data,
        'forum_comments':       ForumComment.objects.filter(user=viewed_user).count(),
        'forum_posts':          Forum.objects.filter(user=viewed_user).count(),
        'chart_data':           chart,
    }


def _ai_context(viewed_profile):
    next_at = None
    if viewed_profile and viewed_profile.ai_analysis_at:
        candidate = viewed_profile.ai_analysis_at + AI_COOLDOWN
        if candidate > timezone.now():
            next_at = candidate
    return {'ai_enabled': ai.is_enabled(), 'ai_next_at': next_at}


# ── Own profile ───────────────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_profile
def index(request):
    ctx = _build_profile_context(request.user)
    ctx.update(_ai_context(ctx['viewed_profile']))
    ctx['is_own_profile'] = True
    return render(request, 'user/profile.html', ctx)


# ── Admin: view any user ──────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def user_detail_view(request, user_id):
    viewed_user = get_object_or_404(User.objects.select_related('userprofile'), pk=user_id)
    if viewed_user == request.user:
        return redirect('user:index')

    ctx = _build_profile_context(viewed_user)
    ctx.update(_ai_context(ctx['viewed_profile']))
    ctx['is_own_profile'] = False
    ctx['role_choices'] = UserProfile.ROLE_CHOICES
    ctx['temp_password'] = request.session.pop(f'temp_password_{viewed_user.pk}', None)
    ctx['reset_requests'] = (
        PasswordResetRequest.objects.filter(linked_user=viewed_user, is_resolved=False)
        .order_by('-requested_at')
    )
    return render(request, 'user/profile.html', ctx)


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def change_role_view(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    role = request.POST.get('role')
    roles = dict(UserProfile.ROLE_CHOICES)
    if role not in roles:
        messages.error(request, "Rolni tanlang.")
    elif target == request.user:
        messages.error(request, "O'z rolingizni o'zgartira olmaysiz.")
    else:
        profile, _ = UserProfile.objects.get_or_create(user=target, defaults={'role': role})
        if profile.role != role:
            profile.role = role
            profile.save(update_fields=['role'])
        messages.success(request, f"Foydalanuvchi roli o'zgartirildi: {roles[role]}")
    return redirect('user:user_detail', target.pk)


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def reset_password_view(request, user_id):
    """Answer a 'forgot password' request: set a temporary password and show it
    once to the administrator, who passes it on to the user."""
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        return redirect('user:settings')
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, NO_ACCESS_MESSAGE)
        return redirect('user:user_detail', target.pk)

    password = ''.join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(10))
    target.set_password(password)
    target.save(update_fields=['password'])
    PasswordResetRequest.objects.filter(linked_user=target, is_resolved=False).update(is_resolved=True)
    request.session[f'temp_password_{target.pk}'] = password
    messages.success(request, "Yangi vaqtinchalik parol yaratildi. Uni foydalanuvchiga yetkazing.")
    return redirect('user:user_detail', target.pk)


@login_required(login_url=LOGIN_URL)
@require_profile
@require_POST
def ai_analysis_view(request, user_id=None):
    """Run the (optional) Claude AI analysis for the own profile, or — for
    administrators — for any student."""
    target = request.user if user_id is None else get_object_or_404(User, pk=user_id)
    own = target == request.user
    if not own and not is_admin(request.user):
        messages.error(request, NO_ACCESS_MESSAGE)
        return redirect('user:index')
    back = (reverse('user:index') if own else reverse('user:user_detail', args=[target.pk])) + '#ai'

    profile = get_profile(target)
    if profile is None:
        messages.error(request, "Profil topilmadi.")
        return redirect(back)
    if not ai.is_enabled():
        messages.info(request, "AI tahlili hozircha yoqilmagan.")
        return redirect(back)
    if (profile.ai_analysis_at and profile.ai_analysis_at + AI_COOLDOWN > timezone.now()
            and not is_admin(request.user)):
        messages.info(request, "AI tahlili yaqinda yangilangan. Birozdan so'ng qayta urinib ko'ring.")
        return redirect(back)

    ctx = _build_profile_context(target)
    if not ctx['total_responses']:
        messages.info(request, "Tahlil uchun avval kamida bitta test topshiring.")
        return redirect(back)

    try:
        text = ai.generate_analysis(ai.build_student_payload(ctx))
    except ai.AIUnavailable as exc:
        messages.error(request, str(exc))
        return redirect(back)

    profile.ai_analysis = text
    profile.ai_analysis_at = timezone.now()
    profile.save(update_fields=['ai_analysis', 'ai_analysis_at'])
    messages.success(request, "AI tahlili tayyor.")
    return redirect(back)


def register_view(request):
    # ------------------------------------------------------------------
    # 1. CHECK IF USER IS ALREADY LOGGED IN
    if request.user.is_authenticated:
        messages.info(request, "Siz allaqachon tizimga kirgansiz.")  # You are already logged in.
        return redirect('user:index')
    # ------------------------------------------------------------------

    form = {}
    if request.method == 'POST':
        # 2. Retrieve data from the form
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'gender',
                  'region', 'otm', 'date_of_birth')
        form = {name: (request.POST.get(name) or '').strip() for name in fields}
        password = request.POST.get('password') or ''
        password2 = request.POST.get('password2') or ''
        email = form['email'].lower()

        # 3. Validation (the form is shown again with the entered data on error)
        errors = []
        if not form['first_name'] or not form['last_name']:
            errors.append("Ism va familiyani kiriting.")
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Email manzilni to'g'ri kiriting.")
        else:
            if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
                errors.append("Bu email avval ro'yxatdan o'tgan.")
        if form['gender'] not in ('0', '1'):
            errors.append("Jinsingizni tanlang.")
        if not form['date_of_birth']:
            errors.append("Tug'ilgan sanani kiriting.")
        date_of_birth = _parse_birth_date(form['date_of_birth'], errors)
        if form['region'] and form['region'] not in REGIONS:
            errors.append("Viloyatni ro'yxatdan tanlang.")
        if form['otm'] and form['otm'] not in OTMS:
            errors.append("Ta'lim muassasasini ro'yxatdan tanlang.")
        if password != password2:
            errors.append("Parollar bir xil emas!")
        else:
            probe = User(username=email, email=email,
                         first_name=form['first_name'], last_name=form['last_name'])
            try:
                validate_password(password, user=probe)
            except ValidationError as exc:
                errors.extend(exc.messages)

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "user/register.html", {'form': form, 'regions': REGIONS, 'otms': OTMS})

        # 4. Create the built-in Django User and the linked UserProfile (role 'student')
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=form['first_name'][:150],
                last_name=form['last_name'][:150],
            )
            UserProfile.objects.create(
                user=user,
                role='student',
                phone=form['phone_number'][:30] or None,
                gender=int(form['gender']),
                region=form['region'] or None,
                otm=form['otm'] or None,
                date_of_birth=date_of_birth,
            )

        # 5. Log the user in immediately after registration
        login(request, user)
        messages.success(request, "Muvaffaqiyatli ro'yxatdan o'tdingiz!")
        return redirect('user:index')

    return render(request, "user/register.html", {'form': form, 'regions': REGIONS, 'otms': OTMS})


def login_view(request):
    next_url = safe_next_url(request)

    # 1. Check if user is already logged in
    if request.user.is_authenticated:
        messages.info(request, "Siz allaqachon tizimga kirgansiz.")
        return redirect(next_url or 'user:index')

    if request.method == 'POST':
        # 2. Retrieve data from the form
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        remember_me = request.POST.get('remember_me')

        # 3. Find the account by email (case-insensitive) and check the password
        candidates = (
            User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).order_by('id')
            if email else User.objects.none()
        )
        user = None
        for candidate in candidates[:5]:
            user = authenticate(request, username=candidate.username, password=password)
            if user is not None:
                break

        if user is None:
            if not candidates.exists():
                messages.error(request, "Bunday email mavjud emas")
            else:
                messages.error(request, "Email yoki parol noto'g'ri. Iltimos, tekshirib ko'ring.")
            return render(request, "user/login.html", {'email': email, 'next': next_url})

        # 4. Login successful
        login(request, user)
        if not remember_me:
            request.session.set_expiry(0)
        messages.success(request, f"Xush kelibsiz, {user.first_name or user.username}!")
        return redirect(next_url or 'user:index')

    return render(request, "user/login.html", {'next': next_url})


def logout_view(request):
    # Logging out needs a POST (the header's logout dialog sends one), so other
    # sites cannot log users out with a simple link.
    if request.method != 'POST':
        return redirect('courses:index')
    logout(request)
    messages.info(request, "Tizimdan muvaffaqiyatli chiqdingiz.")
    return redirect('user:login')


def _find_user_by_contact(contact):
    user = User.objects.filter(email__iexact=contact).order_by('id').first()
    if user:
        return user
    digits = re.sub(r'\D', '', contact)
    if len(digits) < 7:
        return None
    tail = digits[-9:]  # ignore +998 / 8 prefixes and formatting
    for user_id, phone in (UserProfile.objects.exclude(phone__isnull=True).exclude(phone='')
                           .values_list('user_id', 'phone')):
        if re.sub(r'\D', '', phone).endswith(tail):
            return User.objects.filter(pk=user_id).first()
    return None


def forgot_password_view(request):
    if request.method == 'POST':
        # Get the input which could be email or phone number
        contact_input = (request.POST.get('contact_input') or '').strip()[:150]

        if not contact_input:
            messages.error(request, "Iltimos, email yoki telefon raqamingizni kiriting.")
            return render(request, "user/forgot_password.html")

        # Do not let one person flood the administrators with requests.
        recent = PasswordResetRequest.objects.filter(
            contact_input__iexact=contact_input,
            requested_at__gte=timezone.now() - timedelta(hours=1),
        ).count()
        if recent < 3:
            PasswordResetRequest.objects.create(
                contact_input=contact_input,
                linked_user=_find_user_by_contact(contact_input),
            )

        messages.success(request, "Rahmat, so'rovingiz qabul qilindi. Administratorlarimiz tez orada parolingizni tiklab berishadi.")
        return redirect('user:login')

    return render(request, "user/forgot_password.html")


@login_required(login_url=LOGIN_URL)
@require_profile
def settings_view(request):
    """'Sozlamalar' — edit personal data and change the password."""
    user = request.user
    profile = get_profile(user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'profile':
            first_name = (request.POST.get('first_name') or '').strip()
            last_name = (request.POST.get('last_name') or '').strip()
            phone = (request.POST.get('phone') or '').strip()
            gender = request.POST.get('gender') or ''
            region = (request.POST.get('region') or '').strip()
            otm = (request.POST.get('otm') or '').strip()
            errors = []
            if not first_name or not last_name:
                errors.append("Ism va familiyani kiriting.")
            dob = _parse_birth_date((request.POST.get('date_of_birth') or '').strip(), errors)
            if gender not in ('', '0', '1'):
                errors.append("Jinsni tanlang.")
            if region and region not in REGIONS and region != profile.region:
                errors.append("Viloyatni ro'yxatdan tanlang.")
            if otm and otm not in OTMS and otm != profile.otm:
                errors.append("Ta'lim muassasasini ro'yxatdan tanlang.")
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                user.first_name, user.last_name = first_name[:150], last_name[:150]
                user.save(update_fields=['first_name', 'last_name'])
                profile.phone = phone[:30] or None
                profile.gender = int(gender) if gender else None
                profile.region = region or None
                profile.otm = otm or None
                profile.date_of_birth = dob
                profile.save()
                messages.success(request, "Ma'lumotlaringiz saqlandi.")
            return redirect('user:settings')

        if action == 'password':
            old_password = request.POST.get('old_password') or ''
            new_password = request.POST.get('new_password') or ''
            new_password2 = request.POST.get('new_password2') or ''
            if not user.check_password(old_password):
                messages.error(request, "Joriy parol noto'g'ri.")
            elif new_password != new_password2:
                messages.error(request, "Yangi parollar bir xil emas.")
            else:
                try:
                    validate_password(new_password, user=user)
                except ValidationError as exc:
                    for error in exc.messages:
                        messages.error(request, error)
                else:
                    user.set_password(new_password)
                    user.save(update_fields=['password'])
                    update_session_auth_hash(request, user)  # stay logged in
                    messages.success(request, "Parolingiz o'zgartirildi.")
            return redirect(reverse('user:settings') + '#password')

    return render(request, 'user/settings.html', {
        'profile': profile,
        'regions': REGIONS,
        'otms': OTMS,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def all_users_view(request):
    now = timezone.now()
    user_stats = User.objects.aggregate(
        total_count=Count('id'),
        student_count=Count('id', filter=Q(userprofile__role='student')),
        teacher_count=Count('id', filter=Q(userprofile__role='teacher')),
        new_this_month=Count('id', filter=Q(date_joined__year=now.year, date_joined__month=now.month)),
    )
    users = (
        User.objects.select_related('userprofile')
        .annotate(response_count=Count('response', distinct=True))
        .order_by('-date_joined')
    )
    reset_requests = (
        PasswordResetRequest.objects.filter(is_resolved=False)
        .select_related('linked_user').order_by('-requested_at')[:50]
    )
    return render(request, 'user/all_users.html', {
        'users': users,
        'total_users': user_stats['total_count'],
        'student_count': user_stats['student_count'],
        'teacher_count': user_stats['teacher_count'],
        'new_this_month': user_stats['new_this_month'],
        'reset_requests': reset_requests,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def resolve_reset_request_view(request, request_id):
    reset_request = get_object_or_404(PasswordResetRequest, pk=request_id)
    reset_request.is_resolved = True
    reset_request.save(update_fields=['is_resolved'])
    messages.success(request, "So'rov yopildi.")
    return redirect('user:all_users')


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def delete_user_view(request, user_id):
    user_to_delete = get_object_or_404(User, pk=user_id)
    if user_to_delete == request.user:
        messages.error(request, "O'z akkauntingizni o'chira olmaysiz!")
        return redirect('user:all_users')
    if user_to_delete.is_superuser and not request.user.is_superuser:
        messages.error(request, "Bosh administratorni o'chira olmaysiz.")
        return redirect('user:all_users')
    name = user_to_delete.get_full_name() or user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f"Foydalanuvchi o'chirildi: {name}")
    return redirect('user:all_users')
