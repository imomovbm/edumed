"""What every variant is made of.

Each variant takes exactly one question from every (topic, difficulty) slot below,
so all variants have the same topics and the same difficulty mix — the fairest way
to give every student a different set of questions.
"""

# (code, label, difficulty of each question the variant takes from this topic)
TOPICS = [
    ('storage', "Taqsimlangan fayl tizimlari, obʼektli saqlash va formatlar (2-maʼruza)", (1, 2, 3)),
    ('mapreduce', "MapReduce paradigmasi (3-maʼruza)", (1, 2, 3)),
    ('spark', "Apache Spark va RDD (4-maʼruza)", (1, 2, 3)),
    ('nosql', "NoSQL, Redis, IMDG va Big Data asoslari (5-maʼruza)", (1, 2)),
    ('lakehouse', "Maʼlumotlar ombori, data lake va lakehouse (6-maʼruza)", (2, 3)),
    ('json', "JSON", (2,)),
    ('python', "Python", (2,)),
]

TOPIC_CHOICES = [(code, label) for code, label, _ in TOPICS]
TOPIC_LABELS = dict(TOPIC_CHOICES)
TOPIC_ORDER = {code: index for index, (code, _, _) in enumerate(TOPICS)}

DIFFICULTY_CHOICES = [
    (1, 'Boshlangʻich'),
    (2, 'Oʻrta'),
    (3, 'Murakkabroq'),
]

# One slot = one question of every variant.
SLOTS = [(code, difficulty) for code, _, pattern in TOPICS for difficulty in pattern]
QUESTIONS_PER_VARIANT = len(SLOTS)  # 15

OPTION_LETTERS = 'ABCDEFGH'
