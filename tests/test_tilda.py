"""The second kind of catalogue: one that is rendered in the browser.

Nothing here reaches the network. What is worth covering is the part that can
fail quietly — a store whose init parameters moved, a programme joined to
another programme's landing page, and a catalogue that has no crossed-out price
at all, which used to empty the feed one offer at a time.
"""

import json

import pytest

import crawler
import feed


SECTION = '/profperepodgotovka/vysshee-obrazovanie/'
SECTION_HTML = """
<div class="t-store js-store"></div>
<script>var options={recid:'564636554',storepart:'573304721591',previewmode:'yes'};</script>
"""

PRODUCTS = {
    "total": 2,
    "products": [
        {
            "uid": 390452343381,
            "title": "Ортодонтия",
            "price": "20000.0000",
            "priceold": "",
            "gallery": json.dumps([{"img": "https://static.tildacdn.com/stor/41898949.png"}]),
            "url": "https://third-academy.example%stproduct/564636554-390452343381-ortodontiya" % SECTION,
            "characteristics": [
                {"title": "Продолжительность", "value": "576 (3 месяца)"},
                {"title": "Специальность", "value": "Ортодонтия"},
            ],
        },
        {
            "uid": 656603285351,
            "title": "Психиатрия",
            "price": "21000.0000",
            "priceold": "",
            "gallery": "",
            "url": "https://third-academy.example%stproduct/564636554-656603285351-psihiatriya" % SECTION,
            "characteristics": [],
        },
    ],
}

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
 <url><loc>https://third-academy.example/</loc></url>
 <url><loc>https://third-academy.example%(s)sortodontiya</loc></url>
 <url><loc>https://third-academy.example%(s)spsikhiatriya</loc></url>
 <url><loc>https://third-academy.example%(s)sneiroanesteziologiya</loc></url>
</urlset>""" % {'s': SECTION}


class FakeResponse(object):
    def __init__(self, text):
        self.text = text

    def json(self):
        return json.loads(self.text)


def fake_get(pages):
    """Stand-in for crawler._get: a url either has an answer or blows up."""
    def _get(session, url, attempts=4):
        for fragment, body in pages.items():
            if fragment in url:
                return FakeResponse(body)
        raise AssertionError('unexpected url %s' % url)
    return _get


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(crawler, '_get', fake_get({
        SECTION + '?': SECTION_HTML,
        'getproductslist': json.dumps(PRODUCTS),
        SECTION: SECTION_HTML,
        'sitemap.xml': SITEMAP,
    }))


def test_store_products_carry_id_price_and_picture(store):
    items = crawler.crawl_tilda_store(crawler._session(), 'https://third-academy.example', SECTION)
    assert [i['id'] for i in items] == ['390452343381', '656603285351']
    first = items[0]
    assert first['name'] == 'Ортодонтия'
    assert first['price'] == 20000
    # No standing discount on this catalogue: an absent crossed-out price has
    # to arrive as None rather than as 0, which would read as free.
    assert first['oldprice'] is None
    assert first['picture'] == 'https://static.tildacdn.com/stor/41898949.png'
    assert 'Продолжительность: 576 (3 месяца)' in first['hints']
    assert items[1]['picture'] == ''


def test_a_store_whose_parameters_moved_is_an_error_not_an_empty_section(monkeypatch):
    monkeypatch.setattr(crawler, '_get', fake_get({SECTION: '<div class="t-store"></div>'}))
    with pytest.raises(RuntimeError):
        crawler.crawl_tilda_store(crawler._session(), 'https://third-academy.example', SECTION)


def test_landing_pages_are_joined_across_transliterations(store):
    items = crawler.crawl_tilda_store(crawler._session(), 'https://third-academy.example', SECTION)
    crawler.resolve_landings(items, 'https://third-academy.example', crawler._session())
    assert items[0]['url'] == SECTION + 'ortodontiya'
    # «psihiatriya» in the store, «psikhiatriya» on the page: the same word
    # spelled by two different tools.
    assert items[1]['url'] == SECTION + 'psikhiatriya'
    assert not any(i.get('landing_missing') for i in items)


def test_a_programme_with_no_page_of_its_own_keeps_the_store_url(store):
    items = crawler.crawl_tilda_store(crawler._session(), 'https://third-academy.example', SECTION)
    items[1]['name'] = 'Эндоскопия'
    items[1]['url'] = SECTION + 'tproduct/564636554-656603285351-endoskopiya'
    crawler.resolve_landings(items, 'https://third-academy.example', crawler._session())
    # Pointing it at the one page still free would send the ads for one
    # programme to another programme's page.
    assert items[1]['url'].startswith(SECTION + 'tproduct/')
    assert items[1]['landing_missing'] is True


def test_skeleton_ignores_the_transliteration_and_not_the_word():
    assert crawler._skeleton('psihiatriya') == crawler._skeleton('psikhiatriya')
    assert crawler._skeleton('detskaya-hirurgiya') == crawler._skeleton('detskaya-khirurgiya')
    assert crawler._skeleton('nefrologiya') != crawler._skeleton('neврologiya')
    assert crawler._skeleton('ortodontiya') != crawler._skeleton('ortopediya')


# --- a catalogue without a crossed-out price ------------------------------

CONFIG = {
    "shop_name": "МЦМФО",
    "base_url": "https://third-academy.example",
    "bucket": "third-feeds",
    "image_prefix": "img/third/",
    "label_source": "name",
    "require_oldprice": False,
    "categories": [{"id": "1", "name": "Профпереподготовка"}],
    "documents": {"Переподготовка": {"prefix": "Переподготовка", "document": "Диплом"}},
    "name_templates": {"Повышение квалификации": "%s. Удостоверение!"},
    "sections": {SECTION: "1"},
    "facts": {"kind": [{"source": "url", "pattern": "(/profperepodgotovka/)",
                        "template": "Переподготовка"}]},
    "price_rules": [{"source": "body", "pattern": "Стоимость курса[:\\s]*([\\d\\s]{3,12})руб",
                     "min": 1000, "max": 500000}],
    "picture_priority": ["own", "site"],
}


def catalogue():
    return {SECTION + 'ortodontiya/': dict(
        id='390452343381', name='Ортодонтия', url=SECTION + 'ortodontiya',
        price=20000, oldprice=None, sections=[SECTION],
        picture='https://static.tildacdn.com/stor/41898949.png',
        hints=['Продолжительность: 576 (3 месяца)'])}


def pages(body='Стоимость курса: 21 000 руб. Продолжительность обучения: 576 ак.ч.'):
    return {SECTION + 'ortodontiya/': dict(
        h1='«Ортодонтия: профессиональная переподготовка»',
        title='Ортодонтия переподготовка врачей', meta='Курсы переподготовки', body=body)}


def build(cfg=None, page_body=None):
    cfg = dict(CONFIG, **(cfg or {}))
    body = pages() if page_body is None else pages(page_body)
    return feed.build_offers(catalogue(), body, cfg, {}, {'offers': {}})


def test_an_offer_without_a_crossed_out_price_still_enters_the_feed():
    offers = build()
    assert len(offers) == 1
    assert feed.validate(offers, dict(CONFIG)) == []


def test_the_same_offer_is_dropped_where_the_client_does_expect_one():
    assert build({'require_oldprice': True}) == []


def test_an_empty_oldprice_is_left_out_of_the_xml():
    xml = feed.render(build(), CONFIG)
    assert '<price>21000</price>' in xml
    assert '<oldprice>' not in xml


def test_the_price_the_landing_page_states_wins_over_the_store_card():
    # The two disagree on this site by a thousand roubles on almost every
    # programme, and the ad has to show what the visitor will read.
    assert build()[0]['price'] == 21000
    # No figure on the page is not a reason to drop the offer.
    assert build(page_body='Продолжительность обучения: 576 ак.ч.')[0]['price'] == 20000


def test_the_picture_comes_from_the_catalogue_itself():
    offer = build()[0]
    assert offer['picture'] == 'https://static.tildacdn.com/stor/41898949.png'
    assert offer['picture_source'] == 'site'


def test_the_title_wording_comes_from_the_config():
    cfg = dict(CONFIG, facts={"kind": [{"source": "url", "pattern": "(/profperepodgotovka/)",
                                        "template": "Повышение квалификации"}]})
    assert build(cfg)[0]['name'] == 'Ортодонтия. Удостоверение!'
