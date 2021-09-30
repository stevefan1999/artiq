from sipyco.sync_struct import Subscriber

from artiq.dashboard.moninj.device_manager import DeviceManager
from artiq.dashboard.moninj.widgets.moninj_dock import MonInjDock


class MonInj:
    def __init__(self, server, proxy_core_pubsub_port, proxy_core_rpc_port):
        self.ttl_dock = MonInjDock("TTL")
        self.dds_dock = MonInjDock("DDS")
        self.dac_dock = MonInjDock("DAC")

        self.dm = DeviceManager(server, proxy_core_pubsub_port, proxy_core_rpc_port)
        self.dm.ttl_cb = lambda: self.ttl_dock.layout_widgets(
            self.dm.ttl_widgets.values())
        self.dm.dds_cb = lambda: self.dds_dock.layout_widgets(
            self.dm.dds_widgets.values())
        self.dm.dac_cb = lambda: self.dac_dock.layout_widgets(
            self.dm.dac_widgets.values())

        self.subscriber = Subscriber("devices", self.dm.init_ddb, self.dm.notify)

    async def start(self, server, port):
        await self.subscriber.connect(server, port)

    async def stop(self):
        await self.subscriber.close()
        if self.dm is not None:
            await self.dm.close()
