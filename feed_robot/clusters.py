# -*- coding: utf-8 -*-
"""Groups programs into visual micro-categories.

One generated image serves every program in a cluster: a dozen CBT courses do
not need a dozen different photos of a therapy session. Rules are ordered —
the first match wins, so put the specific ones above the general ones.

Each entry: (cluster key, russian label, [keywords], "image prompt scene").
"""

RULES = [
    # --- психология: методы и школы -------------------------------------
    ('psy_cbt', 'КПТ и схема-терапия',
     ['когнитивно-поведенч', 'кпт', 'схема-терапия'],
     'a psychologist and a client sitting opposite each other in a bright modern '
     'consulting room, a worksheet with hand-drawn diagrams on the table'),
    ('psy_art', 'Арт-терапия',
     ['арт-терап', 'арт терап'],
     'an art therapy session, adults painting with watercolours at a large wooden '
     'table in a light studio'),
    ('psy_mak', 'Метафорические карты',
     ['метафорическ', 'мак для', 'обучение мак'],
     'a set of illustrated association cards spread on a table between two people '
     'in a warm consulting room'),
    ('psy_play', 'Песочная терапия и сказкотерапия',
     ['песочн', 'сказкотерап', 'игралочка'],
     'a child play therapy room, a sand tray with small figurines, soft daylight'),
    ('psy_body', 'Телесная терапия и психосоматика',
     ['телесн', 'психосоматик', 'танцевально', 'софролог', 'кинезитерап'],
     'a body-oriented therapy session in a calm studio with yoga mats, an adult '
     'stretching while a specialist observes'),
    ('psy_analysis', 'Психоанализ и гипноз',
     ['психоанал', 'аналитическая психолог', 'гипноз', 'юнгиан'],
     'a classic psychoanalysis room with a couch, an armchair, bookshelves and '
     'warm lamp light'),
    ('psy_modality', 'Психотерапевтические подходы',
     ['гештальт', 'экзистенц', 'позитивная психотерап', 'транзактн', 'провокативн',
      'интегральная психотерап', 'смехотерап', 'психотерапевтические технолог',
      'психотерапевт', 'ароматерап'],
     'a small group therapy circle of adults in a bright room with soft chairs'),

    # --- психология: направления работы ---------------------------------
    ('psy_neuro_child', 'Детская нейропсихология',
     ['нейропсихологическ', 'сенсомотор', 'нейрофитнес', 'нейропсихолог'],
     'a specialist working with a child at a desk using colourful cognitive '
     'development cards and wooden puzzles'),
    ('psy_child', 'Детская психология и педагог-психолог',
     ['детская психолог', 'детский психолог', 'педагог-психолог', 'педагог психолог',
      'психология детей', 'дошкольного образования'],
     'a school psychologist talking with a child in a friendly office with soft '
     'toys and drawings on the wall'),
    ('psy_family', 'Семейная психология',
     ['семейн'],
     'a family counselling session, a couple sitting on a sofa opposite a '
     'psychologist in a warm room'),
    ('psy_sex', 'Сексология',
     ['сексолог', 'сексуальн'],
     'two adults in a private consulting room with a specialist, discreet warm '
     'interior, neutral mood'),
    ('psy_perinatal', 'Перинатальная психология',
     ['перинатальн'],
     'a pregnant woman talking with a specialist in a light calm consulting room'),
    ('psy_clinical', 'Клиническая психология',
     ['клиническая психолог', 'клинический психолог', 'патопсихолог'],
     'a clinical psychologist reviewing diagnostic materials at a desk in a '
     'medical office, neutral clinical interior'),
    ('psy_military', 'Военная психология',
     ['военн'],
     'a psychologist talking with a serviceman in a plain office, calm serious '
     'atmosphere, no uniforms with insignia, no flags'),
    ('psy_crisis', 'Кризисная и оперативная психология',
     ['кризисн', 'экстремальн', 'оперативной психолог', 'оперативная психодиагност'],
     'a psychologist supporting an adult in a quiet room, calm serious atmosphere'),
    ('psy_food', 'Психология пищевого поведения',
     ['пищевого поведения', 'пищевыми нарушен', 'консультант по питанию',
      'избыточной массой'],
     'a nutrition consultation, a specialist and a client at a table with fresh '
     'food and a notebook'),
    ('psy_addiction', 'Психология зависимостей',
     ['зависимост', 'созависим'],
     'a support group of adults sitting in a circle in a plain bright room'),
    ('psy_profiling', 'Профайлинг и НЛП',
     ['профайлинг', 'нлп', 'физиогномик'],
     'a specialist analysing behaviour patterns on a laptop and printed charts in '
     'a modern office'),
    ('psy_counseling', 'Психологическое консультирование',
     ['психологическое консультирован', 'психолог-консультант', 'психодиагностик',
      'диагностика личности', 'практическая психолог', 'психолог в социальной'],
     'a one-on-one counselling session in a modern light office, two armchairs and '
     'a low table'),
    ('psy_supervision', 'Супервизия',
     ['супервиз'],
     'a professional peer supervision group of psychologists around a table in a '
     'meeting room'),
    ('psy_mediation', 'Медиация и конфликтология',
     ['медиатор', 'медиаци', 'конфликтолог', 'психология общения', 'буллинг',
      'моббинг'],
     'a mediator sitting between two people at a round table in a neutral office'),
    ('psy_corporate', 'Корпоративная психология',
     ['корпоративн', 'организационная психолог'],
     'a workplace psychologist talking with an employee in a modern open-plan office'),
    ('psy_sport', 'Спортивная психология',
     ['спортивная психолог', 'спортивный психолог'],
     'a sports psychologist talking with an athlete on the edge of a training hall'),
    ('psy_special', 'Специальная психология и АВА',
     ['специальн', 'ава-терап'],
     'a specialist working one-on-one with a child using structured learning cards '
     'at a small table'),
    ('psy_coach', 'Коучинг и бизнес-тренинг',
     ['коуч', 'бизнес-тренер', 'бизнес тренер', 'психолог-тренер', 'тренинг',
      'лаборатория коуч'],
     'a business coach running a small workshop with adults around a whiteboard in '
     'a bright office'),
    ('psy_career', 'Профориентация',
     ['профориент'],
     'a career counsellor and a young adult reviewing options at a desk with a '
     'laptop and printed materials'),

    # --- педагогика ------------------------------------------------------
    ('ped_speech', 'Логопедия и дефектология',
     ['логопед', 'дефектолог', 'афазиолог', 'олигофренопедагог', 'зпр',
      'логопедическ', 'нарушения речи'],
     'a speech therapist working with a child at a small table with articulation '
     'cards and a mirror'),
    ('ped_preschool', 'Дошкольное образование',
     ['доу', 'дошкольн', 'предшкольн', 'раннего развития', 'монтессори',
      'воспитатель'],
     'a kindergarten teacher with a small group of children at a low table with '
     'wooden toys'),
    ('ped_school', 'Школа и СПО',
     ['начальных классов', 'спо', 'профессионального обучения', 'преподаватель в'],
     'a teacher in front of a small class of students in a bright modern classroom'),
    ('ped_language', 'Языки',
     ['английск', 'рки', 'иностранн'],
     'a language teacher with adult students at a table with textbooks in a light '
     'classroom'),
    ('ped_creative', 'Творческие дисциплины',
     ['изобраз', 'учитель изо', 'хореограф', 'каллиграф', 'культурно-досуг',
      'танцам', 'танцев', 'танцы'],
     'a creative workshop for children with art supplies and a teacher helping at '
     'an easel'),
    ('ped_brain', 'Развитие интеллекта',
     ['ментальн', 'скорочтен', 'мнемотехник', 'чтению', 'шахмат', 'шашк',
      'арифметик', 'развития памяти'],
     'children solving logic puzzles and abacus exercises at desks with a teacher '
     'nearby'),
    ('ped_it', 'Цифровые технологии в образовании',
     ['робототехник', 'нейросет', 'игрофикац', 'геймификац'],
     'a teacher and children assembling a small robot at a desk with a laptop'),
    ('ped_admin', 'Управление в образовании',
     ['завхоз', 'заместитель директора', 'руководитель образовательн',
      'руководитель организации доп', 'методист', 'советник руководител'],
     'a school administrator working with documents and a laptop in a tidy office'),
    ('ped_general', 'Общая педагогика и воспитание',
     ['педагог дополнительного', 'педагог-организатор', 'социальный педагог',
      'тьютор', 'организационно-методическ', 'социально-культурн',
      'педагогическая деятельность', 'воспитательного процесса', 'учитель биологии',
      'учитель физики', 'учитель химии', 'преподаватель'],
     'a teacher working with a small group of teenagers in a bright school room'),
    ('ped_finlit', 'Финансовая грамотность детей',
     ['финансовая грамотность'],
     'children learning about money with coins and colourful counting materials at '
     'a table with a teacher'),

    # --- спорт -----------------------------------------------------------
    ('sport_afk', 'Адаптивная физкультура',
     ['адаптивн', 'афк', 'гидрореабилит'],
     'an adaptive physical education session, a coach assisting a person with '
     'limited mobility in a bright gym'),
    ('sport_swim', 'Плавание и вода',
     ['плаван', 'аквафитнес', 'аквааэроб'],
     'a swimming coach beside a pool giving instructions, clear water and bright '
     'indoor light'),
    ('sport_team', 'Игровые виды спорта',
     ['футбол', 'хокке', 'баскетбол', 'волейбол', 'гандбол', 'теннис'],
     'a coach training a youth team on a sports field, action shot from the '
     'sideline'),
    ('sport_combat', 'Единоборства',
     ['бокс', 'каратэ', 'рукопашн', 'единоборств'],
     'a martial arts coach instructing students in a training hall with mats'),
    ('sport_athletics', 'Лёгкая атлетика и гимнастика',
     ['легкой атлетик', 'гимнастик', 'акробатик', 'кроссфит', 'пауэрлифт'],
     'an athletics coach with runners on a stadium track, morning light'),
    ('sport_gym', 'Тренажёрный зал и фитнес',
     ['фитнес-тренер', 'фитнес тренер', 'тренажерн', 'бодибилдинг',
      'тренер по избранному', 'тренер-преподаватель', 'инструктор-методист'],
     'a personal trainer coaching a client with dumbbells in a modern gym'),
    ('sport_group', 'Групповые программы',
     ['пилатес', 'стретчинг', 'аэробик', 'бодифлекс', 'ментальный фитнес'],
     'a group fitness class on mats in a bright studio with an instructor in front'),
    ('sport_yoga', 'Йога',
     ['йог'],
     'a yoga instructor guiding a small group in a calm studio with wooden floor'),
    ('sport_kids', 'Детский спорт',
     ['детский фитнес', 'детск'],
     'children exercising in a bright gym with a friendly coach'),
    ('sport_nutrition', 'Нутрициология и диетология',
     ['нутрициолог', 'диетолог'],
     'a nutritionist at a desk with fresh vegetables, a notebook and a laptop'),
    ('sport_generic', 'Тренерская работа',
     ['тренер', 'инструктор', 'физкультур', 'спорт'],
     'a sports coach with a whistle instructing a group in a training hall'),
    ('sport_admin', 'Организация спорта',
     ['антидопинг', 'судья', 'мотивации людей', 'экономика и управление в спорте',
      'физической культуры и спорта'],
     'a sports administrator with a clipboard beside an indoor arena'),

    # --- бизнес, финансы, управление -------------------------------------
    ('biz_accounting', 'Бухгалтерский учёт',
     ['бухгалтер', 'бухгалтерск', 'налогов'],
     'an accountant working with spreadsheets and paper documents at an office desk'),
    ('biz_1c', '1С и офисные программы',
     ['1с', 'excel', 'трудовые книжки'],
     'an office specialist working at a desktop computer with data tables on screen'),
    ('biz_finance', 'Финансы и экономика',
     ['финансов', 'экономист', 'экономическая безопасност', 'экономика и норм',
      'финансовых вложен', 'антикризисн'],
     'a financial analyst reviewing charts on two monitors in a modern office'),
    ('biz_hr', 'Управление персоналом',
     ['персонал', 'рекрутер', 'кадров', 'табельщик',
      'тестирование персонал', 'обучение и развитие'],
     'an HR manager interviewing a candidate across a table in a bright office'),
    ('biz_docs', 'Делопроизводство',
     ['делопроизводств', 'документационн', 'документооборот'],
     'an office administrator sorting documents and folders at a tidy workplace'),
    ('biz_gov', 'Госуправление и закупки',
     ['государственное и муниципальн', 'гму', 'закуп', 'тендер', 'контрактн'],
     'a public administration office, officials working with documents at desks'),
    ('biz_marketing', 'Маркетинг и продажи',
     ['маркетолог', 'маркетинг', 'отдела продаж'],
     'a marketing team reviewing analytics on a large screen in a modern office'),
    ('biz_project', 'Проекты и руководство',
     ['проект', 'эффективный руководител', 'управление проект'],
     'a project team at a whiteboard covered with sticky notes in a bright office'),
    ('biz_hospitality', 'Гостеприимство и сервис',
     ['ресторан', 'предприятием питания', 'гостиниц', 'туризм', 'администратор',
      'общепит'],
     'a hotel or restaurant manager greeting guests at a reception desk'),
    ('biz_culture', 'Культура и творческие индустрии',
     ['культуре и искусств', 'режиссер', 'массовых представлен'],
     'a cultural event manager coordinating a stage rehearsal in a theatre hall'),
    ('biz_analyst', 'Бизнес-аналитика',
     ['бизнес-аналитик', 'бизнес аналитик'],
     'a business analyst presenting process diagrams on a screen to colleagues'),
    ('biz_logistics', 'Логистика и хозяйство',
     ['логистик', 'кадастров'],
     'a logistics specialist with a tablet in a warehouse aisle'),
    ('biz_edu_manage', 'Менеджмент в образовании',
     ['менеджмент в образован'],
     'an education manager leading a staff meeting in a school office'),

    # --- прочее -----------------------------------------------------------
    ('media_journalism', 'Журналистика и медиа',
     ['журналист', 'редактор', 'радиовед', 'сторителлинг', 'сми', 'пресс-секретар'],
     'a journalist working at a newsroom desk with a laptop and notes'),
    ('design_graphic', 'Дизайн',
     ['дизайн', 'иллюстратор', 'figma'],
     'a graphic designer working at a large monitor with a drawing tablet'),
    ('social_medical', 'Медицина и уход',
     ['медицинская сестра', 'дезинфектор', 'младшая медиц'],
     'a healthcare assistant in scrubs preparing supplies in a clean clinic room'),
    ('social_care', 'Социальная сфера и сервис',
     ['нян', 'социального работника', 'горничная', 'кассир', 'проводник'],
     'a care worker helping an elderly person at home, warm domestic interior'),
]

FALLBACK = ('general_study', 'Общее обучение',
            'adults studying online at a laptop in a bright home office, notebooks '
            'and coffee on the desk')


import re

# Marketing filler carries no topic and creates false matches — "дистанционно"
# contains "танц", which used to drag every course into the dance cluster.
NOISE = re.compile(
    r'дистанцион\w*|рассрочк\w*|диплом\w*|удостоверен\w*|сертификат\w*|онлайн|'
    r'brandname|фрдо|установленного образца|с нуля|с записью|выдачей|'
    r'\d+\s*ч\b|\d+\s*ч\.|час\w*|месяц\w*',
    re.I)


def normalize(label):
    return re.sub(r'\s{2,}', ' ', NOISE.sub(' ', label.lower())).strip()


def assign(label):
    """Return the cluster key for a program label."""
    low = normalize(label)
    for key, _, keywords, _ in RULES:
        for kw in keywords:
            if kw in low:
                return key
    return FALLBACK[0]


def catalog():
    """cluster key -> (russian label, image scene)"""
    out = {key: (title, scene) for key, title, _, scene in RULES}
    out[FALLBACK[0]] = (FALLBACK[1], FALLBACK[2])
    return out
