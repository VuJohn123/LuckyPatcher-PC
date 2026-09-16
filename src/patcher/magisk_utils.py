"""Helper tạo Magisk module tối thiểu."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile

logger = logging.getLogger(__name__)


def create_magisk_module(services_jar_path: str, output_zip: str) -> str | None:
    tmp = tempfile.mkdtemp(prefix="magisk_")
    try:
        fw_dir = os.path.join(tmp, "system", "framework")
        os.makedirs(fw_dir, exist_ok=True)
        if os.path.exists(services_jar_path):
            shutil.copy2(services_jar_path,
                         os.path.join(fw_dir, "services.jar"))

        with open(os.path.join(tmp, "module.prop"), "w") as f:
            f.write(
                "id=lp_pc_signature_patch\n"
                "name=LP-PC Signature Patch\n"
                "version=v1\n"
                "versionCode=1\n"
                "author=LP-PC Suite\n"
                "description=Disable APK signature verification\n"
            )
        with open(os.path.join(tmp, "post-fs-data.sh"), "w") as f:
            f.write(
                "#!/system/bin/sh\n"
                "mount -o bind "
                "$MODDIR/system/framework/services.jar "
                "/system/framework/services.jar\n"
            )
        os.chmod(os.path.join(tmp, "post-fs-data.sh"), 0o755)

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(tmp):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, tmp)
                    z.write(full, arcname=rel)
        return output_zip
    except OSError as e:
        logger.warning("create_magisk_module failed: %s", e)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)