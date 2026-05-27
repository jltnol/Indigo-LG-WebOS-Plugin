#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
plugin.py  –  Indigo plugin for LG WebOS TVs.

Features:
  • Power On (Wake-on-LAN) / Power Off / Toggle
  • Volume Up/Down/Set/Mute
  • Channel Up/Down/Set
  • Input selection
  • Remote key injection
  • App launching
  • Picture mode
  • Toast notifications
  • Periodic status polling (volume, channel, input, power)
"""

import indigo
import threading
import time
import os
import sys

# Add our plugin directory to the path so we can import helpers
# Indigo's plugin host may not define __file__, so we fall back to sys.argv
try:
    _plugin_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _plugin_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.append(_plugin_dir)

from webos_client import WebOSClient
from wol import power_on_tv

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
POLL_INTERVAL   = 30   # seconds between status polls
RECONNECT_DELAY = 15   # seconds before attempting reconnect after lost connection
WOL_RETRY_WAIT  = 8    # seconds after WoL before first connection attempt


# ══════════════════════════════════════════════════════════════════════════════
# Plugin
# ══════════════════════════════════════════════════════════════════════════════
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.debug = pluginPrefs.get("showDebugInfo", False)

        # device_id -> WebOSClient instance
        self._clients   = {}
        # device_id -> threading.Thread (polling)
        self._poll_threads = {}
        # device_id -> bool (stop signal)
        self._stop_poll = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Indigo lifecycle
    # ──────────────────────────────────────────────────────────────────────────
    def startup(self):
        self.debugLog("LG WebOS plugin starting up")

    def shutdown(self):
        self.debugLog("LG WebOS plugin shutting down")
        for dev_id in list(self._stop_poll.keys()):
            self._stop_poll[dev_id] = True
        for client in self._clients.values():
            try:
                client.disconnect()
            except Exception:
                pass

    def deviceStartComm(self, dev):
        self.debugLog("deviceStartComm: {}".format(dev.name))
        dev.updateStateOnServer("connectionStatus", "Disconnected")
        dev.updateStateOnServer("onOffState", False)
        self._connectDevice(dev)

    def deviceStopComm(self, dev):
        self.debugLog("deviceStopComm: {}".format(dev.name))
        self._stop_poll[dev.id] = True
        if dev.id in self._clients:
            self._clients[dev.id].disconnect()
            del self._clients[dev.id]

    def runConcurrentThread(self):
        """Main loop – drives periodic polling."""
        try:
            while True:
                self.sleep(POLL_INTERVAL)
                for dev in indigo.devices.iter("self"):
                    if dev.id in self._clients and self._clients[dev.id]._connected:
                        self._pollDevice(dev)
        except self.StopThread:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Device config UI callbacks
    # ──────────────────────────────────────────────────────────────────────────
    def pairWithTV(self, valuesDict, typeId, devId):
        """Called when the user clicks 'Pair with TV' in the device config dialog."""
        host = valuesDict.get("address", "").strip()
        if not host:
            errorsDict = indigo.Dict()
            errorsDict["address"] = "Please enter the TV's IP address first."
            return valuesDict, errorsDict

        existing_key = valuesDict.get("clientKey", "").strip() or None
        client = WebOSClient(host, client_key=existing_key, logger=self._log)

        valuesDict["statusMsg"] = "Connecting … accept the prompt on your TV."
        success, key, msg = client.connect()

        if success:
            valuesDict["clientKey"] = key or ""
            valuesDict["statusMsg"] = "✅  Paired successfully! Client key saved."
            client.disconnect()
        else:
            errorsDict = indigo.Dict()
            errorsDict["statusMsg"] = "❌  {}".format(msg)
            valuesDict["statusMsg"] = "❌  {}".format(msg)
            return valuesDict, errorsDict

        return valuesDict

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        valuesDict = indigo.Dict(pluginProps)
        errorsDict = indigo.Dict()
        if "address"    not in valuesDict: valuesDict["address"]    = ""
        if "clientKey"  not in valuesDict: valuesDict["clientKey"]  = ""
        if "macAddress" not in valuesDict: valuesDict["macAddress"] = ""
        if "statusMsg"  not in valuesDict: valuesDict["statusMsg"]  = ""
        return valuesDict, errorsDict

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errorsDict = indigo.Dict()
        host = valuesDict.get("address", "").strip()
        if not host:
            errorsDict["address"] = "IP address is required."
        return (len(errorsDict) == 0), valuesDict, errorsDict

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────
    def _log(self, msg):
        indigo.server.log(msg)

    def _connectDevice(self, dev):
        """Establish (or re-establish) a WebSocket connection for a device."""
        host       = dev.pluginProps.get("address", "").strip()
        client_key = dev.pluginProps.get("clientKey", "").strip() or None

        if not host:
            indigo.server.log("LG WebOS: No IP address for device '{}'".format(dev.name), isError=True)
            return

        # Check reachability first to avoid long timeouts when TV is off
        if not WebOSClient.is_reachable(host):
            self.debugLog("TV '{}' not reachable at {}. Will retry later.".format(dev.name, host))
            dev.updateStateOnServer("connectionStatus", "Unreachable")
            dev.updateStateOnServer("onOffState", False)
            return

        client = WebOSClient(host, client_key=client_key, logger=self.debugLog)
        success, key, msg = client.connect()

        if success:
            # Persist updated key if it changed
            if key and key != client_key:
                props = dev.pluginProps
                props["clientKey"] = key
                dev.replacePluginPropsOnServer(props)

            self._clients[dev.id] = client
            dev.updateStateOnServer("connectionStatus", "Connected")
            dev.updateStateOnServer("onOffState", True)
            indigo.server.log("LG WebOS: Connected to '{}' ({})".format(dev.name, host))
            self._pollDevice(dev)
        else:
            dev.updateStateOnServer("connectionStatus", "Error")
            self.debugLog("LG WebOS: Could not connect to '{}': {}".format(dev.name, msg))

    def _getClient(self, dev):
        """Return the connected client for a device, reconnecting if needed."""
        client = self._clients.get(dev.id)
        if client and client._connected:
            return client
        # Try to reconnect
        self._connectDevice(dev)
        return self._clients.get(dev.id)

    def _pollDevice(self, dev):
        """Fetch current volume, mute, and channel from the TV and update states."""
        client = self._clients.get(dev.id)
        if not client or not client._connected:
            dev.updateStateOnServer("connectionStatus", "Disconnected")
            dev.updateStateOnServer("onOffState", False)
            return

        # Volume
        try:
            vol_result = client.get_volume()
            if vol_result:
                volume = vol_result.get("volume", dev.states.get("currentVolume", 0))
                muted  = vol_result.get("muted", False)
                dev.updateStateOnServer("currentVolume", int(volume))
                dev.updateStateOnServer("isMuted", bool(muted))
        except Exception as e:
            self.debugLog("Poll volume error: {}".format(e))

        # Channel
        try:
            ch_result = client.get_current_channel()
            if ch_result:
                ch_name = ch_result.get("channelName", "")
                ch_num  = ch_result.get("channelNumber", "")
                ch_str  = "{} ({})".format(ch_num, ch_name) if ch_name else str(ch_num)
                dev.updateStateOnServer("currentChannel", ch_str)
        except Exception as e:
            self.debugLog("Poll channel error: {}".format(e))

        # Foreground app / input
        try:
            app_result = client.get_current_app()
            if app_result:
                app_id = app_result.get("appId", "")
                dev.updateStateOnServer("currentInput", app_id)
        except Exception as e:
            self.debugLog("Poll input error: {}".format(e))

    # ──────────────────────────────────────────────────────────────────────────
    # Action handlers
    # ──────────────────────────────────────────────────────────────────────────

    # ── Power ──────────────────────────────────────────────────────────────
    def powerOn(self, pluginAction, dev):
        mac = dev.pluginProps.get("macAddress", "").strip()
        ok, msg = power_on_tv(mac, logger=self._log)
        indigo.server.log("LG WebOS: Power On – {}".format(msg))
        if ok:
            # Allow TV time to boot, then attempt connection
            def _delayed_connect():
                time.sleep(WOL_RETRY_WAIT)
                self._connectDevice(dev)
            t = threading.Thread(target=_delayed_connect)
            t.daemon = True
            t.start()

    def powerOff(self, pluginAction, dev):
        client = self._getClient(dev)
        if client:
            client.power_off()
            dev.updateStateOnServer("onOffState", False)
            dev.updateStateOnServer("connectionStatus", "Off")
            indigo.server.log("LG WebOS: Powered off '{}'".format(dev.name))
        else:
            indigo.server.log("LG WebOS: Cannot power off '{}' – not connected".format(dev.name), isError=True)

    def powerToggle(self, pluginAction, dev):
        if dev.states.get("onOffState", False):
            self.powerOff(pluginAction, dev)
        else:
            self.powerOn(pluginAction, dev)

    # ── Volume ─────────────────────────────────────────────────────────────
    def setVolume(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        try:
            level = int(pluginAction.props.get("volume", 20))
        except ValueError:
            indigo.server.log("LG WebOS: Invalid volume value", isError=True)
            return
        client.set_volume(level)
        dev.updateStateOnServer("currentVolume", level)
        self.debugLog("Set volume to {}".format(level))

    def volumeUp(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        try:
            steps = int(pluginAction.props.get("steps", 1))
        except ValueError:
            steps = 1
        for _ in range(steps):
            client.volume_up()
            time.sleep(0.15)
        # Re-poll to get actual value
        self._pollDevice(dev)

    def volumeDown(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        try:
            steps = int(pluginAction.props.get("steps", 1))
        except ValueError:
            steps = 1
        for _ in range(steps):
            client.volume_down()
            time.sleep(0.15)
        self._pollDevice(dev)

    def muteToggle(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        current = dev.states.get("isMuted", False)
        client.set_mute(not current)
        dev.updateStateOnServer("isMuted", not current)

    def setMute(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        mute_state = pluginAction.props.get("muteState", "true") == "true"
        client.set_mute(mute_state)
        dev.updateStateOnServer("isMuted", mute_state)

    # ── Channel ────────────────────────────────────────────────────────────
    def channelUp(self, pluginAction, dev):
        client = self._getClient(dev)
        if client:
            client.channel_up()
            time.sleep(0.5)
            self._pollDevice(dev)

    def channelDown(self, pluginAction, dev):
        client = self._getClient(dev)
        if client:
            client.channel_down()
            time.sleep(0.5)
            self._pollDevice(dev)

    def setChannel(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        ch_num = pluginAction.props.get("channelNumber", "").strip()
        if not ch_num:
            indigo.server.log("LG WebOS: No channel number provided", isError=True)
            return
        result = client.open_channel(ch_num)
        if result is not None:
            self.debugLog("Tuned to channel {}".format(ch_num))
            time.sleep(0.5)
            self._pollDevice(dev)
        else:
            indigo.server.log("LG WebOS: Channel {} not found in channel list".format(ch_num), isError=True)

    # ── Input ──────────────────────────────────────────────────────────────
    def setInput(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        input_id = pluginAction.props.get("inputId", "HDMI_1")
        client.set_input(input_id)
        dev.updateStateOnServer("currentInput", input_id)
        self.debugLog("Input set to {}".format(input_id))

    # ── Remote keys ────────────────────────────────────────────────────────
    def sendKey(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        key = pluginAction.props.get("keyName", "ENTER")
        client.send_key(key)
        self.debugLog("Sent key: {}".format(key))

    # ── Apps ───────────────────────────────────────────────────────────────
    def launchApp(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        app_id = pluginAction.props.get("appId", "")
        if not app_id:
            return
        result = client.launch_app(app_id)
        if result is not None:
            dev.updateStateOnServer("currentInput", app_id)
            self.debugLog("Launched app: {}".format(app_id))
        else:
            indigo.server.log("LG WebOS: Failed to launch app '{}'".format(app_id), isError=True)

    # ── Picture mode ────────────────────────────────────────────────────────
    def setPictureMode(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        mode = pluginAction.props.get("pictureMode", "cinema")
        client.set_picture_mode(mode)
        self.debugLog("Picture mode set to {}".format(mode))

    # ── Toast / Notification ───────────────────────────────────────────────
    def showToast(self, pluginAction, dev):
        client = self._getClient(dev)
        if not client:
            return
        message = pluginAction.props.get("message", "Hello from Indigo!")
        client.show_toast(message)
        self.debugLog("Toast: {}".format(message))

    # ── Status refresh ────────────────────────────────────────────────────
    def updateStatus(self, pluginAction, dev):
        client = self._getClient(dev)
        if client:
            self._pollDevice(dev)
        else:
            indigo.server.log("LG WebOS: '{}' not connected – attempting reconnect".format(dev.name))
            self._connectDevice(dev)

    # ──────────────────────────────────────────────────────────────────────────
    # Plugin Preferences UI
    # ──────────────────────────────────────────────────────────────────────────
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo", False)
