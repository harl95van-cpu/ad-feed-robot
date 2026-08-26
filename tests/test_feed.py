"""Feed assembly rules. Two things matter here: the ad platform rejects a feed
that breaks its limits, and the legal team rejects copy that carries claims the
client is not allowed to make."""

import feed


CONFIG = {
    "shop_name": "Demo Academy",
    "base_url": "https://demo-academy.example",
    "categories": [
        {"id": "1795", "name": "Design"},
        {"id": "565", "name": "Management"},
    ],
}


def offer(**over):
    base = {
        "id": "101",
        "name": "Дизайн интерьера",
        "url": "https://demo-academy.example/catalog/design/interior/",
        "picture": "https://storage.example/img/demo/101.jpg",
        "description": "Программа профессиональной переподготовки.",
        "price": 88400,
        "oldprice": 120000,
        "categoryId": "1795",
        "available": "true",
    }
    base.update(over)
    return base


# --- forbidden claims -------------------------------------------------------

def test_forbidden_phrase_is_removed():
    text = feed.strip_forbidden(
        "Диплом государственного образца по итогам обучения.",
        ["государственного образца"],
    )

    assert "государственного образца" not in text


def test_removal_does_not_leave_double_spaces_or_stray_punctuation():
    text = feed.strip_forbidden(
        "Диплом «государственного образца», выдаём всем.",
        ["государственного образца"],
    )

    assert "  " not in text
    assert " ," not in text
    assert "«»" not in text


def test_copy_without_forbidden_phrases_is_left_untouched():
    original = "Диплом  с  авторским   форматированием."

    assert feed.strip_forbidden(original, ["другая фраза"]) == original


# --- length trimming --------------------------------------------------------

def test_short_text_is_not_trimmed():
    assert feed._cut("Дизайн интерьера", 100) == "Дизайн интерьера"


def test_trimming_happens_on_a_word_boundary():
    trimmed = feed._cut("Дизайн интерьера и предметной среды", 20)

    assert len(trimmed) <= 20
    assert not trimmed.endswith(" ")
    assert trimmed in "Дизайн интерьера и предметной среды"


def test_trimming_does_not_leave_a_dangling_preposition():
    """Cutting mid-phrase must not end the line on «в», «и», «для» and friends."""
    trimmed = feed._cut("Управление персоналом в организации и", 36)

    assert trimmed == "Управление персоналом в организации"


# --- validation -------------------------------------------------------------

def test_valid_offer_passes():
    assert feed.validate([offer()], CONFIG) == []


def test_duplicate_ids_are_reported():
    problems = feed.validate([offer(), offer(url="https://demo-academy.example/x/")], CONFIG)

    assert any("дубль id" in p for p in problems)


def test_duplicate_urls_are_reported():
    problems = feed.validate([offer(), offer(id="102")], CONFIG)

    assert any("дубль url" in p for p in problems)


def test_category_outside_the_reference_list_is_reported():
    problems = feed.validate([offer(categoryId="9999")], CONFIG)

    assert any("вне справочника" in p for p in problems)


def test_empty_required_field_is_reported():
    problems = feed.validate([offer(picture="")], CONFIG)

    assert any("пустое поле picture" in p for p in problems)


def test_old_price_not_above_price_is_reported():
    """A crossed-out price that is not actually higher gets the feed rejected."""
    problems = feed.validate([offer(price=100000, oldprice=90000)], CONFIG)

    assert any("не выше" in p for p in problems)


def test_name_longer_than_the_platform_limit_is_reported():
    problems = feed.validate([offer(name="Д" * 101)], CONFIG)

    assert any("длиннее 100" in p for p in problems)


# --- rendering --------------------------------------------------------------

def test_rendered_feed_is_xml_with_the_shop_name():
    xml = feed.render([offer()], CONFIG)

    assert xml.startswith("<?xml")
    assert "<yml_catalog" in xml
    assert "Demo Academy" in xml


def test_offer_fields_reach_the_xml():
    xml = feed.render([offer()], CONFIG)

    assert "88400" in xml
    assert "120000" in xml
    assert "Дизайн интерьера" in xml


def test_unused_categories_are_dropped_from_the_feed():
    xml = feed.render([offer(categoryId="1795")], CONFIG)

    assert "Design" in xml
    assert "Management" not in xml


def test_special_characters_are_escaped():
    xml = feed.render([offer(name="Дизайн & интерьер")], CONFIG)

    assert "&amp;" in xml
    assert "Дизайн & интерьер" not in xml
