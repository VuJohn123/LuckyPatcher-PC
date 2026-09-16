"""Test AppCloner — mock decompile/recompile/sign."""
import os
import tempfile
from unittest.mock import patch

from patcher.app_cloner import AppCloner


def test_clone_decompile_fails():
    with patch("patcher.app_cloner.decompile_apk") as mock_decomp:
        mock_decomp.side_effect = RuntimeError("fail")
        cloner = AppCloner("/tmp/app.apk", "com.new.app",
                          log_callback=lambda *_: None)
        result = cloner.clone()
        assert result is None
        cloner.cleanup()


def test_clone_no_manifest():
    with patch("patcher.app_cloner.decompile_apk") as mock_decomp, \
         patch("patcher.app_cloner.tempfile.mkdtemp", return_value="/tmp/clone_test"):

        def fake_decomp(apk, out, **kw):
            os.makedirs(out, exist_ok=True)
            # Không tạo manifest

        mock_decomp.side_effect = fake_decomp

        cloner = AppCloner("/tmp/app.apk", "com.new.app",
                          log_callback=lambda *_: None)
        result = cloner.clone()
        assert result is None
        cloner.cleanup()


def test_clone_no_package_in_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        decomp = os.path.join(tmp, "decompiled")

        with patch("patcher.app_cloner.decompile_apk") as mock_decomp, \
             patch("patcher.app_cloner.tempfile.mkdtemp", return_value=tmp):

            def fake_decomp(apk, out, **kw):
                os.makedirs(out, exist_ok=True)
                with open(os.path.join(out, "AndroidManifest.xml"), "w") as f:
                    f.write("<manifest></manifest>")

            mock_decomp.side_effect = fake_decomp

            cloner = AppCloner("/tmp/app.apk", "com.new.app",
                              log_callback=lambda *_: None)
            result = cloner.clone()
            assert result is None
            cloner.cleanup()


def test_clone_success():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("patcher.app_cloner.decompile_apk") as mock_decomp, \
             patch("patcher.app_cloner.recompile_apk") as mock_rec, \
             patch("patcher.app_cloner.sign_apk") as mock_sign, \
             patch("patcher.app_cloner.tempfile.mkdtemp", return_value=tmp), \
             patch("shutil.copy2"):

            def fake_decomp(apk, out, **kw):
                os.makedirs(out, exist_ok=True)
                with open(os.path.join(out, "AndroidManifest.xml"), "w") as f:
                    f.write('<manifest package="com.old.app"></manifest>')

            mock_decomp.side_effect = fake_decomp
            mock_rec.return_value = os.path.join(tmp, "cloned.apk")
            mock_sign.return_value = os.path.join(tmp, "cloned_signed.apk")

            cloner = AppCloner("/tmp/app.apk", "com.new.app",
                              log_callback=lambda *_: None)
            cloner.clone()
            cloner.cleanup()


def test_patch_interface():
    with patch.object(AppCloner, "clone", return_value="/tmp/x.apk"):
        cloner = AppCloner("/tmp/app.apk", "com.new.app",
                          log_callback=lambda *_: None)
        assert cloner.patch() == 1
        cloner.cleanup()