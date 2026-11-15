"""
Packer bypass patcher — act on the fusion layer's `BypassStrategy`.

The scanner's precision fusion (`scanner.checks.packer_fusion`) decides how
readable a packed APK really is. This patcher turns that verdict into a
concrete edit on the decompiled tree:

  DEX_PLAINTEXT    → nothing to do; the app dex is already readable.
  SHELL_SWAP       → repoint `<application android:name>` at the real
                     Application class and neutralise the shell entry.
  STUB_NEUTRALIZE  → make the shell Application's lifecycle methods return
                     immediately so control falls through to plaintext code.
  UNPACK_REQUIRED  → refuse; an external unpacker is needed.

The patcher never guesses silently: when it cannot find a safe target it
reports why and returns 0 patched files, so the pipeline can surface the
strategy to the user instead of shipping a half-patched APK.
"""
from __future__ import annotations

import logging
import os
import re

from core.smali_utils import get_all_smali_files
from patcher.base import BasePatcher

logger = logging.getLogger(__name__)

_APP_TAG_RE = re.compile(
    r"<application\b(?P<attrs>[^>]*)>", re.DOTALL
)
_APP_NAME_RE = re.compile(
    r'android:name\s*=\s*"(?P<name>[^"]+)"'
)
_SUPER_APP_RE = re.compile(
    r"^\.super\s+Landroid/app/Application;", re.MULTILINE
)
_CLASS_DECL_RE = re.compile(
    r"^\.class\b[^\n]*?\s(?P<desc>L[^\s;]+;)", re.MULTILINE
)
_LIFECYCLE_METHODS = ("onCreate", "attachBaseContext")

# Class prefixes owned by known packers. A real Application never lives
# under one of these, so they are skipped when hunting for the swap target.
_SHELL_PREFIXES = (
    "com/pairip/",
    "com/tencent/",
    "com/qihoo/",
    "com/stub/",
    "com/bangcle/",
    "com/secneo/",
    "com/shell/",
    "com/guardsquare/",
    "com/licel/",
    "com/liapp/",
    "kr/co/liapp/",
    "com/virbox/",
    "com/sense/",
    "com/arxan/",
    "com/nagain/",
    "com/nagacore/",
    "com/promon/",
    "com/inka/",
    "com/appsealing/",
)


class PackerBypassPatcher(BasePatcher):
    """Apply a `BypassStrategy` to a decompiled APK tree."""

    def __init__(
        self,
        decompiled_path: str,
        log_callback=print,
        file_cache=None,
        *,
        strategy: str = "dex_plaintext",
        shell_application: str | None = None,
        real_application: str | None = None,
    ):
        super().__init__(decompiled_path, log_callback, file_cache)
        self.strategy = (strategy or "dex_plaintext").strip().lower()
        self.shell_application = shell_application
        self.real_application = real_application

    # ============================================================
    # PUBLIC
    # ============================================================
    def patch(self) -> int:
        if self.strategy == "dex_plaintext":
            self._log_traced(
                "[i] [Bypass] dex_plaintext — không cần bypass, "
                "patch trực tiếp."
            )
            return 0
        if self.strategy == "unpack_required":
            self._log_traced(
                "[!] [Bypass] unpack_required — payload mã hoá, "
                "cần unpacker ngoài (không sửa gì)."
            )
            return 0
        if self.strategy == "shell_swap":
            return self._shell_swap()
        if self.strategy == "stub_neutralize":
            return self._stub_neutralize()

        self._log_traced(
            f"[!] [Bypass] Strategy không hỗ trợ: {self.strategy}"
        )
        return 0

    # ============================================================
    # SHELL SWAP
    # ============================================================
    def _shell_swap(self) -> int:
        manifest = os.path.join(self.decompiled_path, "AndroidManifest.xml")
        try:
            content = self._read(manifest)
        except OSError as e:
            self._log_traced(f"[!] [Bypass] Manifest read fail: {e}")
            return 0

        shell = self.shell_application or self._manifest_application(content)
        if not shell:
            # No shell declared in the manifest. If a real Application was
            # supplied explicitly, inject it; otherwise there is nothing to
            # swap away from.
            if self.real_application and _APP_TAG_RE.search(content):
                patched = self._inject_application_name(
                    content, self.real_application
                )
                if patched:
                    self._write(manifest, patched)
                    self._log_traced(
                        f"[✔] [Bypass] Injected Application "
                        f"{self.real_application}"
                    )
                    return 1
            self._log_traced(
                "[!] [Bypass] Không thấy <application android:name>"
            )
            return 0

        real = self.real_application or self._find_real_application(shell)
        if not real:
            self._log_traced(
                f"[!] [Bypass] Không tìm được Application thật "
                f"(shell={shell}) — fallback stub_neutralize."
            )
            self.strategy = "stub_neutralize"
            return self._stub_neutralize()

        if real == shell:
            self._log_traced(
                "[i] [Bypass] Manifest đã trỏ Application thật — skip."
            )
            return 0

        patched = self._repoint_manifest(content, shell, real)
        if not patched:
            self._log_traced(
                f"[!] [Bypass] Không sửa được android:name {shell} → {real}"
            )
            return 0

        self._write(manifest, patched)
        self._log_traced(
            f"[✔] [Bypass] Shell swap: {shell} → {real}"
        )
        return 1

    def _inject_application_name(
        self, content: str, real: str
    ) -> str | None:
        match = _APP_TAG_RE.search(content)
        if not match:
            return None
        attrs = match.group("attrs")
        if _APP_NAME_RE.search(attrs):
            return None
        new_attrs = f'{attrs.rstrip()} android:name="{real}"'
        return (
            content[: match.start("attrs")]
            + new_attrs
            + content[match.end("attrs"):]
        )

    def _repoint_manifest(
        self, content: str, shell: str, real: str
    ) -> str | None:
        match = _APP_TAG_RE.search(content)
        if not match:
            return None
        attrs = match.group("attrs")
        name_match = _APP_NAME_RE.search(attrs)
        if not name_match:
            # No android:name → inject one on the <application> tag.
            new_attrs = (
                f'{attrs.rstrip()} android:name="{real}"'
            )
            return (
                content[: match.start("attrs")]
                + new_attrs
                + content[match.end("attrs"):]
            )
        if name_match.group("name") != shell:
            return None
        new_attrs = (
            attrs[: name_match.start("name")]
            + real
            + attrs[name_match.end("name"):]
        )
        return (
            content[: match.start("attrs")]
            + new_attrs
            + content[match.end("attrs"):]
        )

    # ============================================================
    # STUB NEUTRALIZE
    # ============================================================
    def _stub_neutralize(self) -> int:
        shell = self.shell_application or self._manifest_application(
            self._safe_read_manifest()
        )
        if not shell:
            self._log_traced(
                "[!] [Bypass] Không xác định được shell Application."
            )
            return 0

        smali_path = self._find_smali_for_class(shell)
        if not smali_path:
            self._log_traced(
                f"[!] [Bypass] Không thấy smali cho {shell}"
            )
            return 0

        try:
            content = self._read(smali_path)
        except OSError as e:
            self._log_traced(f"[!] [Bypass] Read {shell} fail: {e}")
            return 0

        new_content, changed = self._neutralize_lifecycle(content)
        if not changed:
            self._log_traced(
                f"[i] [Bypass] {shell} không có lifecycle method để neutralize."
            )
            return 0

        self._write(smali_path, new_content)
        self._log_traced(
            f"[✔] [Bypass] Neutralized lifecycle của {shell}"
        )
        return 1

    def _neutralize_lifecycle(self, content: str) -> tuple[str, bool]:
        """Force lifecycle methods to return early (idempotent)."""
        lines = content.splitlines()
        out: list[str] = []
        changed = False
        i = 0
        while i < len(lines):
            line = lines[i]
            method = self._method_name(line)
            if method in _LIFECYCLE_METHODS:
                # Collect the whole method block.
                block = [line]
                i += 1
                while i < len(lines) and not lines[i].strip().startswith(
                    ".end method"
                ):
                    block.append(lines[i])
                    i += 1
                if i < len(lines):
                    block.append(lines[i])  # .end method
                    i += 1

                if self._block_is_neutral(block):
                    out.extend(block)
                    continue

                out.extend(self._neutral_block(block))
                changed = True
                continue
            out.append(line)
            i += 1
        return "\n".join(out) + ("\n" if content.endswith("\n") else ""), changed

    @staticmethod
    def _block_is_neutral(block: list[str]) -> bool:
        body = [
            ln.strip() for ln in block[1:-1]
            if ln.strip() and not ln.strip().startswith((".annotation", "end annotation"))
        ]
        return (
            len(body) == 2
            and body[0].startswith((".locals", ".registers"))
            and body[1] == "return-void"
        )

    @staticmethod
    def _neutral_block(block: list[str]) -> list[str]:
        """Keep signature + .locals, replace the body with return-void."""
        signature = block[0]
        locals_line = None
        for ln in block[1:]:
            stripped = ln.strip()
            if stripped.startswith((".locals", ".registers")):
                locals_line = ln
                break
        if locals_line is None:
            locals_line = "    .locals 0"
        return [signature, locals_line, "", "    return-void", ".end method"]

    @staticmethod
    def _method_name(line: str) -> str | None:
        stripped = line.strip()
        if not stripped.startswith(".method"):
            return None
        match = re.search(r"(\w+)\(", stripped)
        return match.group(1) if match else None

    # ============================================================
    # DISCOVERY
    # ============================================================
    def _manifest_application(self, content: str) -> str | None:
        match = _APP_TAG_RE.search(content or "")
        if not match:
            return None
        name_match = _APP_NAME_RE.search(match.group("attrs"))
        if not name_match:
            return None
        return name_match.group("name").lstrip(".")

    def _safe_read_manifest(self) -> str:
        try:
            return self._read(
                os.path.join(self.decompiled_path, "AndroidManifest.xml")
            )
        except OSError:
            return ""

    def _find_real_application(self, shell: str) -> str | None:
        """Find a concrete Application subclass that is not a packer shell."""
        shell_desc = "L" + shell.replace(".", "/") + ";"
        candidates: list[tuple[int, str]] = []
        try:
            files = get_all_smali_files(self.decompiled_path)
        except Exception as e:
            logger.debug("Smali enumeration failed: %s", e)
            return None

        for filepath in files:
            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    head = f.read(4096)
            except OSError:
                continue
            if not _SUPER_APP_RE.search(head):
                continue
            decl = _CLASS_DECL_RE.search(head)
            if not decl:
                continue
            desc = decl.group("desc")
            if desc == shell_desc:
                continue
            internal = desc[1:-1]
            if any(internal.startswith(p) for p in _SHELL_PREFIXES):
                continue
            # Prefer classes outside the packer namespace; break ties by
            # shallower nesting (app-level Application is rarely deep).
            candidates.append((internal.count("/"), desc))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1][1:-1].replace("/", ".")

    def _find_smali_for_class(self, class_name: str) -> str | None:
        rel = class_name.replace(".", os.sep) + ".smali"
        try:
            from core.smali_utils import get_smali_dirs
        except ImportError:  # pragma: no cover - defensive
            return None
        for smali_dir in get_smali_dirs(self.decompiled_path):
            candidate = os.path.join(smali_dir, rel)
            if os.path.exists(candidate):
                return candidate
        # Fall back to a case-insensitive basename search.
        base = os.path.basename(rel).lower()
        try:
            for filepath in get_all_smali_files(self.decompiled_path):
                if os.path.basename(filepath).lower() == base:
                    return filepath
        except Exception:  # pragma: no cover - defensive
            return None
        return None
