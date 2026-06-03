# Release helpers for the pyx index.
#
# The published version is driven by the git tag. `just tagnewversion v0.1.7`:
#   1. bumps pylabrobot/__version__.py to match the tag (this is the version
#      source — pyproject.toml has no version field),
#   2. commits it on the branch you release from,
#   3. fast-forwards `publish` to that commit,
#   4. pushes the branch, `publish`, and the tag together (atomically).
#
# Pushing the tag triggers .github/workflows/publish.yml, whose gate requires
# the tag to point at the tip of origin/publish — which step 3 guarantees.
#
# Run it from the branch you release from (currently `arvind-dev`), up to date
# with origin and with a clean working tree. Set YES=1 to skip the prompt.

remote := "origin"
publish_branch := "publish"

_default:
    @just --list

# Cut and publish a new version, e.g. `just tagnewversion v0.1.7`
tagnewversion tag:
    #!/usr/bin/env bash
    set -euo pipefail

    tag="{{tag}}"
    remote="{{remote}}"
    publish="{{publish_branch}}"

    # Tag must be v<number>...; publish.yml validates full PEP 440.
    case "$tag" in
      v[0-9]*) version="${tag#v}" ;;
      *) echo "error: tag must look like v0.1.7 (got '$tag')" >&2; exit 1 ;;
    esac

    branch="$(git symbolic-ref --quiet --short HEAD)" || {
      echo "error: detached HEAD — check out the branch you release from" >&2; exit 1; }

    # Refuse on a dirty tree so the only change in the release commit is the bump.
    git update-index -q --refresh || true
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "error: working tree not clean — commit or stash first" >&2; exit 1
    fi

    git fetch --quiet --tags "$remote"

    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null \
       || git ls-remote --exit-code --tags "$remote" "$tag" >/dev/null 2>&1; then
      echo "error: tag $tag already exists" >&2; exit 1
    fi

    # HEAD must be able to fast-forward publish (the publish.yml gate). This also
    # fails fast if you're on the wrong branch (e.g. main, which publish trails).
    if ! git merge-base --is-ancestor "$remote/$publish" HEAD; then
      echo "error: HEAD can't fast-forward $remote/$publish (wrong branch?)" >&2; exit 1
    fi

    echo "Release plan:"
    echo "  version  $version   (pylabrobot/__version__.py)"
    echo "  commit   on $branch"
    echo "  push     $remote: $branch + $publish + tag $tag  ($publish fast-forwards)"
    echo "  trigger  publish.yml -> build + publish to pyx"
    if [ -z "${YES:-}" ]; then
      read -r -p "Proceed? [y/N] " ans
      case "${ans:-}" in y|Y) ;; *) echo "aborted; nothing changed."; exit 1 ;; esac
    fi

    # Bump the version source to match the tag.
    python3 - "$version" <<'PY'
    import re, sys, pathlib
    version = sys.argv[1]
    path = pathlib.Path("pylabrobot/__version__.py")
    new_text, count = re.subn(
        r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', path.read_text()
    )
    if count != 1:
        raise SystemExit(f"error: expected one __version__ line, replaced {count}")
    path.write_text(new_text)
    PY

    if git diff --quiet -- pylabrobot/__version__.py; then
      echo "__version__.py already at $version; tagging current commit"
    else
      git commit -q -m "Release $tag" -- pylabrobot/__version__.py
    fi

    git tag -a "$tag" -m "Release $tag"
    git push --atomic "$remote" "HEAD:$branch" "HEAD:$publish" "refs/tags/$tag"
    echo "pushed $tag and advanced $remote/$publish; publish.yml is building it for pyx."
