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


def draw_body(layout, context):
    """Panel contents, shared by both tabs."""
    obj = context.active_object
    if obj is None:
        layout.label(text="Select a garment or the character", icon="INFO")
        return
    row = layout.row()
    row.label(text=obj.name, icon="OBJECT_DATA")
    if "cloth" in obj or "shoe" in obj:
        row.label(text="clothing", icon="CHECKMARK")

    from .common import find_rig
    rig = find_rig(obj)
    if rig is None:
        box = layout.box()
        box.alert = True
        box.label(text="No HumGen character found", icon="ERROR")
    else:
        layout.label(text="rig: " + rig.name, icon="ARMATURE_DATA")

    from .weights import arp_available, GUARD_NAME
    layout.label(text="engine: " + ("Auto-Rig Pro voxel" if arp_available()
                                    else "bone heat / surface"),
                 icon="MOD_VERTEX_WEIGHT")
    guard = obj.modifiers.get(GUARD_NAME) if obj.type == "MESH" else None
    if guard is not None:
        layout.label(text="guard: %s, %.0f mm" % (guard.target.name if guard.target
                                                   else "no target",
                                                   guard.offset * 1000),
                     icon="MOD_SHRINKWRAP")

    layout.separator()
    layout.label(text="Clothing", icon="MOD_CLOTH")
    draw_clothing_tools(layout, context)
    layout.separator()
    layout.label(text="Rig", icon="ARMATURE_DATA")
    draw_rig_tools(layout, context)


# Two independent panels, NOT a subclass: registering a Panel subclass lets Blender
# clobber the base class's bl_category, which silently moved the Arche FX tab.
class ARCHEFX_PT_tools(bpy.types.Panel):
    """The add-on's own sidebar tab."""

    bl_idname = "ARCHEFX_PT_tools"
    bl_label = "Arche Extensions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        draw_body(self.layout, context)


class ARCHEFX_PT_humgen_tab(bpy.types.Panel):
    """The same buttons, inside HumGen's own sidebar tab.

    Appending into HumGen's panels does not work: `bpy.types.HG_PT_CLOTHING` is the
    very class you get by importing it, yet `_draw_funcs` stays empty after
    `append()`. Registering our own panel with `bl_category = "HumGen"` puts the
    buttons in that tab reliably, and nothing another add-on does can wipe it.
    """

    bl_idname = "ARCHEFX_PT_humgen_tab"
    bl_label = "Arche Extensions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HumGen"

    def draw(self, context):
        draw_body(self.layout, context)


# Appending into HumGen's panels was tried and does not work - see the note above.
PANEL_HOOKS = ()

classes = (ARCHEFX_PT_tools, ARCHEFX_PT_humgen_tab)
