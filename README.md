# Arche FX — HumGen Tools

Four Blender buttons for [Human Generator](https://help.humgen3d.com/) characters,
put where you actually need them.

> **Not affiliated with Human Generator.** Contains no Human Generator code and needs
> no modification to it.

| Button | Tab | What it does |
|---|---|---|
| **Add to Character Clothing** | Clothing | Turns any mesh you've placed on the character into real HumGen clothing — corrective shape keys, drivers, weight painting, the lot. |
| **Add to Clothing Asset Library** | Clothing | Saves **one** garment into your HumGen library so it loads onto any future character. |
| **Remove Clothing** | Clothing | Deletes garments *and* the body mask modifiers they added, so you aren't left with holes in the body. |
| **Re-bind Clothing to Rigify** | Pose | Fixes clothing that stopped following the rig after a Rigify conversion. |

---

## Why these exist

**Custom clothing.** HumGen can already do this, but it's in the Content tab, several
clicks from where you're working, and its save function bundles your *whole outfit* into
one library entry. These buttons sit in the Clothing tab and default to saving the single
garment you selected.

**Removing clothing.** HumGen's delete button lives inside the clothing *material*
sub-panel, which you only reach after drilling into one garment. This puts it in the
Clothing tab, and adds modes for removing all clothing, all footwear, or everything.
Either way the body's mask modifiers go with it — miss that and the body keeps the holes
the garment was hiding.

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

The buttons appear under an **Arche FX** heading in **3D View ▸ Sidebar (N) ▸ HumGen**:
the three clothing tools in the **Clothing** tab, the re-bind in the **Pose** tab. If the
add-on cannot attach to HumGen's panels it falls back to its own **Arche FX** tab. All
four are also in the F3 search menu.

### Adding a custom garment

1. Model or import the garment and place it on the character, **rig at rest pose** — the
   shape gets corrected to the A-pose, so a posed rig bakes in the wrong shape.
2. Select it → **Add to Character Clothing** → pick Torso / Pants / Full Body / Footwear.
3. Optionally → **Add to Clothing Asset Library** to make it reusable.

Add clothing **before** converting to Rigify where you can. If you forget, that's what
the Pose tab button is for.

### Removing a garment

Select it → **Remove Clothing**. The dialog lists exactly what will be deleted before you
confirm. Modes: *Selected Garments* (default), *All Clothing*, *All Footwear*,
*Everything*.

Each garment records the body masks it added as `mask_0`…`mask_9` custom properties;
those modifiers go with it, and masks belonging to garments you kept are left alone.

## What it does that HumGen doesn't

- **Saves a single garment.** HumGen's save writes every object tagged as clothing as one
  outfit. *Only This Garment* (on by default) temporarily drops the tag from the others,
  saves, and restores them exactly.
- **Puts removal where you can reach it.** HumGen's delete button is inside the clothing
  *material* sub-panel, one garment at a time. This is in the Clothing tab with bulk
  modes, and always cleans up the body masks.
- **Preserves your mask settings.** HumGen's weight painting switches every body MASK
  modifier back **on** afterwards, whatever you had. This snapshots and restores them.
- **Forces a depsgraph update before the weight transfer.** HumGen disables the body's
  masks and immediately transfers weights without one. In background/batch this samples
  a body whose arms are still masked away — measured result: forearm groups with **zero**
  weighted vertices and a sleeve that travelled 0.0040 m instead of 0.1360 m.
- **Repairs driver bone targets HumGen misses.** Its conversion only `DEF-`-prefixes
  `forearm`, `upper_arm`, `thigh` and `foot`. Anything else is left dangling — `shin` in
  particular, which breaks the knee corrective shape keys.
- **Rebuilds the weights properly.** HumGen does one `data_transfer` with `vert_mapping="NEAREST"` and no cleanup. Measured on a real garment that left **72.9% of vertices with weights not summing to 1** (2,676 of them under 0.5, following the armature at less than half strength), a median of **5** bone influences against the body's 2, and **58 vertex groups holding no weight**. This re-derives from the body with `POLYINTERP_NEAREST`, then limits to 4 influences, purges dead groups, fills any unweighted vertex and normalises - every vertex ends at exactly 1.000, median 2 influences, zero dead groups.
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
- **Removal:** removing the jeans dropped `mask_lower_long` and kept `mask_torso`,
  `mask_arms_long` and `mask_foot`; other garments untouched; bulk modes cleared
  everything with no masks left over; the body mesh survived; a second run cancels
  cleanly rather than erroring.
- **Re-bind:** binding broken exactly as HumGen leaves late-added clothing → deformation
  died → after re-bind, 63/63 vertex groups restored, drivers byte-identical, deformation
  back to baseline within 1e-6. Idempotent.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).

## On weight transfer, if you are reimplementing this

`POLYINTERP_VNORPROJ` scored better on drift (p95 0.0343 vs 0.0563) and produced fewer
skin pokes — and was still the wrong choice. It shoots a ray along each garment vertex's
own normal, and on a thick closed garment in an A-pose those rays land on unrelated body
parts: it produced **27 implausible vertex groups** including `DEF-toe.L`, `DEF-foot.L`,
`DEF-shin.*` and finger bones. A shirt that twitches when a toe moves is wrong however
good the aggregate numbers look. `POLYINTERP_NEAREST` kept 14 sensible groups.

Order matters: run `vertex_group_smooth` **after** `limit_total`, not before — smoothing
spreads weight into neighbouring groups, so limiting first then smoothing re-broadens what
you just capped (measured: 14 influences per vertex). Smooth, then limit again.

`vertex_group_smooth` also polls for EDIT/WEIGHT_PAINT mode while `clean`, `limit_total`
and `normalize_all` work in object mode.
