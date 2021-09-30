#!/usr/bin/env python3

import argparse
import asyncio
import atexit
import logging
import os

from sipyco import common_args
from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.pc_rpc import Server as RPCServer
from sipyco.sync_struct import Publisher

from artiq import __version__ as artiq_version
from artiq.master.moninj_proxy import MonInjProxy

logger = logging.getLogger(__name__)


def get_argparser():
    parser = argparse.ArgumentParser(description="ARTIQ MonInj Proxy")
    parser.add_argument("--version", action="version",
                        version="ARTIQ v{}".format(artiq_version),
                        help="print the ARTIQ version number")

    common_args.simple_network_args(parser, [
        ("notify", "master notification service", 3250),
        ("proxy-core-pubsub", "data synchronization service for core device", 1383),
        ("proxy-core-rpc", "remote control service to core device", 1384)
    ])

    parser.add_argument(
        "-s", "--server", default="::1",
        help="hostname or IP of the master to connect to")

    return parser


def main():
    args = get_argparser().parse_args()
    if os.name == "nt":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()
    atexit.register(loop.close)
    bind = common_args.bind_address_from_args(args)

    proxy = MonInjProxy(args.server, args.port_notify)
    proxy_notify = Publisher({
        "coredevice": proxy.notify,
    })
    proxy_rpc = RPCServer({
        "proxy": proxy
    }, allow_parallel=False)
    loop.run_until_complete(proxy.connect())
    loop.run_until_complete(proxy_notify.start(bind, args.port_proxy_core_pubsub))
    loop.run_until_complete(proxy_rpc.start(bind, args.port_proxy_core_rpc))

    atexit_register_coroutine(proxy_notify.stop)
    atexit_register_coroutine(proxy_rpc.stop)
    atexit_register_coroutine(proxy.stop)

    print("ARTIQ Core Device MonInj Proxy is now ready.")
    loop.run_forever()


if __name__ == "__main__":
    main()
