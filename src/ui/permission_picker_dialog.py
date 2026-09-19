"""
Permission Picker — dialog chọn permissions để xóa.

v4 (2026):
  - Robust classifier: full name + short name + progressive suffix.
  - Panel "Sẽ bị xóa" hiển thị list permission đã chọn.
  - Confirmation dialog chi tiết trước khi apply.
  - Fixed: checkbox render đúng (bỏ AutoTristate).
"""
from __future__ import annotations

import logging
import os

from androguard.core.apk import APK
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QFrame,
)

logger = logging.getLogger(__name__)


# ============================================================
# PERMISSION DATABASE (key = SHORT name)
# ============================================================
_PERMISSION_DB: dict[str, tuple[str, str, str]] = {
    # ============ DANGEROUS: LOCATION ============
    "ACCESS_FINE_LOCATION": ("📍", "dangerous", "Vị trí GPS chính xác"),
    "ACCESS_COARSE_LOCATION": ("📍", "dangerous", "Vị trí GPS tương đối"),
    "ACCESS_BACKGROUND_LOCATION": ("📍", "dangerous", "Vị trí khi chạy nền"),
    "ACCESS_MEDIA_LOCATION": ("📍", "dangerous", "Vị trí từ media metadata"),

    # ============ DANGEROUS: STORAGE ============
    "READ_EXTERNAL_STORAGE": ("📁", "dangerous", "Đọc file bộ nhớ ngoài"),
    "WRITE_EXTERNAL_STORAGE": ("💾", "dangerous", "Ghi file bộ nhớ ngoài"),
    "MANAGE_EXTERNAL_STORAGE": ("🗂️", "special", "Quản lý toàn bộ bộ nhớ ngoài"),
    "READ_MEDIA_IMAGES": ("🖼️", "dangerous", "Đọc ảnh (Android 13+)"),
    "READ_MEDIA_VIDEO": ("🎬", "dangerous", "Đọc video (Android 13+)"),
    "READ_MEDIA_AUDIO": ("🎵", "dangerous", "Đọc audio (Android 13+)"),
    "READ_MEDIA_VISUAL_USER_SELECTED": ("🖼️", "dangerous", "Đọc ảnh user chọn"),

    # ============ DANGEROUS: CAMERA/MIC ============
    "CAMERA": ("📷", "dangerous", "Sử dụng camera"),
    "RECORD_AUDIO": ("🎤", "dangerous", "Ghi âm microphone"),

    # ============ DANGEROUS: CONTACTS ============
    "READ_CONTACTS": ("👥", "dangerous", "Đọc danh bạ"),
    "WRITE_CONTACTS": ("✏️", "dangerous", "Sửa danh bạ"),
    "GET_ACCOUNTS": ("👤", "dangerous", "Đọc tài khoản thiết bị"),

    # ============ DANGEROUS: PHONE ============
    "READ_PHONE_STATE": ("📱", "dangerous", "Đọc trạng thái ĐT"),
    "READ_PHONE_NUMBERS": ("📱", "dangerous", "Đọc số điện thoại"),
    "CALL_PHONE": ("📞", "dangerous", "Gọi điện trực tiếp"),
    "ANSWER_PHONE_CALLS": ("📞", "dangerous", "Tự trả lời cuộc gọi"),
    "READ_CALL_LOG": ("📜", "dangerous", "Đọc lịch sử gọi"),
    "WRITE_CALL_LOG": ("📝", "dangerous", "Sửa lịch sử gọi"),
    "ADD_VOICEMAIL": ("📧", "dangerous", "Thêm voicemail"),
    "USE_SIP": ("☎️", "dangerous", "Gọi VoIP SIP"),
    "PROCESS_OUTGOING_CALLS": ("📤", "dangerous", "Xử lý cuộc gọi đi"),
    "ACCEPT_HANDOVER": ("📞", "dangerous", "Chuyển cuộc gọi"),

    # ============ DANGEROUS: SMS/MMS ============
    "READ_SMS": ("💬", "dangerous", "Đọc tin nhắn SMS"),
    "SEND_SMS": ("✉️", "dangerous", "Gửi SMS"),
    "RECEIVE_SMS": ("📨", "dangerous", "Nhận SMS"),
    "RECEIVE_MMS": ("📩", "dangerous", "Nhận MMS"),
    "RECEIVE_WAP_PUSH": ("📬", "dangerous", "Nhận WAP push"),

    # ============ DANGEROUS: CALENDAR ============
    "READ_CALENDAR": ("📅", "dangerous", "Đọc lịch"),
    "WRITE_CALENDAR": ("🗓️", "dangerous", "Sửa lịch"),

    # ============ DANGEROUS: SENSORS ============
    "BODY_SENSORS": ("❤️", "dangerous", "Cảm biến cơ thể"),
    "BODY_SENSORS_BACKGROUND": ("❤️", "dangerous", "Cảm biến (nền)"),
    "ACTIVITY_RECOGNITION": ("🏃", "dangerous", "Nhận diện hoạt động"),

    # ============ DANGEROUS: NEARBY / BT ============
    "BLUETOOTH_CONNECT": ("📶", "dangerous", "Kết nối Bluetooth"),
    "BLUETOOTH_SCAN": ("🔍", "dangerous", "Quét Bluetooth"),
    "BLUETOOTH_ADVERTISE": ("📢", "dangerous", "Quảng cáo Bluetooth"),
    "NEARBY_WIFI_DEVICES": ("📡", "dangerous", "WiFi lân cận"),
    "UWB_RANGING": ("📡", "dangerous", "Đo khoảng cách UWB"),

    # ============ DANGEROUS: NOTIFICATIONS ============
    "POST_NOTIFICATIONS": ("🔔", "dangerous", "Đăng thông báo (Android 13+)"),

    # ============ SPECIAL ============
    "WRITE_SETTINGS": ("⚙️", "special", "Sửa cài đặt hệ thống"),
    "SYSTEM_ALERT_WINDOW": ("🪟", "special", "Vẽ overlay trên app khác"),
    "PACKAGE_USAGE_STATS": ("📊", "special", "Đọc lịch sử dùng app"),
    "REQUEST_INSTALL_PACKAGES": ("📦", "special", "Yêu cầu cài APK khác"),
    "REQUEST_DELETE_PACKAGES": ("🗑️", "special", "Yêu cầu xóa APK khác"),
    "SCHEDULE_EXACT_ALARM": ("⏰", "special", "Báo thức chính xác"),
    "USE_EXACT_ALARM": ("⏰", "special", "Dùng báo thức chính xác"),
    "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS": ("🔋", "special", "Bỏ qua tối ưu pin"),

    # ============ NORMAL: NETWORK ============
    "INTERNET": ("🌐", "normal", "⚠️ Truy cập Internet — xóa có thể hỏng app"),
    "ACCESS_NETWORK_STATE": ("📶", "normal", "Kiểm tra trạng thái mạng"),
    "ACCESS_WIFI_STATE": ("📡", "normal", "Kiểm tra trạng thái WiFi"),
    "CHANGE_WIFI_STATE": ("📡", "normal", "Bật/tắt WiFi"),
    "CHANGE_NETWORK_STATE": ("🔌", "normal", "Đổi trạng thái mạng"),
    "CHANGE_WIFI_MULTICAST_STATE": ("📡", "normal", "WiFi multicast"),
    "ACCESS_LOCATION_EXTRA_COMMANDS": ("📍", "normal", "Lệnh vị trí bổ sung"),

    # ============ NORMAL: SYSTEM ============
    "VIBRATE": ("📳", "normal", "Rung thiết bị"),
    "WAKE_LOCK": ("🔓", "normal", "Giữ máy không ngủ"),
    "RECEIVE_BOOT_COMPLETED": ("🚀", "normal", "Tự chạy khi khởi động"),
    "FOREGROUND_SERVICE": ("🎯", "normal", "Chạy foreground service"),
    "FOREGROUND_SERVICE_DATA_SYNC": ("🔄", "normal", "FG sync data"),
    "FOREGROUND_SERVICE_MEDIA_PLAYBACK": ("▶️", "normal", "FG media"),
    "FOREGROUND_SERVICE_LOCATION": ("📍", "normal", "FG location"),
    "FOREGROUND_SERVICE_CONNECTED_DEVICE": ("🔗", "normal", "FG device"),
    "FOREGROUND_SERVICE_MEDIA_PROJECTION": ("📺", "normal", "FG projection"),
    "FOREGROUND_SERVICE_PHONE_CALL": ("📞", "normal", "FG phone call"),

    # ============ NORMAL: MISC ============
    "SET_WALLPAPER": ("🖼️", "normal", "Đặt hình nền"),
    "SET_WALLPAPER_HINTS": ("🖼️", "normal", "Gợi ý hình nền"),
    "EXPAND_STATUS_BAR": ("📊", "normal", "Mở rộng status bar"),
    "KILL_BACKGROUND_PROCESSES": ("🛑", "normal", "Kill tiến trình nền"),
    "REORDER_TASKS": ("📋", "normal", "Sắp xếp lại task"),
    "GET_TASKS": ("📋", "normal", "Đọc danh sách task"),
    "MODIFY_AUDIO_SETTINGS": ("🔊", "normal", "Đổi cài đặt âm thanh"),
    "NFC": ("📻", "normal", "Sử dụng NFC"),
    "BLUETOOTH": ("📶", "normal", "Sử dụng Bluetooth"),
    "BLUETOOTH_ADMIN": ("📶", "normal", "Quản trị Bluetooth"),
    "FLASHLIGHT": ("🔦", "normal", "Đèn flash"),
    "INSTALL_SHORTCUT": ("📌", "normal", "Tạo shortcut"),
    "UNINSTALL_SHORTCUT": ("📌", "normal", "Xóa shortcut"),
    "DISABLE_KEYGUARD": ("🔓", "normal", "Tắt khóa màn hình"),
    "QUERY_ALL_PACKAGES": ("📦", "normal", "Đọc ds app đã cài"),
    "BROADCAST_STICKY": ("📻", "normal", "Broadcast sticky"),
    "SET_TIME_ZONE": ("⏰", "normal", "Đặt timezone"),
    "SET_ALARM": ("⏰", "normal", "Đặt alarm"),
    "WRITE_SYNC_SETTINGS": ("⚙️", "normal", "Sửa sync settings"),
    "READ_SYNC_SETTINGS": ("⚙️", "normal", "Đọc sync settings"),
    "READ_SYNC_STATS": ("⚙️", "normal", "Đọc sync stats"),
    "USE_FULL_SCREEN_INTENT": ("📺", "normal", "Full screen intent"),
    "BROADCAST_SMS": ("📨", "normal", "Broadcast SMS"),
    "RECEIVE_EMERGENCY_BROADCAST": ("🚨", "normal", "Emergency broadcast"),

    # ============ NORMAL: GOOGLE / VENDOR ============
    "AD_ID": ("🎯", "normal", "Advertising ID (Google Ads)"),
    "ACCESS_ADSERVICES_AD_ID": ("🎯", "normal", "Ads Services: Ad ID"),
    "ACCESS_ADSERVICES_ATTRIBUTION": ("🎯", "normal", "Ads Services: Attribution"),
    "ACCESS_ADSERVICES_CUSTOM_AUDIENCE": ("🎯", "normal", "Ads: Custom Audience"),
    "ACCESS_ADSERVICES_TOPICS": ("🎯", "normal", "Ads Services: Topics"),
    "BIND_GET_INSTALL_REFERRER_SERVICE": ("🔗", "normal", "Đọc install referrer"),
    "DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION": ("📻", "normal", "Dynamic receiver"),
    "RECEIVE": ("📨", "normal", "Nhận broadcast (C2DM)"),
    "C2D_MESSAGE": ("📨", "normal", "Cloud to Device Message"),
    "WRITE_INTERNAL_STORAGE": ("📁", "normal", "Ghi bộ nhớ trong"),
    "READ_INTERNAL_STORAGE": ("📁", "normal", "Đọc bộ nhớ trong"),
    "ATTEST": ("🔒", "normal", "Attest (safety net)"),

    # ============ SIGNATURE ============
    "BILLING": ("💳", "signature", "Mua hàng trong app (IAP)"),
    "CHECK_LICENSE": ("🔑", "signature", "Kiểm tra giấy phép Google Play"),
    "INSTALL_PACKAGES": ("📦", "signature", "Cài đặt APK (system app)"),
    "DELETE_PACKAGES": ("🗑️", "signature", "Gỡ cài đặt APK (system app)"),
    "WRITE_SECURE_SETTINGS": ("🔒", "signature", "Sửa settings bảo mật"),
    "DUMP": ("💾", "signature", "Dump hệ thống"),
    "READ_LOGS": ("📜", "signature", "Đọc logs hệ thống"),
    "CAPTURE_AUDIO_OUTPUT": ("🎤", "signature", "Capture audio output"),
    "CAPTURE_VIDEO_OUTPUT": ("🎬", "signature", "Capture video output"),
    "MODIFY_AUDIO_ROUTING": ("🔊", "signature", "Sửa audio routing"),
    "CHANGE_CONFIGURATION": ("⚙️", "signature", "Đổi cấu hình"),
    "DEVICE_POWER": ("🔋", "signature", "Quản lý nguồn"),
    "REBOOT": ("🔄", "signature", "Khởi động lại"),
    "SHUTDOWN": ("⏻", "signature", "Tắt máy"),
    "MASTER_CLEAR": ("💥", "signature", "Wipe data"),
    "MOUNT_FORMAT_FILESYSTEMS": ("💾", "signature", "Format filesystem"),
    "MOUNT_UNMOUNT_FILESYSTEMS": ("💾", "signature", "Mount/unmount FS"),
    "SET_PREFERRED_APPLICATIONS": ("🎯", "signature", "Đặt app ưu tiên"),
    "FORCE_BACK": ("⬅️", "signature", "Force back"),
    "MANAGE_APP_TOKENS": ("🎫", "signature", "Quản lý app tokens"),
    "ACCOUNT_MANAGER": ("👤", "signature", "Account manager"),
    "WRITE_APN_SETTINGS": ("📶", "signature", "Sửa APN settings"),
    "MANAGE_USB": ("🔌", "signature", "Quản lý USB"),
    "MANAGE_USERS": ("👥", "signature", "Quản lý user"),
    "INTERACT_ACROSS_USERS": ("👥", "signature", "Cross-user"),
}


# ============================================================
# ROBUST CLASSIFIER
# ============================================================
def _classify(perm: str) -> tuple[str, str, str]:
    """
    Return (emoji, category, description).
    Handles full name + short name + progressive suffix.
    """
    # 1. Exact full-name match
    if perm in _PERMISSION_DB:
        return _PERMISSION_DB[perm]

    # 2. Short name (last segment)
    short = perm.rsplit(".", 1)[-1]
    if short in _PERMISSION_DB:
        return _PERMISSION_DB[short]

    # 3. Progressive suffixes
    parts = perm.split(".")
    for i in range(1, len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in _PERMISSION_DB:
            return _PERMISSION_DB[suffix]

    # 4. Fallback heuristic
    if ".permission." in perm:
        return ("❔", "normal", f"Android permission: {short}")
    if perm.startswith("com.") or perm.startswith("net."):
        return ("❔", "normal", f"Vendor permission: {short}")

    return ("❔", "other", "(Không có mô tả)")


_CATEGORY_ORDER = (
    "dangerous", "special", "normal", "signature", "other",
)

_CATEGORY_LABELS = {
    "dangerous": "🔴 DANGEROUS — Yêu cầu runtime permission",
    "special": "🟠 SPECIAL — Truy cập hệ thống nhạy cảm",
    "normal": "🟢 NORMAL — Cấp tự động khi cài",
    "signature": "⚙️ SIGNATURE — Yêu cầu cùng chữ ký",
    "other": "❔ KHÁC — Không có trong database",
}

_CATEGORY_EMOJI = {
    "dangerous": "🔴",
    "special": "🟠",
    "normal": "🟢",
    "signature": "⚙️",
    "other": "❔",
}


# ============================================================
# DIALOG
# ============================================================
class PermissionPickerDialog(QDialog):
    """Dialog chọn permission để XÓA khỏi AndroidManifest.xml."""

    def __init__(
        self,
        apk_path: str,
        package: str = "",
        app_name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.apk_path = apk_path
        self.package = package
        self.app_name = app_name
        self.item_map: dict[str, QTreeWidgetItem] = {}
        self.summary: QLabel | None = None
        self.warn_label: QLabel | None = None

        self.setWindowTitle(
            f"Quản lý Permissions - {app_name or package}"
        )

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.resize(
                min(760, int(avail.width() * 0.55)),
                min(760, int(avail.height() * 0.9)),
            )
            self.setMinimumSize(560, 500)

        self.permissions = self._load_permissions()

        # Debug classification (nếu bật LP_PERM_DEBUG)
        if os.environ.get("LP_PERM_DEBUG", "").strip():
            self._debug_log()

        self._init_ui()

    # ============================================================
    # LOAD + DEBUG
    # ============================================================
    def _load_permissions(self) -> list[str]:
        try:
            apk = APK(self.apk_path)
            perms = list(apk.get_permissions() or [])
            return sorted(set(perms))
        except Exception as e:
            logger.warning("Không đọc được permissions: %s", e)
            return []

    def _debug_log(self) -> None:
        counts = {
            "dangerous": 0, "special": 0, "normal": 0,
            "signature": 0, "other": 0,
        }
        logger.info(
            "Permission classification (%d perms):",
            len(self.permissions),
        )
        for perm in self.permissions:
            emoji, cat, _ = _classify(perm)
            counts[cat] = counts.get(cat, 0) + 1
            logger.info("  [%-9s] %s", cat, perm)
        logger.info("Category counts: %s", counts)

    # ============================================================
    # UI
    # ============================================================
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QLabel(
            f"<b style='font-size:14px;'>"
            f"📋 {self.app_name or self.package or 'APK'}</b>"
        )
        layout.addWidget(header)

        sub = QLabel(
            f"<span style='color:#8b949e;'>Tìm thấy "
            f"<b style='color:#58a6ff;'>{len(self.permissions)}"
            f"</b> permission trong AndroidManifest.xml. "
            f"<b>Tick</b> các permission muốn "
            f"<b style='color:#f85149;'>XÓA</b>.</span>"
        )
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Preset buttons
        preset_row = QHBoxLayout()
        for label, slot in [
            ("🔴 Chỉ Dangerous", self._preset_dangerous),
            ("🟢 Normal + Signature", self._preset_safe),
            ("✔️ Chọn tất cả", self._preset_all),
            ("✖️ Bỏ chọn", self._preset_none),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Permission", "Mô tả"])
        self.tree.setColumnWidth(0, 340)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        # Custom checkbox indicator
        self.tree.setStyleSheet("""
            QTreeWidget::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #30363d;
                border-radius: 3px;
                background-color: #0d1117;
            }
            QTreeWidget::indicator:checked {
                background-color: #238636;
                border-color: #2ea043;
            }
            QTreeWidget::indicator:unchecked:hover {
                border-color: #58a6ff;
            }
        """)

        # Warning banner
        self.warn_label = QLabel("")
        self.warn_label.setStyleSheet(
            "background-color:#3d1c1c; border:1px solid #f85149;"
            "border-radius:6px; color:#f0f6fc; padding:8px;"
            "font-size:11px;"
        )
        self.warn_label.setWordWrap(True)
        self.warn_label.setVisible(False)

        # === SELECTED LIST PANEL ===
        self.selected_panel = QFrame()
        self.selected_panel.setStyleSheet(
            "QFrame { background-color: #0d1117; "
            "border: 1px solid #30363d; border-radius: 6px; }"
        )
        sel_layout = QVBoxLayout(self.selected_panel)
        sel_layout.setContentsMargins(10, 8, 10, 8)
        sel_layout.setSpacing(4)

        sel_header = QLabel(
            "<b style='color:#f0f6fc; font-size:11px;'>"
            "🗑️ Sẽ bị xóa:</b>"
        )
        sel_layout.addWidget(sel_header)

        self.selected_text = QLabel("(Chưa chọn permission nào)")
        self.selected_text.setStyleSheet(
            "color:#8b949e; font-size:11px;"
            "font-family: 'Cascadia Code', Consolas, monospace;"
        )
        self.selected_text.setWordWrap(True)
        self.selected_text.setMinimumHeight(50)
        sel_layout.addWidget(self.selected_text)

        # Summary
        self.summary = QLabel("Đã chọn: 0 permission")
        self.summary.setStyleSheet(
            "color:#58a6ff; font-size:11px; font-weight:bold;"
        )

        # Build tree
        self._build_tree()
        layout.addWidget(self.tree, 2)
        layout.addWidget(self.selected_panel, 0)
        layout.addWidget(self.warn_label)
        layout.addWidget(self.summary)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)

        apply_btn = QPushButton("🗑️ Xóa permission đã chọn")
        apply_btn.setStyleSheet(
            "background-color:#da3633; color:white;"
            "font-weight:bold; padding:8px 20px; border-radius:6px;"
        )
        apply_btn.clicked.connect(self._on_apply)
        btns.addWidget(apply_btn)
        layout.addLayout(btns)

    # ============================================================
    # TREE BUILD
    # ============================================================
    def _build_tree(self) -> None:
        self.tree.blockSignals(True)

        by_cat: dict[str, list[tuple[str, str, str, str]]] = {}
        for perm in self.permissions:
            emoji, cat, desc = _classify(perm)
            short = perm.rsplit(".", 1)[-1]
            by_cat.setdefault(cat, []).append((perm, short, emoji, desc))

        for cat in _CATEGORY_ORDER:
            items = by_cat.get(cat, [])
            if not items:
                continue

            grp = QTreeWidgetItem(
                self.tree,
                [_CATEGORY_LABELS[cat], f"({len(items)})"],
            )
            grp.setExpanded(cat in ("dangerous", "special"))
            font = grp.font(0)
            font.setBold(True)
            grp.setFont(0, font)

            for perm, short, emoji, desc in items:
                item = QTreeWidgetItem(
                    grp, [f"{emoji}  {short}", desc]
                )
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setToolTip(0, perm)
                self.item_map[perm] = item

        self.tree.blockSignals(False)
        self._update_summary()

    # ============================================================
    # SUMMARY + WARNINGS
    # ============================================================
    def _update_summary(self) -> None:
        if self.summary is None:
            return
        selected = self.get_selected_permissions()
        n = len(selected)
        self.summary.setText(f"Đã chọn: {n} permission")

        # Update selected panel
        if hasattr(self, "selected_text"):
            if not selected:
                self.selected_text.setText(
                    "(Chưa chọn permission nào)"
                )
                self.selected_text.setStyleSheet(
                    "color:#8b949e; font-size:11px;"
                    "font-family: 'Cascadia Code', Consolas, monospace;"
                )
            else:
                lines = []
                for perm in selected:
                    _, cat, _ = _classify(perm)
                    emoji = _CATEGORY_EMOJI.get(cat, "•")
                    short = perm.rsplit(".", 1)[-1]
                    lines.append(f"{emoji} {short}")
                self.selected_text.setText("\n".join(lines))
                self.selected_text.setStyleSheet(
                    "color:#f0f6fc; font-size:11px;"
                    "font-family: 'Cascadia Code', Consolas, monospace;"
                )

    def _check_warnings(self) -> None:
        if self.warn_label is None:
            return
        selected = self.get_selected_permissions()
        warns = []
        for perm in selected:
            short = perm.rsplit(".", 1)[-1]
            if short == "INTERNET":
                warns.append(
                    "⚠️ Đã chọn xóa INTERNET — app có thể "
                    "không kết nối mạng."
                )
            elif short == "BILLING":
                warns.append(
                    "⚠️ Đã chọn xóa BILLING — IAP sẽ không chạy."
                )
        if warns:
            self.warn_label.setText("\n".join(warns))
            self.warn_label.setVisible(True)
        else:
            self.warn_label.setVisible(False)

    # ============================================================
    # SELECTION
    # ============================================================
    def _iter_categories(self) -> dict[str, list[str]]:
        by_cat: dict[str, list[str]] = {}
        for perm in self.permissions:
            _, cat, _ = _classify(perm)
            by_cat.setdefault(cat, []).append(perm)
        return by_cat

    def _preset_dangerous(self) -> None:
        by_cat = self._iter_categories()
        for perm in by_cat.get("dangerous", []):
            self.item_map[perm].setCheckState(
                0, Qt.CheckState.Checked
            )

    def _preset_safe(self) -> None:
        by_cat = self._iter_categories()
        safe = (
            by_cat.get("normal", [])
            + by_cat.get("signature", [])
        )
        for perm in safe:
            self.item_map[perm].setCheckState(
                0, Qt.CheckState.Checked
            )

    def _preset_all(self) -> None:
        for item in self.item_map.values():
            item.setCheckState(0, Qt.CheckState.Checked)

    def _preset_none(self) -> None:
        for item in self.item_map.values():
            item.setCheckState(0, Qt.CheckState.Unchecked)

    def _on_item_changed(self, _item, _col) -> None:
        self._update_summary()
        self._check_warnings()

    # ============================================================
    # PUBLIC
    # ============================================================
    def get_selected_permissions(self) -> list[str]:
        return [
            perm for perm, item in self.item_map.items()
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    # ============================================================
    # APPLY — with detailed confirmation
    # ============================================================
    def _on_apply(self) -> None:
        selected = self.get_selected_permissions()
        if not selected:
            QMessageBox.information(
                self, "Chưa chọn",
                "Bạn chưa chọn permission nào để xóa.",
            )
            return

        # Build detailed confirmation
        dangerous_selected = []
        lines = []
        for perm in selected:
            _, cat, _ = _classify(perm)
            short = perm.rsplit(".", 1)[-1]
            emoji = _CATEGORY_EMOJI.get(cat, "•")
            lines.append(f"  {emoji}  {short}")
            if short in ("INTERNET", "ACCESS_NETWORK_STATE"):
                dangerous_selected.append(short)

        msg_text = (
            f"Bạn sẽ XÓA <b>{len(selected)}</b> permission:\n\n"
            + "<br>".join(lines)
        )

        if dangerous_selected:
            msg_text += (
                f"\n\n<b style='color:#f85149;'>⚠️ CẢNH BÁO:</b> "
                f"Bạn đang xóa permission quan trọng: "
                f"<b>{', '.join(dangerous_selected)}</b>. "
                f"App có thể ngừng hoạt động."
            )

        reply = QMessageBox.question(
            self, "Xác nhận xóa permission",
            msg_text,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.accept()