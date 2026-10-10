_registered = False


def register() -> bool:
    global _registered
    if _registered:
        return True
    try:
        import pillow_heif
    except Exception:
        return False
    pillow_heif.register_heif_opener()
    _registered = True
    return True


def heif_available() -> bool:
    return register()
