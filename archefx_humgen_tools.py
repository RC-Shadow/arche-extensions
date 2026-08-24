# Arche FX - HumGen Tools
# Copyright (C) 2026 Arche FX
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See LICENSE for the full text.

bl_info = {
    "name": "Arche FX - HumGen Tools",
    "author": "Arche FX",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > HumGen > Pose > Rigify (or its own Arche FX tab)",
    "description": (
        "Human Generator helpers: bind clothing added after a Rigify conversion, "
        "turn any mesh into clothing, and save a single garment to the library."
    ),
    "category": "Rigging",
    "doc_url": "https://github.com/RC-Shadow/archefx-humgen-tools",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

# Human Generator skips these when it renames vertex groups during its own Rigify
# conversion. Matched here so a re-bind produces the same result as converting in
# the right order would have.
SKIP_PREFIXES = ("mask", "pin", "def-", "hair", "fh", "sim", "lip")

# Marker Human Generator writes onto the armature data of a rig it converted.
HG_RIGIFY_MARKER = "hg_rigify"

# Corrective-shapekey set names, as keyed in HumGen's corrective_sk_names_v2.json.
# NOTE: outfit.add_obj's docstring says "top", but the JSON key is "torso" and
# passing "top" raises KeyError. "torso" is the value that works.
CLOTH_TYPE_ITEMS = [
    ("torso", "Torso", "Shirt, jacket, top - adds elbow and shoulder corrective keys", 0),
    ("pants", "Pants", "Trousers, skirt - adds leg raise and foot down corrective keys", 1),
    ("full", "Full Body", "Dress, overall - adds both arm and leg corrective keys", 2),
    ("footwear", "Footwear", "Shoes, boots - adds foot down corrective keys", 3),
]


# ---------------------------------------------------------------------------
# Rigify re-bind. Deliberately depends on nothing from Human Generator, so this
# half keeps working no matter what HumGen changes.
# ---------------------------------------------------------------------------

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
    bone rotation. Skip this and the garment follows the rig but stops flexing.

    Only targets that are empty or already point at an armature are claimed, so
    drivers referencing some other object are left alone. The DEF- prefix is only
    added when the bare name genuinely does not resolve and the prefixed one does --
    which also covers bones HumGen's own conversion misses, such as `shin`.

    Returns the number of bone targets that were corrected.
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
                bone_target = target.bone_target
                if bone_target and bone_target not in bones and "DEF-" + bone_target in bones:
                    target.bone_target = "DEF-" + bone_target
                    fixed += 1
    return fixed


def rebind_to_rig(rig):
    """Re-bind every mesh child of rig that currently drives no deform bone.

    Returns the list of object names that were changed. Idempotent.
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


# ---------------------------------------------------------------------------
# Clothing tools. These wrap Human Generator's own API rather than
# reimplementing it -- A-pose correction, corrective shapekeys and auto weight
# painting are hundreds of lines of well-tested vendor code. HumGen is imported
# lazily so this add-on still registers (and re-bind still works) without it.
# ---------------------------------------------------------------------------

def _humgen_human(obj):
    """Return (Human, error_message). Human is None when it cannot be resolved."""
    try:
        from HumGen3D.human.human import Human
    except Exception:  # noqa: BLE001
        return None, "Human Generator is not installed or not enabled"

    # HumGen's own proximity search first, same as its Content panel button
    try:
        from HumGen3D.human.clothing.add_obj_to_clothing import get_human_from_distance

        human = get_human_from_distance(obj)
        if human:
            return human, ""
    except Exception:  # noqa: BLE001
        pass

    for candidate in (obj.parent, find_hg_rigify_rig(obj)):
        if candidate is None:
            continue
        try:
            human = Human.from_existing(candidate)
            if human:
                return human, ""
        except Exception:  # noqa: BLE001
            continue

    return None, (
        "Could not find a Human Generator character for this object. "
        "Move it onto the character, or parent it to the character's rig."
    )


def _verify_binding(obj, rig):
    """Report how well obj is bound. Returns (groups_driving_deform, bad_drivers)."""
    deform_bones = {b.name for b in rig.data.bones if b.use_deform}
    driving = sum(1 for vg in obj.vertex_groups if vg.name in deform_bones)

    bad = []
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys and shape_keys.animation_data:
        for driver in shape_keys.animation_data.drivers:
            for var in driver.driver.variables:
                for target in var.targets:
                    bone_target = target.bone_target
                    if bone_target and bone_target not in rig.data.bones:
                        bad.append(bone_target)
    return driving, bad


class ARCHEFX_OT_add_as_clothing(bpy.types.Operator):
    """Turn the selected mesh into clothing on this Human Generator character"""

    bl_idname = "archefx.add_as_clothing"
    bl_label = "Add to Character Clothing"
    bl_description = (
        "Turn the active mesh into clothing on the Human Generator character it sits "
        "on. Corrects its shape to the A-pose, adds the corrective shape keys and "
        "their drivers, auto weight paints it and parents it to the rig"
    )
    bl_options = {"REGISTER", "UNDO"}

    cloth_type: EnumProperty(
        name="Type",
        description="What part of the body this covers - decides which corrective "
        "shape keys are added",
        items=CLOTH_TYPE_ITEMS,
        default="torso",
    )
    recalculate_weights: BoolProperty(
        name="Auto Weight Paint",
        description="Recalculate vertex weights from the body. Turn off only if you "
        "already weight painted this yourself",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cloth_type")
        col.prop(self, "recalculate_weights")
        obj = context.active_object
        if obj and ("cloth" in obj or "shoe" in obj):
            col.separator()
            box = col.box()
            box.label(text="Already clothing - this will redo it", icon="INFO")
            box.label(text="Weight painting will be reset.")

    def execute(self, context):
        cloth_obj = context.active_object
        human, err = _humgen_human(cloth_obj)
        if human is None:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        # HumGen weight paints by transferring from the body with its clothing MASK
        # modifiers switched off, but it does not force a depsgraph update first and
        # it switches every mask back ON afterwards regardless of how you had them.
        # Snapshot them, pre-disable with an explicit update (which is what makes the
        # transfer work in background/batch too), then restore exactly.
        body = getattr(human.objects, "body", None)
        masks = [m for m in getattr(body, "modifiers", []) if m.type == "MASK"]
        mask_state = [(m, m.show_viewport, m.show_render) for m in masks]
        for mask in masks:
            mask.show_viewport = False
            mask.show_render = False
        context.evaluated_depsgraph_get().update()

        try:
            if self.cloth_type == "footwear":
                human.clothing.footwear.add_obj(
                    cloth_obj, self.recalculate_weights, context
                )
            else:
                human.clothing.outfit.add_obj(
                    cloth_obj, self.cloth_type, self.recalculate_weights, context
                )
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, "Human Generator could not add this: %s" % exc)
            return {"CANCELLED"}
        finally:
            for mask, show_vp, show_render in mask_state:
                mask.show_viewport = show_vp
                mask.show_render = show_render

        rig = cloth_obj.parent if cloth_obj.parent and cloth_obj.parent.type == "ARMATURE" else None
        msg = "Added '%s' as %s clothing" % (cloth_obj.name, self.cloth_type)
        if rig is not None:
            # HumGen's conversion only DEF-prefixes forearm/upper_arm/thigh/foot, so
            # a driver on any other bone (shin, for one) is left dangling on a Rigify
            # character. Repair those here rather than shipping a broken garment.
            fixed = rebind_drivers(cloth_obj, rig)
            driving, bad = _verify_binding(cloth_obj, rig)
            msg += " | %d groups drive deform bones" % driving
            if fixed:
                msg += " | fixed %d driver target(s)" % fixed
            if bad:
                msg += " | WARNING unresolved driver bones: %s" % ", ".join(sorted(set(bad)))
                self.report({"WARNING"}, msg)
                return {"FINISHED"}

        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ARCHEFX_OT_save_clothing_to_library(bpy.types.Operator):
    """Save this garment into the Human Generator clothing library"""

    bl_idname = "archefx.save_clothing_to_library"
    bl_label = "Add to Clothing Asset Library"
    bl_description = (
        "Save this garment to the Human Generator library so it can be loaded onto "
        "any future character. By default only the active garment is saved, not the "
        "whole outfit"
    )
    bl_options = {"REGISTER"}

    name: StringProperty(
        name="Name",
        description="Name this item will appear under in the library",
        default="",
    )
    category: StringProperty(
        name="Category",
        description="Library folder to save into. Created if it does not exist",
        default="Custom",
    )
    for_male: BoolProperty(name="For Male", default=True)
    for_female: BoolProperty(name="For Female", default=True)
    only_this_object: BoolProperty(
        name="Only This Garment",
        description=(
            "HumGen saves an outfit as a set - every object tagged as clothing at "
            "once. Leave this on to save just the active garment"
        ),
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and ("cloth" in obj or "shoe" in obj)

    def invoke(self, context, event):
        if not self.name:
            self.name = context.active_object.name
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "name")
        col.prop(self, "category")
        row = col.row(align=True)
        row.prop(self, "for_male", toggle=True)
        row.prop(self, "for_female", toggle=True)
        col.separator()
        col.prop(self, "only_this_object")
        siblings = self._siblings(context.active_object)
        if siblings and not self.only_this_object:
            box = col.box()
            box.label(text="Will save %d garments as one outfit:" % (len(siblings) + 1),
                      icon="INFO")
            for obj in siblings:
                box.label(text="   " + obj.name)
        col.separator()
        col.label(text="No thumbnail is saved.", icon="INFO")

    @staticmethod
    def _siblings(obj):
        """Other garments of the same kind currently on the character."""
        tag = "shoe" if "shoe" in obj else "cloth"
        rig = obj.parent
        if rig is None:
            return []
        return [o for o in rig.children if o is not obj and tag in o]

    def execute(self, context):
        cloth_obj = context.active_object
        if not self.name.strip():
            self.report({"ERROR"}, "Give the item a name")
            return {"CANCELLED"}
        if not (self.for_male or self.for_female):
            self.report({"ERROR"}, "Pick at least one gender to save for")
            return {"CANCELLED"}

        human, err = _humgen_human(cloth_obj)
        if human is None:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        is_shoe = "shoe" in cloth_obj
        tag = "shoe" if is_shoe else "cloth"
        settings = human.clothing.footwear if is_shoe else human.clothing.outfit

        # HumGen saves every object carrying the tag as one outfit. To save a single
        # garment, drop the tag from the others for the duration of the call, then
        # put it back exactly as it was.
        stashed = []
        if self.only_this_object:
            for obj in self._siblings(cloth_obj):
                stashed.append((obj, obj[tag]))
                del obj[tag]

        try:
            settings.save_to_library(
                self.name.strip(),
                for_male=self.for_male,
                for_female=self.for_female,
                open_when_finished=False,
                category=self.category.strip() or "Custom",
                thumbnail=None,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, "Human Generator could not save this: %s" % exc)
            return {"CANCELLED"}
        finally:
            for obj, value in stashed:
                obj[tag] = value

        self.report(
            {"INFO"},
            "Saved '%s' to the %s library under '%s'"
            % (self.name.strip(), "footwear" if is_shoe else "outfit", self.category),
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _draw_tools(layout, context):
    col = layout.column()
    col.scale_y = 1.35
    col.operator(ARCHEFX_OT_add_as_clothing.bl_idname, icon="MOD_CLOTH")
    col.operator(ARCHEFX_OT_save_clothing_to_library.bl_idname, icon="FILE_NEW")
    col.separator()
    col.operator(ARCHEFX_OT_rebind_humgen_rigify.bl_idname, icon="GROUP_VERTEX")


def _draw_in_humgen_panel(self, context):
    """Appended to HumGen's pose panel. Wrapped so a failure here can never take
    HumGen's own UI down with it."""
    try:
        box = self.layout.box()
        box.label(text="Arche FX", icon="TOOL_SETTINGS")
        _draw_tools(box, context)
    except Exception:  # noqa: BLE001
        pass


class ARCHEFX_PT_tools(bpy.types.Panel):
    """Fallback panel, registered only when HumGen's pose panel cannot be extended."""

    bl_idname = "ARCHEFX_PT_tools"
    bl_label = "HumGen Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Arche FX"

    def draw(self, context):
        obj = context.active_object
        if obj is None:
            self.layout.label(text="Select an object", icon="INFO")
            return
        self.layout.label(text=obj.name, icon="OBJECT_DATA")
        _draw_tools(self.layout, context)


_classes = (
    ARCHEFX_OT_rebind_humgen_rigify,
    ARCHEFX_OT_add_as_clothing,
    ARCHEFX_OT_save_clothing_to_library,
)

_hooked_panel = []
_fallback_registered = []


def _try_hook_humgen_panel():
    """Add the buttons to HumGen's pose panel, or fall back to our own tab.

    Deferred on a timer because add-on registration order is not guaranteed --
    HumGen may not have registered its panels yet when we register.
    """
    panel = getattr(bpy.types, "HG_PT_POSE", None)
    if panel is not None:
        panel.append(_draw_in_humgen_panel)
        _hooked_panel.append(panel)
    else:
        bpy.utils.register_class(ARCHEFX_PT_tools)
        _fallback_registered.append(True)
    return None  # returning None unregisters the timer


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
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
            bpy.utils.unregister_class(ARCHEFX_PT_tools)
        except Exception:  # noqa: BLE001
            pass
        _fallback_registered.clear()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
