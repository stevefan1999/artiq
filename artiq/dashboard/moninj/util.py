from collections import namedtuple

from artiq.dashboard.moninj.widgets.dac import DACWidget
from artiq.dashboard.moninj.widgets.dds import DDSWidget
from artiq.dashboard.moninj.widgets.ttl import TTLWidget
from artiq.dashboard.moninj.widgets.urukul import UrukulWidget


def setup_from_ddb(ddb):
    proxy_moninj_server = None
    proxy_moninj_pubsub_port = None
    proxy_moninj_rpc_port = None
    dds_sysclk = None
    description = set()

    for k, v in ddb.items():
        comment = None
        if "comment" in v:
            comment = v["comment"]
        try:
            if not isinstance(v, dict):
                continue
            if v["type"] == "controller" and k == "moninj":
                proxy_moninj_server = v["host"]
                proxy_moninj_pubsub_port = v["pubsub_port"]
                proxy_moninj_rpc_port = v["rpc_port"]
            if v["type"] == "local":
                args, module_, class_ = v["arguments"], v["module"], v["class"]

                def handle_spi():
                    spi_device = args["spi_device"]
                    spi_device = ddb[spi_device]
                    while isinstance(spi_device, str):
                        spi_device = ddb[spi_device]
                    spi_channel = spi_device["arguments"]["channel"]
                    for channel in range(32):
                        widget = WidgetDesc((k, channel), comment, DACWidget, (spi_channel, channel, k))
                        description.add(widget)

                def handle_urukul():
                    urukul_device = ddb[args["cpld_device"]]
                    urukul_args = urukul_device["arguments"]

                    sw_channel = ddb[args["sw_device"]]["arguments"]["channel"]
                    channel = args["chip_select"] - 4
                    pll = args["pll_n"]
                    refclk = urukul_args["refclk"]
                    spi_device = ddb[urukul_args["spi_device"]]
                    spi_channel = spi_device["arguments"]["channel"]
                    widget = WidgetDesc(k, comment, UrukulWidget,
                                        (spi_channel, channel, k, sw_channel, refclk, pll, v["class"] == "AD9910"))
                    description.add(widget)

                if module_ == "artiq.coredevice.ttl":
                    description.add(WidgetDesc(k, comment, TTLWidget, (args["channel"], class_ == "TTLOut", k)))
                elif module_ == "artiq.coredevice.ad9914" and class_ == "AD9914":
                    dds_sysclk = args["sysclk"]
                    description.add(WidgetDesc(k, comment, DDSWidget, (args["bus_channel"], args["channel"], k)))
                elif module_ == "artiq.coredevice.ad53xx" and class_ == "AD53XX":
                    handle_spi()
                elif module_ == "artiq.coredevice.zotino" and class_ == "Zotino":
                    handle_spi()
                elif module_ == "artiq.coredevice.ad9910" and class_ == "AD9910":
                    handle_urukul()
                elif module_ == "artiq.coredevice.ad9912" and class_ == "AD9912":
                    handle_urukul()
        except KeyError:
            pass
    return proxy_moninj_server, proxy_moninj_pubsub_port, proxy_moninj_rpc_port, dds_sysclk, description


WidgetDesc = namedtuple("WidgetDesc", "uid comment cls arguments")
