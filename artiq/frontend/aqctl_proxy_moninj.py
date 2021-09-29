#!/usr/bin/env python3

import argparse
import asyncio
import atexit
import logging
import sys

from sipyco import common_args
from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.pc_rpc import Server as RPCServer
from sipyco.sync_struct import Publisher, Notifier, Subscriber

from artiq import __version__ as artiq_version
from artiq.coredevice.comm_moninj import CommMonInj

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MonInjMaster:
    def __init__(self, on_connected, on_disconnected, on_core_addr_changed):
        self.ddb, self.on_connected, self.on_disconnected = dict(), on_connected, on_disconnected
        self.on_core_addr_changed = on_core_addr_changed
        self.ddb_notify = Subscriber(notifier_name="devices",
                                     notify_cb=self.on_notify,
                                     target_builder=self.build_ddb,
                                     disconnect_cb=self.on_disconnect)
        self.core_addr_cache = None

    async def connect(self, master, port):
        await self.ddb_notify.connect(master, port)

    async def stop(self):
        try:
            await self.ddb_notify.close()
        finally:
            self.on_disconnected()

    async def on_notify(self, mod):
        async def on_core_change():
            if mod["value"]["arguments"]["host"] is not self.core_addr_cache:
                self.core_addr_cache = self.core_addr
                await self.on_core_addr_changed(self.core_addr)

        if mod["action"] == "init":
            await self.on_connected()
            self.core_addr_cache = self.core_addr

        if mod["action"] == "setitem":
            if mod["key"] == "core":
                await on_core_change()

    def build_ddb(self, init):
        self.ddb = init
        return self.ddb

    async def on_disconnect(self):
        self.on_disconnected()

    @property
    def core_addr(self):
        return self.ddb["core"]["arguments"]["host"]


class MonInjCore:
    def __init__(self, on_connected, on_monitor, on_injection_status, on_disconnected):
        self.on_connected, self.on_disconnected = on_connected, on_disconnected
        self.comm = CommMonInj(on_monitor, on_injection_status, on_disconnected)

    async def connect(self, addr, port):
        try:
            await self.comm.connect(addr, port)
            self.on_connected()
        except asyncio.CancelledError:
            raise
        except:
            logger.error("failed to connect to core device moninj", exc_info=True)
            await asyncio.sleep(10.)

    async def stop(self):
        if self.has_connection:
            await self.comm.close()
            self.on_disconnected()

    @property
    def has_connection(self):
        val = hasattr(self.comm, "_writer")
        if not val:
            self.on_disconnected()
        return val


class MonInjProxy:
    def __init__(self, master, notify_port):
        self.notify = Notifier(dict({
            "monitor": dict(),
            "injection_status": dict(),
            "connected": {"coredev": False, "master": False}
        }))
        self.master_addr = master
        self.master_notify_port = notify_port
        self.core = MonInjCore(
            on_connected=self.on_core_connected,
            on_disconnected=self.on_core_disconnected,
            on_monitor=self.on_monitor,
            on_injection_status=self.on_injection_status,
        )
        self.master = MonInjMaster(
            on_connected=self.on_master_connected,
            on_disconnected=self.on_master_disconnected,
            on_core_addr_changed=self.on_core_addr_changed,
        )

    async def connect(self):
        await self.master.connect(self.master_addr, self.master_notify_port)

    async def reconnect(self):
        await self.stop()
        await self.connect()

    async def stop(self):
        await self.core.stop()
        await self.master.stop()

    async def on_master_connected(self):
        logger.info("connected from master")
        self.notify["connected"]["master"] = True
        await self.core.connect(self.master.core_addr, 1383)

    def on_master_disconnected(self):
        logger.info("disconnected from master")
        self.notify["connected"]["master"] = False

    async def on_core_addr_changed(self, addr):
        await self.core.stop()
        await self.core.connect(addr, 1383)

    def on_core_connected(self):
        logging.info("connected to coredev")
        self.notify["connected"]["coredev"] = True

    def on_core_disconnected(self):
        logger.error("disconnected from core device")
        self.notify["connected"]["coredev"] = False

    def on_monitor(self, channel, probe, value):
        if channel not in self.notify["monitor"].raw_view:
            self.notify["monitor"][channel] = dict()
        self.notify["monitor"][channel][probe] = value

    def on_injection_status(self, channel, override, value):
        if channel not in self.notify["injection_status"].raw_view:
            self.notify["injection_status"][channel] = dict()
        self.notify["injection_status"][channel][override] = value

    def monitor_probe(self, enable, channel, probe):
        if self.core.has_connection:
            self.core.comm.monitor_probe(enable, channel, probe)

    def monitor_injection(self, enable, channel, overrd):
        if self.core.has_connection:
            self.core.comm.monitor_injection(enable, channel, overrd)

    def inject(self, channel, override, value):
        if self.core.has_connection:
            self.core.comm.inject(channel, override, value)

    def get_injection_status(self, channel, override):
        if self.core.has_connection:
            self.core.comm.get_injection_status(channel, override)


def get_argparser():
    parser = argparse.ArgumentParser(description="ARTIQ MonInj Proxy")
    parser.add_argument("--version", action="version",
                        version="ARTIQ v{}".format(artiq_version),
                        help="print the ARTIQ version number")

    group = parser.add_argument_group("master related")
    group.add_argument(
        "--master-addr", type=str, required=True,
        help="hostname or IP of the master to connect to")

    group.add_argument(
        "--master-port-notify", type=int, default=3250,
        help="port to connect to for notification service in master")

    common_args.simple_network_args(parser, [
        ("proxy-core-moninj-pubsub", "data synchronization service for core device moninj", 1383),
        ("proxy-core-moninj-rpc", "remote control service to core device moninj", 1384)
    ])

    return parser


def main():
    args = get_argparser().parse_args()
    loop = asyncio.get_event_loop()
    atexit.register(loop.close)
    bind = common_args.bind_address_from_args(args)

    proxy = MonInjProxy(args.master_addr, args.master_port_notify)
    proxy_pubsub = Publisher({
        "coredevice": proxy.notify,
    })
    proxy_rpc = RPCServer({
        "proxy": proxy
    }, allow_parallel=False)
    loop.run_until_complete(proxy.connect())
    loop.run_until_complete(proxy_pubsub.start(bind, args.port_proxy_core_moninj_pubsub))
    loop.run_until_complete(proxy_rpc.start(bind, args.port_proxy_core_moninj_rpc))

    atexit_register_coroutine(proxy_pubsub.stop)
    atexit_register_coroutine(proxy_rpc.stop)
    atexit_register_coroutine(proxy.stop)

    print("ARTIQ Core Device MonInj Proxy is now ready.")
    loop.run_forever()


if __name__ == "__main__":
    main()
