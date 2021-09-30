from artiq.dashboard.moninj.simple_display import SimpleDisplayWidget


class DACWidget(SimpleDisplayWidget):
    def __init__(self, dm, spi_channel, channel, title):
        self.spi_channel = spi_channel
        self.channel = channel
        self.cur_value = 0
        SimpleDisplayWidget.__init__(self, f"{title} ch{channel}")

    def refresh_display(self):
        self.value.setText(f'<font size="4">{self.cur_value * 100 / 2 ** 16:.3f}</font><font size="2"> %</font>')

    def sort_key(self):
        return self.spi_channel, self.channel
