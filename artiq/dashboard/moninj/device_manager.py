import asyncio
import logging
from collections import defaultdict
from itertools import chain

from sipyco.pc_rpc import AsyncioClient
from sipyco.sync_struct import Subscriber

from artiq.coredevice.comm_moninj import TTLOverride, TTLProbe
from artiq.dashboard.moninj.util import setup_from_ddb
from artiq.dashboard.moninj.widgets.dac import DACWidget
from artiq.dashboard.moninj.widgets.dds import DDSWidget
from artiq.dashboard.moninj.widgets.ttl import TTLWidget

logger = logging.getLogger(__name__)


class WidgetContainer:
    def __init__(self, setup_layout=lambda x: None):
        self.setup_layout = setup_layout
        self._widgets = dict()
        self._widgets_by_uid = dict()

    async def remove_by_widget(self, widget):
        widget.deleteLater()
        await widget.setup_monitoring(False)
        del self._widgets_by_uid[next(uid for uid, wkey in self._widgets_by_uid.items() if wkey == widget.sort_key)]
        del self._widgets[widget.sort_key]
        self.setup_layout(self._widgets.values())

    async def remove_by_key(self, key):
        await self.remove_by_widget(self._widgets[key])

    async def remove_by_uid(self, uid):
        await self.remove_by_key(self._widgets_by_uid[uid])

    async def add(self, uid, widget):
        self._widgets_by_uid[uid] = widget.sort_key
        self._widgets[widget.sort_key] = widget
        await widget.setup_monitoring(True)
        self.setup_layout(self._widgets.values())

    def get_by_key(self, key):
        return self._widgets.get(key, None)

    def values(self):
        return self._widgets.values()


class DeviceManager:
    def __init__(self):
        self._backstore = dict()
        self.reconnect_signal = asyncio.Event()
        self.proxy_moninj_server = None
        self.proxy_moninj_pubsub_port = None
        self.proxy_moninj_rpc_port = None

        self.moninj_connection_pubsub = None
        self.moninj_connection_rpc = None
        self.moninj_connector_task = asyncio.ensure_future(self.moninj_connector())

        self.ddb = dict()
        self.description = set()

        self.dds_sysclk = 0
        self.docks = defaultdict(WidgetContainer)

    def init_ddb(self, ddb):
        self.ddb = ddb
        return ddb

    async def notify(self, _mod):
        def set_connection(moninj_serv, pubsub_port, rpc_port):
            self.proxy_moninj_server = moninj_serv
            self.proxy_moninj_pubsub_port = pubsub_port
            self.proxy_moninj_rpc_port = rpc_port
            self.reconnect_signal.set()

        proxy_moninj_server, proxy_moninj_pubsub_port, proxy_moninj_rpc_port, dds_sysclk, new_desc = \
            setup_from_ddb(self.ddb)
        self.dds_sysclk = dds_sysclk if dds_sysclk else 0
        if proxy_moninj_server != self.proxy_moninj_server:
            set_connection(proxy_moninj_server, proxy_moninj_pubsub_port, proxy_moninj_rpc_port)
        for uid, comment, klass, arguments in new_desc - self.description:
            widget = klass(self, *arguments)
            if comment:
                widget.setToolTip(comment)
            await self.docks[klass].add(uid, widget)
        for uid, _, klass, _ in self.description - new_desc:
            await self.docks[klass].remove_by_uid(uid)
        self.description = new_desc

    def monitor_cb(self, channel, probe, value):
        if widget := self.docks[TTLWidget].get_by_key(channel):
            if probe == TTLProbe.level.value:
                widget.cur_level = bool(value)
            elif probe == TTLProbe.oe.value:
                widget.cur_oe = bool(value)
            widget.refresh_display()
        if widget := self.docks[DDSWidget].get_by_key((channel, probe)):
            widget.cur_frequency = value * self.dds_sysclk / 2 ** 32
            widget.refresh_display()
        if widget := self.docks[DACWidget].get_by_key((channel, probe)):
            widget.cur_value = value
            widget.refresh_display()

    def injection_status_cb(self, channel, override, value):
        if widget := self.docks[TTLWidget].get_by_key(channel):
            if override == TTLOverride.en.value:
                widget.cur_override = bool(value)
            if override == TTLOverride.level.value:
                widget.cur_override_level = bool(value)
            widget.refresh_display()

    def disconnect_cb(self):
        logger.error("lost connection to core device moninj")
        self.reconnect_signal.set()

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
        if mod["action"] == "setitem":
            path_, key_, value_ = mod["path"], mod["key"], mod["value"]
            target = self._backstore
            for key in path_:
                target = target[key]
            if 'injection_status' in path_ and len(path_) > 1:
                self.injection_status_cb(path_[-1], key_, value_)
            if 'monitor' in path_ and len(path_) > 1:
                self.monitor_cb(path_[-1], key_, value_)
            if 'connected' in path_:
                if (key_ in ['coredev', 'master']) and not value_:
                    self.disconnect_cb()

    async def moninj_connector(self):
        async def init_connection(pubsub, rpc):
            self.moninj_connection_pubsub = pubsub
            self.moninj_connection_rpc = rpc
            for widget in self.widgets:
                await widget.setup_monitoring(True)
                widget.setEnabled(True)

        while True:
            await self.reconnect_signal.wait()
            self.reconnect_signal.clear()
            self._reset_connection_state()
            # if there is no moninj server defined, just stop connecting
            if self.proxy_moninj_server is None:
                continue
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
                self.reconnect_signal.set()
            else:
                await init_connection(new_moninj_pubsub, new_moninj_rpc)

    async def close(self):
        self.moninj_connector_task.cancel()
        try:
            await asyncio.wait_for(self.moninj_connector_task, None)
        except asyncio.CancelledError:
            pass
        self._reset_connection_state()

    def _reset_connection_state(self):
        async def ensure_connection_closed():
            if self.moninj_connection_pubsub is not None:
                asyncio.ensure_future(self.moninj_connection_pubsub.close())
            if self.moninj_connection_rpc is not None:
                asyncio.ensure_future(self.moninj_connection_rpc.close())
        asyncio.ensure_future(ensure_connection_closed())
        self.moninj_connection_pubsub = None
        self.moninj_connection_rpc = None
        for widget in self.widgets:
            widget.setEnabled(False)

    @property
    def widgets(self):
        return chain.from_iterable(x.values() for x in self.docks.values())
