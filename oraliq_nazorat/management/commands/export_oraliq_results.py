"""Save the finished oraliq exam's results and student data to CSV files.

    python manage.py export_oraliq_results [--output DIR]

Run it after backing up the database and before ``manage.py migrate`` removes the
old exam (that migration also runs this export automatically as a safety net).
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from ...export import default_export_dir, export_oraliq, migration_state_apps, old_tables_exist


class Command(BaseCommand):
    help = "Eski oraliq nazorat natijalari va talabalar maʼlumotlarini CSV fayllarga eksport qiladi."

    def add_arguments(self, parser):
        parser.add_argument('--output', default=None,
                            help="Papka (default: <loyiha>/oraliq_eksport_<sana_vaqt>)")

    def handle(self, *args, **opts):
        if not old_tables_exist(connection):
            raise CommandError(
                "Eski oraliq nazorat jadvallari bazada yoʻq — ular allaqachon oʻchirilgan. "
                "Migratsiya avtomatik saqlagan oraliq_eksport_* papkasini qidiring."
            )
        out_dir = Path(opts['output']) if opts['output'] else default_export_dir()
        if out_dir.exists():
            raise CommandError(f"{out_dir} papkasi allaqachon mavjud — boshqa papka koʻrsating.")
        counts = export_oraliq(migration_state_apps(connection), out_dir)
        self.stdout.write(self.style.SUCCESS(f"Eksport saqlandi: {out_dir}"))
        for name, rows in counts.items():
            self.stdout.write(f"  {name:<26} {rows} qator")
