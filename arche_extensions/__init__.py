# Arche Extensions
# Copyright (C) 2026 Arche FX
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE for the full text.

bl_info = {
    "name": "Arche Extensions",
    "author": "Arche FX",
    "version": (2, 3, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > HumGen tab, and its own Arche FX tab",
    "description": (
        "Human Generator helpers: bind garment weights properly, turn any mesh into "
        "clothing, save a single garment to the library, remove clothing cleanly, and "
        "repair clothing added after a Rigify conversion."
    ),
    "category": "Rigging",
    "doc_url": "https://github.com/RC-Shadow/arche-extensions",
}

import bpy

from . import clothing, rigify, ui

_hooked = []


def _hook_panels():
    """Kept as a no-op hook point.

    Appending into HumGen's panels was tried and does not work: bpy.types.HG_PT_CLOTHING
    is the same object you get by importing the class, yet its _draw_funcs stays empty
    after append(). The buttons are registered as our own panels instead - one in the
    Arche FX tab, one inside HumGen's tab - which nothing can wipe.
    """
    return None


def register():
    for cls in rigify.classes + clothing.classes + ui.classes:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_hook_panels, first_interval=0.5)


def unregister():
    for panel, draw_func in _hooked:
        try:
            panel.remove(draw_func)
        except Exception:  # noqa: BLE001
            pass
    _hooked.clear()

    for cls in reversed(rigify.classes + clothing.classes + ui.classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    register()
