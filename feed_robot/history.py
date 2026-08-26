# -*- coding: utf-8 -*-
"""Change history for client feeds, stored in PostgreSQL.

The daily run writes one row per change — a programme appeared, disappeared or
changed price. Reports in the bucket are per-run snapshots; this table is what
answers «when did the client raise the price» and can be joined with the Direct
statistics that already live in the same database.

Connection settings follow the existing ETL convention: POSTGRES_HOST_<CLIENT>
falling back to POSTGRES_HOST, and a per-client schema.
"""
import os

DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.feed_changes (
    id          BIGSERIAL PRIMARY KEY,
    changed_at  DATE        NOT NULL,
    client      TEXT        NOT NULL,
    offer_id    TEXT        NOT NULL,
    event       TEXT        NOT NULL,
    name        TEXT,
    url         TEXT,
    old_price   INTEGER,
    new_price   INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A re-run on the same day must not duplicate rows.
CREATE UNIQUE INDEX IF NOT EXISTS feed_changes_uniq
    ON {schema}.feed_changes (changed_at, client, offer_id, event);

CREATE INDEX IF NOT EXISTS feed_changes_event_idx
    ON {schema}.feed_changes (client, event, changed_at DESC);
"""

INSERT = """
INSERT INTO {schema}.feed_changes
    (changed_at, client, offer_id, event, name, url, old_price, new_price)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (changed_at, client, offer_id, event) DO UPDATE
SET name = EXCLUDED.name,
    url = EXCLUDED.url,
    old_price = EXCLUDED.old_price,
    new_price = EXCLUDED.new_price
"""


def _param(client_code, name, default=None):
    if client_code:
        for suffix in (client_code.upper(), client_code.lower()):
            value = os.environ.get('%s_%s' % (name, suffix))
            if value:
                return value
    return os.environ.get(name, default)


def configured(client_code):
    return bool(_param(client_code, 'POSTGRES_HOST'))


def connect(client_code):
    import psycopg2
    args = {
        'host': _param(client_code, 'POSTGRES_HOST'),
        'port': _param(client_code, 'POSTGRES_PORT', '5432'),
        'dbname': _param(client_code, 'POSTGRES_DATABASE'),
        'user': _param(client_code, 'POSTGRES_USER'),
        'password': _param(client_code, 'POSTGRES_PASSWORD'),
        'connect_timeout': 20,
    }
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, 'cloud-ca.crt'), 'cloud-ca.crt'):
        if os.path.exists(candidate):
            args.update({'sslmode': 'verify-full', 'sslrootcert': candidate})
            break
    return psycopg2.connect(**args)


def record(client_code, today, diff):
    """Write the day's diff. Never raises — the feed is already published."""
    if not configured(client_code):
        print('[history] postgres не настроен, пропускаем')
        return 0

    rows = []
    for c in diff.get('price_changes', []):
        rows.append((today, client_code, c['id'], 'price', c.get('name'),
                     c.get('url'), c.get('old'), c.get('new')))
    for a in diff.get('added', []):
        rows.append((today, client_code, a['id'], 'added', a.get('name'),
                     a.get('url'), None, a.get('price')))
    for r in diff.get('removed', []):
        rows.append((today, client_code, r['id'], 'removed', r.get('name'),
                     r.get('url'), r.get('price'), None))
    if not rows:
        return 0

    schema = client_code
    try:
        conn = connect(client_code)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(DDL.format(schema=schema))
                cur.executemany(INSERT.format(schema=schema), rows)
        finally:
            conn.close()
        print('[history] записано изменений: %d' % len(rows))
        return len(rows)
    except Exception as exc:
        print('[history] не записали: %s' % str(exc)[:200])
        return 0


def fetch(client_code, since=None, until=None, limit=5000):
    """Read the history back for reports."""
    where = ['client = %s']
    params = [client_code]
    if since:
        where.append('changed_at >= %s')
        params.append(since)
    if until:
        where.append('changed_at <= %s')
        params.append(until)
    sql = ("SELECT changed_at, offer_id, event, name, url, old_price, new_price "
           "FROM {schema}.feed_changes WHERE {where} "
           "ORDER BY changed_at DESC, event, offer_id LIMIT %s").format(
        schema=client_code, where=' AND '.join(where))
    params.append(limit)
    conn = connect(client_code)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()
