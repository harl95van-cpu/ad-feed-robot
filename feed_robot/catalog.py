# -*- coding: utf-8 -*-
"""Client programme catalogue, published to PostgreSQL by the daily feed robot.

The crawler already knows every programme on the client's site — id, url, name,
price, hours, type — so the same run publishes it as a table the analytics can
join to. Leads carry the landing page of the form (bitrix_leads.landing_path),
and `url_path` here is normalised exactly the same way, so «which programme did
this lead come for» becomes a join instead of a manual mapping.

The whole catalogue is published, not just what enters the feed: BRANDNAME
advertises retraining only, but leads arrive on refresher and mini-course pages
too, and those still need a programme name.

Connection settings follow the ETL convention: POSTGRES_HOST_<CLIENT> falling
back to POSTGRES_HOST, one schema per client.
"""

from history import connect, configured  # same credentials and SSL handling

DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.programs (
    url_path    TEXT        PRIMARY KEY,
    program_id  TEXT        NOT NULL,
    client      TEXT        NOT NULL,
    name        TEXT,
    url         TEXT,
    price       INTEGER,
    oldprice    INTEGER,
    hours       INTEGER,
    kind        TEXT,
    category_id TEXT,
    sections    TEXT,
    in_feed     BOOLEAN     NOT NULL DEFAULT FALSE,
    first_seen  DATE        NOT NULL,
    last_seen   DATE        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS programs_program_id_idx ON {schema}.programs (program_id);
CREATE INDEX IF NOT EXISTS programs_last_seen_idx  ON {schema}.programs (last_seen DESC);
"""

INSERT = """
INSERT INTO {schema}.programs
    (url_path, program_id, client, name, url, price, oldprice, hours, kind,
     category_id, sections, in_feed, first_seen, last_seen)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (url_path) DO UPDATE
SET program_id  = EXCLUDED.program_id,
    name        = EXCLUDED.name,
    url         = EXCLUDED.url,
    price       = EXCLUDED.price,
    oldprice    = EXCLUDED.oldprice,
    hours       = EXCLUDED.hours,
    kind        = EXCLUDED.kind,
    category_id = EXCLUDED.category_id,
    sections    = EXCLUDED.sections,
    in_feed     = EXCLUDED.in_feed,
    last_seen   = EXCLUDED.last_seen,
    updated_at  = now()
"""


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_rows(client_code, today, programs, pages, offers, cfg):
    """One row per programme found on the site."""
    import facts
    import feed as feed_builder

    in_feed = {o.get('key') for o in offers if o.get('key')}
    base = cfg['base_url']
    rows = []
    for key, program in programs.items():
        page = pages.get(key, {})
        known = facts.extract(page, program, cfg)
        rows.append((
            key,
            str(program['id']),
            client_code,
            program.get('name'),
            base + key,
            _int(program.get('price')),
            _int(program.get('oldprice')),
            _int(known['hours']),
            known['kind'],
            feed_builder.category_of(program, cfg),
            ','.join(program.get('sections', [])),
            key in in_feed,
            today,
            today,
        ))
    return rows


def record(client_code, today, programs, pages, offers, cfg):
    """Publish the catalogue. Never raises — the feed is already live."""
    if not configured(client_code):
        print('[catalog] postgres не настроен, пропускаем')
        return 0

    rows = build_rows(client_code, today, programs, pages, offers, cfg)
    if not rows:
        return 0
    try:
        conn = connect(client_code)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(DDL.format(schema=client_code))
                cur.executemany(INSERT.format(schema=client_code), rows)
        finally:
            conn.close()
        print('[catalog] опубликовано программ: %d' % len(rows))
        return len(rows)
    except Exception as exc:
        print('[catalog] не записали: %s' % str(exc)[:200])
        return 0
