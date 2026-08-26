# -*- coding: utf-8 -*-
"""Assembles a YML feed for Yandex Direct out of crawled catalog data."""
import re
import datetime
from xml.sax.saxutils import escape
from collections import Counter

import clusters

EMOJI = re.compile('[\U0001F000-\U0001FAFF←-⯿️‍]+')
STOP_TAIL = {'и', 'в', 'с', 'по', 'на', 'для', 'от', 'к', 'о', 'об', 'при', 'у', 'за', 'из'}


def _cut(s, n):
    """Trim to n chars on a word boundary, dropping a dangling preposition."""
    if len(s) <= n:
        return s
    words = s[:n].rsplit(' ', 1)[0].rstrip(' ,.-').split(' ')
    while len(words) > 1 and words[-1].lower().strip(',.') in STOP_TAIL:
        words.pop()
    return ' '.join(words).rstrip(' ,.-')


def strip_forbidden(text, phrases):
    """Remove banned marketing claims (e.g. the Saint Petersburg wording).

    Cleans up whatever the removal leaves behind — empty quotes, a space before
    punctuation, a run of punctuation marks — but keeps the sentence's own
    closing period.
    """
    original = text
    for p in phrases:
        text = text.replace(p, '')
    if text == original:
        return text          # nothing removed — leave the copy exactly as written
    text = re.sub(r'\s*[«"„]\s*[»"“]', '', text)
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)
    text = re.sub(r'([,.!?;:])[\s]*[,.!?;:]+', r'\1', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip(' ,;:-')


def hours_of(program, page):
    for h in program['hints']:
        m = re.match(r'(\d+)', h)
        if m:
            return m.group(1)
    m = re.search(r'\((\d+)\s*ч', page.get('h1', ''))
    return m.group(1) if m else ''


def kind_of(program):
    for h in program['hints']:
        if not h[:1].isdigit():
            return h
    return 'Переподготовка'


def label_of(page, source='title'):
    """Short marketing label for the course.

    `title`     — the part of <title> before the colon.
    `h1_quoted` — the «…» phrase inside <h1> (for sites whose <title> is a
                  keyword-stuffed SEO string).
    """
    quoted = re.search(r'«([^»]+)»', page.get('h1', ''))
    if source == 'h1_quoted' and quoted:
        label = quoted.group(1)
    else:
        title = page.get('title', '').split('|')[0].strip()
        label = title.split(':')[0].strip() if ':' in title else title
        label = re.sub(r'\s*[—-]\s*(переподготовка|повышение).*$', '', label, flags=re.I).strip()
        if (not label or len(label) > 70) and quoted:
            label = quoted.group(1)
    return re.sub(r'\s+', ' ', label).strip(' .«»')


def build_name(page, program, phrases, label_source='title'):
    label = strip_forbidden(label_of(page, label_source), phrases)
    kind = kind_of(program)
    if kind.startswith('Повышение'):
        name = '%s. Курс повышения квалификации' % _cut(label, 44)
    elif kind.startswith('Профессиональное обучение'):
        name = 'Обучение: %s. Документ о квалификации' % _cut(label, 38)
    else:
        name = 'Обучение: %s. Диплом!' % _cut(label, 44)
    return re.sub(r'\s+', ' ', name).strip()


MAX_DESCRIPTION = 85

# Direct cuts the description mid-word in the banner, so it has to be short and
# front-loaded: what the course is, then the standing offer. The document name
# follows the programme type — retraining gives a diploma, refresher courses an
# udostoverenie, vocational training a svidetelstvo.
KIND_WORDING = {
    'Переподготовка': ('Переподготовка', 'Диплом'),
    'Профессиональная переподготовка': ('Переподготовка', 'Диплом'),
    'Повышение квалификации': ('Повышение квалификации', 'Удостоверение'),
    'Профессиональное обучение': ('Профобучение', 'Свидетельство'),
}

# Standing offer at the end of every description — differs per client.
DEFAULT_OFFER = 'Рассрочка до 36 мес.'


# Ad-title decorations we strip to get back to the bare course name.
NAME_LEAD = re.compile(
    r'^(дистанционное обучение|онлайн[- ]обучение|обучение онлайн|'
    r'дистанционный курс|онлайн[- ]курс|курсы|курс|обучение)\s*:\s*', re.I)
NAME_TAIL = re.compile(
    r'\s*[.,]?\s*((обучение|курс)\s*\d+\s*мес\w*\.?|'
    r'курс(ы)?( обучения)?( повышения квалификации)?( онлайн)?|'
    r'повышение квалификации|документ о квалификации|переподготовка|'
    r'профобучени\w*|проф\.?\s*обучени\w*|установленного образца|'
    r'диплом(\s+москвы|\s+санкт-петербурга)?|сертификат|удостоверение|'
    r'свидетельство|онлайн|дистанционно)[!.]*\s*$',
    re.I)
HOURS_TAIL = re.compile(r'\s*[.,]?\s*\(?\d+\s*(ч|час\w*|месяц\w*|мес\.?)\)?\s*$', re.I)
# Room for the ", 640 ч" the dedupe pass may insert.
HOURS_RESERVE = 8


def course_label(name):
    """Bare course name taken from the ad title: «Обучение: Логопед. Диплом!»
    becomes «Логопед»."""
    label = HOURS_TAIL.sub('', name or '')
    for _ in range(2):                      # «Онлайн обучение: Курс: X»
        stripped = NAME_LEAD.sub('', label)
        if stripped == label:
            break
        label = stripped
    for _ in range(4):                      # titles stack up to four tails
        stripped = NAME_TAIL.sub('', label)
        if stripped == label:
            break
        label = stripped
    label = label.replace('«', '').replace('»', '')
    return re.sub(r'\s{2,}', ' ', label).strip(' .,:!')


def build_description(page, program, phrases, offer=DEFAULT_OFFER, label_source='title'):
    prefix, document = KIND_WORDING.get(kind_of(program), KIND_WORDING['Переподготовка'])
    label = course_label(program.get('offer_name') or '') or label_of(page, label_source)
    label = strip_forbidden(EMOJI.sub('', label), phrases).strip(' .')
    tail = '%s %s!' % (offer.rstrip(), document)
    budget = MAX_DESCRIPTION - HOURS_RESERVE

    with_prefix = '%s: %s. %s' % (prefix, label, tail)
    if len(with_prefix) <= budget:
        return with_prefix
    return '%s. %s' % (_cut(label, budget - len(tail) - 2), tail)


def category_of(program, cfg):
    for section in program['sections']:
        cid = cfg['sections'].get(section)
        if cid:
            return cid
    return ''


def picture_of(offer_id, cid, cfg, images, state, cluster_key=None):
    """Resolve the offer picture by the client's configured priority.

    `own`     — a creative generated for this exact program
    `cluster` — the shared creative of its micro-category
    `stored`  — the picture the client's own feed used last time

    a client puts `cluster` above `stored` because the client's originals were
    WebP and risky at moderation; a client keeps its own JPG/PNG photos, so there
    `stored` wins and generated art only fills the gaps.
    """
    base = 'https://storage.yandexcloud.net/%s/%s' % (cfg['bucket'], cfg['image_prefix'])
    known = state.get('offers', {}).get(offer_id, {}).get('picture')
    cluster = ('cluster_%s' % cluster_key) if cluster_key else None

    for source in cfg.get('picture_priority', ['own', 'cluster', 'stored']):
        if source == 'own' and offer_id in images:
            return base + images[offer_id], 'own'
        if source == 'cluster' and cluster and cluster in images:
            return base + images[cluster], 'cluster'
        if source == 'stored' and known:
            return known, 'stored'

    pool = [o.get('picture') for o in state.get('offers', {}).values()
            if o.get('picture') and o.get('categoryId') == cid]
    if not pool:
        fb = cfg.get('picture_fallback_category', {}).get(cid)
        pool = [o.get('picture') for o in state.get('offers', {}).values()
                if o.get('picture') and o.get('categoryId') == fb]
    if not pool:
        pool = [o.get('picture') for o in state.get('offers', {}).values() if o.get('picture')]
    # A stand-in belongs to another programme — usable in the feed, but it must
    # never be written back to state as if it were this offer's own picture.
    return (pool[0] if pool else ''), 'fallback'


def build_offers(programs, pages, cfg, images, state):
    """Turn crawled programs into offer dicts, carrying over stored fields."""
    phrases = cfg.get('forbidden_phrases', [])
    offer_line = cfg.get('offer_tail', DEFAULT_OFFER)
    label_source = cfg.get('label_source', 'title')
    # Some clients advertise only part of their catalogue (a client — retraining
    # only), so refresher courses and mini-courses never enter the feed.
    include = cfg.get('include_kinds')
    stored = state.get('offers', {})
    offers = []
    skipped = []
    for key, program in programs.items():
        if include and kind_of(program) not in include:
            continue
        # A price is mandatory in YML; a card without one cannot be advertised.
        if not program.get('price') or not program.get('oldprice'):
            skipped.append((program['id'], program.get('name', ''), key))
            continue
        page = pages.get(key, {})
        oid = program['id']
        prev = stored.get(oid, {})
        # Keep the category the client's own feed assigned; the section mapping
        # is only a fallback for programs we are seeing for the first time.
        cid = prev.get('categoryId') or category_of(program, cfg)
        cluster_key = clusters.assign('%s %s' % (label_of(page, label_source), program['name']))
        # The ad title is the cleanest source for the course name, so build it
        # first and let the description reuse it.
        name = strip_forbidden(
            prev.get('name') or build_name(page, program, phrases, label_source), phrases)
        program = dict(program, offer_name=name)
        picture = picture_of(oid, cid, cfg, images, state, cluster_key)
        offers.append(dict(
            key=key,
            id=oid,
            available='true',
            name=name,
            categoryId=cid,
            url=cfg['base_url'] + key,
            picture=picture[0],
            picture_source=picture[1],
            description=build_description(page, program, phrases, offer_line, label_source),
            price=program['price'],
            oldprice=program['oldprice'],
            custom_label_0=prev.get('custom_label_0', 'False'),
            custom_label_1=prev.get('custom_label_1', 'False'),
            custom_score=prev.get('custom_score'),
            sales_notes=prev.get('sales_notes'),
            hours=hours_of(program, page),
            kind=kind_of(program),
            cluster=cluster_key,
            has_own_image=oid in images,
            has_cluster_image=('cluster_%s' % cluster_key) in images,
        ))

    # Programs that vanished from the catalog stay in the feed as unavailable
    # for one cycle, so Direct stops serving them instead of erroring out.
    live = {o['id'] for o in offers}
    for oid, prev in stored.items():
        if oid in live or prev.get('gone_cycles', 0) >= 1:
            continue
        prev = dict(prev)
        prev.update(id=oid, available='false', gone_cycles=prev.get('gone_cycles', 0) + 1,
                    has_own_image=False, hours='', kind='')
        offers.append(prev)

    _dedupe_names(offers)
    _dedupe_descriptions(offers)
    if skipped:
        print('      без цены, в фид не попали: %d' % len(skipped))
        for oid, nm, key in skipped[:10]:
            print('        %s %s' % (oid, (nm or key)[:60]))
    return offers


def _dedupe_names(offers):
    counts = Counter(o['name'] for o in offers)
    for o in offers:
        if counts[o['name']] > 1:
            suffix = ' (%s ч)' % o['hours'] if o.get('hours') else ' (id %s)' % o['id']
            o['name'] = _cut(o['name'], 96 - len(suffix)) + suffix
    still = {n for n, c in Counter(o['name'] for o in offers).items() if c > 1}
    for o in offers:
        if o['name'] in still:
            o['name'] = _cut(o['name'], 84 - len(o['id'])) + ' (id %s)' % o['id']


def _dedupe_descriptions(offers):
    """Two programmes can share a label; the hours tell them apart without
    pushing the line past the truncation point."""
    counts = Counter(o['description'] for o in offers)
    for o in offers:
        if counts[o['description']] > 1 and o.get('hours'):
            o['description'] = o['description'].replace(
                '. Рассрочка', ', %s ч. Рассрочка' % o['hours'], 1)


def validate(offers, cfg):
    """Hard checks — anything here would get the feed rejected by Direct."""
    cats = {c['id'] for c in cfg['categories']}
    problems = []
    seen_ids, seen_urls = set(), set()
    for o in offers:
        if o['id'] in seen_ids:
            problems.append('дубль id %s' % o['id'])
        seen_ids.add(o['id'])
        if o['url'] in seen_urls:
            problems.append('дубль url %s' % o['url'])
        seen_urls.add(o['url'])
        if o['categoryId'] not in cats:
            problems.append('оффер %s: категория %r вне справочника' % (o['id'], o['categoryId']))
        for field in ('name', 'url', 'picture', 'description', 'price', 'oldprice'):
            if not o.get(field):
                problems.append('оффер %s: пустое поле %s' % (o['id'], field))
        if o.get('price') and o.get('oldprice') and o['oldprice'] <= o['price']:
            problems.append('оффер %s: oldprice %s не выше price %s'
                            % (o['id'], o['oldprice'], o['price']))
        if len(o['name']) > 100:
            problems.append('оффер %s: имя длиннее 100 символов' % o['id'])
        if o.get('sales_notes') and len(o['sales_notes']) > 50:
            problems.append('оффер %s: sales_notes длиннее 50 символов' % o['id'])
    return problems


def render(offers, cfg):
    def el(tag, value):
        return '<%s>%s</%s>' % (tag, escape(str(value)), tag)

    used = {o['categoryId'] for o in offers}
    by_id = {c['id']: c for c in cfg['categories']}
    keep = set(used)
    for cid in list(keep):
        parent = (by_id.get(cid) or {}).get('parentId')
        while parent:
            keep.add(parent)
            parent = (by_id.get(parent) or {}).get('parentId')

    out = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append('<yml_catalog date="%s">'
               % datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+03:00'))
    out.append('<shop>')
    out.append(el('name', cfg['shop_name']))
    out.append(el('company', cfg['shop_name']))
    out.append(el('url', cfg['base_url'] + '/'))
    out.append('<currencies>')
    out.append('<currency id="RUR" rate="1"/>')
    out.append('</currencies>')
    out.append('<categories>')
    for c in cfg['categories']:
        if c['id'] not in keep:
            continue
        parent = ' parentId="%s"' % c['parentId'] if c.get('parentId') else ''
        out.append('<category id="%s"%s>%s</category>' % (c['id'], parent, escape(c['name'])))
    out.append('</categories>')
    out.append('<offers>')
    for o in offers:
        out.append('<offer id="%s" available="%s">' % (o['id'], o['available']))
        out.append(el('name', o['name']))
        out.append(el('vendor', cfg['shop_name']))
        out.append(el('categoryId', o['categoryId']))
        out.append(el('url', o['url']))
        out.append(el('picture', o['picture']))
        out.append(el('description', o['description']))
        if o.get('sales_notes'):
            out.append(el('sales_notes', o['sales_notes']))
        out.append(el('price', o['price']))
        out.append(el('oldprice', o['oldprice']))
        out.append(el('currencyId', 'RUR'))
        out.append(el('custom_label_0', o.get('custom_label_0', 'False')))
        out.append(el('custom_label_1', o.get('custom_label_1', 'False')))
        if o.get('custom_score'):
            out.append(el('custom_score', o['custom_score']))
        out.append('</offer>')
    out.append('</offers>')
    out.append('</shop>')
    out.append('</yml_catalog>')
    return '\n'.join(out) + '\n'
