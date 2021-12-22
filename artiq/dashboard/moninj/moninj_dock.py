from PyQt5.QtWidgets import QDockWidget, QScrollArea, QWidget

from artiq.gui.flowlayout import FlowLayout


class MonInjDock(QDockWidget):
    def __init__(self, name):
        QDockWidget.__init__(self, name)
        self.setObjectName(name)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

    def layout_widgets(self, widgets):
        scroll_area = QScrollArea()
        self.setWidget(scroll_area)

        grid = FlowLayout()
        grid_widget = QWidget()
        grid_widget.setLayout(grid)

        for widget in sorted(widgets):
            grid.addWidget(widget)

        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_widget)
