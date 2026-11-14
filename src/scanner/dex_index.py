"""Single-pass structural DEX index shared by every analyzer check.

Why this module exists
----------------------
Every check used to re-read the APK zip and re-run an ASCII regex over the
raw dex bytes. On an 84 MB / 9-dex APK that is:

    read zip          6x  ~8.4s
    ASCII extraction  ~126x (8 packer signatures x 9 dex, plus license,
                             iap and security)  ~60s

The `id(dex_bytes)` blob cache in `packer_check` never hit because each
`get_all_dex_bytes()` call returns fresh `bytes` objects, so the cache was
cleared long before a signature could reuse it.

This module parses each dex header *once* and answers the questions the
checks actually ask:

  * which class descriptors exist            -> `classes`
  * which class defines method X             -> `method_owners`
  * does the raw blob contain string Y       -> `string_hits`

Parsing the `string_ids` / `type_ids` / `method_ids` tables directly is
~15x faster than the ASCII sweep and gives exact owner classes, which also
lets the root check drop false positives such as Kotlin's
`FilePathComponents.isRooted` (a filesystem helper, not a root check).

The parser is deliberately defensive: a malformed or truncated dex simply
yields an empty index instead of raising, so analysis degrades to "nothing
detected" rather than crashing.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEX_MAGIC = b"dex\n"
_NO_INDEX = 0xFFFFFFFF


# ============================================================
# LOW-LEVEL READERS
# ============================================================
def _uleb128(buf: bytes, off: int) -> tuple[int, int]:
    """Decode an unsigned LEB128 value; return (value, next_offset)."""
    result = 0
    shift = 0
    while True:
        b = buf[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, off
        shift += 7


def _read_mutf8(buf: bytes, off: int) -> bytes:
    """Return the raw string_data payload at `off` (length prefix skipped)."""
    length, pos = _uleb128(buf, off)
    return buf[pos:pos + length]


def _is_printable(byte: int) -> bool:
    return 0x20 <= byte <= 0x7E


def _expand_run(raw: bytes, idx: int, needle_len: int) -> str:
    """Grow `idx` outwards over printable bytes to recover the full token."""
    start = idx
    while start > 0 and _is_printable(raw[start - 1]):
        start -= 1
    end = idx + needle_len
    n = len(raw)
    while end < n and _is_printable(raw[end]):
        end += 1
    return raw[start:end].decode("latin-1", "ignore")


# ============================================================
# INDEX
# ============================================================
@dataclass
class DexIndex:
    """Structural view over every dex in one APK."""

    classes: list[str] = field(default_factory=list)
    # Parallel to `classes`, precomputed so lookups don't re-lower 67k names.
    classes_lower: list[str] = field(default_factory=list)
    # lowercased method name -> {owner class descriptors}
    method_owners: dict[str, set[str]] = field(default_factory=dict)
    # lowercased method name -> original-case spelling
    method_display: dict[str, str] = field(default_factory=dict)
    # lowercased needle -> original-case occurrence recovered from the blob
    string_hits: dict[str, str] = field(default_factory=dict)
    dex_count: int = 0

    # ------------------------------------------------------------------
    def owners_of(self, method_name: str) -> set[str]:
        """Owner classes of a method, matched case-insensitively."""
        return self.method_owners.get(method_name.lower(), set())

    def display_name(self, method_name: str) -> str:
        return self.method_display.get(method_name.lower(), method_name)

    def has_string(self, needle: str) -> bool:
        return needle.lower() in self.string_hits

    def class_starting_with(self, prefix: str) -> str | None:
        """First class descriptor beginning with `prefix` (case-insensitive)."""
        return self.classes_starting_with_any((prefix,))

    def classes_starting_with_any(
        self, prefixes: tuple[str, ...] | list[str],
    ) -> str | None:
        """First class matching any prefix, in one pass."""
        pls = tuple(p.lower() for p in prefixes)
        if not pls:
            return None
        for cname, cl in zip(self.classes, self.classes_lower, strict=False):
            if cl.startswith(pls):
                return cname
        return None

    def class_containing(self, needle: str) -> str | None:
        """First class descriptor containing `needle` (case-insensitive)."""
        return self.class_containing_any((needle,))

    def class_containing_any(
        self, needles: tuple[str, ...] | list[str],
    ) -> str | None:
        """First class containing any needle, in one pass."""
        nls = tuple(n.lower() for n in needles)
        if not nls:
            return None
        for cname, cl in zip(self.classes, self.classes_lower, strict=False):
            for nl in nls:
                if nl in cl:
                    return cname
        return None

    def classes_containing(self, needle: str) -> list[str]:
        nl = needle.lower()
        return [
            c for c, cl in zip(self.classes, self.classes_lower, strict=False)
            if nl in cl
        ]

    def classes_containing_any(
        self, needles: tuple[str, ...] | list[str],
    ) -> list[str]:
        nls = tuple(n.lower() for n in needles)
        if not nls:
            return []
        return [
            c for c, cl in zip(self.classes, self.classes_lower, strict=False)
            if any(nl in cl for nl in nls)
        ]

    def class_matches(self, regex) -> list[str]:
        return [c for c in self.classes if regex.search(c)]

    @property
    def is_empty(self) -> bool:
        return not self.classes and not self.method_owners


# ============================================================
# BUILDER
# ============================================================
def _parse_one_dex(
    raw: bytes,
    method_exact: set[bytes],
    method_prefixes: tuple[bytes, ...],
    string_needles: tuple[bytes, ...],
    index: DexIndex,
) -> None:
    """Parse one dex and merge into `index`. Never raises."""
    if len(raw) < 0x70 or raw[:4] != _DEX_MAGIC:
        return

    try:
        sid_size, sid_off, tid_size, tid_off = struct.unpack_from(
            "<IIII", raw, 0x38
        )
        mid_size, mid_off = struct.unpack_from("<II", raw, 0x58)
    except struct.error:
        return

    # --- string_ids resolved lazily + memoized ---
    # Precomputing (offset, length) for all ~376k strings cost ~1.1s and the
    # only consumer was the type table; resolving on demand with a memo is
    # ~2x faster overall.
    str_memo: dict[int, bytes] = {}

    def string_bytes(sidx: int) -> bytes:
        cached = str_memo.get(sidx)
        if cached is not None:
            return cached
        if sidx >= sid_size:
            str_memo[sidx] = b""
            return b""
        try:
            data_off = struct.unpack_from("<I", raw, sid_off + sidx * 4)[0]
        except struct.error:
            str_memo[sidx] = b""
            return b""
        if data_off >= len(raw):
            str_memo[sidx] = b""
            return b""
        try:
            length, pos = _uleb128(raw, data_off)
        except IndexError:
            str_memo[sidx] = b""
            return b""
        if pos + length > len(raw):
            str_memo[sidx] = b""
            return b""
        value = raw[pos:pos + length]
        str_memo[sidx] = value
        return value

    # --- type_ids -> class descriptors ---
    class_by_type: dict[int, str] = {}
    try:
        for t in range(tid_size):
            sidx = struct.unpack_from("<I", raw, tid_off + t * 4)[0]
            desc = string_bytes(sidx)
            if len(desc) >= 3 and desc[:1] == b"L" and desc[-1:] == b";":
                cname = desc.decode("latin-1", "ignore")
                class_by_type[t] = cname
                index.classes.append(cname)
                index.classes_lower.append(cname.lower())
    except (struct.error, IndexError):
        return

    # --- method_ids -> owners, but only for needles we care about ---
    # Walk method_ids once and resolve each name lazily (memoized): ~460k
    # method entries but only ~60k distinct strings, so the memo removes
    # the repeated uleb decode that made the naive pass 2.5s. The candidate
    # test itself is memoized per string index too: the same name repeats
    # across every overload, so this cuts 1.56s -> 1.11s.
    if method_exact or method_prefixes:
        candidate_memo: dict[int, bool] = {}
        try:
            for i in range(mid_size):
                base = mid_off + i * 8
                class_idx, _proto, name_idx = struct.unpack_from(
                    "<HHI", raw, base
                )
                is_candidate = candidate_memo.get(name_idx)
                if is_candidate is None:
                    nm = string_bytes(name_idx).lower()
                    is_candidate = bool(
                        nm
                        and (
                            nm in method_exact
                            or nm.startswith(method_prefixes)
                        )
                    )
                    candidate_memo[name_idx] = is_candidate
                if not is_candidate:
                    continue
                owner = class_by_type.get(class_idx)
                if not owner:
                    continue
                nm_bytes = string_bytes(name_idx)
                key = nm_bytes.lower().decode("latin-1", "ignore")
                index.method_owners.setdefault(key, set()).add(owner)
                index.method_display.setdefault(
                    key, nm_bytes.decode("latin-1", "ignore")
                )
        except (struct.error, IndexError):
            pass

    # --- raw string needles (paths, marker text) ---
    # String data lives after the lowest string_data offset, so scanning from
    # there instead of the whole file covers ~25 MB instead of ~62 MB with
    # identical results (0.94s -> 0.41s on the 9-dex benchmark APK).
    if string_needles:
        try:
            first_off = min(
                struct.unpack_from("<I", raw, sid_off + i * 4)[0]
                for i in range(sid_size)
            )
        except (struct.error, ValueError):
            first_off = 0
        region = raw[first_off:] if 0 < first_off < len(raw) else raw
        lower = region.lower()
        for needle in string_needles:
            key = needle.decode("latin-1", "ignore").lower()
            if key in index.string_hits:
                continue
            idx = lower.find(needle)
            if idx < 0:
                continue
            index.string_hits[key] = _expand_run(
                region, idx, len(needle)
            )

    index.dex_count += 1


def build_dex_index(
    dex_entries,
    method_exact: set[str] | None = None,
    method_prefixes: tuple[str, ...] = (),
    string_needles: tuple[str, ...] = (),
) -> DexIndex:
    """Build a :class:`DexIndex` from `[(name, bytes), ...]`."""
    index = DexIndex()
    if not dex_entries:
        return index

    exact = {s.lower().encode() for s in (method_exact or ())}
    prefixes = tuple(s.lower().encode() for s in method_prefixes)
    needles = tuple(s.lower().encode() for s in string_needles)

    for _name, raw in dex_entries:
        if not raw:
            continue
        try:
            _parse_one_dex(raw, exact, prefixes, needles, index)
        except Exception as e:  # defensive: never break analysis
            logger.debug("DexIndex: skipping a dex (%s)", e)
    return index
