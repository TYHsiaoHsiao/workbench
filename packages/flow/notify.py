"""失败通知外送：把 JSON 通知 POST 到 webhook（零依赖，失败不影响主流程）。

M28 起由批次运行（``flow.batch``）与队列运行（``flow.queue``）共用；
M33 增加重试/退避与飞书文本消息格式（``format="feishu"``）。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "workbench-flow/2.33"
WEBHOOK_FORMATS = ("generic", "feishu")


def build_webhook_body(payload: dict[str, Any], fmt: str = "generic") -> dict[str, Any]:
    """把内部通知负载转换成目标平台的消息体。"""
    if fmt == "generic":
        return payload
    if fmt == "feishu":
        message = str(payload.get("message") or "").strip()
        if not message:
            message = json.dumps(payload, ensure_ascii=False)
        failed = payload.get("failed_graphs") or []
        text = f"【AI 影视工作台】{message}"
        if failed:
            text += "\n失败图：" + "、".join(str(item) for item in failed[:10])
        return {"msg_type": "text", "content": {"text": text}}
    raise ValueError(f"未知 webhook 格式: {fmt}（可选 {'/'.join(WEBHOOK_FORMATS)}）")


def notify_webhook(
    webhook_url: str | None,
    payload: dict[str, Any],
    *,
    format: str = "generic",
    retries: int = 0,
    backoff: float = 1.0,
) -> dict[str, Any]:
    """把 ``payload`` 以 JSON POST 外送到 ``webhook_url``。

    - ``format``：``generic``（内部完整 JSON）或 ``feishu``（飞书群机器人文本消息）。
    - ``retries``：失败后额外的重试次数（0–3），重试间隔 ``backoff * 第几次`` 秒。
    返回 ``{"configured","ok","status_code","error","attempts","format"}``；
    未配置时 ``configured`` 为 False，网络/HTTP 失败只记录 error，不抛出。
    """
    result: dict[str, Any] = {
        "configured": bool(webhook_url),
        "ok": False,
        "format": format,
        "attempts": 0,
    }
    if not webhook_url:
        return result
    retries = max(0, min(3, int(retries)))
    try:
        body = json.dumps(build_webhook_body(payload, format), ensure_ascii=False).encode("utf-8")
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": USER_AGENT,
    }
    for attempt in range(retries + 1):
        result["attempts"] = attempt + 1
        request = urllib.request.Request(webhook_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result["status_code"] = getattr(response, "status", None)
                result["ok"] = True
                result.pop("error", None)
                return result
        except (OSError, urllib.error.URLError, ValueError) as exc:
            result["error"] = str(exc)
            if attempt < retries:
                time.sleep(max(0.0, backoff * (attempt + 1)))
    return result


__all__ = ["USER_AGENT", "WEBHOOK_FORMATS", "build_webhook_body", "notify_webhook"]
