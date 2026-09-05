from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from pdrive_desktop.domain.drive import DriveNode, DrivePath, NodeKind
from pdrive_desktop.domain.transfer import TransferJob, TransferKind, TransferStatus
from pdrive_desktop.presentation.controller import DesktopController


class PDriveApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.pdrive.Desktop")

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_string(
            ".pdrive-sidebar { background: #f6f4ff; padding: 12px; }"
            ".brand-title { font-size: 18px; font-weight: 700; }"
            ".brand-subtitle { color: alpha(currentColor, .58); font-size: 12px; }"
            ".nav-button { border-radius: 10px; padding: 10px 12px; }"
            ".nav-button.active { background: alpha(#6d4aff, .13); "
            "color: #5b3fd6; font-weight: 700; }"
            ".privacy-card { background: alpha(#6d4aff, .08); "
            "border-radius: 12px; padding: 12px; }"
            ".privacy-badge { color: #5b3fd6; font-weight: 700; }"
            ".content-toolbar { padding: 12px 18px; "
            "border-bottom: 1px solid alpha(currentColor, .08); }"
            ".breadcrumb { font-size: 20px; font-weight: 700; }"
            ".file-list { background: transparent; margin: 12px 18px; }"
            ".file-row { padding: 5px 8px; border-radius: 10px; }"
            ".selection-bar { padding: 8px 18px; border-top: 1px solid alpha(currentColor, .08); }"
            ".status-text { color: alpha(currentColor, .58); font-size: 12px; }"
        )
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self)
        window.present()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs, title="PDrive", default_width=1180, default_height=760)
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
        self._list.add_css_class("file-list")
        self._status_label = Gtk.Label(label="Bağlantı bekleniyor")
        self._status_label.add_css_class("dim-label")
        self._progress = Gtk.ProgressBar(visible=False)
        self._pulse_source: int | None = None
        self._busy = False
        self._transfer_busy = False
        self._retry_transfer_id: str | None = None
        self._current_path = DrivePath.parse("/my-files")
        self._section_root = self._current_path
        self._nav_buttons: dict[str, Gtk.Button] = {}
        self._row_nodes: dict[Gtk.ListBoxRow, DriveNode] = {}
        self._connect_button = Gtk.Button(label="Güvenli bağlan")
        self._connect_button.add_css_class("suggested-action")
        self._refresh_button = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text="Yenile"
        )
        self._back_button = Gtk.Button(
            icon_name="go-up-symbolic", tooltip_text="Üst klasör"
        )
        self._upload_button = Gtk.Button(
            icon_name="document-send-symbolic", tooltip_text="Dosya yükle"
        )
        self._upload_folder_button = Gtk.Button(
            icon_name="folder-new-symbolic", tooltip_text="Klasör yükle"
        )
        self._backup_button = Gtk.Button(
            icon_name="emblem-synchronizing-symbolic",
            tooltip_text="Klasörü tek yönlü güvenli yedekle",
        )
        self._download_button = Gtk.Button(
            icon_name="document-save-symbolic", tooltip_text="Seçilenleri indir"
        )
        self._trash_button = Gtk.Button(
            icon_name="user-trash-symbolic", tooltip_text="Çöp kutusuna taşı"
        )
        self._cancel_transfer_button = Gtk.Button(
            label="İptal", tooltip_text="Aktif aktarımı güvenle iptal et", visible=False
        )
        self._retry_transfer_button = Gtk.Button(
            label="Yeniden dene", tooltip_text="Başarısız aktarımı yeniden dene", visible=False
        )
        self._download_button.set_sensitive(False)
        self._trash_button.set_sensitive(False)
        self._search = Gtk.SearchEntry(placeholder_text="Drive'da ara")
        self._search.set_size_request(240, -1)
        self._search.connect("search-changed", self._filter_rows)

        self._controller = DesktopController(
            on_nodes=self._show_nodes,
            on_error=self._show_error,
            on_state=self._show_state,
            on_transfer=self._show_transfer,
        )
        self._connect_button.connect("clicked", lambda _button: self._controller.connect())
        self._refresh_button.connect("clicked", lambda _button: self._controller.refresh())
        self._back_button.connect("clicked", lambda _button: self._controller.go_up())
        self._upload_button.connect("clicked", self._choose_upload_files)
        self._upload_folder_button.connect("clicked", self._choose_upload_folder)
        self._backup_button.connect("clicked", self._choose_backup_folder)
        self._download_button.connect("clicked", self._choose_download_folder)
        self._trash_button.connect("clicked", self._confirm_trash)
        self._cancel_transfer_button.connect(
            "clicked", lambda _button: self._controller.cancel_transfer()
        )
        self._retry_transfer_button.connect(
            "clicked", lambda _button: self._controller.retry_last_failed()
        )
        self._list.connect("row-activated", self._row_activated)
        self._list.connect("row-selected", self._row_selected)
        self._list.connect("selected-rows-changed", self._selection_changed)
        self.set_content(self._build_layout())
        self.connect("close-request", self._window_closing)
        self._controller.refresh()

    def _build_layout(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._window_title = Adw.WindowTitle(title="PDrive", subtitle="Proton Drive")
        header.set_title_widget(self._window_title)
        header.pack_start(self._back_button)
        header.pack_end(self._refresh_button)
        toolbar.add_top_bar(header)

        split = Adw.NavigationSplitView()
        split.set_sidebar(self._sidebar())
        split.set_content(self._content())
        toolbar.set_content(split)
        return toolbar

    def _sidebar(self) -> Adw.NavigationPage:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("pdrive-sidebar")
        box.set_size_request(250, -1)
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_bottom(14)
        brand.append(Gtk.Image(icon_name="pdrive-desktop", pixel_size=36))
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label(label="PDrive", xalign=0)
        title.add_css_class("brand-title")
        subtitle = Gtk.Label(label="Proton Drive istemcisi", xalign=0)
        subtitle.add_css_class("brand-subtitle")
        brand_text.append(title)
        brand_text.append(subtitle)
        brand.append(brand_text)
        box.append(brand)
        for icon, label, path in (
            ("folder-symbolic", "Dosyalarım", "/my-files"),
            ("computer-symbolic", "Bilgisayarlar", "/devices"),
            ("emblem-shared-symbolic", "Paylaşılanlar", "/shared-by-me"),
            ("user-available-symbolic", "Benimle paylaşılanlar", "/shared-with-me"),
            ("camera-photo-symbolic", "Fotoğraflar", "/photos"),
            ("user-trash-symbolic", "Çöp Kutusu", "/trash"),
        ):
            button = self._nav_button(icon, label, active=path == "/my-files")
            button.connect("clicked", self._navigate_sidebar, path, label)
            self._nav_buttons[path] = button
            box.append(button)
        spacer = Gtk.Box(vexpand=True)
        box.append(spacer)
        privacy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        privacy_box.add_css_class("privacy-card")
        privacy = Gtk.Label(label="Gizlilik korumalı", xalign=0)
        privacy.add_css_class("privacy-badge")
        privacy_detail = Gtk.Label(
            label="PDrive sunucusu ve parola erişimi yok", xalign=0, wrap=True
        )
        privacy_detail.add_css_class("brand-subtitle")
        privacy_box.append(privacy)
        privacy_box.append(privacy_detail)
        box.append(privacy_box)
        return Adw.NavigationPage.new(box, "Proton Drive")

    @staticmethod
    def _nav_button(icon: str, label: str, *, active: bool = False) -> Gtk.Button:
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content.append(Gtk.Image(icon_name=icon, pixel_size=18))
        content.append(Gtk.Label(label=label, xalign=0, hexpand=True))
        button = Gtk.Button(child=content, halign=Gtk.Align.FILL)
        button.add_css_class("flat")
        button.add_css_class("nav-button")
        if active:
            button.add_css_class("active")
        return button

    def _navigate_sidebar(
        self, _button: Gtk.Button, path: str, label: str
    ) -> None:
        location = DrivePath.parse(path)
        self._section_root = location
        for route, button in self._nav_buttons.items():
            if route == path:
                button.add_css_class("active")
            else:
                button.remove_css_class("active")
        self._breadcrumb.set_label(label)
        self._search.set_text("")
        self._controller.open_location(location)

    def _content(self) -> Adw.NavigationPage:
        connect_page = Adw.StatusPage(
            icon_name="folder-remote-symbolic",
            title="Proton Drive'a bağlanın",
            description=(
                "Giriş resmî Proton sayfasında yapılır. "
                "Parolanız PDrive tarafından görülmez."
            ),
        )
        connect_page.set_child(self._connect_button)
        self._stack.add_named(connect_page, "connect")

        self._breadcrumb = Gtk.Label(label="Dosyalarım", xalign=0, hexpand=True)
        self._breadcrumb.add_css_class("breadcrumb")
        content_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content_toolbar.add_css_class("content-toolbar")
        content_toolbar.append(self._breadcrumb)
        content_toolbar.append(self._search)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        actions.set_margin_top(6)
        actions.set_margin_bottom(6)
        actions.set_margin_start(6)
        actions.set_margin_end(6)
        for button, icon, label in (
            (self._upload_button, "document-send-symbolic", "Dosya yükle"),
            (self._upload_folder_button, "folder-new-symbolic", "Klasör yükle"),
            (self._backup_button, "emblem-synchronizing-symbolic", "Güvenli yedekle"),
        ):
            button.set_child(self._action_content(icon, label))
            button.add_css_class("flat")
            actions.append(button)
        actions.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        self._new_folder_button = Gtk.Button(
            child=self._action_content("folder-new-symbolic", "Yeni klasör")
        )
        self._new_folder_button.add_css_class("flat")
        self._new_folder_button.connect("clicked", self._show_create_folder)
        actions.append(self._new_folder_button)
        new_popover = Gtk.Popover(child=actions)
        self._new_button = Gtk.MenuButton(popover=new_popover)
        self._new_button.set_child(self._action_content("list-add-symbolic", "Yeni"))
        self._new_button.add_css_class("suggested-action")
        content_toolbar.append(self._new_button)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self._list)
        empty = Adw.StatusPage(
            icon_name="folder-symbolic",
            title="Bu klasör boş",
            description="Dosya yükleyebilir veya yeni bir klasör oluşturabilirsiniz.",
        )
        self._files_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True
        )
        self._files_stack.add_named(scroller, "list")
        self._files_stack.add_named(empty, "empty")

        selection_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        selection_bar.add_css_class("selection-bar")
        self._status_label.set_xalign(0)
        self._status_label.set_hexpand(True)
        self._status_label.add_css_class("status-text")
        self._download_button.set_child(
            self._action_content("document-save-symbolic", "İndir")
        )
        self._trash_button.set_child(
            self._action_content("user-trash-symbolic", "Çöpe taşı")
        )
        selection_bar.append(self._status_label)
        selection_bar.append(self._retry_transfer_button)
        selection_bar.append(self._cancel_transfer_button)
        selection_bar.append(self._download_button)
        selection_bar.append(self._trash_button)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_box.append(content_toolbar)
        content_box.append(self._files_stack)
        content_box.append(self._progress)
        content_box.append(selection_bar)
        self._stack.add_named(content_box, "files")
        self._stack.set_visible_child_name("connect")
        return Adw.NavigationPage.new(self._stack, "Dosyalarım")

    @staticmethod
    def _action_content(icon: str, label: str) -> Gtk.Box:
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        content.append(Gtk.Image(icon_name=icon, pixel_size=16))
        content.append(Gtk.Label(label=label))
        return content

    def _show_state(self, message: str) -> bool:
        self._status_label.set_label(message)
        busy = message.endswith("…")
        self._busy = busy
        self._connect_button.set_sensitive(not busy)
        self._refresh_button.set_sensitive(not busy)
        self._upload_button.set_sensitive(not busy)
        self._upload_folder_button.set_sensitive(not busy)
        self._backup_button.set_sensitive(not busy)
        self._new_button.set_sensitive(not busy)
        self._new_folder_button.set_sensitive(not busy)
        self._back_button.set_sensitive(
            not busy and self._current_path != self._section_root
        )
        self._selection_changed(self._list)
        self._update_progress()
        self._update_location_actions()
        return False

    def _update_progress(self) -> None:
        running = self._busy or self._transfer_busy
        if running and self._pulse_source is None:
            self._progress.set_visible(True)
            self._pulse_source = GLib.timeout_add(120, self._pulse_progress)
        elif not running and self._pulse_source is not None:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = None
            self._progress.set_visible(False)

    def _show_transfer(self, job: TransferJob, waiting: int) -> bool:
        labels = {
            TransferKind.UPLOAD: "Yükleme",
            TransferKind.DOWNLOAD: "İndirme",
            TransferKind.BACKUP: "Yedekleme",
        }
        action = labels[job.kind]
        suffix = f" · {waiting} aktarım sırada" if waiting else ""
        messages = {
            TransferStatus.QUEUED: f"{action} sıraya alındı{suffix}",
            TransferStatus.RUNNING: f"{action} devam ediyor{suffix}",
            TransferStatus.CANCELLING: f"{action} iptal ediliyor{suffix}",
            TransferStatus.COMPLETED: f"{action} tamamlandı{suffix}",
            TransferStatus.FAILED: f"{action} tamamlanamadı{suffix}",
            TransferStatus.CANCELLED: f"{action} iptal edildi{suffix}",
        }
        self._status_label.set_label(messages[job.status])
        self._transfer_busy = job.status in {
            TransferStatus.RUNNING,
            TransferStatus.CANCELLING,
        } or waiting > 0
        self._cancel_transfer_button.set_visible(
            job.status in {TransferStatus.RUNNING, TransferStatus.CANCELLING}
        )
        self._cancel_transfer_button.set_sensitive(job.status is TransferStatus.RUNNING)
        if job.status is TransferStatus.FAILED and job.retryable:
            self._retry_transfer_id = job.job_id
        elif job.status is TransferStatus.QUEUED and job.job_id == self._retry_transfer_id:
            self._retry_transfer_id = None
        self._retry_transfer_button.set_visible(self._retry_transfer_id is not None)
        self._update_progress()
        return False

    def _pulse_progress(self) -> bool:
        self._progress.pulse()
        return True

    def _show_error(self, message: str) -> bool:
        dialog = Adw.AlertDialog(heading="İşlem tamamlanamadı", body=message)
        dialog.add_response("close", "Kapat")
        dialog.present(self)
        return False

    def _window_closing(self, _window: Adw.ApplicationWindow) -> bool:
        self._controller.shutdown()
        return False

    def _show_nodes(self, path: DrivePath, nodes: Sequence[DriveNode]) -> bool:
        self._current_path = path
        self._breadcrumb.set_label(
            "Dosyalarım" if str(path) == "/my-files" else path.value
        )
        self._back_button.set_sensitive(path != self._section_root)
        self._row_nodes.clear()
        while row := self._list.get_row_at_index(0):
            self._list.remove(row)
        ordered = sorted(
            nodes, key=lambda item: (item.kind is not NodeKind.FOLDER, item.name.casefold())
        )
        for node in ordered:
            row = self._node_row(node)
            self._row_nodes[row] = node
            self._list.append(row)
        self._files_stack.set_visible_child_name("list" if nodes else "empty")
        self._stack.set_visible_child_name("files")
        self._selection_changed(self._list)
        self._filter_rows(self._search)
        self._update_location_actions()
        return False

    def _filter_rows(self, search: Gtk.SearchEntry) -> None:
        query = search.get_text().strip().casefold()
        for row, node in self._row_nodes.items():
            row.set_visible(not query or query in node.name.casefold())

    def _row_activated(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        node = self._row_nodes.get(row)
        if node is not None and node.kind is NodeKind.FOLDER:
            self._controller.open_folder(node.path)

    def _row_selected(
        self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None
    ) -> None:
        if row is None or self._busy:
            return
        node = self._row_nodes.get(row)
        if node is not None and node.kind is NodeKind.FOLDER:
            self._controller.open_folder(node.path)

    def _update_location_actions(self) -> None:
        root = str(self._section_root)
        writable = root in {"/my-files", "/devices", "/shared-with-me"}
        self._upload_button.set_sensitive(writable and not self._busy)
        self._upload_folder_button.set_sensitive(writable and not self._busy)
        self._backup_button.set_sensitive(writable and not self._busy)
        self._new_folder_button.set_sensitive(writable and not self._busy)
        self._trash_button.set_visible(root != "/trash")

    def _selection_changed(self, _list: Gtk.ListBox) -> None:
        has_selection = bool(self._selected_nodes())
        self._download_button.set_sensitive(has_selection and not self._busy)
        self._trash_button.set_sensitive(has_selection and not self._busy)

    def _selected_nodes(self) -> tuple[DriveNode, ...]:
        return tuple(
            self._row_nodes[row]
            for row in self._list.get_selected_rows()
            if row in self._row_nodes
        )

    def _choose_upload_files(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Proton Drive'a yüklenecek dosyaları seçin")
        dialog.open_multiple(self, None, self._upload_files_selected)

    def _upload_files_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = tuple(
            Path(local_path)
            for index in range(files.get_n_items())
            if (local_path := files.get_item(index).get_path()) is not None
        )
        if paths:
            self._controller.upload(paths)

    def _choose_upload_folder(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Proton Drive'a yüklenecek klasörü seçin")
        dialog.select_folder(self, None, self._upload_folder_selected)

    def _upload_folder_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        local_path = folder.get_path()
        if local_path is not None:
            self._controller.upload((Path(local_path),))

    def _choose_backup_folder(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Tek yönlü yedeklenecek klasörü seçin")
        dialog.select_folder(self, None, self._backup_folder_selected)

    def _backup_folder_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        local_path = folder.get_path()
        if local_path is not None:
            self._confirm_backup(Path(local_path))

    def _confirm_backup(self, local_path: Path) -> None:
        dialog = Adw.AlertDialog(
            heading="Tek yönlü güvenli yedekleme",
            body=(
                f"{local_path.name} klasörü mevcut Proton klasörüne yüklenecek. "
                "Yerel veya uzak dosyalar silinmeyecek. Değişen dosyalar yeni revizyon olur."
            ),
        )
        dialog.add_response("cancel", "İptal")
        dialog.add_response("backup", "Yedeklemeyi başlat")
        dialog.set_response_appearance("backup", Adw.ResponseAppearance.SUGGESTED)

        def response(_dialog: Adw.AlertDialog, response_name: str) -> None:
            if response_name == "backup":
                self._controller.backup_folder(local_path)

        dialog.connect("response", response)
        dialog.present(self)

    def _choose_download_folder(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="İndirme klasörünü seçin")
        dialog.select_folder(self, None, self._download_folder_selected)

    def _download_folder_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        local_path = folder.get_path()
        nodes = self._selected_nodes()
        if local_path is not None and nodes:
            self._controller.download(nodes, Path(local_path))

    def _show_create_folder(self, _button: Gtk.Button) -> None:
        entry = Gtk.Entry(placeholder_text="Klasör adı", activates_default=True)
        dialog = Adw.AlertDialog(heading="Yeni klasör", body="Klasör adını girin.")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "İptal")
        dialog.add_response("create", "Oluştur")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")

        def response(_dialog: Adw.AlertDialog, response_name: str) -> None:
            name = entry.get_text().strip()
            if response_name == "create" and name:
                self._controller.create_folder(name)

        dialog.connect("response", response)
        dialog.present(self)

    def _confirm_trash(self, _button: Gtk.Button) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        dialog = Adw.AlertDialog(
            heading="Çöp kutusuna taşınsın mı?",
            body=f"Seçilen {len(nodes)} öğe Proton Drive çöp kutusuna taşınacak.",
        )
        dialog.add_response("cancel", "İptal")
        dialog.add_response("trash", "Çöp kutusuna taşı")
        dialog.set_response_appearance("trash", Adw.ResponseAppearance.DESTRUCTIVE)

        def response(_dialog: Adw.AlertDialog, response_name: str) -> None:
            if response_name == "trash":
                self._controller.trash(nodes)

        dialog.connect("response", response)
        dialog.present(self)

    @staticmethod
    def _node_row(node: DriveNode) -> Gtk.ListBoxRow:
        row = Adw.ActionRow(title=node.name)
        row.add_css_class("file-row")
        icon_name = (
            "folder-symbolic"
            if node.kind is NodeKind.FOLDER
            else "image-x-generic-symbolic"
            if node.kind is NodeKind.PHOTO
            else "text-x-generic-symbolic"
        )
        row.add_prefix(Gtk.Image(icon_name=icon_name, pixel_size=32))
        if node.size is not None:
            row.set_subtitle(_format_size(node.size))
        return row


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def run() -> int:
    app = PDriveApplication()
    return int(app.run(sys.argv))
