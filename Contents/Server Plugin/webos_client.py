#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webos_client.py  - LG WebOS WebSocket client using ONLY Python built-in libraries.
No external packages required.
"""

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading

REGISTRATION_PAYLOAD = {
    "forcePairing": False,
    "pairingType": "PROMPT",
    "manifest": {
        "manifestVersion": 1,
        "appVersion": "1.1",
        "signed": {
            "created": "20140509",
            "appId": "com.indigo.lgwebos",
            "vendorId": "com.indigo",
            "localizedAppNames": {"": "Indigo LG WebOS Plugin"},
            "localizedVendorNames": {"": "Perceptive Automation"},
            "permissions": [
                "CONTROL_POWER", "READ_CURRENT_CHANNEL", "READ_RUNNING_APPS",
                "READ_UPDATE_INFO", "UPDATE_FROM_REMOTE_APP", "READ_LGE_TV_INPUT_EVENTS"
            ],
            "serial": "2f930e2d2cfe083771f68e4fe7bb07"
        },
        "permissions": [
            "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE",
            "CONTROL_AUDIO", "CONTROL_DISPLAY", "CONTROL_INPUT_TV",
            "CONTROL_POWER", "READ_APP_STATUS", "READ_CURRENT_CHANNEL",
            "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE", "READ_RUNNING_APPS",
            "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST",
            "READ_POWER_STATE", "READ_COUNTRY_INFO"
        ],
        "signatures": [{"signatureVersion": 1, "signature": "eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbmctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9.hrVRgjCW_NntIopovRTl7r3mCINM1ik5Yq5w8w1MUGUnfbHPPiqJVd5PKBNG7GHZjQGaNmYLJhLhDDLzRwLpuBfhNTHxNlRMT_MPAN2TDKlFd-JHG3lMNiyHGiauT9JqUHXdVkP4ANBOO9f7bdcMcyiAFe4QkFy4hZF-nNFNDSgFieTIPQ73UpW2HwYFNgBRqY1V3TRtFE8G8SVzNHpwxiMnFGP49YCXR7mfCzREWPvFfM1qL0K8xEjyqkgCJl1WUv3IHFz-qoV-s7CrEPXN5W2ynIpSwxUyVd7fHfkQXXR3NZXRqzFjKCqcMBmfVyqBWzk6JKcF6jKlUw"}]
    }
}


class _RawWebSocket:
    """Minimal WebSocket client (RFC 6455) using only socket + ssl."""

    WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, host, port=3001):
        self.host = host
        self.port = port
        self._sock = None
        self._send_lock = threading.Lock()

    def connect(self, timeout=10):
        raw = socket.create_connection((self.host, self.port), timeout=timeout)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self._sock = ctx.wrap_socket(raw, server_hostname=self.host)
        self._sock.settimeout(timeout)

        key = base64.b64encode(os.urandom(16)).decode()
        hs = (
            "GET / HTTP/1.1\r\n"
            "Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(host=self.host, port=self.port, key=key)
        self._sock.sendall(hs.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(1024)
            if not chunk:
                raise ConnectionError("Handshake failed - connection closed")
            resp += chunk

        expected = base64.b64encode(hashlib.sha1((key + self.WS_GUID).encode()).digest()).decode()
        if expected not in resp.decode("utf-8", errors="ignore"):
            raise ConnectionError("Handshake failed - bad server accept key")

        self._sock.settimeout(None)

    def send_text(self, text):
        payload = text.encode("utf-8")
        n = len(payload)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

        hdr = bytearray([0x81])
        if n <= 125:
            hdr.append(0x80 | n)
        elif n <= 65535:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        hdr += mask

        with self._send_lock:
            self._sock.sendall(bytes(hdr) + masked)

    def recv_frame(self):
        def exact(n):
            buf = b""
            while len(buf) < n:
                c = self._sock.recv(n - len(buf))
                if not c:
                    return None
                buf += c
            return buf

        h = exact(2)
        if not h:
            return None, None

        opcode = h[0] & 0x0F
        masked = (h[1] & 0x80) != 0
        length = h[1] & 0x7F

        if length == 126:
            e = exact(2)
            if not e: return None, None
            length = struct.unpack(">H", e)[0]
        elif length == 127:
            e = exact(8)
            if not e: return None, None
            length = struct.unpack(">Q", e)[0]

        mk = b""
        if masked:
            mk = exact(4)
            if not mk: return None, None

        data = exact(length) if length else b""
        if data is None:
            return None, None

        if masked and mk:
            data = bytes(b ^ mk[i % 4] for i, b in enumerate(data))

        return opcode, data

    def close(self):
        try:
            if self._sock:
                self._sock.sendall(b"\x88\x00")
                self._sock.close()
        except Exception:
            pass
        self._sock = None


class WebOSClient:

    WS_PORT          = 3001
    CONNECT_TIMEOUT  = 10
    RESPONSE_TIMEOUT = 8

    def __init__(self, host, client_key=None, logger=None):
        self.host       = host
        self.client_key = client_key
        self.logger     = logger
        self._ws        = None
        self._connected = False
        self._cmd_id    = 0
        self._pending   = {}
        self._lock      = threading.Lock()
        self._pair_event = threading.Event()
        self._pair_key   = None
        self._pair_error = None

    def connect(self):
        try:
            ws = _RawWebSocket(self.host, self.WS_PORT)
            ws.connect(timeout=self.CONNECT_TIMEOUT)
            self._ws = ws
            self._connected = True
        except Exception as e:
            return False, None, "Cannot connect to TV at {}: {}".format(self.host, e)

        self._pair_event.clear()
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()
        self._send_register()

        if not self._pair_event.wait(timeout=self.CONNECT_TIMEOUT):
            self.disconnect()
            return False, None, "Timeout waiting for pairing. Make sure the TV is ON and accept the prompt on screen."

        if self._pair_error:
            return False, None, self._pair_error

        return True, self._pair_key, "Connected successfully"

    def disconnect(self):
        self._connected = False
        if self._ws:
            self._ws.close()
            self._ws = None

    @staticmethod
    def is_reachable(host, port=3001, timeout=3):
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except (socket.timeout, OSError):
            return False

    def _send_register(self):
        payload = dict(REGISTRATION_PAYLOAD)
        if self.client_key:
            payload["client-key"] = self.client_key
        self._ws.send_text(json.dumps({"id": "register_0", "type": "register", "payload": payload}))

    def _recv_loop(self):
        while self._connected and self._ws and self._ws._sock:
            try:
                opcode, data = self._ws.recv_frame()
            except Exception as e:
                self._log("Recv error: {}".format(e))
                break
            if opcode is None:
                break
            if opcode == 0x8:
                break
            if opcode == 0x9:
                try: self._ws._sock.sendall(b"\x8a\x00")
                except Exception: pass
                continue
            if opcode not in (0x1, 0x2):
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
                self._dispatch(msg)
            except Exception:
                continue

        self._connected = False
        if not self._pair_event.is_set():
            self._pair_error = "Connection closed before pairing completed"
            self._pair_event.set()

    def _dispatch(self, msg):
        mid  = msg.get("id", "")
        mtype = msg.get("type", "")
        payload = msg.get("payload", {})

        if mid == "register_0":
            if mtype == "registered":
                self._pair_key = payload.get("client-key")
                self._pair_error = None
                self._pair_event.set()
            elif mtype == "response" and payload.get("pairingType") == "PROMPT":
                self._log("Accept the pairing prompt on your TV screen.")
            elif mtype == "error":
                self._pair_error = "Pairing error: {}".format(payload)
                self._pair_event.set()
            return

        if mid in self._pending:
            e = self._pending[mid]
            e["payload"] = payload
            e["type"]    = mtype
            e["event"].set()

    def _next_id(self):
        with self._lock:
            self._cmd_id += 1
            return "cmd_{}".format(self._cmd_id)

    def _send(self, uri, payload=None):
        if not self._connected or not self._ws:
            return None
        cid = self._next_id()
        msg = {"id": cid, "type": "request", "uri": uri}
        if payload:
            msg["payload"] = payload
        entry = {"event": threading.Event(), "payload": None, "type": None}
        self._pending[cid] = entry
        try:
            self._ws.send_text(json.dumps(msg))
        except Exception as e:
            self._log("Send error: {}".format(e))
            self._pending.pop(cid, None)
            return None
        if not entry["event"].wait(timeout=self.RESPONSE_TIMEOUT):
            self._pending.pop(cid, None)
            return None
        self._pending.pop(cid, None)
        return entry.get("payload")

    def _log(self, msg):
        if self.logger:
            self.logger(msg)

    # ── TV Commands ───────────────────────────────────────────────────────────
    def power_off(self):
        return self._send("ssap://system/turnOff")

    def get_volume(self):
        return self._send("ssap://audio/getVolume")

    def set_volume(self, level):
        return self._send("ssap://audio/setVolume", {"volume": max(0, min(100, int(level)))})

    def volume_up(self):
        return self._send("ssap://audio/volumeUp")

    def volume_down(self):
        return self._send("ssap://audio/volumeDown")

    def get_mute(self):
        return self._send("ssap://audio/getMute")

    def set_mute(self, muted):
        return self._send("ssap://audio/setMute", {"mute": bool(muted)})

    def get_current_channel(self):
        return self._send("ssap://tv/getCurrentChannel")

    def channel_up(self):
        return self._send("ssap://tv/channelUp")

    def channel_down(self):
        return self._send("ssap://tv/channelDown")

    def get_channel_list(self):
        return self._send("ssap://tv/getChannelList")

    def open_channel(self, channel_number):
        result = self.get_channel_list()
        if result and "channelList" in result:
            for ch in result["channelList"]:
                if str(ch.get("channelNumber", "")) == str(channel_number):
                    return self._send("ssap://tv/openChannel", {"channelId": ch["channelId"]})
        return None

    def get_inputs(self):
        return self._send("ssap://tv/getExternalInputList")

    def set_input(self, input_id):
        return self._send("ssap://tv/switchInput", {"inputId": input_id})

    def get_current_app(self):
        return self._send("ssap://com.webos.applicationManager/getForegroundAppInfo")

    def launch_app(self, app_id, params=None):
        p = {"id": app_id}
        if params:
            p["params"] = params
        return self._send("ssap://system.launcher/launch", p)

    def send_key(self, key_name):
        return self._send("ssap://com.webos.service.ime/sendKeycode", {"keyCode": key_name})

    def show_toast(self, message):
        return self._send("ssap://system.notifications/createToast", {"message": str(message)})

    def set_picture_mode(self, mode):
        return self._send("ssap://settings/setSystemSettings",
                          {"category": "picture", "settings": {"pictureMode": mode}})

    def get_system_info(self):
        return self._send("ssap://system/getSystemInfo")
