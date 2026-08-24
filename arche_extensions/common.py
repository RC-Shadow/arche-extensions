# Arche FX HumGen Tools - shared lookups and safety guards.
# Copyright (C) 2026 Arche FX. GPL-3.0-or-later, see LICENSE.
"""Object lookup plus the guards every operator wraps itself in.

Every guard here exists because its absence cost real time:

* `weight_snapshot` - a cleanup pass once wiped all 15 vertex groups off a garment,
  leaving it parented but unskinned.
* `preserve_pose`   - a failure mid-run left the rig at rest and destroyed a hand-made
  pose. Twice.
* `preserve_masks`  - an aborted run left a body MASK modifier switched off; the viewport
  showed skin through the chest and it read as a weighting failure for several rounds.
* `object_mode`     - a leftover WEIGHT_PAINT mode makes `select_all.poll()` fail, and
  `select_set()` silently no-ops on a hidden object, after which Auto-Rig Pro reports
  "Select at least a mesh and the armature".
"""

import contextlib

import bpy

HG_RIGIFY_MARKER = "hg_rigify"

# HumGen skips these when renaming vertex groups during its Rigify conversion.
SKIP_PREFIXES = ("mask", "pin", "def-", "hair", "fh", "sim", "lip")

# A garment must never follow these, whatever a binder decides.
NEVER_BIND = ("head", "jaw", "toe", "eye", "tongue", "teeth", "brow", "cheek",
              "nose", "lip", "chin", "ear")


# --------------------------------------------------------------------------- lookup

def find_hg_rigify_rig(obj):
    """The HumGen Rigify armature related to obj, or None."""
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


def find_rig(obj):
    """Any armature driving obj - Rigify-converted or a stock HumGen rig."""
    if obj is None:
        return None
    if obj.type == "ARMATURE":
        return obj
    for mod in getattr(obj, "modifiers", []):
        if mod.type == "ARMATURE" and mod.object:
            return mod.object
    if obj.parent is not None and obj.parent.type == "ARMATURE":
        return obj.parent
    return find_hg_rigify_rig(obj)


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


def deform_bone_names(rig):
    """Only `use_deform` bones move mesh.

    Do not test against every bone: Rigify carries plain-named *control* bones
    (foot.L, f_index.01.L, eyeball.L) that collide with HumGen's un-prefixed group
    names. On a garment that genuinely did not deform, 37 groups still matched a bone.
    """
    return {b.name for b in rig.data.bones if b.use_deform}


def find_garment_masks(obj):
    """Body MASK modifier names this garment brought with it (HumGen stores mask_0..9)."""
    masks = []
    for i in range(10):
        try:
            masks.append(obj["mask_%d" % i])
        except (KeyError, TypeError):
            break
    return masks


# --------------------------------------------------------------------------- guards

@contextlib.contextmanager
def object_mode(obj=None):
    """Force OBJECT mode for the duration, restoring the previous mode after."""
    ctx = bpy.context
    if obj is not None and ctx.view_layer.objects.active is None:
        ctx.view_layer.objects.active = obj
    active = ctx.view_layer.objects.active
    previous = active.mode if active else "OBJECT"
    if active is not None and previous != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        yield
    finally:
        act = bpy.context.view_layer.objects.active
        if act is not None and previous != "OBJECT" and act.mode != previous:
            with contextlib.suppress(RuntimeError):
                bpy.ops.object.mode_set(mode=previous)


@contextlib.contextmanager
def selection(active, also=()):
    """Make `active` visible, selected and active - and put selection back after."""
    ctx = bpy.context
    prev_active = ctx.view_layer.objects.active
    prev_selected = [o for o in ctx.view_layer.objects if o.select_get()]
    prev_hidden = {}
    try:
        for obj in (active,) + tuple(also):
            if obj is None:
                continue
            prev_hidden[obj] = (obj.hide_viewport, obj.hide_get())
            obj.hide_viewport = False
            obj.hide_set(False)
        for obj in ctx.view_layer.objects:
            obj.select_set(False)
        for obj in (active,) + tuple(also):
            if obj is not None:
                obj.select_set(True)
        ctx.view_layer.objects.active = active
        yield
    finally:
        for obj, (hv, hg) in prev_hidden.items():
            with contextlib.suppress(ReferenceError):
                obj.hide_viewport = hv
                obj.hide_set(hg)
        with contextlib.suppress(ReferenceError, RuntimeError):
            for obj in bpy.context.view_layer.objects:
                obj.select_set(False)
            for obj in prev_selected:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = prev_active


@contextlib.contextmanager
def preserve_pose(rig):
    """Restore every posed bone afterwards, even if the body of the block raises."""
    stash = {}
    if rig is not None:
        identity = None
        for pb in rig.pose.bones:
            if identity is None:
                identity = pb.matrix_basis.Identity(4)
            if pb.matrix_basis != identity:
                stash[pb.name] = (pb.location.copy(),
                                  pb.rotation_quaternion.copy(),
                                  pb.rotation_euler.copy(),
                                  pb.rotation_mode,
                                  pb.scale.copy())
    try:
        yield stash
    finally:
        if rig is not None:
            for name, (loc, quat, euler, mode, scale) in stash.items():
                pb = rig.pose.bones.get(name)
                if pb is None:
                    continue
                pb.rotation_mode = mode
                pb.location = loc
                pb.rotation_quaternion = quat
                pb.rotation_euler = euler
                pb.scale = scale
            bpy.context.view_layer.update()


def clear_pose(rig):
    """Zero every pose bone. Only ever call inside a `preserve_pose` block."""
    for pb in rig.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


@contextlib.contextmanager
def preserve_masks(body, disable=False):
    """Optionally switch the body's MASK modifiers off, always restore them.

    Weight transfer has to sample a body whose arms and torso still exist, so the
    masks come off - but they must come back even on failure.
    """
    saved = []
    if body is not None:
        saved = [(m, m.show_viewport, m.show_render)
                 for m in body.modifiers if m.type == "MASK"]
        if disable:
            for mod, _vp, _rd in saved:
                mod.show_viewport = False
                mod.show_render = False
            # HumGen omits this, and without it a transfer samples masked-away arms
            bpy.context.evaluated_depsgraph_get().update()
    try:
        yield
    finally:
        for mod, show_vp, show_render in saved:
            with contextlib.suppress(ReferenceError):
                mod.show_viewport = show_vp
                mod.show_render = show_render
        bpy.context.evaluated_depsgraph_get().update()


def weight_snapshot(obj):
    """{group_name: {vertex_index: weight}} for restoring after a failed experiment."""
    names = {g.index: g.name for g in obj.vertex_groups}
    snap = {}
    for vert in obj.data.vertices:
        for grp in vert.groups:
            if grp.weight > 1e-6:
                snap.setdefault(names[grp.group], {})[vert.index] = grp.weight
    return snap


def weight_restore(obj, snap):
    """Put weights back exactly as `weight_snapshot` captured them."""
    obj.vertex_groups.clear()
    for name, weights in snap.items():
        vgroup = obj.vertex_groups.new(name=name)
        for index, weight in weights.items():
            vgroup.add([index], weight, "REPLACE")
    bpy.context.view_layer.update()


@contextlib.contextmanager
def weights_guarded(obj):
    """Snapshot weights, and roll them back if the block raises."""
    snap = weight_snapshot(obj)
    try:
        yield snap
    except Exception:
        weight_restore(obj, snap)
        raise
