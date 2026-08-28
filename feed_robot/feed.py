# -*- coding: utf-8 -*-
"""Assembles a YML feed for Yandex Direct out of crawled catalog data."""
import re
import datetime
from xml.sax.saxutils import escape
from collections import Counter

import clusters
import facts as facts_rules
import texts

# Re-exported so the builder signatures below can default to it without
# reaching into another module in every call.
DEFAULT_KIND = facts_rules.DEFAULT_KIND

EMOJI = re.compile('[\U0001F000-\U0001FAFF←-⯿️‍]+')
STOP_TAIL = {'и', 'в', 'с', 'по', 'на', 'для', 'от', 'к', 'о', 'об', 'при', 'у', 'за', 'из'}
# Everything a cut may leave at the end of a phrase. The em dash and the en dash
# are the ones that were missing: the sites write «—», the code stripped «-».
DEBRIS = ' ,.-—–:;'


def _trim_tail(s):
    """Drop whatever is left dangling at the end of a shortened phrase.

    Used both after cutting to a length and after stripping a search-engine
    tail: «Психолог-консультант переподготовка с дипломом» loses its tail and is
    left ending on a preposition.
    """
    words = s.rstrip(DEBRIS).split(' ')
    while len(words) > 1 and (words[-1].lower().strip(',.') in STOP_TAIL
                              or words[-1].strip(DEBRIS) == ''):
        words.pop()
    return ' '.join(words).rstrip(DEBRIS)


def _cut(s, n):
    """Trim to n chars on a word boundary, leaving a phrase that reads.

    Three kinds of leftover, all of which reached live ads: a dangling
    preposition, a dangling dash — «Кадастровый инженер дистанционно —» — and
    half a bracket, «Няня (работник по уходу и присмотру». The dash cases got
    through for years because the tidy-up stripped the ASCII hyphen and the site
    writes an em dash.
    """
    if len(s) <= n:
        return s
    out = _trim_tail(s[:n].rsplit(' ', 1)[0])
    # An opening bracket with nothing to close it: drop the fragment it started.
    if out.count('(') > out.count(')'):
        out = out[:out.rfind('(')]
    if out.count('«') > out.count('»'):
        out = out[:out.rfind('«')]
    return out.rstrip(DEBRIS)


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


# A page title is written for search engines, so it carries a tail the ad does
# not want: «Кадастровый инженер дистанционно — обучение», «Педагог раннего
# развития — профпереподготовка». Cutting the label short used to hide these by
# accident; once the label had room to keep them, they showed up in live ads.
SEO_TAIL = re.compile(
    r'\s*[—–-]\s*(переподготовка|проф\w*|повышение|обучение|курсы?|диплом)\b.*$'
    r'|[\s,]+(онлайн|дистанционно)\s*$'
    # «Учитель логопед обучение», «Нейропсихология взрослых обучение с дипломом
    # за 8 месяцев» — the tail is for the search engine, not for the reader.
    # Only «обучение» and «диплом» start such a tail: «курс» is usually the head
    # of the phrase, and cutting there left «Дистанционный» and «Онлайн» alone.
    # The lookbehind keeps a short label from being eaten whole.
    r'|(?<=.{8})\s+(обучение|диплом\w*)\b.*$', re.I)


def label_of(page, source='title', program=None):
    """Short marketing label for the course.

    `title`     — the part of <title> before the colon (demo-academy.example).
    `h1_quoted` — the «…» phrase inside <h1> (second-academy.example, whose <title> is a
                  keyword-stuffed SEO string).
    `name`      — the catalogue's own name for the programme (third-academy.example,
                  where <title> is a keyword string written for search and <h1>
                  repeats the programme kind after a colon, while the store
                  card holds the bare speciality).
    """
    if source == 'name' and (program or {}).get('name'):
        return re.sub(r'\s+', ' ', program['name']).strip(' .«»')
    quoted = re.search(r'«([^»]+)»', page.get('h1', ''))
    if source == 'h1_quoted' and quoted:
        label = quoted.group(1)
    else:
        title = page.get('title', '').split('|')[0].strip()
        label = title.split(':')[0].strip() if ':' in title else title
        label = _trim_tail(SEO_TAIL.sub('', label).strip())
        if (not label or len(label) > 70) and quoted:
            label = quoted.group(1)
    return re.sub(r'\s+', ' ', label).strip(' .«»')


NAME_TEMPLATES = {
    'Повышение': '%s. Курс повышения квалификации',
    'Профессиональное обучение': 'Обучение: %s. Документ о квалификации',
    '': 'Обучение: %s. Диплом!',
}


# The catalogue titles these came from are SEO strings that already say
# «обучение»: «Кризисный психолог обучение на базе», «Обучение КПТ для
# психологов онлайн». Adding the template's own opening to those produced
# «Обучение: Обучение КПТ…» in live ads.
SAYS_TRAINING = re.compile(r'\bобучени\w*', re.I)
TEMPLATE_LEAD = 'Обучение: '


def _template_for(kind, cfg=None):
    """The title wording for this programme kind.

    Overridable from the config for the same reason `documents` is: the wording
    that fits one catalogue starves another. «%s. Курс повышения квалификации»
    spends 29 of the 56 characters on itself, and on a catalogue of long
    speciality names that is what cuts «Сестринское дело в косметологии» down
    to «Сестринское дело» — three programmes with one title, told apart in the
    live ad by an id. A client whose names are long says so here instead.
    """
    table = (cfg or {}).get('name_templates') or NAME_TEMPLATES
    for prefix, template in table.items():
        if prefix and kind.startswith(prefix):
            return template
    return table.get('', NAME_TEMPLATES[''])


def build_name(page, program, phrases, label_source='title', kind=DEFAULT_KIND,
               cfg=None):
    """The pre-model title rules, kept as the fallback.

    The label budget is derived from the template rather than written down: the
    old fixed numbers were sized for the feed format's 100 characters, which is
    how titles 72 characters long reached live ads and got cut mid-word.

    The programme kind is passed in rather than worked out here: it comes from
    the client config like every other fact.
    """
    label = strip_forbidden(label_of(page, label_source, program), phrases)
    template = _template_for(kind, cfg)
    if template.startswith(TEMPLATE_LEAD) and SAYS_TRAINING.search(label):
        # Dropping the opening also hands its ten characters back to the name.
        template = template[len(TEMPLATE_LEAD):]
    # No room is set aside for the « (640 ч)» the dedupe pass may add: only
    # duplicates ever get it, and charging every title eight characters cost
    # «Бухгалтерский и налоговый учет» its noun.
    name = template % _cut(label, texts.TITLE_LIMIT - len(template.replace('%s', '')))
    return texts.tidy(re.sub(r'\s+', ' ', name).strip())


# The banner clamps the description to two lines and wraps on word boundaries,
# so the real ceiling is well under what the feed format allows.
MAX_DESCRIPTION = texts.TEXT_LIMIT

# Direct cuts the description mid-word in the banner, so it has to be short and
# front-loaded: what the course is, then the standing offer. The document name
# follows the programme type — retraining gives a diploma, refresher courses an
# udostoverenie, vocational training a svidetelstvo.
#
# This is the default for a Russian further-education provider. A client whose
# programmes issue something else — or a project in another field that issues
# nothing at all — overrides it with a `documents` block in the config, so the
# word «Диплом» never has to be edited out of the code.
KIND_WORDING = {
    'Переподготовка': ('Переподготовка', 'Диплом'),
    'Профессиональная переподготовка': ('Переподготовка', 'Диплом'),
    'Повышение квалификации': ('Повышение квалификации', 'Удостоверение'),
    'Профессиональное обучение': ('Профобучение', 'Свидетельство'),
}


def wording_for(kind, cfg=None):
    """How this programme kind is named, and what document it issues."""
    table = (cfg or {}).get('documents')
    if table:
        pair = table.get(kind) or table.get(DEFAULT_KIND) or {}
        return pair.get('prefix', kind), pair.get('document', '')
    return KIND_WORDING.get(kind, KIND_WORDING[DEFAULT_KIND])

# Standing offer at the end of every description — differs per client.
DEFAULT_OFFER = 'Рассрочка 12 мес.'


# Ad-title decorations we strip to get back to the bare course name.
NAME_LEAD = re.compile(
    r'^(дистанционное обучение|онлайн[- ]обучение|обучение онлайн|'
    r'дистанционный курс|онлайн[- ]курс|курсы|курс|обучение|'
    # The description prefixes its own kind, so a name that already opens with
    # one produced «Переподготовка: Переподготовка: Педагог-хореограф».
    r'профессиональная переподготовка|переподготовка|'
    r'повышение квалификации|профобучение)\s*:\s*', re.I)
NAME_TAIL = re.compile(
    r'\s*[.,]?\s*((обучение|курс)\s*\d+\s*мес\w*\.?|'
    r'курс(ы)?( обучения)?( повышения квалификации)?( онлайн)?|'
    r'повышение квалификации|документ о квалификации|переподготовка|'
    r'профобучени\w*|проф\.?\s*обучени\w*|установленного образца|'
    r'диплом(\s+москвы|\s+санкт-петербурга)?|сертификат|удостоверение|'
    r'свидетельство|онлайн|дистанционно)[!.]*\s*$',
    re.I)
HOURS_TAIL = re.compile(r'\s*[.,]?\s*\(?\d+\s*(ч|час\w*|месяц\w*|мес\.?)\)?\s*$', re.I)


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


def build_description(page, program, phrases, offer=DEFAULT_OFFER,
                      label_source='title', kind=DEFAULT_KIND, cfg=None):
    prefix, document = wording_for(kind, cfg)
    label = (course_label(program.get('offer_name') or '')
             or label_of(page, label_source, program))
    label = strip_forbidden(EMOJI.sub('', label), phrases).strip(' .')
    tail = ('%s %s!' % (offer.rstrip(), document)) if document else offer.rstrip()
    # Same reasoning as in build_name: the hours are inserted only into
    # duplicates, and _dedupe_descriptions refuses to do it when the result
    # would overflow. Reserving room in every description just shortens it.
    budget = MAX_DESCRIPTION

    with_prefix = '%s: %s. %s' % (prefix, label, tail)
    if len(with_prefix) <= budget:
        return texts.tidy(with_prefix)
    return texts.tidy('%s. %s' % (_cut(label, budget - len(tail) - 2), tail))


# The marks _dedupe_names leaves on a title it had to make unique.
DEDUPED = re.compile(r'\((?:\d+\s*ч|id\s*\d+)\)\s*$')

INSTALMENT = re.compile(r'рассрочк', re.I)


def clean_sales_notes(stored):
    """Drop a special-offer line that repeats the instalment plan.

    Two offers still carried «Рассрочка на 24 и 36 месяцев» inherited from the
    client's own feed. The instalment terms change and are configured in one
    place now; a second, stale copy of them in another field is how a wrong
    promise reaches a live ad.
    """
    if stored and INSTALMENT.search(stored):
        return None
    return stored


def price_is_on_the_page(price, page):
    """Does the figure we are about to advertise appear on the landing page?

    Direct requires the price in the ad to match the page, and the two can drift
    apart on their own: a listing caches an old figure, a client introduces
    tariffs and the card starts showing «от …», a promotion ends. Nothing here
    changes the feed — a mismatch is reported so a person can look.
    """
    body = page.get('body') or ''
    if not body or not price:
        return True
    grouped = '{:,}'.format(int(price)).replace(',', ' ')
    return grouped in body or str(int(price)) in body


def category_of(program, cfg):
    for section in program['sections']:
        cid = cfg['sections'].get(section)
        if cid:
            return cid
    return ''


def picture_of(offer_id, cid, cfg, images, state, cluster_key=None, program=None):
    """Resolve the offer picture by the client's configured priority.

    `own`     — a creative generated for this exact program
    `cluster` — the shared creative of its micro-category
    `stored`  — the picture the client's own feed used last time
    `site`    — the picture the catalogue itself publishes for the programme

    the first client puts `cluster` above `stored` because the client's originals were
    WebP and risky at moderation; the second client keeps its own JPG/PNG photos, so there
    `stored` wins and generated art only fills the gaps.
    """
    # Same store as the feed itself, so the endpoint is configured in one place.
    import storage
    base = storage.public_url(cfg['bucket'], cfg['image_prefix'])
    known = state.get('offers', {}).get(offer_id, {}).get('picture')
    cluster = ('cluster_%s' % cluster_key) if cluster_key else None

    for source in cfg.get('picture_priority', ['own', 'cluster', 'stored']):
        if source == 'own' and offer_id in images:
            return base + images[offer_id], 'own'
        if source == 'cluster' and cluster and cluster in images:
            return base + images[cluster], 'cluster'
        if source == 'stored' and known:
            return known, 'stored'
        # A catalogue that publishes its own artwork needs no stand-in, and its
        # picture is the one the visitor sees on the landing page.
        if source == 'site' and (program or {}).get('picture'):
            return program['picture'], 'site'

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


class Generator(object):
    """Writes ad copy for offers that do not have any yet.

    `client` may be None — no key, no credit, generation switched off — and the
    run then falls back to the rules below, which is exactly what it did before
    generation existed.
    """

    def __init__(self, client=None, retries=2, reason=''):
        self.client = client
        self.retries = retries
        self.reason = reason
        self.exhausted = False
        self.stats = Counter()


def _legacy_copy(page, program, cfg, phrases, label_source, offer_line,
                 kind=DEFAULT_KIND):
    """The rules the feed used before the model — kept as the safety net."""
    def build():
        name = strip_forbidden(
            build_name(page, program, phrases, label_source, kind, cfg), phrases)
        text = build_description(page, dict(program, offer_name=name), phrases,
                                 offer_line, label_source, kind, cfg)
        return name, text
    return build


def _copy_for(program, page, prev, cfg, generator, legacy, known=None):
    """Decide where this offer's copy comes from. Returns (name, text, ad).

    The order matters and is the whole point of the caching rule: a stored ad is
    reassembled with today's price, an offer that predates generation keeps the
    copy it already has, and only a genuinely new offer costs a model call.
    Rewriting a live offer would reset the statistics Direct has accumulated on
    it, which is far more expensive than the call itself.
    """
    price = program['price']
    stored_ad = prev.get('ad')
    if stored_ad and stored_ad.get('name'):
        title, text, _ = texts.assemble(stored_ad, price, cfg)
        generator.stats['cached'] += 1
        return title, text, stored_ad
    if prev.get('name'):
        name = prev['name']
        # One exception to leaving stored copy alone: a title over the display
        # limit is already broken — the ad shows two thirds of it and an
        # ellipsis. Rebuilding it costs the offer's statistics but buys back a
        # readable ad, which is the whole point of the statistics.
        fresh = None
        if len(name) > texts.TITLE_LIMIT or texts.artefacts(name):
            # Over the limit, or cut in the wrong place — «Кадастровый инженер
            # дистанционно —. Диплом!». Either way the ad is already spoiled, so
            # the statistics a rebuild costs are worth less than the repair.
            fresh = legacy()[0]
        elif not DEDUPED.search(name):
            # The same title cut short by a budget that has since been relaxed:
            # «Обучение: Государственное. Диплом!» where the rules now yield
            # «Обучение: Государственное и муниципальное управление». Only a
            # title that starts the same way and got longer qualifies, so this
            # repairs what we truncated and leaves everything else alone.
            #
            # A title the dedupe pass shaped is excluded, and that exclusion is
            # what makes the repair terminate. Dedupe trades «. Диплом!» for
            # « (540 ч)» to tell two identical titles apart, leaving a name one
            # character shorter than the rules produce — so without this guard
            # the repair and the dedupe undo each other on every single run,
            # rewriting those offers daily and resetting their statistics daily.
            candidate = legacy()[0]
            if len(candidate) > len(name) and candidate[:12] == name[:12]:
                fresh = candidate
        if fresh:
            name = fresh
            generator.stats['reshaped'] += 1
        text = build_description(page, dict(program, offer_name=name),
                                 cfg.get('forbidden_phrases', []),
                                 cfg.get('offer_tail', DEFAULT_OFFER),
                                 cfg.get('label_source', 'title'),
                                 (known or {}).get('kind', DEFAULT_KIND), cfg)
        generator.stats['kept'] += 1
        return name, text, None
    if generator.client and not generator.exhausted:
        known = dict(known or facts_rules.extract(page, program, cfg))
        known['mode_hint'] = cfg.get('mode_overrides', {}).get(program['id'], '')
        title, text, ad, meta = texts.generate(known, cfg, price, generator.client,
                                               legacy, generator.retries)
        generator.stats[meta['source']] += 1
        generator.stats['attempts'] += meta['attempts']
        if meta.get('exhausted'):
            # The ceiling is per run, not per offer: once it is hit every
            # remaining programme takes the deterministic path without trying.
            generator.exhausted = True
        return title, text, ad
    name, text = legacy()
    generator.stats['legacy'] += 1
    return name, text, None


def build_offers(programs, pages, cfg, images, state, generator=None):
    """Turn crawled programs into offer dicts, carrying over stored fields."""
    phrases = cfg.get('forbidden_phrases', [])
    offer_line = cfg.get('offer_tail', DEFAULT_OFFER)
    label_source = cfg.get('label_source', 'title')
    # Some clients advertise only part of their catalogue (the second client — retraining
    # only), so refresher courses and mini-courses never enter the feed.
    include = cfg.get('include_kinds')
    # Where the catalogue and the landing page keep two different prices, the
    # ad has to show the one the visitor will read, so the page wins wherever
    # it states a price at all. Configured as rules, like every other thing
    # this robot reads off a page.
    price_rules = cfg.get('price_rules')
    stored = state.get('offers', {})
    generator = generator or Generator()
    offers = []
    skipped = []
    mismatched = []
    for key, program in programs.items():
        page = pages.get(key, {})
        # Every fact this offer needs, read once from the client's rules. The
        # kind used to be worked out separately here, in build_name and in
        # build_description, which meant the config could be edited without the
        # robot's behaviour following — and the extraction check would report a
        # kind the feed never actually used.
        known = facts_rules.extract(page, program, cfg)
        if include and known['kind'] not in include:
            continue
        if price_rules:
            stated = facts_rules.value_of(price_rules, page, program)
            if stated:
                program = dict(program, price=int(stated))
        # A price is mandatory in YML; a card without one cannot be advertised.
        # The crossed-out price is not: catalogues that do not run a standing
        # discount have none, and demanding it there empties the feed.
        if not program.get('price') or (cfg.get('require_oldprice', True)
                                        and not program.get('oldprice')):
            skipped.append((program['id'], program.get('name', ''), key))
            continue
        oid = program['id']
        prev = stored.get(oid, {})
        # Keep the category the client's own feed assigned; the section mapping
        # is only a fallback for programs we are seeing for the first time.
        cid = prev.get('categoryId') or category_of(program, cfg)
        cluster_key = clusters.assign('%s %s'
                                      % (label_of(page, label_source, program), program['name']))
        legacy = _legacy_copy(page, program, cfg, phrases, label_source, offer_line,
                              known['kind'])
        name, description, ad = _copy_for(program, page, prev, cfg, generator,
                                          legacy, known)
        picture = picture_of(oid, cid, cfg, images, state, cluster_key, program)
        if not price_is_on_the_page(program['price'], page):
            generator.stats['price_mismatch'] += 1
            mismatched.append((oid, program['price'], key))
        offers.append(dict(
            key=key,
            id=oid,
            available='true',
            name=name,
            categoryId=cid,
            url=cfg['base_url'] + key,
            picture=picture[0],
            picture_source=picture[1],
            description=description,
            ad=ad,
            price=program['price'],
            oldprice=program['oldprice'],
            custom_label_0=prev.get('custom_label_0', 'False'),
            custom_label_1=prev.get('custom_label_1', 'False'),
            custom_score=prev.get('custom_score'),
            sales_notes=clean_sales_notes(prev.get('sales_notes')),
            hours=known['hours'],
            kind=known['kind'],
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
    if mismatched:
        print('      цена не найдена на странице программы: %d' % len(mismatched))
        for oid, price, key in mismatched[:5]:
            print('        %s %s ₽ %s' % (oid, price, key))
    if skipped:
        print('      без цены, в фид не попали: %d' % len(skipped))
        for oid, nm, key in skipped[:10]:
            print('        %s %s' % (oid, (nm or key)[:60]))
    return offers


def _dedupe_names(offers):
    """Two programmes can end up with the same title; the hours tell them apart.

    The budget is the display limit, not the feed format's 100 characters —
    padding a title to 96 only means the ad shows two thirds of it and an
    ellipsis.
    """
    limit = texts.TITLE_LIMIT
    counts = Counter(o['name'] for o in offers)
    for o in offers:
        if counts[o['name']] > 1:
            suffix = ' (%s ч)' % o['hours'] if o.get('hours') else ' (id %s)' % o['id']
            o['name'] = _cut(o['name'], limit - len(suffix)) + suffix
    still = {n for n, c in Counter(o['name'] for o in offers).items() if c > 1}
    for o in offers:
        if o['name'] in still:
            suffix = ' (id %s)' % o['id']
            o['name'] = _cut(o['name'], limit - len(suffix)) + suffix


def _dedupe_descriptions(offers):
    """Two programmes can share a label; the hours tell them apart without
    pushing the line past the truncation point."""
    counts = Counter(o['description'] for o in offers)
    for o in offers:
        if counts[o['description']] > 1 and o.get('hours'):
            longer = o['description'].replace(
                '. Рассрочка', ', %s ч. Рассрочка' % o['hours'], 1)
            # Telling two offers apart is not worth pushing the line past the
            # point where Direct truncates it.
            if len(longer) <= texts.TEXT_LIMIT:
                o['description'] = longer


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
        required = ['name', 'url', 'picture', 'description', 'price']
        if cfg.get('require_oldprice', True):
            required.append('oldprice')
        for field in required:
            if not o.get(field):
                problems.append('оффер %s: пустое поле %s' % (o['id'], field))
        if o.get('price') and o.get('oldprice') and o['oldprice'] <= o['price']:
            problems.append('оффер %s: oldprice %s не выше price %s'
                            % (o['id'], o['oldprice'], o['price']))
        if len(o['name']) > 100:
            problems.append('оффер %s: имя длиннее 100 символов' % o['id'])
        # Cosmetic, so it does not block publishing — but it must never again be
        # something only a screenshot of a live ad reveals.
        for field in ('name', 'description'):
            for found in texts.artefacts(o.get(field, '')):
                problems.append('оффер %s: %s в поле %s — %s'
                                % (o['id'], found, field, o[field][:60]))
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
        # An empty <oldprice> is not «no discount», it is a malformed offer.
        if o.get('oldprice'):
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
