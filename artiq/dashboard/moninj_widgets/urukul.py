from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QGridLayout, QSizePolicy, \
    QStackedWidget, QToolButton
from numpy import int64

from artiq.coredevice.ad9910 import AD9910_REG_PROFILE0, AD9910_REG_PROFILE7, \
    AD9910_REG_FTW, AD9910_REG_ASF
from artiq.coredevice.ad9912_reg import AD9912_POW1
from artiq.dashboard.moninj_widgets import MoninjWidget
from artiq.dashboard.moninj_widgets.ttl import TTLWidget
from artiq.gui.tools import LayoutWidget
from artiq.language.units import MHz

class UrukulWidget(MoninjWidget):
    def __init__(self, dm, bus_channel, channel, title, sw_channel, ref_clk, pll, is_9910, clk_div=0):
        MoninjWidget.__init__(self)
        self.bus_channel = bus_channel
        self.channel = channel
        self.dm = dm
        self.title = title
        self.sw_channel = sw_channel
        self.ref_clk = ref_clk
        self.pll = pll
        self.is_9910 = is_9910
        self.clk_div = clk_div

        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Raised)

        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(0)
        self.setLayout(grid)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumWidth(100)
        label.setSizePolicy(QSizePolicy.Ignored,
                            QSizePolicy.Preferred)
        grid.addWidget(label, 1, 1)

        self.stack = QStackedWidget()
        grid.addWidget(self.stack, 2, 1)

        self.on_off_label = QLabel()
        self.on_off_label.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.on_off_label)

        grid_cb = LayoutWidget()
        grid_cb.layout.setContentsMargins(0, 0, 0, 0)
        grid_cb.layout.setSpacing(0)
        self.override = QToolButton()
        self.override.setText("OVR")
        self.override.setCheckable(True)
        self.override.setToolTip("Override")
        grid_cb.addWidget(self.override, 1, 1)
        self.level = QToolButton()
        self.level.setText("LVL")
        self.level.setCheckable(True)
        self.level.setToolTip("Level")
        grid_cb.addWidget(self.level, 1, 2)
        self.stack.addWidget(grid_cb)

        grid_freq = QGridLayout()
        grid_freq.setContentsMargins(0, 0, 0, 0)
        grid_freq.setSpacing(0)
        self.freq_stack = QStackedWidget()
        grid_freq.addWidget(self.freq_stack, 1, 1)
        self.freq_label = QLabel()
        self.freq_label.setAlignment(Qt.AlignCenter)
        self.freq_label.setMaximumWidth(100)
        self.freq_label.setSizePolicy(QSizePolicy.Preferred,
                                      QSizePolicy.Preferred)
        self.freq_stack.addWidget(self.freq_label)
        unit = QLabel()
        unit.setAlignment(Qt.AlignCenter)
        unit.setText(' MHz')
        grid_freq.addWidget(unit, 1, 2)
        grid_freq.setColumnStretch(1, 1)
        grid_freq.setColumnStretch(2, 0)
        grid.addLayout(grid_freq, 3, 1)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 0)
        grid.setRowStretch(4, 1)

        self.programmatic_change = False
        self.override.clicked.connect(self.override_toggled)
        self.level.clicked.connect(self.level_toggled)

        self.cur_level = False
        self.cur_override = False
        self.cur_override_level = False
        self.cur_frequency = 0
        self.cur_amp = 0
        self.cur_reg = 0
        self.cur_data_high = 0
        self.cur_data_low = 0

        max_freq, clk_mult = (1 << 32, [4, 1, 2, 4]) if is_9910 else (1 << 48, [1, 1, 2, 4])
        sysclk = ref_clk / clk_mult[clk_div] * pll
        self.ftw_per_hz = 1 / sysclk * max_freq
        self.refresh_display()

    def enterEvent(self, event):
        self.stack.setCurrentIndex(1)
        self.freq_stack.setCurrentIndex(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.stack.setCurrentIndex(0)
        self.freq_stack.setCurrentIndex(0)
        super().leaveEvent(event)

    def override_toggled(self, override):
        comm = self.dm.core_connection
        if comm:
            comm.inject(self.bus_channel, 0, int(override))
            TTLWidget.set_mode(self, ("1" if self.level.isChecked() else "0") if override else "exp", channel=self.sw_channel)

    def level_toggled(self, level):
        if self.programmatic_change:
            return
        if self.override.isChecked():
            TTLWidget.set_mode(self, "1" if level else "0", channel=self.sw_channel)

    def update_reg(self, reg):
        if self.is_9910:
            self.cur_reg = (reg >> 24) & 0xff
        else:
            self.cur_reg = ((reg >> 16) & ~(3 << 13)) & 0xffff

    def update_data_high(self, data):
        if self.is_9910:
            if AD9910_REG_PROFILE0() <= self.cur_reg <= AD9910_REG_PROFILE7():
                asf = (data >> 16) & 0xffff
                self.cur_amp = self._asf_to_amp(asf)
        else:
            if self.cur_reg == AD9912_POW1:
                ftw = int64((data & 0xffff)) << 32
                self.cur_frequency = self._ftw_to_freq(ftw)

    def update_data_low(self, data):
        if self.is_9910:
            if (AD9910_REG_PROFILE0() <= self.cur_reg <= AD9910_REG_PROFILE7() or
                    self.cur_reg == AD9910_REG_FTW()):
                self.cur_frequency = self._ftw_to_freq(data)
            elif self.cur_reg == AD9910_REG_ASF():
                self.cur_amp = self._asf_to_amp(data)
        else:
            if self.cur_reg == AD9912_POW1:
                # mask to avoid improper sign extension
                self.cur_frequency += self._ftw_to_freq(int64(data & 0xffffffff))

    def _ftw_to_freq(self, ftw):
        return ftw / self.ftw_per_hz

    @staticmethod
    def _asf_to_amp(asf):
        return asf / float(0x3ffe)  # coredevice.ad9912 doesn't allow amplitude control so only need to worry about 9910

    def refresh_display(self):
        on_off = self.cur_override_level if self.cur_override else self.cur_level
        on_off_s = "ON" if on_off else "OFF"

        if self.cur_override:
            on_off_s = f"<b>{on_off_s}</b>"
            color = ' color="red"'
        else:
            color = ""
        self.on_off_label.setText(f'<font size="2">{on_off_s}</font>')
        self.freq_label.setText(f'<font size="4"{color}>{self.cur_frequency / MHz:.3f}</font>')
        self.programmatic_change = True
        try:
            self.override.setChecked(self.cur_override)
            if self.cur_override:
                self.stack.setCurrentIndex(1)
                self.freq_stack.setCurrentIndex(1)
                self.level.setChecked(self.cur_level)
        finally:
            self.programmatic_change = False

    @property
    def sort_key(self):
        return self.bus_channel, self.channel

    def setup_monitoring(self, enable):
        comm = self.dm.core_connection
        if comm:
            comm.monitor_probe(enable, self.bus_channel, self.channel)  # register addresses
            comm.monitor_probe(enable, self.bus_channel, self.channel + 4)  # first data
            comm.monitor_probe(enable, self.bus_channel, self.channel + 8)  # second data
            if self.channel == 0:
                comm.monitor_injection(enable, self.bus_channel, 0)
                comm.monitor_injection(enable, self.bus_channel, 1)
                comm.monitor_injection(enable, self.bus_channel, 2)
                if enable:
                    comm.get_injection_status(self.bus_channel, 0)

    def on_monitor(self, *, probe, value, **_):
        type = probe // 4
        if type == 0:  # probes 0-3: register addresses
            self.update_reg(value)
        elif type == 1:  # probes 4-7: data_high (for 64 bit transfer)
            self.update_data_high(value)
        elif type == 2:  # probes 8-11: data_low (for 64 bit) or just data (32 bit)
            self.update_data_low(value)

    @staticmethod
    def extract_key(*, channel, probe, **_):
        return channel, probe % 4