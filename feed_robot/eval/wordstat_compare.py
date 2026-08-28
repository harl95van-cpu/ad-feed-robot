# -*- coding: utf-8 -*-
"""Decide «профессия или тема» in the title by what people actually search for.

The question cannot be settled by campaign statistics — that data would take
months to accumulate at a granularity we do not have — and a model judge turned
out to grade whichever wording matched the catalogue title, not the one that
pulls. Wordstat answers it directly and today.

The comparison is between **commercial bundles**, not masks and not single
words: «обучение на логопеда» against «обучение логопедии». A bare word's
frequency mixes commercial demand with informational demand and settles nothing.

Two numbers come back per phrase — the exact frequency (the phrase in quotes,
word forms fixed) and the broad one. The exact figure decides; the broad one is
printed as a sanity check, because a bundle that wins on one and loses on the
other is a coin flip and is left alone.

    venv/Scripts/python.exe Scripts/feeds/feed_builder/eval/wordstat_compare.py \
        --run eval/runs/<file>.json --limit 12

Writes a verdict per programme and, with --emit-config, the `mode_overrides`
block to paste into clients_config.json. The daily run never calls Wordstat: it
reads that block, so two identical runs stay identical.
"""
import os
import re
import sys
import json
import time
import argparse
import requests
from collections import Counter

BUILDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BUILDER)

import llm  # noqa: E402


def direct_token(client_code):
    """The Direct API token for this account.

    Read straight from the environment rather than through a shared client, so
    this script has no dependency outside the package: `YANDEX_DIRECT_TOKEN_<CODE>`
    first, `YANDEX_DIRECT_TOKEN` as the fallback for a single-account setup.
    """
    for name in ('YANDEX_DIRECT_TOKEN_%s' % (client_code or '').upper(),
                 'YANDEX_DIRECT_TOKEN'):
        token = os.environ.get(name)
        if token:
            return token
    raise SystemExit('нет токена Директа: задай YANDEX_DIRECT_TOKEN в окружении')

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(HERE, 'reference_set.json')
API = 'https://api.direct.yandex.ru/v4/json/'
RUSSIA = 225
# The v4 report takes a handful of phrases at a time and the daily quota is
# small, so requests are batched and the queue is cleaned up after itself.
BATCH = 10

PHRASE_PROMPT = """Тебе дана учебная программа. Составь две поисковые фразы, которыми
человек искал бы это обучение в Яндексе.

profession_query — связка «обучение + профессия». Обязательно начинается со
                   слов «обучение на » и дальше профессия в винительном падеже:
                   «обучение на логопеда», «обучение на бухгалтера».
topic_query      — связка «обучение + направление», без слова «на»:
                   «обучение логопедии», «обучение бухгалтерскому учету».

Обе фразы: строчными буквами, без кавычек, без слов «курс», «дистанционно»,
«диплом». Начинай обе со слова «обучение». Падежи естественные, как в живом
поиске. Ничего не выдумывай сверх того, что дано.

Каждая фраза — не длиннее пяти слов. Так люди и ищут: не «обучение экономике
и управлению в физической культуре и спорте», а «обучение спортивному
менеджменту». Бери самое узнаваемое ядро.

Ответ — только JSON:
{"profession_query": "...", "topic_query": "..."}"""


def parse_json(answer):
    body = re.sub(r'^```[a-z]*\s*|\s*```$', '', (answer or '').strip(), flags=re.S)
    m = re.search(r'\{.*\}', body, re.S)
    return json.loads(m.group(0) if m else body)


class Wordstat(object):
    """Yandex Direct API v4 — the same path the semantics collector uses."""

    def __init__(self, client_code):
        self.token = direct_token(client_code)

    def _call(self, method, param=None):
        body = {'method': method, 'token': self.token}
        if param is not None:
            body['param'] = param
        r = requests.post(API, timeout=60,
                          headers={'Content-Type': 'application/json; charset=utf-8'},
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'))
        answer = r.json()
        if 'error_code' in answer:
            raise RuntimeError('Wordstat: %s' % json.dumps(answer, ensure_ascii=False)[:200])
        return answer.get('data')

    def _drain(self):
        for report in (self._call('GetWordstatReportList') or []):
            self._call('DeleteWordstatReport', report['ReportID'])

    def shows(self, phrases, geo=RUSSIA):
        """{phrase: (exact, broad)} — exact decides, broad is the sanity check."""
        out = {}
        for start in range(0, len(phrases), BATCH):
            chunk = phrases[start:start + BATCH]
            self._drain()
            report_id = self._call('CreateNewWordstatReport',
                                   {'Phrases': ['"%s"' % p for p in chunk],
                                    'GeoID': [geo]})
            for _ in range(60):
                listed = self._call('GetWordstatReportList') or []
                current = next((x for x in listed if x['ReportID'] == report_id), None)
                if current and current['StatusReport'] == 'Done':
                    break
                if current and current['StatusReport'] == 'Failed':
                    raise RuntimeError('Wordstat отчёт %s не собрался' % report_id)
                time.sleep(4)
            for item in (self._call('GetWordstatReport', report_id) or []):
                bare = (item.get('Phrase') or '').strip('"')
                exact = broad = 0
                for row in item.get('SearchedWith') or []:
                    if row['Phrase'].startswith('"'):
                        exact = max(exact, row['Shows'])
                    else:
                        broad = max(broad, row['Shows'])
                out[bare] = (exact, broad)
            self._call('DeleteWordstatReport', report_id)
        return out


def build_queries(client, rows, reference):
    """One model call per programme to phrase both bundles naturally."""
    pairs = []
    for row in rows:
        ref = reference.get((row['client'], row['id']), {})
        facts = ['Название программы: %s' % (ref.get('listing_name') or row['title'])]
        if row.get('profession'):
            facts.append('Профессия: %s' % row['profession'])
        else:
            continue          # nothing to compare against — no profession exists
        try:
            answer = client.chat([{'role': 'system', 'content': PHRASE_PROMPT},
                                  {'role': 'user', 'content': '\n'.join(facts)}],
                                 temperature=0)
            data = parse_json(answer)
        except Exception as exc:
            print('  [x] %s: %s' % (row['id'], str(exc)[:120]))
            continue
        a = re.sub(r'\s+', ' ', str(data.get('profession_query') or '')).strip().lower()
        b = re.sub(r'\s+', ' ', str(data.get('topic_query') or '')).strip().lower()
        # Wordstat refuses a keyword longer than seven words. Trimming one
        # would change what is being measured, so an over-long pair is dropped
        # and counted rather than quietly reshaped.
        if not a or not b:
            continue
        if a == b:
            # Nothing to compare: the model could not phrase the two bundles
            # differently, which usually means the programme has no profession.
            print('  пропущено, обе связки совпали: %s' % a)
            continue
        # Wordstat refuses a keyword longer than seven words. Trimming one would
        # change what is being measured, so an over-long pair is dropped and
        # counted rather than quietly reshaped.
        if max(len(a.split()), len(b.split())) > 7:
            print('  пропущено, фраза длиннее 7 слов: %s / %s' % (a, b))
            continue
        if not a.startswith('обучение на '):
            a = 'обучение на ' + re.sub(r'^обучение\s+', '', a)
        pairs.append((row, a, b))
    return pairs


def verdict(exact_a, exact_b, broad_a, broad_b):
    """Person wins only when both readings agree — otherwise leave it alone."""
    if exact_a == exact_b:
        return ''
    winner = 'person' if exact_a > exact_b else 'topic'
    agrees = (broad_a > broad_b) if winner == 'person' else (broad_b > broad_a)
    return winner if agrees else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, help='evaluation run with the entries')
    ap.add_argument('--reference', default=REFERENCE)
    ap.add_argument('--client-code', default='DEMO',
                    help='which Direct account the Wordstat quota is taken from')
    ap.add_argument('--model', default='google/gemini-3.1-flash-lite')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--min-balance', type=float)
    ap.add_argument('--emit-config', action='store_true',
                    help='print the mode_overrides block for clients_config.json')
    args = ap.parse_args()

    llm.load_environment()

    with open(args.reference, encoding='utf-8') as f:
        reference = {(r['client'], r['id']): r for r in json.load(f)}
    with open(args.run, encoding='utf-8') as f:
        rows = json.load(f)['results']
    if args.limit:
        rows = rows[:args.limit]

    cfg = {'text_generation': {'model': args.model, 'temperature': 0,
                               'max_spend_usd': 0.10,
                               'min_balance_usd': (args.min_balance
                                                   if args.min_balance is not None else 0.05)}}
    client, reason = llm.open_client(cfg)
    if not client:
        print('сравнение не запущено: %s' % reason)
        return

    pairs = build_queries(client, rows, reference)
    print('сравниваем связки по %d программам\n' % len(pairs))
    phrases = sorted({p for _, a, b in pairs for p in (a, b)})
    shows = Wordstat(args.client_code).shows(phrases)

    tally, overrides, undecided = Counter(), {}, 0
    for row, a, b in pairs:
        ea, ba = shows.get(a, (0, 0))
        eb, bb = shows.get(b, (0, 0))
        who = verdict(ea, eb, ba, bb)
        tally[who or 'ничья'] += 1
        if who:
            overrides.setdefault(row['client'], {})[row['id']] = who
        else:
            undecided += 1
        mark = {'person': 'ПРОФЕССИЯ', 'topic': 'ТЕМА'}.get(who, 'ничья')
        print('%-10s %s' % (mark, row['url'][:60]))
        print('   %-42s точно %5d | широко %6d' % (a, ea, ba))
        print('   %-42s точно %5d | широко %6d' % (b, eb, bb))

    print('\nпрофессия чаще: %d | тема чаще: %d | не решено: %d'
          % (tally['person'], tally['topic'], undecided))
    print('вызовов модели: %d | потрачено $%.5f' % (client.calls, client.spent))

    out = os.path.join(HERE, 'wordstat', 'modes_%s.json' % time.strftime('%Y-%m-%d_%H%M'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(dict(tally=dict(tally), overrides=overrides,
                       shows={k: list(v) for k, v in shows.items()}), f,
                  ensure_ascii=False, indent=1)
    print('решения: %s' % out)

    if args.emit_config:
        print('\nв clients_config.json, в блок клиента:')
        for code, table in overrides.items():
            print('  "%s": "mode_overrides": %s'
                  % (code, json.dumps(table, ensure_ascii=False, indent=2)))


if __name__ == '__main__':
    main()
