# courses/management/commands/load_topics.py
#
# Run once with:  python manage.py load_topics
# Run safely multiple times (clears old data first per topic title).

from django.core.management.base import BaseCommand
from courses.models import Topic, TopicSection, TopicSectionItem


def make_topic(title, description='', icon='fa-book'):
    topic, _ = Topic.objects.get_or_create(title=title)
    topic.description = description
    topic.icon = icon
    topic.save()
    # Clear existing sections so re-running is idempotent
    topic.sections.all().delete()
    return topic


def add_section(topic, stype, title='', order=0):
    return TopicSection.objects.create(
        topic=topic, type=stype, title=title, order=order
    )


def add_item(section, text='', sub_text='', label='', order=0):
    return TopicSectionItem.objects.create(
        section=section, text=text, sub_text=sub_text,
        label=label, order=order
    )


class Command(BaseCommand):
    help = 'Load hamshiralik lecture content into the database'

    def handle(self, *args, **kwargs):
        self.load_topic_1()
        self.load_topic_2()
        self.load_topic_3()
        self.load_topic_4()
        self.load_topic_5()
        self.load_topic_6()
        self.stdout.write(self.style.SUCCESS('✅  Barcha mavzular muvaffaqiyatli yuklandi!'))

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 1: Hamshiralik ishi tarixi
    # ──────────────────────────────────────────────────────────────────
    def load_topic_1(self):
        topic = make_topic(
            title="Hamshiralik ishi tarixi va namoyandalari",
            description=(
                "Hamshiralik ishi qadimdan mavjud bo'lib, insoniyat bilan birga rivojlanib kelgan. "
                "Dastlab bu ishni diniy shaxslar, doyalar yoki oddiy insonlar bemorlarga yordam "
                "sifatida amalga oshirishgan. Keyinchalik hamshiralik asta-sekin alohida kasb va "
                "ilmiy yo'nalish sifatida shakllandi."
            ),
            icon='fa-history',
        )

        # Intro quote
        s = add_section(topic, 'quote', order=0)
        add_item(s,
            text="Hamshira — bu nafaqat parvarishchi, balki inson hayotini saqlovchi ilmiy mutaxassis.",
            order=0)

        # Dastlabki bosqichlar
        s = add_section(topic, 'text', title='Dastlabki bosqichlar', order=1)
        add_item(s,
            text=(
                "Qadim zamonlarda bemorlarni parvarish qilishni asosan diniy tashkilotlar "
                "bajarardi. Masalan, monastirlarda rohibalar kasallarga yordam ko'rsatgan. "
                "Hamshiralik ishining maqsadi shunchaki yordam va rahm-shafqat edi."
            ), order=0)

        # Florence Nightingale
        s = add_section(topic, 'person', title='Florence Nightingale (1820–1910)', order=2)
        add_item(s,
            label='Florence Nightingale',
            sub_text='1820–1910 · "Chiroq tutgan ayol"',
            text=(
                "1850-yillarda hamshiralik ishini professional darajaga olib chiqdi. "
                "Krim urushi (1853–1856) davrida askarlarni parvarish qilib, infektsiyalarni "
                "kamaytirishda katta rol o'ynadi. 1860-yilda Londonda birinchi Hamshiralik "
                "maktabini ochdi. Naytingeylning qarashlari: gigiyena, tozalik, bemorga "
                "individual yondashuv.\n\n"
                "1899-yilga kelib Xalqaro Hamshiralik Assotsatsiyasi ochildi (shtab-kvartirasi "
                "Jeneva, Shveytsariyada). 1900-yilda kengash nizomi qabul qilindi va uning "
                "birinchi prezidenti etib angliyalik Bezfard Fenvik saylandi. Tashkilot har "
                "4 yilda bir marta konferensiyalar o'tkazadi. 1971-yildan boshlab 12-may "
                "(F.Naytingeyl tug'ilgan kuni) Xalqaro hamshiralar kuni deb e'lon qilindi."
            ), order=0)

        # Virginia Henderson
        s = add_section(topic, 'person', title='Virginia Henderson (1897–1996)', order=3)
        add_item(s,
            label='Virginia Henderson',
            sub_text='1897–1996 · XX asrning yirik nazariyotchisi',
            text=(
                "'Hamshiralikning 14 asosiy ehtiyoji' nazariyasini yaratdi. Hamshiralik ishini "
                "shaxsning sog'lig'ini tiklash, saqlash va mustaqil hayotini davom ettirish uchun "
                "yordam berish faoliyati deb ta'rifladi. Uning konsepsiyasi bo'yicha hamshira "
                "shifokor yordamchisi emas, balki mustaqil mutaxassis bo'lib, bemorning "
                "ehtiyojlarini qondirishda asosiy rol o'ynaydi."
            ), order=0)

        # O'zbekistonda vaqt chizig'i
        s = add_section(topic, 'timeline', title="O'zbekistonda hamshiralik ishi rivojlanishi", order=4)
        items = [
            ('1918–1920',
             "Turkiston umumtibbiyot komissiyasi tashkil etildi, barcha tibbiyot xodimlari "
             "ro'yxatdan o'tkazildi. Toshkentda birinchi tibbiyot bilim yurti (Oxuboboyev nomli) ochildi.", ''),
            ('1920–1932',
             "O'rta Osiyo Davlat dorilfunini shakllandi, 1931-yildan Toshkent Davlat Tibbiyot "
             "Instituti deb yuritila boshlandi. 1932-yilda Toshkentda vrachlar malakasini oshirish "
             "instituti tashkil etildi.", ''),
            ('1991 yildan keyin',
             "O'zbekiston mustaqillikka erishgach, 'Hamshiralik ishi' alohida mutaxassislik "
             "sifatida e'tirof etildi.",
             "1998-yildan boshlab tibbiyot bilim yurtlarida 'Hamshiralik ishi' mutaxassisligi joriy etildi.\n"
             "Hamshiralik kasbining huquqiy asoslari mustahkamlandi."),
            ('1998-yil, 10-noyabr',
             "O'zbekiston Respublikasi Prezidentining 2107-sonli qarori asosida tibbiy oliy o'quv "
             "yurtlari qoshida 'Oliy malakali hamshira' tayyorlash yo'lga qo'yildi.", ''),
            ('Hozirgi davr',
             "O'zbekistonda hamshiralarni tayyorlash ikki darajada: o'rta maxsus ta'lim (kollejlar) "
             "va oliy ta'lim (bakalavr/magistr) orqali olib boriladi.",
             "Hamshiralar nafaqat parvarish, balki profilaktika, sog'lom turmush tarzini targ'ib qilish, "
             "jamoat salomatligi yo'nalishida ham faoliyat yuritmoqda.\n"
             "Istiqbol: xalqaro tajribani joriy etish, oliy ma'lumotli hamshiralar rolini kengaytirish, "
             "ilmiy tadqiqotlarda hamshiralarni jalb qilish."),
        ]
        for i, (label, text, sub) in enumerate(items):
            add_item(s, label=label, text=text, sub_text=sub, order=i)

        # Key points
        s = add_section(topic, 'keypoints', title='Asosiy eslatmalar', order=5)
        kp = [
            ("Hamshiralik — mustaqil ilmiy fan",
             "Shifokor yordamchisi emas, balki to'liq mutaxassis."),
            ("12-may — Xalqaro hamshiralar kuni",
             "Florence Nightingale tug'ilgan kuniga bag'ishlangan."),
            ("O'zbekistonda 1998-yildan oliy hamshiralik ta'limi",
             "Prezident qarori bilan joriy etilgan."),
            ("JSST Xalqaro Hamshiralik Assotsatsiyasi",
             "1899-yildan faoliyat yuritadi, har 4 yilda konferensiya o'tkazadi."),
        ]
        for i, (text, sub) in enumerate(kp):
            add_item(s, text=text, sub_text=sub, order=i)

        self.stdout.write('  ✓ Mavzu 1 yuklandi')

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 2: Bioetika va deontologiya
    # ──────────────────────────────────────────────────────────────────
    def load_topic_2(self):
        topic = make_topic(
            title="Hamshiralik ishi bioetikasi va deontologiyasi",
            description=(
                "Hamshiralik ishida bioetika va deontologiya tamoyillariga amal qilish — "
                "bemorning huquqlarini, qadr-qimmatini, shaxsiy hayotini hurmat qilish demakdir."
            ),
            icon='fa-heart',
        )

        # Deontologiya
        s = add_section(topic, 'info', title='Tibbiy deontologiya haqida tushuncha', order=0)
        add_item(s,
            label='Ta\'rif',
            text=(
                "Deontologiya (yunoncha deon — burch, logos — ta'limot) — bu tibbiyot xodimlarining "
                "kasbiy odob-axloq qoidalari va ularning kasbiy burchlarini bajarish tamoyillari "
                "to'g'risidagi ta'limotdir. Tibbiy deontologiya shifokor va hamshiraning bemor, uning "
                "qarindoshlari, hamkasblari hamda jamiyat oldidagi xatti-harakatlarini tartibga soladi."
            ), order=0)
        add_item(s,
            label='Asosiy maqsad',
            text=(
                "Bemorga zarar yetkazmaslik, unga yuksak darajada yordam ko'rsatish, kasbiy sirni "
                "saqlash va inson qadr-qimmatini hurmat qilish."
            ), order=1)

        # Bioetika tamoyillari
        s = add_section(topic, 'keypoints', title="Bioetikaning asosiy tamoyillari", order=1)
        principles = [
            ("\"Zarar yetkazma\" (Primum non nocere)",
             "Noto'g'ri qaror yoki parvarish bemorga zarar bermasligi kerak."),
            ("Adolat",
             "Barcha bemorlarga millatidan, jinsidan, yoshidan qat'i nazar, teng xizmat ko'rsatish."),
            ("Avtonomiya",
             "Bemorning o'z tanlovi va qaroriga hurmat bilan qarash."),
            ("Xayriya (Benefitsiya)",
             "Bemorning manfaatini ustuvor qo'yish."),
        ]
        for i, (text, sub) in enumerate(principles):
            add_item(s, text=text, sub_text=sub, order=i)

        # Oliy ma'lumotli hamshira vazifalari
        s = add_section(topic, 'keypoints', title="Oliy ma'lumotli hamshiraning burchi va vazifalari", order=2)
        duties = [
            "Bemorning huquqlarini hurmat qilish va himoya qilish.",
            "Davolash-profilaktika jarayonida shifokor bilan hamkorlikda ishlash.",
            "Hamshiralik jarayonini mustaqil tashkil qilish (diagnostika, reja tuzish, parvarish).",
            "Bioetika va deontologiya qoidalariga qat'iy rioya qilish.",
            "Yosh hamshiralarni tarbiyalash va o'qitish.",
            "Ilmiy izlanishlar olib borish, kasbiy bilimni uzluksiz oshirib borish.",
        ]
        for i, d in enumerate(duties):
            add_item(s, text=d, order=i)

        # Tibbiy sir
        s = add_section(topic, 'info', title="Tibbiy sir haqida tushuncha", order=3)
        add_item(s,
            label='Ta\'rif',
            text=(
                "Tibbiy sir — bemor haqida uning roziligisiz hech kimga aytilmasligi kerak bo'lgan "
                "ma'lumotlar yig'indisidir. Bunga kiradi: tashxis, kasallik tarixi, laboratoriya va "
                "instrumental tekshiruv natijalari, davolash jarayoni, shaxsiy hayotga oid ma'lumotlar."
            ), order=0)
        add_item(s,
            label='Sirni oshkor qilish mumkin bo\'lgan holatlar',
            text=(
                "Faqat ikki holatda ruxsat etiladi:\n"
                "1. Bemorning yozma roziligi bilan.\n"
                "2. Qonuniy asos bo'lsa (masalan, sud-tergov jarayoni, jamoat xavfsizligi)."
            ), order=1)

        # Eftanaziya
        s = add_section(topic, 'info', title="Eftanaziya haqida tushuncha", order=4)
        add_item(s,
            label='Ta\'rif',
            text=(
                "Eftanaziya — og'ir va davolab bo'lmaydigan kasallikka chalingan bemorning azobini "
                "yengillashtirish maqsadida uning hayotiga sun'iy ravishda barham berishdir."
            ), order=0)
        add_item(s,
            label='Turlari',
            text=(
                "Faol eftanaziya — maxsus dori vositalari yordamida hayotni to'xtatish.\n"
                "Passiv eftanaziya — davolash yoki hayotni qo'llab-quvvatlovchi choralarni to'xtatish."
            ), order=1)
        add_item(s,
            label='O\'zbekistonda holati',
            text=(
                "O'zbekiston Respublikasida eftanaziya qonunan taqiqlangan. Shifokor va hamshiralar "
                "hayotni saqlashga, bemorning azobini yengillashtirishga majbur, lekin uning hayotiga "
                "qasd qilishga haqli emas."
            ), order=2)

        self.stdout.write('  ✓ Mavzu 2 yuklandi')

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 3: LEMON loyihasi
    # ──────────────────────────────────────────────────────────────────
    def load_topic_3(self):
        topic = make_topic(
            title='"LEMON" xalqaro o\'quv loyihasi',
            description=(
                "'LEMON' o'quv dasturi (Learning Materials on Nursing) — JSST Yevropa Regional "
                "Byurosi ishtirokida 1988-yilda Vena shahrida tashkil qilingan. Maqsadi: hamshiralik "
                "sohasida bilim va o'quv resurslarini takomillashtirish."
            ),
            icon='fa-lemon',
        )

        # Boblar
        s = add_section(topic, 'keypoints', title='"LEMON" loyihasining 12 bobi', order=0)
        chapters = [
            ("Hayot, sog'liq va atrof-muhit",
             "Sog'liqning atrof muhit bilan aloqasi, ijtimoiy-madaniy omillar."),
            ("Hamshiralik ishi va ijtimoiy fanlar",
             "Hamshiralik kasbi ijtimoiy kontekstda, jamiyatdagi o'rni."),
            ("Muloqot-munosabatlar",
             "Bemor-hamshira, hamshira-hamshira munosabatlari, kommunikatsiya ko'nikmalari."),
            ("Hamshiralik jarayoni va hujjatlar",
             "Parvarish, protokollar, dokumentatsiya."),
            ("Sanitariya-maorif va sog'liqni mustahkamlash",
             "Profilaktika, sanitariya, gigiyena bilimlari."),
            ("Anatomiya va fiziologiya masalalari",
             "Bemorning tana tizimlari, fiziologik asoslar."),
            ("Sog'lom onalik",
             "Ona va bola sog'ligi, homiladorlik, tug'ruqdan keyingi parvarish."),
            ("Klinik sharoitda hamshiralik ishi",
             "Kasalxona jarayonlari, bemorlarni parvarish, muolajalar."),
            ("Professional va axloqiy aspektlar",
             "Bioetika, etika, professionallik."),
            ("Hamshiralar salomatligi va mehnat xavfsizligi",
             "Ish sharoiti, profilaktika, xodim salomatligi."),
            ("Hamshiralar ishidagi asosiy o'zgarishlar",
             "Zamonaviy yondashuvlar, texnologiyalar, sanoat ta'siri."),
            ("O'quv materiallariga oid ko'rsatkichlar",
             "Baholash mezonlari, o'rgatuvchi va o'quvchi materiallari."),
        ]
        for i, (text, sub) in enumerate(chapters):
            add_item(s, text=f"{i+1}. {text}", sub_text=sub, order=i)

        # O'zbekistonda o'rni
        s = add_section(topic, 'info', title="O'zbekiston kontekstida ahamiyati", order=1)
        add_item(s,
            label='Ta\'lim tizimiga integratsiya',
            text=(
                "Loyihaning boblari O'zbekiston darsliklarida keltirilgan. 'O'zbekiston "
                "Respublikasida hamshiralik ishi asoslari' qo'llanmalarida 'Xalqaro LEMON dasturida "
                "hamshiralik ishi haqida' bo'limlari mavjud. Shuningdek, hamshiralik fakultetlarida "
                "o'quv moduli sifatida kiritilgan."
            ), order=0)
        add_item(s,
            label='Oliy ma\'lumotli hamshiralarga beradigan afzalliklari',
            text=(
                "Jamiyat salomatligi va profilaktika bilimlarini chuqurroq o'zlashtirish.\n"
                "Etika va professional me'yorlar, kommunikatsiya ko'nikmalarini yaxshilash.\n"
                "Tibbiy hujjatlar yuritish va klinik standartlarga rioya qilish malakasini oshirish."
            ), order=1)

        # Kamchiliklar
        s = add_section(topic, 'info', title="Tahlil va e'tiborga olinishi kerak bo'lgan jihatlar", order=2)
        issues = [
            ("Lokal adaptatsiya ehtiyoji",
             "'LEMON' loyihasi Yevropa kontekstida yaratilgan — lokal epidemiologiya, "
             "madaniyat va tibbiy xizmat ko'rsatish sharoiti farqlari hisobga olinishi kerak."),
            ("O'qituvchilar tayyorgarligi",
             "Materiallar juda kompleks bo'lgan joylarda o'qituvchilarning hamshiralik tajribasi "
             "va pedagogik ko'nikmalari yetarli bo'lmasligi mumkin."),
            ("Texnologik infratuzilma",
             "Laboratoriya jihozlari va klinik amaliyot uchun namunaviy sharoitlar yetishmaydigan "
             "joylarda ba'zi modullar bajarilishi cheklangan bo'lishi mumkin."),
        ]
        for i, (label, text) in enumerate(issues):
            add_item(s, label=label, text=text, order=i)

        self.stdout.write('  ✓ Mavzu 3 yuklandi')

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 4: Salomatlik
    # ──────────────────────────────────────────────────────────────────
    def load_topic_4(self):
        topic = make_topic(
            title="Salomatlik va unga ta'sir etuvchi omillar",
            description=(
                "Inson salomatligi — jamiyatning eng katta boyligi. Sog'liqni saqlash tizimi oldida "
                "tibbiy xizmat bilan bir qatorda profilaktika va sog'lomlashtirish vazifalari ham turadi."
            ),
            icon='fa-heartbeat',
        )

        # JSST ta'rifi
        s = add_section(topic, 'quote', order=0)
        add_item(s,
            text="Salomatlik — bu faqat kasallik va nuqsonlarning yo'qligi emas, balki jismoniy, ruhiy va ijtimoiy farovonlik holatidir.",
            label='Jahon sog\'liqni saqlash tashkiloti (JSST)',
            order=0)

        # Salomatlik turlari
        s = add_section(topic, 'keypoints', title="Salomatlikning to'rt jihati", order=1)
        aspects = [
            ("Jismoniy salomatlik", "Organizmning normal faoliyati, kasalliklardan holilik."),
            ("Ruhiy salomatlik", "Stresslarga chidamlilik, ijobiy emotsional holat."),
            ("Ijtimoiy salomatlik", "Jamiyatga moslashuv, ijtimoiy faollik."),
            ("Ma'naviy salomatlik", "Axloqiy qadriyatlar, hayot ma'nosini his qilish."),
        ]
        for i, (text, sub) in enumerate(aspects):
            add_item(s, text=text, sub_text=sub, order=i)

        # Tarix davrlari
        s = add_section(topic, 'timeline', title="Salomatlikni o'rganish davrlari", order=2)
        periods = [
            ('Antik davr', "Salomatlik va kasallik tushunchalari falsafiy asosda ko'rilgan.", ''),
            ('XIX asrgacha (Biomedikal yondashuv)',
             "Salomatlik kasallik yo'qligi deb qaralgan.", ''),
            ('XX asr boshlari (Gigiyenik yondashuv)',
             "Gigiyena va profilaktikaga e'tibor ortdi.", ''),
            ('XX asr o\'rtasi (Ijtimoiy-madaniy yondashuv)',
             "Salomatlikni ijtimoiy muhit, ekologiya, turmush tarzi bilan bog'liq holda o'rganish boshlandi.", ''),
            ('Zamonaviy kompleks yondashuv',
             "Jismoniy, ruhiy, ijtimoiy, ekologik va ma'naviy omillar birgalikda baholanadi.", ''),
        ]
        for i, (label, text, sub) in enumerate(periods):
            add_item(s, label=label, text=text, sub_text=sub, order=i)

        # Ta'sir etuvchi omillar
        s = add_section(topic, 'info', title="Salomatlikka ta'sir etuvchi omillar (JSST ma'lumotlari)", order=3)
        factors = [
            ('Turmush tarzi — 50%',
             "Ovqatlanish, jismoniy faollik, zararli odatlarning yo'qligi, gigiyena."),
            ('Atrof-muhit — 20%',
             "Ekologiya, ishlab chiqarish xavfsizligi, turar-joy sharoiti."),
            ("Irsiy omillar — 20%",
             "Genetik moyillik va irsiy kasalliklar."),
            ("Sog'liqni saqlash tizimi sifati — 10%",
             "Tibbiy xizmat sifati va mavjudligi."),
        ]
        for i, (label, text) in enumerate(factors):
            add_item(s, label=label, text=text, order=i)

        # Sog'lomlashtirish ishlari
        s = add_section(topic, 'keypoints', title="Hamshiralik ishida sog'lomlashtirish yo'nalishlari", order=4)
        works = [
            ("Aholi orasida sog'lom turmush tarzini targ'ib qilish",
             "Ma'ruzalar, suhbatlar, ko'rgazmali qurollar."),
            ("To'g'ri ovqatlanish bo'yicha maslahatlar", ""),
            ("Jismoniy faollikni rag'batlantirish", ""),
            ("Stresslarni kamaytirish va psixologik yordam ko'rsatish", ""),
            ("Zararli odatlarning oldini olish",
             "Chekish, spirtli ichimlik, giyohvandlikka qarshi targ'ibot."),
        ]
        for i, (text, sub) in enumerate(works):
            add_item(s, text=text, sub_text=sub, order=i)

        self.stdout.write('  ✓ Mavzu 4 yuklandi')

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 5: Profilaktika
    # ──────────────────────────────────────────────────────────────────
    def load_topic_5(self):
        topic = make_topic(
            title="Profilaktik ishlar va hamshiralik faoliyatida tibbiy himoyalanish",
            description=(
                "Profilaktika — kasalliklarning oldini olishga qaratilgan tizimli chora-tadbirlar "
                "majmuasidir. Zamonaviy tibbiyotning asosiy tamoyili: 'davolashdan ko'ra, oldini "
                "olish afzal'."
            ),
            icon='fa-shield-alt',
        )

        # Intro
        s = add_section(topic, 'info', title="Profilaktika haqida umumiy tushuncha", order=0)
        add_item(s,
            label="Ta'rif",
            text=(
                "Profilaktika (yunoncha prophylaktikos — oldini olish) — sog'lom insonlarda "
                "kasalliklarning paydo bo'lishi, rivojlanishi va asoratlarini bartaraf etishga "
                "qaratilgan faoliyatdir. JSST tadqiqotlariga ko'ra, aholining sog'lig'iga ta'sir "
                "etuvchi omillarning 50% dan ortig'i turmush tarziga bog'liq — bu esa profilaktika "
                "orqali nazorat qilinadi."
            ), order=0)

        # Profilaktika turlari — 3 ta section
        s = add_section(topic, 'info', title="Birlamchi profilaktika — kasallikni paydo bo'lishidan oldin bartaraf etish", order=1)
        primary = [
            ("Immunizatsiya (emlash)", "Yuqumli kasalliklardan himoya qilish."),
            ("Gigiyenik ta'lim",
             "Aholiga sog'lom turmush tarzi, ovqatlanish va shaxsiy gigiyena bo'yicha bilim berish."),
            ("Ona va bola salomatligini muhofaza qilish",
             "Homiladorlik, tug'ruq va tug'ruqdan keyingi parvarish."),
            ("Zararli odatlarning oldini olish",
             "Chekish, spirtli ichimlik, giyohvandlikka qarshi targ'ibot."),
            ("Ekologik xavfsizlik haqida tushuntirish", ""),
        ]
        for i, (label, text) in enumerate(primary):
            add_item(s, label=label, text=text, order=i)

        s = add_section(topic, 'info', title="Ikkilamchi profilaktika — kasallikni erta aniqlash va davolash", order=2)
        secondary = [
            ("Aholini tibbiy ko'rikdan o'tkazish", "Erta diagnostika va screening."),
            ("Kasallikning dastlabki belgilari haqida ma'lumot berish",
             "Aholi o'z sog'lig'ini o'zi kuzatishi uchun bilim berish."),
            ("Xavf guruhidagi bemorlarni kuzatib borish",
             "Surunkali kasalliklar, yurak-qon tomir xastaliklari."),
            ("Davolash jarayonida shifokorga ko'maklashish", ""),
        ]
        for i, (label, text) in enumerate(secondary):
            add_item(s, label=label, text=text, order=i)

        s = add_section(topic, 'info', title="Uchinchi darajali profilaktika — reabilitatsiya", order=3)
        tertiary = [
            ("Bemorlarni reabilitatsiya markazlariga yo'naltirish",
             "Kasallikdan keyingi nogironlik va asoratlarni kamaytirish."),
            ("Oila va bemorlarni parvarish qilish ko'nikmalariga o'rgatish", ""),
            ("Psixologik va ijtimoiy qo'llab-quvvatlash", ""),
        ]
        for i, (label, text) in enumerate(tertiary):
            add_item(s, label=label, text=text, order=i)

        # Tibbiy himoyalanish
        s = add_section(topic, 'keypoints', title="Hamshiralik faoliyatida tibbiy himoyalanish", order=4)
        protection = [
            ("Shaxsiy himoya vositalari",
             "Qo'lqop, niqob, xalat, ko'zoynak — har bir xavfli muolajada majburiy."),
            ("Infeksion nazorat",
             "Qo'l yuvish qoidalari, dezinfeksiya, sterilizatsiya."),
            ("Mehnat gigiyenasi",
             "Ish joyini toza saqlash, asboblarni to'g'ri ishlatish."),
            ("Stressdan himoyalanish",
             "Ish vaqtini to'g'ri taqsimlash, dam olishga e'tibor berish."),
            ("Kasbiy xavfsizlik",
             "Igna va o'tkir buyumlar bilan ishlashda ehtiyot bo'lish."),
        ]
        for i, (text, sub) in enumerate(protection):
            add_item(s, text=text, sub_text=sub, order=i)

        # Xavf turlari
        s = add_section(topic, 'info', title="Tibbiy xodimlar uchun xavf turlari", order=5)
        risks = [
            ("Biologik xavflar", "Infeksiya yuqishi xavfi: VICH, gepatit B va C, sil va boshqalar."),
            ("Kimyoviy xavflar", "Dori vositalari, dezinfektantlar, kimyoviy reagentlar bilan ishlash."),
            ("Fizik xavflar", "Rentgen nurlari, ultratovush, yuqori temperatura."),
            ("Psixologik xavflar",
             "Stress, charchash, burnout (kasbiy tushkunlik) sindromi."),
        ]
        for i, (label, text) in enumerate(risks):
            add_item(s, label=label, text=text, order=i)

        self.stdout.write('  ✓ Mavzu 5 yuklandi')

    # ──────────────────────────────────────────────────────────────────
    # MAVZU 6: Tibbiy himoya va dezinfeksiya
    # ──────────────────────────────────────────────────────────────────
    def load_topic_6(self):
        topic = make_topic(
            title="Tibbiy himoya, mehnat muhofazasi va dezinfeksiya",
            description=(
                "Tibbiy himoya — tibbiy xodimlar va bemorlarning sog'lig'ini saqlash, infeksion va "
                "noinfeksion xavflardan himoya qilishga qaratilgan chora-tadbirlar majmuasidir."
            ),
            icon='fa-virus-slash',
        )

        # Kasalxona ichki infeksiyasi
        s = add_section(topic, 'info', title="Kasalxona ichki infeksiyasi (Nosocomial infektsiya)", order=0)
        add_item(s,
            label="Ta'rif",
            text=(
                "Tibbiyot muassasasi ichida yuqumli kasallik manbalari tufayli bemorlar yoki "
                "xodimlarda paydo bo'ladigan infeksiya. Asosiy manbalari: steril bo'lmagan "
                "asbob-uskunalar, iflos qo'llar, noto'g'ri parvarish, dezinfeksiya qoidalariga "
                "rioya qilmaslik."
            ), order=0)
        add_item(s,
            label="Eng ko'p tarqalgan qo'zg'atuvchilar",
            text=(
                "Stafilokokk, streptokokk, Pseudomonas aeruginosa, Klebsiella, zamburug'lar."
            ), order=1)

        # Hamshiraning vazifalari
        s = add_section(topic, 'keypoints', title="Ichki infeksiyaga qarshi hamshiraning vazifalari", order=1)
        duties = [
            ("Dezinfeksiya va sterilizatsiya qoidalariga qat'iy rioya qilish", ""),
            ("Aseptika va antiseptika qoidalariga amal qilish", ""),
            ("Shaxsiy gigiyena va himoya vositalaridan foydalanish",
             "Qo'lqop, niqob, xalat majburiy."),
            ("Kasalxona sanitar-epidemiologik rejimini bajarish", ""),
            ("Yuqumli kasallik aniqlansa, tezkor ravishda xabar berish", ""),
        ]
        for i, (text, sub) in enumerate(duties):
            add_item(s, text=text, sub_text=sub, order=i)

        # Dezinfeksiya turlari
        s = add_section(topic, 'info', title="Dezinfeksiya, dezinseksiya va deratizatsiya", order=2)
        add_item(s, label="Dezinfeksiya",
            text="Mikroorganizmlarni yo'qotish yoki kamaytirishga qaratilgan chora-tadbirlar (mexanik, kimyoviy, fizik).",
            order=0)
        add_item(s, label="Dezinseksiya",
            text="Hasharotlarga qarshi kurash (chivin, pashsha, kanalizatsiya hasharotlari).",
            order=1)
        add_item(s, label="Deratizatsiya",
            text="Kemiruvchilarga qarshi kurashish (sichqon, kalamush).",
            order=2)

        # Eritmalar tayyorlash
        s = add_section(topic, 'info', title="Dezinfeksion eritmalarni tayyorlash qoidalari", order=3)
        rules = [
            ("Ish joyi",
             "Faqat maxsus ajratilgan, shamollatiladigan xonada. Maxsus kiyim, rezina qo'lqop, "
             "respirator va ko'zoynak majburiy."),
            ("Idishlar",
             "Faqat maxsus belgilangan idishlarda (plastik yoki shisha). Idishda eritma "
             "konsentratsiyasi, tayyorlangan sana va amal qilish muddati yozib qo'yiladi."),
            ("Aralashtirish qoidasi",
             "'Eritmani suvga qo'shish emas, balki suvni eritmaga qo'shish' qoidasi amal qiladi "
             "(chayqalish va kuyishning oldini olish uchun)."),
            ("Nazorat",
             "Har bir tayyorlangan eritma sifati va konsentratsiyasi maxsus laborator usullar "
             "bilan nazorat qilinadi. Tayyorlangan eritma maxsus dezinfeksiya jurnaliga qayd qilinadi."),
        ]
        for i, (label, text) in enumerate(rules):
            add_item(s, label=label, text=text, order=i)

        # Xlorli ohak amaliy qo'llanishi
        s = add_section(topic, 'info', title="Xlorli ohak eritmasi — amaliy qo'llanishi", order=4)
        applications = [
            ("0,2% eritma",
             "Pol, mebel, eshik tutqichlari, hamshira postini artishda."),
            ("0,5% eritma",
             "Qon, balg'am va najas bilan ifloslangan buyumlar uchun."),
            ("1–2% eritma",
             "Najas, qusindi va balg'amni zararsizlantirishda."),
            ("5% eritma",
             "Faqat maxsus hollarda — yuqori xavfli infeksiyalar o'chog'ida."),
        ]
        for i, (label, text) in enumerate(applications):
            add_item(s, label=label, text=text, order=i)

        # Tayyorlash
        s = add_section(topic, 'info', title="5% xlorli ohak eritmasi tayyorlash tartibi", order=5)
        add_item(s,
            label="Kerakli miqdor",
            text=(
                "500 g xlorli ohak olinadi. Ustiga oz-ozdan 10 litr toza suv qo'shilib, yaxshilab "
                "aralashtiriladi. 24 soat tindiriladi, so'ng filtrlanadi. Hosil bo'lgan suyuqlik — "
                "ishchi eritma hisoblanadi."
            ), order=0)
        add_item(s,
            label="Saqlash muddati",
            text=(
                "Eritma faqat 1 sutka davomida saqlanadi, keyin yangidan tayyorlanadi. "
                "Buyumlar eritmaga to'liq botiriladi yoki eritma bilan artiladi. Eritma bilan "
                "ishlov berilgach, buyumlar albatta toza suv bilan chayiladi."
            ), order=1)

        self.stdout.write('  ✓ Mavzu 6 yuklandi')
