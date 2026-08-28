# -*- coding: utf-8 -*-
"""Model-as-judge over an evaluation run — the checks a regex cannot make.

Whether the line reads as Russian, whether it still describes this programme
and not a neighbouring one, whether it sounds like an ad or like a database
row. Deliberately not wired into the daily job: it would double the cost of
every offer and add a second unreliable model to a path that has to be
predictable. It runs when the prompt or the writing model changes.

Two modes:

    judge.py --run eval/runs/<file>.json
        scores one run and lists the offers a human should look at

    judge.py --run <new>.json --against <old>.json
        for every offer whose copy differs, asks which version is better —
        that is the question a prompt change actually needs answered

The judge is a different model family from the writer on purpose: asked to
grade its own style, a model grades it generously.
"""
import os
import re
import sys
import json
import random
import argparse
from collections import Counter

BUILDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BUILDER)

import llm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(BUILDER, '..', '..', '..'))
REFERENCE = os.path.join(HERE, 'reference_set.json')

DEFAULT_JUDGE = 'qwen/qwen3.7-flash'

# Without this the judge marks every trimmed title down for missing the opening
# and the ending, which are exactly what the assembly gives up on purpose.
HOW_IT_WORKS = """Как устроено объявление, чтобы ты не снижал оценку за то, что задумано:

- Заголовок собирается автоматически. Если название профессии или темы длинное,
  приставка «Обучение на» и концовка «. Диплом!» намеренно убираются, чтобы
  уместился смысл. Их отсутствие — не недостаток.
- Цена подставляется кодом на каждой сборке. За её формат не снижай.
- Заголовок не длиннее 56 символов, текст — 81. Это лимиты площадки.
- Объявление может называть либо профессию, которую получит выпускник
  («Обучение на Бухгалтера»), либо тему программы («Обучение: Бухгалтерский
  учет в НКО»). Оба варианта задуманы и допустимы. Дословное совпадение с
  названием курса в каталоге само по себе не достоинство: человек ищет работу
  или навык, а не строку из каталога. Не выбирай вариант только за то, что он
  ближе к названию программы."""

SCORE_SYSTEM = """Ты — редактор рекламы учебного центра. Оцениваешь готовые объявления.

%s

Оцени объявление по трём критериям, каждый — целое число от 1 до 3:

grammar — русский язык, падежи, пунктуация.
  3 — безупречно. 2 — есть шероховатость. 1 — грамматическая ошибка.
meaning — объявление описывает именно эту программу.
  3 — точно. 2 — обобщено, но не врёт. 1 — названа другая профессия или предмет.
style — читается как объявление, а не как строка из базы.
  3 — живо. 2 — сухо, но приемлемо. 1 — набор слов.

Ответ — только JSON:
{"grammar": 3, "meaning": 3, "style": 2, "comment": ""}

comment — одна короткая фраза по-русски, и только если что-то не так.
Если всё хорошо, оставь пустую строку.""" % HOW_IT_WORKS

PAIR_SYSTEM = """Ты — редактор рекламы учебного центра. Сравниваешь два варианта
объявления для одной и той же программы.

%s

Выбери вариант, который точнее передаёт суть программы и лучше читается.
Точность смысла важнее красоты формулировки.

Ответ — только JSON:
{"winner": "А", "reason": "почему"}

winner — «А», «Б» или «равно». reason — одна короткая фраза по-русски.""" % HOW_IT_WORKS


def parse_json(answer):
    body = re.sub(r'^```[a-z]*\s*|\s*```$', '', (answer or '').strip(), flags=re.S)
    m = re.search(r'\{.*\}', body, re.S)
    return json.loads(m.group(0) if m else body)


def load_run(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_reference(path):
    with open(path, encoding='utf-8') as f:
        return {(r['client'], r['id']): r for r in json.load(f)}


def describe(row, reference):
    """The programme as the site names it — the ground truth for the judge."""
    ref = reference.get((row['client'], row['id']), {})
    lines = ['Название программы на сайте: %s' % (ref.get('listing_name') or '—')]
    if row.get('profession'):
        lines.append('Профессия, извлечённая со страницы: %s' % row['profession'])
    return '\n'.join(lines)


def score_one(client, row, reference):
    user = ('%s\n\nОБЪЯВЛЕНИЕ\nЗаголовок: %s\nТекст: %s'
            % (describe(row, reference), row['title'], row['text']))
    answer = client.chat([{'role': 'system', 'content': SCORE_SYSTEM},
                          {'role': 'user', 'content': user}], temperature=0)
    data = parse_json(answer)
    return {k: max(1, min(3, int(data.get(k, 0) or 0)))
            for k in ('grammar', 'meaning', 'style')}, str(data.get('comment') or '').strip()


def compare_one(client, row, other, reference, rng):
    """Positions are shuffled per offer: a judge shown the same order every time
    develops a preference for one of the slots rather than for the copy."""
    flipped = rng.random() < 0.5
    first, second = (other, row) if flipped else (row, other)
    user = ('%s\n\nВАРИАНТ А\nЗаголовок: %s\nТекст: %s\n\nВАРИАНТ Б\nЗаголовок: %s\nТекст: %s'
            % (describe(row, reference), first['title'], first['text'],
               second['title'], second['text']))
    answer = client.chat([{'role': 'system', 'content': PAIR_SYSTEM},
                          {'role': 'user', 'content': user}], temperature=0)
    data = parse_json(answer)
    winner = str(data.get('winner') or '').strip().upper()[:1]
    if winner not in ('А', 'A', 'Б', 'B'):
        return 'равно', str(data.get('reason') or '').strip()
    picked_first = winner in ('А', 'A')
    # Un-shuffle: report in terms of the run being judged, not the slot.
    new_wins = picked_first != flipped
    return ('новый' if new_wins else 'старый'), str(data.get('reason') or '').strip()


def run_scoring(client, rows, reference):
    totals, weak = Counter(), []
    for row in rows:
        try:
            scores, comment = score_one(client, row, reference)
        except Exception as exc:
            print('  [x] %s: %s' % (row['id'], str(exc)[:120]))
            continue
        for key, value in scores.items():
            totals[key] += value
            totals[key + '_n'] += 1
        worst = min(scores.values())
        if worst <= 2:
            weak.append((row, scores, comment))
    return totals, weak


def report_scoring(totals, weak, total, client):
    print('\nоценено программ: %d' % total)
    for key, label in (('grammar', 'язык'), ('meaning', 'смысл'), ('style', 'стиль')):
        n = totals[key + '_n']
        if n:
            print('  %-6s %.2f из 3' % (label, totals[key] / float(n)))
    print('\nтребуют внимания: %d' % len(weak))
    for row, scores, comment in weak:
        print('\n  %s %s' % (row['client'], row['url'][:66]))
        print('    %s' % row['title'])
        print('    %s' % row['text'])
        print('    язык %d, смысл %d, стиль %d — %s'
              % (scores['grammar'], scores['meaning'], scores['style'], comment or '—'))
    print('\nвызовов: %d | потрачено $%.5f' % (client.calls, client.spent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, help='evaluation run to judge')
    ap.add_argument('--against', help='earlier run — switches to pairwise comparison')
    ap.add_argument('--reference', default=REFERENCE)
    ap.add_argument('--model', default=DEFAULT_JUDGE)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--min-balance', type=float)
    ap.add_argument('--out')
    args = ap.parse_args()

    llm.load_environment()

    reference = load_reference(args.reference)
    rows = load_run(args.run)['results']
    if args.limit:
        rows = rows[:args.limit]

    cfg = {'text_generation': {'model': args.model, 'temperature': 0,
                               'max_spend_usd': 0.10,
                               'min_balance_usd': (args.min_balance
                                                   if args.min_balance is not None else 0.05)}}
    client, reason = llm.open_client(cfg)
    if not client:
        print('судья не запущен: %s' % reason)
        return
    print('судья: %s | программ: %d' % (client.model, len(rows)))

    if args.against:
        older = {(r['client'], r['id']): r for r in load_run(args.against)['results']}
        changed = [r for r in rows
                   if (r['client'], r['id']) in older
                   and older[(r['client'], r['id'])]['title'] != r['title']]
        print('различаются заголовки у %d программ\n' % len(changed))
        rng = random.Random(7)
        verdicts, notes = Counter(), []
        for row in changed:
            other = older[(row['client'], row['id'])]
            try:
                winner, reason_text = compare_one(client, row, other, reference, rng)
            except Exception as exc:
                print('  [x] %s: %s' % (row['id'], str(exc)[:120]))
                continue
            verdicts[winner] += 1
            notes.append(dict(client=row['client'], id=row['id'], url=row['url'],
                              old=other['title'], new=row['title'],
                              winner=winner, reason=reason_text))
            print('  %s  %s' % (winner.upper(), row['url'][:64]))
            print('    старый: %s' % other['title'])
            print('    новый : %s' % row['title'])
            print('    %s' % reason_text)
        print('\nновый лучше: %d | старый лучше: %d | равно: %d'
              % (verdicts['новый'], verdicts['старый'], verdicts['равно']))
        print('вызовов: %d | потрачено $%.5f' % (client.calls, client.spent))
        payload = dict(mode='pairwise', judge=client.model,
                       verdicts=dict(verdicts), notes=notes)
    else:
        totals, weak = run_scoring(client, rows, reference)
        report_scoring(totals, weak, len(rows), client)
        payload = dict(mode='scoring', judge=client.model, totals=dict(totals),
                       weak=[dict(id=r['id'], client=r['client'], url=r['url'],
                                  title=r['title'], text=r['text'],
                                  scores=s, comment=c) for r, s, c in weak])

    out = args.out or os.path.join(
        HERE, 'judgements',
        '%s_%s' % (payload['mode'], os.path.basename(args.run)))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    payload['spent'] = round(client.spent, 5)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print('вердикт: %s' % out)


if __name__ == '__main__':
    main()
