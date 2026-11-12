"""JSON: sintaksis, maʼlumot turlari va Python dagi json moduli."""
from . import Q

PREFIX = 'JS'

QUESTIONS = [
    Q(2, "Quyidagilardan qaysi biri toʻgʻri (valid) JSON?",
      '{"ism": "Ali", "yosh": 20, "talaba": true}',
      "{'ism': 'Ali', 'yosh': 20, 'talaba': true}",
      '{"ism": "Ali", "yosh": 20, "talaba": True}',
      '{"ism": "Ali", "yosh": 20, "talaba": true,}',
      tags=('json-syntax',)),
    Q(2, "JSON standartida nechta maʼlumot turi bor va ular qaysilar?",
      "6 ta: string, number, boolean, null, object, array",
      "4 ta: string, integer, float, date",
      "5 ta: string, number, boolean, date, array",
      "3 ta: text, number, list",
      tags=('json-types',)),
    Q(2, "Python da JSON matnini (str) Python obyektiga (dict, list …) aylantiruvchi funksiya qaysi?",
      "json.loads()", "json.dumps()", "json.dump()", "json.encode()",
      tags=('json-loads',)),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "None", "null", "KeyError xatosi", "{'b': None}",
      code="""
          import json

          data = json.loads('{"a": [1, 2, {"b": null}]}')
          print(data["a"][2]["b"])
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      '{"ok": true, "qiymat": null}',
      "{'ok': True, 'qiymat': None}",
      '{"ok": True, "qiymat": None}',
      '{"ok": "true", "qiymat": "null"}',
      code="""
          import json

          print(json.dumps({"ok": True, "qiymat": None}))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      '{"1": "bir", "2": "ikki"}',
      '{1: "bir", 2: "ikki"}',
      'TypeError: kalitlar son boʻlishi mumkin emas',
      '["bir", "ikki"]',
      code="""
          import json

          print(json.dumps({1: "bir", 2: "ikki"}))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[1, 2, 3] list", "(1, 2, 3) tuple", "[1, 2, 3] tuple", "(1, 2, 3) list",
      code="""
          import json

          s = json.dumps((1, 2, 3))
          print(s, type(json.loads(s)).__name__)
      """),
    Q(2, "Standart JSON faylida izoh (komentariy) yozish mumkinmi?",
      "Yoʻq — standart JSON izohlarni qoʻllab-quvvatlamaydi",
      "Ha — // bilan boshlangan satrlar izoh hisoblanadi",
      "Ha — # bilan boshlangan satrlar izoh hisoblanadi",
      "Ha — faqat /* … */ koʻrinishidagi izohlar",
      tags=('json-comments',)),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "{'a': 2}", "{'a': 1}", "{'a': [1, 2]}", "ValueError: kalit takrorlangan",
      code="""
          import json

          print(json.loads('{"a": 1, "a": 2}'))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "str 3", "dict 3", "str 7", "list 3",
      code="""
          import json

          talaba = {"ism": "Gul", "baholar": [5, 4, 5]}
          matn = json.dumps(talaba)
          print(type(matn).__name__, len(json.loads(matn)["baholar"]))
      """),
    Q(2, "json.dumps({\"ism\": \"Oʻgʻiloy\"}) natijasida oʻzbekcha harflar \\u02bb kabi kodlarga aylanmay, oʻz holicha yozilishi uchun qaysi parametr kerak?",
      "ensure_ascii=False", "indent=4", "sort_keys=True", "allow_nan=False",
      tags=('json-ascii',)),
    Q(2, "JSON Lines (NDJSON) formati nima va u Big Data da nega qulay?",
      "Har bir satrda alohida JSON obyekt yoziladi; faylni satrlar boʻyicha boʻlib, parallel va oqim tarzida oʻqish mumkin",
      "Butun fayl bitta katta JSON massiv; uni faqat toʻliq xotiraga yuklab oʻqish mumkin",
      "JSON ning siqilgan binar versiyasi; uni matn muharririda ochib boʻlmaydi",
      "Har bir ustun alohida JSON faylda saqlanadigan ustunli format",
      tags=('json-lines',)),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "2", "95", "3", "{'id': 2, 'ball': 95}",
      code="""
          import json

          data = json.loads('[{"id": 1, "ball": 80}, {"id": 2, "ball": 95}, {"id": 3, "ball": 70}]')
          print(max(data, key=lambda t: t["ball"])["id"])
      """),
    Q(2, "Quyidagi JSON hujjatining eng yuqori (tashqi) darajasida nechta kalit bor?",
      "4", "6", "7", "5",
      code="""
          {
            "id": 1,
            "ism": "Bekzod",
            "kontakt": {"email": "b@mail.uz", "tel": "123-45-67"},
            "kurslar": ["Big Data", "Python"]
          }
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "[1, 2.0, True, None]",
      "[1, 2, true, null]",
      "[1, 2.0, 'true', 'null']",
      "['1', '2.0', 'true', 'null']",
      code="""
          import json

          print(json.loads("[1, 2.0, true, null]"))
      """),
    Q(2, "JSON da sana (masalan, 2026-yil 12-noyabr) odatda qanday saqlanadi?",
      "Satr sifatida, masalan \"2026-11-12\" (ISO 8601) — JSON da alohida sana turi yoʻq",
      "Maxsus date turi bilan: date(2026, 11, 12)",
      "Faqat yil, oy va kun uchun uchta alohida kalit bilan",
      "JSON da sanani umuman saqlab boʻlmaydi",
      tags=('json-dates', '~json-types')),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      "4.0", "4", "12", "TypeError xatosi",
      code="""
          import json

          s = '{"talaba": {"ism": "Ali", "baholar": [5, 3, 4]}}'
          d = json.loads(s)
          print(sum(d["talaba"]["baholar"]) / len(d["talaba"]["baholar"]))
      """),
    Q(2, "Quyidagi kod nimani chiqaradi?",
      '{"a":[1,2],"b":1}',
      '{"b":1,"a":[1,2]}',
      '{"a": [1, 2], "b": 1}',
      '{a:[1,2],b:1}',
      code="""
          import json

          print(json.dumps({"b": 1, "a": [1, 2]}, sort_keys=True, separators=(",", ":")))
      """),
    Q(2, "Quyidagi JSON matnida qanday xato bor?",
      "Son 0 bilan boshlanishi mumkin emas (021)",
      "Massivda satrlar boʻlishi mumkin emas",
      "Kalitlar qoʻshtirnoqsiz yozilishi kerak",
      "Xato yoʻq — bu toʻgʻri JSON",
      code="""
          {"ism": "Vali", "yosh": 021, "fanlar": ["Big Data", "Python"]}
      """,
      tags=('json-syntax',)),
    Q(2, "JSON dagi obyekt (object) va massiv (array) qanday farq qiladi?",
      "Obyekt — {} ichidagi kalit–qiymat juftliklari; massiv — [] ichidagi tartiblangan qiymatlar roʻyxati",
      "Obyekt — [] ichidagi roʻyxat; massiv — {} ichidagi juftliklar",
      "Obyekt faqat sonlarni, massiv esa faqat satrlarni saqlay oladi",
      "Ular bir xil, faqat qavslari farq qiladi",
      tags=('json-types',)),
]
