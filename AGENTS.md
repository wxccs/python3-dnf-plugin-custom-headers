# AGENTS.md

Instructions and context for AI coding agents working on this
repository.

## Project overview

`python3-dnf-plugin-custom-headers` is a DNF4 plugin that turns
`header_*` options in repository configuration files into HTTP request
headers sent to the repository upstream. It covers metadata downloads
and package downloads alike. DNF4 only - DNF5 (C++ plugin system,
default on RHEL 10+ when invoked as `dnf`) is not and cannot be
supported by this codebase.

License: GPLv2+ (same as dnf). Keep new files free of copyright header
comments.

## Repository layout

```
dnf-plugins/custom_headers.py   # the plugin itself (installed into dnf's pluginpath)
conf/custom-headers.conf        # /etc/dnf/plugins/<name>.conf switch file
tests/test_custom_headers.py    # unit tests (unittest, run on the host python)
scripts/header_echo_server.py   # local HTTP server recording request headers
scripts/smoke-test.sh           # smoke test: installed plugin -> local server -> grep headers
scripts/integration-test.sh     # full chain: dummy rpm + local repo + dnf install --downloadonly
SPECS/...spec                   # RPM spec (noarch, el8/9/10 + fedora)
build.sh                        # build the rpm on the current system -> dist/
Makefile                        # make test | smoke | integration | rpm | clean
.github/workflows/build-rpm.yml # multi-distro container build matrix + release
```

## Commands

```bash
make test         # unit tests (plugin source is loaded from the tree; nothing to install)
make smoke        # requires the plugin to be installed on the host
make integration  # requires rpm-build + createrepo_c; also requires the plugin installed
make rpm          # ./build.sh -> dist/  (requires rpm-build + python3)
```

Test conventions: TDD. Unit tests must not touch the network or the
host dnf configuration. `tests/test_custom_headers.py` imports the
plugin module by file path, so no installation is needed.

## Architecture notes (verified against dnf 4.7 / 4.14 / 4.20 / 4.22)

- The dnf4 CLI runs plugin hooks in this order:
  `init_plugins -> pre_config() -> read_all_repos() -> config() ->
  fill_sack() (metadata download) -> ... -> transaction`.
  The `config()` hook is therefore the only official injection point:
  repositories are fully loaded (`repo.cfg` is populated) while nothing
  has been downloaded yet. Do not move the logic to `sack()` or later
  hooks - metadata would already be downloaded without headers.
- Repo files are parsed by `libdnf.conf.ConfigParser`. Unknown options
  such as `header_X-Proxy-Token` are kept verbatim (case preserved) and
  are reachable through `repo.cfg` (a per-repo parser instance
  containing the whole repo file).
- Header injection uses the public API `repo.set_http_headers([...])`
  (wire format `"Name: value"`), which libdnf applies to the librepo
  handles of both metadata and package downloads via `LRO_HTTPHEADER`.
  Never manipulate librepo handles directly.
- `repo.id` holds the *substituted* section name; the parser holds the
  *raw* one. `find_repo_section()` bridges the two (sections like
  `[repo-$releasever]` need the substitution pass). Substitutions come
  from `base.conf.substitutions` (a plain dict, works on every dnf 4.x;
  `parser.getSubstitutions()` does not exist on older libdnf builds).
- Repo objects created via `--repofrompath` or the Python API have no
  `repo.cfg` and are silently skipped - there is no place their headers
  could be configured.

## Hard rules

- **Never log header values.** They carry tokens. Log header names
  only. This rule also applies to test output.
- **Never let the plugin raise** out of a hook: wrap per-repo work in
  try/except and log a warning. A plugin must never break dnf itself.
- Keep the plugin compatible with **Python 3.6** (RHEL 8) - no
  f-strings in the plugin or its tests, no walrus operators, etc.
  (3.6-compatible syntax only; the scripts under `scripts/` run on the
  build host and may use anything the target distros support.)

## RPM packaging gotchas

- The spec must install the plugin into **exactly** the directory dnf
  scans (`dnf.const.PLUGINPATH`). It prefers `%{python3_sitelib}` when
  python3-rpm-macros is installed and falls back to
  `python3 -c "import dnf; print(dnf.const.PLUGINPATH)"` otherwise.
  **Do not** fall back to plain `sysconfig.get_paths()['purelib']`: on
  RHEL 10 it reports `/usr/local/lib/...` while dnf scans
  `/usr/lib/python3.X/...` - the rpm would install into a dead path.
- A `%prep`-time sanity check rejects unexpected plugin directories -
  keep it.
- The plugin path differs per distro (`python3.6` on el8, `python3.9`
  on el9, `python3.12` on el10/fedora), which is why every distro is
  built in its own container. Artifacts are noarch but not portable
  across python minor versions.
- On RHEL 10 family images the default `dnf` is dnf5; the `dnf4`
  command comes from `python3-dnf`, which this package `Requires`.
  Test scripts detect this via `command -v dnf4 || command -v dnf`.

## Release process

1. Update `Version:` in the spec and the `%changelog` entry
   (author: Daniel Wu <wxc@wxccs.org>).
2. Commit, then create a **signed** annotated tag: `git tag -s vX.Y.Z`.
3. Push the tag. The CI builds all distros, runs the smoke tests and
   creates the GitHub Release with all rpms attached.

Commit messages follow `type(scope): description` in English.
