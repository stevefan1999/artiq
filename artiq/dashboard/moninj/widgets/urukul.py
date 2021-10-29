import asyncio

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QGridLayout, QSizePolicy, QStackedWidget, QToolButton, QLineEdit
from numpy import int64

from artiq.coredevice.ad9910 import AD9910_REG_PROFILE0, AD9910_REG_PROFILE7, AD9910_REG_FTW, AD9910_REG_ASF
from artiq.coredevice.ad9912_reg import AD9912_POW1
from artiq.gui.tools import LayoutWidget
from artiq.language.environment import ProcessArgumentManager
from artiq.language.units import MHz
from artiq.master import worker_db
from repository.urukul_clock import UrukulFreqSet


class LocalDeviceDB:
    def __init__(self, data):
        self.data = data

    def get_device_db(self):
        return self.data

    def get(self, key, resolve_alias=False):
        desc = self.data[key]
        if resolve_alias:
            while isinstance(desc, str):
                desc = self.data[desc]
        return desc


class UrukulWidget(QFrame):
    def __init__(self, dm, bus_channel, channel, title, sw_channel, ref_clk, pll, is_9910, clk_div=0):
        QFrame.__init__(self)
        self.setStyleSheet("""
QLineEdit[enable="false"] {
    color: #808080; 
    background-color: #F0F0F0;
}
        """)

        self.bus_channel = bus_channel
        self.channel = channel
        self.worker_dm = worker_db.DeviceManager(LocalDeviceDB(dm.ddb))
        self.set_on_off = dm.ttl_set_mode  # todo
        self.urukul_set_override = dm.urukul_set_override
        self.urukul_write = dm.urukul_write
        self.title = title
        self.sw_channel = sw_channel
        self.ref_clk = ref_clk
        self.pll = pll
        self.is_9910 = is_9910
        self.clk_div = clk_div

        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Raised)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.setLayout(grid)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
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
        # self.freq_label.setMaximumWidth(100)
        # self.freq_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
        #                               QtWidgets.QSizePolicy.Preferred)
        self.freq_stack.addWidget(self.freq_label)
        self.freq_edit = QLineEdit()
        self.freq_edit.setAlignment(Qt.AlignCenter)
        # self.freq_edit.setInputMask("0.0000")
        self.freq_edit.setReadOnly(True)
        self.freq_edit.setEnabled(False)
        # self.freq_edit.setTextMargins(0, 0, 0, 0)
        self.freq_edit.setSizePolicy(QSizePolicy.Ignored,
                                     QSizePolicy.Preferred)
        # self.freq_edit.setMaximumWidth(100)
        self.freq_stack.addWidget(self.freq_edit)
        unit = QLabel()
        unit.setAlignment(Qt.AlignCenter)
        unit.setText('<font size="2">  MHz</font>')
        grid_freq.addWidget(unit, 1, 2)
        grid_freq.setColumnStretch(1, 1)
        grid_freq.setColumnStretch(2, 0)
        grid.addLayout(grid_freq, 3, 1)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 0)
        grid.setRowStretch(4, 1)

        self.programmatic_change = False
        self.override.clicked.connect(lambda override: asyncio.ensure_future(self.override_toggled(override)))
        self.level.clicked.connect(lambda toggled: asyncio.ensure_future(self.level_toggled(toggled)))
        self.freq_edit.returnPressed.connect(lambda: asyncio.ensure_future(self.frequency_edited()))

        self.cur_level = False
        self.cur_override = False
        self.cur_override_level = False
        self.cur_frequency = 0
        self.cur_amp = 0
        self.cur_reg = 0
        self.cur_data_high = 0
        self.cur_data_low = 0
        if is_9910:
            self.ftw_per_hz = (1 << 32) / (ref_clk / [4, 1, 2, 4][clk_div] * pll)
        else:
            self.ftw_per_hz = (1 << 48) / (ref_clk / [1, 1, 2, 4][clk_div] * pll)
        self.refresh_display()

    def enterEvent(self, event):
        self.stack.setCurrentIndex(1)
        self.freq_stack.setCurrentIndex(1)
        QFrame.enterEvent(self, event)

    def leaveEvent(self, event):
        self.stack.setCurrentIndex(0)
        self.freq_stack.setCurrentIndex(0)
        QFrame.leaveEvent(self, event)

    async def override_toggled(self, override):
        if self.programmatic_change:
            return
        await self.urukul_set_override(self.bus_channel, override)
        self.freq_edit.setReadOnly(not override)
        self.freq_edit.setEnabled(override)
        if override:
            if self.level.isChecked():
                await self.set_on_off(self.sw_channel, "1")
            else:
                await self.set_on_off(self.sw_channel, "0")
        else:
            await self.set_on_off(self.sw_channel, "exp")
        self.cur_override_level = override

    async def level_toggled(self, level):
        if self.programmatic_change:
            return
        if self.override.isChecked():
            if level:
                await self.set_on_off(self.sw_channel, "1")
            else:
                await self.set_on_off(self.sw_channel, "0")

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
        # print(self.cur_frequency)

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
        # print(self.cur_frequency)

    async def frequency_edited(self):
        freq = float(self.freq_edit.text()) * MHz
        self.cur_frequency = freq
        print("frequency edited: ", freq)

        args = {"chan": self.title, 'freq': freq}
        argument_mgr = ProcessArgumentManager(args)
        experiment = UrukulFreqSet((self.worker_dm, None, argument_mgr, None))
        experiment.prepare()
        experiment.run()

    def _ftw_to_freq(self, ftw):
        return ftw / self.ftw_per_hz

    @staticmethod
    def _asf_to_amp(asf):
        return asf / float(0x3ffe)  # coredevice.ad9912 doesn't allow amplitude control so only need to worry about 9910

    def refresh_display(self):
        print(self.cur_reg, self.cur_frequency, self.cur_amp)
        on_off = self.cur_override_level if self.cur_override else self.cur_level
        on_off_s = "ON" if on_off else "OFF"

        if self.cur_override:
            on_off_s = f"<b>{on_off_s}</b>"
            color = ' color="red"'
        else:
            color = ""

        self.on_off_label.setText(f'<font size="2">{on_off_s}</font>')

        self.freq_label.setText(f'<font size="4"{color}>{self.cur_frequency / 1e6:.4f}</font>')
        self.freq_edit.setText("{:.4f}".format(self.cur_frequency / 1e6))

        self.programmatic_change = True
        try:
            self.override.setChecked(self.cur_override)
            if self.cur_override:
                self.stack.setCurrentIndex(1)
                self.freq_stack.setCurrentIndex(1)
                self.level.setChecked(self.cur_level)
        finally:
            self.programmatic_change = False

    def sort_key(self):
        return self.bus_channel, self.channel
