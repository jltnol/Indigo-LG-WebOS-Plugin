# LG WebOS TV – Indigo Plugin

Control your LG WebOS TV directly from Indigo home automation software.

---

## Requirements

| Requirement | Details |
|---|---|
| Indigo | Version 7.x or later (Python 2.7 / 3.x compatible) |
| Python library | `websocket-client` (see Installation) |
| LG TV | WebOS 3.x or later (most LG smart TVs from 2016+) |
| Network | TV and Indigo Mac must be on the same LAN |

---

## Installation

### 1 – Install the `websocket-client` Python library

Open Terminal on the Indigo Mac and run:

```bash
# For Indigo 7 (Python 2.7 embedded)
/Library/Application\ Support/Perceptive\ Automation/Indigo\ 7/IndigoPluginHost.app/Contents/MacOS/IndigoPluginHost -install websocket-client

# OR using the system pip that matches Indigo's Python:
pip install websocket-client
# or
pip3 install websocket-client
```

### 2 – Install the plugin

Double-click `LGWebOS.indigoPlugin` to install it into Indigo.

### 3 – Add a device

1. In Indigo, go to **Devices → New Device**.
2. Choose **Type: LG WebOS TV**.
3. Enter the **IP address** of your TV (assign a static IP in your router!).
4. Leave **Client Key** blank on the first pairing.
5. Click **Pair with TV** – a prompt appears on the TV screen.
6. Accept the prompt on the TV. The client key is saved automatically.
7. Optionally enter the **MAC Address** for Wake-on-LAN power-on support.

---

## TV Network Setup

### Static / Reserved IP

Assign a static or DHCP-reserved IP to the TV so its address never changes.

### Wake-on-LAN (Power On)

To power on the TV from Indigo:

1. On the TV: **Settings → General → Mobile TV On** (or "LG Connect Apps") → **Turn On via Wi-Fi**.
2. The TV must remain in standby (not fully unplugged).
3. Enter the MAC address in the device config. Find it at:
   `TV Settings → General → About This TV → Network Info`.

---

## Available Actions

### Power
| Action | Description |
|---|---|
| **Power On** | Sends a Wake-on-LAN magic packet |
| **Power Off** | Sends power-off command via WebSocket |
| **Toggle Power** | On → Off or Off → On |

### Volume
| Action | Description |
|---|---|
| **Set Volume** | Set absolute volume level (0–100) |
| **Volume Up** | Increment volume (configurable steps) |
| **Volume Down** | Decrement volume (configurable steps) |
| **Mute / Unmute** | Toggle mute state |
| **Set Mute State** | Explicitly mute or unmute |

### Channel
| Action | Description |
|---|---|
| **Channel Up** | Tune to next channel |
| **Channel Down** | Tune to previous channel |
| **Set Channel Number** | Tune to a specific channel number (e.g. `5` or `5-1`) |

### Input
| Action | Description |
|---|---|
| **Set Input Source** | Switch to HDMI 1/2/3/4, AV, Component, PC, or Live TV |

### Apps
| Action | Description |
|---|---|
| **Launch App** | Open Netflix, Prime Video, Hulu, Disney+, YouTube, Browser, Live TV, or HDMI inputs |

### Remote Keys
| Action | Description |
|---|---|
| **Send Remote Key** | Inject any key: arrows, OK, Back, Home, Menu, Play/Pause, colour buttons, digits 0–9 |

### Display
| Action | Description |
|---|---|
| **Set Picture Mode** | Vivid, Standard, Cinema, Sport, Game, Filmmaker, Expert |

### Notifications
| Action | Description |
|---|---|
| **Show Toast Notification** | Display a text message on the TV screen |

### Utility
| Action | Description |
|---|---|
| **Refresh TV Status** | Poll the TV for current volume, channel, input, and connection state |

---

## Device States

| State | Type | Description |
|---|---|---|
| `onOffState` | Boolean | TV on/off |
| `connectionStatus` | String | Connected / Disconnected / Unreachable / Off / Error |
| `currentVolume` | Integer | Current volume level (0–100) |
| `isMuted` | Boolean | Mute state |
| `currentChannel` | String | Channel number and name |
| `currentInput` | String | Active input / foreground app ID |

Use these states in Indigo Triggers and Control Pages.

---

## Triggers & Control Pages

### Example Trigger
> *"When volume changes above 50, send a notification"*

1. New Trigger → Type: **Device State Change**
2. Device: your LG TV device
3. State: **Volume changed**
4. Condition: **Greater than 50**

### Example Control Page

Add device state labels to a Control Page:
- **On/Off button** bound to `onOffState`
- **Volume slider** bound to `currentVolume`
- **Text label** showing `currentChannel`

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "websocket-client not installed" | Run `pip install websocket-client` and restart Indigo |
| Pairing prompt never appears on TV | Confirm the IP address is correct and the TV is on. Disable any network firewall between them. |
| TV turns off but won't turn on | Check MAC address format (`AA:BB:CC:DD:EE:FF`). Confirm "Mobile TV On" is enabled in TV settings. |
| Channel tuning fails | Some channels may not appear in the channel list if a cable box is the source. Use HDMI input + Set Channel on the cable box instead. |
| Plugin loses connection | The plugin reconnects automatically on the next poll (every 30 s). Manually trigger **Refresh TV Status** if you need immediate reconnect. |
| Input IDs don't match | Use **Refresh TV Status** and check Indigo logs for the actual input/app IDs reported by your TV model. |

---

## Advanced: Custom App IDs

If your TV has apps not in the preset list, you can find app IDs by:

1. Enabling **Debug Logging** in Plugin Preferences.
2. Opening the app on the TV.
3. Running **Refresh TV Status** – the `currentInput` state shows the app ID.
4. Use that ID with the **Launch App** action (type it directly in the action config).

---

## License

MIT License – free to use and modify.

Plugin developed for Perceptive Automation Indigo.
LG, WebOS are trademarks of LG Electronics.
