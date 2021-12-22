from sipyco.sync_struct import Subscriber

from artiq.dashboard.moninj.device_manager import DeviceManager, WidgetContainer
from artiq.dashboard.moninj.widgets.dac import DACWidget
from artiq.dashboard.moninj.widgets.dds import DDSWidget
from artiq.dashboard.moninj.moninj_dock import MonInjDock
from artiq.dashboard.moninj.widgets.ttl import TTLWidget


class MonInj:
    def __init__(self):
        self.ttl_dock = MonInjDock("TTL")
        self.dds_dock = MonInjDock("DDS")
        self.dac_dock = MonInjDock("DAC")

        self.dm = DeviceManager()
        self.dm.docks.update({
            TTLWidget: WidgetContainer(lambda x: self.ttl_dock.layout_widgets(x)),
            DDSWidget: WidgetContainer(lambda x: self.dds_dock.layout_widgets(x)),
            DACWidget: WidgetContainer(lambda x: self.dac_dock.layout_widgets(x))
        })

        self.subscriber = Subscriber("devices", self.dm.init_ddb, self.dm.notify)

    async def start(self, server, port):
        await self.subscriber.connect(server, port)

    async def stop(self):
        await self.subscriber.close()
        if self.dm is not None:
            await self.dm.close()


