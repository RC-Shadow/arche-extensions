import bpy, sys, hashlib, importlib
ROOT = r"C:\Claude\_tools\archefx-humgen-tools"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAIL = []
def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (" | " + detail if detail else ""))
    if not cond:
        FAIL.append(label)

import arche_extensions
importlib.reload(arche_extensions)
arche_extensions.register()
from arche_extensions import common, weights

rig = bpy.data.objects["Porfirio_RIGIFY"]
shirt = bpy.data.objects["TSA_Shirt"]
body = common.find_hg_body(rig)

def masksig():
    return hashlib.sha1(str([(m.name, m.vertex_group, m.invert_vertex_group,
                              m.show_viewport, m.show_render)
                             for m in body.modifiers if m.type == "MASK"]).encode()
                        ).hexdigest()[:12]

def skstate():
    sk = shirt.data.shape_keys
    if not sk:
        return None
    names = [k.name for k in sk.key_blocks]
    drv = []
    if sk.animation_data:
        for d in sk.animation_data.drivers:
            key = d.data_path.split('"')[1] if '"' in d.data_path else d.data_path
            for v in d.driver.variables:
                for t in v.targets:
                    drv.append((key, t.id.name if t.id else None, t.bone_target))
    return names, sorted(drv)

# a pose the operator must give back untouched
rig.pose.bones["hand_ik.R"].location = (0.12, 0.02, 0.20)
bpy.context.view_layer.update()
pose_before = rig.pose.bones["hand_ik.R"].location.copy()
mask_before = masksig()
sk_before = skstate()
mods_before = [(m.type, m.show_viewport, m.show_render) for m in shirt.modifiers]

print("=== run the Bind Weights button ===")
bpy.context.view_layer.objects.active = shirt
res = bpy.ops.archefx.bind_weights(resolution=7, use_debleed=True,
                                   debleed_threshold=0.10)
check("operator FINISHED", res == {"FINISHED"}, str(res))

print("=== weights ===")
a = weights.audit(shirt, rig)
check("no vertex off-normal", a["off_normal"] == 0, "%d" % a["off_normal"])
check("no unweighted vertex", a["unweighted"] == 0, "%d" % a["unweighted"])
check("sums are 1.0", abs(a["sum_min"] - 1.0) < 0.01 and abs(a["sum_max"] - 1.0) < 0.01,
      "%.3f..%.3f" % (a["sum_min"], a["sum_max"]))
check("influences capped", a["bones_max"] <= 6, "med %d max %d" % (a["bones_med"], a["bones_max"]))
deform = common.deform_bone_names(rig)
names = [g.name for g in shirt.vertex_groups]
check("only deform bones kept", all(n in deform for n in names),
      str([n for n in names if n not in deform][:4]))
check("no head/jaw groups",
      not any(t in n.lower() for n in names for t in ("head", "jaw", "toe")), str(names))
print("   groups (%d): %s" % (len(names), sorted(names)))

print("=== nothing else disturbed ===")
check("body masks untouched", masksig() == mask_before)
check("shape keys + drivers preserved", skstate() == sk_before)
check("modifier stack preserved",
      [(m.type, m.show_viewport, m.show_render) for m in shirt.modifiers] == mods_before)
check("cloth tag + mask_0 kept",
      "cloth" in shirt and shirt.get("mask_0") is not None)
after = rig.pose.bones["hand_ik.R"].location
check("user pose restored", (pose_before - after).length < 1e-6,
      "%.4f vs %.4f" % (pose_before.z, after.z))

for pb in rig.pose.bones:
    pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0)
bpy.context.view_layer.update()
arche_extensions.unregister()
print("\nRESULT: %s" % ("ALL PASS" if not FAIL else "FAILURES -> %s" % FAIL))
