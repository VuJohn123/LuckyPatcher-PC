"""Test GMS spoofer."""
import os
import tempfile

from patcher.gms_spoofer import GMSSpoofer


def test_patch_creates_stub():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        spoofer = GMSSpoofer(tmp, log_callback=lambda *_: None)
        count = spoofer.patch()
        assert count >= 1
        stub = os.path.join(
            tmp, "smali", "com", "google", "android", "gms", "common",
            "GoogleApiAvailability.smali",
        )
        assert os.path.exists(stub)
        with open(stub) as f:
            assert "isGooglePlayServicesAvailable" in f.read()


def test_patch_idempotent_stub():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        GMSSpoofer(tmp, log_callback=lambda *_: None).patch()
        count2 = GMSSpoofer(tmp, log_callback=lambda *_: None).patch()
        assert count2 >= 0


def test_patch_gsignin_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        smali_dir = os.path.join(tmp, "smali", "com", "test")
        os.makedirs(smali_dir)
        path = os.path.join(smali_dir, "A.smali")
        with open(path, "w") as f:
            f.write(
                ".class public LA;\n"
                ".method public static signIn()V\n"
                "    invoke-static {}, "
                "Lcom/google/android/gms/auth/api/signin/GoogleSignIn;->"
                "getLastSignedInAccount()Lcom/google/android/gms/auth/api/"
                "signin/GoogleSignInAccount;\n"
                "    return-void\n"
                ".end method\n"
            )
        spoofer = GMSSpoofer(tmp, log_callback=lambda *_: None)
        spoofer.patch()
        with open(path) as f:
            assert "Disabled by LP-PC Suite" in f.read()


def test_patch_gms_check_returns_zero():
    with tempfile.TemporaryDirectory() as tmp:
        smali_dir = os.path.join(tmp, "smali", "com", "test")
        os.makedirs(smali_dir)
        path = os.path.join(smali_dir, "A.smali")
        with open(path, "w") as f:
            f.write(
                ".class public LA;\n"
                ".method public static checkGms()I\n"
                "    .locals 1\n"
                "    invoke-static {}, Lcom/x;->isGooglePlayServicesAvailable()I\n"
                "    move-result v0\n"
                "    return v0\n"
                ".end method\n"
            )
        spoofer = GMSSpoofer(tmp, log_callback=lambda *_: None)
        spoofer.patch()
        with open(path) as f:
            content = f.read()
        assert "const/4 v0, 0x0" in content


def test_patch_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "smali"))
        spoofer = GMSSpoofer(tmp, log_callback=lambda *_: None)
        # Chỉ inject stub — count >= 1
        assert spoofer.patch() >= 1