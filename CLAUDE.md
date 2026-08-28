# Working on this repository

This is a product feed robot for **Yandex Direct**, built for **online
education**. It runs unattended once a day against live ad accounts. Read this
before changing anything: most of the code that looks redundant is a guard, and
each one is here because something went wrong once.

Google Ads feeds are a different format with different rules. This code does not
target them, and making it do so is a rewrite, not a flag.

## The decisions, and why

An agent that does not know the reasons will remove these as clutter.

**The run stops instead of publishing a short catalogue.** If the crawl returns
fewer offers than `min_offers_guard`, the site is broken, not the catalogue.
Publishing what came back would delete most of the advertiser's dynamic ads and
the recovery is not automatic. Yesterday's feed stays live and a human is told.

**A programme that vanished stays in the feed for one cycle as
`available=false`.** Dropping it outright makes the platform error on an offer
it still references; marking it unavailable makes the platform retire the ads
cleanly.

**Copy is written once, for new programmes only.** Rewriting the text of a live
offer resets the statistics the platform has accumulated on it, which costs far
more than the model call it saves. `feed._copy_for()` encodes the order: a
cached entry is reassembled, an offer that already has copy is left alone, only
a genuinely new one costs a call. There is exactly one exception — copy that is
already broken (over the length limit, or carrying the debris listed under
`texts.ARTEFACTS`) is rebuilt, because a spoiled ad is worth less than the
statistics.

**That exception must not fight the deduplication pass.** Two identical titles
are told apart by appending the hours, which trades away the ending and leaves
the stored name one character shorter than the rules produce. Without the guard
in `_copy_for`, the repair and the dedupe undo each other every run and those
offers are rewritten daily. If you touch either, verify by running twice and
checking that `reshaped` is zero the second time.

**The price is substituted on every build; the model never writes a figure.**
The price in the ad has to match the landing page, so it must be fresh — and if
the model wrote it into the copy, every price change would trigger a rewrite and
the reset above. The duration is frozen into the cached entry for the same
reason, in reverse: it changes rarely and should not move the copy when it does.

**Length limits are 56 and 75, not the feed format's 100 and 85.** The platform
applies its own limits when it renders the ad. 56 is the search-ad title limit;
75 comes from a live banner that clamped a 79-character description to two lines
and cut it after 76. These are display limits, not format limits, and raising
them to what the XML allows puts an ellipsis in the middle of live ads.

**The name is never shortened to make the line fit.** `texts.title_options()`
and `text_options()` list wordings from the most decorated to the barest, and
`_fit` takes the first that fits. Decoration goes; meaning does not. A title
that says exactly what the course is beats a well-formed one that says something
else — that is the whole point of the ladder, and "just truncate the name"
undoes it.

**Banned phrases are checked after generation even though the prompt forbids
them.** The prompt lowers the odds; the check gives the guarantee. Across
thousands of programmes, one percent of misses is dozens of live ads carrying a
claim the advertiser is not allowed to make.

**Facts come from the config and from nowhere else.** `facts.extract()` is the
only extractor. There used to be a second copy of the same logic in `feed.py`,
and they could disagree — which mattered because the programme kind decides
which programmes enter the feed at all. A config edited to fit a new site would
appear to work in the extraction check while the robot kept the old behaviour.
Do not reintroduce a shortcut that reads a fact directly from the page.

**The rule that matched is recorded, not just the field.** `sources` says
`qualification` or `heuristic`, and the prompt trusts them differently: a
qualification the page states outright is not second-guessed, a label scraped
out of a page title is. Collapsing that back to a field name makes the copy
either credulous or skittish.

**Reports and model calls go through a relay.** The cloud region this runs in
reaches neither `api.telegram.org` nor `openrouter.ai`; the latter answers 403
to the whole network. `relay/` is one file per endpoint. The relay holds the
model API key, so the job is deployed without one — do not "simplify" this by
putting the key back into the function's environment.

**Modules import each other by bare name.** The package is zipped flat into a
cloud function. Turning it into a proper package with relative imports breaks
the deployment.

**Campaign statistics do not decide wording; search demand does.** Comparing ad
performance at this granularity is not data anyone has. `eval/wordstat_compare.py`
compares whole commercial phrases — «обучение на логопеда» against «обучение
логопедии» — and writes the verdict into `mode_overrides` in the config. The
daily run never calls Wordstat, so two identical runs stay identical.

**The judge is not in the daily job.** It would double the cost of every offer
and add a second unreliable model to a path that has to be predictable. It also
has a measurable bias: told nothing about what the assembly does on purpose, it
marked down every trimmed title and preferred whichever version was closer to
the catalogue name. Adding one paragraph of context to its prompt flipped its
verdict on the same nine pairs. Treat it as a signal.

## What you need to run it

- **Object storage, S3-compatible.** Required. The feed must live at a stable
  public URL — that URL is what goes into the ad account — and the run state
  must survive between runs. Without the state every run thinks every programme
  is new.
- **A model API key.** Required for generated copy and creative. Without it the
  run still builds a feed; new programmes just get the deterministic copy.
- **PostgreSQL.** Optional. Without it you lose the price history and the join
  between leads and programmes; the feed is still built and published.
- **Telegram.** Optional. Without it the run is silent.

## Adapting it to another site

In this order:

1. **`feed_robot/clients_config.example.json`** — start here. Catalogue
   sections, category reference list, the minimum-offers floor, banned phrases.
2. **`crawler.py`, the listing profiles.** The parsers are written against
   specific markup. A new site needs a new profile; `listing_profile` picks it.
3. **The `facts` block in the config.** Every site hides the duration, the hours
   and the qualification somewhere different — verified across three. A rule is
   a source, a pattern, an optional numeric range and an optional `reject` guard
   for the wording that invalidates a match. The guard exists because a page
   that states the duration also states an instalment plan, a payment schedule
   and an access period, all measured in months.
4. **`texts.py` — the prompt and the wording.** «Обучение на» and «Диплом!» make
   sense for education and none for a garage. The endings in `TOPIC_ENDINGS` and
   `FIELD_ENDINGS` are Russian morphology; another language needs its own or
   none.
5. **`feed.py` — `validate` and the limits.** The rules of your ad platform.

## How the model request is built

Read `texts.build_messages()`. What matters:

- Extracted facts go in as separate labelled fields, never the raw page.
- The model returns a name and its accusative — not a finished line.
- The character budget is computed by code and handed over as a number.
- Which template to use is decided by code and stated, not left open.
- The answer is checked against the facts before anything uses it.

For another domain the facts, the templates and the checks all change together.
Changing one of the three is usually a bug.

## Where things live, and what can be swapped

| Thing | Where | Replaceable |
| --- | --- | --- |
| Published feed | Object storage, public URL | Any S3-compatible store. The URL must not change |
| State between runs | JSON in the same bucket | Anything durable. Holds the copy cache |
| History and catalogue | PostgreSQL, schema per client | Optional |
| Schedule | Cloud function timer | cron, Airflow, CI — the code runs as a script too |
| Reports | Telegram via relay | Optional; direct API works where reachable |
| Model access | OpenRouter, direct or via relay | Another provider means editing `llm.py` |

Configurable without touching code: the text model, the image model, the
prompts' inputs, the spend ceiling per run, the retry count, the document each
programme type issues, and the per-programme wording overrides.

## Do not

- Remove a guard because it looks like a redundant check.
- Publish a feed that failed validation.
- Commit `clients_config.json`, `.env`, or anything under `eval/` that holds
  real catalogue data.
- Move logic out of the config into the code.
- Rewrite the copy of existing offers without a reason that outweighs losing
  their statistics.
- Put the model API key into the cloud function.

## Before you commit

Run `pytest`. The suite is fast and deliberately covers the expensive failures.

If you changed a regular expression, print the compiled pattern and confirm it
is what you meant. Much of this repository is regular expressions, and a pattern
that silently never matches looks exactly like a check that always passes — two
of them shipped that way and were only found by reading the compiled output.

If you changed anything that touches existing offers, run the build twice
against the same input and confirm the second run changes nothing. A repair that
does not converge rewrites live ads every morning.
