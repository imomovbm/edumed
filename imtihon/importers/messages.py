"""Every message the test importer shows (Uzbek, like the rest of the UI).

Kept in one place so the wording is easy to review and to translate later.
"""

# File level
NO_FILE = "Fayl tanlanmagan."
EMPTY_FILE = "Fayl boʻsh."
WRONG_TYPE = "«{ext}» turidagi fayl qabul qilinmaydi. Testlarni {allowed} faylga saqlab yuklang."
TOO_LARGE = "Fayl juda katta: {size}. Eng koʻpi {limit} boʻlishi mumkin."
TEXT_TOO_LARGE = "Matn juda katta: {size}. Eng koʻpi {limit} boʻlishi mumkin."
NOT_TEXT = ("Bu matn fayli emas ({kind} boʻlishi mumkin). Testlarni Bloknot (Notepad) yoki Word da "
            "«Oddiy matn (.txt)» sifatida saqlang.")
BAD_ENCODING = ("Fayl kodlashini aniqlab boʻlmadi. Faylni UTF-8 kodlashida saqlang "
                "(Bloknot: «Saqlash» → «Kodlash: UTF-8»).")
NO_QUESTIONS = "Faylda birorta ham savol topilmadi. Formatni tekshiring: savol, ====, javoblar, ++++."
TOO_MANY_QUESTIONS = "Savollar juda koʻp: {count} ta. Bitta imtihonda eng koʻpi {limit} ta boʻlishi mumkin."

# Question level (the page shows them as "N-savol, M-qator: …")
EMPTY_QUESTION = "Savol matni boʻsh."
QUESTION_TOO_LONG = "Savol matni juda uzun ({length} belgi, eng koʻpi {limit})."
TOO_FEW_OPTIONS = "Kamida 2 ta javob varianti boʻlishi kerak (hozir {count} ta)."
TOO_MANY_OPTIONS = "Javob variantlari {limit} tadan oshmasligi kerak (hozir {count} ta)."
EMPTY_OPTION = "{letter}-variant boʻsh (ketma-ket ikkita ==== qatori)."
OPTION_TOO_LONG = "{letter}-variant juda uzun ({length} belgi, eng koʻpi {limit})."
NO_CORRECT = "Toʻgʻri javob belgilanmagan — toʻgʻri variantning boshiga # qoʻying."
MANY_CORRECT = "Bir nechta toʻgʻri javob belgilangan ({letters}) — faqat bittasi # bilan boshlanishi kerak."
DUPLICATE_OPTION = "{first} va {second} variantlar bir xil: «{text}»."
DUPLICATE_QUESTION = "Bu savol {other}-savol bilan bir xil (ogohlantirish)."
QUESTION_STARTS_WITH_HASH = ("Savol matni # bilan boshlanadi. # faqat toʻgʻri javob oldiga qoʻyiladi — "
                             "savoldan keyin ==== tushib qolmaganini tekshiring (ogohlantirish).")
HASH_INSIDE = ("{line}-qator # bilan boshlanadi, lekin u alohida variant emas. Agar bu javob varianti boʻlsa, "
               "oldiga ==== qoʻying (ogohlantirish).")
