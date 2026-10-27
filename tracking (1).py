"""
Anonymous usage counter for the launch.

Each event (start, upload, download) is sent as one response to a Google Form,
which fills a Google Sheet. Only three things are sent: the event name, whether
the data was the sample or the user's own file, and the number of rows analysed.
No file contents, names, emails or customer data ever leave the app.
"""
import json
import re
import threading

import requests

FORM_ID = "1FAIpQLSfiwLbEf2x8Fvh7MjcCpvLsU9sMJJG5E7xwtlpjUiZWtMpUlw"
FORM_VIEW = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
FORM_POST = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"

_fields = {}          # {"event": "entry.123", "source": "entry.456", "rows": "entry.789"}
_lock = threading.Lock()


def _form_fields():
    """Read the form once and map each question title to its entry ID."""
    with _lock:
        if not _fields:
            html = requests.get(FORM_VIEW, timeout=8).text
            raw = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\]);\s*</script>", html, re.S).group(1)
            for q in json.loads(raw)[1][1]:
                if len(q) > 4 and q[4]:
                    _fields[str(q[1]).strip().lower()] = f"entry.{q[4][0][0]}"
        return dict(_fields)


def _send(event, source, rows):
    try:
        f = _form_fields()
        data = {f["event"]: event, f["source"]: source, f["rows"]: str(rows)}
        requests.post(FORM_POST, data=data, timeout=8)
    except Exception:
        pass  # counting must never break the app


def track(event, source, rows=""):
    """Send one event in the background so the app never waits for it."""
    threading.Thread(target=_send, args=(event, source, rows), daemon=True).start()
