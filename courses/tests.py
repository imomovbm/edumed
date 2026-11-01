import json
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from edumed.test_utils import (
    EdumedTestCase, choice_id, make_question, make_quiz, make_topic, make_user,
)

from .grading import apply_manual_grade, pending_text_answers
from .models import (
    Forum, ForumComment, Question, Quiz, Response, ResponseDetails, Topic,
    TopicComment, TopicProgress, TopicSection,
)


class AccessControlTests(EdumedTestCase):
    ADMIN_PAGES = [
        ('courses:all_questions', []), ('courses:add_question', []),
        ('courses:all_quizzes', []), ('courses:add_quiz', []),
        ('courses:create_topic', []), ('courses:report_csv', []),
        ('user:all_users', []),
    ]

    def test_students_cannot_open_admin_pages(self):
        self.login(self.student)
        for name, args in self.ADMIN_PAGES:
            response = self.client.get(reverse(name, args=args))
            self.assertRedirects(response, reverse('courses:index'), msg_prefix=name)

    def test_teachers_and_moderators_are_not_admins(self):
        for user in (self.teacher, self.moder):
            self.login(user)
            response = self.client.get(reverse('courses:add_question'))
            self.assertEqual(response.status_code, 302)

    def test_admin_can_open_admin_pages(self):
        self.login(self.admin)
        for name, args in self.ADMIN_PAGES:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 200, name)

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(reverse('courses:topics'))
        self.assertRedirects(response, reverse('user:login') + '?next=' + reverse('courses:topics'))

    def test_student_cannot_delete_or_edit_content(self):
        topic = make_topic()
        question = make_question('Q?', 'sha')
        quiz = make_quiz('Quiz', [question])
        self.login(self.student)
        self.client.post(reverse('courses:delete_topic', args=[topic.id]))
        self.client.post(reverse('courses:delete_question', args=[question.id]))
        self.client.post(reverse('courses:delete_quiz', args=[quiz.id]))
        self.client.post(reverse('courses:save_question'), {'question_text': 'x', 'type': 'sha'})
        self.client.post(reverse('courses:create_topic'), {'title': 'Hack', 'sections_json': '[]'})
        self.assertTrue(Topic.objects.filter(pk=topic.pk).exists())
        self.assertTrue(Question.objects.filter(pk=question.pk).exists())
        self.assertTrue(Quiz.objects.filter(pk=quiz.pk).exists())
        self.assertFalse(Question.objects.filter(question_text='x').exists())
        self.assertFalse(Topic.objects.filter(title='Hack').exists())

    def test_superuser_without_profile_becomes_superadmin(self):
        boss = make_user('boss@edumed.uz', role=None)
        boss.is_superuser = boss.is_staff = True
        boss.save()
        self.login(boss)
        response = self.client.get(reverse('courses:all_questions'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(boss.userprofile.role, 'superadmin')


class GradingTests(EdumedTestCase):
    def setUp(self):
        self.topic = make_topic()
        self.tf = make_question('Yurak 4 kamerali?', 'tf', correct=(0,))
        self.mc = make_question('Poytaxt?', 'mc', ['Toshkent', 'Samarqand', 'Buxoro'], correct=(0,))
        self.ms = make_question('Tub sonlar?', 'ms', ['2', '3', '4'], correct=(0, 1))
        self.sha = make_question('Qisqa javob', 'sha')
        self.quiz = make_quiz('Aralash test', [self.tf, self.mc, self.ms, self.sha], topic=self.topic)
        self.login(self.student)

    def submit(self, data):
        self.client.post(reverse('courses:submit_quiz', args=[self.quiz.id]), data)
        return Response.objects.filter(user=self.student).latest('id')

    def test_true_false_answer_is_graded_correctly(self):
        resp = self.submit({f'q_{self.tf.id}': choice_id(self.tf, "To'g'ri")})
        self.assertEqual(resp.correct_count, 1)
        wrong = self.submit({f'q_{self.tf.id}': choice_id(self.tf, "Noto'g'ri")})
        self.assertEqual(wrong.correct_count, 0)
        self.assertEqual(wrong.incorrect_count, 1)

    def test_true_false_legacy_values_still_work(self):
        resp = self.submit({f'q_{self.tf.id}': 'true'})
        self.assertEqual(resp.correct_count, 1)

    def test_multi_select_needs_exact_set_and_marks_rows(self):
        resp = self.submit({f'q_{self.ms.id}': [choice_id(self.ms, '2'), choice_id(self.ms, '3')]})
        self.assertEqual(resp.correct_count, 1)
        rows = ResponseDetails.objects.filter(response=resp, question=self.ms)
        self.assertEqual(set(rows.values_list('is_correct', flat=True)), {True})
        partial = self.submit({f'q_{self.ms.id}': [choice_id(self.ms, '2')]})
        self.assertEqual(partial.correct_count, 0)

    def test_every_question_is_recorded_and_counts_add_up(self):
        resp = self.submit({f'q_{self.mc.id}': choice_id(self.mc, 'Toshkent')})
        self.assertEqual(ResponseDetails.objects.filter(response=resp).values('question').distinct().count(), 4)
        self.assertEqual(resp.correct_count + resp.incorrect_count + resp.skipped_count, 4)
        self.assertEqual(resp.score, 25.0)

    def test_tampered_values_do_not_crash(self):
        resp = self.submit({f'q_{self.mc.id}': 'abc', f'q_{self.ms.id}': ['x', '999999']})
        self.assertEqual(resp.incorrect_count, 1)  # mc answered with garbage
        self.assertEqual(resp.skipped_count, 3)

    def test_teacher_grades_text_answer(self):
        resp = self.submit({
            f'q_{self.tf.id}': choice_id(self.tf, "To'g'ri"),
            f'q_{self.sha.id}': 'Yurak qon aylanishini taminlaydi',
        })
        self.assertEqual(resp.score, 25.0)
        detail = pending_text_answers().get(response=resp)

        self.login(self.student)
        self.client.post(reverse('courses:grade_answer', args=[detail.id]), {'verdict': 'correct'})
        detail.refresh_from_db()
        self.assertIsNone(detail.is_correct)  # students cannot grade

        self.login(self.teacher)
        self.client.post(reverse('courses:grade_answer', args=[detail.id]),
                         {'verdict': 'correct', 'feedback': 'Barakalla'})
        resp.refresh_from_db()
        detail.refresh_from_db()
        self.assertTrue(detail.is_correct)
        self.assertEqual(detail.feedback, 'Barakalla')
        self.assertEqual((resp.correct_count, resp.skipped_count), (2, 2))
        self.assertEqual(resp.score, 50.0)

        # Changing the decision keeps the totals consistent.
        apply_manual_grade(detail, False)
        resp.refresh_from_db()
        self.assertEqual((resp.correct_count, resp.incorrect_count, resp.skipped_count), (1, 1, 2))

    def test_grading_page_lists_pending_results(self):
        self.submit({f'q_{self.sha.id}': 'javob'})
        self.login(self.teacher)
        response = self.client.get(reverse('courses:grading'))
        self.assertContains(response, self.student.get_full_name())
        self.assertEqual(response.context['total_pending'], 1)

    def test_topic_progress_follows_results(self):
        self.submit({f'q_{self.mc.id}': choice_id(self.mc, 'Buxoro')})
        progress = TopicProgress.objects.get(user=self.student, topic=self.topic)
        self.assertEqual((progress.status, progress.progress), ('in_progress', 0))

        easy = make_quiz('Oson', [make_question('2+2=4?', 'tf', correct=(0,))], topic=self.topic)
        self.quiz.delete()
        q = easy.quizquestion_set.get().question
        self.client.post(reverse('courses:submit_quiz', args=[easy.id]), {f'q_{q.id}': choice_id(q, "To'g'ri")})
        progress = TopicProgress.objects.get(user=self.student, topic=self.topic)
        self.assertEqual((progress.status, progress.progress), ('completed', 100))


class ResultPagesTests(EdumedTestCase):
    def setUp(self):
        self.question = make_question('Savol?', 'mc', ['A', 'B'], correct=(0,))
        self.quiz = make_quiz('Test', [self.question])
        self.login(self.student)
        self.client.post(reverse('courses:submit_quiz', args=[self.quiz.id]),
                         {f'q_{self.question.id}': choice_id(self.question, 'B')})
        self.resp = Response.objects.get(user=self.student)

    def test_owner_sees_details_and_correct_answer(self):
        response = self.client.get(reverse('courses:score_details', args=[self.resp.id]))
        self.assertContains(response, "To'g'ri javob: A")

    def test_other_students_cannot_see_details(self):
        self.login(self.other)
        for url in (reverse('courses:score_details', args=[self.resp.id]) + f'?user={self.student.id}',
                    reverse('courses:score_view', args=[self.resp.id])):
            self.assertRedirects(self.client.get(url), reverse('user:index'))

    def test_teacher_can_see_details(self):
        self.login(self.teacher)
        response = self.client.get(reverse('courses:score_details', args=[self.resp.id]))
        self.assertEqual(response.status_code, 200)

    def test_details_survive_deleted_question_and_quiz(self):
        self.question.delete()
        response = self.client.get(reverse('courses:score_details', args=[self.resp.id]))
        self.assertContains(response, "o'chirilgan")
        self.quiz.delete()
        for name in ('courses:score_details', 'courses:score_view'):
            self.assertEqual(self.client.get(reverse(name, args=[self.resp.id])).status_code, 200)


class QuestionEditorTests(EdumedTestCase):
    def setUp(self):
        self.login(self.admin)

    def test_removed_middle_choice_does_not_drop_later_ones(self):
        self.client.post(reverse('courses:save_question'), {
            'question_text': 'Gap', 'type': 'mc',
            'choice_text_1': 'A', 'choice_text_3': 'C', 'choice_text_4': 'D', 'correct_choice': '4',
        })
        question = Question.objects.get(question_text='Gap')
        self.assertEqual(list(question.questionchoice_set.order_by('id').values_list('choice_text', flat=True)), ['A', 'C', 'D'])
        self.assertEqual(question.questionchoice_set.get(is_correct=True).choice_text, 'D')

    def test_validation_errors_keep_the_form(self):
        response = self.client.post(reverse('courses:save_question'), {
            'question_text': 'Hech qaysi to\'g\'ri emas', 'type': 'mc',
            'choice_text_1': 'A', 'choice_text_2': 'B',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitta to&#x27;g&#x27;ri javobni belgilang.")
        self.assertFalse(Question.objects.exists())
        response = self.client.post(reverse('courses:save_question'), {'question_text': 'TF', 'type': 'tf'})
        self.assertFalse(Question.objects.exists())

    def test_editing_keeps_choice_rows_so_old_answers_survive(self):
        question = make_question('Rang?', 'mc', ['Qizil "yorqin"', 'Ko\'k'], correct=(0,))
        first, second = question.questionchoice_set.order_by('id')
        self.client.post(reverse('courses:edit_question', args=[question.id]), {
            'question_text': 'Rang? (tahrir)', 'type': 'mc',
            'choice_text_1': 'Qizil "yorqin"', 'choice_id_1': first.id,
            'choice_text_2': "Ko'k", 'choice_id_2': second.id,
            'choice_text_3': 'Yashil', 'correct_choice': '2',
        })
        self.assertEqual(
            list(question.questionchoice_set.order_by('id').values_list('id', 'choice_text', 'is_correct')),
            [(first.id, 'Qizil "yorqin"', False), (second.id, "Ko'k", True),
             (question.questionchoice_set.get(choice_text='Yashil').id, 'Yashil', False)],
        )

    def test_true_false_edit_preselects_answer_and_keeps_choices(self):
        question = make_question('Rostmi?', 'tf', correct=(1,))  # correct = "Noto'g'ri"
        response = self.client.get(reverse('courses:edit_question', args=[question.id]))
        self.assertEqual(response.context['init']['tf_answer'], 'false')
        ids = set(question.questionchoice_set.values_list('id', flat=True))
        self.client.post(reverse('courses:edit_question', args=[question.id]),
                         {'question_text': 'Rostmi?', 'type': 'tf', 'tf_answer': 'true'})
        self.assertEqual(set(question.questionchoice_set.values_list('id', flat=True)), ids)
        self.assertEqual(question.questionchoice_set.get(is_correct=True).choice_text, "To'g'ri")

    def test_choice_text_is_escaped_in_editor(self):
        question = make_question('X', 'mc', ['</script><b>x</b>', 'y'], correct=(0,))
        response = self.client.get(reverse('courses:edit_question', args=[question.id]))
        self.assertNotContains(response, '</script><b>x</b>')


class QuizEditorTests(EdumedTestCase):
    def setUp(self):
        self.login(self.admin)
        self.topic = make_topic()
        self.q1 = make_question('Bir', 'sha')
        self.q2 = make_question('Ikki', 'sha')

    def test_topic_quiz_needs_topic_and_general_quiz_drops_it(self):
        self.client.post(reverse('courses:save_quiz'), {'title': 'T', 'type': '1', 'question_ids': [self.q1.id]})
        self.assertFalse(Quiz.objects.exists())
        self.client.post(reverse('courses:save_quiz'), {
            'title': 'G', 'type': '2', 'topic': self.topic.id, 'duration': '30',
            'question_ids': [self.q2.id, self.q1.id, self.q2.id],
        })
        quiz = Quiz.objects.get()
        self.assertIsNone(quiz.topic)
        self.assertEqual(quiz.duration, 30)
        self.assertEqual(list(quiz.quizquestion_set.order_by('order').values_list('question_id', flat=True)),
                         [self.q2.id, self.q1.id])

    def test_edit_errors_return_to_edit_page(self):
        quiz = make_quiz('E', [self.q1])
        response = self.client.post(reverse('courses:edit_quiz', args=[quiz.id]), {'title': '', 'type': '2'})
        self.assertRedirects(response, reverse('courses:edit_quiz', args=[quiz.id]))

    def test_question_text_with_quotes_is_safe_in_picker(self):
        make_question('Uning "nomi" </script> nima?', 'sha')
        response = self.client.get(reverse('courses:add_quiz'))
        self.assertNotContains(response, 'nomi" </script>')
        self.assertContains(response, 'id="quiz-questions"')


class TopicEditorTests(EdumedTestCase):
    def setUp(self):
        self.login(self.admin)
        self.topic = make_topic()
        section = TopicSection.objects.create(topic=self.topic, type='text', title='Kirish')
        section.items.create(text='Matn')

    def test_broken_or_missing_sections_json_keeps_content(self):
        url = reverse('courses:edit_topic', args=[self.topic.id])
        self.client.post(url, {'title': 'Yangi nom', 'sections_json': ''})
        self.client.post(url, {'title': 'Yangi nom', 'sections_json': '{oops'})
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.title, 'Yangi nom')
        self.assertEqual(self.topic.sections.count(), 1)

    def test_sections_are_saved_and_cleaned(self):
        payload = [
            {'type': 'timeline', 'title': 'Tarix', 'items': [{'label': 'L' * 300, 'text': '1860'}, {'text': ''}]},
            {'type': 'evil', 'title': '', 'items': [{'text': 'oddiy matn'}]},
            {'type': 'quote', 'title': '', 'items': [{'text': ''}]},
        ]
        self.client.post(reverse('courses:edit_topic', args=[self.topic.id]),
                         {'title': 'T', 'icon': 'fa-history"><script>', 'sections_json': json.dumps(payload)})
        sections = list(self.topic.sections.all())
        self.assertEqual([s.type for s in sections], ['timeline', 'text'])
        self.assertEqual(sections[0].items.count(), 1)
        self.assertEqual(len(sections[0].items.get().label), 100)
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.icon, 'fa-book')

    def test_editor_embeds_content_safely(self):
        self.topic.sections.get().items.update(text='</script><script>alert(1)</script>')
        response = self.client.get(reverse('courses:edit_topic', args=[self.topic.id]))
        self.assertNotContains(response, '</script><script>alert(1)')

    def test_delete_topic_redirects_to_topic_list(self):
        response = self.client.post(reverse('courses:delete_topic', args=[self.topic.id]))
        self.assertRedirects(response, reverse('courses:topics'))
        self.assertFalse(Topic.objects.exists())


class QuizAttemptTests(EdumedTestCase):
    def setUp(self):
        self.question = make_question('Savol', 'tf', correct=(0,))
        self.quiz = make_quiz('Vaqtli test', [self.question], duration=10)
        self.login(self.student)
        self.url = reverse('courses:quiz_attempt', args=[self.quiz.id])

    def test_quiz_without_questions_is_not_opened(self):
        empty = make_quiz('Bo\'sh', [])
        response = self.client.get(reverse('courses:quiz_attempt', args=[empty.id]))
        self.assertRedirects(response, reverse('courses:quizzes'))

    def test_reload_keeps_timer_and_violations(self):
        first = self.client.get(self.url)
        self.assertEqual(first.context['quiz_duration'], 10)
        self.client.post(reverse('courses:log_violation'),
                         json.dumps({'quiz_id': self.quiz.id, 'count': 2}), content_type='application/json')
        second = self.client.get(self.url)
        self.assertEqual(first.context['attempt_token'], second.context['attempt_token'])
        self.assertLessEqual(second.context['remaining_seconds'], 600)
        self.assertEqual(second.context['initial_violations'], 2)

    def test_double_submit_creates_one_result_with_violations(self):
        token = self.client.get(self.url).context['attempt_token']
        data = {'attempt_token': token, 'violations': '1', f'q_{self.question.id}': choice_id(self.question, "To'g'ri")}
        url = reverse('courses:submit_quiz', args=[self.quiz.id])
        first = self.client.post(url, data)
        second = self.client.post(url, data)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(first['Location'], second['Location'])
        self.assertEqual(Response.objects.get().violation_count, 1)

    def test_attempt_page_renders_true_false_choices(self):
        response = self.client.get(self.url)
        true_choice = choice_id(self.question, "To'g'ri")
        self.assertContains(response, f'value="{true_choice}"')

    def test_bad_violation_payload(self):
        response = self.client.post(reverse('courses:log_violation'), 'nope', content_type='application/json')
        self.assertEqual(response.status_code, 400)


class StudentPagesTests(EdumedTestCase):
    def test_quizzes_page_lists_general_quizzes(self):
        make_quiz('Umumiy test', [make_question('Q', 'sha')])
        make_quiz('Savolsiz', [])
        self.login(self.student)
        response = self.client.get(reverse('courses:quizzes'))
        self.assertContains(response, 'Umumiy test')
        self.assertNotContains(response, 'Savolsiz')

    def test_mark_topic_without_quizzes_as_read(self):
        topic = make_topic()
        self.login(self.student)
        self.client.post(reverse('courses:update_progress', args=[topic.id]), {'status': 'completed'})
        progress = TopicProgress.objects.get(user=self.student, topic=topic)
        self.assertEqual((progress.status, progress.progress), ('completed', 100))

    def test_manual_status_ignored_for_topics_with_quizzes(self):
        topic = make_topic()
        make_quiz('Q', [make_question('Q', 'sha')], topic=topic)
        self.login(self.student)
        self.client.post(reverse('courses:update_progress', args=[topic.id]), {'status': 'completed'})
        self.assertFalse(TopicProgress.objects.filter(user=self.student, status='completed').exists())

    def test_main_pages_render(self):
        topic = make_topic(description='Tavsif')
        section = TopicSection.objects.create(topic=topic, type='keypoints', title='Muhim')
        section.items.create(text='Birinchi', sub_text='izoh')
        make_quiz('Mavzu testi', [make_question('Q', 'mc', ['a', 'b'], correct=(0,))], topic=topic)
        forum = Forum.objects.create(user=self.other, title='Savol', forum_question='Matn')
        TopicComment.objects.create(user=self.other, topic=topic, text='Zo\'r')
        self.login(self.student)
        for url in (reverse('courses:index'), reverse('courses:topics'), reverse('courses:topic', args=[topic.id]),
                    reverse('courses:forums'), reverse('courses:forum', args=[forum.id]),
                    reverse('courses:quizzes'), reverse('courses:search') + '?q=Mavzu',
                    reverse('user:index'), reverse('user:settings')):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_dashboard_is_public_and_hides_admin_links(self):
        response = self.client.get(reverse('courses:index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('courses:report_csv'))
        self.assertContains(response, 'id="monthly-labels"')


class TopicCommentTests(EdumedTestCase):
    def setUp(self):
        self.topic = make_topic()
        self.url = reverse('courses:topic', args=[self.topic.id])

    def test_blank_comments_are_rejected(self):
        self.login(self.student)
        self.client.post(self.url, {'comment_text': '   '})
        self.assertFalse(TopicComment.objects.exists())
        self.client.post(self.url, {'comment_text': 'Savolim bor'})
        self.assertEqual(TopicComment.objects.get().text, 'Savolim bor')

    def test_like_link_no_longer_works_with_get(self):
        comment = TopicComment.objects.create(user=self.other, topic=self.topic, text='x')
        self.login(self.student)
        self.assertEqual(self.client.get(reverse('courses:like_comment', args=[comment.id])).status_code, 405)
        self.client.post(reverse('courses:toggle_vote'), json.dumps({'type': 'tcomment', 'id': comment.id, 'action': 'like'}),
                         content_type='application/json')
        self.assertEqual(comment.likes.count(), 1)

    def test_only_author_or_moderator_deletes(self):
        comment = TopicComment.objects.create(user=self.other, topic=self.topic, text='x')
        self.login(self.student)
        self.client.post(reverse('courses:delete_topic_comment', args=[comment.id]))
        self.assertTrue(TopicComment.objects.exists())
        self.login(self.moder)
        self.client.post(reverse('courses:delete_topic_comment', args=[comment.id]))
        self.assertFalse(TopicComment.objects.exists())


class ForumTests(EdumedTestCase):
    def setUp(self):
        self.forum = Forum.objects.create(user=self.other, title='Forum', forum_question='Savol?')

    def vote(self, payload):
        return self.client.post(reverse('courses:toggle_vote'), json.dumps(payload), content_type='application/json')

    def test_vote_toggle_and_switch(self):
        self.login(self.student)
        data = self.vote({'type': 'forum', 'id': self.forum.id, 'action': 'like'}).json()
        self.assertEqual((data['likes'], data['liked']), (1, True))
        data = self.vote({'type': 'forum', 'id': self.forum.id, 'action': 'dislike'}).json()
        self.assertEqual((data['likes'], data['dislikes'], data['disliked']), (0, 1, True))
        data = self.vote({'type': 'forum', 'id': self.forum.id, 'action': 'dislike'}).json()
        self.assertEqual(data['dislikes'], 0)

    def test_bad_vote_requests(self):
        self.login(self.student)
        self.assertEqual(self.client.post(reverse('courses:toggle_vote'), 'x', content_type='application/json').status_code, 400)
        self.assertEqual(self.vote({'type': 'forum', 'id': 'abc', 'action': 'like'}).status_code, 400)
        self.assertEqual(self.vote({'type': 'forum', 'id': 99999, 'action': 'like'}).status_code, 404)

    def test_replies_attach_to_top_level_comment_of_same_forum(self):
        top = ForumComment.objects.create(user=self.other, forum=self.forum, text='top')
        reply = ForumComment.objects.create(user=self.other, forum=self.forum, text='reply', parent=top)
        foreign = ForumComment.objects.create(
            user=self.other, forum=Forum.objects.create(user=self.other, title='B', forum_question='?'), text='f')
        self.login(self.student)
        url = reverse('courses:post_comment', args=[self.forum.id])
        self.client.post(url, {'text': 'javobga javob', 'comment_id': reply.id})
        self.client.post(url, {'text': 'boshqa forum', 'comment_id': foreign.id})
        self.assertEqual(ForumComment.objects.get(text='javobga javob').parent, top)
        self.assertIsNone(ForumComment.objects.get(text='boshqa forum').parent)

    def test_counts_are_not_inflated_by_likes(self):
        comment = ForumComment.objects.create(user=self.other, forum=self.forum, text='c')
        comment.likes.add(self.student, self.teacher, self.admin)
        response = self.client.get(reverse('courses:forums'))
        top = list(response.context['top_contributors'])[0]
        self.assertEqual((top['comment_count'], top['like_count']), (1, 3))

    def test_search_with_special_characters(self):
        response = self.client.get(reverse('courses:forums') + '?q=a%26b&sort=top')
        self.assertEqual(response.status_code, 200)
        self.assertIn('q=a%26b', response.context['base_qs'])

    def test_delete_rules(self):
        self.login(self.student)
        self.client.post(reverse('courses:delete_forum', args=[self.forum.id]))
        self.assertTrue(Forum.objects.exists())
        self.login(self.other)
        self.client.post(reverse('courses:delete_forum', args=[self.forum.id]))
        self.assertFalse(Forum.objects.exists())

    def test_create_forum_goes_to_new_post(self):
        self.login(self.student)
        response = self.client.post(reverse('courses:forums'), {'title': 'Yangi', 'forum_question': 'Matn'})
        forum = Forum.objects.get(title='Yangi')
        self.assertRedirects(response, reverse('courses:forum', args=[forum.id]))


class ReportAndSearchTests(EdumedTestCase):
    def test_csv_report(self):
        evil = make_user('=cmd@x.uz')
        evil.first_name = '=HYPERLINK("x")'
        evil.save()
        quiz = make_quiz('Test', [make_question('Q', 'sha')])
        Response.objects.create(user=evil, quiz=quiz, score=80)
        self.login(self.admin)
        response = self.client.get(reverse('courses:report_csv'))
        content = response.content.decode('utf-8')
        self.assertTrue(content.startswith('﻿'))
        self.assertIn("'=HYPERLINK", content)
        self.assertIn('80.0', content)

    def test_search_finds_topics_and_hides_questions_from_students(self):
        make_topic('Bioetika asoslari')
        make_question('Bioetika nima?', 'sha')
        self.login(self.student)
        response = self.client.get(reverse('courses:search') + '?q=bioetika')
        self.assertContains(response, 'Bioetika asoslari')
        self.assertEqual(response.context['questions'], [])
        self.login(self.admin)
        response = self.client.get(reverse('courses:search') + '?q=bioetika')
        self.assertEqual(len(response.context['questions']), 1)


class RecalculateCommandTests(EdumedTestCase):
    def test_fixes_old_true_false_results(self):
        question = make_question('Rost?', 'tf', correct=(0,))
        quiz = make_quiz('Eski', [question], topic=make_topic())
        # What the old grader stored: text answer, no verdict, counted as incorrect.
        old = Response.objects.create(user=self.student, quiz=quiz, score=0, incorrect_count=1)
        ResponseDetails.objects.create(response=old, question=question, user_text_answer='true')

        out = StringIO()
        call_command('recalculate_scores', '--dry-run', stdout=out)
        old.refresh_from_db()
        self.assertEqual(old.score, 0)

        call_command('recalculate_scores', stdout=out)
        old.refresh_from_db()
        self.assertEqual((old.score, old.correct_count, old.incorrect_count), (100.0, 1, 0))
        self.assertEqual(TopicProgress.objects.get(user=self.student).status, 'completed')
