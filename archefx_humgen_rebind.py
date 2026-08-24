# Arche FX - Re-bind Clothing to Rigify (for Human Generator characters)
# Copyright (C) 2026 Arche FX
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See LICENSE for the full text.

bl_info = {
    "name": "Arche FX - HumGen Rigify Re-bind",
    "author": "Arche FX",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > HumGen > Pose > Rigify (or its own Arche FX tab)",
    "description": (
        "Binds clothing added AFTER a Human Generator character was converted to "
        "Rigify, so it follows the rig again."
    ),
    "category": "Rigging",
    "doc_url": "https://github.com/RC-Shadow/archefx-humgen-rebind",
}

import bpy

# Human Generator skips these when it renames vertex groups during its own Rigify
# conversion. Matched here so a re-bind produces the same result as converting in
# the right order would have.
SKIP_PREFIXES = ("mask", "pin", "def-", "hair", "fh", "sim", "lip")

# Marker Human Generator writes onto the armature data of a rig it converted.
# This add-on imports nothing from Human Generator, so a HumGen update cannot
# break it -- this string is the only point of contact.
HG_RIGIFY_MARKER = "hg_rigify"


def find_hg_rigify_rig(obj):
    """Return the HumGen Rigify armature related to obj, or None."""
    if obj is None:
        return None

    candidates = [obj, obj.parent]
    try:
        candidates.append(obj.find_armature())
    except (AttributeError, RuntimeError):
        pass
    for mod in getattr(obj, "modifiers", []):
        if mod.type == "ARMATURE" and mod.object:
            candidates.append(mod.object)

    for cand in candidates:
        if cand and cand.type == "ARMATURE" and HG_RIGIFY_MARKER in cand.data:
            return cand
    return None


def needs_rebind(obj, deform_bones):
    """True if none of the vertex groups on obj drive a deform bone.

    Tested against `use_deform` bones only, deliberately. Rigify also carries
    plain-named *control* bones (foot.L, f_index.01.L, eyeball.L) that collide with
    the un-prefixed group names HumGen uses. On a garment that genuinely did not
    deform at all, 37 groups still matched a bone that way -- so matching "any bone"
    is not evidence of anything. Only deform bones move mesh.
    """
    skip = tuple(p for p in SKIP_PREFIXES if p != "def-")
    groups = [vg.name for vg in obj.vertex_groups if not vg.name.lower().startswith(skip)]
    if not groups:
        return False
    return not any(name in deform_bones for name in groups)


def rename_vertex_groups(obj):
    """Prefix deforming groups with DEF- to match the Rigify naming convention."""
    for vg in obj.vertex_groups:
        if not vg.name.lower().startswith(SKIP_PREFIXES):
            vg.name = "DEF-" + vg.name


def rebind_drivers(obj, rig):
    """Repoint shape key drivers at the rig and correct their bone targets.

    Clothing corrective keys (cor_FootDown_Lt, cor_ElbowBend_Rt, ...) are driven by
    bone rotation and still reference the pre-Rigify rig, which no longer exists.
    Skip this and the garment follows the rig but stops flexing at the joint.

    Only targets that are empty or already point at an armature are claimed, so
    drivers referencing some other object are left alone. The DEF- prefix is only
    added when the bare name genuinely does not resolve and the prefixed one does.
    """
    shape_keys = getattr(obj.data, "shape_keys", None)
    if not shape_keys or not shape_keys.animation_data:
        return

    bones = rig.data.bones
    for driver in shape_keys.animation_data.drivers:
        for var in driver.driver.variables:
            for target in var.targets:
                if target.id is not None and getattr(target.id, "type", None) != "ARMATURE":
                    continue
                target.id = rig
                bone_target = target.bone_target
                if bone_target and bone_target not in bones and "DEF-" + bone_target in bones:
                    target.bone_target = "DEF-" + bone_target


def rebind_to_rig(rig):
    """Re-bind every mesh child of rig that currently drives no deform bone.

    Returns the list of object names that were changed. Idempotent: an already
    bound item matches dozens of deform bones, so it is never touched twice.
    """
    deform_bones = {bone.name for bone in rig.data.bones if bone.use_deform}
    rebound = []
    for child in rig.children:
        if child.type != "MESH" or not needs_rebind(child, deform_bones):
            continue
        rename_vertex_groups(child)
        for mod in child.modifiers:
            if mod.type == "ARMATURE":
                mod.object = rig
        rebind_drivers(child, rig)
        rebound.append(child.name)
    return rebound


class ARCHEFX_OT_rebind_humgen_rigify(bpy.types.Operator):
    """Bind clothing that was added after the Rigify conversion"""

    bl_idname = "archefx.rebind_humgen_rigify"
    bl_label = "Re-bind Clothing to Rigify"
    bl_description = (
        "Fixes clothing and footwear added after this Human Generator character was "
        "converted to Rigify. Renames its vertex groups to the DEF- convention, "
        "repoints its armature modifier and corrects its shape key drivers. "
        "Safe to run more than once"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return find_hg_rigify_rig(context.active_object) is not None

    def execute(self, context):
        rig = find_hg_rigify_rig(context.active_object)
        if rig is None:
            self.report({"ERROR"}, "No Human Generator Rigify rig found for the active object")
            return {"CANCELLED"}

        rebound = rebind_to_rig(rig)
        if rebound:
            self.report(
                {"INFO"},
                "Re-bound %d object(s): %s" % (len(rebound), ", ".join(rebound)),
            )
        else:
            self.report({"INFO"}, "Nothing to re-bind, all clothing already follows the rig")
        return {"FINISHED"}


def _draw_in_humgen_panel(self, context):
    """Appended to the Human Generator pose panel.

    Wrapped so that a failure here can never take HumGen's own UI down with it.
    """
    try:
        if find_hg_rigify_rig(context.active_object) is None:
            return
        box = self.layout.box()
        box.label(text="Arche FX", icon="GROUP_VERTEX")
        box.label(text="Clothing added after Rigify?", icon="INFO")
        col = box.column()
        col.scale_y = 1.4
        col.operator(ARCHEFX_OT_rebind_humgen_rigify.bl_idname, icon="GROUP_VERTEX")
    except Exception:  # noqa: BLE001
        pass


class ARCHEFX_PT_rebind(bpy.types.Panel):
    """Fallback panel, registered only when HumGen's pose panel cannot be extended."""

    bl_idname = "ARCHEFX_PT_rebind"
    bl_label = "HumGen Rigify Re-bind"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Arche FX"

    def draw(self, context):
        layout = self.layout
        rig = find_hg_rigify_rig(context.active_object)
        if rig is None:
            layout.label(text="Select a HumGen Rigify character", icon="INFO")
            return
        layout.label(text=rig.name, icon="ARMATURE_DATA")
        col = layout.column()
        col.scale_y = 1.4
        col.operator(ARCHEFX_OT_rebind_humgen_rigify.bl_idname, icon="GROUP_VERTEX")


_hooked_panel = []
_fallback_registered = []


def _try_hook_humgen_panel():
    """Add the button to HumGen's pose panel, or fall back to our own tab.

    Deferred on a timer because add-on registration order is not guaranteed --
    HumGen may not have registered its panels yet when we register.
    """
    panel = getattr(bpy.types, "HG_PT_POSE", None)
    if panel is not None:
        panel.append(_draw_in_humgen_panel)
        _hooked_panel.append(panel)
    else:
        bpy.utils.register_class(ARCHEFX_PT_rebind)
        _fallback_registered.append(True)
    return None  # returning None unregisters the timer


def register():
    bpy.utils.register_class(ARCHEFX_OT_rebind_humgen_rigify)
    bpy.app.timers.register(_try_hook_humgen_panel, first_interval=0.5)


def unregister():
    for panel in _hooked_panel:
        try:
            panel.remove(_draw_in_humgen_panel)
        except Exception:  # noqa: BLE001
            pass
    _hooked_panel.clear()

    if _fallback_registered:
        try:
            bpy.utils.unregister_class(ARCHEFX_PT_rebind)
        except Exception:  # noqa: BLE001
            pass
        _fallback_registered.clear()

    bpy.utils.unregister_class(ARCHEFX_OT_rebind_humgen_rigify)


if __name__ == "__main__":
    register()
