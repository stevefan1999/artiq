from PyQt5 import QtWidgets, QtCore


class MoninjWidget(QtWidgets.QFrame):
    def setup_monitoring(self, enabled): raise NotImplementedError

    def refresh_display(self): raise NotImplementedError

    @property
    def sort_key(self): raise NotImplementedError

    def setEnabled(self, value):
        super().setEnabled(value)
        self.refresh_display()

    def __lt__(self, other):
        return self.sort_key < other.sort_key

    def __eq__(self, other):
        return self.sort_key == other.sort_key

    def __hash__(self):
        return hash(self.sort_key)


class SimpleDisplayWidget(MoninjWidget):
    def __init__(self, title):
        QtWidgets.QFrame.__init__(self)

        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        label = QtWidgets.QLabel(title)
        label.setAlignment(QtCore.Qt.AlignCenter)
        grid.addWidget(label, 1, 1)

        self.value = QtWidgets.QLabel()
        self.value.setAlignment(QtCore.Qt.AlignCenter)
        grid.addWidget(self.value, 2, 1, 6, 1)

        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 1)

        self.setLayout(grid)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setFrameShadow(QtWidgets.QFrame.Raised)
        self.refresh_display()
