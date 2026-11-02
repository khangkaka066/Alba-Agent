"""Scoped image, speech, and gateway video delivery into run artifacts."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import re
import socket
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class MediaCredential:
    preset_id: str
    api_key: str
    base_url: str
    default_models: dict[str, str] = field(default_factory=dict)
    settings: dict[str, object] = field(default_factory=dict)


def _safe_name(value: object, extension: str) -> str:
    stem = str(value or "generated_media").rsplit(".", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", stem):
        raise ValueError("Media filename must contain only letters, digits, underscore or hyphen")
    return f"{stem}.{extension}"


def _png_card(path: Path, prompt: str) -> None:
    """Create a visibly synthetic storyboard placeholder when image quota fails."""
    width, height = 1280, 720
    seed = hashlib.sha256(prompt.encode()).digest()
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            stripe = (x // 160 + y // 120) % 2
            rows.extend((36 + seed[0] // 6 + stripe * 14, 45 + seed[1] // 7, 67 + seed[2] // 8))
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"Description\x00Storyboarding placeholder; remote image generation unavailable") + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")
    path.write_bytes(png)
    path.with_suffix(".md").write_text("# Storyboard placeholder\n\nRemote image generation was unavailable. This card is not an AI rendering.\n\nPrompt: " + prompt[:4000] + "\n", encoding="utf-8")


async def _public_download(client: httpx.AsyncClient, url: str, limit: int = 120_000_000) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Media result URL must be public HTTPS")
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Media result URL is not public")
    async with client.stream("GET", url, follow_redirects=False) as response:
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > limit:
                raise ValueError("Media output exceeds the download limit")
        return bytes(content)


class MediaGatewayService:
    def __init__(self, credential: MediaCredential, artifact_root: Path) -> None:
        self.credential = credential
        self.artifact_root = artifact_root

    def _model(self, kind: str, payload: dict[str, Any]) -> str:
        defaults = {"image": "gpt-image-2-all" if self.credential.preset_id == "shopaikey" else "dall-e-3",
                    "audio": "tts-1-hd", "video": "veo3.1-fast"}
        model = str(payload.get("model") or self.credential.default_models.get(kind) or defaults[kind])
        if not re.fullmatch(r"[A-Za-z0-9._/-]{2,120}", model):
            raise ValueError("Invalid media model name")
        return model

    async def generate(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = "audio" if kind in {"audio", "tts"} else kind
        if normalized not in {"image", "audio", "video"}:
            raise ValueError("Unsupported media kind")
        prompt = str(payload.get("prompt") or payload.get("text") or "").strip()
        if not 1 <= len(prompt) <= 4000:
            raise ValueError("Media prompt must contain 1 to 4000 characters")
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        model = self._model(normalized, payload)
        headers = {"Authorization": f"Bearer {self.credential.api_key}"}
        base = self.credential.base_url.rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("Media provider must use HTTPS")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=False) as client:
            if normalized == "image":
                path = self.artifact_root / _safe_name(payload.get("filename", "generated_image"), "png")
                try:
                    response = await client.post(f"{base}/images/generations", headers=headers,
                        json={"model": model, "prompt": prompt, "size": str(payload.get("size", "1024x1024")), "n": 1})
                    response.raise_for_status()
                    item = response.json()["data"][0]
                    data = base64.b64decode(item["b64_json"], validate=True) if item.get("b64_json") else await _public_download(client, str(item["url"]), 30_000_000)
                    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Image provider did not return PNG data")
                    path.write_bytes(data)
                    return {"artifact": path.name, "kind": "image", "model": model, "fallback": False}
                except (httpx.HTTPError, KeyError, ValueError, TypeError):
                    _png_card(path, prompt)
                    return {"artifact": path.name, "kind": "image", "model": model, "fallback": True,
                            "note": "Remote generation failed; produced a clearly labeled storyboard placeholder"}
            if normalized == "audio":
                path = self.artifact_root / _safe_name(payload.get("filename", "generated_speech"), "mp3")
                if self.credential.preset_id == "elevenlabs":
                    voice = str(payload.get("voice") or self.credential.settings.get("default_voice_id") or "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", voice):
                        raise ValueError("ElevenLabs voice ID is required")
                    response = await client.post(f"{base}/text-to-speech/{voice}", headers={"xi-api-key": self.credential.api_key},
                        json={"text": prompt, "model_id": model})
                else:
                    response = await client.post(f"{base}/audio/speech", headers=headers,
                        json={"model": model, "input": prompt, "voice": str(payload.get("voice", "alloy")), "response_format": "mp3"})
                response.raise_for_status()
                data = response.content
                if not (data.startswith(b"ID3") or (len(data) > 2 and data[0] == 0xff and data[1] & 0xe0 == 0xe0)):
                    raise ValueError("Speech provider did not return MP3 data")
                path.write_bytes(data)
                return {"artifact": path.name, "kind": "audio", "model": model}
            if self.credential.preset_id != "shopaikey":
                raise ValueError("Video generation requires a connected Nexus Harness workspace credential whose provider offers video generation")
            video_base = base.removesuffix("/v1")
            url = f"{video_base}/v1/video/generations"
            metadata = {"aspect_ratio": str(payload.get("aspect_ratio", "16:9")), "enhance_prompt": bool(payload.get("enhance_prompt", True))}
            response = await client.post(url, headers=headers, json={"model": model, "prompt": prompt, "metadata": metadata})
            response.raise_for_status()
            submitted = response.json()
            submission = submitted.get("data") if isinstance(submitted.get("data"), dict) else submitted
            task_id = str(submission.get("task_id") or submission.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", task_id):
                raise ValueError("Video provider returned an invalid task ID")
            for _attempt in range(120):
                await asyncio.sleep(5)
                status_response = await client.get(f"{url}/{task_id}", headers=headers)
                status_response.raise_for_status()
                body = status_response.json()
                state = body.get("data") if isinstance(body.get("data"), dict) else body
                status = str(state.get("status", "")).upper()
                if status in {"FAILURE", "FAILED", "ERROR"}:
                    raise RuntimeError("Video provider reported generation failure: " + str(state.get("fail_reason") or state.get("message") or "unknown")[:200])
                if status in {"SUCCESS", "COMPLETED"}:
                    result_url = state.get("result_url") or state.get("video_url") or state.get("url")
                    if not isinstance(result_url, str):
                        raise ValueError("Video provider completed without a downloadable result URL")
                    data = await _public_download(client, result_url)
                    if len(data) < 12 or data[4:8] != b"ftyp":
                        raise ValueError("Video provider did not return an MP4 file")
                    path = self.artifact_root / _safe_name(payload.get("filename", "generated_video"), "mp4")
                    path.write_bytes(data)
                    return {"artifact": path.name, "kind": "video", "model": model, "task_id": task_id}
            raise TimeoutError("Video generation exceeded ten minutes")
