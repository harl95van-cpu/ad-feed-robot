# -*- coding: utf-8 -*-
"""A price written into the ad copy, and the day the page's price moves.

Stored copy is left strictly alone as a rule: it is a live ad, and rewriting it
resets the statistics Direct has accumulated on it. A quoted price is the one
exception, because it stops being copy and becomes a claim — «Обучение по
травматологии 20000₽» beside an offer that now costs 21000 sends the visitor to
a page charging something else, which is exactly what the client asked never to
happen. Only the figure moves, so the wording the ad has earned on stays.
"""

import feed
import texts


CONFIG = {
    "base_url": "https://example.ru",
    "offer_tail": "Обучение дистанционно.",
    "forbidden_phrases": [],
    "label_source": "name",
    "facts": {"profession": [], "program": [], "hours": [],
              "duration_months": [], "kind": []},
}

PROGRAM = {"id": "1", "name": "Травматология и ортопедия", "url": "/tr/",
           "price": 21000, "oldprice": None, "hints": []}


# --- the substitution itself -------------------------------------------------

def test_a_stale_figure_is_replaced():
    assert feed.refresh_price("Обучение по травматологии 20000₽. Диплом!",
                              21000) == "Обучение по травматологии 21000₽. Диплом!"


def test_copy_quoting_the_right_price_is_untouched():
    """Identity matters: anything that comes back different is a rewritten ad."""
    line = "Обучение по травматологии 21000₽. Диплом!"

    assert feed.refresh_price(line, 21000) is line or feed.refresh_price(line, 21000) == line


def test_copy_with_no_price_is_untouched():
    line = "Обучение на логопеда за 6 мес. Диплом Москвы!"

    assert feed.refresh_price(line, 21000) == line


def test_the_thousands_separator_the_copy_uses_is_kept():
    """Two catalogues write the same number two ways, and the ad should keep
    reading the way it was written."""
    assert feed.refresh_price("Курс за 20 000 ₽", 21000) == "Курс за 21 000 ₽"
    assert feed.refresh_price("Курс за 20000₽", 21000) == "Курс за 21000₽"


def test_the_word_form_of_the_currency_is_recognised():
    assert feed.refresh_price("Курс 20000 руб.", 21000) == "Курс 21000 руб."


def test_a_number_that_is_not_a_price_is_left_where_it_is():
    """Hours and months are numbers too, and none of them follow the price."""
    line = "Обучение по хирургии за 3 мес. 1296 часов. Диплом!"

    assert feed.refresh_price(line, 21000) == line


def test_no_price_yet_means_nothing_is_guessed():
    assert feed.refresh_price("Курс за 20000₽", 0) == "Курс за 20000₽"


# --- how the build uses it ---------------------------------------------------

def test_the_build_refreshes_a_stored_title():
    stored = {"name": "Обучение по травматологии 20000₽. Диплом!",
              "description": "С занесением в ФИС ФРДО. Диплом гос.образца."}
    generator = feed.Generator(None, retries=2)

    def legacy():
        return "Обучение: Травматология и ортопедия. Диплом!", "текст"

    name, _, _ = feed._copy_for(PROGRAM, {}, stored, CONFIG, generator, legacy)

    assert name == "Обучение по травматологии 21000₽. Диплом!"
    assert generator.stats["price_refreshed"] == 1


def test_a_stored_title_that_is_already_right_costs_no_rewrite():
    stored = {"name": "Обучение по травматологии 21000₽. Диплом!",
              "description": "С занесением в ФИС ФРДО."}
    generator = feed.Generator(None, retries=2)

    name, _, _ = feed._copy_for(PROGRAM, {}, stored, CONFIG, generator,
                                lambda: ("x", "y"))

    assert name == "Обучение по травматологии 21000₽. Диплом!"
    assert generator.stats["price_refreshed"] == 0


def test_a_longer_figure_that_would_overflow_gives_up_the_price():
    """A correct number past the display limit is a number nobody sees, so the
    deterministic title — which quotes no price at all — wins instead."""
    stored = {"name": "Обучение по травматологии и ортопедии для врачей 9000₽",
              "description": "С занесением в ФИС ФРДО."}
    generator = feed.Generator(None, retries=2)
    clean = "Обучение: Травматология и ортопедия. Диплом!"

    name, _, _ = feed._copy_for(dict(PROGRAM, price=1210000), {}, stored, CONFIG,
                                generator, lambda: (clean, "текст"))

    assert len(name) <= texts.TITLE_LIMIT
    assert name == clean
