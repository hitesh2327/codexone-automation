"""Launch Playwright's Chromium; fall back to the system Microsoft Edge if its browsers are missing."""


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(channel="msedge")
