# Arche Extensions - panels.
# Copyright (C) 2026 Arche FX. GPL-3.0-or-later, see LICENSE.
"""Buttons are appended into Human Generator's own tabs where they belong - clothing
tools in the Clothing tab, the Rigify repair in the Pose tab - with a standalone
fallback tab when those panels cannot be reached.
"""

import bpy

from .clothing import (ARCHEFX_OT_add_as_clothing, ARCHEFX_OT_bind_weights,
                       ARCHEFX_OT_remove_clothing,
                       ARCHEFX_OT_save_clothing_to_library)
from .rigify import ARCHEFX_OT_rebind_humgen_rigify

PANEL_CATEGORY = "Arche FX"


def draw_clothing_tools(layout, context):
    col = layout.column()
    col.scale_y = 1.35
    col.operator(ARCHEFX_OT_bind_weights.bl_idname, icon="MOD_VERTEX_WEIGHT")
    col.separator()
    col.operator(ARCHEFX_OT_add_as_clothing.bl_idname, icon="MOD_CLOTH")
    col.operator(ARCHEFX_OT_save_clothing_to_library.bl_idname, icon="FILE_NEW")
    col.separator()
    sub = col.column()
    sub.alert = True
    sub.operator(ARCHEFX_OT_remove_clothing.bl_idname, icon="TRASH")


def draw_rig_tools(layout, context):
    col = layout.column()
    col.scale_y = 1.35
    col.operator(ARCHEFX_OT_rebind_humgen_rigify.bl_idname, icon="GROUP_VERTEX")


def _draw_in_clothing_panel(self, context):
    """Appended to HumGen's Clothing tab. Wrapped so a failure here can never take
    HumGen's own UI down with it."""
    try:
        box = self.layout.box()
        box.label(text="Arche Extensions", icon="TOOL_SETTINGS")
        draw_clothing_tools(box, context)
    except Exception:  # noqa: BLE001
        pass


def _draw_in_pose_panel(self, context):
    try:
        box = self.layout.box()
        box.label(text="Arche Extensions", icon="TOOL_SETTINGS")
        draw_rig_tools(box, context)
    except Exception:  # noqa: BLE001
        pass


class ARCHEFX_PT_tools(bpy.types.Panel):
    """Fallback panel, registered only when HumGen's panels cannot be extended."""

    bl_idname = "ARCHEFX_PT_tools"
    bl_label = "Arche Extensions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        obj = context.active_object
        if obj is None:
            self.layout.label(text="Select an object", icon="INFO")
            return
        self.layout.label(text=obj.name, icon="OBJECT_DATA")
        draw_clothing_tools(self.layout, context)
        self.layout.separator()
        draw_rig_tools(self.layout, context)


PANEL_HOOKS = (
    ("HG_PT_CLOTHING", _draw_in_clothing_panel),
    ("HG_PT_POSE", _draw_in_pose_panel),
)

classes = (ARCHEFX_PT_tools,)
