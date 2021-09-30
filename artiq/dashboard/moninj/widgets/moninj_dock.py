from PyQt5 import QtWidgets

from artiq.gui.flowlayout import FlowLayout


class MonInjDock(QtWidgets.QDockWidget):
    def __init__(self, name):
        QtWidgets.QDockWidget.__init__(self, name)
        self.setObjectName(name)
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)

    def layout_widgets(self, widgets):
        scroll_area = QtWidgets.QScrollArea()
        self.setWidget(scroll_area)

        grid = FlowLayout()
        grid_widget = QtWidgets.QWidget()
        grid_widget.setLayout(grid)

        for widget in sorted(widgets, key=lambda w: w.sort_key()):
            grid.addWidget(widget)

        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_widget)
