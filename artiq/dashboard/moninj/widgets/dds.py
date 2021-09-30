from artiq.dashboard.moninj.simple_display import SimpleDisplayWidget

class DDSWidget(SimpleDisplayWidget):
    def __init__(self, dm, bus_channel, channel, title):
        self.bus_channel = bus_channel
        self.channel = channel
        self.cur_frequency = 0
        SimpleDisplayWidget.__init__(self, title)

    def refresh_display(self):
        self.value.setText(f'<font size="4">{self.cur_frequency / 1e6:.7f}</font><font size="2"> MHz</font>')

    def sort_key(self):
        return self.bus_channel, self.channel
