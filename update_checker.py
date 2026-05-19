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

    assets = payload.get("assets") or []
    installer = next(
        (
            asset.get("browser_download_url")
            for asset in assets
            if str(asset.get("name") or "").lower().endswith(".exe")
            and "setup" in str(asset.get("name") or "").lower()
        ),
        "",
    )
    download_url = installer or (assets[0].get("browser_download_url") if assets else "")

    return {
        "tag": payload.get("tag_name") or "",
        "name": payload.get("name") or "",
        "url": payload.get("html_url") or "",
        "download_url": download_url,
        "published_at": payload.get("published_at") or "",
    }
