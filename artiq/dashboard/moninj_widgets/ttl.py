from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QToolButton, QStackedWidget, QLabel, QSizePolicy, QGridLayout, QFrame

from artiq.coredevice.comm_moninj import TTLOverride, TTLProbe
from artiq.dashboard.moninj_widgets import MoninjWidget
from artiq.gui.tools import LayoutWidget


class TTLWidget(MoninjWidget):
    def __init__(self, dm, channel, force_out, title):
        super().__init__()

        self.channel = channel
        self.dm = dm
        self.force_out = force_out

        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Raised)

        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(0)
        self.setLayout(grid)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setSizePolicy(QSizePolicy.Preferred,
                            QSizePolicy.Preferred)
        grid.addWidget(label, 1, 1)

        self.stack = QStackedWidget()
        grid.addWidget(self.stack, 2, 1)

        self.direction = QLabel()
        self.direction.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.direction)

        grid_cb = LayoutWidget()
        grid_cb.layout.setContentsMargins(0, 0, 0, 0)
        grid_cb.layout.setHorizontalSpacing(0)
        grid_cb.layout.setVerticalSpacing(0)
        self.override = QToolButton()
        self.override.setText("OVR")
        self.override.setCheckable(True)
        self.override.setToolTip("Override")
        grid_cb.addWidget(self.override, 3, 1)
        self.level = QToolButton()
        self.level.setText("LVL")
        self.level.setCheckable(True)
        self.level.setToolTip("Level")
        grid_cb.addWidget(self.level, 3, 2)
        self.stack.addWidget(grid_cb)

        self.value = QLabel()
        self.value.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.value, 3, 1)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        grid.setRowStretch(3, 1)
        grid.setRowStretch(4, 1)

        self.override.toggled.connect(self.override_toggled)
        self.override.toggled.connect(self.refresh_display)

        self.level.toggled.connect(self.level_toggled)
        self.level.toggled.connect(self.refresh_display)

        self.cur_oe = False
        self.cur_override_level = False

    @property
    def cur_level(self):
        return self.cur_override_level if self.override.isChecked() else self.level.isChecked()

    def enterEvent(self, event):
        self.stack.setCurrentIndex(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.override.isChecked():
            self.stack.setCurrentIndex(0)
        super().leaveEvent(event)

    def override_toggled(self, override):
        self.set_mode(self.channel, ("1" if self.level.isChecked() else "0") if override else "exp")

    def level_toggled(self, level):
        self.set_mode(self.channel, "1" if level else "0")

    def refresh_display(self):
        value_s = "1" if self.cur_level else "0"

        if self.override.isChecked():
            value_s = f"<b>{value_s}</b>"
            color = ' color="red"'
        else:
            color = ""
        self.value.setText(f'<font size="5"{color}>{value_s}</font>')
        self.direction.setText(f'<font size="2">{"OUT" if self.force_out or self.cur_oe else "IN"}</font>')

        if self.override.isChecked():
            self.stack.setCurrentIndex(1)

    @property
    def sort_key(self):
        return self.channel

    def setup_monitoring(self, enable):
        conn = self.dm.core_connection
        if conn:
            conn.monitor_probe(enable, self.channel, TTLProbe.level.value)
            conn.monitor_probe(enable, self.channel, TTLProbe.oe.value)
            conn.monitor_injection(enable, self.channel, TTLOverride.en.value)
            conn.monitor_injection(enable, self.channel,
                                   TTLOverride.level.value)
            if enable:
                conn.get_injection_status(self.channel, TTLOverride.en.value)

    def set_mode(self, channel, mode):
        conn = self.dm.core_connection
        if conn:
            if mode == "0":
                self.override.setChecked(True)
                conn.inject(channel, TTLOverride.level.value, 0)
                conn.inject(channel, TTLOverride.oe.value, 1)
                conn.inject(channel, TTLOverride.en.value, 1)
            elif mode == "1":
                self.override.setChecked(True)
                conn.inject(channel, TTLOverride.level.value, 1)
                conn.inject(channel, TTLOverride.oe.value, 1)
                conn.inject(channel, TTLOverride.en.value, 1)
            elif mode == "exp":
                self.override.setChecked(False)
                conn.inject(channel, TTLOverride.en.value, 0)
            else:
                raise ValueError
            # override state may have changed
            self.refresh_display()

    def on_monitor(self, *, probe, value, **_):
        if probe == TTLProbe.level.value:
            self.level.setChecked(bool(value))
        elif probe == TTLProbe.oe.value:
            self.cur_oe = bool(value)

    def on_injection_status(self, *, override, value, **_):
        if override == TTLOverride.en.value:
            self.override.setChecked(bool(value))
        if override == TTLOverride.level.value:
            self.cur_override_level = bool(value)

    @staticmethod
    def extract_key(*, channel, **_):
        return channel
