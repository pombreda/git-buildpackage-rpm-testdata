Name:       gbp-test2-alt
Summary:    Test package 2 alternative for git-buildpackage
Epoch:      1
Version:    2.0
Release:    0
Group:      Development/Libraries
License:    GPLv2
Source10:   ftp://ftp.host.com/%{name}-%{version}.tar.gz
Source:     foo.txt
Source20:   bar.tar.gz
# Gbp-Ignore-Patches: 0
Patch:      my.patch
Patch10:    http://example.com/patches/my2.patch
Patch20:    my3.patch
Packager:   Markus Lehtonen <markus.lehtonen@linux.intel.com>

%description
Package for testing the RPM functionality of git-buildpackage.
Version 2 which has packaging and development in the same
git branch. Alternative spec file used.


%prep
%setup -T -n %{name}-%{version} -c -a 10

%patch
%patch -P 20 -p1

echo "Do things"

# Gbp-Patch-Macros

%build
make


%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{_datadir}/%{name}
cp -R * %{buildroot}/%{_datadir}/%{name}
install %{SOURCE0} %{buildroot}/%{_datadir}/%{name}



%files
%defattr(-,root,root,-)
%dir %{_datadir}/%{name}
%{_datadir}/%{name}
