"""Menu items."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

items = (
    NavMenuItem(
        link="plugins:nbcot:order_search",
        name="Order Search",
        permissions=["nbcot.view_ciscoorder"],
    ),
    NavMenuItem(
        link="plugins:nbcot:subscription_search",
        name="CCW-R Search",
        permissions=["nbcot.view_ciscoorder"],
    ),
    NavMenuItem(
        link="plugins:nbcot:ciscoorder_list",
        name="Tracked Orders",
        permissions=["nbcot.view_ciscoorder"],
        buttons=(
            NavMenuAddButton(
                link="plugins:nbcot:order_search",
                permissions=["nbcot.add_ciscoorder"],
            ),
        ),
    ),
)

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(NavMenuGroup(name="NBCOT", items=tuple(items)),),
    ),
)
