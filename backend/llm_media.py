"""Shared helpers for sending question media through the LLM gateway."""

from __future__ import annotations

from typing import Any


def guess_mime_type(base64_data: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    prefix = (base64_data or "")[:16]
    if prefix.startswith("/9j/"):
        return "image/jpeg"
    if prefix.startswith("iVBOR"):
        return "image/png"
    if prefix.startswith("R0lGOD"):
        return "image/gif"
    if prefix.startswith("UklGR"):
        return "image/webp"
    return "image/png"


def normalize_media_items(media_items: Any) -> list[dict[str, str]]:
    if not isinstance(media_items, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in media_items:
        if not isinstance(item, dict):
            continue
        base64_data = str(item.get("base64") or "").strip()
        if not base64_data:
            continue
        media_type = str(item.get("type") or "image").strip() or "image"
        mime_type = guess_mime_type(base64_data, str(item.get("mime_type") or "").strip() or None)
        normalized.append({
            "type": media_type,
            "mime_type": mime_type,
            "base64": base64_data,
        })
    return normalized


def media_input_refs(media_items: Any) -> dict[str, Any]:
    normalized = normalize_media_items(media_items)
    if not normalized:
        return {}
    return {
        "media_count": len(normalized),
        "media_types": sorted({item["type"] for item in normalized}),
    }


def messages_with_media(prompt: str, media_items: Any) -> list[dict[str, Any]]:
    normalized = normalize_media_items(media_items)
    if not normalized:
        return [{"role": "user", "content": prompt}]

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for item in normalized:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{item['mime_type']};base64,{item['base64']}",
            },
        })
    return [{"role": "user", "content": content}]
