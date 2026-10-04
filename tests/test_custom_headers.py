#!/usr/bin/env python3
"""Unit tests for the custom-headers DNF plugin.

Run with:  python3 -m unittest discover -s tests -v
"""

import importlib.util
import os
import unittest

from libdnf.conf import ConfigParser

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_PATH = os.path.join(HERE, os.pardir, 'dnf-plugins', 'custom_headers.py')


def load_plugin_module():
    """Import the plugin module directly from the source tree."""
    spec = importlib.util.spec_from_file_location('custom_headers', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ch = load_plugin_module()


def make_parser(content, substitutions=None):
    parser = ConfigParser()
    if substitutions:
        parser.setSubstitutions(substitutions)
    parser.readString(content)
    return parser


class TestExtractHeaders(unittest.TestCase):
    """extract_headers() pulls header_* options out of a repo section."""

    def test_extracts_simple_header(self):
        parser = make_parser("""
[r]
header_X-Proxy-Token = abc123
""")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Proxy-Token', 'abc123')])

    def test_preserves_header_name_case(self):
        parser = make_parser("""
[r]
header_X-Custom-CASE = v
""")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Custom-CASE', 'v')])

    def test_matches_prefix_case_insensitively(self):
        parser = make_parser("""
[r]
HEADER_x-token = v
""")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('x-token', 'v')])

    def test_multiple_headers_keep_file_order(self):
        parser = make_parser("""
[r]
header_Z-Last = 3
header_A-First = 1
header_M-Middle = 2
""")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('Z-Last', '3'), ('A-First', '1'), ('M-Middle', '2')])

    def test_no_header_options_returns_empty(self):
        parser = make_parser("""
[r]
name = My Repo
baseurl = https://example.com/repo/
enabled = 1
""")
        self.assertEqual(ch.extract_headers(parser, 'r'), [])

    def test_ignores_options_of_other_sections(self):
        parser = make_parser("""
[other]
header_X-Other = nope
[r]
header_X-Mine = yes
""")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Mine', 'yes')])

    def test_unknown_section_returns_empty(self):
        parser = make_parser("[r]\nheader_X-A = v\n")
        self.assertEqual(ch.extract_headers(parser, 'missing'), [])

    def test_substitutes_variables_in_value(self):
        parser = make_parser(
            "[r]\nheader_X-Release = release-$releasever-$basearch\n",
            substitutions={'releasever': '9.5', 'basearch': 'x86_64'})
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Release', 'release-9.5-x86_64')])

    def test_keeps_unknown_variables_verbatim(self):
        parser = make_parser(
            "[r]\nheader_X-Weird = $undefined_var\n",
            substitutions={'releasever': '9.5'})
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Weird', '$undefined_var')])

    def test_empty_value_allowed(self):
        parser = make_parser("[r]\nheader_X-Empty =\n")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('X-Empty', '')])

    def test_value_with_colon_preserved(self):
        parser = make_parser("[r]\nheader_Authorization = Bearer a:b:c\n")
        self.assertEqual(
            ch.extract_headers(parser, 'r'),
            [('Authorization', 'Bearer a:b:c')])

    def test_skips_empty_header_name(self):
        parser = make_parser("[r]\nheader_ = value\n")
        self.assertEqual(ch.extract_headers(parser, 'r'), [])

    def test_skips_invalid_header_name(self):
        parser = make_parser("[r]\nheader_Has Space = v\n")
        self.assertEqual(ch.extract_headers(parser, 'r'), [])


class TestIsValidHeaderName(unittest.TestCase):
    """is_valid_header_name() implements the RFC 7230 token rule."""

    def test_valid_names(self):
        for name in ('X-Proxy-Token', 'Authorization', 'a', 'a1',
                     'x-a_b.c~d', "X#Frag$Token'quoted'", 'a+b|c^d'):
            self.assertTrue(ch.is_valid_header_name(name), name)

    def test_invalid_names(self):
        for name in ('', 'a b', 'a:b', 'a,b', 'a(b)', 'täken'):
            self.assertFalse(ch.is_valid_header_name(name), name)


class TestFormatHeader(unittest.TestCase):
    """format_header() renders the librepo wire format 'Name: value'."""

    def test_basic(self):
        self.assertEqual(ch.format_header('X-A', 'b'), 'X-A: b')

    def test_empty_value(self):
        self.assertEqual(ch.format_header('X-A', ''), 'X-A: ')


class TestFindSection(unittest.TestCase):
    """find_repo_section() maps a repo id back to its raw config section."""

    def test_exact_match(self):
        parser = make_parser("[my-repo]\nheader_X-A = v\n")
        self.assertEqual(ch.find_repo_section(parser, 'my-repo'), 'my-repo')

    def test_substituted_section_match(self):
        parser = make_parser(
            "[repo-$releasever]\nheader_X-A = v\n",
            substitutions={'releasever': '9.5'})
        self.assertEqual(
            ch.find_repo_section(parser, 'repo-9.5'), 'repo-$releasever')

    def test_substituted_section_match_with_explicit_dict(self):
        # explicit substitutions win over the parser's own table
        parser = make_parser("[repo-$releasever]\nheader_X-A = v\n")
        self.assertEqual(
            ch.find_repo_section(
                parser, 'repo-9.5', substitutions={'releasever': '9.5'}),
            'repo-$releasever')

    def test_no_match_returns_none(self):
        parser = make_parser("[r]\nheader_X-A = v\n")
        self.assertIsNone(ch.find_repo_section(parser, 'other'))


class TestApplyToRepo(unittest.TestCase):
    """apply_repo_headers() works against real dnf.repo.Repo objects."""

    @classmethod
    def setUpClass(cls):
        import dnf
        cls.base = dnf.Base()

    @classmethod
    def tearDownClass(cls):
        cls.base.close()

    def make_repo(self, repo_id, content, substitutions=None):
        import dnf
        repo = dnf.repo.Repo(repo_id, self.base.conf)
        repo.cfg = make_parser(content, substitutions)
        return repo

    def test_applies_headers_to_repo(self):
        repo = self.make_repo('test-repo', """
[test-repo]
name = Test
header_X-Proxy-Token = abc123
header_Authorization = Bearer xyz
""")
        ch.apply_repo_headers(repo)
        self.assertEqual(
            repo.get_http_headers(),
            ('X-Proxy-Token: abc123', 'Authorization: Bearer xyz'))

    def test_repo_without_cfg_is_noop(self):
        import dnf
        repo = dnf.repo.Repo('bare-repo', self.base.conf)
        ch.apply_repo_headers(repo)  # must not raise
        self.assertFalse(repo.get_http_headers())

    def test_repo_without_headers_is_noop(self):
        repo = self.make_repo('plain-repo', """
[plain-repo]
name = Plain
baseurl = https://example.com/repo/
""")
        ch.apply_repo_headers(repo)  # must not raise
        self.assertFalse(repo.get_http_headers())


class TestPluginHook(unittest.TestCase):
    """The dnf.Plugin config() hook injects headers into base.repos."""

    def test_config_hook_applies_to_all_repos(self):
        import dnf
        base = dnf.Base()
        self.addCleanup(base.close)

        repo = dnf.repo.Repo('hooked-repo', base.conf)
        repo.cfg = make_parser("""
[hooked-repo]
name = Hooked
header_X-Proxy-Token = secret-token
""")
        base.repos.add(repo)

        plugin = ch.CustomHeaders(base, None)
        plugin.config()

        self.assertEqual(
            repo.get_http_headers(), ('X-Proxy-Token: secret-token',))

    def test_config_hook_without_any_headers(self):
        import dnf
        base = dnf.Base()
        self.addCleanup(base.close)

        repo = dnf.repo.Repo('plain-hooked', base.conf)
        repo.cfg = make_parser("""
[plain-hooked]
name = Plain
baseurl = https://example.com/repo/
""")
        base.repos.add(repo)

        plugin = ch.CustomHeaders(base, None)
        plugin.config()  # must not raise
        self.assertFalse(repo.get_http_headers())

    def test_config_hook_with_substituted_section(self):
        # repo sections whose name itself contains a variable must be
        # matched via base.conf.substitutions
        import dnf
        base = dnf.Base()
        self.addCleanup(base.close)

        releasever = base.conf.substitutions['releasever']
        repo_id = 'hooked-rel-%s' % releasever
        repo = dnf.repo.Repo(repo_id, base.conf)
        repo.cfg = make_parser("""
[hooked-rel-$releasever]
name = Hooked
header_X-Proxy-Token = var-section-token
""")
        base.repos.add(repo)

        plugin = ch.CustomHeaders(base, None)
        plugin.config()

        self.assertEqual(
            repo.get_http_headers(), ('X-Proxy-Token: var-section-token',))


if __name__ == '__main__':
    unittest.main()
