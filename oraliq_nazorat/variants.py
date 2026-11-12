"""Build exam variants from the question bank.

Every variant takes exactly one question from every slot of ``blueprint.SLOTS``
(topic + difficulty), so all variants cover the same topics with the same
difficulty mix. Within each slot the questions are used equally often; a local
search then

* removes every pair of questions that give each other away (``bank.conflicts``),
* keeps any two variants as different as possible (few shared questions).

The result depends only on the bank and the seed, so re-running the setup
command with the same seed rebuilds exactly the same variants.
"""
import math
import random
from dataclasses import dataclass

from .bank import conflicts
from .blueprint import SLOTS

CONFLICT_WEIGHT = 1_000_000


def _overlap_cost(shared):
    # 0 shared questions is ideal, 1 is fine, 2+ grows fast.
    return 0 if shared <= 0 else 4 ** (shared - 1)


@dataclass
class BuildReport:
    variants: list
    conflicts: int
    max_overlap: int
    overlap_histogram: dict
    max_usage: int


def build_variants(questions, count=41, seed=2026, iterations=120_000):
    """Return a :class:`BuildReport`; ``report.variants`` is a list of ``count``
    lists of bank questions, each in blueprint (display) order."""
    rng = random.Random(seed)
    questions = sorted(questions, key=lambda q: q.ref)
    index = {q.ref: i for i, q in enumerate(questions)}
    pools = []
    for slot in SLOTS:
        pool = [index[q.ref] for q in questions if (q.topic, q.difficulty) == slot]
        if not pool:
            raise ValueError(f'Savollar banki: {slot} uchun savol yoʻq')
        pools.append(pool)

    clash = [[False] * len(questions) for _ in questions]
    for i, a in enumerate(questions):
        for j in range(i + 1, len(questions)):
            if conflicts(a, questions[j]):
                clash[i][j] = clash[j][i] = True

    # 1. Balanced start: in every slot each question is used ⌊count/m⌋ or ⌈count/m⌉ times.
    S = len(SLOTS)
    assign = [[0] * S for _ in range(count)]
    for s, pool in enumerate(pools):
        order = pool[:]
        rng.shuffle(order)
        column = [order[k % len(order)] for k in range(count)]
        rng.shuffle(column)
        for v in range(count):
            assign[v][s] = column[v]

    members = [dict() for _ in range(S)]  # slot -> question -> set of variants
    for v in range(count):
        for s in range(S):
            members[s].setdefault(assign[v][s], set()).add(v)

    overlap = [[0] * count for _ in range(count)]
    for s in range(S):
        for group in members[s].values():
            group = sorted(group)
            for x in range(len(group)):
                for y in range(x + 1, len(group)):
                    overlap[group[x]][group[y]] += 1
                    overlap[group[y]][group[x]] += 1

    def conflicts_of(v, s, q):
        row = clash[q]
        return sum(1 for t in range(S) if t != s and row[assign[v][t]])

    # 2. Local search: swap one slot's questions between two variants (usage stays balanced).
    temperature = 2.0
    cooling = (0.02 / temperature) ** (1 / max(1, iterations))
    for _ in range(iterations):
        temperature *= cooling
        s = rng.randrange(S)
        v, w = rng.randrange(count), rng.randrange(count)
        a, b = assign[v][s], assign[w][s]
        if v == w or a == b:
            continue

        delta = CONFLICT_WEIGHT * (
            conflicts_of(v, s, b) - conflicts_of(v, s, a)
            + conflicts_of(w, s, a) - conflicts_of(w, s, b)
        )
        changes = []
        for u in members[s][a]:
            if u != v:
                changes.append((v, u, -1))
                changes.append((w, u, +1))
        for u in members[s][b]:
            if u != w:
                changes.append((w, u, -1))
                changes.append((v, u, +1))
        for x, y, d in changes:
            delta += _overlap_cost(overlap[x][y] + d) - _overlap_cost(overlap[x][y])

        if delta > 0 and rng.random() >= math.exp(-delta / temperature):
            continue
        if delta == 0 and rng.random() < 0.5:
            continue
        assign[v][s], assign[w][s] = b, a
        members[s][a].discard(v)
        members[s][a].add(w)
        members[s][b].discard(w)
        members[s][b].add(v)
        for x, y, d in changes:
            overlap[x][y] += d
            overlap[y][x] += d

    total_conflicts = sum(
        1
        for v in range(count)
        for s in range(S)
        for t in range(s + 1, S)
        if clash[assign[v][s]][assign[v][t]]
    )
    histogram = {}
    for v in range(count):
        for w in range(v + 1, count):
            histogram[overlap[v][w]] = histogram.get(overlap[v][w], 0) + 1
    usage = {}
    for v in range(count):
        for s in range(S):
            usage[assign[v][s]] = usage.get(assign[v][s], 0) + 1

    variants = [[questions[assign[v][s]] for s in range(S)] for v in range(count)]
    return BuildReport(
        variants=variants,
        conflicts=total_conflicts,
        max_overlap=max(histogram) if histogram else 0,
        overlap_histogram=dict(sorted(histogram.items())),
        max_usage=max(usage.values()) if usage else 0,
    )
