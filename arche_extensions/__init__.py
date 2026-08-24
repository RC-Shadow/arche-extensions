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
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > HumGen > Clothing and Pose (or its own Arche FX tab)",
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
_fallback = []


def _hook_panels():
    """Append into HumGen's panels, or register our own tab.

    Deferred on a timer because add-on registration order is not guaranteed - HumGen
    may not have registered its panels yet when we register.
    """
    for idname, draw_func in ui.PANEL_HOOKS:
        panel = getattr(bpy.types, idname, None)
        if panel is not None:
            panel.append(draw_func)
            _hooked.append((panel, draw_func))
    if not _hooked:
        bpy.utils.register_class(ui.ARCHEFX_PT_tools)
        _fallback.append(True)
    return None  # returning None unregisters the timer


def register():
    for cls in rigify.classes + clothing.classes:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_hook_panels, first_interval=0.5)


def unregister():
    for panel, draw_func in _hooked:
        try:
            panel.remove(draw_func)
        except Exception:  # noqa: BLE001
            pass
    _hooked.clear()

    if _fallback:
        try:
            bpy.utils.unregister_class(ui.ARCHEFX_PT_tools)
        except Exception:  # noqa: BLE001
            pass
        _fallback.clear()

    for cls in reversed(rigify.classes + clothing.classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    register()
