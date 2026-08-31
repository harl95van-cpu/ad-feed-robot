"""What the run says on a day with no news.

Reporting only when something changed is right about the catalogue and wrong
about the reader: five quiet days are indistinguishable from a robot that
stopped on the first of them, which is exactly how it was noticed."""

import feed
import main as robot
import notify


def test_a_quiet_day_still_produces_a_line():
    line = notify.format_heartbeat('demo', 329)

    assert 'demo' in line and '329' in line
    assert line.count('\n') == 0


def test_the_workarounds_a_quiet_day_hides_are_surfaced():
    """None of these move the catalogue, so none reach the change report — but a
    run working around the same thing every morning is a problem nobody sees."""
    generator = feed.Generator(None, retries=2)
    generator.stats['fallback'] = 3
    generator.stats['price_mismatch'] = 2

    line = notify.format_heartbeat('second', 239, robot.quiet_warnings(generator))

    assert 'старом алгоритме: 3' in line
    assert 'не найдена на странице: 2' in line


def test_a_clean_run_carries_no_warnings():
    assert robot.quiet_warnings(feed.Generator(None, retries=2)) == []


def test_generation_being_off_is_worth_saying_on_a_quiet_day():
    generator = feed.Generator(None, retries=2, reason='нет ретранслятора')

    assert any('нет ретранслятора' in w for w in robot.quiet_warnings(generator))
