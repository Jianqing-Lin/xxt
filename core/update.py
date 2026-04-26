def Vsif(version):
    target = version.split('Autumn-xxt')[-1]
    parts = target.strip().split('.')
    if len(parts) < 3:
        return False
    a, b, c = parts[:3]
    return int(a) > 0 or int(b) > 0 or int(c) > 1


def Update(logger, enabled=False):
    if enabled:
        logger("Autumn-xxt update check is currently not configured", 2)
