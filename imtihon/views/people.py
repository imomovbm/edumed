"""Teacher panel for students and groups. All changes go through ``user.students``."""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.debug import sensitive_post_parameters

from user import students as student_service
from user.models import StudentGroup
from user.students import StudentError

from ..forms import NEW_GROUP, GroupForm, PasswordForm, StudentForm
from ..models import Attempt
from .common import proctor_required


def _student_or_404(user_id):
    return get_object_or_404(student_service.students(), pk=user_id)


def _apply_errors(form, exc):
    for field, message in exc.errors.items():
        form.add_error(field if field in form.fields else None, message)


@sensitive_post_parameters('password')
@proctor_required
def students_view(request):
    """Quick add (the form stays open for the next student) + the list with search and group filter."""
    selected_group = request.GET.get('guruh', '')
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                user = student_service.create_student(
                    form.cleaned_data['login'], form.cleaned_data['password'],
                    form.cleaned_data['full_name'], form.group_value(),
                )
            except StudentError as exc:
                _apply_errors(form, exc)
            else:
                group = user.userprofile.group
                messages.success(request, f"Talaba qoʻshildi: {user.get_full_name()} ({user.username}) — "
                                          f"{group.name}. Keyingi talabani kiriting.")
                return redirect(reverse('imtihon:manage_students') + '?' + urlencode({'guruh': group.pk}) + '#qoshish')
    else:
        form = StudentForm(initial={'group': selected_group} if selected_group.isdigit() else None)

    query = (request.GET.get('q') or '').strip()
    people = student_service.students().annotate(
        attempt_total=Count('imtihon_attempts', filter=~Q(imtihon_attempts__status=Attempt.ASSIGNED)),
    )
    if query:
        people = people.filter(Q(username__icontains=query) | Q(first_name__icontains=query)
                               | Q(last_name__icontains=query))
    if selected_group == 'none':
        people = people.filter(userprofile__group__isnull=True)
    elif selected_group.isdigit():
        people = people.filter(userprofile__group_id=int(selected_group))
    return render(request, 'imtihon/manage/students.html', {
        'form': form,
        'people': people,
        'query': query,
        'selected_group': selected_group,
        'groups': student_service.groups_with_counts(),
        'total': student_service.students().count(),
        'new_group_value': NEW_GROUP,
        'nav': 'students',
    })


@sensitive_post_parameters('password')
@proctor_required
def student_edit_view(request, user_id):
    user = _student_or_404(user_id)
    profile = user.userprofile
    initial = {'login': user.username, 'full_name': user.get_full_name(),
               'group': str(profile.group_id) if profile.group_id else ''}
    form = StudentForm(initial=initial, with_password=False)
    password_form = PasswordForm()
    if request.method == 'POST':
        if request.POST.get('action') == 'password':
            password_form = PasswordForm(request.POST)
            if password_form.is_valid():
                try:
                    student_service.set_student_password(user, password_form.cleaned_data['password'])
                except StudentError as exc:
                    _apply_errors(password_form, exc)
                else:
                    messages.success(request, "Yangi parol saqlandi. Uni talabaga ayting — tizim parolni "
                                              "boshqa koʻrsatmaydi.")
                    return redirect('imtihon:manage_student', user_id=user.pk)
        else:
            form = StudentForm(request.POST, with_password=False)
            if form.is_valid():
                try:
                    student_service.update_student(user, form.cleaned_data['login'],
                                                   form.cleaned_data['full_name'], form.group_value())
                except StudentError as exc:
                    _apply_errors(form, exc)
                else:
                    messages.success(request, "Talaba maʼlumotlari saqlandi.")
                    return redirect('imtihon:manage_students')
    return render(request, 'imtihon/manage/student.html', {
        'student': user,
        'form': form,
        'password_form': password_form,
        'new_group_value': NEW_GROUP,
        'attempts': Attempt.objects.filter(user=user).select_related('exam').order_by('-started_at'),
        'nav': 'students',
    })


@proctor_required
def student_delete_view(request, user_id):
    user = _student_or_404(user_id)
    results = Attempt.objects.filter(user=user).exclude(status=Attempt.ASSIGNED).count()
    if request.method == 'POST':
        name = user.get_full_name() or user.username
        user.delete()
        messages.success(request, f"Talaba oʻchirildi: {name}.")
        return redirect('imtihon:manage_students')
    return render(request, 'imtihon/manage/confirm_delete.html', {
        'nav': 'students',
        'title': "Talabani oʻchirish",
        'object_name': f"{user.get_full_name()} ({user.username})",
        'warnings': ["Hisob butunlay oʻchiriladi — talaba tizimga kira olmaydi."]
                    + ([f"Talabaning {results} ta imtihon natijasi ham oʻchadi."] if results else []),
        'cancel_url': reverse('imtihon:manage_student', args=[user.pk]),
    })


@proctor_required
def groups_view(request):
    form = GroupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            group = student_service.create_group(form.cleaned_data['name'])
        except StudentError as exc:
            form.add_error('name', exc.errors.get('group'))
        else:
            messages.success(request, f"Guruh yaratildi: {group.name}.")
            return redirect('imtihon:manage_groups')
    groups = student_service.groups_with_counts().annotate(exam_count=Count('exams', distinct=True))
    return render(request, 'imtihon/manage/groups.html', {'form': form, 'groups': groups, 'nav': 'groups'})


@proctor_required
def group_edit_view(request, group_id):
    group = get_object_or_404(StudentGroup, pk=group_id)
    form = GroupForm(request.POST or None, initial={'name': group.name})
    if request.method == 'POST' and form.is_valid():
        try:
            student_service.rename_group(group, form.cleaned_data['name'])
        except StudentError as exc:
            form.add_error('name', exc.errors.get('group'))
        else:
            messages.success(request, f"Guruh nomi oʻzgartirildi: {group.name}.")
            return redirect('imtihon:manage_groups')
    return render(request, 'imtihon/manage/group.html', {
        'group': group,
        'form': form,
        'members': group.members.select_related('user').order_by('user__first_name'),
        'nav': 'groups',
    })


@proctor_required
def group_delete_view(request, group_id):
    group = get_object_or_404(StudentGroup, pk=group_id)
    members = group.members.count()
    exams = group.exams.count()
    if request.method == 'POST':
        name = group.name
        group.delete()
        messages.success(request, f"Guruh oʻchirildi: {name}." + (f" {members} ta talaba guruhsiz qoldi." if members else ""))
        return redirect('imtihon:manage_groups')
    warnings = []
    if members:
        warnings.append(f"Guruhda {members} ta talaba bor. Ular oʻchirilmaydi, lekin guruhsiz qoladi "
                        f"va bu guruhga biriktirilgan imtihonlarni koʻrmay qoladi.")
    if exams:
        warnings.append(f"Guruh {exams} ta imtihonga biriktirilgan — bu bogʻlanishlar oʻchadi.")
    return render(request, 'imtihon/manage/confirm_delete.html', {
        'nav': 'groups',
        'title': "Guruhni oʻchirish",
        'object_name': group.name,
        'warnings': warnings,
        'cancel_url': reverse('imtihon:manage_groups'),
    })
