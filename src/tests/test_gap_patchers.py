from patcher.fake_package_patcher import FakePackagePatcher
from patcher.hosts_blocker import HostsBlocker
from patcher.install_dir_patcher import InstallDirPatcher


def test_fake_pkg(tmp_path):
    (tmp_path / "AndroidManifest.xml").write_text('<manifest package="com.real.app"></manifest>')
    p = FakePackagePatcher(str(tmp_path), log_callback=lambda *a: None, new_package="fake.lp.pkg")
    assert p.patch() == 1
    assert 'fake.lp.pkg' in (tmp_path / "AndroidManifest.xml").read_text()

def test_install_dir(tmp_path):
    assert InstallDirPatcher(str(tmp_path), log_callback=lambda *a: None).patch() == 1
    assert "install_dir" in (tmp_path / "apk.yml").read_text()

def test_hosts_block(tmp_path):
    n = HostsBlocker(str(tmp_path), log_callback=lambda *a: None).patch()
    assert n > 0 and (tmp_path / "hosts.lp").exists()
