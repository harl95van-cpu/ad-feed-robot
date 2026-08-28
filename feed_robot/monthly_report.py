# -*- coding: utf-8 -*-
"""Monthly summary of feed changes, built from the history table.

    venv\\Scripts\\python.exe Scripts\\feeds\\feed_builder\\monthly_report.py \\
        --client second --month 2026-08

Without --month it summarises the previous calendar month. The daily job calls
render() on the first of the month and drops a copy into the bucket.
"""
import os
import sys
import argparse
import calendar
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history


def month_bounds(year_month):
    year, month = (int(x) for x in year_month.split('-'))
    last = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last)


def previous_month(today=None):
    today = today or datetime.date.today()
    first = today.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return '%04d-%02d' % (prev.year, prev.month)


def _rub(n):
    return '{:,}'.format(int(n)).replace(',', ' ') if n is not None else '—'


def render(client_code, year_month, rows):
    """rows: (changed_at, offer_id, event, name, url, old_price, new_price)"""
    up, down, added, removed = [], [], [], []
    for changed_at, oid, event, name, url, old, new in rows:
        if event == 'price':
            (up if (new or 0) > (old or 0) else down).append((changed_at, oid, name, url, old, new))
        elif event == 'added':
            added.append((changed_at, oid, name, url, new))
        elif event == 'removed':
            removed.append((changed_at, oid, name, url, old))

    def price_table(items):
        head = '| Дата | ID | Программа | Было | Стало | Δ |\n|---|---|---|---|---|---|\n'
        body = '\n'.join(
            '| %s | %s | [%s](%s) | %s | %s | %+d%% |'
            % (d.strftime('%d.%m'), oid, (name or '')[:60], url or '',
               _rub(old), _rub(new),
               round((new - old) / old * 100) if old else 0)
            for d, oid, name, url, old, new in items)
        return head + body if items else '_нет_'

    def simple_table(items, price_header):
        head = '| Дата | ID | Программа | %s |\n|---|---|---|---|\n' % price_header
        body = '\n'.join(
            '| %s | %s | [%s](%s) | %s |'
            % (d.strftime('%d.%m'), oid, (name or '')[:60], url or '', _rub(price))
            for d, oid, name, url, price in items)
        return head + body if items else '_нет_'

    total = len(rows)
    return """# Изменения в фиде: %(client)s, %(month)s

**Всего изменений за месяц: %(total)d** — подорожало %(up)d, подешевело %(down)d, добавилось %(added)d, пропало %(removed)d.

Источник — таблица `%(client)s.feed_changes`, её заполняет ежедневный робот.

## Подорожало

%(up_table)s

## Подешевело

%(down_table)s

## Появилось на сайте

%(added_table)s

## Пропало с сайта

%(removed_table)s
""" % dict(client=client_code, month=year_month, total=total,
           up=len(up), down=len(down), added=len(added), removed=len(removed),
           up_table=price_table(up), down_table=price_table(down),
           added_table=simple_table(added, 'Цена'),
           removed_table=simple_table(removed, 'Последняя цена'))


def build(client_code, year_month):
    since, until = month_bounds(year_month)
    rows = history.fetch(client_code, since=since, until=until)
    return render(client_code, year_month, rows), len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True)
    parser.add_argument('--month', help='YYYY-MM, по умолчанию прошлый месяц')
    parser.add_argument('--out', help='куда положить markdown')
    args = parser.parse_args()

    from dotenv import load_dotenv
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    load_dotenv(os.path.join(root, 'Credentials.env'))

    month = args.month or previous_month()
    md, count = build(args.client, month)
    out = args.out or os.path.join(root, 'Clients', args.client, 'feed_changes',
                                   '%s.md' % month)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(md)
    print('изменений за %s: %d' % (month, count))
    print('отчёт: %s' % out)


if __name__ == '__main__':
    main()
