from migen import *

from artiq.coredevice.spi2 import SPI_CONFIG_ADDR, SPI_DATA_ADDR, SPI_END, SPI_INPUT
from artiq.coredevice.urukul import CS_DDS_CH0, CS_DDS_MULTI

class UrukulMonitor(Module):
    def __init__(self, spi_rtlink, phy, nchannels=4):
        # [0:3] = register address, [4:7] = data_high, [8:11] = data_low (or just data for 32-bit transfers)
        self.probes = Array([
            Signal(48) for i in range(nchannels)
        ])
        self.rtlink = spi_rtlink

        current_address = Signal.like(self.rtlink.o.address)
        current_data = Signal.like(self.rtlink.o.data)
        self.sync.rio += If(
            self.rtlink.o.stb,
            current_address.eq(self.rtlink.o.address),
            current_data.eq(self.rtlink.o.data)
        )

        cs = Signal(8)
        length = Signal(8)
        end = Signal()
        input = Signal()
        self.sync.rio += If(
            self.rtlink.o.stb & (current_address == SPI_CONFIG_ADDR),
            cs.eq(current_data[24:]),
            length.eq(current_data[8:16]),
            If(current_data & SPI_END, end.eq(1)).Else(end.eq(0)),
            If(current_data & SPI_INPUT, input.eq(1)).Else(input.eq(0))
        )

        def selected(c):
            if cs == CS_DDS_MULTI:
                return True
            else:
                return c == cs

        data = {
            'values': [Signal(48) for i in range(nchannels)]
        }
        for i in range(nchannels):
            self.sync.rio_phy += If(
                selected(i + CS_DDS_CH0) & (current_address == SPI_DATA_ADDR) & ~input & (length == 31),
                If(end, data['values'][i][:32].eq(current_data)).Else(data['values'][i][32:48].eq(current_data[:16]))
            )

        self.sync.rio_phy += If(
            phy.rtlink.o.stb & (current_address == SPI_DATA_ADDR), [
                If(selected(i + CS_DDS_CH0) & ~input, [
                    self.probes[i].eq(data['values'][i])
                ]) for i in range(nchannels)
            ]
        )
