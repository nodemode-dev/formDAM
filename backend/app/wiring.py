_connected = False


def connect() -> None:
    global _connected
    if _connected:
        return
    _connected = True
    from .services import clipsvc, followon, geosvc, metasvc, stacksvc

    metasvc.on_applied(stacksvc.on_metadata)
    metasvc.on_applied(geosvc.on_metadata)
    followon.register("clip", clipsvc.ready, clipsvc.index_job)
