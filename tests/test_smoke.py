import bpy, sys, os, importlib
ROOT = r"C:\Claude\_tools\archefx-humgen-tools"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAIL = []
def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (" | " + detail if detail else ""))
    if not cond:
        FAIL.append(label)

print("=== import & register ===")
import arche_extensions
importlib.reload(arche_extensions)
check("package imports", True)
check("bl_info name", arche_extensions.bl_info["name"] == "Arche Extensions",
      arche_extensions.bl_info["name"])
check("version 2.0.0", arche_extensions.bl_info["version"] == (2, 0, 0))
arche_extensions.register()
for op in ("bind_weights", "add_as_clothing", "save_clothing_to_library",
           "remove_clothing", "rebind_humgen_rigify"):
    check("operator %s" % op, hasattr(bpy.types, "ARCHEFX_OT_" + op))

print("=== guards behave ===")
from arche_extensions import common, weights
check("ARP detected", weights.arp_available())
check("voxel clamp 3..8", (weights.VOXEL_RES_MIN, weights.VOXEL_RES_MAX) == (3, 8))
check("engine pinned to 1", weights.VOXEL_ENGINE == "1")

rig = bpy.data.objects.get("Porfirio_RIGIFY")
shirt = bpy.data.objects.get("TSA_Shirt")
if rig and shirt:
    body = common.find_hg_body(rig)
    check("finds rig from garment", common.find_rig(shirt) == rig)
    check("finds body", body is not None, body.name if body else "None")
    deform = common.deform_bone_names(rig)
    check("deform bones found", len(deform) > 50, "%d" % len(deform))

    # preserve_pose must put a pose back even when the block raises
    rig.pose.bones["hand_ik.R"].location = (0.1, 0.0, 0.2)
    bpy.context.view_layer.update()
    before = rig.pose.bones["hand_ik.R"].location.copy()
    try:
        with common.preserve_pose(rig):
            common.clear_pose(rig)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    after = rig.pose.bones["hand_ik.R"].location
    check("preserve_pose survives an exception", (before - after).length < 1e-6,
          "%.4f vs %.4f" % (before.z, after.z))
    rig.pose.bones["hand_ik.R"].location = (0, 0, 0)
    bpy.context.view_layer.update()

    # preserve_masks must restore visibility even when the block raises
    masks = [(m.name, m.show_viewport) for m in body.modifiers if m.type == "MASK"]
    try:
        with common.preserve_masks(body, disable=True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    after_masks = [(m.name, m.show_viewport) for m in body.modifiers if m.type == "MASK"]
    check("preserve_masks survives an exception", masks == after_masks, str(after_masks))

    # weights_guarded must roll weights back
    n_before = len(shirt.vertex_groups)
    try:
        with common.weights_guarded(shirt):
            shirt.vertex_groups.clear()
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    check("weights_guarded rolls back", len(shirt.vertex_groups) == n_before,
          "%d -> %d" % (n_before, len(shirt.vertex_groups)))
else:
    print("  (no TSA character in this file, skipped scene checks)")

arche_extensions.unregister()
check("unregisters cleanly", True)
print("\nRESULT: %s" % ("ALL PASS" if not FAIL else "FAILURES -> %s" % FAIL))
