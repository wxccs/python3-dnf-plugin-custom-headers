# The plugin must land exactly in the directory dnf scans for plugins.
# Prefer the distro macro when python3-rpm-macros is installed; otherwise
# ask the dnf module itself (python3-dnf is a BuildRequire anyway). Do NOT
# fall back to plain sysconfig here: on e.g. RHEL 10 sysconfig reports
# /usr/local/... while dnf actually scans /usr/lib/python3.X/... .
%{!?__python3:%global __python3 /usr/bin/python3}
%if 0%{?python3_sitelib:1}
%global plugindir %{python3_sitelib}/dnf-plugins
%else
%global plugindir %(%{__python3} -c "import dnf; print(dnf.const.PLUGINPATH)")
%endif

%global srcname  dnf-plugin-custom-headers

Name:           python3-dnf-plugin-custom-headers
Version:        0.1.0
Release:        1%{?dist}
Summary:        DNF plugin for per-repository custom HTTP headers
License:        GPLv2+
URL:            https://github.com/wxccs/python3-dnf-plugin-custom-headers
Source0:        %{srcname}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-dnf >= 4.2.0
Requires:       python3-dnf >= 4.2.0

%description
This DNF plugin turns repository configuration options starting with
"header_" into HTTP request headers sent to the upstream repository,
for example:

    [my-mirror]
    baseurl = https://mirror.example.com/repo/
    header_X-Proxy-Token = my-secret-token

Every request DNF makes to that repository (metadata as well as package
downloads) then carries "X-Proxy-Token: my-secret-token". Header names
are used verbatim (case preserved) and values support the usual DNF
variables ($releasever, $basearch, ...).

Useful for mirrors behind authenticating proxies or API gateways
(Artifactory, Nexus, cloud mirrors, ...) that expect a token header.

%prep
%setup -q -n %{srcname}-%{version}
# fail the build instead of silently installing into a bogus location
case "%{plugindir}" in
    /usr/lib/python3*/site-packages/dnf-plugins) ;;
    *) echo "ERROR: unexpected dnf plugin dir: %{plugindir}" >&2; exit 1 ;;
esac

%build
# pure python, nothing to build

%install
install -D -m 644 dnf-plugins/custom_headers.py \
    %{buildroot}%{plugindir}/custom_headers.py
install -D -m 644 conf/custom-headers.conf \
    %{buildroot}%{_sysconfdir}/dnf/plugins/custom-headers.conf

%{__python3} -m compileall -q -f -d %{plugindir} \
    %{buildroot}%{plugindir}

%check
%{__python3} -m unittest discover -s tests

%files
%license LICENSE
%doc README.md
%config(noreplace) %{_sysconfdir}/dnf/plugins/custom-headers.conf
%{plugindir}/custom_headers.py
%{plugindir}/__pycache__/*.pyc

%changelog
* Sun Oct 04 2026 Daniel Wu <wxc@wxccs.org> - 0.1.0-1
- Initial package
