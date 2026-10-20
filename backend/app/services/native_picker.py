import os
import shutil
import subprocess
import sys
import threading
from typing import List, Optional

_LOCK = threading.Lock()


class PickerBusy(Exception):
    pass


class PickerUnavailable(Exception):
    pass


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _mac(initial: Optional[str]) -> Optional[str]:
    prompt = "Choose a folder to import into formDAM"
    script = f'POSIX path of (choose folder with prompt "{prompt}" with showing package contents)'
    if initial and os.path.isdir(initial) and '"' not in initial:
        script = (
            f'POSIX path of (choose folder with prompt "{prompt}" '
            f'default location POSIX file "{initial}" with showing package contents)'
        )
    proc = _run(["osascript", "-e", script])
    if proc.returncode != 0:
        if "canceled" in proc.stderr.lower() or "cancelled" in proc.stderr.lower():
            return None
        raise PickerUnavailable(f"The macOS folder dialog could not open: {proc.stderr.strip() or 'unknown error'}")
    return proc.stdout.strip() or None


def _windows(initial: Optional[str]) -> Optional[str]:
    seed = ""
    if initial and os.path.isdir(initial) and "'" not in initial:
        seed = f"$dialog.SelectedPath = '{initial}';"
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$dialog.Description = 'Choose a folder to import into formDAM';"
        "$dialog.ShowNewFolderButton = $false;"
        + seed
        + "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK)"
        + " { Write-Output $dialog.SelectedPath }"
    )
    proc = _run(["powershell", "-NoProfile", "-STA", "-Command", script])
    if proc.returncode != 0:
        raise PickerUnavailable(f"The Windows folder dialog could not open: {proc.stderr.strip() or 'unknown error'}")
    return proc.stdout.strip() or None


def _linux(initial: Optional[str]) -> Optional[str]:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise PickerUnavailable("No graphical session detected; use the in-app browser below")
    seed = initial if initial and os.path.isdir(initial) else os.path.expanduser("~")
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=Choose a folder to import into formDAM"]
        cmd.append(f"--filename={seed.rstrip(os.sep)}{os.sep}")
        proc = _run(cmd)
        if proc.returncode not in (0, 1):
            raise PickerUnavailable(f"zenity could not open: {proc.stderr.strip() or 'unknown error'}")
        if proc.returncode == 1:
            return None
        return proc.stdout.strip() or None
    if shutil.which("kdialog"):
        proc = _run(["kdialog", "--getexistingdirectory", seed, "--title", "Choose a folder to import into formDAM"])
        if proc.returncode not in (0, 1):
            raise PickerUnavailable(f"kdialog could not open: {proc.stderr.strip() or 'unknown error'}")
        if proc.returncode == 1:
            return None
        return proc.stdout.strip() or None
    raise PickerUnavailable("No system folder dialog found (install zenity or kdialog); use the in-app browser below")


def pick_folder(initial: Optional[str] = None) -> Optional[str]:
    if not _LOCK.acquire(blocking=False):
        raise PickerBusy("A folder picker window is already open")
    try:
        if sys.platform == "darwin":
            picked = _mac(initial)
        elif os.name == "nt":
            picked = _windows(initial)
        else:
            picked = _linux(initial)
    finally:
        _LOCK.release()
    if picked is None:
        return None
    picked = os.path.abspath(picked)
    if not os.path.isdir(picked):
        raise PickerUnavailable("The dialog returned a path that is not a folder")
    return picked
