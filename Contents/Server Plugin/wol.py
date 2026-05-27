#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
wol.py – Wake-on-LAN helper for powering on the LG TV.

LG WebOS TVs support Wake-on-LAN when the "TV On with Mobile" (or similar)
feature is enabled in Settings > General > Mobile TV On.
"""

import socket
import struct


def send_magic_packet(mac_address, broadcast="255.255.255.255", port=9):
    """
    Build and broadcast a Wake-on-LAN magic packet.

    mac_address: string like "AA:BB:CC:DD:EE:FF" or "AA-BB-CC-DD-EE-FF"
    broadcast:   broadcast IP (default is global broadcast)
    port:        WoL port, typically 7 or 9

    Returns True on success, raises ValueError / socket.error on failure.
    """
    # Normalise MAC – strip separators
    mac_clean = mac_address.upper().replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError("Invalid MAC address: {}".format(mac_address))

    # Pack 6 bytes
    mac_bytes = bytes(bytearray([int(mac_clean[i:i+2], 16) for i in range(0, 12, 2)]))

    # Magic packet = 6x 0xFF + 16x MAC
    magic = b"\xff" * 6 + mac_bytes * 16

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.connect((broadcast, port))
        sock.send(magic)

    return True


def power_on_tv(mac_address, logger=None):
    """
    High-level wrapper used by the plugin.
    Returns (success: bool, message: str).
    """
    if not mac_address or mac_address.strip() == "":
        return False, "No MAC address configured. Please enter the TV's MAC address in the device settings."

    try:
        send_magic_packet(mac_address.strip())
        if logger:
            logger("WoL magic packet sent to {}".format(mac_address))
        return True, "Wake-on-LAN packet sent to {}".format(mac_address)
    except ValueError as e:
        return False, str(e)
    except socket.error as e:
        return False, "Network error sending WoL packet: {}".format(e)
    except Exception as e:
        return False, "Unexpected error: {}".format(e)
