import os
import sys
import time

if os.getenv("ARTIQ_DEBUG", False):
    # A terrible hack
    extra_paths = str(os.getenv("ARTIQ_DEBUG_EXTRA_PATH", "")).split(":")
    sys.path.extend(extra_paths)

    backend = os.getenv("ARTIQ_DEBUG_BACKEND", False)
    if backend == "idea":
        import pydevd_pycharm

        debug_host = str(os.getenv("ARTIQ_DEBUG_IDEA_HOST", "localhost"))
        debug_port = int(os.getenv("ARTIQ_DEBUG_IDEA_PORT", 31234))
        while True:
            try:
                pydevd_pycharm.settrace(host=debug_host, port=debug_port, stdoutToServer=True, stderrToServer=True,
                                        patch_multiprocessing=True, suspend=False)
                break
            except:
                time.sleep(1)
                continue
