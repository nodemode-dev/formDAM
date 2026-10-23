_registered = False


def register() -> bool:
    global _registered
    if _registered:
        return True
    try:
        import pi_heif
    except Exception:
        return False
    pi_heif.register_heif_opener()
    _registered = True
    return True


def heif_available() -> bool:
    return register()
