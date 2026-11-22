"""Removed: the one-off "oraliq" midterm exam.

Only what is needed to retire it safely is left here:

* ``export_oraliq_results`` — saves the old results and student data to CSV;
* migration 0002 — runs that export automatically, deletes the exam's student
  accounts (student<N>@mail.uz) and drops the old tables.

Once ``manage.py migrate`` has run on every database, remove this app from
INSTALLED_APPS and delete the folder. The reusable exam platform is ``imtihon``.
"""
