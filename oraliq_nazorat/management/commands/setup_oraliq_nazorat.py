"""Create the midterm exam: question bank, variants and student accounts.

    python manage.py setup_oraliq_nazorat

* loads the question bank (oraliq_nazorat/bank) into the database,
* builds the variants (41 by default, 15 questions each, same topics and
  difficulty mix in every variant),
* creates student1@mail.uz ... student40@mail.uz with different numeric passwords
  and gives every student a different variant,
* writes the e-mails, passwords and variant numbers to a CSV file.

Running it again changes nothing that already exists: passwords stay the same
(use --reset-passwords to make new ones) and variants are only rebuilt with
--rebuild (refused once a student has started, unless --force).
"""
import csv
import random
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from user.models import UserProfile

from ...bank import load_bank, validate_bank
from ...blueprint import QUESTIONS_PER_VARIANT
from ...models import Attempt, Choice, Exam, Question, Variant, VariantQuestion
from ...variants import build_variants

DEFAULT_CODE = 'big-data-oraliq'


def numeric_password(length, taken):
    """A random numeric password: no leading zero (Excel would drop it), not too simple."""
    for _ in range(10_000):
        low = 10 ** (length - 1)
        password = str(low + secrets.randbelow(9 * low))
        if len(set(password)) >= 3 and password not in taken and password not in '01234567890' \
                and password not in '98765432109':
            taken.add(password)
            return password
    raise CommandError("Parol yaratib boʻlmadi — uzunlikni oshiring.")


class Command(BaseCommand):
    help = "Oraliq nazorat: savollar banki, variantlar va talabalar hisoblarini yaratadi."

    def add_arguments(self, parser):
        parser.add_argument('--code', default=DEFAULT_CODE, help="Imtihon kodi (default: %(default)s)")
        parser.add_argument('--title', default=None, help="Imtihon nomi")
        parser.add_argument('--subject', default=None, help="Fan nomi")
        parser.add_argument('--students', type=int, default=40, help="Talabalar soni (default: 40)")
        parser.add_argument('--first', type=int, default=1, help="Birinchi talaba raqami (default: 1)")
        parser.add_argument('--variants', type=int, default=41, help="Variantlar soni (default: 41)")
        parser.add_argument('--duration', type=int, default=None, help="Davomiyligi, daqiqa (default: 20)")
        parser.add_argument('--max-leaves', type=int, default=None, help="Oynadan chiqish limiti (default: 3)")
        parser.add_argument('--email-pattern', default='student{n}@mail.uz',
                            help="Email shabloni, {n} — talaba raqami (default: %(default)s)")
        parser.add_argument('--password-length', type=int, default=6, help="Parol uzunligi (default: 6)")
        parser.add_argument('--reset-passwords', action='store_true',
                            help="Mavjud talabalarga ham yangi parol berish")
        parser.add_argument('--rebuild', action='store_true', help="Savollar va variantlarni qayta yaratish")
        parser.add_argument('--force', action='store_true',
                            help="--rebuild bilan: boshlangan/yakunlangan urinishlarni ham OʻCHIRIB qayta yaratish")
        parser.add_argument('--seed', type=int, default=2026, help="Variantlar uchun seed (default: 2026)")
        parser.add_argument('--closed', action='store_true',
                            help="Imtihonni yopiq holatda yaratish (nazoratchi keyin ochadi)")
        parser.add_argument('--output', default=None,
                            help="CSV fayl yoʻli (default: <loyiha>/oraliq_nazorat_parollar.csv)")

    def handle(self, *args, **opts):
        if not 1 <= opts['students'] <= 1000:
            raise CommandError("--students 1 dan 1000 gacha boʻlishi kerak.")
        if opts['variants'] < 1:
            raise CommandError("--variants kamida 1 boʻlishi kerak.")
        if not 4 <= opts['password_length'] <= 12:
            raise CommandError("--password-length 4 dan 12 gacha boʻlishi kerak.")
        if '{n}' not in opts['email_pattern']:
            raise CommandError("--email-pattern da {n} boʻlishi kerak, masalan student{n}@mail.uz")

        bank = load_bank()
        problems = validate_bank(bank, opts['variants'])
        if problems:
            raise CommandError("Savollar bankida xatolar:\n  " + "\n  ".join(problems))

        with transaction.atomic():
            exam, created = self._exam(opts)
            rebuilt = self._questions_and_variants(exam, bank, opts, created)
            rows = self._students(exam, opts)

        self._write_csv(exam, rows, opts)
        self._report(exam, rows, created, rebuilt)

    # ── steps ─────────────────────────────────────────────────────────────────

    def _exam(self, opts):
        defaults = {
            'title': opts['title'] or "Big Data tahlili — oraliq nazorat",
            'subject': opts['subject'] or "Big Data tahlili",
            'duration_minutes': opts['duration'] or 20,
            'max_leaves': opts['max_leaves'] or 3,
            'is_open': not opts['closed'],
        }
        exam, created = Exam.objects.get_or_create(code=opts['code'], defaults=defaults)
        if not created:
            changed = []
            for option, field in (('title', 'title'), ('subject', 'subject'),
                                  ('duration', 'duration_minutes'), ('max_leaves', 'max_leaves')):
                if opts[option] is not None and getattr(exam, field) != opts[option]:
                    setattr(exam, field, opts[option])
                    changed.append(field)
            if changed:
                exam.save(update_fields=changed)
        return exam, created

    def _questions_and_variants(self, exam, bank, opts, created):
        has_variants = exam.variants.exists()
        if has_variants and not opts['rebuild']:
            have = exam.variants.count()
            if have < opts['variants']:
                self.stdout.write(self.style.WARNING(
                    f"Imtihonda {have} ta variant bor; {opts['variants']} ta qilish uchun --rebuild bilan ishga tushiring."
                ))
            return False

        started = exam.attempts.exclude(status=Attempt.ASSIGNED)
        if started.exists() and not opts['force']:
            raise CommandError(
                f"{started.count()} ta talaba testni boshlagan yoki tugatgan. Variantlarni qayta yaratish "
                "ularning natijalarini oʻchiradi. Rostdan ham shunday qilmoqchi boʻlsangiz, --force qoʻshing."
            )

        report = build_variants(bank, count=opts['variants'], seed=opts['seed'])
        if report.conflicts:
            raise CommandError(
                f"Variantlarda bir-birini fosh qiladigan {report.conflicts} juft savol qoldi. "
                "Boshqa --seed bilan urinib koʻring."
            )
        self.build_report = report

        # Old attempts point at the old variants (PROTECT): they are recreated below.
        exam.attempts.all().delete()
        exam.variants.all().delete()
        exam.questions.all().delete()

        questions = Question.objects.bulk_create([
            Question(exam=exam, ref=q.ref, topic=q.topic, difficulty=q.difficulty, text=q.text, code=q.code)
            for q in bank
        ])
        by_ref = {q.ref: q for q in Question.objects.filter(exam=exam)}
        choices = []
        for q in bank:
            # Store the options in a random order so the row order never hints at the answer.
            options = [(text, text == q.correct) for text in q.options]
            random.Random(f"{opts['seed']}:{q.ref}").shuffle(options)
            choices.extend(
                Choice(question=by_ref[q.ref], text=text, is_correct=correct) for text, correct in options
            )
        Choice.objects.bulk_create(choices)

        items = []
        for number, variant_questions in enumerate(report.variants, start=1):
            variant = Variant.objects.create(exam=exam, number=number)
            items.extend(
                VariantQuestion(variant=variant, question=by_ref[q.ref], order=order)
                for order, q in enumerate(variant_questions, start=1)
            )
        VariantQuestion.objects.bulk_create(items)
        self.question_total = len(questions)
        return True

    def _students(self, exam, opts):
        taken = set()
        rows = []
        variants = list(exam.variants.order_by('number'))
        used = set(exam.attempts.values_list('variant_id', flat=True))
        free = [v for v in variants if v.pk not in used]
        random.Random(f"{opts['seed']}:assign").shuffle(free)

        for n in range(opts['first'], opts['first'] + opts['students']):
            email = opts['email_pattern'].format(n=n).strip().lower()
            user = User.objects.filter(username__iexact=email).first() or \
                User.objects.filter(email__iexact=email).first()
            password = None
            if user is None:
                password = numeric_password(opts['password_length'], taken)
                user = User.objects.create_user(
                    username=email, email=email, password=password,
                    first_name='Talaba', last_name=str(n),
                )
            elif opts['reset_passwords']:
                password = numeric_password(opts['password_length'], taken)
                user.set_password(password)
                user.save(update_fields=['password'])
            UserProfile.objects.get_or_create(user=user, defaults={'role': 'student'})

            attempt = Attempt.objects.filter(exam=exam, user=user).select_related('variant').first()
            if attempt is None:
                if free:
                    variant = free.pop(0)
                else:
                    # More students than variants: reuse the least used variant.
                    counts = {v.pk: 0 for v in variants}
                    for vid in Attempt.objects.filter(exam=exam).values_list('variant_id', flat=True):
                        counts[vid] = counts.get(vid, 0) + 1
                    variant = min(variants, key=lambda v: (counts.get(v.pk, 0), v.number))
                attempt = Attempt.objects.create(exam=exam, user=user, variant=variant)
            rows.append({
                'n': n,
                'email': email,
                'name': user.get_full_name() or email,
                'password': password,
                'variant': attempt.variant.number,
                'status': attempt.get_status_display(),
            })
        return rows

    def _write_csv(self, exam, rows, opts):
        path = Path(opts['output']) if opts['output'] else Path(settings.BASE_DIR) / 'oraliq_nazorat_parollar.csv'
        if not any(r['password'] for r in rows) and path.exists():
            self.csv_path = None  # nothing new: keep the file with the passwords made earlier
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['№', 'Email (login)', 'Parol', 'F.I.Sh', 'Variant', 'Holat'])
            for r in rows:
                writer.writerow([
                    r['n'], r['email'], r['password'] or '(oʻzgarmagan)', r['name'], r['variant'], r['status'],
                ])
        self.csv_path = path

    def _report(self, exam, rows, created, rebuilt):
        out = self.stdout
        style = self.style
        out.write(style.MIGRATE_HEADING(f"\n{exam.title}  [{exam.code}]"))
        out.write(f"  Holat: {'OCHIQ' if exam.is_open else 'YOPIQ'} · {exam.duration_minutes} daqiqa · "
                  f"chiqish limiti {exam.max_leaves} · {QUESTIONS_PER_VARIANT} ta savol")
        if rebuilt:
            r = self.build_report
            out.write(style.SUCCESS(
                f"  Savollar banki: {self.question_total} ta savol · {len(r.variants)} ta variant yaratildi"
            ))
            out.write(f"  Ikki variant orasidagi umumiy savollar: eng koʻpi {r.max_overlap} ta "
                      f"(taqsimot {r.overlap_histogram}); bitta savol koʻpi bilan {r.max_usage} ta variantda")
        else:
            out.write(f"  Variantlar: {exam.variants.count()} ta (oʻzgartirilmadi)")

        out.write('')
        out.write(f"  {'№':>3}  {'Email':<24} {'Parol':<10} {'Variant':>7}")
        for r in rows:
            password = r['password'] or '—'
            out.write(f"  {r['n']:>3}  {r['email']:<24} {password:<10} {r['variant']:>7}")
        new = sum(1 for r in rows if r['password'])
        out.write('')
        if self.csv_path:
            out.write(style.SUCCESS(f"  Parollar saqlandi: {self.csv_path}"))
            out.write(style.WARNING("  Diqqat: bu faylni talabalarga koʻrsatmang va git ga qoʻshmang."))
        elif not new:
            out.write("  Yangi parol yaratilmadi (mavjud parollar oʻzgarmadi; --reset-passwords bilan yangilash mumkin).")
        free = exam.variants.exclude(pk__in=exam.attempts.values_list('variant_id', flat=True))
        spare = ', '.join(str(v.number) for v in free.order_by('number'))
        if spare:
            out.write(f"  Zaxira variant(lar): {spare} — “qayta topshirish” uchun ishlatiladi.")
        out.write("  Talabalar uchun kirish sahifasi: /oraliq-nazorat/   ·   Nazorat paneli: /oraliq-nazorat/nazorat/")
