"""A catalogue whose ids are url slugs rather than short numbers.

The first two clients number their programmes, so every disambiguating tag was
a handful of digits and nothing ever tested a long one. The third keeps a Tilda
store, where the id is the page slug — and three programmes whose titles
collapse onto the same 45-character prefix came out as

    Обучение: Дефектология. Работа (id defektologiya-narushenie-…-noda)

at 94 to 105 characters: past the display limit, and past the 100 the feed
format itself allows, so Direct would reject the offer outright.
"""

import feed
import texts


CONFIG = {
    "base_url": "https://example.ru",
    "offer_tail": "Обучение дистанционно.",
    "forbidden_phrases": [],
    "label_source": "name",
    "categories": [{"id": "7", "name": "Переподготовка"}],
    "facts": {"profession": [], "program": [], "hours": [],
              "duration_months": [], "kind": []},
}

LONG = "defektologiya-zaderzhka-psihicheskogo-razvitiya-zpr"


def named(*pairs):
    """Offers carrying only what the dedupe passes look at."""
    return [dict(id=oid, name=name, hours="") for oid, name in pairs]


# --- the tag that goes into a title -----------------------------------------

def test_a_short_numeric_id_is_used_as_it_is():
    """The two clients already running must keep the titles they have — a new
    tag on an old offer is a rewritten ad and a reset set of statistics."""
    assert feed._mark("101") == "101"
    assert feed._mark("76808") == "76808"


def test_a_slug_is_reduced_to_its_own_last_segment():
    """Which is the client's own abbreviation, so the tag still says something."""
    assert feed._mark(LONG) == "zpr"
    assert feed._mark("defektologiya-rasstroystva-autisticheskogo-spektra-ras") == "ras"


def test_a_slug_with_no_short_tail_falls_back_to_a_hash():
    mark = feed._mark("defektolig-perepodgotovka-professionalnaya")

    assert len(mark) <= feed.MARK_LIMIT
    assert mark.isalnum()


def test_the_tag_is_stable_across_runs():
    """An unstable tag rewrites the ad every morning."""
    assert feed._mark(LONG) == feed._mark(LONG)


# --- what the dedupe pass may produce ---------------------------------------

def test_a_deduped_title_stays_within_the_display_limit():
    offers = named((LONG, "Обучение: Дефектология. Работа с обучающимися"),
                   ("defektologiya-tiflopedagogika",
                    "Обучение: Дефектология. Работа с обучающимися"))

    feed._dedupe_names(offers)

    for o in offers:
        assert len(o["name"]) <= texts.TITLE_LIMIT, o["name"]
    assert offers[0]["name"] != offers[1]["name"]


def test_the_guard_against_the_rewrite_loop_recognises_a_slug_tag():
    """DEDUPED is what stops the repair pass and the dedupe pass from undoing
    each other every run. A tag it fails to recognise brings that loop back —
    the most expensive bug this robot has had."""
    offers = named((LONG, "Обучение: Дефектология. Работа с обучающимися"),
                   ("defektologiya-tiflopedagogika",
                    "Обучение: Дефектология. Работа с обучающимися"))

    feed._dedupe_names(offers)

    for o in offers:
        assert feed.DEDUPED.search(o["name"]), o["name"]


def test_hours_are_still_preferred_over_an_id():
    offers = [dict(id="101", name="Обучение: Логопед", hours="600"),
              dict(id="102", name="Обучение: Логопед", hours="340")]

    feed._dedupe_names(offers)

    assert offers[0]["name"].endswith("(600 ч)")
    assert offers[1]["name"].endswith("(340 ч)")


def test_a_bracketed_phrase_is_not_mistaken_for_a_tag():
    assert not feed.DEDUPED.search("Обучение: Няня (работник по уходу)")


# --- a quote the source never closed ----------------------------------------

def test_a_label_the_client_left_open_is_closed():
    """The store card is typed by hand and this one is named «Профессия
    «Адаптивная физкультура» — it reached a live title with the quote hanging."""
    program = {"id": "1", "name": "Профессия «Адаптивная физкультура"}

    label = feed.label_of({}, "name", program)

    assert label == "Профессия «Адаптивная физкультура»"
    assert not texts.artefacts(label)


def test_a_quote_inside_the_name_survives_the_decoration_strip():
    """The strip exists to undo «Логопед» → Логопед, where it takes both marks.
    On a name whose quote sits inside, it took the closing one and left the
    opening one behind — the same dangling quote, arrived at from the other
    direction."""
    program = {"id": "1", "name": "Курс «Логопедия»"}

    label = feed.label_of({}, "name", program)

    assert label == "Курс «Логопедия»"
    assert not texts.artefacts(label)


def test_decorative_quotes_around_the_whole_name_are_still_dropped():
    assert feed.label_of({}, "name", {"id": "1", "name": "«Логопед»"}) == "Логопед"


def test_the_finished_title_carries_no_open_quote():
    program = {"id": "1", "name": "Профессия «Адаптивная физкультура",
               "price": 15000, "oldprice": None, "hints": [], "url": "/x/"}

    name = feed.build_name({}, program, [], "name", "kind", CONFIG)

    assert not texts.artefacts(name)
    assert len(name) <= texts.TITLE_LIMIT
