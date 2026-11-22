from django import forms
from django.contrib.auth.models import User
from django.db.models import Count

from user.models import StudentGroup
from user.students import MIN_PASSWORD_LENGTH, students

from .models import Exam

DATETIME_FORMAT = '%Y-%m-%dT%H:%M'
NEW_GROUP = '__new__'
# Logins and the passwords a teacher types for a student: no autocomplete, no autocorrect.
PLAIN = {'autocomplete': 'off', 'autocapitalize': 'none', 'autocorrect': 'off', 'spellcheck': 'false'}


class StudentChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, user):
        profile = getattr(user, 'userprofile', None)
        group = profile.group.name if profile and profile.group_id else 'guruhsiz'
        return f'{user.get_full_name() or user.username} · {user.username} · {group}'


class GroupChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, group):
        count = getattr(group, 'student_count', None)
        return f'{group.name} ({count} ta talaba)' if count is not None else group.name


class ExamSettingsForm(forms.ModelForm):
    """Everything a teacher sets on an exam. Question selection is locked once anyone has started."""

    LOCKED_AFTER_START = ('question_count', 'shuffle_questions', 'shuffle_options')

    groups = GroupChoiceField(
        queryset=StudentGroup.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label="Guruhlar",
    )
    students = StudentChoiceField(
        queryset=User.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label="Alohida talabalar",
    )

    class Meta:
        model = Exam
        fields = [
            'title', 'subject', 'duration_minutes', 'starts_at', 'ends_at', 'question_count',
            'shuffle_questions', 'shuffle_options', 'max_leaves', 'count_fullscreen_exit', 'show_score',
            'groups', 'students',
        ]
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DATETIME_FORMAT),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format=DATETIME_FORMAT),
        }

    def __init__(self, *args, question_total=0, has_attempts=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.question_total = question_total
        self.fields['groups'].queryset = StudentGroup.objects.annotate(student_count=Count('members'))
        self.fields['students'].queryset = students()
        for name in ('starts_at', 'ends_at'):
            self.fields[name].input_formats = [DATETIME_FORMAT, '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['title'].error_messages['required'] = "Imtihon nomini kiriting."
        self.fields['question_count'].widget.attrs.update(placeholder=f'Hammasi ({question_total})', min=1)
        self.fields['duration_minutes'].widget.attrs.update(min=1, max=600)
        self.fields['max_leaves'].widget.attrs.update(min=1, max=20)
        if has_attempts:
            for name in self.LOCKED_AFTER_START:
                self.fields[name].disabled = True
                self.fields[name].help_text = "Talabalar boshlagani uchun oʻzgartirib boʻlmaydi."

    def clean_title(self):
        title = ' '.join((self.cleaned_data.get('title') or '').split())
        if not title:
            raise forms.ValidationError("Imtihon nomini kiriting.")
        return title

    def clean_subject(self):
        return ' '.join((self.cleaned_data.get('subject') or '').split())

    def clean(self):
        data = super().clean()
        starts, ends = data.get('starts_at'), data.get('ends_at')
        if starts and ends and ends <= starts:
            self.add_error('ends_at', "Tugash vaqti boshlanish vaqtidan keyin boʻlishi kerak.")
        count = data.get('question_count')
        if count and self.question_total and count > self.question_total:
            self.add_error('question_count', f"Imtihonda faqat {self.question_total} ta savol bor.")
        return data


class GroupSelectMixin(forms.Form):
    group = forms.ChoiceField(label="Guruh", required=False)
    new_group = forms.CharField(label="Yangi guruh nomi", required=False, max_length=100)

    def setup_groups(self):
        groups = [(str(g.pk), g.name) for g in StudentGroup.objects.order_by('name')]
        self.fields['group'].choices = [('', '— guruhni tanlang —'), *groups, (NEW_GROUP, '+ Yangi guruh…')]

    def group_value(self):
        """A StudentGroup, a new group's name, or '' (the service reports what is missing)."""
        choice = self.cleaned_data.get('group')
        if choice == NEW_GROUP:
            return self.cleaned_data.get('new_group') or ''
        if choice:
            return StudentGroup.objects.filter(pk=choice).first() or ''
        return ''


class StudentForm(GroupSelectMixin):
    login = forms.CharField(label="Login", max_length=150, required=False, widget=forms.TextInput(attrs=PLAIN))
    password = forms.CharField(
        label="Parol", required=False, strip=False, widget=forms.TextInput(attrs=PLAIN),
        help_text=f"Kamida {MIN_PASSWORD_LENGTH} ta belgi; faqat raqamlar ham boʻladi. "
                  "Talabaga ayting — tizim uni keyin koʻrsatmaydi.",
    )
    full_name = forms.CharField(label="F.I.Sh", max_length=150, required=False)

    field_order = ['login', 'password', 'full_name', 'group', 'new_group']

    def __init__(self, *args, with_password=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_groups()
        if not with_password:
            del self.fields['password']


class PasswordForm(forms.Form):
    password = forms.CharField(
        label="Yangi parol", required=False, strip=False, widget=forms.TextInput(attrs=PLAIN),
        help_text=f"Kamida {MIN_PASSWORD_LENGTH} ta belgi.",
    )


class GroupForm(forms.Form):
    name = forms.CharField(label="Guruh nomi", max_length=100, required=False)
