# python3-dnf-plugin-custom-headers

A DNF (DNF4) plugin that automatically adds custom HTTP request headers
when talking to repository upstreams.

Any repository configuration option whose name starts with `header_` is
turned into an HTTP request header sent to that repository's upstream,
and applies to **every** request DNF makes for it (metadata downloads as
well as package downloads). For example:

```ini
[my-artifactory]
name = Artifactory Mirror
baseurl = https://mirror.example.com/repo/$releasever/
enabled = 1
header_X-Proxy-Token = my-secret-token
header_Authorization = Bearer xxxx-yyyy
```

makes every request DNF sends to `my-artifactory` carry:

```
X-Proxy-Token: my-secret-token
Authorization: Bearer xxxx-yyyy
```

Useful for mirrors behind authenticating proxies or API gateways
(Artifactory, Nexus, cloud mirror gateways, ...).

## Features

- **Official API only**: headers are injected through
  `dnf.repo.Repo.set_http_headers()` (DNF >= 4.2). libdnf applies them on
  the librepo handles of both metadata and package downloads
  (`LRO_HTTPHEADER`). Nothing outside the repo configuration is touched.
- **Correct injection point**: the plugin works in the `config()` hook -
  at that point all repositories are loaded (`read_all_repos()` has
  finished) while no network request has happened yet, so every command
  (`dnf install`, `dnf download`, `dnf reposync`, `dnf makecache`, ...)
  is covered.
- **Header name case is preserved** (`header_X-Proxy-Token` ->
  `X-Proxy-Token`); matching of the `header_` prefix itself is
  case-insensitive.
- **Values support DNF variable substitution**: `$releasever`,
  `$basearch`, `$arch`, ... (same semantics as in `baseurl`; unknown
  variables are left untouched).
- **Header values are never logged**: only header names appear in logs,
  so tokens do not leak into log files.
- Repositories without any `header_*` option are left completely alone.

## Supported distributions

Anything DNF4-based (`dnf --version` reports 4.x). The following
platforms have been **fully verified end to end in containers**
(unit tests -> RPM build -> install -> header verification on metadata
and package downloads):

| Platform | dnf | python | Result |
| --- | --- | --- | --- |
| Rocky Linux 8 (RHEL 8 family) | 4.7.0 | 3.6 | 27/27 unit tests, 7/7 requests carried headers |
| Rocky Linux 9 (RHEL 9 family) | 4.14.0 | 3.9 | 27/27 unit tests, 7/7 requests carried headers |
| Rocky Linux 10.2 | 4.20.0 | 3.12 | 27/27 unit tests, 6/6 requests carried headers |
| Fedora 40 | 4.22.0 | 3.12 | 27/27 unit tests, 5/5 requests carried headers |

The remaining sibling distributions (AlmaLinux, CentOS Stream, Oracle
Linux) are built and smoke-tested by the same CI matrix.

> On RHEL 10 family systems the default `dnf` command is **DNF5** (a
> C++ plugin system, incompatible with this plugin); use the `dnf4`
> command there, or switch `dnf` back to DNF4 via alternatives. Under
> DNF5 this plugin is simply not loaded (no side effects).

## Installation

```bash
# After downloading the rpm for your distribution from the Releases page:
dnf install ./python3-dnf-plugin-custom-headers-0.1.0-1.el9.noarch.rpm
```

Or build from source (see below).

No additional configuration is needed after installation - just write
`header_*` options into your repo files.

## Configuration

### Per-repository (`/etc/yum.repos.d/*.repo`)

| Option | Effect |
| --- | --- |
| `header_X-Proxy-Token = abc` | sends `X-Proxy-Token: abc` |
| `header_Authorization = Bearer t` | sends `Authorization: Bearer t` |
| `header_X-Release = rel-$releasever` | value is variable-substituted, then sent |

Rules:

1. The option name with the `header_` prefix stripped is used verbatim
   as the HTTP header name, **case preserved**.
2. The prefix match is case-insensitive: `HEADER_x-a` and `Header_x-a`
   work too.
3. The header name must be a valid RFC 7230 token (no spaces etc.);
   invalid names are skipped with a warning.
4. Values are variable-substituted (`$releasever`, ...); empty values
   are allowed.
5. **Note**: libdnf prints an `Unknown configuration option:
   header_...` warning for every `header_*` option. This is expected,
   harmless behavior and cannot be suppressed.

### Plugin switch (`/etc/dnf/plugins/custom-headers.conf`)

```ini
[main]
# Set to 0 to disable the plugin entirely (header_* options are then ignored)
enabled = 1
```

## How it works

```
repo file (header_X-Proxy-Token = abc)
    |  parsed by libdnf.conf.ConfigParser (unknown options are kept
    |  verbatim - including case - and stored on the repo as repo.cfg)
    v
plugin config() hook  <--- repos are loaded, no network request has
    |                     happened yet at this point
    |  extract_headers(): collect header_* options (values substituted)
    v
repo.set_http_headers(["X-Proxy-Token: abc"])
    |  libdnf.repo.Repo.setHttpHeaders()
    v
librepo handles (LRO_HTTPHEADER) ----> metadata + package downloads
                                        both carry the header
```

## Building RPMs from source

On the target distribution (requires `rpm-build`, `python3`,
`python3-dnf`):

```bash
./build.sh
# or
make rpm
```

Artifacts land in `dist/` (noarch rpm + srpm).

Local development verification:

```bash
make test          # unit tests (plugin does not need to be installed)
make smoke         # smoke test: verifies the installed plugin sends
                   # headers to a local echo server
make integration   # full chain: local dummy repository + dnf install
                   # --downloadonly; verifies metadata AND package
                   # downloads carry the headers
```

## GitHub Actions / CI

`.github/workflows/build-rpm.yml` builds the rpm and runs the smoke
tests in containers of the following distributions:

- Rocky Linux 8 / 9 / 10
- AlmaLinux 8 / 9 / 10
- CentOS Stream 9 / 10
- Oracle Linux 8 / 9
- Fedora 39 / 40

Pushing a `v*` tag creates a GitHub Release and uploads all rpm
artifacts; regular pushes and PRs build and upload workflow artifacts.

## FAQ

**Q: Why do I see `Unknown configuration option: header_...` warnings?**
A: libdnf warns about every unknown option in repo files and this cannot
   be turned off. It is harmless - ignore it.

**Q: Do mirrorlist / metalink requests carry the headers too?**
A: Yes. The headers live on the repository's librepo handle, which is
   used for mirrorlist/metalink resolution as well as repodata and
   package downloads.

**Q: What about DNF5 (the default on RHEL 10+)?**
A: DNF5 plugins are a C++ system; this DNF4 Python plugin has no effect
   under DNF5. On RHEL 10 family systems use the `dnf4` command or
   switch via alternatives. Native DNF5 support would require a
   separate C++ plugin.

## License

GPLv2+ (same license as dnf itself), see [LICENSE](LICENSE).
