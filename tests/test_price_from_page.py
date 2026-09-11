# -*- coding: utf-8 -*-
"""Reading the price off the landing page, which is the one that has to match.

The ad sends the visitor to the landing page, so the figure in the feed must be
the figure on that page — the catalogue card is only a fallback for pages that
state no price at all. A card and a page disagree whenever the client updates
one and forgets the other, and that happened on seven programmes at once.

Pages write a price in more shapes than one, and three of those shapes carry a
number that must not be taken: the crossed-out price, the monthly instalment,
and the second tariff of a page that sells three. Rules are tried in order and
the first hit wins, so the specific shapes have to come before the general one.
"""

import facts as facts_rules


# The shapes, ordered as a client config must order them.
RULES = [
    {"name": "two_prices", "source": "body",
     "pattern": "Стоимость курса[:\\s]*[\\d\\s\\u00a0]{3,12}/\\s*([\\d\\s\\u00a0]{3,12})\\s*руб",
     "min": 1000, "max": 500000},
    {"name": "was_now", "source": "body",
     "pattern": "Стоимость[а-я ]{0,14}[:\\s]*(?:от\\s*)?([\\d\\s\\u00a0]{3,12})"
                "\\s*(?:руб|₽)\\s*(?:от\\s*)?([\\d\\s\\u00a0]{3,12})\\s*(?:руб|₽)"
                "(?!\\s*(?:в\\s*мес|/\\s*мес))",
     "group": 2, "min": 1000, "max": 500000},
    {"name": "stated", "source": "body",
     "pattern": "Стоимость[а-я ]{0,14}[:\\s]*([\\d\\s\\u00a0]{3,12})"
                "\\s*(?:руб|₽|р\\b)(?!\\s*(?:в\\s*мес|/\\s*мес))",
     "min": 1000, "max": 500000},
]

PROGRAM = {"id": "1", "name": "Курс", "hints": [], "price": 99999}


def read(page_text):
    return facts_rules.value_of(RULES, {"body": page_text}, PROGRAM)


def test_a_single_price_is_read_as_it_is():
    assert read("Стоимость курса: 21000 руб. Продолжительность: 1296 ак.часов") == "21000"


def test_the_rouble_can_be_spelled_with_one_letter():
    """«Стоимость: 15 000 р» — six programmes sat behind this one letter."""
    assert read("Стоимость: 15 000 р. вместо 35 000 р.") == "15000"


def test_two_prices_over_a_slash_mean_the_second_one():
    assert read("Стоимость курса: 35 000 / 21 000 руб") == "21000"
    assert read("Стоимость курса: 35 000/21 000 руб") == "21000"


def test_a_crossed_out_price_is_not_the_price():
    """«Стоимость 56 000 руб 44 000 руб» — the first figure is struck through on
    the page, and taking it would advertise a course as more expensive than it
    is."""
    assert read("Стоимость 56 000 руб 44 000 руб ⭐️ Выгода 12 000 руб") == "44000"
    assert read("Стоимость обучения: от 35000₽ от 20000 ₽ Полная от 1667₽") == "20000"


def test_a_monthly_instalment_is_never_the_price():
    """«Стоимость 32 000 ₽ 2 666 ₽ в месяц» has the same shape as a crossed-out
    price and means something else entirely: 2 666 in a feed would promise a
    course for a twelfth of its cost."""
    assert read("Стоимость 32 000 ₽ 2 666 ₽ в месяц Рассрочка на 12 месяцев") == "32000"
    assert read("Стоимость 42 000 ₽ 3 500 ₽/мес") == "42000"


def test_the_price_before_instead_of_is_the_live_one():
    """«35000 р. вместо 76000 р.» is the discount written the other way round —
    the new price comes first, so the general rule taking the first figure is
    right and the crossed-out rule must not fire here."""
    assert read("Стоимость: 35000 р. вместо 76000 р. Стоимость: 48500 р.") == "35000"


def test_a_page_with_no_figure_leaves_the_card_price_alone():
    """Silence, not a guess: the card is then the only source there is."""
    assert read("Стоимость обучения Программа курса — 2 месяца") == ""
    assert read("Стоимость обучения 0 ₽ вместо 25 000 ₽") == ""


def test_a_heading_that_swallows_the_number_is_not_matched():
    """«Стоимость Зарегистрироваться 42 000 ₽ …» — the words between the heading
    and the figure mean it belongs to a button, not to this programme."""
    assert read("Стоимость Зарегистрироваться 42 000 ₽ 3 500 ₽ в месяц") == ""
