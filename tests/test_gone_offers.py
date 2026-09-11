"""A programme retired from the catalogue, and the state file it left behind.

It stays in the feed one more cycle as unavailable so Direct stops serving it
instead of erroring on an offer that is simply gone. That path runs only on the
day a programme is retired — weeks apart — so nothing exercised it, and the
stored entry was being appended to the offer list as if it were a finished
offer. It was not: `description` had been added to what the build reads long
before it was added to what the state keeps, so on 10 September both feeds died
on KeyError: 'description' at the first offer that had disappeared.
"""

import feed
import main as robot
import texts


CONFIG = {
    "base_url": "https://example.ru",
    "title_tail": ". Диплом!",
    "offer_tail": "Рассрочка 12 мес.",
    "forbidden_phrases": [],
    "label_source": "title",
    "categories": [{"id": "7", "name": "Переподготовка"}],
    "facts": {"profession": [], "program": [], "hours": [],
              "duration_months": [], "kind": []},
}

# A stored entry as the live buckets actually held it on 10 September: written
# by a build_state that did not keep the description.
OLD_STATE_ENTRY = {
    "name": "Обучение: Логопед. Диплом!",
    "categoryId": "7",
    "url": "https://example.ru/logoped/",
    "picture": "https://example.ru/p.jpg",
    "price": 25300,
    "oldprice": 29095,
    "available": "true",
}


def build(stored, cfg=None):
    """Run the assembly with an empty catalogue: every stored offer is gone."""
    return feed.build_offers({}, {}, cfg or CONFIG, {},
                             {"offers": stored}, feed.Generator(None, retries=2))


# --- the failure itself -----------------------------------------------------

def test_a_retired_programme_does_not_bring_the_run_down():
    offers = build({"101": dict(OLD_STATE_ENTRY)})

    assert len(offers) == 1
    assert offers[0]["available"] == "false"
    assert offers[0]["gone_cycles"] == 1


def test_the_missing_description_is_rebuilt_from_the_stored_title():
    """The page is unreachable by now, but the ad title still holds the course
    name, and course_label strips the decorations back off it."""
    offers = build({"101": dict(OLD_STATE_ENTRY)})

    assert "Логопед" in offers[0]["description"]
    assert not texts.artefacts(offers[0]["description"])


def test_a_revived_offer_passes_the_same_validation_as_a_live_one():
    offers = build({"101": dict(OLD_STATE_ENTRY)})

    assert feed.validate(offers, CONFIG) == []


def test_a_stored_description_is_kept_rather_than_rebuilt():
    """It is the text of an ad Direct has statistics on — the same reason the
    title is left alone."""
    entry = dict(OLD_STATE_ENTRY, description="Переподготовка: Логопед. Рассрочка.")

    offers = build({"101": entry})

    assert offers[0]["description"] == "Переподготовка: Логопед. Рассрочка."


def test_an_entry_too_thin_to_publish_is_dropped_not_half_built():
    """Nothing invents a category or a price. One extra cycle in the feed is a
    courtesy to Direct, not a requirement."""
    entry = {k: v for k, v in OLD_STATE_ENTRY.items() if k != "categoryId"}

    assert build({"101": entry}) == []


def test_a_programme_gone_for_a_second_cycle_leaves_the_feed():
    entry = dict(OLD_STATE_ENTRY, gone_cycles=1)

    assert build({"101": entry}) == []


# --- what keeps the two field lists together --------------------------------

def test_the_state_keeps_every_field_an_offer_needs():
    """This is the guard. A field added to OFFER_FIELDS and not to build_state
    is a run that crashes on the next retired programme, weeks later, in a
    branch no other test touches."""
    offer = dict(OLD_STATE_ENTRY, id="101", description="Переподготовка: Логопед.",
                 available="true", picture_source="site")

    kept = robot.build_state([offer], "2026-09-11")["offers"]["101"]

    for field in feed.OFFER_FIELDS:
        if field == "id":
            continue                        # it is the key, not a field
        assert field in kept, "build_state теряет поле %s" % field


def test_the_crossed_out_price_is_not_demanded_where_there_is_no_discount():
    cfg = dict(CONFIG, require_oldprice=False)
    entry = {k: v for k, v in OLD_STATE_ENTRY.items() if k != "oldprice"}

    assert len(build({"101": entry}, cfg)) == 1
