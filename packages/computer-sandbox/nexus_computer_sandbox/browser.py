"""One real browser per computer, controlled over a private pipe through the PTY owner."""
from __future__ import annotations

import asyncio
import base64
import json
from time import monotonic
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from .browser_http import public_fetch

LaunchBrowser = Callable[[], Awaitable[asyncio.subprocess.Process]]
LocalFetch = Callable[[int, str, str, dict[str, str], bytes | None], Awaitable[dict[str, Any]]]


class ComputerBrowser:
    def __init__(self, launch: LaunchBrowser, local_fetch: LocalFetch) -> None:
        self.launch = launch
        self.local_fetch = local_fetch
        self.process: asyncio.subprocess.Process | None = None
        self.errors: asyncio.Task[None] | None = None
        self.error_tail = ""
        self.reader: asyncio.Task[None] | None = None
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.sequence = 0
        self.session: str | None = None
        self.takeover_until = 0.0
        self.approved_until = 0.0
        self.last_frame = ""
        self.pointer = (0.0, 0.0)
        self.pressed: set[str] = set()
        self.loaded = asyncio.Event()
        self._starting = asyncio.Lock()
        self.requests: set[asyncio.Task[None]] = set()

    async def _send(self, method: str, params: dict[str, Any] | None = None, page: bool = True) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Browser is not running")
        self.sequence += 1
        number = self.sequence
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[number] = future
        message = {"id": number, "method": method, "params": params or {}, **({"sessionId": self.session} if page and self.session else {})}
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()
        try:
            return await asyncio.wait_for(future, 45 if method == "Page.navigate" else 20)
        finally:
            self.pending.pop(number, None)

    async def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                number = message.get("id")
                if number in self.pending:
                    future = self.pending[number]
                    if not future.done():
                        if "error" in message:
                            future.set_exception(RuntimeError(message["error"].get("message", "Browser protocol failure")))
                        else:
                            future.set_result(message.get("result", {}))
                elif message.get("method") == "Page.loadEventFired":
                    self.loaded.set()
                elif message.get("method") == "Fetch.requestPaused":
                    task = asyncio.create_task(self._fetch(message["params"]))
                    self.requests.add(task)
                    task.add_done_callback(self.requests.discard)
                elif message.get("method") == "Page.screencastFrame":
                    self.last_frame = str(message["params"]["data"])
                    await self._send_no_wait("Page.screencastFrameAck", {"sessionId": message["params"]["sessionId"]})
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("Sandbox browser closed: " + self.error_tail[-1500:]))

    async def _send_no_wait(self, method: str, params: dict[str, Any]) -> None:
        if self.process is not None and self.process.stdin is not None:
            self.sequence += 1
            self.process.stdin.write((json.dumps({"id": self.sequence, "method": method, "params": params, "sessionId": self.session}) + "\n").encode())
            await self.process.stdin.drain()

    async def _fetch(self, event: dict[str, Any]) -> None:
        request = event["request"]
        try:
            url = urlsplit(request["url"])
            if any(domain in (url.hostname or "") for domain in ("google-analytics", "googletagmanager", "mixpanel", "segment.io", "sentry.io")):
                raise PermissionError("Analytics requests are disabled")
            method = str(request["method"])
            if method not in {"GET", "HEAD", "OPTIONS"} and monotonic() > max(self.takeover_until, self.approved_until):
                raise PermissionError("External browser writes require approval or human control")
            body = request.get("postData", "").encode() or None
            if url.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
                response = await self.local_fetch(url.port or 80, url.path + ("?" + url.query if url.query else ""), method, request.get("headers", {}), body)
            else:
                response = await asyncio.to_thread(public_fetch, request["url"], method, request.get("headers", {}), body)
            await self._send("Fetch.fulfillRequest", {"requestId": event["requestId"], "responseCode": response["status"], "responseHeaders": response["headers"], "body": response["body"]})
        except Exception:
            try:
                await self._send("Fetch.failRequest", {"requestId": event["requestId"], "errorReason": "BlockedByClient"})
            except (RuntimeError, ConnectionError, asyncio.TimeoutError):
                return

    async def start(self) -> None:
        async with self._starting:
            if self.process is not None and self.process.returncode is None:
                return
            self.process = await self.launch()
            async def drain_errors() -> None:
                assert self.process is not None and self.process.stderr is not None
                while block := await self.process.stderr.read(4096):
                    self.error_tail = (self.error_tail + block.decode(errors="replace"))[-16000:]
            self.errors = asyncio.create_task(drain_errors())
            self.reader = asyncio.create_task(self._read())
            context = await self._send("Target.createBrowserContext", {"disposeOnDetach": True}, False)
            target = await self._send("Target.createTarget", {"url": "about:blank", "browserContextId": context["browserContextId"], "newWindow": True}, False)
            attached = await self._send("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}, False)
            self.session = attached["sessionId"]
            await self._send("Page.enable")
            await self._send("Page.bringToFront")
            await self._send("Page.setWebLifecycleState", {"state": "active"})
            await self._send("Runtime.enable")
            await self._send("Network.enable")
            await self._send("Network.setCacheDisabled", {"cacheDisabled": True})
            await self._send("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False})
            await self._send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
            await self._send("Page.startScreencast", {"format": "png", "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 12})

    async def action(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action = str(arguments.get("action", "screenshot"))
        if action == "close":
            await self.close()
            return {"closed": True}
        await self.start()
        human = bool(arguments.get("human"))
        if arguments.get("approved"):
            self.approved_until = monotonic() + 10
        if action == "takeover":
            if not arguments.get("enabled"):
                for button in tuple(self.pressed):
                    await self._send("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": button, "x": self.pointer[0], "y": self.pointer[1], "clickCount": 0})
                self.pressed.clear()
            self.takeover_until = monotonic() + 300 if arguments.get("enabled") else 0
        elif human and monotonic() > self.takeover_until:
            raise PermissionError("Take control before sending mouse or keyboard input")
        if action == "frame":
            return {"frame_png_base64": self.last_frame, "width": 1280, "height": 720, "human_control": monotonic() < self.takeover_until}
        if not human and action not in {"screenshot", "status", "takeover"}:
            while monotonic() < self.takeover_until:
                await asyncio.sleep(0.1)
        if action == "navigate":
            parsed = urlsplit(str(arguments.get("url", "")))
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("Browser navigation supports HTTP(S) only")
            self.loaded.clear()
            navigation = await self._send("Page.navigate", {"url": arguments["url"]})
            if navigation.get("errorText"):
                raise RuntimeError("Browser navigation failed: " + str(navigation["errorText"]))
            try:
                await asyncio.wait_for(self.loaded.wait(), 5)
            except asyncio.TimeoutError:
                pass
            await self._send("Page.bringToFront")
        elif action == "mouse":
            kind = str(arguments.get("type", "mousePressed"))
            if kind not in {"mousePressed", "mouseReleased", "mouseMoved", "mouseWheel"}:
                raise ValueError("Unsupported mouse event")
            params: dict[str, Any] = {"type": kind, "x": max(0, min(1280, float(arguments.get("x", 0)))), "y": max(0, min(720, float(arguments.get("y", 0))))}
            if kind == "mouseWheel":
                params.update(deltaX=float(arguments.get("deltaX", 0)), deltaY=float(arguments.get("deltaY", 0)))
            else:
                params.update(button=str(arguments.get("button", "left")), clickCount=1)
            self.pointer = (float(params["x"]), float(params["y"]))
            button = str(arguments.get("button", "left"))
            if kind == "mousePressed":
                self.pressed.add(button)
            elif kind == "mouseReleased":
                self.pressed.discard(button)
            await self._send("Input.dispatchMouseEvent", params)
        elif action == "key":
            if arguments.get("text"):
                await self._send("Input.insertText", {"text": str(arguments["text"])[:4096]})
            else:
                key = str(arguments.get("key", ""))[:80]
                codes = {"Enter": 13, "Tab": 9, "Backspace": 8, "Delete": 46, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40, "Escape": 27}
                await self._send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "windowsVirtualKeyCode": codes.get(key, 0), "modifiers": int(arguments.get("modifiers", 0))})
                await self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
        elif action in {"click", "fill", "extract"}:
            selector = json.dumps(str(arguments.get("selector", "body")))
            if action == "extract":
                result = await self._send("Runtime.evaluate", {"expression": f"document.querySelector({selector})?.innerText", "returnByValue": True})
                return {"text": str(result.get("result", {}).get("value", ""))[:50_000]}
            expression = f"document.querySelector({selector})"
            expression = f"{expression}?.click()" if action == "click" else f"(()=>{{const e={expression};if(e){{e.value={json.dumps(str(arguments.get('value', '')))};e.dispatchEvent(new Event('input',{{bubbles:true}}));}}}})()"
            await self._send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        elif action not in {"takeover", "status", "screenshot"}:
            raise ValueError("Unsupported browser action")
        if human and action in {"mouse", "key"}:
            return {"human_control": monotonic() < self.takeover_until}
        for attempt in range(20):
            try:
                frame = await self._send("Page.captureScreenshot", {"format": "png"})
                break
            except RuntimeError as error:
                if "active page" not in str(error) or attempt == 19:
                    raise
                await asyncio.sleep(.1)
        self.last_frame = frame["data"]
        return {"frame_png_base64": self.last_frame, "width": 1280, "height": 720, "human_control": monotonic() < self.takeover_until}

    async def close(self) -> None:
        if self.process is not None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 4)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader is not None:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        for task in self.requests:
            task.cancel()
        await asyncio.gather(*self.requests, return_exceptions=True)
        if self.errors is not None:
            self.errors.cancel()
            await asyncio.gather(self.errors, return_exceptions=True)
        self.process = None
        self.session = None
        self.last_frame = ""
        self.error_tail = ""
        self.pressed.clear()
        self.takeover_until = 0
