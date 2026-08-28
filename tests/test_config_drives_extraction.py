"""The client config is the only place facts are extracted from.

There used to be a second, hardcoded copy of that logic in feed.py, and the two
could disagree. The dangerous half was the programme kind: it decides which
programmes enter the feed at all, so a config edited to fit a new site would
appear to work in the extraction check while the feed silently kept the old
behaviour — or silently dropped offers."""

import feed


def config(**over):
    base = {
        "base_url": "https://example.ru",
        "bucket": "bucket",
        "image_prefix": "img/x/",
        "title_tail": ". Диплом!",
        "offer_tail": "Рассрочка 0%.",
        "forbidden_phrases": [],
        "label_source": "title",
        "sections": {"/s/": "1"},
        "facts": {
            "profession": [],
            "program": [],
            "hours": [{"source": "hints", "pattern": "^(\\d+)", "min": 16, "max": 5000}],
            "duration_months": [],
            "kind": [{"source": "hints", "pattern": "^(\\D.{1,60})$"}],
        },
    }
    base.update(over)
    return base


def catalogue():
    return {
        "/retraining/": {"id": "1", "name": "Логопедия", "url": "/retraining/",
                         "price": 25300, "oldprice": 29095, "sections": ["/s/"],
                         "hints": ["600 часов", "Профессиональная переподготовка"]},
        "/refresher/": {"id": "2", "name": "Логопедия кратко", "url": "/refresher/",
                        "price": 9000, "oldprice": 11000, "sections": ["/s/"],
                        "hints": ["72 часа", "Повышение квалификации"]},
    }


def pages():
    return {"/retraining/": {"title": "Логопед: переподготовка", "h1": "", "meta": ""},
            "/refresher/": {"title": "Логопед: повышение", "h1": "", "meta": ""}}


def build(cfg):
    offers = feed.build_offers(catalogue(), pages(), cfg, {}, {"offers": {}},
                               feed.Generator())
    return {o["id"]: o for o in offers}


def test_include_kinds_filters_on_the_kind_the_config_extracted():
    built = build(config(include_kinds=["Профессиональная переподготовка"]))

    assert set(built) == {"1"}
    assert built["1"]["kind"] == "Профессиональная переподготовка"


def test_a_kind_rule_that_matches_nothing_changes_what_enters_the_feed():
    """The point of the consolidation: editing the rule has to move the feed.
    While feed.py kept its own copy, this rule could be broken and the filter
    would carry on using the hardcoded answer."""
    cfg = config(include_kinds=["Профессиональная переподготовка"])
    cfg["facts"]["kind"] = [{"source": "hints", "pattern": "^(ничему не соответствует)$"}]

    assert build(cfg) == {}


def test_hours_come_from_the_configured_range_not_from_a_second_rule():
    """72 hours is a real refresher course; the range in the config is what
    decides whether it counts, and nothing else gets a second opinion."""
    cfg = config()
    cfg["facts"]["hours"][0]["min"] = 100

    built = build(cfg)

    assert built["1"]["hours"] == "600"
    assert built["2"]["hours"] == ""


def test_the_kind_reaches_the_wording_of_the_copy():
    """build_name and build_description used to work the kind out for
    themselves. They are handed it now, so one rule governs the filter and the
    wording together."""
    built = build(config())

    assert built["2"]["name"].endswith("Курс повышения квалификации")
    assert "Удостоверение" in built["2"]["description"]
