import os
import subprocess
import sys
from typing import List

SERVICES = {
    "airdrop": "NSSharingServiceNameSendViaAirDrop",
    "mail": "NSSharingServiceNameComposeEmail",
    "messages": "NSSharingServiceNameComposeMessage",
}
TIMEOUT_S = 900


def available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import AppKit  # noqa: F401
    except Exception:
        return False
    return True


def launch(service: str, items: List[str], subject: str = "") -> bool:
    if service not in SERVICES or not available():
        return False
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--share", service, subject]
    else:
        entry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop_entry.py")
        args = [sys.executable, entry, "--share", service, subject]
    try:
        subprocess.Popen(args + items, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def run(argv: List[str]) -> int:
    import AppKit
    import Foundation

    service_key, subject, raw = argv[0], argv[1], argv[2:]
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    items = []
    for value in raw:
        if value.startswith(("http://", "https://")):
            items.append(Foundation.NSURL.URLWithString_(value))
        elif os.path.isfile(value):
            items.append(Foundation.NSURL.fileURLWithPath_(value))
        elif value:
            items.append(Foundation.NSString.stringWithString_(value))
    service = AppKit.NSSharingService.sharingServiceNamed_(getattr(AppKit, SERVICES[service_key]))
    if service is None or not items or not service.canPerformWithItems_(items):
        return 2

    class Done(AppKit.NSObject):
        def sharingService_didShareItems_(self, svc, shared):
            app.terminate_(None)

        def sharingService_didFailToShareItems_error_(self, svc, failed, error):
            app.terminate_(None)

    delegate = Done.alloc().init()
    service.setDelegate_(delegate)
    if subject:
        service.setSubject_(subject)
    app.activateIgnoringOtherApps_(True)
    service.performWithItems_(items)
    Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(TIMEOUT_S, app, "terminate:", None, False)
    app.run()
    return 0
