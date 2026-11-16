"""失败通知外送：把 JSON 通知 POST 到 webhook（零依赖，失败不影响主流程）。

M28 起由批次运行（``flow.batch``）与队列运行（``flow.queue``）共用。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "workbench-flow/2.15"


def notify_webhook(webhook_url: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    """把 ``payload`` 以 JSON POST 外送到 ``webhook_url``。

    返回 ``{"configured": bool, "ok": bool, "status_code": int | None, "error": str}``；
    未配置时 ``configured`` 为 False，网络/HTTP 失败只记录 error，不抛出。
    """
    result: dict[str, Any] = {"configured": bool(webhook_url), "ok": False}
    if not webhook_url:
        return result
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result["status_code"] = getattr(response, "status", None)
            result["ok"] = True
    except (OSError, urllib.error.URLError, ValueError) as exc:
        result["error"] = str(exc)
    return result


__all__ = ["USER_AGENT", "notify_webhook"]
