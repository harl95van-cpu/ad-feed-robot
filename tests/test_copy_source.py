"""Where an offer's copy comes from, and what happens when the model misbehaves.

The caching rule is the expensive one to get wrong. Rewriting the copy of a live
offer resets the statistics Direct has accumulated on it, which costs far more
than the model call it saves — so an offer that already has copy must come out
of this untouched, every run, forever."""

import json

import feed
import texts


CONFIG = {
    "base_url": "https://example.ru",
    "title_tail": ". Диплом!",
    "offer_tail": "Рассрочка 0%.",
    "forbidden_phrases": [],
    "label_source": "h1_quoted",
    "facts": {
        "profession": [{"source": "h1", "pattern": "квалификации\\s*«([^»]+)»",
                        "max_len": 60}],
        "program": [{"source": "h1", "pattern": "«([^»]+)»", "max_len": 160}],
        "hours": [{"source": "hints", "pattern": "^(\\d+)\\s*час", "min": 16, "max": 5000}],
        "duration_months": [],
        "kind": [{"source": "hints", "pattern": "^(\\D[\\w\\s-]{3,40})$"}],
    },
}

PAGE = {
    "title": "Логопед: курс переподготовки",
    "h1": "Курс «Логопедия» с присвоением квалификации «Логопед» (600 ч.)",
    "meta": "Курс переподготовки на логопеда.",
}

PROGRAM = {"id": "101", "name": "Логопедия", "url": "/logoped/",
           "price": 25300, "oldprice": 29095, "hints": ["600 часов", "Переподготовка"]}

CACHED = {"mode": "person", "name": "Логопед", "accusative": "логопеда",
          "duration": "5 мес."}


class FakeClient(object):
    """Answers from a script instead of from OpenRouter."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0
        self.spent = 0.0

    def chat(self, messages, temperature=None):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def answer(name="Логопед", accusative="логопеда", mode="профессия"):
    return json.dumps({"mode": mode, "name": name, "accusative": accusative},
                      ensure_ascii=False)


def legacy():
    return "Обучение: Старый заголовок. Диплом!", "Старый текст."


def copy_for(prev, client=None):
    generator = feed.Generator(client, retries=2)
    name, text, ad = feed._copy_for(PROGRAM, PAGE, prev, CONFIG, generator, legacy)
    return name, text, ad, generator


# --- where the copy comes from ----------------------------------------------

def test_a_cached_entry_is_reassembled_without_calling_the_model():
    client = FakeClient()

    name, text, ad, generator = copy_for({"ad": CACHED}, client)

    assert client.calls == 0
    assert name == "Обучение на Логопеда. Диплом!"
    assert "25 300 ₽" in text
    assert ad is CACHED
    assert generator.stats["cached"] == 1


def test_a_cached_entry_picks_up_todays_price():
    dearer = dict(PROGRAM, price=27900)
    generator = feed.Generator(FakeClient(), retries=2)

    _, text, _ = feed._copy_for(dearer, PAGE, {"ad": CACHED}, CONFIG, generator, legacy)

    assert "27 900 ₽" in text


def test_an_offer_that_predates_generation_keeps_the_copy_it_has():
    """Every offer in the live feed is in this state on the first run after
    deployment. Not one of them may be rewritten."""
    client = FakeClient()
    existing = {"name": "Обучение: Логопед. Диплом!"}

    name, _, ad, generator = copy_for(existing, client)

    assert client.calls == 0
    assert name == "Обучение: Логопед. Диплом!"
    assert ad is None
    assert generator.stats["kept"] == 1


def test_a_new_offer_is_written_by_the_model_and_cached():
    client = FakeClient(answer())

    name, text, ad, generator = copy_for({}, client)

    assert client.calls == 1
    assert name == "Обучение на Логопеда. Диплом!"
    assert ad["name"] == "Логопед"
    assert generator.stats["model"] == 1


def test_without_a_client_a_new_offer_falls_back_to_the_old_rules():
    name, text, ad, generator = copy_for({}, None)

    assert name.startswith("Обучение")
    assert ad is None
    assert generator.stats["legacy"] == 1


# --- retry and fallback -----------------------------------------------------

def facts_for_logoped():
    return {"profession": "Логопед", "program": "Логопедия", "hours": "600",
            "duration_months": ""}


def test_a_rejected_answer_is_sent_back_with_the_complaints():
    client = FakeClient(answer(name="Сварщик", accusative="сварщика"), answer())

    title, text, entry, meta = texts.generate(facts_for_logoped(), CONFIG, 25300,
                                              client, legacy, retries=2)

    assert client.calls == 2
    assert meta["source"] == "model"
    assert meta["attempts"] == 2
    assert entry["name"] == "Логопед"


def test_answers_that_never_pass_end_on_the_old_rules():
    client = FakeClient(*[answer(name="Сварщик", accusative="сварщика")] * 3)

    title, text, entry, meta = texts.generate(facts_for_logoped(), CONFIG, 25300,
                                              client, legacy, retries=2)

    assert client.calls == 3
    assert meta["source"] == "fallback"
    assert (title, text) == legacy()
    assert entry is None


def test_a_dead_api_does_not_stop_the_offer_from_being_built():
    """The feed is what matters; generation is an improvement on top of it. A
    provider outage must cost copy quality, never the daily rebuild."""
    client = FakeClient(RuntimeError("HTTP 400 no such model"))

    title, text, entry, meta = texts.generate(facts_for_logoped(), CONFIG, 25300,
                                              client, legacy, retries=2)

    assert meta["source"] == "fallback"
    assert meta["attempts"] == 1          # a fatal error is not retried
    assert (title, text) == legacy()


def test_unreadable_json_is_treated_as_a_failed_answer_not_a_crash():
    client = FakeClient("не JSON вовсе", answer())

    title, _, entry, meta = texts.generate(facts_for_logoped(), CONFIG, 25300,
                                           client, legacy, retries=2)

    assert meta["source"] == "model"
    assert entry["name"] == "Логопед"


def test_a_stale_instalment_promise_in_sales_notes_is_dropped():
    """The instalment terms live in one configured place. A second copy in
    another field goes stale silently — «Рассрочка на 24 и 36 месяцев» was still
    riding along from the client's own feed after the terms changed to 12."""
    assert feed.clean_sales_notes('Рассрочка на 24 и 36 месяцев') is None


def test_an_unrelated_special_offer_is_left_alone():
    assert feed.clean_sales_notes('Скидка 20% до конца месяца') == 'Скидка 20% до конца месяца'


def test_a_title_we_cut_too_short_is_restored_when_the_budget_relaxes():
    """«Обучение: Государственное. Диплом!» is what a tighter budget left of
    «Государственное и муниципальное управление». Once the budget is relaxed the
    fuller title should come back."""
    generator = feed.Generator(None, retries=2)
    clipped = {"name": "Обучение: Логопедия. Диплом!"}

    def fuller():
        return "Обучение: Логопедия и дефектология. Диплом!", "текст"

    name, _, _ = feed._copy_for(PROGRAM, PAGE, clipped, CONFIG, generator, fuller)

    assert name == "Обучение: Логопедия и дефектология. Диплом!"
    assert generator.stats["reshaped"] == 1


def test_a_title_that_merely_differs_is_left_alone():
    """Only our own truncation is repaired. A title that starts differently came
    from somewhere else and rewriting it would reset its statistics for nothing."""
    generator = feed.Generator(None, retries=2)
    theirs = {"name": "Дефектология: полный курс"}

    name, _, _ = feed._copy_for(PROGRAM, PAGE, theirs, CONFIG, generator, legacy)

    assert name == "Дефектология: полный курс"
    assert generator.stats["reshaped"] == 0


def test_a_title_the_dedupe_pass_shaped_is_never_repaired():
    """The repair and the dedupe pass pull in opposite directions. Dedupe trades
    «. Диплом!» for « (540 ч)» to tell two identical titles apart, which leaves
    the stored name one character shorter than the rules produce — so without
    this guard each run undoes the other and the offer is rewritten daily,
    resetting its statistics every morning."""
    generator = feed.Generator(None, retries=2)
    deduped = {"name": "Обучение: Педагог дополнительного образования (540 ч)"}

    def fuller():
        return "Обучение: Педагог дополнительного образования. Диплом!", "текст"

    name, _, _ = feed._copy_for(PROGRAM, PAGE, deduped, CONFIG, generator, fuller)

    assert name == deduped["name"]
    assert generator.stats["reshaped"] == 0


def test_the_document_wording_comes_from_the_config_when_it_is_there():
    """«Диплом» is meaningful for a Russian further-education provider and
    meaningless for a garage. It has to be replaceable without touching Python."""
    cfg = {"documents": {"Повышение квалификации": {"prefix": "Курс",
                                                    "document": "Сертификат"}}}

    assert feed.wording_for("Повышение квалификации", cfg) == ("Курс", "Сертификат")


def test_without_a_config_table_the_education_defaults_apply():
    assert feed.wording_for("Повышение квалификации") == ("Повышение квалификации",
                                                          "Удостоверение")


def test_a_project_that_issues_no_document_gets_no_exclamation_left_over():
    cfg = {"documents": {"Переподготовка": {"prefix": "Курс", "document": ""}}}
    program = dict(PROGRAM, offer_name="Обучение: Логопед. Диплом!")

    text = feed.build_description(PAGE, program, [], "Рассрочка 0%.", "title",
                                  "Переподготовка", cfg)

    assert text.endswith("Рассрочка 0%.")
    assert "Диплом" not in text


def test_a_price_absent_from_the_landing_page_is_reported():
    """Direct requires the ad price to match the page. The two drift on their
    own — a cached listing, a new tariff, an expired promotion."""
    assert feed.price_is_on_the_page(48300, {"body": "Стоимость 48 300 ₽ сегодня"})
    assert not feed.price_is_on_the_page(48300, {"body": "Стоимость 52 000 ₽ сегодня"})


def test_a_page_we_could_not_read_is_not_reported_as_a_mismatch():
    assert feed.price_is_on_the_page(48300, {})


def test_a_title_cut_in_the_wrong_place_is_rebuilt():
    """«Обучение: Кадастровый инженер дистанционно —. Диплом!» ran as a live ad.
    A stored name carrying that kind of debris is already spoiled, so the
    statistics a rebuild costs are worth less than the repair."""
    generator = feed.Generator(None, retries=2)
    broken = {"name": "Обучение: Кадастровый инженер дистанционно —. Диплом!"}

    def clean():
        return "Обучение: Кадастровый инженер. Диплом!", "текст"

    name, _, _ = feed._copy_for(PROGRAM, PAGE, broken, CONFIG, generator, clean)

    assert name == "Обучение: Кадастровый инженер. Диплом!"
    assert generator.stats["reshaped"] == 1


def test_debris_in_a_finished_offer_is_reported():
    cfg = dict(CONFIG, categories=[{"id": "1"}])
    offer = {"id": "1", "name": "Обучение: Няня (работник по уходу. Диплом!",
             "description": "Всё хорошо.", "url": "/x/", "picture": "p.jpg",
             "price": 1, "oldprice": 2, "categoryId": "1", "available": "true"}

    problems = feed.validate([offer], cfg)

    assert any("незакрытая скобка" in p for p in problems)


# --- what a search-engine page title drags in -------------------------------

def page_titled(title):
    return {"title": title, "h1": "", "meta": ""}


def test_a_search_engine_tail_is_dropped_from_the_label():
    """«Учитель логопед обучение» is written for a search engine. Keeping the
    tail produced «Обучение: Учитель логопед обучение. Диплом!» in a live ad."""
    assert feed.label_of(page_titled("Учитель логопед обучение")) == "Учитель логопед"


def test_dropping_the_tail_does_not_leave_a_preposition_hanging():
    """«…переподготовка с дипломом» loses its tail and would otherwise end on
    «с», which is how «Психолог-консультант переподготовка с. Диплом!» happened."""
    label = feed.label_of(page_titled("Психолог-консультант переподготовка с дипломом"))

    assert label == "Психолог-консультант переподготовка"


def test_a_short_label_is_not_eaten_by_the_tail_rule():
    """«Дистанционный курс оперативной психологии» once became «Дистанционный»."""
    title = "Дистанционный курс оперативной психологии"

    assert feed.label_of(page_titled(title)) == title


def test_the_opening_is_dropped_when_the_name_already_says_it():
    program = dict(PROGRAM, hints=["600 часов", "Переподготовка"])
    page = page_titled("Обучение КПТ для психологов онлайн")

    name = feed.build_name(page, program, [], "title", "Переподготовка")

    # «онлайн» goes with the rest of the search-engine tail, and the opening is
    # not added because the name opens with it already.
    assert name == "Обучение КПТ для психологов. Диплом!"


def test_a_name_that_already_names_its_kind_does_not_get_it_twice():
    """«Переподготовка: Переподготовка: Педагог-хореограф» was in the live feed."""
    program = dict(PROGRAM, offer_name="Переподготовка: Педагог-хореограф")

    text = feed.build_description(page_titled("Педагог-хореограф"), program, [],
                                  "Рассрочка 0%.", "title", "Переподготовка")

    assert text.count("Переподготовка") == 1
