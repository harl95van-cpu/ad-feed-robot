# -*- coding: utf-8 -*-
"""Weekly feed rebuild for Yandex Direct.

Crawls the client's catalog, checks prices and availability against the last
run, rebuilds the YML feed, uploads it to Object Storage and reports to
Telegram. Runs both as a Yandex Cloud Function and from the command line.
"""
import os
import json
import datetime
import traceback

import catalog
import crawler
import feed as feed_builder
import history
import llm
import storage
import notify

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clients_config.json')


def load_config(client_code):
    with open(CONFIG_PATH, encoding='utf-8') as f:
        config = json.load(f)
    if client_code not in config:
        raise ValueError('Unknown client %r. Known: %s' % (client_code, ', '.join(config)))
    return config[client_code]


def diff_against_state(offers, state):
    """Compare this run to the previous one: prices, new and vanished programs."""
    stored = state.get('offers', {})
    live = [o for o in offers if o['available'] == 'true']
    result = dict(total=len(offers), price_changes=[], added=[], removed=[])
    for o in live:
        prev = stored.get(o['id'])
        if not prev:
            result['added'].append(dict(id=o['id'], name=o['name'],
                                        price=o['price'], url=o['url']))
        elif prev.get('price') and o.get('price') and int(prev['price']) != int(o['price']):
            result['price_changes'].append(dict(id=o['id'], name=o['name'], url=o['url'],
                                                old=int(prev['price']), new=int(o['price'])))
    live_ids = {o['id'] for o in live}
    for oid, prev in stored.items():
        if oid not in live_ids and prev.get('available') != 'false':
            result['removed'].append(dict(id=oid, name=prev.get('name', ''),
                                          url=prev.get('url'), price=prev.get('price')))
    return result


def has_changes(diff, problems):
    return bool(diff['price_changes'] or diff['added'] or diff['removed'] or problems)


def _publish_monthly(s3, bucket, client_code):
    """On the first of the month, drop last month's summary into the bucket."""
    if datetime.date.today().day != 1:
        return
    try:
        import monthly_report
        month = monthly_report.previous_month()
        md, count = monthly_report.build(client_code, month)
        key = 'reports/%s_monthly_%s.md' % (client_code, month)
        storage.put_text(s3, bucket, key, md, 'text/markdown; charset=utf-8')
        print('[история] месячная сводка за %s: %d изменений' % (month, count))
    except Exception as exc:
        print('[история] месячную сводку не собрали: %s' % str(exc)[:200])


def build_state(offers, today):
    return {
        'updated_at': today,
        'offers': {o['id']: {
            'name': o['name'],
            'categoryId': o['categoryId'],
            'url': o['url'],
            # Stand-ins are not this offer's picture — storing one would make
            # the next run treat it as known and never upgrade to a real image.
            'picture': o['picture'] if o.get('picture_source') != 'fallback' else None,
            'price': o['price'],
            'oldprice': o['oldprice'],
            'available': o['available'],
            'custom_label_0': o.get('custom_label_0', 'False'),
            'custom_label_1': o.get('custom_label_1', 'False'),
            'custom_score': o.get('custom_score'),
            'sales_notes': o.get('sales_notes'),
            'gone_cycles': o.get('gone_cycles', 0),
            # The written copy, cached so the model is never asked twice for the
            # same programme: name, its accusative and the duration frozen at
            # the time of writing. The price is deliberately not here — it is
            # substituted fresh on every build.
            'ad': o.get('ad'),
        } for o in offers},
    }


def open_generator(cfg, disabled=False):
    """Set up ad-copy generation, or explain why the run goes without it.

    Never raises: no key, no credit or a dead endpoint must not stop a feed from
    being rebuilt. Without a generator every offer keeps the copy it has and new
    ones fall back to the deterministic rules.
    """
    opts = llm.settings(cfg)
    if disabled:
        return feed_builder.Generator(None, opts['retries'], 'отключено флагом')
    client, reason = llm.open_client(cfg)
    if reason:
        print('      [тексты] генерация не запущена: %s' % reason)
    return feed_builder.Generator(client, opts['retries'], reason)


def generation_summary(generator):
    """One line for the console and the Telegram report."""
    s = generator.stats
    if generator.reason:
        # Generation being off does not make the counts uninteresting: the
        # reshaped titles happen either way and are worth seeing.
        parts = ['генерация выключена (%s)' % generator.reason,
                 'без генерации: %d' % (s.get('kept', 0) + s.get('legacy', 0))]
        if s.get('reshaped'):
            parts.append('укорочено заголовков: %d' % s['reshaped'])
        return 'тексты: ' + ', '.join(parts)
    parts = ['новых от модели: %d' % s.get('model', 0)]
    if s.get('fallback'):
        parts.append('откатов: %d' % s['fallback'])
    if s.get('model'):
        parts.append('попыток на текст: %.1f'
                     % (s.get('attempts', 0) / float(s['model'] + s.get('fallback', 0))))
    if generator.client and generator.client.spent:
        parts.append('потрачено $%.4f' % generator.client.spent)
    parts.append('из кэша: %d' % s.get('cached', 0))
    if s.get('kept'):
        parts.append('без генерации: %d' % s['kept'])
    if s.get('reshaped'):
        parts.append('укорочено заголовков: %d' % s['reshaped'])
    if s.get('price_mismatch'):
        parts.append('ЦЕНА НЕ НАЙДЕНА НА СТРАНИЦЕ: %d' % s['price_mismatch'])
    return 'тексты: ' + ', '.join(parts)


def run(client_code, dry_run=False, out_path=None, no_generate=False):
    cfg = load_config(client_code)
    today = datetime.date.today().isoformat()
    s3 = storage.client()
    bucket = cfg['bucket']

    state = storage.get_json(s3, bucket, cfg['state_key'], default={'offers': {}})

    print('[1/6] обход каталога %s' % cfg['base_url'])
    programs = crawler.crawl_catalog(cfg)
    print('      найдено программ: %d' % len(programs))

    # Guard: a broken layout or a site outage must never wipe the live feed.
    guard = cfg.get('min_offers_guard', 0)
    if len(programs) < guard:
        reason = ('Каталог вернул всего %d программ при пороге %d — похоже, сайт лежит '
                  'или поменялась вёрстка.' % (len(programs), guard))
        print('[!] ' + reason)
        notify.send(notify.format_alert(client_code, reason))
        return {'status': 'aborted', 'reason': reason}

    print('[2/6] карточки программ')
    pages = crawler.fetch_details(programs, cfg['base_url'])
    missed = [k for k in programs if not pages.get(k, {}).get('meta')]
    if len(missed) > max(10, len(programs) * 0.1):
        reason = ('Не удалось прочитать карточки %d программ из %d — сайт отдаёт ошибки.'
                  % (len(missed), len(programs)))
        print('[!] ' + reason)
        notify.send(notify.format_alert(client_code, reason))
        return {'status': 'aborted', 'reason': reason}
    if missed:
        print('      без описания с сайта: %d (возьмём шаблон)' % len(missed))

    print('[3/6] картинки из хранилища')
    images = storage.list_images(s3, bucket, cfg['image_prefix'])
    print('      своих картинок: %d' % len(images))

    print('[4/6] сборка офферов')
    generator = open_generator(cfg, no_generate)
    offers = feed_builder.build_offers(programs, pages, cfg, images, state, generator)
    print('      %s' % generation_summary(generator))
    problems = feed_builder.validate(offers, cfg)
    if problems:
        print('      проблемы валидации: %d' % len(problems))
        for p in problems[:10]:
            print('        - %s' % p)

    diff = diff_against_state(offers, state)
    no_image = sum(1 for o in offers if o['available'] == 'true'
                   and not o.get('has_own_image') and not o.get('has_cluster_image'))
    own = sum(1 for o in offers if o.get('has_own_image'))
    print('      картинок: %d персональных, %d по микрокатегориям, %d без своей'
          % (own, len(offers) - own - no_image, no_image))
    xml = feed_builder.render(offers, cfg)

    if out_path:
        with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(xml)
        print('      локальная копия: %s' % out_path)

    if dry_run:
        print('[dry-run] фид не загружен, офферов: %d' % len(offers))
        print(notify.format_report(client_code, diff,
                                   storage.public_url(bucket, cfg['feed_key']),
                                   problems, no_image, generation_summary(generator)))
        return {'status': 'dry-run', 'offers': len(offers), 'diff': diff,
                'texts': dict(generator.stats)}

    print('[5/6] загрузка в Object Storage')
    storage.put_text(s3, bucket, cfg['feed_key'], xml, 'application/xml; charset=utf-8')
    storage.put_json(s3, bucket, cfg['state_key'], build_state(offers, today))
    storage.put_json(s3, bucket, 'reports/%s_%s.json' % (client_code, today),
                     dict(diff=diff, problems=problems, no_image=no_image))
    history.record(client_code, today, diff)
    # Leads land on refresher and mini-course pages too, so the catalogue
    # published for analytics covers more of the site than the feed does.
    catalog_programs = dict(programs)
    for section in cfg.get('catalog_sections', []):
        try:
            catalog_programs.update({k: v for k, v in
                                     crawler.crawl_catalog(cfg, [section]).items()
                                     if k not in catalog_programs})
        except Exception as exc:
            print('[catalog] раздел %s не обошли: %s' % (section, str(exc)[:120]))
    catalog.record(client_code, today, catalog_programs, pages, offers, cfg)
    _publish_monthly(s3, bucket, client_code)

    # Daily runs would otherwise ping every morning with "nothing changed".
    if has_changes(diff, problems):
        print('[6/6] отчёт в телеграм')
        notify.send(notify.format_report(client_code, diff,
                                         storage.public_url(bucket, cfg['feed_key']),
                                         problems, no_image,
                                         generation_summary(generator)))
    else:
        print('[6/6] изменений нет — в телеграм не пишем')
    return {'status': 'ok', 'offers': len(offers), 'diff': diff,
            'problems': len(problems), 'texts': dict(generator.stats)}


def selftest(cfg):
    """Can this machine reach the model provider at all?

    Worth having as a button: the balance endpoint answers on a laptop and comes
    back «Access denied by security policy» inside the cloud function, and the
    daily run cannot tell us whether generation works because it only calls the
    model when a genuinely new programme appears — which can be weeks apart.
    """
    result = {}
    client, reason = llm.open_client(cfg)
    result['клиент'] = reason or 'создан'
    if not client:
        return result
    balance = client.credits()
    result['баланс'] = 'не прочитан' if balance is None else round(balance, 4)
    try:
        answer = client.chat([{'role': 'user', 'content': 'Ответь одним словом: работает'}])
        result['вызов модели'] = 'ok: %s' % answer.strip()[:40]
        result['стоимость'] = round(client.spent, 6)
    except Exception as exc:
        result['вызов модели'] = 'ОШИБКА: %s' % str(exc)[:200]
    return result


def handler(event, context):
    """Yandex Cloud Function entry point."""
    client_code = os.environ.get('CLIENT_CODE')
    if isinstance(event, dict) and event.get('selftest'):
        return {'statusCode': 200,
                'body': json.dumps(selftest(load_config(client_code)), ensure_ascii=False)}
    try:
        result = run(client_code)
        return {'statusCode': 200, 'body': json.dumps(result, ensure_ascii=False)}
    except Exception as exc:
        trace = traceback.format_exc()
        print(trace)
        notify.send(notify.format_alert(client_code or '?', 'Ошибка: %s' % exc))
        return {'statusCode': 500, 'body': str(exc)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out', help='save the rendered feed to a local file')
    parser.add_argument('--no-generate', action='store_true',
                        help='skip the model entirely — a dry run that costs nothing')
    args = parser.parse_args()

    llm.load_environment()
    print(json.dumps(run(args.client, dry_run=args.dry_run, out_path=args.out,
                         no_generate=args.no_generate),
                     ensure_ascii=False, indent=1))
