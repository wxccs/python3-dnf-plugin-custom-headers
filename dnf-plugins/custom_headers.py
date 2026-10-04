"""custom_headers.py - DNF plugin adding per-repository custom HTTP headers.

Repository configuration options whose name starts with "header_" are
forwarded to librepo as HTTP request headers on every request DNF makes
to that repository (metadata as well as package downloads):

    [my-mirror]
    baseurl = https://mirror.example.com/repo/$releasever/
    header_X-Proxy-Token = my-secret-token

makes DNF send "X-Proxy-Token: my-secret-token" with every request to
my-mirror.

Notes:
  * The part after the "header_" prefix is used verbatim as the header
    name, so its case is preserved. The prefix match itself is
    case-insensitive ("HEADER_x-a" works too).
  * Values support the usual DNF config variables ($releasever,
    $basearch, ...); unknown variables are left untouched.
  * Repos without any header_* option are left completely alone.

The plugin is controlled by /etc/dnf/plugins/custom-headers.conf
(set enabled = 0 there to disable it).
"""

import logging
import re

import dnf
from libdnf.conf import ConfigParser

logger = logging.getLogger('dnf')

HEADER_PREFIX = 'header_'

# Valid HTTP header field name per RFC 7230 (the "token" rule).
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def is_valid_header_name(name):
    """Return True if name is a valid HTTP header field name (RFC 7230)."""
    return bool(_HEADER_NAME_RE.match(name))


def extract_headers(parser, section):
    """Collect (name, value) pairs of header_* options from a repo section.

    ``parser`` is a libdnf.conf.ConfigParser holding the raw repository
    file contents. Values are returned with DNF variables substituted.
    """
    if not parser.hasSection(section):
        return []
    options = parser.getData()[section]
    headers = []
    for key in options:
        if not key.lower().startswith(HEADER_PREFIX):
            continue
        name = key[len(HEADER_PREFIX):]
        if not is_valid_header_name(name):
            logger.warning(
                'custom-headers: ignoring option "%s": "%s" is not a '
                'valid HTTP header name', key, name)
            continue
        headers.append((name, parser.getSubstitutedValue(section, key)))
    return headers


def format_header(name, value):
    """Render one header in the librepo wire format "Name: value"."""
    return '%s: %s' % (name, value)


def find_repo_section(parser, repo_id, substitutions=None):
    """Map a (substituted) repo id back to its raw section name.

    Section headers may themselves contain variables, e.g.
    "[repo-$releasever]", while repo.id holds the substituted value, so
    a plain lookup can miss. Returns None when no section matches.

    ``substitutions`` (a plain dict, e.g. base.conf.substitutions) is
    used for the comparison when given; otherwise the parser's own
    substitution table is consulted.
    """
    if parser.hasSection(repo_id):
        return repo_id
    if substitutions is None:
        try:
            substitutions = parser.getSubstitutions()
        except AttributeError:
            # older libdnf builds do not expose getSubstitutions()
            substitutions = {}
    for section in parser.getData():
        if ConfigParser.substitute(section, substitutions) == repo_id:
            return section
    return None


def apply_repo_headers(repo, substitutions=None):
    """Apply the header_* options of one repo as its HTTP headers.

    Repos that carry no raw config parser (repo.cfg, e.g. created via
    --repofrompath or the Python API) are skipped silently.
    """
    parser = getattr(repo, 'cfg', None)
    if parser is None:
        return
    section = find_repo_section(parser, repo.id, substitutions)
    if section is None:
        return
    headers = extract_headers(parser, section)
    if not headers:
        return
    if not hasattr(repo, 'set_http_headers'):
        logger.warning(
            'custom-headers: repo "%s": this dnf version does not support '
            'setting HTTP headers, ignoring header_* options', repo.id)
        return
    repo.set_http_headers([format_header(name, value)
                           for name, value in headers])
    # Log header names only - values may carry secrets.
    logger.debug(
        'custom-headers: repo "%s" sends HTTP headers: %s',
        repo.id, ', '.join(name for name, _ in headers))


class CustomHeaders(dnf.Plugin):

    """DNF plugin injecting header_* repo options as HTTP request headers."""

    name = 'custom-headers'

    def config(self):
        # Runs after base.read_all_repos() but before any metadata or
        # package download starts, so every enabled repo can still be
        # configured.
        try:
            # plain dict, works on every dnf 4.x; more robust than the
            # parser's own substitution table on older libdnf builds
            substitutions = dict(self.base.conf.substitutions)
        except Exception:
            substitutions = None
        for repo in self.base.repos.values():
            try:
                apply_repo_headers(repo, substitutions)
            except Exception as e:  # never break dnf because of a plugin
                logger.warning(
                    'custom-headers: failed to configure HTTP headers for '
                    'repo "%s": %s', getattr(repo, 'id', '?'), e)
