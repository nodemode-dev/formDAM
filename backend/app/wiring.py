_connected = False


def connect() -> None:
    global _connected
    if _connected:
        return
    _connected = True
    from .services import metasvc, stacksvc

    metasvc.on_applied(stacksvc.on_metadata)
