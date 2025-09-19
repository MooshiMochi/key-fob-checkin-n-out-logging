from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtPrintSupport import QPrintDialog, QPrinter


def show_temp_message(
    parent,
    title,
    text,
    icon=QtWidgets.QMessageBox.Icon.Information,
    timeout_ms: int = 3000,
):
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(icon)
    box.setText(text)
    box.setWindowTitle(title)
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    box.setModal(False)
    box.show()
    QtCore.QTimer.singleShot(timeout_ms, box.accept)
    return box


from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from .config import cfg
from .crypto_secure import Crypto
from .models import (
    check_in_key,
    check_out_key,
    get_key_log_times,
    get_tag_info,
    register_or_overwrite_tag,
    verify_tag_content,
)
from .reader_adapter import MockReader, MockState, ReaderAdapter, RealReader
from .services import LogRow, TagRow, fetch_logs, fetch_registered_tags, set_tag_active


@dataclass
class SessionState:
    active_employee_card_id: Optional[int] = None
    window_expires_at: Optional[datetime] = None


class LogTableModel(QtCore.QAbstractTableModel):
    HEADERS = ["Key", "Employee", "Checked Out", "Checked In", "Status", "Elapsed"]

    def __init__(self, rows: list[LogRow]):
        super().__init__()
        self._rows = rows

    def update(self, rows: list[LogRow]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(
        self,
        parent: (
            QtCore.QModelIndex | QtCore.QPersistentModelIndex
        ) = QtCore.QModelIndex(),
    ):
        return len(self._rows)

    def columnCount(
        self,
        parent: (
            QtCore.QModelIndex | QtCore.QPersistentModelIndex
        ) = QtCore.QModelIndex(),
    ):
        return len(self.HEADERS)

    def headerData(
        self,
        section,
        orientation,
        role: QtCore.Qt.ItemDataRole | int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if (
            role == QtCore.Qt.ItemDataRole.DisplayRole
            and orientation == QtCore.Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]
        return None

    def data(self, index, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return r.key_label
            if col == 1:
                return r.employee_name or "—"
            if col == 2:
                return r.check_out.strftime("%Y-%m-%d %H:%M:%S")
            if col == 3:
                return r.check_in.strftime("%Y-%m-%d %H:%M:%S") if r.check_in else "—"
            if col == 4:
                return "IN" if r.check_in else "OUT"
            if col == 5:
                if r.check_in:
                    delta = r.check_in - r.check_out
                else:
                    delta = datetime.now() - r.check_out
                mins = int(delta.total_seconds() // 60)
                hrs = mins // 60
                mins = mins % 60
                secs = int(delta.total_seconds() % 60)
                if hrs == 0 and mins == 0:
                    return f"{secs}s"
                if hrs > 0:
                    return f"{hrs}h {mins}m"
                return f"{mins}m {secs}s"
        if role == QtCore.Qt.ItemDataRole.BackgroundRole:
            # Green for checked in, yellow for out
            if r.check_in:
                return QtGui.QBrush(QtGui.QColor(40, 167, 69, 60))
            else:
                return QtGui.QBrush(QtGui.QColor(255, 193, 7, 60))
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if col in (2, 3, 4, 5):
                return int(QtCore.Qt.AlignmentFlag.AlignCenter)
        return None


class TagManagerDialog(QtWidgets.QDialog):
    def __init__(self, crypto: Crypto, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Tags")
        self.resize(700, 420)
        self.crypto = crypto
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["UID", "Type", "Label", "Active", "Action"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        self.reload()

    def reload(self):
        tags = fetch_registered_tags(self.crypto)
        self.table.setRowCount(len(tags))
        for row, t in enumerate(tags):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(t.uid)))
            self.table.setItem(
                row,
                1,
                QtWidgets.QTableWidgetItem("Employee" if t.type == "emp" else "Key"),
            )
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(t.label))
            active_item = QtWidgets.QTableWidgetItem("Yes" if t.active else "No")
            active_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, active_item)
            btn = QtWidgets.QPushButton("Deactivate" if t.active else "Activate")

            def make_handler(uid=t.uid, active=t.active):
                def handler():
                    try:
                        set_tag_active(uid, not active)
                        self.reload()
                    except Exception as e:
                        show_temp_message(
                            self, "Error", str(e), QtWidgets.QMessageBox.Icon.Critical
                        )

                return handler

            btn.clicked.connect(make_handler())
            self.table.setCellWidget(row, 4, btn)


class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, crypto: Crypto, reader: ReaderAdapter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Tag")
        self.crypto = crypto
        self.reader = reader
        self.setModal(True)
        self.resize(420, 240)

        self.type_box = QtWidgets.QComboBox()
        self.type_box.addItems(["Employee", "Key"])
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setPlaceholderText("Full name or key label/number")

        self.status_label = QtWidgets.QLabel("Tap the target tag when ready.")
        self.status_label.setWordWrap(True)
        self.start_btn = QtWidgets.QPushButton("Start Registration")
        self.start_btn.clicked.connect(self.start)

        form = QtWidgets.QFormLayout()
        form.addRow("Type", self.type_box)
        form.addRow("Label", self.label_edit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)

        # Add simulate tap controls when using mock reader
        if isinstance(self.reader, MockReader):
            mock_box = QtWidgets.QGroupBox("Mock Tap")
            mock_uid = QtWidgets.QLineEdit()
            mock_uid.setPlaceholderText("UID e.g. 1234")
            mock_text = QtWidgets.QLineEdit()
            mock_text.setPlaceholderText("Text on card (uuid or blank)")
            sim_btn = QtWidgets.QPushButton("Simulate Tap")

            def do_sim():
                try:
                    uid = int(mock_uid.text().strip())
                    text = mock_text.text().strip()
                    self.reader.set_next(uid, text)  # type: ignore - this is validated by isinstance above
                except Exception as e:
                    show_temp_message(
                        self, "Mock Error", str(e), QtWidgets.QMessageBox.Icon.Warning
                    )

            sim_btn.clicked.connect(do_sim)
            h = QtWidgets.QHBoxLayout()
            h.addWidget(QtWidgets.QLabel("UID:"))
            h.addWidget(mock_uid)
            h.addWidget(QtWidgets.QLabel("Text:"))
            h.addWidget(mock_text)
            h.addWidget(sim_btn)
            mock_box.setLayout(h)
            layout.addWidget(mock_box)

        layout.addStretch(1)
        layout.addWidget(self.start_btn)

        self._worker: Optional[QtCore.QThread] = None

    def start(self):
        label = self.label_edit.text().strip()
        if not label:
            show_temp_message(
                self,
                "Input Required",
                "Please enter a label/name.",
                QtWidgets.QMessageBox.Icon.Warning,
            )
            return
        self.start_btn.setEnabled(False)
        self.status_label.setText("Waiting for tag...")

        # Worker thread to block on reader.read()
        class ReaderWorker(QtCore.QThread):
            got = QtCore.Signal(int, str)
            err = QtCore.Signal(str)

            def __init__(self, reader: ReaderAdapter):
                super().__init__()
                self.reader = reader

            def run(self):
                try:
                    uid, text = self.reader.read()
                    self.got.emit(uid, text)
                except Exception as e:
                    self.err.emit(str(e))

        worker = ReaderWorker(self.reader)
        worker.got.connect(lambda uid, text: self._do_register(uid, text))
        worker.err.connect(lambda msg: self._on_error(msg))
        worker.start()
        self._worker = worker

    def _on_error(self, msg: str):
        self.start_btn.setEnabled(True)
        show_temp_message(
            self, "Reader Error", msg, QtWidgets.QMessageBox.Icon.Critical
        )

    def _do_register(self, uid: int, current_text: str):
        try:
            tag_type = "emp" if self.type_box.currentIndex() == 0 else "key"
            label = self.label_edit.text().strip()
            encrypted = self.crypto.encrypt_name(label)
            # generate uuid string
            import uuid

            uuid_key = str(uuid.uuid4()).replace("-", "")
            register_or_overwrite_tag(uid, tag_type, uuid_key, encrypted)
            # Write to tag and verify
            self.reader.write(uuid_key)
            self.status_label.setText(
                f"Registered UID {uid}. Please re-tap to verify..."
            )

            # Verify by reading again
            if isinstance(self.reader, MockReader):
                # Auto-place the tag with the new UUID for verification in mock mode
                self.reader.set_next(uid, uuid_key)
            uid2, text2 = self.reader.read()
            if uid2 == uid and (text2 or "").strip() == uuid_key:
                show_temp_message(
                    self,
                    "Success",
                    f"Tag {uid} registered.",
                    QtWidgets.QMessageBox.Icon.Information,
                )
                self.accept()
            else:
                raise RuntimeError("Verification failed. Try again.")
        except Exception as e:
            traceback.print_exc()
            show_temp_message(
                self, "Registration Error", str(e), QtWidgets.QMessageBox.Icon.Critical
            )
        finally:
            self.start_btn.setEnabled(True)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        crypto: Crypto,
        reader: Optional[ReaderAdapter] = None,
        mock_state: Optional[MockState] = None,
    ):
        super().__init__()
        self.crypto = crypto
        self.reader = reader
        self.mock_state = mock_state
        self.state = SessionState()
        self.setWindowTitle("Key Fob Check-In/Out")
        self.resize(1000, 640)

        # Filters
        self.key_filter = QtWidgets.QLineEdit()
        self.key_filter.setPlaceholderText("Filter by key label")
        self.emp_filter = QtWidgets.QLineEdit()
        self.emp_filter.setPlaceholderText("Filter by employee name")
        self.status_filter = QtWidgets.QComboBox()
        self.status_filter.addItems(["All", "Checked Out", "Checked In"])
        self.start_date = QtWidgets.QDateTimeEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd-MM-yyyy HH:mm")
        self.end_date = QtWidgets.QDateTimeEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd-MM-yyyy HH:mm")

        now = QtCore.QDateTime.currentDateTime()
        self.start_date.setDateTime(
            QtCore.QDateTime(now.date().addDays(-7), QtCore.QTime(0, 0))
        )
        self.end_date.setDateTime(QtCore.QDateTime(now.date(), QtCore.QTime(23, 59)))

        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setToolTip("Clear all filters and reset date range")
        self.clear_btn.clicked.connect(self.clear_filters)

        filter_bar = QtWidgets.QHBoxLayout()
        filter_bar.addWidget(QtWidgets.QLabel("Key:"))
        filter_bar.addWidget(self.key_filter)
        filter_bar.addWidget(QtWidgets.QLabel("Employee:"))
        filter_bar.addWidget(self.emp_filter)
        filter_bar.addWidget(QtWidgets.QLabel("From:"))
        filter_bar.addWidget(self.start_date)
        filter_bar.addWidget(QtWidgets.QLabel("To:"))
        filter_bar.addWidget(self.end_date)
        filter_bar.addWidget(QtWidgets.QLabel("Status:"))
        filter_bar.addWidget(self.status_filter)
        filter_bar.addWidget(self.clear_btn)

        # Table
        self.table = QtWidgets.QTableView()
        self.model = LogTableModel([])
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(
            QtWidgets.QTableView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )

        # Toolbar
        tb = QtWidgets.QToolBar()
        tb.setMovable(False)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, tb)
        act_register_key = QtGui.QAction("Register Tag", self)
        act_register_key.triggered.connect(lambda: self.open_register(emp=False))
        act_manage = QtGui.QAction("Manage Tags", self)
        act_manage.triggered.connect(self.open_manage)
        act_print = QtGui.QAction("Print Logs", self)
        act_print.triggered.connect(self.print_logs)
        act_refresh = QtGui.QAction("Refresh", self)
        act_refresh.triggered.connect(self.fetch_data)

        tb.addAction(act_register_key)
        tb.addSeparator()
        tb.addAction(act_manage)
        tb.addSeparator()
        tb.addAction(act_print)
        tb.addSeparator()
        tb.addAction(act_refresh)

        # Mock input (if any)
        mock_box = None
        if isinstance(self.reader, MockReader):
            mock_box = QtWidgets.QGroupBox("Mock Tap")
            mock_uid = QtWidgets.QLineEdit()
            mock_uid.setPlaceholderText("UID e.g. 1234")
            mock_text = QtWidgets.QLineEdit()
            mock_text.setPlaceholderText("Text/UUID on card")
            send_btn = QtWidgets.QPushButton("Simulate Tap")

            def do_mock():
                try:
                    uid = int(mock_uid.text().strip())
                    text = mock_text.text().strip()
                    self.reader.set_next(uid, text)  # type: ignore - this is validated by isinstance above
                    self._process_tag(uid, text)
                except Exception as e:
                    show_temp_message(
                        self, "Mock Error", str(e), QtWidgets.QMessageBox.Icon.Warning
                    )

            send_btn.clicked.connect(do_mock)
            h = QtWidgets.QHBoxLayout()
            h.addWidget(QtWidgets.QLabel("UID:"))
            h.addWidget(mock_uid)
            h.addWidget(QtWidgets.QLabel("Text:"))
            h.addWidget(mock_text)
            h.addWidget(send_btn)
            mock_box.setLayout(h)

        # Central layout
        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.addLayout(filter_bar)
        v.addWidget(self.table)
        if mock_box:
            v.addWidget(mock_box)
        self.setCentralWidget(central)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Periodic refresh
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.fetch_data)
        self._timer.start()

        # Style (simple modern look)
        self.setStyleSheet(
            """
            QMainWindow { background: #0f1115; }
            QToolBar { background: #111318; border: none; }
            QTableView { background: #151821; color: #e2e8f0; gridline-color: #2d3340; alternate-background-color:#171a24; }
            QHeaderView::section { background: #121520; color: #b6c2d9; padding:6px; border: 1px solid #2d3340; }
            QLabel, QLineEdit, QDateTimeEdit, QDateEdit, QTimeEdit { color: #e2e8f0; }
            QLineEdit, QDateTimeEdit, QDateEdit, QTimeEdit { background:#0d0f14; border:1px solid #2b3242; padding:6px; border-radius:4px; }
            QPushButton { background:#1f2737; color:#e2e8f0; padding:6px 10px; border:1px solid #2b3242; border-radius:6px; }
            QPushButton:hover { background:#273149; }
            QGroupBox { border:1px solid #2b3242; border-radius:6px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            """
        )

        # Filter debounce for text inputs
        self._filter_timer = QtCore.QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self.apply_filters)

        # Bind filter changes
        self.emp_filter.textChanged.connect(lambda _: self._filter_timer.start())
        self.key_filter.textChanged.connect(lambda _: self._filter_timer.start())
        self.status_filter.currentTextChanged.connect(
            lambda _: self._filter_timer.start()
        )
        # Bind date/time changes to data (re)fetch
        self.start_date.dateChanged.connect(lambda _: self.fetch_data())
        self.end_date.dateChanged.connect(lambda _: self.fetch_data())

        # Data cache for fast filtering
        self._base_rows: list[LogRow] = []

        self.fetch_data()

    # Core processing logic without CLI prompts
    CHECKOUT_WINDOW = timedelta(seconds=20)
    CHECKIN_MIN_AGE = timedelta(minutes=2)

    def _process_tag(self, uid: int, text: str):
        now = datetime.now()
        tag_type, is_active = get_tag_info(uid)
        if tag_type is None:
            self.statusBar().showMessage(
                f"Unregistered tag {uid}. Use Register Tag.", 5000
            )
            return
        if not is_active:
            self.statusBar().showMessage(
                f"Inactive tag {uid}. Activate in Manage Tags.", 5000
            )
            return
        if not verify_tag_content(uid, text):
            self.statusBar().showMessage(
                f"Invalid content on tag {uid}. Re-register.", 5000
            )
            return

        if tag_type == "emp":
            # set session
            self.state.active_employee_card_id = uid
            self.state.window_expires_at = now + self.CHECKOUT_WINDOW
            self.statusBar().showMessage(
                "Employee ready. Tap key(s) to check out.", 5000
            )
            return

        if tag_type == "key":
            co, ci = get_key_log_times(uid, text)
            if (not co and not ci) or (ci and co):
                # key is in
                if (
                    not self.state.active_employee_card_id
                    or not self.state.window_expires_at
                    or now > self.state.window_expires_at
                ):
                    self.statusBar().showMessage(
                        "No active employee. Tap employee card first.", 5000
                    )
                    self.state.active_employee_card_id = None
                    self.state.window_expires_at = None
                    return
                try:
                    check_out_key(uid, text, self.state.active_employee_card_id)
                    self.statusBar().showMessage(
                        "Checked out. You can return after 2 minutes.", 5000
                    )
                    self.fetch_data()
                except Exception as e:
                    show_temp_message(
                        self,
                        "Check Out Failed",
                        str(e),
                        QtWidgets.QMessageBox.Icon.Warning,
                    )
                return

            if co and not ci:
                if co + self.CHECKIN_MIN_AGE > now:
                    secs = int((co + self.CHECKIN_MIN_AGE - now).total_seconds())
                    self.statusBar().showMessage(
                        f"Too soon to check in. Wait {secs}s.", 5000
                    )
                    return
                try:
                    check_in_key(uid, text)
                    self.statusBar().showMessage("Checked in.", 5000)
                    self.fetch_data()
                except Exception as e:
                    show_temp_message(
                        self,
                        "Check In Failed",
                        str(e),
                        QtWidgets.QMessageBox.Icon.Warning,
                    )
                return

        self.statusBar().showMessage("Unexpected tag state.", 5000)

    def _current_range(self) -> tuple[datetime, datetime]:
        sd, st = self.start_date.date(), self.start_date.time()
        ed, et = self.end_date.date(), self.end_date.time()
        start_dt = datetime(sd.year(), sd.month(), sd.day(), st.hour(), st.minute())
        end_dt = datetime(ed.year(), ed.month(), ed.day(), et.hour(), et.minute())
        return start_dt, end_dt

    def fetch_data(self):
        start_dt, end_dt = self._current_range()
        self._base_rows = fetch_logs(
            self.crypto, start=start_dt, end=end_dt, limit=1000
        )
        self.apply_filters()

    def apply_filters(self):
        rows = self._base_rows
        emp_q = self.emp_filter.text().strip().lower()
        key_q = self.key_filter.text().strip().lower()
        if emp_q:
            rows = [
                r for r in rows if (r.employee_name or "").lower().find(emp_q) != -1
            ]
        if key_q:
            rows = [r for r in rows if (r.key_label or "").lower().find(key_q) != -1]
        if self.status_filter.currentText() != "All":
            if self.status_filter.currentText() == "Checked Out":
                rows = [r for r in rows if r.check_in is None]
            else:
                rows = [r for r in rows if r.check_in is not None]
        # Prioritize checked out first, then by check out time desc
        rows = sorted(rows, key=lambda r: r.check_in is None, reverse=True)
        rows = sorted(rows, key=lambda r: r.check_out, reverse=True)
        self.model.update(rows)

    def clear_filters(self):
        now = QtCore.QDateTime.currentDateTime()
        self.emp_filter.clear()
        self.key_filter.clear()
        self.status_filter.setCurrentIndex(0)
        self.start_date.setDateTime(
            QtCore.QDateTime(now.date().addDays(-7), QtCore.QTime(0, 0))
        )
        self.end_date.setDateTime(QtCore.QDateTime(now.date(), QtCore.QTime(23, 59)))
        self.fetch_data()

    def open_manage(self):
        dlg = TagManagerDialog(self.crypto, self)
        dlg.exec()
        self.fetch_data()

    def open_register(self, emp: bool):
        if not self.reader:
            show_temp_message(
                self,
                "Reader Required",
                "Registration requires a reader (real or mock).",
                QtWidgets.QMessageBox.Icon.Information,
            )
            return
        dlg = RegisterDialog(self.crypto, self.reader, self)
        dlg.type_box.setCurrentIndex(0 if emp else 1)
        dlg.exec()
        self.fetch_data()

    def print_logs(self):
        # HTML doc for printing
        rows = [self.model._rows[i] for i in range(self.model.rowCount())]

        def esc(s: str) -> str:
            return (
                (s or "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        html = [
            "<html><head><style>body{font-family:Arial,sans-serif;} table{border-collapse:collapse;width:100%;} th,td{border:1px solid #999;padding:6px;text-align:left;} .in{background:#d4edda;} .out{background:#fff3cd;}</style></head><body>",
            f"<h3>Key Logs {datetime.now().strftime('%Y-%m-%d %H:%M')}</h3>",
            "<table><tr><th>Key</th><th>Employee</th><th>Checked Out</th><th>Checked In</th><th>Status</th><th>Elapsed</th></tr>",
        ]
        for r in rows:
            status = "IN" if r.check_in else "OUT"
            cls = "in" if r.check_in else "out"
            elapsed = ""
            if r.check_in:
                delta = r.check_in - r.check_out
            else:
                delta = datetime.now() - r.check_out
            mins = int(delta.total_seconds() // 60)
            hrs = mins // 60
            mins = mins % 60
            secs = int(delta.total_seconds() % 60)
            if hrs == 0 and mins == 0:
                elapsed = f"{secs}s"
            if hrs > 0:
                elapsed = f"{hrs}h {mins}m"
            else:
                elapsed = f"{mins}m {secs}s"

            html.append(
                f"<tr class='{cls}'><td>{esc(r.key_label)}</td><td>{esc(r.employee_name or '')}</td><td>{r.check_out}</td><td>{r.check_in or ''}</td><td>{status}</td><td>{elapsed}</td></tr>"
            )
        html.append("</table></body></html>")
        doc = QtGui.QTextDocument()
        doc.setHtml("".join(html))

        # Set job/file name for spool/Print to File
        start_dt, end_dt = self._current_range()
        job_name = f"Export-KeyLogs-{start_dt.strftime('%Y%m%d-%H%M')}_to_{end_dt.strftime('%Y%m%d-%H%M')}"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(job_name)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Print Logs")
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            doc.print_(printer)


def run_ui(mock: bool = False):
    app = QtWidgets.QApplication(sys.argv)
    crypto = Crypto(cfg.secret_key_path)
    reader: Optional[ReaderAdapter]
    mock_state = None
    if mock:
        mock_state = MockState()
        reader = MockReader(mock_state)
    else:
        try:
            reader = RealReader()
        except Exception:
            reader = None
    win = MainWindow(crypto, reader, mock_state)
    win.show()
    sys.exit(app.exec())
