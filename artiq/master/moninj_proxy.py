import asyncio
import logging

from sipyco.sync_struct import Notifier, Subscriber

from artiq.coredevice.comm_moninj import CommMonInj

logger = logging.getLogger(__name__)


class MonInjProxy:
    def __init__(self, master_server_host, notify_port):
        self.notify = Notifier(dict({"monitor": dict(), "injection_status": dict(), "disconnect": []}))
        self.ddb = dict()
        self.master_server_host = master_server_host
        self.master_notify_port = notify_port
        self.core_connection = CommMonInj(self.on_monitor, self.on_injection_status, self.on_disconnect)
        self.ddb_notify = Subscriber(notifier_name="devices", notify_cb=self.on_notify,
                                     target_builder=self.on_notify_build)

    async def on_notify(self, mod):
        if mod["action"] != "init":
            await self.reconnect()

    async def on_notify_build(self, init):
        self.ddb = init
        await self.connect_coredev()
        return self.ddb

    def on_monitor(self, channel, probe, value):
        if channel not in self.notify["monitor"].raw_view:
            self.notify["monitor"][channel] = dict()
        self.notify["monitor"][channel][probe] = value

    def on_injection_status(self, channel, override, value):
        if channel not in self.notify["injection_status"].raw_view:
            self.notify["injection_status"][channel] = dict()
        self.notify["injection_status"][channel][override] = value

    def on_disconnect(self):
        self.notify["disconnect"].append(None)

    async def reconnect(self):
        await self.stop()
        await self.connect()

    async def stop(self):
        try:
            await self.ddb_notify.close()
            await self.core_connection.close()
        except:
            pass

    async def connect(self):
        await self.ddb_notify.connect(self.master_server_host, self.master_notify_port)

    async def connect_coredev(self):
        try:
            await self.core_connection.connect(self.ddb["core"]["arguments"]["host"], 1383)
        except asyncio.CancelledError:
            raise
        except:
            logger.error("failed to connect to core device moninj", exc_info=True)
            await asyncio.sleep(10.)

    def monitor_probe(self, enable, channel, probe):
        if hasattr(self.core_connection, "_writer"):
            self.core_connection.monitor_probe(enable, channel, probe)

    def monitor_injection(self, enable, channel, overrd):
        if hasattr(self.core_connection, "_writer"):
            self.core_connection.monitor_injection(enable, channel, overrd)

    def inject(self, channel, override, value):
        if hasattr(self.core_connection, "_writer"):
            self.core_connection.inject(channel, override, value)

    def get_injection_status(self, channel, override):
        if hasattr(self.core_connection, "_writer"):
            self.core_connection.get_injection_status(channel, override)
