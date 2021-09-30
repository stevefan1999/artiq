from collections import namedtuple
from typing import Optional

import typing

from artiq.dashboard.moninj.widgets.dac import DACWidget
from artiq.dashboard.moninj.widgets.dds import DDSWidget
from artiq.dashboard.moninj.widgets.ttl import TTLWidget


def setup_from_ddb(ddb):
    core_addr: Optional[str] = None
    dds_sysclk: Optional[int] = None
    description: typing.Set[WidgetDesc] = set()

    for k, v in ddb.items():
        comment = None
        if "comment" in v:
            comment = v["comment"]
        try:
            if isinstance(v, dict) and v["type"] == "local":
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

                if k == "core":
                    core_addr = args["host"]
                elif module_ == "artiq.coredevice.ttl":
                    description.add(WidgetDesc(k, comment, TTLWidget, (args["channel"], class_ == "TTLOut", k)))
                elif module_ == "artiq.coredevice.ad9914" and class_ == "AD9914":
                    dds_sysclk = args["sysclk"]
                    description.add(WidgetDesc(k, comment, DDSWidget, (args["bus_channel"], args["channel"], k)))
                elif module_ == "artiq.coredevice.ad53xx" and class_ == "AD53XX":
                    handle_spi()
                elif module_ == "artiq.coredevice.zotino" and class_ == "Zotino":
                    handle_spi()
        except KeyError:
            pass
    return core_addr, dds_sysclk, description


WidgetDesc = namedtuple("WidgetDesc", "uid comment cls arguments")
