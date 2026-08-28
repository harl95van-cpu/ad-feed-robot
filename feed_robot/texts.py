# -*- coding: utf-8 -*-
"""Prompt, checks and assembly for model-written offer copy.

The model does only what a model is good at: it names the thing the programme
trains for and puts that name in the accusative. Everything else — choosing the
wording of the line, fitting it into Direct's limits, substituting today's
price — is arithmetic, and arithmetic belongs in code. Asking the model to
count characters does not work: it takes a long qualification verbatim and
blows the limit, or it mangles the name to make room for decoration.

The order of sacrifice is fixed: the name of the programme is never shortened
to fit. If the line does not fit, the decoration goes — first the duration,
then the standing offer, then the «Диплом!» ending, then the «Обучение на»
opening. A title that says exactly what the course is beats a well-formed one
that says something else.

Nothing numeric is ever written by the model. The price is substituted on every
build, so a price change on the site never triggers a regeneration — and
regenerating is expensive not in money but in performance, because rewriting an
offer resets the statistics Direct has accumulated for it.
"""
import json
import re

from llm import BudgetExceeded

# Direct applies search-ad limits when it renders a smart banner, so the feed
# format's own 100/85 allowance is not the real ceiling — anything longer is cut
# mid-word in the live ad.
TITLE_LIMIT = 56
# 81 is the search-ad limit, but a live banner showed a 79-character line cut
# after 76 with an ellipsis: the placement clamps the description to two lines,
# and word wrapping decides where that lands. 75 is what reliably survives.
TEXT_LIMIT = 75

DEFAULT_TITLE_TAIL = '. Диплом!'

# Two shapes an ad can take. A programme that plainly trains a person gets the
# person; a programme that names a field gets the field. Naming a neighbouring
# profession for a field — «Финансовый аналитик» for a course in financial
# security — is a hard error, so the topic template exists to make it avoidable.
PERSON = 'Обучение на '
TOPIC = 'Обучение: '

MODES = {'профессия': 'person', 'тема': 'topic'}


def format_price(price):
    """32200 -> «32 200» — the way the price reads on the landing page."""
    return '{:,}'.format(int(price)).replace(',', ' ')


def _cap(value):
    return value[:1].upper() + value[1:] if value else value


# --- Сборка строк (1.7) ----------------------------------------------------

def opening_for(entry):
    """The opening, or None when the name already supplies one.

    «Обучение: Обучение и развитие персонала» stutters and «Обучение: 1С:
    Комплексная автоматизация» has two colons in five words. In both cases the
    bare name reads better and still carries the word the autotargeting looks
    for, so the prefixed rungs are simply not offered.
    """
    name = entry.get('name') or ''
    if entry.get('mode') == 'person':
        return PERSON + _cap(entry.get('accusative') or name)
    if ':' in name or re.match(r'\s*обучени', name, re.I):
        return None
    return TOPIC + name


def title_options(entry, cfg):
    """Title wordings from the richest to the barest.

    Only the decoration differs between them: the name itself is identical in
    every option, which is what guarantees the meaning survives the fit.
    """
    tail = cfg.get('title_tail', DEFAULT_TITLE_TAIL)
    name = entry.get('name') or ''
    lead = opening_for(entry)
    if lead is None:
        return [name + tail, name]
    if entry.get('mode') == 'person':
        # «Обучение на» carries meaning here — it says the course trains you to
        # be this — so it outlives the ending.
        return [lead + tail, lead, name + tail, name]
    # In topic mode the opening is a bare label. The ending names the document
    # the student receives, which is one of the three things an edtech buyer
    # decides on, so it is worth more than the word «Обучение:».
    return [lead + tail, name + tail, lead, name]


def text_options(entry, price, cfg):
    """Body wordings, same idea: the duration goes first, the standing offer
    next, the «Обучение на» opening last — it is what the autotargeting reads.

    The duration is read from the cached entry, not from today's crawl: it is
    frozen when the copy is written, so a wording change on the site cannot
    rewrite a live offer and reset its statistics. The price is the opposite —
    it is substituted fresh every build, because Direct requires the figure in
    the ad to match the landing page.
    """
    offer = (cfg.get('offer_tail') or '').strip()
    duration = entry.get('duration') or ''
    name = entry.get('name') or ''
    money = 'за %s ₽' % format_price(price)
    lead = opening_for(entry)
    if lead is None:
        lead = name
    elif entry.get('mode') == 'person':
        lead = PERSON + (entry.get('accusative') or name)

    def line(head, with_duration, with_offer):
        out = '%s %s' % (head, money)
        if with_duration and duration:
            out += ', %s' % duration
        if with_offer and offer:
            # The duration carries its own full stop («5 мес.»), so the sentence
            # break before the standing offer has to replace it, not follow it.
            out = '%s. %s' % (out.rstrip('. '), offer)
        return out

    seen, options = set(), []
    for head, dur, off in ((lead, True, True), (lead, False, True),
                           (lead, True, False), (lead, False, False),
                           (name, False, False)):
        candidate = line(head, dur, off)
        if candidate not in seen:
            seen.add(candidate)
            options.append(candidate)
    return options


def _fit(options, limit):
    """First wording that fits, or the shortest one when none does."""
    for i, option in enumerate(options):
        if len(option) <= limit:
            return option, i
    shortest = min(options, key=len)
    return shortest, options.index(shortest)


def assemble(entry, price, cfg):
    """Build both lines for today's price. Returns (title, text, rungs)."""
    title, ti = _fit(title_options(entry, cfg), TITLE_LIMIT)
    text, xi = _fit(text_options(entry, price, cfg), TEXT_LIMIT)
    return title, text, (ti, xi)


def name_room(price):
    """Longest name that can still be carried by the barest wording of both
    lines. The title is the tighter of the two at any realistic price."""
    money = len(' за %s ₽' % format_price(price))
    return min(TITLE_LIMIT, TEXT_LIMIT - money)


# --- Промпт (1.2) ----------------------------------------------------------

SYSTEM = """Ты называешь профессию или тему учебной программы для объявления
Яндекс Директа. Клиент — центр дополнительного профессионального образования.

Пиши по-русски, без эмодзи, без кавычек, без CAPS, без цифр.
Ты работаешь только с выданными фактами. Ничего не добавляй: ни трудоустройства,
ни гарантий, ни господдержки, ни лицензий, ни отзывов.

Ответ — только JSON, без пояснений и без markdown:
{"mode": "профессия", "name": "Логопед", "accusative": "логопеда"}"""


def _rules(cfg, facts, price):
    profession = facts.get('profession') or ''
    room = name_room(price)

    declension = ['Поле name — профессия в именительном падеже, с заглавной буквы.',
                  'Поле accusative — она же в винительном, со строчной:',
                  'объявление читается как «%sлогопеда».' % PERSON]

    if recommend_mode(facts) == 'person' and trusted_source(facts):
        # The page states this qualification outright, so there is nothing to
        # second-guess: doubting it here is how «Обучение на Бухгалтера» turned
        # into «Бухгалтерский учет на предприятиях общественного питания».
        choice = ['Режим: "профессия". Страница прямо называет квалификацию — «%s».'
                  % profession] + declension
    elif recommend_mode(facts) == 'person':
        choice = ['Режим: "профессия", но профессия извлечена не из поля квалификации,',
                  'а по косвенному признаку, поэтому проверь её сам: «%s» —' % profession,
                  'можно ли сказать «он работает <кем>»? Логопедом — можно.',
                  'Анализом финансовых вложений, детским фитнесом — нельзя,',
                  'это занятие, а не человек. Нельзя — ставь режим "тема".'] + declension
    elif profession:
        choice = ['Режим: "тема". В фактах названа тема — «%s», а не человек.'
                  % profession,
                  'Профессию для неё выдумывать нельзя.',
                  'Поле name — название темы, поле accusative оставь пустым.']
    else:
        choice = ['Режим: "тема". Профессия не извлечена.',
                  'Режим "профессия" допустим, только если она прямо названа в',
                  'названии программы. Домысливать её нельзя.',
                  'В режиме "тема" поле accusative оставь пустым.']

    lines = choice + [
        '',
        'ГЛАВНОЕ ПРАВИЛО',
        'Название должно точно передавать смысл программы. Смысл важнее краткости.',
        'Обрамление («%s», «%s») подставим мы сами и уберём, если не хватит места,'
        % (PERSON.strip(), cfg.get('title_tail', DEFAULT_TITLE_TAIL).strip('. ')),
        'поэтому ужимать название ради него не надо.',
        '',
        'ДЛИНА',
        '1. Название — не длиннее %d символов. Это жёсткий предел.' % room,
        '2. В пределах этого дай самую короткую формулировку, которая не теряет',
        '   смысл. Уложишься в %d — объявление получится полным.' % (room - 21),
        '3. Не сокращай слова точками: «гос.», «проф.», «мун.» недопустимы.',
        '   Не помещается — выбирай формулировку короче, а не обрубок.',
        '4. Названия продуктов и аббревиатуры пиши как на странице, с заглавных:',
        '   Figma, 1С, ОВЗ, Microsoft Excel. Строчными их писать нельзя.',
        '5. Сохраняй пунктуацию названия. «Ресторанный бизнес: управление',
        '   предприятием питания» без двоеточия читается как набор слов.',
        '',
        'ЧЕГО НЕЛЬЗЯ',
        '1. Называть соседнюю профессию. Для программы про финансовую',
        '   безопасность «финансовый аналитик» недопустим: это другая',
        '   специальность.',
        '2. Вводить слова, которых нет в фактах. Синонимы не подбирай.',
        '3. Писать цифры: цена и срок подставляются кодом.',
    ]

    forbidden = cfg.get('forbidden_phrases', [])
    if forbidden:
        lines += ['', 'ЗАПРЕЩЕННЫЕ ФОРМУЛИРОВКИ (не употреблять ни в каком виде):',
                  '; '.join(sorted(set(forbidden), key=len, reverse=True)[:8])]
    return '\n'.join(lines)


def build_messages(facts, cfg, price):
    """Chat messages for one program: the rules, then the facts as fields."""
    known = [('Профессия', facts.get('profession')),
             ('Название программы', facts.get('program')),
             ('Тип программы', facts.get('kind')),
             ('Объём, академических часов', facts.get('hours')),
             ('Срок обучения', facts.get('duration_months'))]
    block = '\n'.join('%s: %s' % (k, v) for k, v in known if v)
    user = '%s\n\nФАКТЫ О ПРОГРАММЕ\n%s' % (_rules(cfg, facts, price), block)
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': user}]


def parse(answer):
    """Read the model's JSON, tolerating a markdown fence around it."""
    body = answer.strip()
    if body.startswith('```'):
        body = re.sub(r'^```[a-z]*\s*|\s*```$', '', body, flags=re.S)
    m = re.search(r'\{.*\}', body, re.S)
    data = json.loads(m.group(0) if m else body)
    mode = MODES.get(str(data.get('mode') or '').strip().lower(), '')
    return dict(mode=mode,
                name=re.sub(r'\s+', ' ', str(data.get('name') or '')).strip(' .,:;«»"'),
                accusative=re.sub(r'\s+', ' ',
                                  str(data.get('accusative') or '')).strip(' .,:;«»"'))


# --- Проверка вывода (1.5) -------------------------------------------------

EMOJI = re.compile('[\U0001F000-\U0001FAFF←-⯿️‍]+')

# Words are compared by a fixed-length prefix, not by cutting the ending off:
# «логопед» and «логопеда» have to land on the same stem, and trimming two
# characters from each gives «логоп» and «логопе». Five characters is long
# enough that a shared stem means the same word rather than a common prefix.
STEM = 5

# Prepositions end the noun phrase that names the subject: in «Специалист по
# управлению рисками» only «Специалист» describes who is being trained.
PREPOSITIONS = ('по', 'в', 'с', 'для', 'на', 'о', 'об', 'при', 'из', 'к', 'у', 'за')

# Endings a person's name never takes, but a subject does: «Финансовая
# безопасность», «Бизнес-коучинг». Deliberately short — «-ика» would reject
# «Аналитик», «-ние» «Образование» — so this catches the common slip and the
# judge model (1.10) owns the rest.
TOPIC_ENDINGS = ('ость', 'есть', 'инг', 'инга', 'инге', 'ство')

# Choosing the mode is a looser question than rejecting a finished name, so it
# uses a wider net: a qualification never ends in «-ние» or «-ия», a programme
# title routinely does («Специальное дефектологическое образование»). These are
# not in TOPIC_ENDINGS because there they would reject «Преподаватель
# рисования», where the -ния word is a dependent, not the profession.
FIELD_ENDINGS = TOPIC_ENDINGS + ('ние', 'ния', 'ие', 'ия')

# A short Russian word followed by a full stop is a clipped word, not a
# sentence: a name holds one phrase and never ends a sentence mid-line.
ABBREVIATION = re.compile(r'[А-Яа-яЁё]{2,4}\.(?=\s|$)')

# What a line looks like when it was cut in the wrong place. Each of these
# reached a live ad: «Кадастровый инженер дистанционно —. Диплом!» (a dash left
# hanging because the tidy-up stripped the ASCII hyphen and not the em dash),
# «Няня (работник по уходу и присмотру. Диплом!» (cut inside a bracket) and
# «…управление. Диплом!!» (an ending appended to a name that already had one).
ARTEFACTS = (
    ('висящее тире', re.compile(r'[—–-]\s*[.,!?;:]')),
    ('сдвоенная пунктуация', re.compile(r'[.,!?;:]\s*[.,!?;:]')),
    ('пробел перед знаком', re.compile(r'\s[.,!?;:]')),
    ('незакрытая скобка', re.compile(r'\([^)]*$')),
    ('незакрытая кавычка', re.compile(r'«[^»]*$')),
    # A preposition at the end of a phrase, whether the line ends there or the
    # next sentence begins: «Психолог-консультант переподготовка с. Диплом!»
    ('обрывается на предлоге',
     re.compile(r'\s(и|или|с|со|для|по|на|от|в|во|к|у|о|об|за|из|при)\s*([.,;!]|$)', re.I)),
    # «Обучение: Обучение КПТ для психологов» — the opening repeats the first
    # word of a name that already carried it.
    # «Обучение: Обучение КПТ для психологов», «Обучение: Кризисный психолог
    # обучение на базе» — the opening repeats a word the name already carried,
    # next to it or further along. Checked against both live feeds: it matches
    # those four titles and nothing else in 568 offers.
    ('повтор слова', re.compile(r'^(\w{5,})\b.*?\b\1\b', re.I)),
)


def artefacts(text):
    """Names of the cut-in-the-wrong-place patterns this line matches."""
    return [name for name, rx in ARTEFACTS if rx.search(text or '')]


def tidy(text):
    """Repair what cutting a phrase short leaves behind.

    Cheaper and more reliable than trying to cut correctly everywhere: the cut
    happens in several places for several reasons, and the mess it makes is
    always the same handful of shapes.
    """
    if not text:
        return text
    text = re.sub(r'\s*[—–-]+\s*([.,!?;:])', r'\1', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'([.,!?;:])[\s]*[.,!?;:]+', r'\1', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip(' ,;:—–-')


def _words(value):
    return [w for w in re.findall(r'[\w-]+', (value or '').lower()) if len(w) >= STEM]


def _stems(*values):
    return {w[:STEM] for value in values for w in _words(value)}


def _digits(text):
    return set(re.findall(r'\d+', text or ''))


def _head_words(value):
    """Words up to the first preposition — the part that names the subject."""
    out = []
    for word in re.findall(r'[\w-]+', (value or '').lower()):
        if word in PREPOSITIONS:
            break
        out.append(word)
    return out


# Rules whose hit is the profession itself rather than a guess at it: the
# qualification the page states, and a title phrased «Обучение на <кого-то>».
# Everything else lands on a marketing label as often as on a profession.
TRUSTED_SOURCES = ('qualification', 'profession_phrase')


def trusted_source(facts):
    return (facts.get('sources') or {}).get('profession') in TRUSTED_SOURCES


def recommend_mode(facts):
    """Pick the mode in code, the way the character budget is picked in code.

    Left to itself the model gets skittish: warned that inventing a profession
    is a hard error, it retreats to the topic wording even for «Бухгалтер»,
    where «Обучение на Бухгалтера» is plainly right.
    """
    # A verdict measured against Wordstat beats any guess made from spelling:
    # whichever bundle people actually search for is the one to advertise. It is
    # decided offline by eval/wordstat_compare.py and stored in the client
    # config, so the daily run stays deterministic and makes no API calls.
    hint = facts.get('mode_hint')
    if hint in ('person', 'topic'):
        return hint
    profession = facts.get('profession') or ''
    if not profession:
        return 'topic'
    head = _head_words(profession)
    return 'topic' if any(w.endswith(FIELD_ENDINGS) for w in head) else 'person'


def validate(entry, title, text, facts, cfg, price):
    """Everything a regex can settle, checked on every generated offer."""
    name = entry.get('name') or ''
    if not entry.get('mode') or not name:
        return ['модель не вернула режим или название']

    problems = []
    room = name_room(price)
    if len(name) > room:
        problems.append('название %d символов при пределе %d — нужна формулировка '
                        'короче, но без потери смысла' % (len(name), room))
    if entry['mode'] == 'person' and not entry.get('accusative'):
        problems.append('нет винительного падежа в поле accusative')
    if len(title) > TITLE_LIMIT:
        problems.append('заголовок %d символов при лимите %d' % (len(title), TITLE_LIMIT))
    if len(text) > TEXT_LIMIT:
        problems.append('текст %d символов при лимите %d' % (len(text), TEXT_LIMIT))

    # The accusative has to be the same words, not a different name: the two
    # lines would otherwise advertise two different things.
    if entry.get('accusative') and _stems(name) - _stems(entry['accusative']):
        problems.append('винительный падеж «%s» не совпадает с названием «%s»'
                        % (entry['accusative'], name))

    # Every word of the name has to come from the facts. Checking that merely
    # one word overlaps is not enough: «Финансовый аналитик» for a course in
    # financial security shares «финанс» and would slip through.
    known = _stems(facts.get('profession'), facts.get('program'))
    invented = [w for w in _words(name) if w[:STEM] not in known]
    if known and invented:
        problems.append('слова «%s» нет в фактах программы — не выдумывай, возьми '
                        'формулировку из названия программы' % invented[0])

    if entry['mode'] == 'person':
        # An animate masculine noun changes in the accusative — «логопед» becomes
        # «логопеда». One that comes back unchanged is a thing, not a person:
        # «Обучение на Анализ финансовых вложений», «Обучение на Детский фитнес».
        if entry.get('accusative', '').lower() == name.lower():
            problems.append('«%s» в винительном падеже не меняется, значит это не человек: '
                            'переключись на режим "тема"' % name)
        topic = [w for w in _head_words(name) if w.endswith(TOPIC_ENDINGS)]
        if topic:
            problems.append('«%s» — это тема, а не человек: либо назови профессию, '
                            'либо переключись на режим "тема"' % topic[0])

    allowed = _digits(' '.join(str(facts.get(f) or '') for f in
                               ('profession', 'program', 'hours', 'duration_months')))
    stray = _digits(name) | _digits(entry.get('accusative') or '')
    if stray - allowed:
        problems.append('в названии цифры, которых не было в фактах: %s'
                        % ', '.join(sorted(stray - allowed)))

    clipped = ABBREVIATION.search(name) or ABBREVIATION.search(entry.get('accusative') or '')
    if clipped:
        problems.append('«%s» — обрубок слова: подбери формулировку короче, '
                        'а не сокращай точкой' % clipped.group(0))

    blob = ('%s %s' % (title, text)).lower()
    for phrase in cfg.get('forbidden_phrases', []):
        if phrase.lower() in blob:
            problems.append('запрещённая формулировка: %s' % phrase)
    if EMOJI.search(name) or EMOJI.search(entry.get('accusative') or ''):
        problems.append('в названии эмодзи')
    return problems


# --- Повтор и фолбэк (1.6) -------------------------------------------------

RETRY_INTRO = ('Твой прошлый ответ не прошёл проверку:\n%s\n\n'
               'Исправь ровно эти замечания и верни JSON того же вида. '
               'Остальное не переписывай.')


def generate(facts, cfg, price, client, fallback, retries=2):
    """Copy for one offer: model, then retries with the exact complaints, then
    the deterministic algorithm.

    `fallback` is a callable returning (title, text) built the old way. It is
    passed in rather than imported so that feed.py keeps owning the legacy rules
    and this module stays free of a circular import.

    Returns (title, text, entry, meta). `entry` is what gets cached in the run
    state — the name and its accusative, never the finished line, so that the
    next build can put a fresh price into it.
    """
    messages = build_messages(facts, cfg, price)
    last_problems = []
    budget_gone = False
    used = 0
    for attempt in range(retries + 1):
        used = attempt + 1
        try:
            answer = client.chat(messages)
        except BudgetExceeded as exc:
            last_problems = ['потолок расходов исчерпан: %s' % exc]
            budget_gone = True
            break
        except Exception as exc:
            last_problems = ['вызов не удался: %s' % str(exc)[:140]]
            break
        try:
            entry = parse(answer)
            entry['duration'] = facts.get('duration_months') or ''
        except Exception:
            entry = dict(mode='', name='', accusative='', duration='')
        title, text, rungs = assemble(entry, price, cfg)
        problems = validate(entry, title, text, facts, cfg, price)
        if not problems:
            return title, text, entry, dict(source='model', attempts=used,
                                            mode=entry['mode'], rungs=rungs)
        last_problems = problems
        messages = messages + [
            {'role': 'assistant', 'content': answer},
            {'role': 'user', 'content': RETRY_INTRO % '\n'.join('- %s' % p for p in problems)},
        ]

    title, text = fallback()
    return title, text, None, dict(source='fallback', attempts=used, mode='legacy',
                                   rungs=(0, 0), problems=last_problems,
                                   exhausted=budget_gone)
