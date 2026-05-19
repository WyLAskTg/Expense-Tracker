import json
import re
import urllib.error
import urllib.request


def version_tuple(version):
    parts = re.findall(r"\d+", version or "")
    return tuple(int(part) for part in parts[:4])


def is_newer_version(latest, current):
    return version_tuple(latest) > version_tuple(current)


def latest_release(repo, timeout=8):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"User-Agent": "ExpenseTracker"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not check for updates.") from exc

    return {
        "tag": payload.get("tag_name") or "",
        "name": payload.get("name") or "",
        "url": payload.get("html_url") or "",
        "published_at": payload.get("published_at") or "",
    }
