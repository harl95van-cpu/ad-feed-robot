# -*- coding: utf-8 -*-
"""Run the text generator over the reference set and score the result.

This is how a prompt change or a model change is judged — on the same fixed set
of programs every time, not on whatever ten offers happened to be new that day.

    venv/Scripts/python.exe Scripts/feeds/feed_builder/eval/eval_texts.py \
        --model google/gemini-3.1-flash-lite --limit 10

Each run is saved as a JSON file. Passing --against an earlier one prints only
what changed, which is the useful view: a prompt edit meant to fix three
programs should not quietly reword forty others.

The run costs money, so --limit exists and the estimated spend is printed on the
way out. There is no reason to evaluate the whole set after a one-line edit.
"""
import os
import re
import sys
import json
import time
import argparse
from collections import Counter

BUILDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BUILDER)

import facts as facts_rules  # noqa: E402
import texts                 # noqa: E402
import llm                   # noqa: E402
import feed                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BUILDER, '..', '..', '..'))
REFERENCE = os.path.join(HERE, 'reference_set.json')


def load_config(client):
    with open(os.path.join(BUILDER, 'clients_config.json'), encoding='utf-8') as f:
        return json.load(f)[client]


def as_page(row):
    return dict(title=row['title'], h1=row['h1'], meta=row['meta'],
                body=row.get('body', ''))


def as_program(row):
    return dict(id=row['id'], name=row['listing_name'], url=row['url'],
                price=row['price'], oldprice=row['oldprice'], hints=row['hints'])


def fact_asker(client):
    """The model-assisted second pass of extraction, same as the robot uses."""
    def ask(fields, page_text):
        prompt = (
            'Ниже — фрагменты страницы курса. Верни JSON строго с полями: %s.\n'
            'Значение бери дословно из текста страницы, ничего не сочиняй.\n'
            'Если поля на странице нет — верни для него пустую строку.\n'
            'profession — короткое название профессии или квалификации, которую\n'
            'получает выпускник, не длиннее 60 символов. Название программы\n'
            'профессией не является.\n\n%s' % (', '.join(fields), page_text))
        content = client.chat([{'role': 'user', 'content': prompt}], temperature=0)
        body = re.sub(r'^```[a-z]*\s*|\s*```$', '', content.strip(), flags=re.S)
        m = re.search(r'\{.*\}', body, re.S)
        return json.loads(m.group(0) if m else body)
    return ask


def evaluate(rows, client, retries, configs):
    results, tally = [], Counter()
    ask = fact_asker(client)
    for row in rows:
        page, program = as_page(row), as_program(row)
        cfg = configs[row['client']]
        known = facts_rules.extract(page, program, cfg)
        known = facts_rules.resolve_missing(known, page, program, ask)
        # The same lookup the daily run does. Without it the evaluation measures
        # a pipeline production does not have, and a Wordstat verdict already
        # recorded in the config would never show up in the numbers.
        known['mode_hint'] = cfg.get('mode_overrides', {}).get(row['id'], '')
        legacy = feed._legacy_copy(page, program, cfg,
                                   cfg.get('forbidden_phrases', []),
                                   cfg.get('label_source', 'title'),
                                   cfg.get('offer_tail', feed.DEFAULT_OFFER))
        title, text, entry, meta = texts.generate(known, cfg, row['price'],
                                                  client, legacy, retries)
        tally[meta['source']] += 1
        tally['attempts'] += meta['attempts']
        if meta['source'] == 'model':
            tally['mode_' + meta['mode']] += 1
            # A dropped rung means the decoration had to go to keep the meaning.
            tally['title_trimmed'] += 1 if meta['rungs'][0] else 0
            tally['text_trimmed'] += 1 if meta['rungs'][1] else 0
        if row.get('gold_title'):
            tally['gold_total'] += 1
            tally['gold_match'] += 1 if title == row['gold_title'] else 0
        results.append(dict(client=row['client'], id=row['id'], url=row['url'],
                            profession=known['profession'],
                            profession_source=known['sources']['profession'],
                            title=title, text=text, entry=entry,
                            source=meta['source'], attempts=meta['attempts'],
                            problems=meta.get('problems', [])))
    return results, tally


def report(tally, total, client):
    written = tally['model'] + tally['fallback']
    print('\nвсего программ: %d' % total)
    print('от модели: %d | откатов: %d' % (tally['model'], tally['fallback']))
    if written:
        print('попыток на текст: %.2f' % (tally['attempts'] / float(written)))
    print('режим: профессия %d, тема %d'
          % (tally['mode_person'], tally['mode_topic']))
    print('пришлось убрать обрамление: заголовок %d, текст %d'
          % (tally['title_trimmed'], tally['text_trimmed']))
    if tally['gold_total']:
        print('совпало с эталоном: %d из %d'
              % (tally['gold_match'], tally['gold_total']))
    print('вызовов: %d | сбоев: %d | потрачено $%.5f'
          % (client.calls, client.failures, client.spent))
    if total:
        print('в пересчёте на программу: $%.5f' % (client.spent / total))


def compare(results, path):
    """Only what moved since the earlier run — a targeted fix should be targeted."""
    with open(path, encoding='utf-8') as f:
        before = {r['id']: r for r in json.load(f)['results']}
    changed = [r for r in results
               if r['id'] in before and before[r['id']]['title'] != r['title']]
    print('\nизменилось заголовков: %d из %d' % (changed and len(changed) or 0,
                                                 len(results)))
    for r in changed:
        print('  %s' % r['url'][:70])
        print('    было : %s' % before[r['id']]['title'])
        print('    стало: %s' % r['title'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', default=REFERENCE)
    ap.add_argument('--model', help='override the model from the client config')
    ap.add_argument('--limit', type=int, help='evaluate only the first N programs')
    ap.add_argument('--min-balance', type=float,
                    help='lower the pre-flight floor for a cheap run')
    ap.add_argument('--out', help='where to save this run (default: eval/runs/…)')
    ap.add_argument('--against', help='an earlier run file to diff against')
    args = ap.parse_args()

    llm.load_environment()

    with open(args.reference, encoding='utf-8') as f:
        rows = json.load(f)
    if args.limit:
        rows = rows[:args.limit]

    configs = {}
    for code in {r['client'] for r in rows}:
        cfg = load_config(code)
        if args.model:
            cfg.setdefault('text_generation', {})['model'] = args.model
        if args.min_balance is not None:
            cfg.setdefault('text_generation', {})['min_balance_usd'] = args.min_balance
        configs[code] = cfg

    any_cfg = configs[rows[0]['client']]
    client, reason = llm.open_client(any_cfg)
    if not client:
        print('оценка не запущена: %s' % reason)
        return
    retries = llm.settings(any_cfg)['retries']
    print('модель: %s | программ: %d | повторов: %d' % (client.model, len(rows), retries))

    started = time.time()
    results, tally = evaluate(rows, client, retries, configs)
    for r in results:
        print('\n%s %s' % (r['client'], r['url'][:66]))
        print('  %-2d %s' % (len(r['title']), r['title']))
        print('  %-2d %s' % (len(r['text']), r['text']))
        if r['source'] == 'fallback':
            print('  ОТКАТ: %s' % '; '.join(r['problems'])[:160])
    report(tally, len(rows), client)
    print('время: %.0f с' % (time.time() - started))

    # Seconds, not minutes: two runs a minute apart shared a filename, and the
    # second silently overwrote the very file the first was being compared with.
    out = args.out or os.path.join(
        HERE, 'runs', '%s_%s.json' % (client.model.replace('/', '_'),
                                      time.strftime('%Y-%m-%d_%H%M%S')))
    if args.against and os.path.abspath(out) == os.path.abspath(args.against):
        raise SystemExit('результат совпал бы с файлом сравнения: укажи --out')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(dict(model=client.model, spent=round(client.spent, 5),
                       tally=dict(tally), results=results), f,
                  ensure_ascii=False, indent=1)
    print('результат: %s' % out)

    if args.against:
        compare(results, args.against)


if __name__ == '__main__':
    main()
