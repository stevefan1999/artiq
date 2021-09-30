import asyncio
import logging

from sipyco.pc_rpc import AsyncioClient
from sipyco.sync_struct import Subscriber

from artiq.coredevice.comm_moninj import TTLOverride, TTLProbe
from artiq.dashboard.moninj.util import setup_from_ddb
from artiq.dashboard.moninj.widgets.dac import DACWidget
from artiq.dashboard.moninj.widgets.dds import DDSWidget
from artiq.dashboard.moninj.widgets.ttl import TTLWidget

logger = logging.getLogger(__name__)


class DeviceManager:
    def __init__(self):
        self._backstore = dict()
        self.reconnect_core = asyncio.Event()
        self.proxy_moninj_server = None
        self.proxy_moninj_pubsub_port = None
        self.proxy_moninj_rpc_port = None

        self.moninj_connection_pubsub = None
        self.moninj_connection_rpc = None
        self.moninj_connector_task = asyncio.ensure_future(self.moninj_connector())

        self.ddb = dict()
        self.description = set()
        self.widgets_by_uid = dict()

        self.dds_sysclk = 0
        self.ttl_cb = lambda: None
        self.ttl_widgets = dict()
        self.dds_cb = lambda: None
        self.dds_widgets = dict()
        self.dac_cb = lambda: None
        self.dac_widgets = dict()

    def init_ddb(self, ddb):
        self.ddb = ddb
        return ddb

    async def notify(self, _mod):
        proxy_moninj_server, proxy_moninj_pubsub_port, proxy_moninj_rpc_port, dds_sysclk, description = \
            setup_from_ddb(self.ddb)
        self.dds_sysclk = dds_sysclk if dds_sysclk else 0

        if proxy_moninj_server != self.proxy_moninj_server:
            self.proxy_moninj_server = proxy_moninj_server
            self.proxy_moninj_pubsub_port = proxy_moninj_pubsub_port
            self.proxy_moninj_rpc_port = proxy_moninj_rpc_port
            self.reconnect_core.set()

        for to_remove in self.description - description:
            widget = self.widgets_by_uid[to_remove.uid]
            del self.widgets_by_uid[to_remove.uid]

            if isinstance(widget, TTLWidget):
                await self.setup_ttl_monitoring(False, widget.channel)
                widget.deleteLater()
                del self.ttl_widgets[widget.channel]
                self.ttl_cb()
            elif isinstance(widget, DDSWidget):
                await self.setup_dds_monitoring(False, widget.bus_channel, widget.channel)
                widget.deleteLater()
                del self.dds_widgets[(widget.bus_channel, widget.channel)]
                self.dds_cb()
            elif isinstance(widget, DACWidget):
                await self.setup_dac_monitoring(False, widget.spi_channel, widget.channel)
                widget.deleteLater()
                del self.dac_widgets[(widget.spi_channel, widget.channel)]
                self.dac_cb()
            else:
                raise ValueError

        for to_add in description - self.description:
            widget = to_add.cls(self, *to_add.arguments)
            if to_add.comment is not None:
                widget.setToolTip(to_add.comment)
            self.widgets_by_uid[to_add.uid] = widget

            if isinstance(widget, TTLWidget):
                self.ttl_widgets[widget.channel] = widget
                self.ttl_cb()
                await self.setup_ttl_monitoring(True, widget.channel)
            elif isinstance(widget, DDSWidget):
                self.dds_widgets[(widget.bus_channel, widget.channel)] = widget
                self.dds_cb()
                await self.setup_dds_monitoring(True, widget.bus_channel, widget.channel)
            elif isinstance(widget, DACWidget):
                self.dac_widgets[(widget.spi_channel, widget.channel)] = widget
                self.dac_cb()
                await self.setup_dac_monitoring(True, widget.spi_channel, widget.channel)
            else:
                raise ValueError

        self.description = description

    async def ttl_set_mode(self, channel, mode):
        if self.moninj_connection_rpc is not None:
            widget = self.ttl_widgets[channel]
            if mode == "0":
                widget.cur_override = True
                widget.cur_level = False

                await self.moninj_connection_rpc.inject(channel, TTLOverride.level.value, 0)
                await self.moninj_connection_rpc.inject(channel, TTLOverride.oe.value, 1)
                await self.moninj_connection_rpc.inject(channel, TTLOverride.en.value, 1)
            elif mode == "1":
                widget.cur_override = True
                widget.cur_level = True
                await self.moninj_connection_rpc.inject(channel, TTLOverride.level.value, 1)
                await self.moninj_connection_rpc.inject(channel, TTLOverride.oe.value, 1)
                await self.moninj_connection_rpc.inject(channel, TTLOverride.en.value, 1)
            elif mode == "exp":
                widget.cur_override = False
                await self.moninj_connection_rpc.inject(channel, TTLOverride.en.value, 0)
            else:
                raise ValueError
            # override state may have changed
            widget.refresh_display()

    async def setup_ttl_monitoring(self, enable, channel):
        if self.moninj_connection_rpc is not None:
            await self.moninj_connection_rpc.monitor_probe(enable, channel, TTLProbe.level.value)
            await self.moninj_connection_rpc.monitor_probe(enable, channel, TTLProbe.oe.value)
            await self.moninj_connection_rpc.monitor_injection(enable, channel, TTLOverride.en.value)
            await self.moninj_connection_rpc.monitor_injection(enable, channel, TTLOverride.level.value)
            if enable:
                await self.moninj_connection_rpc.get_injection_status(channel, TTLOverride.en.value)

    async def setup_dds_monitoring(self, enable, bus_channel, channel):
        if self.moninj_connection_rpc is not None:
            await self.moninj_connection_rpc.monitor_probe(enable, bus_channel, channel)

    async def setup_dac_monitoring(self, enable, spi_channel, channel):
        if self.moninj_connection_rpc is not None:
            await self.moninj_connection_rpc.monitor_probe(enable, spi_channel, channel)

    def monitor_cb(self, channel, probe, value):
        if channel in self.ttl_widgets:
            widget = self.ttl_widgets[channel]
            if probe == TTLProbe.level.value:
                widget.cur_level = bool(value)
            elif probe == TTLProbe.oe.value:
                widget.cur_oe = bool(value)
            widget.refresh_display()
        if (channel, probe) in self.dds_widgets:
            widget = self.dds_widgets[(channel, probe)]
            widget.cur_frequency = value * self.dds_sysclk / 2 ** 32
            widget.refresh_display()
        if (channel, probe) in self.dac_widgets:
            widget = self.dac_widgets[(channel, probe)]
            widget.cur_value = value
            widget.refresh_display()

    def injection_status_cb(self, channel, override, value):
        if channel in self.ttl_widgets:
            widget = self.ttl_widgets[channel]
            if override == TTLOverride.en.value:
                widget.cur_override = bool(value)
            if override == TTLOverride.level.value:
                widget.cur_override_level = bool(value)
            widget.refresh_display()

    def disconnect_cb(self):
        logger.error("lost connection to core device moninj")
        self.reconnect_core.set()

    def replay_snapshots(self, data):
        self._backstore = data
        for channel, chan_data in data["monitor"].items():
            for probe, value in chan_data.items():
                self.monitor_cb(channel, probe, value)
        for channel, chan_data in data["injection_status"].items():
            for override, value in chan_data.items():
                self.injection_status_cb(channel, override, value)
        return self._backstore

    def on_notify(self, mod):
        target = self._backstore

        if mod["action"] == "setitem":
            for key in mod["path"]:
                target = target[key]
            if 'injection_status' in mod["path"] and len(mod["path"]) > 1:
                self.injection_status_cb(mod["path"][-1], mod["key"], mod["value"])
            if 'monitor' in mod["path"] and len(mod["path"]) > 1:
                self.monitor_cb(mod["path"][-1], mod["key"], mod["value"])
        if 'path' in mod and 'disconnect' in mod["path"]:
            self.disconnect_cb()

    async def moninj_connector(self):
        while True:
            await self.reconnect_core.wait()
            self.reconnect_core.clear()
            await self.ensure_connection_closed()
            self.moninj_connection_pubsub = None
            self.moninj_connection_rpc = None

            new_moninj_pubsub = Subscriber("coredevice", target_builder=self.replay_snapshots, notify_cb=self.on_notify,
                                           disconnect_cb=self.disconnect_cb)
            new_moninj_rpc = AsyncioClient()
            try:
                await new_moninj_pubsub.connect(self.proxy_moninj_server, self.proxy_moninj_pubsub_port)
                await new_moninj_rpc.connect_rpc(self.proxy_moninj_server, self.proxy_moninj_rpc_port,
                                                 target_name="proxy")
            except asyncio.CancelledError:
                logger.info("cancelled connection to core device moninj")
                break
            except:
                logger.error("failed to connect to core device moninj", exc_info=True)
                await asyncio.sleep(10.)
                self.reconnect_core.set()
                return False
            else:
                self.moninj_connection_pubsub = new_moninj_pubsub
                self.moninj_connection_rpc = new_moninj_rpc
                for ttl_channel in self.ttl_widgets.keys():
                    await self.setup_ttl_monitoring(True, ttl_channel)
                for bus_channel, channel in self.dds_widgets.keys():
                    await self.setup_dds_monitoring(True, bus_channel, channel)
                for spi_channel, channel in self.dac_widgets.keys():
                    await self.setup_dac_monitoring(True, spi_channel, channel)

    async def close(self):
        self.moninj_connector_task.cancel()
        try:
            await asyncio.wait_for(self.moninj_connector_task, None)
        except asyncio.CancelledError:
            pass
        await self.ensure_connection_closed()

    async def ensure_connection_closed(self):
        if self.moninj_connection_pubsub is not None:
            await self.moninj_connection_pubsub.close()
        if self.moninj_connection_rpc is not None:
            await self.moninj_connection_rpc.close()
