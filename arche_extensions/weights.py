# Arche FX HumGen Tools - garment skinning.
# Copyright (C) 2026 Arche FX. GPL-3.0-or-later, see LICENSE.
"""Bind a garment to a HumGen character, properly.

Measured on a 29,736-vert shirt against HG_Body, clipping vertices over 7 poses:

    HumGen data_transfer NEAREST + cleanup ... 10,539   (1,482 at rest)
    Auto-Rig Pro pseudo-voxel bind .........,.  3,611     (321 at rest)

HumGen's `_auto_weight_paint` runs a single `data_transfer` with
`vert_mapping="NEAREST"` and no cleanup at all, which leaves 72.9% of vertices with
weights that do not sum to 1, a median of 5 bone influences (the body's is 2) and 58
vertex groups holding no weight.

Auto-Rig Pro's `bind_to_rig()` with the PSEUDO_VOXELS engine works on a *Rigify* rig,
not just ARP rigs, binds in ~16 s, and assigns the twist bones (DEF-upper_arm.L.001)
that surface transfer never touches.
"""

import bpy

from . import common

# Resolution 12 ran for 221 minutes and reached 20.5 GB before it had to be killed.
# ARP's own tooltip: "Low values may sometimes work better than high values depending
# on the mesh complexity."
VOXEL_RES_MIN, VOXEL_RES_MAX, VOXEL_RES_DEFAULT = 3, 8, 7

# Engine '2' binds faster (8.6 s vs 16 s) but produced no usable weights on a real
# garment, so it is deliberately not exposed.
VOXEL_ENGINE = "1"

MAX_INFLUENCES = 4
CHEST_REGION = ("DEF-spine", "DEF-breast", "DEF-neck")
BLEED_PARTS = ("upper_arm", "shoulder")
SMOOTH_GROUPS = ("DEF-upper_arm.R", "DEF-upper_arm.R.001", "DEF-shoulder.R",
                 "DEF-upper_arm.L", "DEF-upper_arm.L.001", "DEF-shoulder.L")


def arp_available():
    return hasattr(bpy.types, "ARP_OT_bind_to_rig")


# --------------------------------------------------------------------- housekeeping

def fill_unweighted(obj):
    """Give every unweighted vertex its nearest weighted neighbour's weights.

    An unweighted vertex ignores the armature completely and tears away from the mesh.
    """
    from mathutils.kdtree import KDTree

    weighted, orphans = [], []
    for vert in obj.data.vertices:
        target = weighted if any(g.weight > 1e-6 for g in vert.groups) else orphans
        target.append(vert.index)
    if not orphans or not weighted:
        return 0
    tree = KDTree(len(weighted))
    for i, index in enumerate(weighted):
        tree.insert(obj.data.vertices[index].co, i)
    tree.balance()
    groups = list(obj.vertex_groups)
    for index in orphans:
        _co, nearest, _dist = tree.find(obj.data.vertices[index].co)
        for grp in obj.data.vertices[weighted[nearest]].groups:
            if grp.weight > 1e-6:
                groups[grp.group].add([index], grp.weight, "REPLACE")
    return len(orphans)


def purge_groups(obj, deform_bones):
    """Drop groups holding no weight, non-deform junk, and bones a garment must not follow."""
    live = {g.group for v in obj.data.vertices for g in v.groups if g.weight > 0.001}
    doomed = [g for g in obj.vertex_groups
              if g.index not in live
              or g.name not in deform_bones
              or any(t in g.name.lower() for t in common.NEVER_BIND)]
    names = [g.name for g in doomed]
    for group in doomed:
        obj.vertex_groups.remove(group)
    return names


def normalize(obj):
    """Bring every vertex to a total weight of exactly 1.0.

    Blender's `vertex_group_normalize_all` operator has been seen to leave vertices at
    2.0, so this does it directly.
    """
    groups = list(obj.vertex_groups)
    indices = {g.index for g in obj.vertex_groups}
    fixed = 0
    for vert in obj.data.vertices:
        total = sum(g.weight for g in vert.groups
                    if g.group in indices and g.weight > 1e-6)
        if total <= 1e-9 or abs(total - 1.0) <= 1e-4:
            continue
        for grp in list(vert.groups):
            if grp.group in indices and grp.weight > 1e-6:
                groups[grp.group].add([vert.index], grp.weight / total, "REPLACE")
        fixed += 1
    return fixed


def limit_influences(obj, limit=MAX_INFLUENCES):
    with common.selection(obj):
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=limit)


# ------------------------------------------------------------------------ de-bleed

def debleed_chest(obj, threshold):
    """Strip arm/shoulder bleed off torso vertices.

    This is Auto-Rig Pro's own pattern from `bind_improve_weights` (auto_rig.py ~20080),
    where they clean arm and hand bleed off *head* vertices:

        remove_other_parts = ["thumb","hand","index",...,"arm_","forearm","shoulder_bend"]
        if part in group_name and is_in_head_group:
            cur_vgroup.add([vert.index], 0.00, 'REPLACE')

    Same test, region pointed at the chest. ARP's 0.1 threshold is tuned for the head,
    which sits far from the arm; the chest abuts the shoulder, so this is a slider.
    Gentle (0.10) took a measured chest travel ratio from 5.01 to 2.59 with the sleeve
    untouched at 1.05. Pushing to 0.03 reached 2.03 but created a hard weight seam that
    tore the armpit open under a big arm raise.
    """
    names = {g.index: g.name for g in obj.vertex_groups}
    groups = list(obj.vertex_groups)
    touched = stripped = 0
    for vert in obj.data.vertices:
        in_chest = False
        for grp in vert.groups:
            name = names.get(grp.group, "")
            if any(name.startswith(r) for r in CHEST_REGION) and grp.weight > threshold:
                in_chest = True
                break
        if not in_chest:
            continue
        hit = False
        for grp in list(vert.groups):
            name = names.get(grp.group, "")
            if any(part in name for part in BLEED_PARTS) and grp.weight > 0.0:
                groups[grp.group].add([vert.index], 0.00, "REPLACE")
                stripped += 1
                hit = True
        if hit:
            touched += 1
    return touched, stripped


def smooth_boundary(obj, group_names=SMOOTH_GROUPS, factor=0.5, repeat=4):
    """Soften the seam de-bleeding leaves, using ARP's own per-group smooth.

    Their 'smooth neck' block uses `group_select_mode='ACTIVE'` - one group at a time.
    Never use 'ALL': smoothing every group at once collapsed influences to a median of
    1 bone per vertex against the body's 2.
    """
    done = 0
    for name in group_names:
        vgroup = obj.vertex_groups.get(name)
        if vgroup is None:
            continue
        with common.object_mode(obj), common.selection(obj):
            obj.vertex_groups.active_index = vgroup.index
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
            try:
                obj.data.use_paint_mask_vertex = True
                bpy.ops.paint.vert_select_all(action="SELECT")
                bpy.ops.object.vertex_group_smooth(group_select_mode="ACTIVE",
                                                   factor=factor, repeat=repeat,
                                                   expand=0.0)
                bpy.ops.paint.vert_select_all(action="DESELECT")
            finally:
                obj.data.use_paint_mask_vertex = False
                bpy.ops.object.mode_set(mode="OBJECT")
        done += 1
    return done


# ---------------------------------------------------------------------- the binders

def arp_bind(obj, rig, resolution=VOXEL_RES_DEFAULT):
    """Auto-Rig Pro's pseudo-voxel bind. Returns seconds taken."""
    import time

    scene = bpy.context.scene
    resolution = max(VOXEL_RES_MIN, min(VOXEL_RES_MAX, int(resolution)))
    previous = {}
    for key, value in (("arp_bind_engine", "PSEUDO_VOXELS"),
                       ("arp_pseudo_voxels_type", VOXEL_ENGINE),
                       ("arp_pseudo_voxels_resolution", resolution),
                       ("arp_bind_apply_sk", False)):   # or corrective keys get baked
        if hasattr(scene, key):
            previous[key] = getattr(scene, key)
            setattr(scene, key, value)
    started = time.time()
    try:
        # ARP reads the ACTIVE object as the armature, and select_set() is a silent
        # no-op on a hidden object
        with common.object_mode(obj), common.selection(rig, also=(obj,)):
            bpy.ops.arp.bind_to_rig()
    finally:
        for key, value in previous.items():
            setattr(scene, key, value)
    return time.time() - started


def surface_bind(obj, body, rig):
    """Fallback when Auto-Rig Pro is not installed.

    POLYINTERP_NEAREST interpolates across the nearest body face rather than snapping
    to one vertex. POLYINTERP_VNORPROJ scored better on drift but shoots a ray along
    each vertex normal, which on a thick closed garment lands on unrelated body parts -
    it produced 27 implausible groups including toes and finger bones.
    """
    obj.vertex_groups.clear()
    for vert in obj.data.vertices:
        vert.select = True
    with common.preserve_masks(body, disable=True):
        with common.object_mode(obj), common.selection(body, also=(obj,)):
            bpy.ops.object.data_transfer(
                data_type="VGROUP_WEIGHTS", use_create=True,
                vert_mapping="POLYINTERP_NEAREST",
                layers_select_src="ALL", layers_select_dst="NAME",
                mix_mode="REPLACE",
            )


def bind_garment(obj, rig, body, resolution=VOXEL_RES_DEFAULT,
                 debleed_threshold=0.10, use_debleed=True):
    """Full pipeline. Returns a dict of what happened, for the operator to report."""
    deform = common.deform_bone_names(rig)
    report = {"engine": "arp", "seconds": 0.0}

    with common.weights_guarded(obj):
        if arp_available():
            report["seconds"] = arp_bind(obj, rig, resolution)
        else:
            report["engine"] = "surface"
            surface_bind(obj, body, rig)

        with common.object_mode(obj), common.selection(obj):
            limit_influences(obj)
        report["purged"] = len(purge_groups(obj, deform))
        report["filled"] = fill_unweighted(obj)
        normalize(obj)

        if use_debleed:
            touched, stripped = debleed_chest(obj, debleed_threshold)
            report["debleed_verts"] = touched
            report["debleed_weights"] = stripped
            smooth_boundary(obj)
            purge_groups(obj, deform)
            fill_unweighted(obj)
            normalize(obj)

        bpy.context.view_layer.update()

    report.update(audit(obj, rig))
    return report


def audit(obj, rig):
    """Numbers worth reporting: sums, influences, dead groups."""
    deform = common.deform_bone_names(rig)
    indices = {g.index for g in obj.vertex_groups if g.name in deform}
    sums, counts = [], []
    for vert in obj.data.vertices:
        total, count = 0.0, 0
        for grp in vert.groups:
            if grp.group in indices and grp.weight > 1e-6:
                total += grp.weight
                count += 1
        sums.append(total)
        counts.append(count)
    if not sums:
        return {"groups": 0, "unweighted": 0, "sum_min": 0.0, "sum_max": 0.0,
                "bones_med": 0, "bones_max": 0, "off_normal": 0}
    ordered, tallies = sorted(sums), sorted(counts)
    return {
        "groups": len(obj.vertex_groups),
        "unweighted": sum(1 for s in sums if s <= 1e-6),
        "sum_min": ordered[0],
        "sum_max": ordered[-1],
        "bones_med": tallies[len(tallies) // 2],
        "bones_max": tallies[-1],
        "off_normal": sum(1 for s in sums if not 0.99 <= s <= 1.01),
    }
