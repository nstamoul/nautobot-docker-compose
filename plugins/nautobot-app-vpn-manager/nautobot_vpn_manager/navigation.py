"""Menu items for the VPN manager app."""

from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(
            NavMenuGroup(
                name="VPN Manager",
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_vpn_manager:dashboard",
                        name="Dashboard",
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_vpn_manager:workers",
                        name="Worker Steering",
                    ),
                ),
            ),
        ),
    ),
)
