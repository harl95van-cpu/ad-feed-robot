"""Facts that live in the page body rather than in its head.

The duration is the one an edtech buyer actually compares courses on, and on
both of our sites it sits in a spec line halfway down the page — not in the
title, not in the meta description. The body also carries three other numbers
measured in months, and a second programme's duration in the recommendations
block, so reaching it is only useful if the wrong ones stay out."""

import crawler
import facts


PAGE = (
    '<html><head><title>Логопед: переподготовка</title>'
    '<meta name="description" content="Курс переподготовки на логопеда.">'
    '</head><body><h1>Курс «Логопедия» (600 ч.)</h1>'
    '<script>var price = 12;</script>'
    '<div>Старт август 2026 Длительность 5 месяцев (600 часов)</div>'
    '<div>48 300 ₽ 4 025 ₽/мес в рассрочку на 12 месяцев</div>'
    '<div>Доступ к курсу предоставляется на 6 месяцев с момента оплаты</div>'
    '<div>Ещё интересно: Профессиональная переподготовка 4 месяца (502 часа)</div>'
    '</body></html>'
)

CONFIG = {
    "facts": {
        "profession": [],
        "program": [],
        "hours": [{"source": "hints", "pattern": "^(\\d+)", "min": 16, "max": 5000}],
        "duration_months": [
            {"source": "body",
             "pattern": "длительность[^.;]{0,24}?(\\d{1,2})\\s*месяц",
             "reject": "рассрочк|платеж|взнос|доступ|оплат|комисси",
             "min": 1, "max": 36, "template": "{value} мес."},
        ],
        "kind": [{"source": "hints", "pattern": "^(\\D.{1,60})$"}],
    }
}

PROGRAM = {"name": "Логопедия", "hints": ["600 часов", "Переподготовка"], "url": "/x/"}


def extracted(html=PAGE):
    return facts.extract(crawler.parse_details(html), PROGRAM, CONFIG)


# --- parsing ----------------------------------------------------------------

def test_the_body_comes_back_as_plain_text_without_scripts():
    parsed = crawler.parse_details(PAGE)

    assert 'var price' not in parsed['body']
    assert 'Длительность 5 месяцев (600 часов)' in parsed['body']
    assert parsed['title'] == 'Логопед: переподготовка'


def test_the_body_is_capped_so_one_page_cannot_eat_the_run():
    huge = '<html><body>%s</body></html>' % ('слово ' * 40000)

    assert len(crawler.parse_details(huge)['body']) <= crawler.BODY_LIMIT


# --- the duration and the three numbers that are not it ---------------------

def test_the_duration_is_read_from_the_spec_line():
    assert extracted()['duration_months'] == '5 мес.'
    assert extracted()['sources']['duration_months'] == 'body'


def test_the_instalment_plan_is_not_the_duration():
    """«в рассрочку на 12 месяцев» sits on every page of both sites. Picking it
    up would put a plausible, wrong number into hundreds of ads at once."""
    body = '<html><body>Длительность обучения в рассрочку на 12 месяцев</body></html>'

    assert facts.extract(crawler.parse_details(body), PROGRAM, CONFIG)['duration_months'] == ''


def test_another_programmes_duration_in_the_recommendations_is_not_taken():
    """The block at the foot of the page advertises other courses with their own
    «4 месяца (502 часа)». Only the anchored spec line counts."""
    assert extracted()['duration_months'] != '4 мес.'


def test_no_spec_line_means_no_duration_rather_than_a_guess():
    body = '<html><body>Хороший курс. Рассрочка на 12 месяцев.</body></html>'

    assert facts.extract(crawler.parse_details(body), PROGRAM, CONFIG)['duration_months'] == ''
