"""Draw.io generation helpers for Connectivity Matrix.

This is based on the logic in the legacy Job implementation:
`nautobot_jobs_repo/jobs/connectivity_matrix_diagram/connectivity_matrix_diagram.py`.
"""

from __future__ import annotations

import datetime
import re
import zlib
from collections import defaultdict
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Tuple

from nautobot.dcim.models import Device, Interface

try:
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None


def _drawio_safe_id(kind: str, raw: str) -> str:
    """Build a draw.io-safe, stable-ish ID from an arbitrary string."""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") or "item"
    checksum = zlib.adler32(raw.encode("utf-8")) & 0xFFFFFFFF
    return f"{kind}_{sanitized}_{checksum}"


def _map_medium_from_matrix(medium: str) -> Dict[str, str]:
    """Map matrix medium string to medium info with label, color, and medium_attr."""
    value = (medium or "").strip().lower()
    if not value:
        return {"label": "copper", "color": "#000000", "medium_attr": "copper"}

    if "dac" in value:
        return {"label": "DAC", "color": "#000000", "medium_attr": "copper"}
    if "aoc" in value:
        return {"label": "AOC", "color": "#33FFFF", "medium_attr": "AOC"}
    if "smf" in value or "single" in value:
        return {"label": "SMF", "color": "#FFFF00", "medium_attr": "fiber"}
    if "mmf" in value or "multi" in value or "fiber" in value:
        return {"label": "MMF", "color": "#33FFFF", "medium_attr": "fiber"}
    if "cat" in value or "copper" in value or "utp" in value:
        return {"label": "copper", "color": "#000000", "medium_attr": "copper"}
    return {"label": (medium or "").strip() or "copper", "color": "#000000", "medium_attr": "copper"}


def _determine_speed_from_matrix(speed: str) -> Tuple[str, int]:
    """Determine speed label and stroke width from matrix speed string."""
    normalized = (speed or "").strip() or "1G"
    upper = normalized.upper()

    if "400G" in upper:
        return "400G", 12
    if "200G" in upper:
        return "200G", 11
    if "100G" in upper:
        return "100G", 10
    if "40G" in upper:
        return "40G", 8
    if "25G" in upper:
        return "25G", 6
    if "10G" in upper:
        return "10G", 4
    if "1G" in upper or "1000" in upper:
        return "1G", 2
    if "100M" in upper:
        return "100M", 1
    return normalized, 1


def _compose_link_style(color: str, stroke_width: int) -> str:
    """Compose draw.io link style."""
    return f"endArrow=none;strokeWidth={stroke_width};strokeColor={color};"


def _short_interface(name: str) -> str:
    """Shorten interface name for display."""
    mapping = {
        "TenGigabitEthernet": "Te",
        "GigabitEthernet": "Gi",
        "FastEthernet": "Fa",
        "Ethernet": "Eth",
        "HundredGigE": "Hu",
        "FortyGigE": "Fo",
        "TwentyFiveGigE": "Twe",
        "TwoHundredGigE": "Two",
        "FourHundredGigE": "Fr",
    }
    for long, short in mapping.items():
        if name.startswith(long):
            return name.replace(long, short, 1)
    return name


def _determine_device_icon_type(device_type_model: str) -> str:
    """Determine device icon type based on device model string."""
    if not device_type_model:
        return "workgroup_switch"

    platform = device_type_model

    if any(
        x in platform
        for x in ["WS-", "C1000-", "C9200", "C9300", "2960", "2950", "3650", "3850", "3560", "3750"]
    ):
        return "workgroup_switch"
    if "AIR-CT35" in platform:
        return "WLC"
    if "VMware" in platform:
        return "vmware"
    if "UCS-FI" in platform:
        return "UCS-FI"
    if "N3K" in platform:
        return "N3K"
    if "N5K" in platform:
        return "N5K"
    if "N7K" in platform:
        return "N7K"
    if "N9K" in platform:
        return "N9K"
    if any(x in platform for x in ["Meraki", "C9115", "AIR-AP", "AIR-LAP", "AIR-CAP", "AP802"]):
        return "AP"
    if any(x in platform for x in ["ISR", "39", "28", "29", "C8200", "C11", "1841", "C89", "C88", "C87", "C927", "C937", "C931"]):
        return "router"
    return "workgroup_switch"


def _hierarchical_layout(G: "nx.Graph", device_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    """Create hierarchical layout based on device roles."""
    role_groups = defaultdict(list)
    for device_name in G.nodes():
        if device_name in device_dict:
            role = device_dict[device_name].get("role", "Unknown")
            role_groups[role].append(device_name)

    role_hierarchy = {
        "Core": 0,
        "Distribution": 1,
        "Access": 2,
        "Edge": 3,
        "Unknown": 4,
        "Missing": 5,
    }

    pos = {}
    y_spacing = 200
    x_spacing = 150

    for role, devices_in_role in role_groups.items():
        y_level = role_hierarchy.get(role, 4)
        y = y_level * y_spacing + 100

        total_width = (len(devices_in_role) - 1) * x_spacing if len(devices_in_role) > 1 else 0
        start_x = 100 + (800 - total_width / 2)

        for i, device in enumerate(devices_in_role):
            x = start_x + (i * x_spacing)
            pos[device] = (x, y)

    return pos


def _build_topology_from_connections(connections: List[Dict[str, Any]], devices_by_name: Dict[str, Device]) -> Dict[str, Any]:
    """Build topology structure from matrix connections, using Nautobot device metadata when available."""
    location_topologies: Dict[str, Any] = defaultdict(lambda: {"devices": {}, "connections": []})

    ap_patterns = ["Meraki", "C9115", "AIR-AP", "AIR-LAP", "AIR-CAP", "AP802"]

    id_to_name = {device.id: name for name, device in devices_by_name.items()}
    existing_interfaces_by_device: Dict[str, set] = defaultdict(set)
    if id_to_name:
        for device_id, iface_name in Interface.objects.filter(device_id__in=id_to_name.keys()).values_list("device_id", "name"):
            device_name = id_to_name.get(device_id)
            if device_name:
                existing_interfaces_by_device[device_name].add(iface_name)

    def _meta_for(name: str, *, fallback_location: Optional[str] = None) -> Dict[str, Any]:
        device = devices_by_name.get(name)
        if device:
            model_str = device.device_type.model if device.device_type else "Unknown"
            is_ap = bool(device.device_type and any(pattern in model_str for pattern in ap_patterns))
            icon_type = _determine_device_icon_type(model_str)
            primary_ip = str(device.primary_ip.address.ip) if device.primary_ip else None
            link = f"ssh://{primary_ip}" if primary_ip else None
            location_name = device.location.name if device.location else (fallback_location or "Unknown")
            return {
                "name": device.name,
                "device_type": model_str,
                "icon_type": icon_type,
                "platform": device.platform.name if device.platform else "Unknown",
                "location": location_name,
                "role": device.role.name if device.role else "Unknown",
                "primary_ip": primary_ip,
                "serial": device.serial or "",
                "is_ap": is_ap,
                "mgmt_link": link,
                "is_placeholder": False,
            }

        return {
            "name": name,
            "device_type": "Not in Nautobot",
            "icon_type": "missing",
            "platform": "Unknown",
            "location": fallback_location or "Missing",
            "role": "Missing",
            "primary_ip": None,
            "serial": "",
            "is_ap": False,
            "mgmt_link": None,
            "is_placeholder": True,
        }

    def _add_to_location(location_name: str, dev_a: str, meta_a: Dict[str, Any], dev_b: str, meta_b: Dict[str, Any], conn: Dict[str, Any]):
        location_topologies[location_name]["devices"][dev_a] = meta_a
        location_topologies[location_name]["devices"][dev_b] = meta_b
        location_topologies[location_name]["connections"].append(conn)

    for idx, row in enumerate(connections, start=1):
        dev_a = row["device_a"]
        dev_b = row["device_b"]
        int_a = row.get("interface_a", "") or ""
        int_b = row.get("interface_b", "") or ""

        loc_a_known = devices_by_name.get(dev_a).location.name if devices_by_name.get(dev_a) and devices_by_name[dev_a].location else None
        loc_b_known = devices_by_name.get(dev_b).location.name if devices_by_name.get(dev_b) and devices_by_name[dev_b].location else None

        meta_a = _meta_for(dev_a, fallback_location=loc_b_known)
        meta_b = _meta_for(dev_b, fallback_location=loc_a_known)

        speed_label, stroke_width = _determine_speed_from_matrix(row.get("speed", ""))
        medium_info = _map_medium_from_matrix(row.get("medium", ""))
        style = _compose_link_style(medium_info["color"], stroke_width)

        src_label = _short_interface(int_a)
        trgt_label = _short_interface(int_b)

        if dev_a in devices_by_name and int_a and int_a not in existing_interfaces_by_device.get(dev_a, set()):
            src_label = f"{src_label} (missing)"
        if dev_b in devices_by_name and int_b and int_b not in existing_interfaces_by_device.get(dev_b, set()):
            trgt_label = f"{trgt_label} (missing)"

        edge_raw = f"row{row.get('row', idx)}:{dev_a}:{int_a}->{dev_b}:{int_b}"
        edge_id = _drawio_safe_id("edge", edge_raw)

        conn = {
            "local_device": dev_a,
            "local_interface": int_a,
            "neighbor": dev_b,
            "neighbor_interface": int_b,
            "cable_id": None,
            "speed_label": speed_label,
            "medium_label": medium_info["label"],
            "detected_type": "Multimode Fiber" if medium_info["medium_attr"] in {"fiber", "AOC"} else "CAT6",
            "medium_type_attr": medium_info["medium_attr"],
            "src_label": src_label,
            "trgt_label": trgt_label,
            "style": style,
            "edge_id": edge_id,
        }

        loc_a = meta_a.get("location") or "Unknown"
        loc_b = meta_b.get("location") or "Unknown"

        if not meta_a.get("is_placeholder") and not meta_b.get("is_placeholder") and loc_a != loc_b:
            _add_to_location(loc_a, dev_a, meta_a, dev_b, meta_b, conn)
            _add_to_location(loc_b, dev_a, meta_a, dev_b, meta_b, conn)
            continue

        preferred_loc = loc_a if loc_a != "Missing" else loc_b
        preferred_loc = preferred_loc or "Unknown"
        _add_to_location(preferred_loc, dev_a, meta_a, dev_b, meta_b, conn)

    return location_topologies


def generate_drawio_xml(connections: Iterable[Dict[str, Any]], *, devices_by_name: Optional[Dict[str, Device]] = None) -> str:
    """Generate draw.io XML from a list of matrix-like connection dicts."""
    if nx is None:
        raise RuntimeError("networkx is not installed; cannot generate draw.io diagram.")

    connections_list = list(connections)
    if devices_by_name is None:
        names = {c["device_a"] for c in connections_list} | {c["device_b"] for c in connections_list}
        devices_by_name = {d.name: d for d in Device.objects.filter(name__in=names)}

    location_topologies = _build_topology_from_connections(connections_list, devices_by_name)

    device_icon_styles = {
        "router": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=router;fillColor=#FAFAFA;strokeColor=#005073;",
        "vmware": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=hypervisor;fillColor=#FAFAFA;strokeColor=#005073;",
        "workgroup_switch": "sketch=0;verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=l2_switch;fillColor=#FAFAFA;strokeColor=#005073;shadow=0;",
        "UCS-FI": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=nexus_3k;fillColor=#FAFAFA;strokeColor=#005073;",
        "N3K": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=nexus_3k;fillColor=#FAFAFA;strokeColor=#005073;",
        "N5K": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=layer3_nexus_5k_switch;fillColor=#FAFAFA;strokeColor=#005073;",
        "N7K": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=nexus_7k;fillColor=#FAFAFA;strokeColor=#005073;",
        "N9K": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=nexus_9300;fillColor=#FAFAFA;strokeColor=#005073;",
        "WLC": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=wireless_lan_controller;fillColor=#FAFAFA;strokeColor=#005073;",
        "AP": "verticalLabelPosition=bottom;sketch=0;html=1;verticalLabelPosition=bottom;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.wireless_access_point;fillColor=#005073;strokeColor=none;",
        "FIREWALL": "verticalLabelPosition=bottom;html=1;verticalAlign=top;aspect=fixed;align=center;pointerEvents=1;shape=mxgraph.cisco19.rect;prIcon=firewall;fillColor=#FAFAFA;strokeColor=#005073;",
        "missing": "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d9534f;fontColor=#333333;",
    }

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<mxfile host="Nautobot" modified="{datetime.datetime.now().isoformat()}">',
    ]

    for location_name, topology in location_topologies.items():
        device_dict = topology["devices"]
        topo_connections = topology["connections"]

        if not device_dict:
            continue

        G = nx.Graph()
        for conn in topo_connections:
            G.add_edge(conn["local_device"], conn["neighbor"])

        pos = _hierarchical_layout(G, device_dict)
        canvas_width = 1600.0
        canvas_height = 1200.0

        diagram_name = escape(location_name.replace('"', "'"), quote=True)
        xml_lines.append(f'  <diagram name="{diagram_name}" id="{diagram_name}">')
        xml_lines.append(
            f'    <mxGraphModel dx="1360" dy="864" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{int(canvas_width + 400)}" pageHeight="{int(canvas_height + 400)}" math="0" shadow="1">'
        )
        xml_lines.append("      <root>")
        xml_lines.append('        <mxCell id="0" />')
        xml_lines.append('        <mxCell id="1" parent="0" />')

        device_to_cell_id: Dict[str, str] = {}

        for device_name, device_info in device_dict.items():
            if device_name not in pos:
                continue

            x, y = pos[device_name]
            icon_type = device_info.get("icon_type", "workgroup_switch")
            style = device_icon_styles.get(icon_type, device_icon_styles["workgroup_switch"])

            object_id = _drawio_safe_id("dev", device_name)
            label = escape(device_name, quote=True)
            xml_lines.append(f'        <object id="{object_id}" label="{label}" name="{label}">')
            xml_lines.append(f'          <mxCell style="{escape(style, quote=True)}" vertex="1" parent="1">')
            xml_lines.append(f'            <mxGeometry x="{x}" y="{y}" width="50" height="50" as="geometry" />')
            xml_lines.append("          </mxCell>")
            xml_lines.append("        </object>")

            device_to_cell_id[device_name] = object_id

        for conn in topo_connections:
            local_dev = conn["local_device"]
            neighbor = conn["neighbor"]

            if local_dev not in device_to_cell_id or neighbor not in device_to_cell_id:
                continue

            edge_id = escape(conn["edge_id"], quote=True)
            medium = escape(conn["medium_label"], quote=True)
            speed = escape(conn["speed_label"], quote=True)
            src_label = escape(conn["src_label"], quote=True)
            trgt_label = escape(conn["trgt_label"], quote=True)
            style = escape(conn["style"], quote=True)
            medium_type_attr = escape(conn["medium_type_attr"], quote=True)

            xml_lines.append(
                f'        <mxCell id="{edge_id}-src" value="{src_label}" style="labelBackgroundColor=#ffffff;" vertex="1" connectable="0" parent="{edge_id}">'
            )
            xml_lines.append('          <mxGeometry x="-0.5" relative="1" as="geometry">')
            xml_lines.append("            <mxPoint as=\"offset\" />")
            xml_lines.append("          </mxGeometry>")
            xml_lines.append("        </mxCell>")

            xml_lines.append(
                f'        <mxCell id="{edge_id}-trgt" value="{trgt_label}" style="labelBackgroundColor=#ffffff;" vertex="1" connectable="0" parent="{edge_id}">'
            )
            xml_lines.append('          <mxGeometry x="0.5" relative="-1" as="geometry">')
            xml_lines.append("            <mxPoint as=\"offset\" />")
            xml_lines.append("          </mxGeometry>")
            xml_lines.append("        </mxCell>")

            xml_lines.append(
                f'        <object id="{edge_id}" label="{medium}" speed="{speed}" medium_type="{medium_type_attr}" src_label="{src_label}" trgt_label="{trgt_label}" source="{escape(local_dev, quote=True)}" target="{escape(neighbor, quote=True)}">'
            )
            xml_lines.append(
                f'          <mxCell style="{style}" edge="1" parent="1" source="{device_to_cell_id[local_dev]}" target="{device_to_cell_id[neighbor]}">'
            )
            xml_lines.append('            <mxGeometry relative="1" as="geometry" />')
            xml_lines.append("          </mxCell>")
            xml_lines.append("        </object>")

        xml_lines.append("      </root>")
        xml_lines.append("    </mxGraphModel>")
        xml_lines.append("  </diagram>")

    xml_lines.append("</mxfile>")
    return "\n".join(xml_lines)
