# Arche FX — HumGen Tools

Three Blender buttons for [Human Generator](https://help.humgen3d.com/) characters,
put where you actually need them.

> **Not affiliated with Human Generator.** Contains no Human Generator code and needs
> no modification to it.

| Button | What it does |
|---|---|
| **Add to Character Clothing** | Turns any mesh you've placed on the character into real HumGen clothing — corrective shape keys, drivers, weight painting, the lot. |
| **Add to Clothing Asset Library** | Saves **one** garment into your HumGen library so it loads onto any future character. |
| **Re-bind Clothing to Rigify** | Fixes clothing that stopped following the rig after a Rigify conversion. |

---

## Why these exist

**Custom clothing.** HumGen can already do this, but it's in the Content tab, several
clicks from where you're working, and its save function bundles your *whole outfit* into
one library entry. These buttons sit in the Pose panel and default to saving the single
garment you selected.

**Rigify re-bind.** HumGen's Rigify conversion renames every vertex group to the `DEF-`
convention, then rebinds the rig's children — but only the children that exist **at
conversion time**. Anything added later keeps un-prefixed group names, matches no deform
bone, and never moves. The Armature modifier's *target* is set correctly, so nothing
looks wrong and Blender reports no error. HumGen has no built-in way to repair this.

## Install

1. Download `archefx_humgen_tools.py` from
   [Releases](https://github.com/RC-Shadow/archefx-humgen-tools/releases).
2. **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk…**, pick the `.py`, enable
   **Arche FX - HumGen Tools**.

Blender 4.0+. If you had v1.0.0 (`archefx_humgen_rebind.py`) installed, remove it first.

## Use

The buttons appear under an **Arche FX** heading in
**3D View ▸ Sidebar (N) ▸ HumGen ▸ Pose**, or in their own **Arche FX** tab if the add-on
can't attach to HumGen's panel. All three are also in the F3 search menu.

### Adding a custom garment

1. Model or import the garment and place it on the character, **rig at rest pose** — the
   shape gets corrected to the A-pose, so a posed rig bakes in the wrong shape.
2. Select it → **Add to Character Clothing** → pick Torso / Pants / Full Body / Footwear.
3. Optionally → **Add to Clothing Asset Library** to make it reusable.

Add clothing **before** converting to Rigify where you can. If you forget, that's what
the third button is for.

## What it does that HumGen doesn't

- **Saves a single garment.** HumGen's save writes every object tagged as clothing as one
  outfit. *Only This Garment* (on by default) temporarily drops the tag from the others,
  saves, and restores them exactly.
- **Preserves your mask settings.** HumGen's weight painting switches every body MASK
  modifier back **on** afterwards, whatever you had. This snapshots and restores them.
- **Forces a depsgraph update before the weight transfer.** HumGen disables the body's
  masks and immediately transfers weights without one. In background/batch this samples
  a body whose arms are still masked away — measured result: forearm groups with **zero**
  weighted vertices and a sleeve that travelled 0.0040 m instead of 0.1360 m.
- **Repairs driver bone targets HumGen misses.** Its conversion only `DEF-`-prefixes
  `forearm`, `upper_arm`, `thigh` and `foot`. Anything else is left dangling — `shin` in
  particular, which breaks the knee corrective shape keys.
- **Verifies afterwards** and warns if any driver bone still doesn't resolve.

## Two things worth knowing if you fork this

**Test against `use_deform` bones, not all bones.** Rigify carries plain-named *control*
bones (`foot.L`, `f_index.01.L`, `eyeball.L`) that collide with HumGen's un-prefixed
group names. On a garment that genuinely did not deform, **37 groups still matched a bone
name**. Only `use_deform` bones move mesh.

**Rigify limbs default to IK** (`IK_FK = 0.0`). Verify a fix by rotating an FK control and
nothing moves — a perfectly working rig looks broken. Pose through `foot_ik.L` /
`hand_ik.R`.

Also: `outfit.add_obj`'s docstring says the torso type is `"top"`, but the corrective
shape key JSON keys it as `"torso"` — passing `"top"` raises `KeyError`.

## Verified

Round-trip tested on real Human Generator characters, Blender 4.5.11:

- **Custom clothing:** raw mesh → tagged, parented, 6 torso corrective keys, 62 groups
  driving deform bones, every driver resolving, and deformation at 0.1360 m against a
  known-good garment's 0.1569 m. Confirmed independently in the GUI at a **1.39 ratio**
  against a reference shirt.
- **Library save:** one `.blend` written, sibling clothing tags restored exactly.
- **Re-bind:** binding broken exactly as HumGen leaves late-added clothing → deformation
  died → after re-bind, 63/63 vertex groups restored, drivers byte-identical, deformation
  back to baseline within 1e-6. Idempotent.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
