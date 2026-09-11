# v1.2.13 pre-tag checklist

Scope: the **in-place top-up**, and the kit v3 it delivers. Closes the reach
limit v1.2.12 documented rather than fixed — a superseded holder's tables
resolve through the `dataset.yaml` in their OLD version directory, so a fresh
download into a new directory leaves them training against the old kit forever
and they never naturally re-import. Writing into the directory they already
read is the only update that reaches them. Rules: RELEASING.md order (tag →
repo `catalog.json` → gist mirror), never retag, `pytest` last thing before
tagging.

**Epistemic status:** the top-up is verified by execution on real kits, not by
reading — both upgrade paths ran end to end on this machine through the actual
UI, against genuine pre-v1.2.13 job records, and the resulting trees were
checked file-by-file against the published v3 manifest. The one branch NOT
exercised live is the `dataset.yaml` refusal, which is structurally
unreachable from v2→v3 (that upgrade changes `README.md` alone); it is covered
by a synthetic kit built to trip it, and that test also asserts the "kit on
disk is unchanged" claim rather than taking it on trust.

## The ordering gate, and that it was honoured

> **The v3 CDN prefix was live in prod and independently verified BEFORE the
> commit that moved `STARTER_KIT_VERSION`.** `constants.starter_kit_prefix()`
> has no fallback and `downloader.fetch_manifest` fails the job on a 404, so
> the reverse order hard-fails the Import tab's Download section for every
> participant, on a version they cannot roll back from without reinstalling.

Verified 2026-09-11 by Rishikesh against the prod prefix, and every published
fact matched the local build exactly:

| | Prod | Local build |
|---|---|---|
| `manifest.json` bytes | 2,848,920 | 2,848,920 |
| `manifest.json` sha256 | `9ccdb9b98b8c4ef4…` | `9ccdb9b98b8c4ef4…` |
| `kit_version` | v3 | v3 |
| `file_count` | 14,005 | 14,005 |
| `total_bytes` | 623,653,032 | 623,653,032 |
| `part-09-root-labels.zip` sha256 | `6c4852a5…` | `6c4852a5…` |

Prefix also answers `Accept-Ranges: bytes` and returns 206 on a ranged GET,
which is what the resume path needs.

## Kit v3 build

- `package_build/starter_kit/` regenerated from `starter_kit/` (the source of
  truth); all four root files assert equal to source afterwards.
- Built with `scripts/make_kit_manifest.py` **unmodified**, on Windows, the way
  v1 and v2 were built — preserving the `part-09` `rglob` sort documented in
  `WEEK_2026-09-01.md:511`. Normalising it would change `part-09`'s hash for
  every version including v1 and invalidate both committed anchors; it is its
  own task on some future kit, never a rider on this one.
- Staged into a scratch directory and moved into `package_build/cdn/v3/` only
  **after** verification, so the hashes that ship are the hashes that were
  checked. Re-verified after the move: all 11 objects hash-identical to their
  staged form.
- Against `cdn/v2/manifest.json`: 10 shards, all ten names unchanged, the **9
  image shards byte-identical by sha256**, `part-09-root-labels.zip` alone
  differing (1,498,578 → 1,498,951 B, 6,647 files unchanged). File-level delta
  0 missing / 0 extra / **1 changed** — `starter_kit/README.md`, 6,547 →
  7,514 B. `total_bytes` moves by exactly the 967 B the README grew.
- `check_kit_parity.py` against the shipped manifest: **RESULT PARITY**,
  14,005 matched, 0 size / 0 sha / 0 missing / 0 extra.
- Staging cost: **2 uploads + 9 server-side copies**, because the image shards
  are byte-identical to v2's.

Kit content is `../competition_exdark@5cdd48e`; the README sweep that forced
the bump is `@68e19bd`.

## Verified at review (2026-09-11, dev machine)

**Both upgrade paths ran live, through the UI, on real records.** n-1 and n-2
were tested because they are different code paths through `kit_dir_of`: the
n-2 record predates `kit_dir` entirely and exercises the `dest/<version>`
compatibility fallback, while the n-1 record is the ordinary case.

| Path | Record | Result | Files written | Fetched |
|---|---|---|---|---|
| **n-2** v1 → v3 | `3e3fd034…`, completed 2026-08-31, **no `kit_dir` fact** | `updated=True`, `kit_dir=…\v1` | 3 (`README.md`, `LICENSE-ExDark.txt`, `dataset.yaml`) | `part-09` only, 1,498,951 B |
| **n-1** v2 → v3 | `5aa59090…`, completed 2026-09-11, **no `kit_dir` fact** | `updated=True`, `kit_dir=…\v2` | 1 (`README.md`) | `part-09` only, 1,498,951 B |

**Identical resulting trees**, which is the claim that matters — an in-place
top-up must land the same bytes as a fresh download, from either starting
point. `check_kit_parity.py --manifest kit/exdark-low-light/v3/manifest.json`
against **each** directory:

```
v1 directory:  RESULT: PARITY   14005 matched, 0/0/0/0
v2 directory:  RESULT: PARITY   14005 matched, 0/0/0/0
```

Both trees are byte-identical to the published v3 kit across all 14,005 files,
and both now carry a `manifest.json` reading `kit_version: v3`. The
directories keep their old names (`…\v1`, `…\v2`) holding v3 content — which
is the whole reason `kit_dir` had to become a recorded fact.

Also verified at review:

- **The `dataset.yaml` comparison ran live on the n-2 path and allowed it.**
  v1's `dataset.yaml` (508 B) and v3's (666 B) differ as files but agree on
  all six load-bearing keys (`path`, `train`, `val`, `test`, `nc`, `names`), so
  the top-up proceeded. That is exactly why the gate compares PARSED keys and
  not the file hash: a hash check would have falsely refused every v1 holder
  over a comment rewrite.
- **The v3 record restamps correctly**: `facts.kit_version=v3`,
  `facts.kit_dir` populated with the real directory, and `download_state`
  reads `success` from it.
- **Disk-only `download_state` for a pre-v1.2.13 record**, read from a fresh
  process: `superseded`, `kit_version=v2`, `current_version=v3`,
  `kit_dir=dest/v2` **derived, not recorded**, directory and `dataset.yaml`
  both present. The compatibility branch is healthy on a real record.
- **227 tests pass.** New: `tests/test_ui_node_lifetime.py` (4), and 10 top-up
  cases in `test_downloader.py`.
- **Mutation-checked**, not just green: reintroducing the `innerHTML`
  assignment that caused the offer bug fails
  `test_the_offer_blurbs_are_toggled_never_rewritten`.
- `node --check` passes on the fragment; the `validate → run` hop preserves
  `mode` (without it the button would silently start a fresh download).

## The bug found and fixed during review

The top-up offer's first live click did nothing and cleared its own callout.
Not caching and not a lost binding: `dlShowOffer`'s top-up branch set the
innerHTML of the block **containing** `#kg-dl-dest`, deleting that node, and
`dlStart` dereferences it on every click — after it has already set
`dlRunning = true` and cleared the banner. So one click cleared the callout,
threw before `kgStartJob` (no `POST /run`), and latched `dlRunning` so every
later click returned at the guard in silence.

Fixed by making the two blurbs permanent and toggling `hidden`; `dlStart` now
skips the dest read entirely for a top-up (the U1 gate-idling exists because a
download MOVES the kit — a top-up does not, so idling a green gate there would
have been wrong even with the node present). `tests/test_ui_node_lifetime.py`
pins the structure rather than the instance.

## Open pre-tag items

- [ ] **`pytest` immediately before the tag** (RELEASING.md). Green at
      2026-09-11 19:49 on 227 tests; re-run if anything lands after.
- [ ] **Reduced-motion parity** on the top-up offer (ui-notes §2). It renders
      through `dlShowOffer(false, false, 'top_up')` with `animate` false, so
      there should be nothing to gate — confirm rather than assume.
- [ ] **`?kgdev=dl-superseded` fixture** now shows the v2 → v3 pair and the
      **Update the starter kit** CTA. Eyeball it in participant view; fixtures
      always render participant view (ui-notes).

## Post-tag verification

- [ ] Footer reads **1.2.13** after a catalog install (RELEASING.md §4).
- [ ] **Gist mirror — OWED, NOT DONE.** RELEASING.md: the repo `catalog.json`
      is the source of truth and the gist only mirrors it; Rishikesh mirrors
      it, never Claude. Do it with
      `gh gist edit <id> -f catalog.json <path-to-repo-catalog.json>` so the
      repo file is pasted **verbatim** — a hand-paste once introduced a
      duplicate-key error. Then, after the CDN lag (a few minutes), fetch the
      raw URL in an incognito window and confirm the served bytes are
      **identical** to the repo file, not merely that the 1.2.13 entry is
      present.
- [ ] A real catalog install on a host that had 1.2.12, confirming the
      superseded callout offers the top-up and that it lands v3 in the
      existing directory.
