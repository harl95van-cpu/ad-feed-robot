"""Fact extraction. The model is only ever allowed to phrase things, never to
supply them, so everything it is told has to be pulled out of the page here —
correctly, and with a clear "not found" when the page does not say."""

import facts


CONFIG = {
    "facts": {
        "profession": [
            {"source": "h1", "pattern": "квалификации\\s*«([^»]+)»", "max_len": 30},
            {"source": "title", "pattern": "^([^:|]{3,60}):", "max_len": 60},
        ],
        "program": [{"source": "h1", "pattern": "«([^»]+)»", "max_len": 160}],
        "hours": [{"source": "hints", "pattern": "^(\\d+)\\s*час", "min": 16, "max": 5000}],
        "duration_months": [
            {"source": "meta",
             "pattern": "(?:длительност\\w*|обучени\\w*)[^.;]{0,28}?(\\d{1,2})\\s*месяц",
             "reject": "рассрочк|доступ", "min": 1, "max": 36, "template": "{value} мес."},
        ],
        "kind": [{"source": "hints", "pattern": "^(\\D[\\w\\s-]{3,40})$"}],
    }
}


def page(**over):
    base = {
        "title": "Логопед: курс переподготовки онлайн",
        "h1": "«Логопедия» с присвоением квалификации «Логопед» (600 ч.)",
        "meta": "Длительность обучения: 6 месяцев. Диплом.",
    }
    base.update(over)
    return base


def program(**over):
    base = {"name": "Логопедия", "hints": ["600 часов", "Переподготовка"], "url": "/x/"}
    base.update(over)
    return base


# --- rules and their order --------------------------------------------------

def test_first_matching_rule_wins():
    out = facts.extract(page(), program(), CONFIG)

    assert out["profession"] == "Логопед"
    assert out["sources"]["profession"] == "h1"


def test_rule_that_overruns_its_length_cap_falls_through_to_the_next_one():
    long_qualification = "«Логопедия» с присвоением квалификации «%s»" % ("Учитель " * 6)

    out = facts.extract(page(h1=long_qualification), program(), CONFIG)

    assert out["profession"] == "Логопед"          # from <title>, the second rule
    assert out["sources"]["profession"] == "title"


def test_a_list_source_is_searched_item_by_item():
    out = facts.extract(page(), program(hints=["Переподготовка", "600 часов"]), CONFIG)

    assert out["hours"] == "600"


def test_template_is_applied_to_the_captured_value():
    out = facts.extract(page(), program(), CONFIG)

    assert out["duration_months"] == "6 мес."


# --- guards against picking up the wrong number -----------------------------

def test_instalment_plan_does_not_become_the_course_duration():
    """Both are months and both sit in the same sentence — «700 часов за 6
    месяцев» next to «рассрочка на 12 месяцев» — so the rule has to be told
    which one it must not take."""
    meta = "Обучение с рассрочкой на 12 месяцев."

    out = facts.extract(page(meta=meta), program(), CONFIG)

    assert out["duration_months"] == ""


def test_a_number_outside_the_plausible_range_is_ignored():
    out = facts.extract(page(), program(hints=["7 часов", "Переподготовка"]), CONFIG)

    assert out["hours"] == ""


# --- a missing fact is a normal outcome -------------------------------------

def test_missing_fact_is_reported_as_empty_not_guessed():
    out = facts.extract(page(h1="Курс без квалификации", title="Без двоеточия"),
                        program(), CONFIG)

    assert out["profession"] == ""
    assert facts.missing(out) == ["profession"]


def test_kind_falls_back_to_the_default_when_the_page_does_not_say():
    out = facts.extract(page(), program(hints=["600 часов"]), CONFIG)

    assert out["kind"] == facts.DEFAULT_KIND
    assert out["sources"]["kind"] == "default"


# --- the model-assisted second pass -----------------------------------------

def test_value_present_on_the_page_in_another_case_counts_as_grounded():
    assert facts.grounded("логопеда", page(), program())


def test_value_absent_from_the_page_is_not_grounded():
    assert not facts.grounded("Финансовый аналитик", page(), program())


def test_model_answer_is_accepted_when_the_page_backs_it_up():
    blank = page(h1="Курс без квалификации", title="Без двоеточия")
    out = facts.extract(blank, program(), CONFIG)

    facts.resolve_missing(out, blank, program(), lambda fields, text: {"profession": "Логопедия"})

    assert out["profession"] == "Логопедия"
    assert out["sources"]["profession"] == "model"


def test_model_answer_that_is_really_the_programme_title_is_rejected():
    """It is literally on the page, so being grounded is not enough on its own:
    a profession is a short noun phrase, not a whole programme name."""
    blank = page(h1="Курс без квалификации", title="Без двоеточия")
    out = facts.extract(blank, program(), CONFIG)
    verbose = {"profession": "Логопедия " * 12}

    facts.resolve_missing(out, blank, program(), lambda fields, text: verbose)

    assert out["profession"] == ""


def test_model_answer_that_the_page_does_not_contain_is_rejected():
    blank = page(h1="Курс без квалификации", title="Без двоеточия")
    out = facts.extract(blank, program(), CONFIG)

    facts.resolve_missing(out, blank, program(),
                          lambda fields, text: {"profession": "Сварщик"})

    assert out["profession"] == ""


def test_a_broken_model_call_leaves_the_facts_alone_instead_of_raising():
    blank = page(h1="Курс без квалификации", title="Без двоеточия")
    out = facts.extract(blank, program(), CONFIG)

    def explode(fields, text):
        raise RuntimeError("нет связи")

    facts.resolve_missing(out, blank, program(), explode)

    assert out["profession"] == ""
