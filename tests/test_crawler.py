"""Parsing the catalogue listing is the one place where a silent failure is
expensive: a layout change on the site turns into an empty feed rather than an
error, which is why the run also has a minimum-offers guard."""

import crawler


DIR_ITEM_LISTING = """
<div class="dir_item" id="bx_1234567_101">
  <div class="ttl"><a href="/catalog/design/interior/">Дизайн интерьера</a></div>
  <span class="hint--intensive">520 часов</span>
  <span class="hint--intensive">Переподготовка</span>
  <div class="course_full_price">
    <div class="course_price">от 88 400 ₽</div>
    <div class="course_price_old">120 000 ₽</div>
  </div>
  <div class="course_price_desc">рассрочка</div>
</div>
<div class="dir_item" id="bx_1234567_102">
  <div class="ttl"><a href="/catalog/design/web/">Веб-<b>дизайн</b></a></div>
  <span class="hint--intensive">340 часов</span>
  <div class="course_full_price">
    <div class="course_price">45 000 ₽</div>
  </div>
  <div class="course_price_desc">рассрочка</div>
</div>
"""

BX_ELEM_LISTING = """
<div id="bx_7654321_201" class="bx_elem">
  <a href="/short/logopedia/" class="course_title">Логопедия и…</a>
  <span class="hint--intensive">144 часа</span>
  <div class="course_full_price">
    <div class="course_price">19 900 ₽</div>
    <div class="course_price_old">24 900 ₽</div>
  </div>
  <div class="course_price_desc">рассрочка</div>
</div>
"""


def test_listing_yields_one_item_per_programme():
    items = crawler._parse_listing(DIR_ITEM_LISTING, "/catalog/design/")

    assert [i["id"] for i in items] == ["101", "102"]
    assert items[0]["section"] == "/catalog/design/"


def test_name_is_cleaned_of_inline_markup():
    items = crawler._parse_listing(DIR_ITEM_LISTING, "/catalog/design/")

    assert items[1]["name"] == "Веб-дизайн"


def test_price_written_as_a_range_is_parsed_to_a_number():
    """Multi-tariff courses print «от 88 400 ₽» instead of a plain number."""
    items = crawler._parse_listing(DIR_ITEM_LISTING, "/catalog/design/")

    assert items[0]["price"] == 88400
    assert items[0]["oldprice"] == 120000


def test_missing_old_price_is_none_not_zero():
    items = crawler._parse_listing(DIR_ITEM_LISTING, "/catalog/design/")

    assert items[1]["price"] == 45000
    assert items[1]["oldprice"] is None


def test_hints_carry_hours_and_programme_kind():
    items = crawler._parse_listing(DIR_ITEM_LISTING, "/catalog/design/")

    assert items[0]["hints"] == ["520 часов", "Переподготовка"]


def test_second_layout_is_parsed_by_its_own_profile():
    items = crawler._parse_listing(BX_ELEM_LISTING, "/short/", profile="bx_elem")

    assert len(items) == 1
    assert items[0]["id"] == "201"
    assert items[0]["url"] == "/short/logopedia/"
    assert items[0]["price"] == 19900


def test_block_without_a_price_yields_no_price_rather_than_crashing():
    html = """
    <div class="dir_item" id="bx_1_303">
      <div class="ttl"><a href="/catalog/x/">Курс без цены</a></div>
    </div>
    """
    items = crawler._parse_listing(html, "/catalog/")

    assert items[0]["price"] is None
    assert items[0]["oldprice"] is None


def test_unrecognised_markup_yields_nothing():
    assert crawler._parse_listing("<div>not a catalogue</div>", "/catalog/") == []


def test_urls_are_normalised_to_a_site_relative_path():
    base = "https://demo-academy.example"

    assert crawler.norm_url(base + "/catalog/design/", base) == "/catalog/design/"
    assert crawler.norm_url(base + "/catalog/design", base) == "/catalog/design/"
    assert crawler.norm_url("/catalog/design/?utm_source=x", base) == "/catalog/design/"
