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
    """Drop groups holding no weight on this mesh, and non-deform junk.

    Only those two tests. No name blacklist: a shoe needs DEF-toe, and a substring
    list ("ear") silently stripped DEF-forearm off every sleeve.
    """
    live = {g.group for v in obj.data.vertices for g in v.groups if g.weight > 0.001}
    doomed = [g for g in obj.vertex_groups
              if g.index not in live
              or g.name not in deform_bones]
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


def heat_bind(obj, rig):
    """Blender's bone-heat automatic weights. The fallback when Auto-Rig Pro is absent.

    `parent_set(ARMATURE_AUTO)` adds a second Armature modifier; the original is kept
    and the new one removed so the stack order the user built is untouched. Bone heat
    can fail on non-manifold meshes - it then warns and leaves vertices unweighted,
    which the engine ladder in `bind_garment` treats as a miss.
    """
    import time

    obj.vertex_groups.clear()
    before = {m.name for m in obj.modifiers if m.type == "ARMATURE"}
    started = time.time()
    with common.object_mode(obj), common.selection(rig, also=(obj,)):
        bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)
    if before:
        for mod in [m for m in obj.modifiers
                    if m.type == "ARMATURE" and m.name not in before]:
            obj.modifiers.remove(mod)
    return time.time() - started


# -------------------------------------------------------------- proximity + guard

def purge_far_groups(obj, rig, body=None, margin=None, min_fraction=0.05):
    """Drop groups whose bone drives no skin near this mesh - by distance, never by name.

    ARP's voxel bind put DEF-jaw on 501 vertices of a shirt, bone heat on 642. With a
    body: a bone is "near" when at least `min_fraction` of the body vertices it drives
    (weight > 0.25) lie within `margin` of the garment. Jaw skin is on the chin, far
    from a collar - dropped; neck, spine and breast skin sits under the shirt - kept.
    Without a body: the bone segment is sampled every 2 cm against the garment
    surface, and a sample lying *inside* the shell counts as touching (a spine bone is
    10 cm from a shirt's vertices yet obviously drives it).
    `margin` defaults to 5 % of the garment's bounding-box diagonal, never under 3 cm.
    Returns the names removed.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree

    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not verts:
        return []
    lo = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
    hi = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
    if margin is None:
        margin = max(0.03, 0.05 * (hi - lo).length)
    tree = KDTree(len(verts))
    for i, co in enumerate(verts):
        tree.insert(co, i)
    tree.balance()

    skin = {}
    if body is not None and body is not obj:
        wanted = {g.name for g in obj.vertex_groups}
        by_name = {g.index: g.name for g in body.vertex_groups if g.name in wanted}
        coords = common.rest_coords(body)
        for vert in body.data.vertices:
            for grp in vert.groups:
                if grp.group in by_name and grp.weight > 0.25:
                    skin.setdefault(by_name[grp.group], []).append(coords[vert.index])

    bones, world = rig.data.bones, rig.matrix_world
    body_groups = ({g.name for g in body.vertex_groups}
                   if body is not None and body is not obj else None)
    bvh = None
    doomed = []
    for group in list(obj.vertex_groups):
        points = skin.get(group.name)
        if points:
            near = sum(1 for p in points if tree.find(p)[2] <= margin)
            if near < min_fraction * len(points):
                doomed.append(group)
            continue
        if body_groups is not None and group.name not in body_groups:
            # the skin itself never follows this bone (HumGen has no DEF-jaw group),
            # so the garment over it must not either - ARP's voxel leak put it on
            # 637 shirt vertices
            doomed.append(group)
            continue
        # no body: test the bone itself against the garment surface
        bone = bones.get(group.name)
        if bone is None:
            continue
        if bvh is None:
            bvh = BVHTree.FromPolygons(
                [v.to_tuple() for v in verts],
                [tuple(p.vertices) for p in obj.data.polygons], all_triangles=False)
        head, tail = world @ bone.head_local, world @ bone.tail_local
        steps = max(2, int((tail - head).length / 0.02) + 1)
        best = None
        for i in range(steps):
            point = head.lerp(tail, i / (steps - 1))
            loc, normal, _index, dist = bvh.find_nearest(point)
            if loc is None:
                continue
            if (point - loc).dot(normal) < 0:
                dist = 0.0    # inside the shell
            best = dist if best is None else min(best, dist)
        if best is not None and best > margin:
            doomed.append(group)
    names = [g.name for g in doomed]
    for group in doomed:
        obj.vertex_groups.remove(group)
    return names


GUARD_NAME = "ArcheFX_Guard"


def add_guard(obj, body, offset=0.004):
    """Shrinkwrap the garment to stay outside the body, right after the Armature modifier.

    Measured on a 3,281-vert shirt modelled partly *inside* the skin: every weighting
    engine left ~800 vertices inside the body per frame (the raw mesh already had 769
    at rest). With this guard: mean 4, max 18, worst 0.4 cm. Weights cannot fix
    geometry; this can. Idempotent - re-running updates the existing modifier.
    """
    if body is None or body is obj:
        return None
    mod = obj.modifiers.get(GUARD_NAME)
    if mod is not None and mod.type != "SHRINKWRAP":
        obj.modifiers.remove(mod)
        mod = None
    if mod is None:
        mod = obj.modifiers.new(GUARD_NAME, "SHRINKWRAP")
    mod.target = body
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    mod.wrap_mode = "OUTSIDE_SURFACE"
    mod.offset = offset
    mod.show_expanded = False

    # LAST in the stack. Directly after the Armature modifier a Subsurf that follows
    # pulls the surface back inside: a shoe measured 164 vertices inside the foot with
    # the guard after the armature, 1 with the guard last.
    last = len(obj.modifiers) - 1
    current = obj.modifiers.find(mod.name)
    if current != last:
        obj.modifiers.move(current, last)
    return mod


MASK_PREFIX = "ArcheFX_Mask_"


def garment_boundary(obj):
    """World-space points along the garment's open edges (collar, cuffs, hem)."""
    from collections import Counter
    count = Counter()
    for poly in obj.data.polygons:
        for key in poly.edge_keys:
            count[key] += 1
    verts = obj.data.vertices
    pts = []
    for (a, b), n in count.items():
        if n == 1:
            pa, pb = obj.matrix_world @ verts[a].co, obj.matrix_world @ verts[b].co
            pts.append(pa)
            pts.append((pa + pb) * 0.5)
    return pts


def hugs_body(obj, body, limit=0.015):
    """True when the garment follows the skin closely (median rest distance < limit):
    then the body's own weights are the best possible weights for it."""
    from mathutils.bvhtree import BVHTree
    coords = common.rest_coords(body)
    bvh = BVHTree.FromPolygons([c.to_tuple() for c in coords],
                               [tuple(p.vertices) for p in body.data.polygons],
                               all_triangles=False)
    dists = []
    for vert in obj.data.vertices:
        loc, _n, _i, dist = bvh.find_nearest(obj.matrix_world @ vert.co)
        if loc is not None:
            dists.append(dist)
    if not dists:
        return False
    dists.sort()
    return dists[len(dists) // 2] < limit


def add_body_mask(obj, body, depth=0.04, poke_depth=0.08, edge_margin=0.01, grow=1):
    """Hide the skin under the garment - the fix that never touches the garment mesh.

    The Shrinkwrap guard pushed a dense body-hugging shirt around ("destroyed mesh");
    with it off, any hand raise showed skin through the cloth. This is what Human
    Generator's own library garments do instead: a MASK modifier on the body over a
    vertex group of the covered skin. A skin vertex is covered when a ray along its
    normal meets the garment within `depth` in FRONT of it (skin under the cloth), or
    within `poke_depth` BEHIND it (a panel modelled inside the body - the TSA shirt
    sat 6.3 cm deep, which a nearest-point test never reached). Hits within
    `edge_margin` of the garment's open edges (collar, cuffs, hem) do not count, so
    the cut line always sits under the cloth and no ring of skin is lost past it.
    `grow` rings of neighbours close pinholes. Idempotent per garment. Also writes
    obj["mask_N"] the way HumGen does, so Remove Clothing cleans it up.
    """
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree

    if body is None or body is obj or not obj.data.polygons:
        return None
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    bvh = BVHTree.FromPolygons([v.to_tuple() for v in verts],
                               [tuple(p.vertices) for p in obj.data.polygons],
                               all_triangles=False)
    edge_pts = garment_boundary(obj)
    edges = None
    if edge_pts:
        edges = KDTree(len(edge_pts))
        for i, p in enumerate(edge_pts):
            edges.insert(p, i)
        edges.balance()

    coords = common.rest_coords(body)
    rot = body.matrix_world.to_3x3()
    normals = [(rot @ v.normal).normalized() for v in body.data.vertices]

    def covered_at(i):
        p, n = coords[i], normals[i]
        for direction, reach in ((n, depth), (-n, poke_depth)):
            loc, _hn, _idx, dist = bvh.ray_cast(p, direction, reach)
            if loc is None:
                continue
            if edges is not None and edges.find(loc)[2] < edge_margin:
                continue
            return True
        return False

    covered = {i for i in range(len(coords)) if covered_at(i)}
    if not covered:
        return None

    if grow > 0:
        neighbours = {}
        for edge in body.data.edges:
            a, b = edge.vertices
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)
        for _ in range(grow):
            ring = set()
            for i in covered:
                for j in neighbours.get(i, ()):
                    if j in covered:
                        continue
                    # a neighbour whose ray misses but that sits right by the cloth
                    loc, _hn, _idx, dist = bvh.find_nearest(coords[j])
                    if loc is not None and dist <= 0.01 and (
                            edges is None or edges.find(loc)[2] >= edge_margin):
                        ring.add(j)
            covered |= ring

    name = MASK_PREFIX + obj.name
    group = body.vertex_groups.get(name)
    if group is None:
        group = body.vertex_groups.new(name=name)
    else:
        group.remove([v.index for v in body.data.vertices])
    group.add(sorted(covered), 1.0, "REPLACE")

    mod = body.modifiers.get(name)
    if mod is None or mod.type != "MASK":
        if mod is not None:
            body.modifiers.remove(mod)
        mod = body.modifiers.new(name, "MASK")
    mod.vertex_group = name
    mod.invert_vertex_group = True
    mod.show_viewport = mod.show_render = True
    mod.show_expanded = False
    # HumGen-style bookkeeping so Remove Clothing (ours and HumGen's) drops it again
    existing = common.find_garment_masks(obj)
    if name not in existing:
        obj["mask_%d" % len(existing)] = name
    return len(covered)


def add_corrective_keys(obj, body, rig):
    """Give the garment the body's pose-driven corrective shape keys.

    HumGen's skin bulges at elbows and shoulders through driven keys
    (cor_ElbowBend_Lt, cor_ShoulderSideRaise_Lt...). A garment without them keeps its
    rest shape there, and identical weights still leave 150-250 vertices of skin
    through the sleeve on an elbow bend. This is what HumGen does for its own library
    garments: every driven body key becomes a garment key holding the delta of the
    nearest body vertex, with the same driver pointed at the rig. Keys the garment
    already has are refreshed. Returns the key names added.
    """
    from mathutils.kdtree import KDTree

    keys = getattr(body.data, "shape_keys", None)
    if keys is None or keys.animation_data is None or not keys.animation_data.drivers:
        return []
    driven = {}
    for fcurve in keys.animation_data.drivers:
        path = fcurve.data_path
        if path.startswith('key_blocks["') and path.endswith('"].value'):
            driven[path[len('key_blocks["'):-len('"].value')]] = fcurve
    if not driven:
        return []

    coords = common.rest_coords(body)
    tree = KDTree(len(coords))
    for i, co in enumerate(coords):
        tree.insert(co, i)
    tree.balance()
    nearest = [tree.find(obj.matrix_world @ v.co)[1] for v in obj.data.vertices]
    inv = obj.matrix_world.to_3x3().inverted() @ body.matrix_world.to_3x3()

    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    gkeys = obj.data.shape_keys
    ref = keys.reference_key
    added = []
    for name, fcurve in driven.items():
        src_key = keys.key_blocks.get(name)
        if src_key is None:
            continue
        base = src_key.relative_key.data if src_key.relative_key else ref.data
        block = gkeys.key_blocks.get(name) or obj.shape_key_add(name=name, from_mix=False)
        block.slider_min, block.slider_max = src_key.slider_min, src_key.slider_max
        for i, vert in enumerate(obj.data.vertices):
            j = nearest[i]
            block.data[i].co = vert.co + inv @ (src_key.data[j].co - base[j].co)
        # driver: same expression and variables, retargeted at the rig
        if gkeys.animation_data and gkeys.animation_data.drivers:
            for old in [f for f in gkeys.animation_data.drivers
                        if f.data_path == 'key_blocks["%s"].value' % name]:
                gkeys.animation_data.drivers.remove(old)
        new = block.driver_add("value")
        new.driver.type = fcurve.driver.type
        new.driver.expression = fcurve.driver.expression
        for var in fcurve.driver.variables:
            nv = new.driver.variables.new()
            nv.name, nv.type = var.name, var.type
            for src_t, dst_t in zip(var.targets, nv.targets):
                dst_t.id = rig if getattr(src_t.id, "type", None) == "ARMATURE" else src_t.id
                dst_t.bone_target = src_t.bone_target
                dst_t.transform_type = src_t.transform_type
                dst_t.transform_space = src_t.transform_space
                dst_t.rotation_mode = src_t.rotation_mode
                if var.type == "SINGLE_PROP":
                    dst_t.data_path = src_t.data_path
        added.append(name)
    return added


def remove_body_mask(obj, body):
    name = MASK_PREFIX + obj.name
    if body is None:
        return False
    mod = body.modifiers.get(name)
    if mod is not None:
        body.modifiers.remove(mod)
    group = body.vertex_groups.get(name)
    if group is not None:
        body.vertex_groups.remove(group)
    return mod is not None


def remove_guard(obj):
    mod = obj.modifiers.get(GUARD_NAME)
    if mod is not None:
        obj.modifiers.remove(mod)
        return True
    return False


def hidden_polygons(body):
    """Polygon indices the body's MASK modifiers remove (a face goes when any of its
    vertices is in an inverted mask group / outside a plain one)."""
    hidden = set()
    for mod in body.modifiers:
        if mod.type != "MASK" or not mod.show_viewport or not mod.vertex_group:
            continue
        group = body.vertex_groups.get(mod.vertex_group)
        if group is None:
            continue
        members = set()
        for vert in body.data.vertices:
            if any(g.group == group.index and g.weight > 0.0 for g in vert.groups):
                members.add(vert.index)
        for poly in body.data.polygons:
            inside = [v in members for v in poly.vertices]
            if (any(inside) if mod.invert_vertex_group else not all(inside)):
                hidden.add(poly.index)
    return hidden


def verify(obj, body, frames=None, tolerance=0.002):
    """Count garment vertices inside VISIBLE skin on EVERY frame - sampling has passed
    animations that were visibly broken in between. Skin hidden by a body mask is
    measured with the mask off but ignored, so a vertex over masked skin is not judged
    against some unrelated visible face."""
    from mathutils.bvhtree import BVHTree

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    if frames is None:
        frames = range(scene.frame_start, scene.frame_end + 1)
    current = scene.frame_current
    hidden = hidden_polygons(body)
    counts, worst, worst_frame = [], 0.0, None
    try:
        with common.preserve_masks(body, disable=True):
            for frame in frames:
                scene.frame_set(frame)
                depsgraph.update()
                body_eval = body.evaluated_get(depsgraph)
                same_topology = len(body_eval.data.polygons) == len(body.data.polygons)
                tree = BVHTree.FromObject(body_eval, depsgraph)
                world = body.matrix_world
                inverse, rotation = world.inverted(), world.to_3x3()
                garment = obj.evaluated_get(depsgraph)
                mesh = garment.to_mesh()
                inside = 0
                for vert in mesh.vertices:
                    point = garment.matrix_world @ vert.co
                    loc, normal, index, _dist = tree.find_nearest(inverse @ point)
                    if loc is None:
                        continue
                    if hidden and same_topology and index in hidden:
                        continue
                    depth = -(point - (world @ loc)).dot((rotation @ normal).normalized())
                    if depth > tolerance:
                        inside += 1
                        if depth > worst:
                            worst, worst_frame = depth, frame
                garment.to_mesh_clear()
                counts.append(inside)
    finally:
        scene.frame_set(current)
    if not counts:
        return {}
    return {
        "clip_frames": len(counts),
        "clip_mean": sum(counts) / len(counts),
        "clip_max": max(counts),
        "clip_max_frame": frames[counts.index(max(counts))],
        "clip_worst_cm": worst * 100.0,
        "clip_worst_frame": worst_frame,
    }


# --------------------------------------------------------------------- pipeline

def bind_garment(obj, rig, body, resolution=VOXEL_RES_DEFAULT,
                 debleed_threshold=0.10, use_debleed=True,
                 use_proximity=True, proximity_margin=None,
                 clip_fix="mask", guard_offset=0.004, mask_depth=0.03,
                 mask_edge_margin=0.01, prefer_body_weights=True, verify_frames=False,
                 use_guard=None, use_corrective_keys=True):
    """Full pipeline. Returns a dict of what happened, for the operator to report.

    Engine ladder: (body weights first when the garment hugs the skin and
    `prefer_body_weights`) -> Auto-Rig Pro voxel -> Blender bone heat -> surface
    transfer. The first engine whose result is usable (under 10 % of vertices
    unweighted before the fill pass) wins; the rest are recorded in report["tried"].
    clip_fix: "mask" (hide skin under the cloth - default), "guard" (Shrinkwrap),
    "none". A previous fix of the other kind is removed.
    """
    if use_guard is not None:                      # old keyword
        clip_fix = "guard" if use_guard else "none"
    deform = common.deform_bone_names(rig)
    report = {"engine": None, "seconds": 0.0, "tried": []}
    vert_count = max(1, len(obj.data.vertices))

    engines = []
    hugging = body is not None and body is not obj and prefer_body_weights and hugs_body(obj, body)
    report["hugs_body"] = hugging
    if hugging:
        # identical deformation to the skin it sits on: nothing can beat it
        engines.append(("body", lambda: surface_bind(obj, body, rig) or 0.0))
    if arp_available():
        engines.append(("arp", lambda: arp_bind(obj, rig, resolution)))
    engines.append(("heat", lambda: heat_bind(obj, rig)))
    if body is not None and not hugging:
        engines.append(("surface", lambda: surface_bind(obj, body, rig) or 0.0))

    with common.weights_guarded(obj):
        for name, run in engines:
            try:
                seconds = run() or 0.0
            except Exception as exc:  # noqa: BLE001
                report["tried"].append("%s failed: %s" % (name, exc))
                continue
            bare = unweighted_count(obj, deform)
            if bare > 0.10 * vert_count:
                report["tried"].append("%s left %d unweighted" % (name, bare))
                continue
            report["engine"], report["seconds"] = name, seconds
            break
        if report["engine"] is None:
            raise RuntimeError("no engine produced usable weights (%s)"
                               % "; ".join(report["tried"]))

        limit_influences(obj)
        report["purged"] = len(purge_groups(obj, deform))
        if use_proximity:
            report["far_purged"] = purge_far_groups(obj, rig, body, proximity_margin)
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

    if body is not None and body is not obj:
        if clip_fix == "guard":
            remove_body_mask(obj, body)
            add_guard(obj, body, guard_offset)
        elif clip_fix == "mask":
            remove_guard(obj)
            report["masked"] = add_body_mask(obj, body, depth=mask_depth,
                                             edge_margin=mask_edge_margin) or 0
        else:
            remove_guard(obj)
            remove_body_mask(obj, body)
        report["clip_fix"] = clip_fix
        if use_corrective_keys:
            report["corrective_keys"] = add_corrective_keys(obj, body, rig)
        smooth = [m for m in obj.modifiers if m.type == "CORRECTIVE_SMOOTH"
                  and m.show_viewport and m.factor > 0.5]
        if smooth:
            # measured: factor 1.0 x 20 iterations pulled sleeves 3 cm off the skin on
            # every arm raise (256 verts through the cloth; 10 with it off)
            report["warn_smooth"] = ", ".join(m.name for m in smooth)
    report.update(audit(obj, rig))
    if verify_frames and body is not None and body is not obj:
        report.update(verify(obj, body))
    return report


def unweighted_count(obj, deform_bones, threshold=0.001):
    """Vertices with no real deform weight. Same threshold as `purge_groups`, so an
    engine that leaves voxel dust (ARP on a mesh 17 m from its rig) is not accepted
    only to be wiped by the cleanup a moment later."""
    indices = {g.index for g in obj.vertex_groups if g.name in deform_bones}
    bare = 0
    for vert in obj.data.vertices:
        if not any(g.group in indices and g.weight > threshold for g in vert.groups):
            bare += 1
    return bare


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
