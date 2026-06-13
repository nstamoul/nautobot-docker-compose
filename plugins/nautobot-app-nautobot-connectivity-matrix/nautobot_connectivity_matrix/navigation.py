"""Navigation menu items for the Connectivity Matrix Diagram app."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab


menu_items = (
    NavMenuTab(
        name="Plugins",
        groups=(
            NavMenuGroup(
                name="Connectivity Matrix",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_connectivity_matrix:connectionplanbatch_list",
                        name="Connection Batches",
                        permissions=["nautobot_connectivity_matrix.view_connectionplanbatch"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:nautobot_connectivity_matrix:connectionplanbatch_add",
                                permissions=["nautobot_connectivity_matrix.add_connectionplanbatch"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_connectivity_matrix:stack_plan",
                        name="Stack Plan Import",
                        permissions=["dcim.add_device"],
                    ),
                ),
            ),
        ),
    ),
)
