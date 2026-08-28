# -*- coding: utf-8 -*-
"""Deterministic fact extraction from a crawled program page.

The model writes the wording, never the facts: profession, hours, duration and
program kind are pulled out here and handed to it as ready fields. Extraction
rules live in the client config next to the layout profile, because every site
hides the same fact in a different place — on demo-academy.example the duration is absent
altogether, on second-academy.example it sits in the meta description next to an instalment
plan measured in the same months.

A missing fact is a normal outcome, not a reason to guess: the ad template is
required to render without it.
"""
import re

# Every field we know how to extract. Order matters only for readable output.
FIELDS = ('profession', 'program', 'hours', 'duration_months', 'kind')

DEFAULT_KIND = 'Переподготовка'

# A profession is a short noun phrase. Being literally present on the page is
# not enough on its own: asked for a missing profession, the model happily
# returns the whole programme title, which is also literally present.
MODEL_MAX_LEN = {'profession': 70, 'program': 160, 'duration_months': 12, 'hours': 6}

# Enough context before a match to spot the wording that invalidates it —
# «рассрочка на 12 месяцев» must never become the course duration.
REJECT_WINDOW = 48


def _haystacks(page, program):
    """Text fields a rule may point at, by name."""
    return {
        'title': page.get('title', '') or '',
        'h1': page.get('h1', '') or '',
        'meta': page.get('meta', '') or '',
        # The whole page as plain text. Facts that live in a spec line rather
        # than in the head — the duration, on both of our sites — are only
        # reachable here.
        'body': page.get('body', '') or '',
        'name': program.get('name', '') or '',
        'url': program.get('url', '') or '',
        'hints': program.get('hints', []) or [],
    }


def _clean(value):
    return re.sub(r'\s+', ' ', value).strip(' .,:;«»"\'-—–')


def _match(rule, text):
    """First match of the rule in one string, or None.

    Iterates rather than searching once: a rule rejected by its context guard
    should fall through to the next occurrence, not to the next rule.
    """
    pattern = re.compile(rule['pattern'], re.I | re.S)
    reject = re.compile(rule['reject'], re.I) if rule.get('reject') else None
    for m in pattern.finditer(text):
        # The guard covers the match itself as well as the run-up to it: the
        # disqualifying word sits before the number in «Рассрочка на 12
        # месяцев» but inside the match in «обучение в рассрочку на 12 месяцев».
        if reject and reject.search(text[max(0, m.start() - REJECT_WINDOW):m.end()]):
            continue
        value = _clean(m.group(rule.get('group', 1)) or '')
        if not value:
            continue
        if rule.get('max_len') and len(value) > rule['max_len']:
            continue
        if 'min' in rule or 'max' in rule:
            digits = re.sub(r'\D', '', value)
            if not digits:
                continue
            number = int(digits)
            if number < rule.get('min', 0) or number > rule.get('max', 10 ** 9):
                continue
            value = str(number)
        return rule.get('template', '{value}').format(value=value)
    return None


def _apply(rules, texts):
    """Walk the rules in order, return the first hit and which rule found it.

    The rule matters, not just the field. «с присвоением квалификации «Бухгалтер»»
    and the marketing label before the colon in the page title both live in the
    page, but the first is the profession the graduate actually gets and the
    second is whatever the SEO team wrote. Downstream has to be able to tell
    them apart, so a rule may carry a `name` and that is what is recorded.
    """
    for rule in rules:
        source = rule.get('source', 'meta')
        chunks = texts.get(source, '')
        for chunk in (chunks if isinstance(chunks, list) else [chunks]):
            value = _match(rule, chunk)
            if value:
                return value, rule.get('name') or source
    return '', ''


def extract(page, program, cfg):
    """Pull every configured fact out of one program.

    Returns a dict with a key per field — empty string when the fact was not
    found — plus `sources`, a field-to-origin map kept for logs and reports.
    """
    texts = _haystacks(page, program)
    rules = cfg.get('facts', {})
    out, sources = {}, {}
    for field in FIELDS:
        value, source = _apply(rules.get(field, []), texts)
        out[field] = value
        sources[field] = source
    if not out['kind']:
        out['kind'] = DEFAULT_KIND
        sources['kind'] = 'default'
    out['sources'] = sources
    return out


def value_of(rules, page, program):
    """One configured value, pulled out by the same machinery as the facts.

    Used for the things that are not facts about the programme but about the
    page — the price it states — so that a client whose site keeps two
    disagreeing prices describes where the real one lives in the config
    instead of growing a second extractor in the feed builder.
    """
    value, _ = _apply(rules or [], _haystacks(page, program))
    return value


def missing(facts, required=('profession',)):
    """Fields worth asking the model about — everything else is optional."""
    return [f for f in required if not facts.get(f)]


def grounded(value, page, program, min_run=4):
    """True when the value is actually present in the page text.

    Guards the model-assisted extraction path: a profession the model returns
    has to appear in the source, allowing for a different case ending, so we
    compare word stems rather than whole words.
    """
    if not value:
        return False
    texts = _haystacks(page, program)
    blob = ' '.join(texts[k] for k in ('title', 'h1', 'meta', 'name')).lower()
    blob += ' ' + ' '.join(texts['hints']).lower()
    words = [w for w in re.findall(r'[\w-]+', value.lower()) if len(w) >= min_run]
    if not words:
        return False
    return all(w[:max(min_run, len(w) - 2)] in blob for w in words)


def resolve_missing(facts, page, program, ask, required=('profession',)):
    """Second pass: let the model read the page when the patterns found nothing.

    `ask(fields, page_text)` is supplied by the caller and must return a dict of
    field to value. Anything it returns that is not literally backed by the page
    is dropped, so the fallback cannot invent a profession that is not there.
    """
    gaps = missing(facts, required)
    if not gaps or ask is None:
        return facts
    texts = _haystacks(page, program)
    page_text = '\n'.join('%s: %s' % (k, texts[k]) for k in ('title', 'h1', 'meta', 'name'))
    try:
        answer = ask(gaps, page_text) or {}
    except Exception as exc:                       # extraction must never break a run
        print('      [facts] модель не ответила: %s' % str(exc)[:120])
        return facts
    for field in gaps:
        value = _clean(str(answer.get(field) or ''))
        if len(value) > MODEL_MAX_LEN.get(field, 70):
            continue
        if value and grounded(value, page, program):
            facts[field] = value
            facts['sources'][field] = 'model'
    return facts
