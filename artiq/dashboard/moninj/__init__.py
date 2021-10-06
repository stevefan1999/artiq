from sipyco.sync_struct import Subscriber

from artiq.dashboard.moninj.device_manager import DeviceManager, Layout
from artiq.dashboard.moninj.widgets.moninj_dock import MonInjDock


class MonInj:
    def __init__(self):
        self.ttl_dock = MonInjDock("TTL")
        self.dds_dock = MonInjDock("DDS")
        self.dac_dock = MonInjDock("DAC")

        self.dm = DeviceManager()
        self.dm.docks.update({
            "TTL": Layout(lambda x: self.ttl_dock.layout_widgets(x)),
            "DDS": Layout(lambda x: self.dds_dock.layout_widgets(x)),
            "DAC": Layout(lambda x: self.dac_dock.layout_widgets(x))
        })

        self.subscriber = Subscriber("devices", self.dm.init_ddb, self.dm.notify)

    async def start(self, server, port):
        await self.subscriber.connect(server, port)

    async def stop(self):
        await self.subscriber.close()
        if self.dm is not None:
            await self.dm.close()
