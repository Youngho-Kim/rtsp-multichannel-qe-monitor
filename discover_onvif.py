"""WS-Discovery based local ONVIF camera discovery module."""

from __future__ import annotations

import socket
import uuid
import xml.etree.ElementTree as ET
from typing import Dict, List


WS_DISCOVERY_PROBE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:{msg_id}</w:MessageID>
    <w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action a:mustUnderstand="true" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe
    </w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""


def discover_onvif_devices(timeout: float = 2.5, demo: bool = False) -> List[Dict[str, str]]:
    """Discover ONVIF cameras on the local subnet via UDP multicast 3702."""
    if demo:
        return [
            {"ip": "192.168.10.101", "xaddr": "http://192.168.10.101/onvif/device_service", "name": "Demo-Cam-CH01-Lobby"},
            {"ip": "192.168.10.102", "xaddr": "http://192.168.10.102/onvif/device_service", "name": "Demo-Cam-CH02-Gate"},
            {"ip": "192.168.10.103", "xaddr": "http://192.168.10.103/onvif/device_service", "name": "Demo-Cam-CH03-Parking"},
            {"ip": "192.168.10.104", "xaddr": "http://192.168.10.104/onvif/device_service", "name": "Demo-Cam-CH04-Warehouse"},
        ]

    devices: List[Dict[str, str]] = []
    seen_ips = set()
    probe = WS_DISCOVERY_PROBE.format(msg_id=uuid.uuid4()).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    try:
        sock.sendto(probe, ("239.255.255.250", 3702))
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)
                xaddr = f"http://{ip}/onvif/device_service"
                try:
                    root = ET.fromstring(data.decode("utf-8", errors="ignore"))
                    for elem in root.iter():
                        if elem.tag.endswith("XAddrs") and elem.text:
                            xaddr = elem.text.strip().split()[0]
                            break
                except ET.ParseError:
                    pass
                devices.append({"ip": ip, "xaddr": xaddr, "name": f"ONVIF-{ip}"})
            except socket.timeout:
                break
    finally:
        sock.close()

    return devices
