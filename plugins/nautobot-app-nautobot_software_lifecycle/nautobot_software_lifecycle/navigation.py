"""Menu items."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

menu_items = (
    NavMenuTab(
        name="Vendor Lifecycle Management",
        weight=350,  # Position between Devices (300) and IPAM (400)
        groups=(
            NavMenuGroup(
                name="Cisco",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_software_lifecycle:softwarelicense_list",
                        name="Software Licenses",
                        permissions=["nautobot_software_lifecycle.view_softwarelicense"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_software_lifecycle:softwarelicense_add",
                                permissions=["nautobot_software_lifecycle.add_softwarelicense"],
                            ),
                        ),
                    ),
                ),
            ),
            NavMenuGroup(
                name="Juniper",
                weight=200,
                items=(
                    # Placeholder for future Juniper models
                ),
            ),
            NavMenuGroup(
                name="Arista",
                weight=300,
                items=(
                    # Placeholder for future Arista models
                ),
            ),
        ),
    ),
)
