import asyncio

from PyQt5 import QtWidgets, QtCore

from artiq.gui.tools import LayoutWidget


class TTLWidget(QtWidgets.QFrame):
    def __init__(self, dm, channel, force_out, title):
        QtWidgets.QFrame.__init__(self)

        self.channel = channel
        self.set_mode = dm.ttl_set_mode
        self.force_out = force_out

        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)
        self.setLayout(grid)
        label = QtWidgets.QLabel(title)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                            QtWidgets.QSizePolicy.Preferred)
        grid.addWidget(label, 1, 1)

        self.stack = QtWidgets.QStackedWidget()
        grid.addWidget(self.stack, 2, 1)

        self.direction = QtWidgets.QLabel()
        self.direction.setAlignment(QtCore.Qt.AlignCenter)
        self.stack.addWidget(self.direction)

        grid_cb = LayoutWidget()
        grid_cb.layout.setContentsMargins(0, 0, 0, 0)
        grid_cb.layout.setHorizontalSpacing(0)
        grid_cb.layout.setVerticalSpacing(0)
        self.override = QtWidgets.QToolButton()
        self.override.setText("OVR")
        self.override.setCheckable(True)
        self.override.setToolTip("Override")
        grid_cb.addWidget(self.override, 3, 1)
        self.level = QtWidgets.QToolButton()
        self.level.setText("LVL")
        self.level.setCheckable(True)
        self.level.setToolTip("Level")
        grid_cb.addWidget(self.level, 3, 2)
        self.stack.addWidget(grid_cb)

        self.value = QtWidgets.QLabel()
        self.value.setAlignment(QtCore.Qt.AlignCenter)
        grid.addWidget(self.value, 3, 1)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 0)
        grid.setRowStretch(4, 1)

        self.programmatic_change = False
        self.override.clicked.connect(lambda override: asyncio.ensure_future(self.override_toggled(override)))
        self.level.clicked.connect(lambda toggled: asyncio.ensure_future(self.level_toggled(toggled)))

        self.cur_level = False
        self.cur_oe = False
        self.cur_override = False
        self.cur_override_level = False
        self.refresh_display()

    def enterEvent(self, event):
        self.stack.setCurrentIndex(1)
        QtWidgets.QFrame.enterEvent(self, event)

    def leaveEvent(self, event):
        if not self.override.isChecked():
            self.stack.setCurrentIndex(0)
        QtWidgets.QFrame.leaveEvent(self, event)

    async def override_toggled(self, override):
        if self.programmatic_change:
            return
        if override:
            if self.level.isChecked():
                await self.set_mode(self.channel, "1")
            else:
                await self.set_mode(self.channel, "0")
        else:
            await self.set_mode(self.channel, "exp")

    async def level_toggled(self, level):
        if self.programmatic_change:
            return
        if level:
            await self.set_mode(self.channel, "1")
        else:
            await self.set_mode(self.channel, "0")

    def refresh_display(self):
        level = self.cur_override_level if self.cur_override else self.cur_level
        value_s = "1" if level else "0"

        if self.cur_override:
            value_s = f"<b>{value_s}</b>"
            color = ' color="red"'
        else:
            color = ""
        self.value.setText(f'<font size="5"{color}>{value_s}</font>')
        oe = self.cur_oe or self.force_out
        direction = "OUT" if oe else "IN"
        self.direction.setText(f'<font size="2">{direction}</font>')

        self.programmatic_change = True
        try:
            self.override.setChecked(self.cur_override)
            if self.cur_override:
                self.stack.setCurrentIndex(1)
                self.level.setChecked(level)
        finally:
            self.programmatic_change = False

    def sort_key(self):
        return self.channel
