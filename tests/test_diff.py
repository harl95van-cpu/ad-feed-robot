"""The diff between two runs is what the whole robot reports on, so it is the
part that has to be right: a missed price change means the feed silently drifts
away from the site."""

import main


def offer(oid, price, available="true", name=None, url=None):
    return {
        "id": oid,
        "name": name or "Programme %s" % oid,
        "url": url or "/catalog/%s/" % oid,
        "price": price,
        "available": available,
    }


def state_from(offers):
    return {"offers": {o["id"]: dict(o) for o in offers}}


def test_new_programme_is_reported_as_added():
    previous = state_from([offer("1", 10000)])
    diff = main.diff_against_state([offer("1", 10000), offer("2", 20000)], previous)

    assert [a["id"] for a in diff["added"]] == ["2"]
    assert diff["price_changes"] == []
    assert diff["removed"] == []
    assert diff["total"] == 2


def test_price_change_is_reported_with_both_values():
    previous = state_from([offer("1", 10000)])
    diff = main.diff_against_state([offer("1", 12000)], previous)

    assert len(diff["price_changes"]) == 1
    change = diff["price_changes"][0]
    assert change["old"] == 10000
    assert change["new"] == 12000
    assert change["id"] == "1"


def test_price_compared_as_number_not_string():
    """Prices arrive as strings from the crawler and as ints from the state."""
    previous = state_from([offer("1", 9900)])
    diff = main.diff_against_state([offer("1", "9900")], previous)

    assert diff["price_changes"] == []


def test_programme_gone_from_the_site_is_reported_as_removed():
    previous = state_from([offer("1", 10000), offer("2", 20000)])
    diff = main.diff_against_state([offer("1", 10000)], previous)

    assert [r["id"] for r in diff["removed"]] == ["2"]


def test_already_unavailable_programme_is_not_reported_twice():
    """A programme that vanished yesterday should not be announced again today."""
    previous = {"offers": {"2": dict(offer("2", 20000, available="false"))}}
    diff = main.diff_against_state([], previous)

    assert diff["removed"] == []


def test_unavailable_offers_do_not_count_as_added():
    diff = main.diff_against_state([offer("1", 10000, available="false")], {"offers": {}})

    assert diff["added"] == []
    assert diff["total"] == 1


def test_first_run_reports_everything_as_new():
    diff = main.diff_against_state([offer("1", 10000), offer("2", 20000)], {})

    assert len(diff["added"]) == 2


def test_has_changes_is_false_on_a_quiet_run():
    diff = main.diff_against_state([offer("1", 10000)], state_from([offer("1", 10000)]))

    assert main.has_changes(diff, problems=[]) is False


def test_has_changes_is_true_when_validation_found_problems():
    diff = main.diff_against_state([offer("1", 10000)], state_from([offer("1", 10000)]))

    assert main.has_changes(diff, problems=["дубль id 1"]) is True
