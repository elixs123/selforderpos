LIVE = "uživo"
MOVED = "kamera je pomjerena"  # isto kao cameras/tamper.py MOVED


def camera_statuses(guard) -> dict[str, str]:
    """Stanje svake kamere: lokalne kamere iz readera, kamere na serveru iz zadnjeg odgovora servera."""
    if hasattr(guard, "camera_statuses"):
        return dict(guard.camera_statuses)
    return {name: reader.status for name, reader in getattr(guard, "readers", {}).items()}


def cameras_problem(guard, cameras_enabled: bool, lock_on_moved: bool = False) -> str:
    """Prazno ako kamere rade (ili su isključene u postavkama), inače razlog zašto kasa ne smije raditi.
    Pomjerena kamera zaključava kasu samo ako je to uključeno u postavkama (lock_on_moved)."""
    if not cameras_enabled:
        return ""
    if guard is None:
        return "Kamere nisu pokrenute."
    if getattr(guard, "state", "") == "offline":
        return getattr(guard, "message", "") or "Server kamera nije dostupan."
    down = [f"{name} ({status})" for name, status in camera_statuses(guard).items() if status != LIVE]
    if down:
        return "Kamera bez slike: " + ", ".join(down)
    tampered = [f"{name} ({problem})" for name, problem in dict(getattr(guard, "tamper_problems", {})).items()
                if lock_on_moved or problem != MOVED]
    if tampered:
        return "Kamera: " + ", ".join(tampered)
    return getattr(guard, "counter_problem", "")
