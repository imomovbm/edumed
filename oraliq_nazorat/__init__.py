"""Oraliq nazorat — a separate, proctored midterm exam app.

Flow
----
1. ``python manage.py setup_oraliq_nazorat`` loads the question bank, builds the
   variants (41 by default, 15 questions each), creates the student accounts
   (student1@mail.uz ... student40@mail.uz) with numeric passwords and gives every
   student a different variant.
2. A student signs in on ``/oraliq-nazorat/``, reads the rules and presses
   "Testni boshlash"; the 20-minute deadline is kept on the server.
3. Every answer is saved on the server the moment it is clicked and every action
   is written to the event log. Leaving the exam window 3 times, or the deadline,
   finishes the attempt with the answers selected so far.
4. Teachers watch everything live on ``/oraliq-nazorat/nazorat/``.
"""
