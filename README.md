# Arche FX — HumGen Rigify Re-bind

A small Blender add-on that fixes clothing which **stops following the rig** after you
convert a [Human Generator](https://help.humgen3d.com/) character to Rigify.

Add a jacket, a pair of shoes, anything — *after* the Rigify conversion — and it just
hangs in space while the character moves. This adds one button that binds it.

> **Not affiliated with Human Generator.** This is an independent add-on that contains
> no Human Generator code and does not require any modification to it.

---

## The problem

Human Generator's Rigify conversion renames every vertex group to Rigify's `DEF-`
convention, then walks the rig's children and rebinds them — but it walks the children
that exist **at conversion time**.

Anything added later keeps its un-prefixed group names (`foot.L`, `shin.L`). An Armature
modifier binds vertex groups to **bone names**, and Rigify's deform bones are all
`DEF-`-prefixed, so nothing matches and the garment never moves.

The confusing part: the Armature modifier's *target object* is set correctly, so the
modifier looks completely fine. Blender reports no error. The garment simply sits there.

Human Generator has no built-in way to fix this after the fact — the only supported
route is to dress the character fully *before* converting.

## What this does

One button walks every mesh child of the rig and, for any whose vertex groups drive
**no deform bone**:

1. Renames its vertex groups to the `DEF-` convention.
2. Repoints its Armature modifier at the Rigify rig.
3. Retargets its shape key drivers — clothing corrective keys (`cor_FootDown_Lt`,
   `cor_ElbowBend_Rt`) are driven by bone rotation and still reference the rig that the
   conversion deleted.

Miss step 3 and the garment follows the rig but stops flexing at the joint.

Already-bound items are skipped, so it is safe to press more than once.

## Install

1. Download `archefx_humgen_rebind.py` from
   [Releases](https://github.com/RC-Shadow/archefx-humgen-rebind/releases) (or clone).
2. Blender → **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk…**
3. Pick the `.py`, enable **Arche FX - HumGen Rigify Re-bind**.

Blender 4.0+. Human Generator and Rigify do the real work; this only repairs the join
between them.

## Use

1. Select any part of the converted character.
2. **3D View ▸ Sidebar (N) ▸ HumGen ▸ Pose ▸ Rigify** — the button appears under an
   *Arche FX* heading once a Rigify rig is active.
3. Press **Re-bind Clothing to Rigify**.

If the add-on cannot attach to HumGen's panel it falls back to its own **Arche FX** tab
in the same sidebar. The operator is also available from the search menu (F3) as
*Re-bind Clothing to Rigify*.

## Two things worth knowing if you fork this

**Test against `use_deform` bones, not all bones.** Rigify carries plain-named *control*
bones (`foot.L`, `f_index.01.L`, `eyeball.L`) that collide with HumGen's un-prefixed
group names. On a garment that genuinely did not deform at all, **37 vertex groups still
matched a bone name**. Matching "any bone" proves nothing — only `use_deform` bones move
mesh.

**Rigify limbs default to IK** (`IK_FK = 0.0`). If you verify a fix by rotating an FK
control, nothing moves and a perfectly working rig looks broken. Pose through
`foot_ik.L` / `hand_ik.R` instead.

Also: roughly 8 groups (`DEF-Head`, `DEF-heel.L`, `DEF-pelvis.L`) never resolve to a
Rigify bone even after a *correct* conversion, because HumGen has bones Rigify does not.
Unmatched groups on their own are not a failure signal.

## Verified

Round-trip tested against a real Human Generator character on Blender 4.5.11:

- A garment's binding was broken exactly the way HumGen leaves late-added clothing
- Confirmed it stopped deforming (travel dropped from 0.1196 m to ~0 under an IK pose)
- Ran the operator
- **63/63** vertex groups restored, shape key drivers byte-identical to baseline,
  deformation back to 0.1196 m matching baseline to 1e-6
- Already-bound items untouched; second run a no-op

19/19 checks pass.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
