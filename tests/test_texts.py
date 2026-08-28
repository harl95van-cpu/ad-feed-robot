"""Assembling the ad and checking what came back from the model.

Two rules carry most of the weight here. The name of the programme is never
shortened to make room — decoration goes instead, because a title that says
exactly what the course is beats a well-formed one that says something else.
And nothing numeric is ever written by the model: the price is substituted on
every build, so a price change on the site cannot trigger a rewrite that would
reset the statistics Direct has on the offer."""

import texts


CONFIG = {
    "title_tail": ". Диплом!",
    "offer_tail": "Рассрочка 0%.",
    "forbidden_phrases": ["Санкт-Петербург"],
}

FACTS = {
    "profession": "Логопед",
    "program": "Логопедия и коррекционная педагогика",
    "hours": "600",
    "duration_months": "5 мес.",
}

SHORT = {"mode": "person", "name": "Логопед", "accusative": "логопеда",
         "duration": "5 мес."}


def entry(**over):
    base = dict(SHORT)
    base.update(over)
    return base


# --- the ladder -------------------------------------------------------------

def test_a_name_that_fits_keeps_the_full_wording():
    title, text, rungs = texts.assemble(SHORT, 25300, CONFIG)

    assert title == "Обучение на Логопеда. Диплом!"
    assert text == "Обучение на логопеда за 25 300 ₽, 5 мес. Рассрочка 0%."
    assert rungs == (0, 0)


def test_a_long_name_costs_the_decoration_not_the_meaning():
    """«Специалист по коррекции поведенческих расстройств» does not fit any
    decorated wording. Truncating it to «Специалист по коррекции» would leave
    the reader asking «коррекции чего?», so the ending and the opening go."""
    long_name = entry(name="Специалист по коррекции поведенческих расстройств",
                      accusative="специалиста по коррекции поведенческих расстройств",
                      duration="")

    title, text, _ = texts.assemble(long_name, 36500, CONFIG)

    assert title == "Специалист по коррекции поведенческих расстройств"
    assert len(title) <= texts.TITLE_LIMIT
    assert long_name["accusative"] in text
    assert len(text) <= texts.TEXT_LIMIT


def test_the_body_gives_up_the_duration_before_the_standing_offer():
    """The duration is on the landing page anyway; the instalment plan is the
    client's selling point, so it is the later of the two to go."""
    medium = entry(name="Фитнес-тренер по аэробике и степу",
                   accusative="фитнес-тренера по аэробике и степу")

    _, text, rungs = texts.assemble(medium, 25300, CONFIG)

    assert rungs[1] == 1
    assert "5 мес." not in text
    assert text.endswith("Рассрочка 0%.")


def test_the_body_keeps_the_opening_longest_because_autotargeting_reads_it():
    long_name = entry(name="Специалист по коррекции поведенческих расстройств",
                      accusative="специалиста по коррекции поведенческих расстройств",
                      duration="")

    _, text, _ = texts.assemble(long_name, 36500, CONFIG)

    assert text.startswith(texts.PERSON)
    assert "Рассрочка" not in text


def test_topic_mode_uses_the_other_opening():
    topic = {"mode": "topic", "name": "Финансовая безопасность бизнеса",
             "accusative": "", "duration": ""}

    title, text, _ = texts.assemble(topic, 32200, CONFIG)

    assert title == "Обучение: Финансовая безопасность бизнеса. Диплом!"
    assert text.startswith(texts.TOPIC)


def test_a_topic_that_already_says_обучение_does_not_get_the_prefix():
    """«Обучение: Обучение и развитие персонала» stutters, and the bare name
    still carries the word the autotargeting looks for."""
    stutter = {"mode": "topic", "name": "Обучение и развитие персонала",
               "accusative": "", "duration": ""}

    title, text, _ = texts.assemble(stutter, 27300, CONFIG)

    assert title == "Обучение и развитие персонала. Диплом!"
    assert text.startswith("Обучение и развитие персонала за")


def test_a_topic_that_already_has_a_colon_does_not_get_a_second_one():
    colon = {"mode": "topic", "name": "1С: Комплексная автоматизация",
             "accusative": "", "duration": ""}

    title, _, _ = texts.assemble(colon, 27300, CONFIG)

    assert title == "1С: Комплексная автоматизация. Диплом!"


def test_a_duration_that_ends_in_a_full_stop_does_not_double_it():
    _, text, _ = texts.assemble(SHORT, 25300, CONFIG)

    assert ".." not in text


# --- the price is the only thing that changes between builds ----------------

def test_the_same_entry_renders_todays_price():
    _, cheap, _ = texts.assemble(SHORT, 25300, CONFIG)
    _, dearer, _ = texts.assemble(SHORT, 27900, CONFIG)

    assert "25 300 ₽" in cheap
    assert "27 900 ₽" in dearer


def test_price_is_grouped_the_way_the_landing_page_shows_it():
    assert texts.format_price(129000) == "129 000"


# --- choosing the mode ------------------------------------------------------

def test_a_named_profession_gets_the_person_wording():
    assert texts.recommend_mode({"profession": "Бухгалтер"}) == "person"


def test_a_field_of_study_gets_the_topic_wording():
    assert texts.recommend_mode({"profession": "Финансовая безопасность"}) == "topic"


def test_a_programme_title_in_the_profession_slot_gets_the_topic_wording():
    """Extraction sometimes lands on the programme name — «Специальное
    дефектологическое образование» — and «Обучение на Специальное образование»
    is not Russian."""
    assert texts.recommend_mode(
        {"profession": "Специальное дефектологическое образование"}) == "topic"


def test_no_profession_at_all_gets_the_topic_wording():
    assert texts.recommend_mode({"profession": ""}) == "topic"


# --- reading the answer -----------------------------------------------------

def test_json_wrapped_in_a_markdown_fence_is_still_read():
    answer = '```json\n{"mode": "профессия", "name": "Логопед", "accusative": "логопеда"}\n```'

    assert texts.parse(answer)["name"] == "Логопед"


def test_mode_comes_back_in_the_language_the_code_uses():
    answer = '{"mode": "тема", "name": "Логопедия", "accusative": ""}'

    assert texts.parse(answer)["mode"] == "topic"


# --- checks on the answer ---------------------------------------------------

def check(entry_, price=25300, facts=None):
    title, text, _ = texts.assemble(entry_, price, CONFIG)
    return texts.validate(entry_, title, text, facts or FACTS, CONFIG, price)


def test_a_good_answer_raises_nothing():
    assert check(SHORT) == []


def test_a_neighbouring_profession_is_rejected():
    """«Финансовый аналитик» for a course in financial security shares the word
    «финанс» with the facts, so an overlap check that accepts one matching word
    lets it through. Every word has to be backed."""
    facts = {"profession": "Финансовая безопасность бизнеса",
             "program": "Экономическая и финансовая безопасность бизнеса"}
    invented = {"mode": "person", "name": "Финансовый аналитик",
                "accusative": "финансового аналитика", "duration": ""}

    problems = check(invented, 32200, facts)

    assert any("аналитик" in p for p in problems)


def test_a_field_dressed_up_as_a_person_is_rejected():
    facts = {"profession": "Финансовая безопасность бизнеса",
             "program": "Финансовая безопасность бизнеса"}
    wrong = {"mode": "person", "name": "Финансовая безопасность",
             "accusative": "финансовую безопасность", "duration": ""}

    problems = check(wrong, 32200, facts)

    assert any("тема" in p for p in problems)


def test_an_accusative_that_names_something_else_is_rejected():
    mismatched = entry(accusative="дефектолога")

    assert any("винительн" in p for p in check(mismatched))


def test_a_figure_the_facts_never_mentioned_is_rejected():
    invented = entry(name="Логопед 2026", accusative="логопеда 2026")

    assert any("цифр" in p for p in check(invented))


def test_a_forbidden_phrase_is_rejected_even_though_the_prompt_forbids_it():
    """The prompt lowers the odds, the check gives the guarantee: across
    thousands of programmes one percent of misses is dozens of live ads
    carrying a claim the client may not make."""
    facts = dict(FACTS, program="Логопедия Санкт-Петербург")
    banned = entry(name="Логопед Санкт-Петербург", accusative="логопеда Санкт-Петербург")

    assert any("Запрещ" in p or "запрещ" in p for p in check(banned, 25300, facts))


def test_a_word_clipped_with_a_full_stop_is_rejected():
    facts = dict(FACTS, program="Государственное и муниципальное управление")
    clipped = {"mode": "topic", "name": "Гос. управление", "accusative": "",
               "duration": ""}

    assert any("обрубок" in p for p in check(clipped, 25300, facts))


def test_a_name_longer_than_the_barest_wording_is_rejected():
    facts = dict(FACTS, program="Логопедия " * 10)
    huge = entry(name="Логопедия " * 8, accusative="логопедии " * 8)

    assert any("название" in p for p in check(huge, 25300, facts))


def test_an_empty_answer_is_rejected_without_touching_anything_else():
    empty = {"mode": "", "name": "", "accusative": "", "duration": ""}

    assert check(empty) == ["модель не вернула режим или название"]


def test_a_name_that_does_not_decline_is_not_a_person():
    """An animate masculine noun changes in the accusative — «логопед» becomes
    «логопеда». One that comes back untouched is a thing: «Обучение на Анализ
    финансовых вложений» is not Russian."""
    facts = {"profession": "Анализ финансовых вложений",
             "program": "Анализ финансовых вложений"}
    thing = {"mode": "person", "name": "Анализ финансовых вложений",
             "accusative": "анализ финансовых вложений", "duration": ""}

    problems = check(thing, 9000, facts)

    assert any("не человек" in p for p in problems)


# --- how much the extracted profession is trusted ---------------------------

def test_a_stated_qualification_is_trusted():
    """The page saying «с присвоением квалификации «Бухгалтер»» is the profession
    the graduate receives. Second-guessing it is how «Обучение на Бухгалтера»
    became «Бухгалтерский учет на предприятиях общественного питания»."""
    assert texts.trusted_source({"sources": {"profession": "qualification"}})


def test_a_label_scraped_out_of_the_page_title_is_not_trusted():
    """That rule lands on «Анализ финансовых вложений» as readily as on a
    profession, so the copy has to be asked to check it."""
    assert not texts.trusted_source({"sources": {"profession": "heuristic"}})


def test_a_wordstat_verdict_overrides_the_spelling_guess():
    """«Обучение графическому дизайну» is searched seven times more often than
    «обучение на графического дизайнера», and no amount of reasoning about word
    endings would have found that out."""
    facts = {"profession": "Графический дизайнер", "mode_hint": "topic"}

    assert texts.recommend_mode(facts) == "topic"


def test_without_a_verdict_the_spelling_guess_still_applies():
    assert texts.recommend_mode({"profession": "Бухгалтер", "mode_hint": ""}) == "person"


# --- what the title gives up first ------------------------------------------

def test_in_topic_mode_the_document_outlives_the_opening():
    """«Обучение:» is a bare label; «. Диплом!» names the document the student
    receives, which is one of the three things an edtech buyer decides on."""
    topic = {"mode": "topic", "name": "Графический дизайн и визуальные коммуникации",
             "accusative": "", "duration": ""}

    title, _, rungs = texts.assemble(topic, 34200, CONFIG)

    assert title == "Графический дизайн и визуальные коммуникации. Диплом!"
    assert rungs[0] == 1


def test_in_person_mode_the_opening_outlives_the_document():
    """Here «Обучение на» carries meaning — it says the course trains you to be
    this — so it is the ending that goes."""
    person = {"mode": "person", "name": "Специалист по коррекции нарушений речи",
              "accusative": "специалиста по коррекции нарушений речи", "duration": ""}

    title, _, rungs = texts.assemble(person, 34200, CONFIG)

    assert title.startswith(texts.PERSON)
    assert not title.endswith("Диплом!")


# --- debris left by cutting a phrase short ----------------------------------

def test_a_dash_left_hanging_before_a_full_stop_is_removed():
    """The sites write «—» and the old tidy-up stripped «-», so this shipped."""
    assert texts.tidy("Обучение: Кадастровый инженер дистанционно —. Диплом!") == \
        "Обучение: Кадастровый инженер дистанционно. Диплом!"


def test_an_ending_appended_twice_collapses():
    assert texts.tidy("Обучение: Гос. управление. Диплом!!") == \
        "Обучение: Гос. управление. Диплом!"


def test_a_clean_line_is_left_exactly_as_it_is():
    for line in ("Обучение на Логопеда. Диплом!",
                 "1С: Комплексная автоматизация. Диплом!",
                 "Обучение на тренера-преподавателя по хоккею за 25 300 ₽, 5 мес."):
        assert texts.tidy(line) == line


def test_every_shape_that_reached_a_live_ad_is_recognised():
    assert texts.artefacts("Кадастровый инженер дистанционно —. Диплом!")
    assert texts.artefacts("Гос. управление. Диплом!!")
    assert texts.artefacts("Няня (работник по уходу и присмотру. Диплом!")
    assert texts.artefacts("Обучение на Логопеда. Диплом!") == []
