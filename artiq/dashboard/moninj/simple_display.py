from PyQt5 import QtWidgets, QtCore


class SimpleDisplayWidget(QtWidgets.QFrame):
    def __init__(self, title: str):
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

    def refresh_display(self): raise NotImplementedError

    def sort_key(self): raise NotImplementedError
