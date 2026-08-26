# Arche Extensions - clothing operators.
# Copyright (C) 2026 Arche FX. GPL-3.0-or-later, see LICENSE.
"""Add a mesh as clothing, save one garment to the library, remove clothing.

These wrap Human Generator's own API rather than reimplementing it - A-pose correction
and corrective shape keys are hundreds of lines of well-tested vendor code. HumGen is
imported lazily so the add-on still registers (and the Rigify re-bind still works)
without it.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from . import common, weights

# Keys of HumGen's corrective_sk_names_v2.json. Note outfit.add_obj's docstring says
# "top", but the JSON key is "torso" and passing "top" raises KeyError.
CLOTH_TYPE_ITEMS = [
    ("torso", "Torso", "Shirt, jacket, top - adds elbow and shoulder corrective keys", 0),
    ("pants", "Pants", "Trousers, skirt - adds leg raise and foot down corrective keys", 1),
    ("full", "Full Body", "Dress, overall - adds both arm and leg corrective keys", 2),
    ("footwear", "Footwear", "Shoes, boots - adds foot down corrective keys", 3),
]


def humgen_human(obj):
    """(Human, error_message). Human is None when it cannot be resolved."""
    try:
        from HumGen3D.human.human import Human
    except Exception:  # noqa: BLE001
        return None, "Human Generator is not installed or not enabled"
    try:
        from HumGen3D.human.clothing.add_obj_to_clothing import get_human_from_distance

        human = get_human_from_distance(obj)
        if human:
            return human, ""
    except Exception:  # noqa: BLE001
        pass
    for candidate in (obj.parent, common.find_hg_rigify_rig(obj)):
        if candidate is None:
            continue
        try:
            human = Human.from_existing(candidate)
            if human:
                return human, ""
        except Exception:  # noqa: BLE001
            continue
    return None, ("Could not find a Human Generator character for this object. Move it "
                  "onto the character, or parent it to the character's rig.")


class ARCHEFX_OT_bind_weights(bpy.types.Operator):
    """Re-derive this garment's weights from the character"""

    bl_idname = "archefx.bind_weights"
    bl_label = "Bind Weights"
    bl_description = (
        "Skin this garment to the character: Auto-Rig Pro voxel bind (bone heat, then "
        "surface transfer, when ARP is missing), cap influences, drop dead and far-away "
        "groups, remove arm bleed from the chest, normalise, then add a body-collision "
        "guard so the garment can never sink into the skin. Body masks are never "
        "touched. Safe to run more than once"
    )
    bl_options = {"REGISTER", "UNDO"}

    clip_fix: EnumProperty(
        name="Clipping Fix",
        description="How skin is kept from showing through the garment",
        items=[
            ("mask", "Hide skin under cloth (mask)",
             "MASK modifier on the body over the skin this garment covers, with a "
             "margin inside its open edges. The garment mesh is never touched - what "
             "HumGen's own library garments do", 0),
            ("guard", "Push cloth outside skin (shrinkwrap)",
             "Shrinkwrap after the armature. Works on loose garments; on a dense "
             "body-hugging mesh it visibly deforms the cloth", 1),
            ("none", "None", "Weights only", 2),
        ],
        default="mask",
    )
    guard_offset: bpy.props.FloatProperty(
        name="Guard Offset",
        description="How far above the skin the garment is held",
        default=0.004, min=0.001, max=0.02, step=0.1, precision=3, unit="LENGTH",
    )
    mask_depth: bpy.props.FloatProperty(
        name="Mask Depth",
        description="Skin this far under the cloth counts as covered",
        default=0.03, min=0.005, max=0.10, step=0.5, precision=3, unit="LENGTH",
    )
    mask_edge_margin: bpy.props.FloatProperty(
        name="Edge Margin",
        description="Skin within this distance of the garment's open edges (collar, "
                    "cuffs, hem) stays visible, so no gap opens past the cloth",
        default=0.01, min=0.0, max=0.10, step=0.5, precision=3, unit="LENGTH",
    )
    use_corrective_keys: BoolProperty(
        name="Copy Body Corrective Keys",
        description="Give the garment the body's pose-driven corrective shape keys "
                    "(elbow, shoulder, leg) with the same drivers, so it bulges with the "
                    "skin instead of letting it through",
        default=True,
    )
    prefer_body_weights: BoolProperty(
        name="Body Weights for Hugging Garments",
        description="When the garment sits on the skin (median distance < 1.5 cm), copy "
                    "the body's own weights first - identical deformation, nothing to "
                    "clip. Otherwise ARP / bone heat",
        default=True,
    )
    use_proximity: BoolProperty(
        name="Drop Far-Away Bones",
        description="Remove groups whose bone lies nowhere near this mesh (e.g. jaw on a "
                    "shirt). Distance only, no bone names",
        default=True,
    )
    verify_frames: BoolProperty(
        name="Verify Every Frame",
        description="After binding, count vertices inside the body on every frame of "
                    "the scene range and report it. Slow on big garments",
        default=True,
    )
    resolution: IntProperty(
        name="Voxel Detail",
        description="Auto-Rig Pro voxel precision. Higher is slower, and NOT always "
                    "better - ARP warns low values often win on complex meshes",
        default=weights.VOXEL_RES_DEFAULT,
        min=weights.VOXEL_RES_MIN, max=weights.VOXEL_RES_MAX,
    )
    use_debleed: BoolProperty(
        name="Remove Arm Bleed from Chest",
        description="Strip upper_arm/shoulder weight off torso vertices so the chest "
                    "does not slosh when an arm moves",
        default=True,
    )
    debleed_threshold: bpy.props.FloatProperty(
        name="Bleed Threshold",
        description="How much torso weight marks a vertex as chest. Lower strips more; "
                    "below about 0.05 it can create a hard seam at the armpit",
        default=0.10, min=0.01, max=0.50,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "resolution")
        if not weights.arp_available():
            box = col.box()
            box.label(text="Auto-Rig Pro not found", icon="INFO")
            box.label(text="Using bone heat, then surface transfer.")
        col.separator()
        col.prop(self, "prefer_body_weights")
        col.prop(self, "use_corrective_keys")
        col.prop(self, "clip_fix")
        sub = col.column()
        if self.clip_fix == "guard":
            sub.prop(self, "guard_offset")
        elif self.clip_fix == "mask":
            sub.prop(self, "mask_depth")
            sub.prop(self, "mask_edge_margin")
        col.prop(self, "use_proximity")
        col.separator()
        col.prop(self, "use_debleed")
        sub = col.column()
        sub.enabled = self.use_debleed
        sub.prop(self, "debleed_threshold")
        col.separator()
        col.prop(self, "verify_frames")
        col.label(text="Body masks are not modified.", icon="CHECKMARK")

    def execute(self, context):
        obj = context.active_object
        rig = common.find_rig(obj)
        if rig is None:
            self.report({"ERROR"}, "No armature found for this object")
            return {"CANCELLED"}
        body = common.find_body(rig, exclude=obj)

        try:
            with common.preserve_pose(rig) as stash:
                if stash:
                    common.clear_pose(rig)
                with common.preserve_masks(body):
                    report = weights.bind_garment(
                        obj, rig, body,
                        resolution=self.resolution,
                        debleed_threshold=self.debleed_threshold,
                        use_debleed=self.use_debleed,
                        use_proximity=self.use_proximity,
                        clip_fix=self.clip_fix,
                        guard_offset=self.guard_offset,
                        mask_depth=self.mask_depth,
                        mask_edge_margin=self.mask_edge_margin,
                        prefer_body_weights=self.prefer_body_weights,
                        use_corrective_keys=self.use_corrective_keys,
                        verify_frames=self.verify_frames,
                    )
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, "Bind failed, weights rolled back: %s" % exc)
            return {"CANCELLED"}

        msg = format_report(report, body)
        bad = report["unweighted"] or report["off_normal"] or report.get("clip_max", 0) > 30
        self.report({"WARNING" if bad else "INFO"}, msg)
        return {"FINISHED"}


def format_report(report, body):
    """One line for the status bar, everything a user needs to judge the bind."""
    msg = ("%s bind %.1fs | %d groups | %d unweighted | bones/vert med %d max %d"
           % (report["engine"], report["seconds"], report["groups"],
              report["unweighted"], report["bones_med"], report["bones_max"]))
    if report.get("hugs_body"):
        msg += " | hugs the body"
    if report.get("clip_fix") == "mask":
        msg += " | masked %d skin verts" % report.get("masked", 0)
    elif report.get("clip_fix") == "guard":
        msg += " | shrinkwrap guard"
    if report.get("corrective_keys"):
        msg += " | %d corrective keys" % len(report["corrective_keys"])
    if report.get("warn_smooth"):
        msg += (" | WARNING: Corrective Smooth '%s' pulls the cloth off the skin - "
                "lower its factor or disable it" % report["warn_smooth"])
    far = report.get("far_purged")
    if far:
        msg += " | dropped far bones: " + ", ".join(far)
    if report.get("tried"):
        msg += " | skipped: " + "; ".join(report["tried"])
    if body is None:
        msg += " | no body found: no guard, not verified"
    elif "clip_mean" in report:
        msg += (" | inside body over %d frames: mean %.0f max %d (f%d) worst %.1fcm"
                % (report["clip_frames"], report["clip_mean"], report["clip_max"],
                   report["clip_max_frame"], report["clip_worst_cm"]))
    return msg


class ARCHEFX_OT_mask_skin(bpy.types.Operator):
    """Hide the body's skin under this garment (no re-bind, weights untouched)"""

    bl_idname = "archefx.mask_skin"
    bl_label = "Mask Skin Under Garment"
    bl_description = (
        "Add a MASK modifier on the body hiding the skin this garment covers, with a "
        "margin inside the garment's open edges. Removes this garment's shrinkwrap "
        "guard if it has one. Weights are not changed. Safe to run more than once"
    )
    bl_options = {"REGISTER", "UNDO"}

    mask_depth: bpy.props.FloatProperty(
        name="Depth Under Cloth", default=0.04, min=0.005, max=0.15, step=0.5,
        precision=3, unit="LENGTH",
        description="Skin this far beneath the cloth counts as covered")
    poke_depth: bpy.props.FloatProperty(
        name="Buried Panel Reach", default=0.08, min=0.0, max=0.20, step=0.5,
        precision=3, unit="LENGTH",
        description="Skin above a garment panel modelled up to this far INSIDE the "
                    "body also counts as covered")
    mask_edge_margin: bpy.props.FloatProperty(
        name="Edge Margin", default=0.01, min=0.0, max=0.10, step=0.5, precision=3,
        unit="LENGTH",
        description="Skin within this distance of the garment's open edges (collar, "
                    "cuffs, hem) stays visible")
    remove_guard: BoolProperty(name="Remove Shrinkwrap Guard", default=True)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def execute(self, context):
        obj = context.active_object
        rig = common.find_rig(obj)
        body = common.find_body(rig, exclude=obj) if rig else None
        if body is None:
            self.report({"ERROR"}, "No body mesh found under this garment's rig")
            return {"CANCELLED"}
        if self.remove_guard:
            weights.remove_guard(obj)
        with common.preserve_pose(rig) as stash:
            if stash:
                common.clear_pose(rig)
            count = weights.add_body_mask(obj, body, depth=self.mask_depth,
                                          poke_depth=self.poke_depth,
                                          edge_margin=self.mask_edge_margin)
        if not count:
            self.report({"WARNING"}, "No skin found under '%s'" % obj.name)
            return {"CANCELLED"}
        self.report({"INFO"}, "Masked %d skin vertices under '%s' on %s"
                    % (count, obj.name, body.name))
        return {"FINISHED"}


class ARCHEFX_OT_add_as_clothing(bpy.types.Operator):
    """Turn the selected mesh into clothing on this Human Generator character"""

    bl_idname = "archefx.add_as_clothing"
    bl_label = "Add to Character Clothing"
    bl_description = (
        "Turn the active mesh into clothing on the Human Generator character it sits "
        "on: A-pose correction, corrective shape keys and their drivers, then a proper "
        "weight bind"
    )
    bl_options = {"REGISTER", "UNDO"}

    cloth_type: EnumProperty(
        name="Type",
        description="What part of the body this covers - decides which corrective "
                    "shape keys are added",
        items=CLOTH_TYPE_ITEMS, default="torso",
    )
    recalculate_weights: BoolProperty(
        name="Bind Weights",
        description="Run the full weight bind after adding. Turn off only if you "
                    "already weighted this yourself",
        default=True,
    )
    fit: EnumProperty(
        name="Fit",
        description="Whether Human Generator may reshape the mesh",
        items=[
            ("tag", "Tag only (already fitted)",
             "Mark as this character's clothing and bind. The mesh is not moved. Use "
             "for anything modelled or fitted on THIS character", 0),
            ("humgen", "HumGen fitting (default-body garment)",
             "Human Generator's own add: A-pose correction, body-proportion and "
             "corrective shape keys. Only for a garment built on the DEFAULT HumGen "
             "body - on a mesh already fitted to the character it moved a shirt "
             "14 cm up and 30 cm forward", 1),
        ],
        default="tag",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "cloth_type")
        col.prop(self, "fit")
        col.prop(self, "recalculate_weights")
        obj = context.active_object
        if obj and ("cloth" in obj or "shoe" in obj):
            box = col.box()
            box.label(text="Already clothing - this will redo it", icon="INFO")

    def execute(self, context):
        cloth_obj = context.active_object
        human, err = humgen_human(cloth_obj)
        if human is None:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        body = getattr(human.objects, "body", None)
        rig_obj = getattr(human.objects, "rig", None) or common.find_rig(cloth_obj)
        if self.fit == "tag":
            # Mark it the way HumGen marks its own clothing and put it under the rig
            # with its world transform intact. Nothing about the mesh changes.
            tag = "shoe" if self.cloth_type == "footwear" else "cloth"
            cloth_obj[tag] = 1
            if rig_obj is not None and cloth_obj.parent is not rig_obj:
                world = cloth_obj.matrix_world.copy()
                cloth_obj.parent = rig_obj
                cloth_obj.matrix_world = world
            if rig_obj is not None and not any(
                    m.type == "ARMATURE" and m.object is rig_obj
                    for m in cloth_obj.modifiers):
                mod = cloth_obj.modifiers.new("Armature", "ARMATURE")
                mod.object = rig_obj
                cloth_obj.modifiers.move(len(cloth_obj.modifiers) - 1, 0)
            context.view_layer.update()
        else:
            # HumGen samples the body with its masks off but never forces a depsgraph
            # update first, so in background runs it samples masked-away arms. It also
            # switches every mask back ON afterwards regardless of how you had them.
            # It re-parents assuming the object had no parent (an already-parented
            # shirt landed 17 m from the body), so hand it an unparented object and
            # put the world transform back afterwards.
            world_before = cloth_obj.matrix_world.copy()
            if cloth_obj.parent is not None:
                with common.object_mode(cloth_obj), common.selection(cloth_obj):
                    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
            try:
                with common.preserve_masks(body, disable=True):
                    if self.cloth_type == "footwear":
                        human.clothing.footwear.add_obj(cloth_obj, False, context)
                    else:
                        human.clothing.outfit.add_obj(cloth_obj, self.cloth_type,
                                                      False, context)
            except Exception as exc:  # noqa: BLE001
                self.report({"ERROR"}, "Human Generator could not add this: %s" % exc)
                return {"CANCELLED"}
            finally:
                cloth_obj.matrix_world = world_before
                context.view_layer.update()

        msg = "Added '%s' as %s clothing" % (cloth_obj.name, self.cloth_type)
        rig = common.find_rig(cloth_obj)
        if rig is not None:
            from .rigify import rebind_drivers
            rebind_drivers(cloth_obj, rig)
            if self.recalculate_weights:
                try:
                    with common.preserve_pose(rig) as stash:
                        if stash:
                            common.clear_pose(rig)
                        # masks HumGen just added stay as they are: the guard has to
                        # collide with the body exactly as it will render
                        report = weights.bind_garment(cloth_obj, rig, body,
                                                      verify_frames=False)
                    msg += " | " + format_report(report, body)
                except Exception as exc:  # noqa: BLE001
                    self.report({"WARNING"},
                                "Added, but the weight bind failed: %s" % exc)
                    return {"FINISHED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class ARCHEFX_OT_save_clothing_to_library(bpy.types.Operator):
    """Save this garment into the Human Generator clothing library"""

    bl_idname = "archefx.save_clothing_to_library"
    bl_label = "Add to Clothing Asset Library"
    bl_description = (
        "Save this garment to the Human Generator library so it can be loaded onto any "
        "future character. By default only the active garment is saved, not the whole "
        "outfit"
    )
    bl_options = {"REGISTER"}

    name: StringProperty(name="Name", default="")
    category: StringProperty(name="Category", default="Custom")
    for_male: BoolProperty(name="For Male", default=True)
    for_female: BoolProperty(name="For Female", default=True)
    only_this_object: BoolProperty(
        name="Only This Garment",
        description="HumGen saves an outfit as a set - every object tagged as clothing "
                    "at once. Leave this on to save just the active garment",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH"
                and ("cloth" in obj or "shoe" in obj))

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
        human, err = humgen_human(cloth_obj)
        if human is None:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        is_shoe = "shoe" in cloth_obj
        tag = "shoe" if is_shoe else "cloth"
        settings = human.clothing.footwear if is_shoe else human.clothing.outfit

        stashed = []
        if self.only_this_object:
            for obj in self._siblings(cloth_obj):
                stashed.append((obj, obj[tag]))
                del obj[tag]

        # is_valid_clothing_object requires the garment to carry EVERY vertex group the
        # body has. We deliberately delete the dead ones, so re-create them empty for
        # the save and take them away again.
        body = getattr(human.objects, "body", None)
        added = []
        if body is not None:
            have = {g.name for g in cloth_obj.vertex_groups}
            for group in body.vertex_groups:
                if group.name not in have:
                    cloth_obj.vertex_groups.new(name=group.name)
                    added.append(group.name)
        try:
            settings.save_to_library(
                self.name.strip(), for_male=self.for_male, for_female=self.for_female,
                open_when_finished=False,
                category=self.category.strip() or "Custom",
                thumbnail=None, context=context,
            )
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, "Human Generator could not save this: %s" % exc)
            return {"CANCELLED"}
        finally:
            for obj, value in stashed:
                obj[tag] = value
            for name in added:
                vgroup = cloth_obj.vertex_groups.get(name)
                if vgroup is not None:
                    cloth_obj.vertex_groups.remove(vgroup)

        self.report({"INFO"}, "Saved '%s' to the %s library under '%s'"
                    % (self.name.strip(), "footwear" if is_shoe else "outfit",
                       self.category))
        return {"FINISHED"}


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
        items=[("selected", "Selected Garments", "Only the garments you have selected", 0),
               ("outfit", "All Clothing", "Every garment, footwear kept", 1),
               ("footwear", "All Footwear", "Footwear only", 2),
               ("all", "Everything", "All clothing and footwear", 3)],
        default="selected",
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def _targets(self, context):
        rig = common.find_rig(context.active_object)
        if rig is None:
            return []
        garments = [o for o in rig.children
                    if o.type == "MESH" and ("cloth" in o or "shoe" in o)]
        if self.mode == "selected":
            return [o for o in garments
                    if o.select_get() or o is context.active_object]
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
        box = col.box()
        if not targets:
            box.alert = True
            box.label(text="Nothing to remove", icon="ERROR")
            return
        box.label(text="Will delete %d object(s):" % len(targets), icon="TRASH")
        for obj in targets:
            box.label(text="   " + obj.name)

    def execute(self, context):
        rig = common.find_rig(context.active_object)
        if rig is None:
            self.report({"ERROR"}, "No Human Generator character found")
            return {"CANCELLED"}
        targets = self._targets(context)
        if not targets:
            self.report({"WARNING"}, "No clothing matched - nothing removed")
            return {"CANCELLED"}

        body = common.find_hg_body(rig)
        mask_names, removed = [], []
        for obj in targets:
            mask_names.extend(common.find_garment_masks(obj))
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
        self.report({"INFO"}, "Removed %d garment(s): %s | dropped %d body mask(s)"
                    % (len(removed), ", ".join(removed), dropped))
        return {"FINISHED"}


classes = (
    ARCHEFX_OT_bind_weights,
    ARCHEFX_OT_mask_skin,
    ARCHEFX_OT_add_as_clothing,
    ARCHEFX_OT_save_clothing_to_library,
    ARCHEFX_OT_remove_clothing,
)
