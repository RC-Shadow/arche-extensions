# Arche FX HumGen Tools - repair clothing after a Rigify conversion.
# Copyright (C) 2026 Arche FX. GPL-3.0-or-later, see LICENSE.
"""HumGen's Rigify conversion renames vertex groups to the DEF- convention and rebinds
the rig's children - but only the children that exist *at conversion time*
(`_iterate_children`, human/pose/rigify.py). Clothing added later keeps un-prefixed
group names, matches no deform bone, and never moves. Its Armature modifier target is
set correctly, so nothing looks wrong and Blender reports no error.

Nothing here imports Human Generator, so this half keeps working whatever HumGen changes.
"""

import bpy

from .common import HG_RIGIFY_MARKER, SKIP_PREFIXES, find_hg_rigify_rig


def needs_rebind(obj, deform_bones):
    """True when none of this object's vertex groups drive a deform bone."""
    skip = tuple(p for p in SKIP_PREFIXES if p != "def-")
    groups = [vg.name for vg in obj.vertex_groups
              if not vg.name.lower().startswith(skip)]
    if not groups:
        return False
    return not any(name in deform_bones for name in groups)


def rename_vertex_groups(obj):
    for vgroup in obj.vertex_groups:
        if not vgroup.name.lower().startswith(SKIP_PREFIXES):
            vgroup.name = "DEF-" + vgroup.name


def rebind_drivers(obj, rig):
    """Repoint shape key drivers at the rig and fix their bone targets.

    HumGen's own `_correct_drivers` only DEF-prefixes forearm, upper_arm, thigh and
    foot, leaving anything else dangling - `shin` in particular, which silently breaks
    the knee corrective shape keys. Only targets that are empty or already point at an
    armature are claimed, so drivers referencing other objects are left alone.
    """
    shape_keys = getattr(obj.data, "shape_keys", None)
    if not shape_keys or not shape_keys.animation_data:
        return 0
    bones = rig.data.bones
    fixed = 0
    for driver in shape_keys.animation_data.drivers:
        for var in driver.driver.variables:
            for target in var.targets:
                if target.id is not None and getattr(target.id, "type", None) != "ARMATURE":
                    continue
                target.id = rig
                bone = target.bone_target
                if bone and bone not in bones and "DEF-" + bone in bones:
                    target.bone_target = "DEF-" + bone
                    fixed += 1
    return fixed


def rebind_to_rig(rig):
    """Re-bind every mesh child that currently drives no deform bone. Idempotent."""
    deform = {b.name for b in rig.data.bones if b.use_deform}
    rebound = []
    for child in rig.children:
        if child.type != "MESH" or not needs_rebind(child, deform):
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
            self.report({"ERROR"},
                        "No Human Generator Rigify rig found for the active object")
            return {"CANCELLED"}
        rebound = rebind_to_rig(rig)
        if rebound:
            self.report({"INFO"}, "Re-bound %d object(s): %s"
                        % (len(rebound), ", ".join(rebound)))
        else:
            self.report({"INFO"},
                        "Nothing to re-bind, all clothing already follows the rig")
        return {"FINISHED"}


classes = (ARCHEFX_OT_rebind_humgen_rigify,)
