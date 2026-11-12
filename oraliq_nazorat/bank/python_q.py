"""Python: kod natijasini aniqlash va asosiy tushunchalar (oʻrta daraja)."""
from . import Q

PREFIX = 'PY'

QUESTIONS = [
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[0, 4, 16]", "[4, 16, 36]", "[0, 1, 4, 9, 16, 25]", "[1, 9, 25]",
      code="""
          print([x * x for x in range(6) if x % 2 == 0])
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[1, 2]", "[2]", "[1]", "None",
      code="""
          def qosh(x, items=[]):
              items.append(x)
              return items

          qosh(1)
          print(qosh(2))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[1, 2, 3, 4] True", "[1, 2, 3] False", "[1, 2, 3, 4] False", "[1, 2, 3] True",
      code="""
          a = [1, 2, 3]
          b = a
          b.append(4)
          print(a, a is b)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "3 -4 1", "3 -3 1", "3.5 -3.5 1", "3 -4 2",
      code="""
          print(7 // 2, -7 // 2, 7 % 3)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "ataD giB Data", "ataD giB ata", "Data Big Data", "giB ataD Data",
      code="""
          s = "Big Data"
          print(s[::-1], s[4:])
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[('spark', 2)]", "[('hadoop', 1)]", "{'spark': 2}", "[('s', 4)]",
      code="""
          from collections import Counter

          c = Counter("spark spark hadoop".split())
          print(c.most_common(1))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "1", "KeyError xatosi", "None", "3",
      code="""
          d = {"a": 1, "b": 2}
          print(d.get("c", 0) + d.get("a"))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "{'spark': 2, 'hdfs': 1, 'yarn': 1}",
      "{'spark': 1, 'hdfs': 1, 'yarn': 1}",
      "['spark', 'hdfs', 'yarn']",
      "KeyError: 'spark'",
      code="""
          words = ["spark", "hdfs", "yarn", "spark"]
          counts = {}
          for w in words:
              counts[w] = counts.get(w, 0) + 1
          print(counts)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "None [1, 2, 3]", "[1, 2, 3] [1, 2, 3]", "[1, 2, 3] [3, 1, 2]", "None [3, 1, 2]",
      code="""
          nums = [3, 1, 2]
          result = nums.sort()
          print(result, nums)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "['a', 'c', 'b']", "['b', 'c', 'a']", "['a', 'b', 'c']", "['c', 'b', 'a']",
      code="""
          pairs = [("a", 3), ("b", 1), ("c", 2)]
          print([p[0] for p in sorted(pairs, key=lambda p: p[1], reverse=True)])
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[1, 2, 3, 4, 5]", "[[1, 2], [3], [4, 5]]", "[1, 2, [3], 4, 5]", "SyntaxError xatosi",
      code="""
          nested = [[1, 2], [3], [4, 5]]
          print([y for x in nested for y in x])
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[6, 8]", "[2, 4, 6, 8]", "[3, 4]", "[4, 6, 8]",
      code="""
          print(list(map(lambda x: x * 2, filter(lambda x: x > 2, [1, 2, 3, 4]))))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "xato", "(10, 2, 3)", "(1, 2, 3)", "None",
      code="""
          t = (1, 2, 3)
          try:
              t[0] = 10
          except TypeError:
              print("xato")
          else:
              print(t)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "10", "5", "None", "UnboundLocalError xatosi",
      code="""
          x = 10

          def f():
              x = 5
              return x

          f()
          print(x)
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "{2, 3} 3", "{1, 2, 3, 4} 3", "{2, 3} 6", "{1, 4} 3",
      code="""
          print({1, 2, 3} & {2, 3, 4}, len(set("banana")))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "(3, ['a', 'b'])", "(5, [])", "(3, [4, 5])", "(2, ['a', 'b'])",
      code="""
          def f(*args, **kwargs):
              return len(args), sorted(kwargs)

          print(f(1, 2, 3, a=4, b=5))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "6 0", "6 6", "3 3", "0 6",
      code="""
          gen = (x * 2 for x in range(3))
          print(sum(gen), sum(gen))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[('a', 1), ('b', 2)] {'a': 1, 'b': 2}",
      "[('a', 1), ('b', 2), ('c', None)] {'a': 1, 'b': 2}",
      "ValueError xatosi",
      "[('a', 1), ('b', 2), ('c',)] {'a': 1, 'b': 2}",
      code="""
          print(list(zip("abc", [1, 2])), dict(zip("ab", [1, 2])))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "False True False True", "False False False False", "True True False True", "False True False False",
      code="""
          print(bool([]), bool("0"), bool(0.0), bool([0]))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "240", "24", "10", "34",
      code="""
          from functools import reduce

          print(reduce(lambda a, b: a * b, [1, 2, 3, 4], 10))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "10 7 4 1", "10 7 4", "9 6 3", "10 7 4 1 -2",
      code="""
          print(*range(10, 0, -3))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "1 99", "99 99", "1 1", "99 1",
      code="""
          a = [1, 2, 3]
          b = a[:]
          b[0] = 99
          print(a[0], b[0])
      """),
    Q(2, "Python da with open(\"f.txt\") as f: konstruksiyasining asosiy afzalligi nima?",
      "Blok tugagach (hatto xato yuz bersa ham) fayl avtomatik yopiladi",
      "Fayl avtomatik ravishda JSON ga aylantiriladi",
      "Fayl faqat oʻchirish uchun ochiladi",
      "Faylni oʻqish tezligi ikki baravar oshadi",
      tags=('py-with',)),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "3.14 2 4", "3.14 3 4", "3.14159 2 4", "3.15 3 4",
      code="""
          print(f"{3.14159:.2f}", round(2.5), round(3.5))
      """),
]
