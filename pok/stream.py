import json
import time
from urllib.parse import unquote, urlsplit

import websocket

from constants.contracts import ORIGIN
from constants.stream import (
    ACK_TIMEOUT,
    FRAME_SIZE_LIMIT,
    HEARTBEAT_TIMEOUT,
    STREAM_INIT_PAYLOAD,
    WEBSOCKET_PROTOCOL,
    WEBSOCKET_URL,
)


class StreamProtocolError(ConnectionError):
    pass


def parse_frame(raw):
    if not raw or len(raw) > FRAME_SIZE_LIMIT:
        raise StreamProtocolError("Invalid WebSocket frame size")
    try:
        frame = json.loads(raw)
    except (ValueError, TypeError):
        raise StreamProtocolError("Invalid WebSocket JSON") from None
    if not isinstance(frame, dict) or not isinstance(frame.get("type"), str):
        raise StreamProtocolError("Invalid WebSocket envelope")
    return frame


def proxy_options(proxy):
    if not proxy:
        return {}
    parsed = urlsplit(proxy)
    if parsed.scheme not in ("http", "socks5", "socks5h", "socks4"):
        raise ValueError("Unsupported WebSocket proxy scheme")
    if not parsed.hostname or not parsed.port:
        raise ValueError("Proxy host and port are required")
    options = {"http_proxy_host": parsed.hostname, "http_proxy_port": parsed.port,
               "proxy_type": parsed.scheme}
    if parsed.username:
        options["http_proxy_auth"] = (unquote(parsed.username), unquote(parsed.password or ""))
    return options


class StreamConnection:
    def __init__(self, owner, socket=None, clock=time.monotonic):
        self.owner = owner
        self.socket = socket or websocket.WebSocket(sslopt={"ca_certs": owner._ca_bundle})
        self.clock = clock
        self.last_received = clock()

    def connect(self):
        self.socket.connect(WEBSOCKET_URL, origin=ORIGIN,
                            cookie=self.owner._cookie_header(),
                            header=[f"User-Agent: {self.owner.user_agent}"],
                            subprotocols=[WEBSOCKET_PROTOCOL], timeout=ACK_TIMEOUT,
                            **proxy_options(getattr(self.owner, "proxy_url", None) or self.owner.proxy))
        self.send({"type": "connection_init", "payload": STREAM_INIT_PAYLOAD})
        deadline = self.clock() + ACK_TIMEOUT
        while self.clock() < deadline:
            self.socket.settimeout(max(0.1, deadline - self.clock()))
            frame = parse_frame(self.socket.recv())
            if self.handle_control(frame):
                continue
            if frame["type"] != "connection_ack":
                raise StreamProtocolError("Expected connection_ack")
            self.last_received = self.clock()
            self.socket.settimeout(HEARTBEAT_TIMEOUT)
            return frame
        raise StreamProtocolError("WebSocket acknowledgement timed out")

    def send(self, frame):
        self.socket.send(json.dumps(frame))

    def handle_control(self, frame):
        if frame["type"] == "ping":
            self.send({"type": "pong", "payload": frame.get("payload", {})})
            return True
        return frame["type"] == "pong"

    def receive(self):
        while True:
            try:
                frame = parse_frame(self.socket.recv())
            except websocket.WebSocketTimeoutException:
                if self.clock() - self.last_received >= HEARTBEAT_TIMEOUT * 2:
                    raise StreamProtocolError("WebSocket heartbeat timed out") from None
                self.send({"type": "ping"})
                continue
            self.last_received = self.clock()
            if self.handle_control(frame):
                continue
            if frame["type"] == "error" or (frame.get("payload") or {}).get("errors"):
                raise StreamProtocolError("WebSocket subscription rejected")
            return frame

    def close(self):
        self.socket.close()
