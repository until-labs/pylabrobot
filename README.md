# PyLabRobot — until-labs internal fork

Internal fork of [PyLabRobot](https://github.com/pylabrobot/pylabrobot), maintained by Until Labs.

- **Upstream docs:** https://docs.pylabrobot.org
- **Upstream repo:** https://github.com/pylabrobot/pylabrobot

> PyLabRobot is a hardware-agnostic, pure-Python interface for liquid-handling robots,
> plate readers, pumps, scales, heater-shakers, centrifuges, thermocyclers, and other lab
> automation hardware.

---

## Installation

Releases are published to the until-labs **pyx** index.

**From pyx (preferred).** Configure `uv` to use the until-labs pyx index (token-based auth),
then:

```bash
uv pip install pylabrobot
```

**One off** Requires access to the repo:

```bash
uv pip install "git+ssh://git@github.com/until-labs/pylabrobot.git@v0.1.7.dev15"
```

Replace the tag with the version you want (see the repo's tags).

---

## Releasing a new version

This is what differs most from upstream. **The published version is driven by the git tag,
and the committed version file must match it — CI enforces this and never rewrites it.**

### Source of truth

- The version lives in **`pylabrobot/__version__.py`** (`pyproject.toml` has no version field;
  `setup.py` reads `__version__.py`).
- A release tag `vX.Y.Z` must point at a commit whose `__version__.py` already says `X.Y.Z`.
- `publish.yml` **verifies** this and refuses to publish on a mismatch. (It used to overwrite
  the file at build time — it no longer does, so the committed version is now honest and what
  source/`pip` installs report is correct.)

### Cut a release with `just`

From the branch you release from (currently **`arvind-dev`**), with a clean working tree and
up to date with origin:

```bash
just tagnewversion v0.1.7.dev16
```

This:

1. bumps `pylabrobot/__version__.py` to `0.1.7.dev16` and commits it (`Release v0.1.7.dev16`),
2. fast-forwards `publish` to that commit,
3. atomically pushes the branch, `publish`, and the tag.

Pushing the `v*` tag triggers `.github/workflows/publish.yml`, which then:

- checks the tag points at the tip of `origin/publish` (the publish gate),
- checks `__version__.py` matches the tag (fails fast otherwise),
- runs the test suite, builds the wheel + sdist, and verifies the built artifact's version,
- publishes to pyx via trusted publishing (the `pyx-publish` GitHub environment).

Set `YES=1 just tagnewversion …` to skip the confirmation prompt. Run `just` with no args to
list recipes.

### Branch model

`publish` is a pointer that **trails the release branch** — it always equals the commit
currently published. `just tagnewversion` fast-forwards it for you; don't move it by hand.
Note that `main` is **not** the release line here (`publish` isn't even an ancestor of `main`);
releases are currently cut from `arvind-dev`, and every `v0.1.7.dev*` tag lives on that line.

### Tagging by hand is discouraged

If you create a tag without `just tagnewversion`, the commit's `__version__.py` must already
match the tag or CI fails with, e.g.:

```
Version mismatch: pylabrobot/__version__.py is '0.1.7.dev15' but the tag is '0.1.7.dev16'.
Bump it with 'just tagnewversion v0.1.7.dev16' rather than tagging by hand.
```

Just use the recipe — it keeps the file, `publish`, and the tag consistent.

---

## What's different from upstream

Changes layered on top of upstream PyLabRobot in this fork:

### Release & packaging

- **Auto-publish to pyx** on `v*` tags — `.github/workflows/publish.yml`.
- **Tag-driven versioning with CI enforcement.** The workflow verifies `__version__.py == tag`
  rather than overwriting it, and **`just tagnewversion`** (`justfile`) is the one-command
  release path: bump → fast-forward `publish` → push branch + tag atomically.

### Serializer deserialization fix — `pylabrobot/serializer.py`

`get_plr_class_from_string()` imported a fixed list of submodules unconditionally. Three of
them (`gui`, `testing`, `tests`) are **not shipped in built wheels** (no `__init__.py`), and
three more (`pumps`, `storage`, `only_fans`) **eagerly import optional firmware deps**
(`pyserial`, `pylibftdi`). On a plain `pip install pylabrobot`, that made **every**
`deserialize()` / `Resource.load_state()` raise `ModuleNotFoundError`. The bug was invisible
in editable/source installs, which resolve those directories as PEP-420 namespace packages.

Fix: each submodule is now imported defensively (`importlib.import_module` inside
`try/except ImportError`), so a missing module or absent optional dependency can no longer
break deserialization.

### Hardware / behavior (from internal feature branches)

- Surfacing parameters — `z_press_on_distance`, surface z-speed on the CoRe check.
- Compact `Resource` serializer.
- Added resources — Nunc 96-well flat-bottom plate (165305), Hamilton reservoir/trough.

---

## Syncing with upstream

```bash
git remote add upstream https://github.com/pylabrobot/pylabrobot.git  # if not already set
git fetch upstream
git merge upstream/main      # onto the release branch, resolve, run `make test`,
                             # then cut a new version with `just tagnewversion …`
```
