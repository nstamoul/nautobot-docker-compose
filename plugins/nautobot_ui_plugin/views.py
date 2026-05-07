#!./venv/bin/python

from django import forms as django_forms
from django.shortcuts import render
from django.views.generic import View
from nautobot.dcim.models import Cable, Device, Interface, Location, RackGroup
from nautobot.extras.models import Role, Status, Tag
from nautobot.ipam.models import VLAN
from nautobot.tenancy.models import Tenant, TenantGroup
from nautobot.core.forms import BootstrapMixin, DynamicModelChoiceField, DynamicModelMultipleChoiceField
from .models import NautobotSavedTopology
from . import forms as plugin_forms, filters
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_sameorigin
from packaging import version
import json
import re
from uuid import UUID, uuid4

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return obj.hex
        return json.JSONEncoder.default(self, obj)

# Default NeXt UI icons
SUPPORTED_ICONS = {
    'switch',
    'router',
    'firewall',
    'wlc',
    'unknown',
    'server',
    'phone',
    'nexus5000',
    'ipphone',
    'host',
    'camera',
    'accesspoint',
    'groups',
    'groupm',
    'groupl',
    'cloud',
    'unlinked',
    'hostgroup',
    'wirelesshost',
}

# Topology layers would be sorted
# in the same descending order
# as in the tuple below.
# It is expected that Device Role
# ids in Netbox exactly match
# values listed below.
# Update mapping to whatever you use.
DEFAULT_LAYERS_SORT_ORDER = (
    'undefined',
    'outside',
    'border',
    'edge',
    'edge-switch',
    'edge-router',
    'core',
    'core-router',
    'core-switch',
    'distribution',
    'distribution-router',
    'distribution-switch',
    'leaf',
    'spine',
    'access',
    'access-switch',
)


interface_full_name_map = {
    'Eth': 'Ethernet',
    'Fa': 'FastEthernet',
    'Gi': 'GigabitEthernet',
    'Te': 'TenGigabitEthernet',
}


DEFAULT_ICON_MODEL_MAP = {
    'CSR1000V': 'router',
    'Nexus': 'switch',
    'IOSXRv': 'router',
    'IOSv': 'switch',
    '2901': 'router',
    '2911': 'router',
    '2921': 'router',
    '2951': 'router',
    '4321': 'router',
    '4331': 'router',
    '4351': 'router',
    '4421': 'router',
    '4431': 'router',
    '4451': 'router',
    '8200': 'router',
    '8300': 'router',
    '2960': 'switch',
    '3750': 'switch',
    '3850': 'switch',
    '9200': 'switch',
    '9300': 'switch',
    '9400': 'switch',
    '9500': 'switch',
    'ASA': 'firewall',
    '9115': 'accesspoint'
}

MODEL_ICON_FALLBACK_RULES = (
    ('firewall', (
        'FORTIGATE',
        'FIREWALL',
        'PALO ALTO',
        'CHECKPOINT',
        'CHECK POINT',
        'NETGATE',
        'SOPHOS',
        'FPR',
        'FTD',
        'ASA',
    )),
    ('wlc', (
        'AIR-CT',
        'CT5508',
        'CT5520',
        'WLC',
        'C9800',
        '9800-',
    )),
    ('accesspoint', (
        'MERAKI',
        'C9115',
        'AIR-AP',
        'AIR-LAP',
        'AIR-CAP',
        'AP802',
        'AIRONET',
        'ACCESS POINT',
        'WIRELESS AP',
        'CW91',
        'CW92',
    )),
    ('host', ('VMWARE',)),
    ('nexus5000', ('UCS-FI',)),
    ('nexus5000', ('N3K', 'N5K', 'N7K', 'N9K')),
    ('router', (
        'ISR',
        'ASR',
        'C8000',
        'C8200',
        'C8300',
        'C8500',
        'C1100',
        'CSR1000V',
        'ROUTER',
    )),
    ('switch', (
        'WS-',
        'C1000-',
        'C9200',
        'C9300',
        '2960',
        '2950',
        '3650',
        '3850',
        '3560',
        '3750',
        'SWITCH',
    )),
)


DEFAULT_ICON_ROLE_MAP = {
    'border': 'router',
    'edge-switch': 'switch',
    'edge-router': 'router',
    'core-router': 'router',
    'core-switch': 'switch',
    'distribution': 'switch',
    'distribution-router': 'router',
    'distribution-switch': 'switch',
    'leaf': 'switch',
    'spine': 'switch',
    'access': 'switch',
    'access-switch': 'switch',
}


PLUGIN_SETTINGS = settings.PLUGINS_CONFIG.get("nautobot_ui_plugin", dict())

MANUAL_LAYERS_SORT_ORDER = PLUGIN_SETTINGS.get("layers_sort_order", "")
LAYERS_SORT_ORDER = MANUAL_LAYERS_SORT_ORDER or DEFAULT_LAYERS_SORT_ORDER

MANUAL_ICON_MODEL_MAP = PLUGIN_SETTINGS.get("icon_model_map", "")
ICON_MODEL_MAP = MANUAL_ICON_MODEL_MAP or DEFAULT_ICON_MODEL_MAP

MANUAL_ICON_ROLE_MAP = PLUGIN_SETTINGS.get("icon_role_map", "")
ICON_ROLE_MAP = MANUAL_ICON_ROLE_MAP or DEFAULT_ICON_ROLE_MAP

# Defines whether Devices with no connections
# are displayed on the topology view by default or not.
DISPLAY_UNCONNECTED = PLUGIN_SETTINGS.get("DISPLAY_UNCONNECTED", True)

# Defines whether logical links between end-devices for multi-cable hops
# are displayed in addition to the physical cabling on the topology view by default or not.
DISPLAY_LOGICAL_MULTICABLE_LINKS = PLUGIN_SETTINGS.get("DISPLAY_LOGICAL_MULTICABLE_LINKS", False)

# Defines whether passive devices
# are displayed on the topology view by default or not.
# Passive devices are patch pannels, power distribution units, etc.
DISPLAY_PASSIVE_DEVICES = PLUGIN_SETTINGS.get("DISPLAY_PASSIVE_DEVICES", False)

# Hide these roles by default
UNDISPLAYED_ROLE_IDS = PLUGIN_SETTINGS.get("undisplayed_role_ids", tuple())

# Hide devices tagged with these tags
UNDISPLAYED_DEVICE_TAGS = PLUGIN_SETTINGS.get("undisplayed_device_tags", tuple())

# Filter device tags listed in Select Layers menu
SELECT_LAYERS_LIST_INCLUDE_DEVICE_TAGS = PLUGIN_SETTINGS.get("select_layers_list_include_device_tags", tuple())
SELECT_LAYERS_LIST_EXCLUDE_DEVICE_TAGS = PLUGIN_SETTINGS.get("select_layers_list_exclude_device_tags", tuple())

# Defines the initial layer alignment direction on the view
INITIAL_LAYOUT = PLUGIN_SETTINGS.get("INITIAL_LAYOUT", 'auto')
if INITIAL_LAYOUT not in ('vertical', 'horizontal', 'auto'):
    INITIAL_LAYOUT = 'auto'


def if_shortname(ifname):
    for k, v in interface_full_name_map.items():
        if ifname.startswith(v):
            return ifname.replace(v, k)
    return ifname


def get_node_layer_sort_preference(role):
    """Layer priority selection function
    Layer sort preference is designed as numeric value.
    This function identifies it by LAYERS_SORT_ORDER
    object position by default. With numeric values,
    the logic may be improved without changes on NeXt app side.
    0(null) results undefined layer position in NeXt UI.
    Valid indexes start with 1.
    """
    for i, r in enumerate(LAYERS_SORT_ORDER, start=1):
        if role == r:
            return i
    return 1


def get_fallback_icon_from_model(model):
    model_str = str(model or '').upper()
    if not model_str:
        return None
    for icon_type, model_patterns in MODEL_ICON_FALLBACK_RULES:
        for model_pattern in model_patterns:
            if model_pattern in model_str:
                return icon_type
    return None


def get_icon_type(device_id):
    """
    Node icon getter function.
    Selection order:
    1. Based on 'icon_{icon_type}' tag in Netbox device
    2. Based on Netbox device type and ICON_MODEL_MAP
    3. Based on Netbox device role and ICON_ROLE_MAP
    4. Default 'undefined'
    """
    nb_device = Device.objects.get(id=device_id)
    if not nb_device:
        return 'unknown'
    for tag in nb_device.tags.names():
        if 'icon_' in tag:
            if tag.replace('icon_', '') in SUPPORTED_ICONS:
                return tag.replace('icon_', '')
    model = str(nb_device.device_type.model or '')
    model_upper = model.upper()
    for model_base, icon_type in ICON_MODEL_MAP.items():
        if str(model_base).upper() in model_upper:
            return icon_type
    fallback_icon = get_fallback_icon_from_model(model)
    if fallback_icon:
        return fallback_icon
    for role_id, icon_type in ICON_ROLE_MAP.items():
        if str(nb_device.role.pk) == role_id:
            return icon_type
    return 'unknown'


def tag_is_hidden(tag):
    for tag_regex in UNDISPLAYED_DEVICE_TAGS:
        if re.search(tag_regex, tag):
            return True
    return False


def filter_tags(tags):
    if not tags:
        return []
    if SELECT_LAYERS_LIST_INCLUDE_DEVICE_TAGS:
        filtered_tags = []
        for tag in tags:
            for tag_regex in SELECT_LAYERS_LIST_INCLUDE_DEVICE_TAGS:
                if re.search(tag_regex, tag):
                    filtered_tags.append(tag)
                    break
            if tag_is_hidden(tag):
                filtered_tags.append(tag)
        tags = filtered_tags
    if SELECT_LAYERS_LIST_EXCLUDE_DEVICE_TAGS:
        filtered_tags = []
        for tag in tags:
            for tag_regex in SELECT_LAYERS_LIST_EXCLUDE_DEVICE_TAGS:
                if re.search(tag_regex, tag) and not tag_is_hidden(tag):
                    break
            else:
                filtered_tags.append(tag)
        tags = filtered_tags
    return tags

def get_vlan_topology(nb_devices_qs, vlans):

    topology_dict = {'nodes': [], 'links': []}
    roles = set()
    all_device_tags = set()
    multi_cable_connections = []
    vlan = VLAN.objects.get(id=vlans)
    interfaces = vlan.get_interfaces()
    filtred_devices = [d.id for d in nb_devices_qs]
    filtred_interfaces = []
    for interface in interfaces:
        if interface.is_connectable:
            direct_device_id = interface.device.id
            interface_trace = interface.trace()
            if len(interface_trace) != 0:
                termination_b_iface = interface_trace[-1][-1]
                connected_device_id = termination_b_iface.device.id
                if (direct_device_id in filtred_devices) or (direct_device_id in filtred_devices):
                    filtred_interfaces.append(interface)



    devices = []
    for interface in filtred_interfaces:
        if interface.is_connectable:
            if interface.device not in devices:
                devices.append(interface.device)
            interface_trace = interface.trace()
            if len(interface_trace) != 0:
                termination_b_iface = interface_trace[-1][-1]
                if termination_b_iface.device not in devices:
                    devices.append(termination_b_iface.device)


    device_ids = [d.id for d in devices]
    for device in devices:
        device_is_passive = False
        device_url = device.get_absolute_url()
        primary_ip = ''
        if device.primary_ip:
            primary_ip = str(device.primary_ip.address)
        tags = [str(tag) for tag in device.tags.names()]
        for tag in tags:
            all_device_tags.add((tag, not tag_is_hidden(tag)))
        topology_dict['nodes'].append({
            'id': device.id,
            'name': device.name,
            'dcimDeviceLink': device_url,
            'primaryIP': primary_ip,
            'serial_number': device.serial,
            'model': device.device_type.model,
            'role': device.role.pk,
            'layerSortPreference': get_node_layer_sort_preference(
                device.role.id
                ),
            'icon': get_icon_type(
                device.id
                ),
            'isPassive': device_is_passive,
            'tags': tags,
            })
        is_visible = not (device.role.pk in UNDISPLAYED_ROLE_IDS)
        roles.add((device.role.pk, device.role.name, is_visible))

    mapped_links = []
    for interface in filtred_interfaces:
        if interface.is_connectable:
            interface_trace = interface.trace()
            if len(interface_trace) != 0:
                source_cable = interface_trace[0]
                dest_cable = interface_trace[-1]
                mapping_link = [source_cable[0].device.id,dest_cable[-1].device.id]
                if (mapping_link not in mapped_links) and (mapping_link.reverse() not in mapped_links):
                    mapped_links.append(mapping_link)

                    topology_dict['links'].append({
                        'id': source_cable[1].id,
                        'source': source_cable[0].device.id,
                        'target': dest_cable[-1].device.id,
                        "srcIfName": if_shortname(source_cable[0].name),
                        "tgtIfName": if_shortname(dest_cable[-1].name),
                        })

    return topology_dict, roles, multi_cable_connections, list(all_device_tags)


def get_topology(nb_devices_qs):
    topology_dict = {'nodes': [], 'links': []}
    roles = set()
    all_device_tags = set()
    multi_cable_connections = []
    if not nb_devices_qs:
        return topology_dict, roles, multi_cable_connections, list(all_device_tags)
    links = set()
    device_ids = [d.id for d in nb_devices_qs]
    for nb_device in nb_devices_qs:
        device_is_passive = False
        device_url = nb_device.get_absolute_url()
        primary_ip = ''
        if nb_device.primary_ip:
            primary_ip = str(nb_device.primary_ip.address)
        tags = [str(tag) for tag in nb_device.tags.names()] or []
        tags = filter_tags(tags)
        for tag in tags:
            all_device_tags.add((tag, not tag_is_hidden(tag)))
        links_from_device = Cable.objects.filter(_termination_a_device_id=nb_device.id)
        links_to_device = Cable.objects.filter(_termination_b_device_id=nb_device.id)
        from_device_passive, to_device_passive = False, False
        # Device is considered passive if it has no linked Interfaces.
        # Passive cabling devices use Rear and Front Ports.
        for link in links_from_device:
            if isinstance(link.termination_a, Interface) and link.termination_a.device.id == nb_device.id:
                break
        else:
            from_device_passive = True
        for link in links_to_device:
            if isinstance(link.termination_b, Interface) and link.termination_b.device.id == nb_device.id:
                break
        else:
            to_device_passive = True
        device_is_passive = from_device_passive and to_device_passive
        topology_dict['nodes'].append({
            'id': nb_device.id,
            'name': nb_device.name,
            'dcimDeviceLink': device_url,
            'primaryIP': primary_ip,
            'serial_number': nb_device.serial,
            'model': nb_device.device_type.model,
            'role': nb_device.role.pk,
            'layerSortPreference': get_node_layer_sort_preference(
                nb_device.role.id
            ),
            'icon': get_icon_type(
                nb_device.id
            ),
            'isPassive': device_is_passive,
            'tags': tags,
        })
        is_visible = not (nb_device.role.pk in UNDISPLAYED_ROLE_IDS)
        roles.add((nb_device.role.pk, nb_device.role.name, is_visible))
        if not links_from_device:
            continue
        for link in links_from_device:
            # Include links to all devices, not only direct neighbours. There might be passive devices on the way
            links.add(link)
        for link in links_to_device:
            links.add(link)
    roles = list(roles)
    roles.sort(key=lambda i: get_node_layer_sort_preference(i[0]))
    all_device_tags = list(all_device_tags)
    all_device_tags.sort()
    if not links:
        return topology_dict, roles, multi_cable_connections, list(all_device_tags)
    link_ids = set()
    for link in links:
        try:
            link.termination_a.device
            link.termination_b.device
        except AttributeError:
            continue
        if link.termination_a.device.id in device_ids and link.termination_b.device.id in device_ids:
            link_ids.add(link.id)
            topology_dict['links'].append({
                'id': link.id,
                'source': link.termination_a.device.id,
                'target': link.termination_b.device.id,
                "srcIfName": if_shortname(link.termination_a.name),
                "tgtIfName": if_shortname(link.termination_b.name)
            })
        if not (isinstance(link.termination_a, Interface) or isinstance(link.termination_b, Interface)):
            # Skip trace if none of cable terminations is an Interface
            continue
        interface_side = None
        if isinstance(link.termination_a, Interface):
            interface_side = link.termination_a
        elif isinstance(link.termination_b, Interface):
            interface_side = link.termination_b
        trace_result = interface_side.trace()
        if not trace_result:
            continue
        cable_path = trace_result
        # identify segmented cable paths between end-devices
        if len(cable_path) < 2:
            continue
        if isinstance(cable_path[0][0], Interface) and isinstance(cable_path[-1][2], Interface):
            if set([c[1] for c in cable_path]) in [set([c[1] for c in x]) for x in multi_cable_connections]:
                continue
            multi_cable_connections.append(cable_path)
    for cable_path in multi_cable_connections:
        try:
            cable_path[0][0].device
            cable_path[-1][2].device
        except AttributeError:
            continue
        source = cable_path[0][0].device.id
        target = cable_path[-1][2].device.id
        if source in device_ids and target in device_ids:
            link_id = uuid4() # dummy ID for a logical link
            link_ids.add(link_id)
            topology_dict['links'].append({
                'id': link_id,
                'source': source,
                'target': target,
                "srcIfName": if_shortname(cable_path[0][0].name),
                "tgtIfName": if_shortname(cable_path[-1][2].name),
                "isLogicalMultiCable": True,
            })
    return topology_dict, roles, multi_cable_connections, all_device_tags


def get_saved_topology(id):
    topology_dict = {}
    roles = []
    device_tags = []
    roles_detailed = []
    device_tags_detailed = []
    layout_context = {}
    topology_data = NautobotSavedTopology.objects.get(id=id)
    if not topology_data:
        return topology_dict, roles, device_tags, layout_context
    topology_dict = dict(topology_data.topology)
    if 'nodes' not in topology_dict:
        return topology_dict, roles, device_tags, layout_context
    roles = list(set([str(d.get('role')) for d in topology_dict['nodes'] if d.get('role')]))
    for role in roles:
        is_visible = not (role in UNDISPLAYED_ROLE_IDS)
        role_obj = Role.objects.get(id=role)
        if not role_obj:
            roles_detailed.append((role, role, is_visible))
            continue
        roles_detailed.append((role_obj.id, role_obj.name, is_visible))
    roles_detailed.sort(key=lambda i: get_node_layer_sort_preference(i[0]))
    device_tags = set()
    for device in topology_dict['nodes']:
        if 'tags' not in device:
            continue
        for tag in device['tags']:
            device_tags.add(str(tag))
    device_tags = list(device_tags)
    device_tags_detailed = list([(tag, not tag_is_hidden(tag)) for tag in device_tags])
    layout_context = dict(topology_data.layout_context)
    return topology_dict, roles_detailed, device_tags_detailed, layout_context


def get_default_active_status_id():
    active_status = Status.objects.get_for_model(Device).filter(name__iexact='Active').first()
    if not active_status:
        return None
    return str(active_status.id)


class TopologyFilterForm(BootstrapMixin, django_forms.Form):
    model = Device

    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=True,
        to_field_name='id',
        null_option='None',
        label='Tenant',
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=True,
        to_field_name='id',
        null_option='None',
        label='Site',
        query_params={'tenant': '$tenant_id'},
    )
    status_id = DynamicModelMultipleChoiceField(
        queryset=Status.objects.get_for_model(Device),
        required=True,
        to_field_name='id',
        null_option='None',
        label='Status',
    )
    role_id = DynamicModelMultipleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        to_field_name='id',
        null_option='None',
        label='Device Role',
        query_params={'content_types': Device._meta.label_lower},
    )
    rack_group_id = DynamicModelMultipleChoiceField(
        queryset=RackGroup.objects.all(),
        required=False,
        to_field_name='id',
        null_option='None',
        label='Rack Group',
        query_params={'location': '$location_id'},
    )
    device_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(),
        to_field_name='id',
        required=False,
        null_option='None',
        label='Device',
        query_params={
            'tenant': '$tenant_id',
            'location': '$location_id',
            'status': '$status_id',
            'role': '$role_id',
            'rack_group': '$rack_group_id',
        },
    )
    vlan_id = DynamicModelChoiceField(
        queryset=VLAN.objects.all(),
        required=False,
        to_field_name='id',
        null_option='None',
        label='VLAN',
    )
    tenant_group_id = DynamicModelMultipleChoiceField(
        queryset=TenantGroup.objects.all(),
        required=False,
        to_field_name='id',
        null_option='None',
        label='Tenant Group',
    )
    tag_id = DynamicModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        to_field_name='id',
        null_option='None',
        label='Tag',
        query_params={'content_types': Device._meta.label_lower},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields([
            'tenant_id',
            'location_id',
            'status_id',
            'role_id',
            'rack_group_id',
            'device_id',
            'vlan_id',
            'tenant_group_id',
            'tag_id',
        ])
        active_status_id = get_default_active_status_id()
        if active_status_id and not self.is_bound:
            self.fields['status_id'].initial = [active_status_id]


class TopologyView(PermissionRequiredMixin, View):
    """Generic Topology View"""
    permission_required = ('dcim.view_location', 'dcim.view_device', 'dcim.view_cable')
    queryset = Device.objects.all()
    filterset = filters.TopologyFilterSet
    template_name = 'nautobot_ui_plugin/topology.html'

    def get(self, request):
        active_status_id = get_default_active_status_id()
        form_request_data = request.GET.copy()
        if active_status_id and not form_request_data.getlist('status_id'):
            form_request_data.setlist('status_id', [active_status_id])
        if not request.GET:
            self.queryset = Device.objects.none()
        elif 'saved_topology_id' in request.GET:
            self.queryset = Device.objects.none()

        saved_topology_id = request.GET.get('saved_topology_id')
        layout_context = {}

        if saved_topology_id is not None:
            topology_dict, roles, device_tags, layout_context = get_saved_topology(saved_topology_id)
        else:
            vlans = []
            clean_request = form_request_data.copy()
            if 'vlan_id' in clean_request:
                clean_request.pop('vlan_id')
                vlans = form_request_data.get('vlan_id')
            else:
                clean_request = form_request_data.copy()

            required_filter_values_present = all(
                clean_request.getlist(field_name)
                for field_name in ('tenant_id', 'location_id', 'status_id')
            )
            if required_filter_values_present:
                self.queryset = self.filterset(clean_request, self.queryset).qs
                self.queryset = self.queryset.filter(status_id__in=clean_request.getlist('status_id'))
            else:
                self.queryset = Device.objects.none()
            if len(vlans) == 0:
                topology_dict, roles, multi_cable_connections, device_tags = get_topology(self.queryset)
            else:
                topology_dict, roles, multi_cable_connections, device_tags = get_vlan_topology(self.queryset, vlans)

        # don't use default dict cast, doesn't work properly with multivalue dicts
        requestGET = form_request_data.dict()
        filter_form_data = layout_context.get('requestGET') or form_request_data
        if isinstance(filter_form_data, dict):
            filter_form_data = dict(filter_form_data)
            if active_status_id and not filter_form_data.get('status_id'):
                filter_form_data['status_id'] = [active_status_id]

        return render(request, self.template_name, {
            'source_data': json.dumps(topology_dict, cls=UUIDEncoder),
            'display_unconnected': layout_context.get('displayUnconnected') or DISPLAY_UNCONNECTED,
            'roles': roles,
            'device_tags': device_tags,
            'undisplayed_roles': list(UNDISPLAYED_ROLE_IDS),
            'undisplayed_device_tags': list(UNDISPLAYED_DEVICE_TAGS),
            'display_logical_multicable_links': DISPLAY_LOGICAL_MULTICABLE_LINKS,
            'display_passive_devices': layout_context.get('displayPassiveDevices') or DISPLAY_PASSIVE_DEVICES,
            'initial_layout': INITIAL_LAYOUT,
            'filter_form': TopologyFilterForm(
                filter_form_data,
                label_suffix=''
            ),
            'load_saved_filter_form': plugin_forms.LoadNautobotSavedTopologyFilterForm(
                request.GET,
                label_suffix='',
                user=request.user
            ),
            'load_saved': NautobotSavedTopology.objects.all(),
            'requestGET': requestGET,
        })


class LocationTopologyView(TopologyView):
    template_name = 'nautobot_ui_plugin/location_topology.html'

    @xframe_options_sameorigin
    def get(self, request):
        return super().get(request)
