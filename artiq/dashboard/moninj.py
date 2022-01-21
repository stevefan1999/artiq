import asyncio
import logging
from collections import namedtuple
from itertools import chain

from PyQt5 import QtWidgets
from sipyco.sync_struct import Subscriber
from sipyco.pc_rpc import AsyncioClient

from artiq.coredevice.comm_moninj import CommMonInj
from artiq.dashboard.moninj_widgets.dac import DACWidget
from artiq.dashboard.moninj_widgets.dds import DDSWidget
from artiq.dashboard.moninj_widgets.ttl import TTLWidget
from artiq.dashboard.moninj_widgets.urukul import UrukulWidget
from artiq.gui.flowlayout import FlowLayout

logger = logging.getLogger(__name__)


class _WidgetContainer:
    def __init__(self, setup_layout=lambda x: None):
        self.setup_layout = setup_layout
        self._widgets = {}
        self._widgets_by_uid = {}

    def remove_by_widget(self, widget):
        widget.deleteLater()
        widget.setup_monitoring(False)
        uid = next((uid for uid, wkey in self._widgets_by_uid.items() if
                    wkey == widget.sort_key), None)
        if uid is not None:
            del self._widgets_by_uid[uid]
        del self._widgets[widget.sort_key]
        self.setup_layout(self._widgets.values())

    def remove_by_key(self, key):
        self.remove_by_widget(self._widgets[key])

    def remove_by_uid(self, uid):
        self.remove_by_key(self._widgets_by_uid[uid])

    def add(self, uid, widget):
        self._widgets_by_uid[uid] = widget.sort_key
        self._widgets[widget.sort_key] = widget
        widget.setup_monitoring(True)
        self.setup_layout(self._widgets.values())

    def get_by_key(self, key):
        return self._widgets.get(key, None)

    def values(self):
        return self._widgets.values()


_WidgetDesc = namedtuple("_WidgetDesc", "uid comment cls arguments")


def setup_from_ddb(ddb):
    core_addr = None
    proxy_addr = None
    proxy_port = None
    proxy_port_rpc = None
    dds_sysclk = None
    description = set()

    for k, v in ddb.items():
        comment = None
        if "comment" in v:
            comment = v["comment"]
        try:
            if not isinstance(v, dict):
                continue

            if v["type"] == "controller":
                if k == "moninj":
                    proxy_addr = v["host"]
                    proxy_port = v["port_proxy"]
                    proxy_port_rpc = v["port"]

            if v["type"] == "local":
                args, module_, class_ = v["arguments"], v["module"], v["class"]
                is_ad9910 = module_ == "artiq.coredevice.ad9910" and class_ == "AD9910"
                is_ad9912 = module_ == "artiq.coredevice.ad9912" and class_ == "AD9912"
                is_ad9914 = module_ == "artiq.coredevice.ad9914" and class_ == "AD9914"
                is_ad53xx = module_ == "artiq.coredevice.ad53xx" and class_ == "AD53XX"
                is_zotino = module_ == "artiq.coredevice.zotino" and class_ == "Zotino"
                if module_ == "artiq.coredevice.ttl":
                    channel = args["channel"]
                    description.add(_WidgetDesc(k, comment, TTLWidget, (
                        channel, class_ == "TTLOut", k)))
                elif is_ad9914:
                    dds_sysclk, bus_channel, channel = args["sysclk"], args[
                        "bus_channel"], args["channel"]
                    description.add(_WidgetDesc(k, comment, DDSWidget,
                                                (bus_channel, channel, k)))
                elif is_ad53xx or is_zotino:
                    spi_device = ddb[args["spi_device"]]
                    while isinstance(spi_device, str):
                        spi_device = ddb[spi_device]
                    spi_channel = spi_device["arguments"]["channel"]
                    for channel in range(32):
                        widget = _WidgetDesc((k, channel), comment, DACWidget,
                                             (spi_channel, channel, k))
                        description.add(widget)
                elif is_ad9910 or is_ad9912:
                    urukul_device = ddb[args["cpld_device"]]
                    sw_channel = ddb[args["sw_device"]]["arguments"]["channel"]
                    channel = args["chip_select"] - 4
                    pll = args["pll_n"]
                    refclk = urukul_device["arguments"]["refclk"]
                    spi_device = ddb[urukul_device["arguments"]["spi_device"]]
                    spi_channel = spi_device["arguments"]["channel"]
                    widget = _WidgetDesc(k, comment, UrukulWidget,
                                         (spi_channel, channel, k, sw_channel, refclk, pll, is_ad9910))
                    description.add(widget)
        except KeyError:
            pass
    if proxy_addr and proxy_port:
        return "proxy", proxy_addr, proxy_port, proxy_port_rpc, dds_sysclk, description
    missing = ["proxy address"] if not proxy_addr else []
    missing += ["proxy port"] if not proxy_port else []
    logger.warning(f"missing {' and '.join(missing)} for proxy support")
    logger.warning("falling back to direct connection")
    return "fallback", core_addr, 1383, None, dds_sysclk, description


class _DeviceManager:
    def __init__(self):
        self.moninj_addr = None
        self.moninj_port = None
        self.moninj_conn_mode = None
        self.moninj_port_rpc = None
        self.moninj_proxy_rpc_connection = None

        self.health = None
        self.healthcheck_task = None

        self.reconnect_core = asyncio.Event()
        self.core_connection = None
        self.core_connector_task = asyncio.ensure_future(self.core_connector())

        self.ddb = {}
        self.description = set()

        self.dds_sysclk = 0
        self.docks = {}

    def init_ddb(self, ddb):
        self.ddb = ddb
        return ddb

    def notify(self, mod):
        conn_mode, moninj_addr, moninj_port, moninj_port_rpc, dds_sysclk, new_desc = setup_from_ddb(self.ddb)

        if moninj_addr != self.moninj_addr or \
                moninj_port != self.moninj_port or \
                conn_mode != self.moninj_conn_mode:
            self.moninj_conn_mode = conn_mode
            self.moninj_addr = moninj_addr
            self.moninj_port = moninj_port
            self.moninj_port_rpc = moninj_port_rpc
            self.reconnect_core.set()
        for uid, _, klass, _ in self.description - new_desc:
            self.docks[klass].remove_by_uid(uid)
        for uid, comment, klass, arguments in new_desc - self.description:
            widget = klass(self, *arguments)
            if comment:
                widget.setToolTip(comment)
            self.docks[klass].add(uid, widget)
        self.description = new_desc

    def monitor_cb(self, channel, probe, value):
        for klass, widgets in self.docks.items():
            if hasattr(klass, 'on_monitor'):
                key = klass.extract_key(channel=channel, probe=probe)
                widget = widgets.get_by_key(key)
                if widget:
                    widget.on_monitor(probe=probe, value=value)
                    widget.refresh_display()

    def injection_status_cb(self, channel, override, value):
        for klass, widgets in self.docks.items():
            if hasattr(klass, 'on_injection_status'):
                key = klass.extract_key(channel=channel)
                widget = widgets.get_by_key(key)
                if widget:
                    widget.on_injection_status(value=value, override=override)
                    widget.refresh_display()

    def disconnect_cb(self):
        logger.error("lost connection to moninj proxy")
        self.reconnect_proxy.set()

    async def health_check_poll(self):
        try:
            while True:
                healthy = await self.moninj_proxy_rpc_connection.healthy()
                if healthy["health"] != self.health:
                    if self.health and healthy["health"] == "healthy":
                        logger.info("proxy is in a healthy state")
                    if healthy["health"] == "unhealthy":
                        degraded = healthy["degraded"]
                        logger.warning(f"proxy is in an unhealthy state, degraded components: {' and '.join(degraded)}")
                    self.health = healthy["health"]
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            return

    async def core_connector(self):
        while True:
            await self.reconnect_core.wait()
            self.reconnect_core.clear()
            if self.core_connection is not None:
                await self.core_connection.close()
                self.core_connection = None
            new_core_connection = CommMonInj(self.monitor_cb, self.injection_status_cb,
                    self.disconnect_cb)
            try:
                logger.info(f"using {self.moninj_conn_mode} for moninj support")
                await new_core_connection.connect(self.moninj_addr, self.moninj_port)
            except asyncio.CancelledError:
                logger.info("cancelled connection to core device moninj")
                break
            except:
                logger.error("failed to connect to core device moninj", exc_info=True)
                await asyncio.sleep(10.)
                self.reconnect_core.set()
            else:
                self.core_connection = new_core_connection
                if self.moninj_conn_mode == "proxy" and self.moninj_port_rpc:
                    await self._proxy_rpc_init()
                logger.info("connected to moninj proxy")
                for widget in self.widgets:
                    widget.setup_monitoring(True)
                    widget.setEnabled(True)

    async def _proxy_rpc_init(self):
        new_conn = None
        if self.moninj_proxy_rpc_connection is not None:
            self.moninj_proxy_rpc_connection.close_rpc()
            self.moninj_proxy_rpc_connection = None
        if self.healthcheck_task is not None:
            self.healthcheck_task.cancel()
            self.healthcheck_task = None
        try:
            new_conn = AsyncioClient()
            await new_conn.connect_rpc(self.moninj_addr, self.moninj_port_rpc, "health")
        except:
            logger.warning("connection to proxy rpc service failed")
        else:
            logger.debug("rpc support enabled")
            self.moninj_proxy_rpc_connection = new_conn
            self.healthcheck_task = asyncio.ensure_future(self.health_check_poll())

    async def close(self):
        self.core_connector_task.cancel()
        try:
            await asyncio.wait_for(self.core_connector_task, None)
        except asyncio.CancelledError:
            pass
        if self.core_connection is not None:
            await self.core_connection.close()
        if self.healthcheck_task is not None:
            self.healthcheck_task.cancel()
            self.healthcheck_task = None
        for widget in self.widgets:
            widget.setEnabled(False)

    @property
    def widgets(self):
        return chain.from_iterable(x.values() for x in self.docks.values())


class _MonInjDock(QtWidgets.QDockWidget):
    def __init__(self, name):
        super().__init__(name)
        self.setObjectName(name)
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)

    def layout_widgets(self, widgets):
        scroll_area = QtWidgets.QScrollArea()
        self.setWidget(scroll_area)

        grid = FlowLayout()
        grid_widget = QtWidgets.QWidget()
        grid_widget.setLayout(grid)

        for widget in sorted(widgets):
            grid.addWidget(widget)

        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_widget)


class MonInj:
    def __init__(self):
        self.ttl_dock = _MonInjDock("TTL")
        self.dds_dock = _MonInjDock("DDS")
        self.dac_dock = _MonInjDock("DAC")
        self.urukul_dock = _MonInjDock("Urukul")

        self.dm = _DeviceManager()
        self.dm.docks.update({
            TTLWidget: _WidgetContainer(
                lambda x: self.ttl_dock.layout_widgets(x)),
            DDSWidget: _WidgetContainer(
                lambda x: self.dds_dock.layout_widgets(x)),
            DACWidget: _WidgetContainer(
                lambda x: self.dac_dock.layout_widgets(x)),
            UrukulWidget: _WidgetContainer(
                lambda x: self.urukul_dock.layout_widgets(x))
        })

        self.subscriber = Subscriber("devices", self.dm.init_ddb, self.dm.notify)

    async def start(self, server, port):
        await self.subscriber.connect(server, port)

    async def stop(self):
        await self.subscriber.close()
        if self.dm is not None:
            await self.dm.close()
