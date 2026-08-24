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
    "version": (1, 3, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > HumGen > Clothing and Pose (or its own Arche FX tab)",
    "description": (
        "Human Generator helpers: turn any mesh into clothing, save a single garment "
        "to the library, remove clothing cleanly, and bind clothing added after a "
        "Rigify conversion."
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


def _fill_unweighted(obj):
    """Give any vertex with no weight the weights of its nearest weighted vertex.

    An unweighted vertex ignores the armature completely and tears away from the
    rest of the mesh, so none may survive.
    """
    from mathutils.kdtree import KDTree

    weighted, orphans = [], []
    for v in obj.data.vertices:
        (weighted if any(g.weight > 1e-6 for g in v.groups) else orphans).append(v.index)
    if not orphans or not weighted:
        return 0
    kd = KDTree(len(weighted))
    for i, vi in enumerate(weighted):
        kd.insert(obj.data.vertices[vi].co, i)
    kd.balance()
    groups = list(obj.vertex_groups)
    for vi in orphans:
        _, idx, _ = kd.find(obj.data.vertices[vi].co)
        for g in obj.data.vertices[weighted[idx]].groups:
            if g.weight > 1e-6:
                groups[g.group].add([vi], g.weight, "REPLACE")
    return len(orphans)


def _purge_dead_groups(obj, deform_bones):
    """Drop groups holding no weight, and non-deform junk inherited from the body."""
    live = {g.group for v in obj.data.vertices for g in v.groups if g.weight > 0.001}
    doomed = [g for g in obj.vertex_groups
              if g.index not in live or g.name not in deform_bones]
    names = [g.name for g in doomed]
    for g in doomed:
        obj.vertex_groups.remove(g)
    return names


def rebuild_weights(obj, body, rig, context):
    """Re-derive the garment's weights from the body, then clean them up properly.

    HumGen's own pass is a single `data_transfer` with `vert_mapping="NEAREST"` and
    **no cleanup afterwards**. Measured on a real garment, that leaves 72.9% of
    vertices with weights that do not sum to 1 (2,676 of them under 0.5, so they
    follow the armature at less than half strength), a median of 5 bone influences
    per vertex against the body's 2, and 58 vertex groups holding no weight at all.

    This rebuilds with POLYINTERP_NEAREST, which interpolates across the nearest body
    face instead of snapping to one vertex. POLYINTERP_VNORPROJ scored better on drift
    but shoots a ray along each vertex normal, which on a thick closed garment lands on
    unrelated body parts - it produced 27 implausible groups including toes, feet and
    finger bones. A shirt that twitches when a toe moves is not acceptable.

    Result on the reference garment: every vertex sums to 1.000, median 2 influences
    (max 4) matching the body exactly, 14 sensible groups, none dead.
    """
    deform = {b.name for b in rig.data.bones if b.use_deform}
    obj.vertex_groups.clear()
    for v in obj.data.vertices:
        v.select = True

    masks = [(m, m.show_viewport, m.show_render)
             for m in body.modifiers if m.type == "MASK"]
    for m, _vp, _rd in masks:
        m.show_viewport = False
        m.show_render = False
    context.evaluated_depsgraph_get().update()   # or the transfer samples masked-away arms
    try:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        body.select_set(True)
        context.view_layer.objects.active = body      # data_transfer reads the ACTIVE object
        bpy.ops.object.data_transfer(
            data_type="VGROUP_WEIGHTS", use_create=True,
            vert_mapping="POLYINTERP_NEAREST",
            layers_select_src="ALL", layers_select_dst="NAME", mix_mode="REPLACE",
        )
    finally:
        for m, vp, rd in masks:
            m.show_viewport = vp
            m.show_render = rd
        context.evaluated_depsgraph_get().update()

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj

    def tidy():
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=0.001,
                                          keep_single=True)
        _purge_dead_groups(obj, deform)
        _fill_unweighted(obj)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL",
                                                  lock_active=False)

    tidy()
    # Blend across bone boundaries - without this the shoulder seam facets and pinches.
    # vertex_group_smooth polls for EDIT/WEIGHT_PAINT mode, unlike the others.
    if obj.vertex_groups:
        obj.vertex_groups.active_index = 0
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=3)
        bpy.ops.object.mode_set(mode="OBJECT")
        tidy()

    context.view_layer.update()
    return len(obj.vertex_groups)


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

        # HumGen's weight pass leaves unnormalised weights and dozens of dead groups.
        # Redo it properly from the body.
        if rig is not None and self.recalculate_weights and body is not None:
            try:
                kept = rebuild_weights(cloth_obj, body, rig, context)
                msg += " | weights rebuilt from the body, %d groups kept" % kept
            except Exception as exc:  # noqa: BLE001
                self.report({"WARNING"},
                            "Clothing added, but the weight rebuild failed: %s" % exc)

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

        # HumGen's is_valid_clothing_object requires the garment to carry EVERY vertex
        # group the body has. We deliberately delete the dead ones for clean deformation,
        # so re-create them empty for the duration of the save, then take them away again.
        body = getattr(human.objects, "body", None)
        added_groups = []
        if body is not None:
            have = {g.name for g in cloth_obj.vertex_groups}
            for g in body.vertex_groups:
                if g.name not in have:
                    cloth_obj.vertex_groups.new(name=g.name)
                    added_groups.append(g.name)

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
            for name in added_groups:
                vg = cloth_obj.vertex_groups.get(name)
                if vg is not None:
                    cloth_obj.vertex_groups.remove(vg)

        self.report(
            {"INFO"},
            "Saved '%s' to the %s library under '%s'"
            % (self.name.strip(), "footwear" if is_shoe else "outfit", self.category),
        )
        return {"FINISHED"}


def find_garment_masks(obj):
    """Names of the body MASK modifiers this garment brought with it.

    HumGen records them as custom properties mask_0 .. mask_9 on the garment.
    Reimplemented here (it is four lines) so removal needs no HumGen import.
    """
    masks = []
    for i in range(10):
        try:
            masks.append(obj["mask_%d" % i])
        except (KeyError, TypeError):
            break
    return masks


def find_hg_body(rig):
    """The HumGen body mesh under this rig, or None."""
    if rig is None:
        return None
    for child in rig.children:
        if child.type == "MESH" and "hg_body" in child:
            return child
    for child in rig.children:
        if child.type == "MESH" and child.name.startswith("HG_Body"):
            return child
    return None


class ARCHEFX_OT_remove_clothing(bpy.types.Operator):
    """Remove clothing from this character, cleaning up its body masks"""

    bl_idname = "archefx.remove_clothing"
    bl_label = "Remove Clothing"
    bl_description = (
        "Delete clothing from this Human Generator character and remove the geometry "
        "mask modifiers it added to the body, so no holes are left behind"
    )
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Remove",
        items=[
            ("selected", "Selected Garments", "Only the garments you have selected", 0),
            ("outfit", "All Clothing", "Every garment, footwear kept", 1),
            ("footwear", "All Footwear", "Footwear only", 2),
            ("all", "Everything", "All clothing and footwear", 3),
        ],
        default="selected",
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def _rig(self, context):
        obj = context.active_object
        if obj is None:
            return None
        if obj.type == "ARMATURE":
            return obj
        if obj.parent is not None and obj.parent.type == "ARMATURE":
            return obj.parent
        return find_hg_rigify_rig(obj)

    def _targets(self, context):
        rig = self._rig(context)
        if rig is None:
            return []
        garments = [o for o in rig.children
                    if o.type == "MESH" and ("cloth" in o or "shoe" in o)]
        if self.mode == "selected":
            chosen = [o for o in garments if o.select_get() or o is context.active_object]
            return chosen
        if self.mode == "outfit":
            return [o for o in garments if "cloth" in o]
        if self.mode == "footwear":
            return [o for o in garments if "shoe" in o]
        return garments

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "mode")
        col.separator()
        targets = self._targets(context)
        if not targets:
            box = col.box()
            box.alert = True
            box.label(text="Nothing to remove", icon="ERROR")
            return
        box = col.box()
        box.label(text="Will delete %d object(s):" % len(targets), icon="TRASH")
        for obj in targets:
            box.label(text="   " + obj.name)

    def execute(self, context):
        rig = self._rig(context)
        if rig is None:
            self.report({"ERROR"}, "No Human Generator character found for the active object")
            return {"CANCELLED"}

        targets = self._targets(context)
        if not targets:
            self.report({"WARNING"}, "No clothing matched - nothing removed")
            return {"CANCELLED"}

        body = find_hg_body(rig)
        mask_names = []
        removed = []
        for obj in targets:
            mask_names.extend(find_garment_masks(obj))
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

        dropped = 0
        if body is not None:
            for name in mask_names:
                mod = body.modifiers.get(name)
                if mod is not None and mod.type == "MASK":
                    body.modifiers.remove(mod)
                    dropped += 1

        context.view_layer.objects.active = rig
        bpy.context.view_layer.update()
        self.report(
            {"INFO"},
            "Removed %d garment(s): %s | dropped %d body mask(s)"
            % (len(removed), ", ".join(removed), dropped),
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _draw_clothing_tools(layout, context):
    col = layout.column()
    col.scale_y = 1.35
    col.operator(ARCHEFX_OT_add_as_clothing.bl_idname, icon="MOD_CLOTH")
    col.operator(ARCHEFX_OT_save_clothing_to_library.bl_idname, icon="FILE_NEW")
    col.separator()
    sub = col.column()
    sub.alert = True
    sub.operator(ARCHEFX_OT_remove_clothing.bl_idname, icon="TRASH")


def _draw_rig_tools(layout, context):
    col = layout.column()
    col.scale_y = 1.35
    col.operator(ARCHEFX_OT_rebind_humgen_rigify.bl_idname, icon="GROUP_VERTEX")


def _draw_in_clothing_panel(self, context):
    """Appended to HumGen's Clothing tab. Wrapped so a failure here can never take
    HumGen's own UI down with it."""
    try:
        box = self.layout.box()
        box.label(text="Arche FX", icon="TOOL_SETTINGS")
        _draw_clothing_tools(box, context)
    except Exception:  # noqa: BLE001
        pass


def _draw_in_pose_panel(self, context):
    """Appended to HumGen's Pose tab."""
    try:
        box = self.layout.box()
        box.label(text="Arche FX", icon="TOOL_SETTINGS")
        _draw_rig_tools(box, context)
    except Exception:  # noqa: BLE001
        pass


class ARCHEFX_PT_tools(bpy.types.Panel):
    """Fallback panel, registered only when HumGen's panels cannot be extended."""

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
        _draw_clothing_tools(self.layout, context)
        self.layout.separator()
        _draw_rig_tools(self.layout, context)


_classes = (
    ARCHEFX_OT_rebind_humgen_rigify,
    ARCHEFX_OT_add_as_clothing,
    ARCHEFX_OT_save_clothing_to_library,
    ARCHEFX_OT_remove_clothing,
)

# (HumGen panel idname, draw function) - clothing tools go in the Clothing tab,
# the rig tool in the Pose tab, each where it belongs.
_PANEL_HOOKS = (
    ("HG_PT_CLOTHING", _draw_in_clothing_panel),
    ("HG_PT_POSE", _draw_in_pose_panel),
)

_hooked_panels = []
_fallback_registered = []


def _try_hook_humgen_panels():
    """Add the buttons to HumGen's panels, or fall back to our own tab.

    Deferred on a timer because add-on registration order is not guaranteed --
    HumGen may not have registered its panels yet when we register.
    """
    for idname, draw_func in _PANEL_HOOKS:
        panel = getattr(bpy.types, idname, None)
        if panel is not None:
            panel.append(draw_func)
            _hooked_panels.append((panel, draw_func))

    if not _hooked_panels:
        bpy.utils.register_class(ARCHEFX_PT_tools)
        _fallback_registered.append(True)
    return None  # returning None unregisters the timer


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_try_hook_humgen_panels, first_interval=0.5)


def unregister():
    for panel, draw_func in _hooked_panels:
        try:
            panel.remove(draw_func)
        except Exception:  # noqa: BLE001
            pass
    _hooked_panels.clear()

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
