# Arche Extensions

A Blender add-on for [Human Generator](https://help.humgen3d.com/) characters — bind
garment weights properly, manage clothing, and repair what a Rigify conversion breaks.

> **Not affiliated with Human Generator or Auto-Rig Pro.** Contains no code from either
> and requires no modification to them.

| Button | What it does |
|---|---|
| **Bind Weights** | Skins a garment to the character (Auto-Rig Pro voxel bind, or Blender bone heat without ARP), cleans up, adds a body-collision guard, and verifies every frame. **Never touches body masks.** |
| **Add to Character Clothing** | Tags a mesh placed on the character as HumGen clothing and binds it. Optional HumGen fitting for garments built on the default body. |
| **Add to Clothing Asset Library** | Saves **one** garment to your library, not the whole outfit. |
| **Remove Clothing** | Deletes garments *and* the body masks they added, so no holes are left behind. |
| **Re-bind Clothing to Rigify** | Fixes clothing that stopped following the rig after a Rigify conversion. |

---

## Why Bind Weights exists

HumGen's own weighting runs a single `data_transfer` with `vert_mapping="NEAREST"` and
**no cleanup at all**. Measured on a 29,736-vertex shirt against `HG_Body`:

- **72.9%** of vertices had weights that did not sum to 1 — 2,676 of them under 0.5, so
  they followed the armature at less than half strength
- a median of **5** bone influences per vertex, against the body's 2
- **58** vertex groups holding no weight whatsoever

Clipping vertices counted across 7 poses:

| | 7 poses | at rest |
|---|---|---|
| HumGen `data_transfer` NEAREST + cleanup | 10,539 | 1,482 |
| **Auto-Rig Pro pseudo-voxel bind** | **3,611** | **321** |

Auto-Rig Pro's `bind_to_rig()` with the `PSEUDO_VOXELS` engine works on a **Rigify** rig,
not just ARP rigs, binds in ~16 s, and assigns the twist bones (`DEF-upper_arm.L.001`)
that surface transfer never touches.

## What the bind does

1. **Engine ladder** — Auto-Rig Pro pseudo-voxel bind (resolution slider, clamped 3–8,
   default 7) → Blender bone-heat automatic weights → `POLYINTERP_NEAREST` surface
   transfer from the body. The first engine that leaves under 10 % of vertices
   unweighted wins. ARP and HumGen are both optional.
2. **Clean up** — cap influences at 4, drop dead and non-deform groups, fill any
   unweighted vertex, normalise every vertex to exactly 1.0.
3. **Drop far-away bones by proximity, never by name** — a bone stays only if the skin
   it drives on the body lies near the garment. A bone the body has no group for
   (HumGen has no `DEF-jaw`) goes. The old name blacklist stripped `DEF-toe` off shoes
   and, matching `ear`, `DEF-forearm` off every sleeve.
4. **Remove arm bleed from the chest** — otherwise the chest sloshes when an arm moves.
5. **Soften the seam** with a per-group smooth.
6. **Body-collision guard** — a Shrinkwrap (*outside surface*, 4 mm) targeting the body,
   placed **last** in the modifier stack. This is what removes clipping: a shirt modelled
   partly inside the skin had ~800 vertices inside the body per frame with *every*
   weighting engine (769 with no rig at all). With the guard: mean 3, max 21, worst
   0.4 cm over 123 frames. Weights cannot fix geometry; this can.
7. **Verify every frame** — vertices inside the body counted on each frame of the scene
   range and reported in the status bar. Sampled checks have passed animations that
   were broken in between.

## Install

1. Download the latest `arche_extensions-*.zip` from
   [Releases](https://github.com/RC-Shadow/arche-extensions/releases).
2. **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk…**, pick the zip, enable
   **Arche Extensions**.

Blender 4.0+. Auto-Rig Pro is optional but strongly recommended — without it the binder
falls back to surface transfer.

> **Upgrading from v1.x?** Remove the old single-file *Arche FX - HumGen Tools* add-on
> first. Both register the same operators and will collide.

## Use

Press **N** in the 3D view. The buttons appear as an **Arche Extensions** panel in two
places, so they are wherever you happen to be working:

* inside the **HumGen** tab
* in its own **Arche FX** tab

Everything is also in the F3 search menu.

**Adding a garment:** place it on the character with the **rig at rest pose** (the shape
gets corrected to the A-pose, so a posed rig bakes in the wrong shape), select it, then
*Add to Character Clothing*. Add clothing **before** converting to Rigify where you can.

## Notes for anyone forking this

**Test against `use_deform` bones, not all bones.** Rigify carries plain-named *control*
bones (`foot.L`, `f_index.01.L`, `eyeball.L`) that collide with HumGen's un-prefixed
group names. On a garment that genuinely did not deform, **37 groups still matched a bone
name**. Only `use_deform` bones move mesh.

**Rigify limbs default to IK** (`IK_FK = 0.0`). Verify a fix by rotating an FK control and
nothing moves — a perfectly working rig looks broken. Pose through `foot_ik.L` /
`hand_ik.R`.

**Never raise ARP's voxel resolution to 12.** On a 30k-vert closed-solid garment it ran
**221 minutes** and reached **20.5 GB** before it had to be killed. ARP's own tooltip:
*"Low values may sometimes work better than high values."* The slider here is capped at 8.
Diagnose a stuck bind by **memory growth, not CPU** — rising RAM with low CPU is runaway
allocation that will never finish.

**Do not try to `append()` into another add-on's panel.** `bpy.types.HG_PT_CLOTHING` is
the very class you get by importing it, yet its `_draw_funcs` stays empty after `append()`,
so the buttons never render and nothing reports an error. Register your own panel with
`bl_category` set to their tab name instead. And do not create the second panel as a
*subclass* of the first - registering it lets Blender clobber the base class's
`bl_category`, silently moving the original tab.

**Smooth one vertex group at a time** (`group_select_mode='ACTIVE'`). Smoothing with
`'ALL'` collapsed influences to a median of 1 bone per vertex.

**`outfit.add_obj`'s docstring says `"top"`**, but the corrective shape key JSON keys it as
`"torso"` — passing `"top"` raises `KeyError`.

`arp_pseudo_voxels_type='2'` binds faster (8.6 s vs 16 s) but produced no usable weights on
a real garment, so it is not exposed.

## What it deliberately does not do

**Touch your body masks.** The binder only changes weights. Mask painting is yours.

It also cannot fix a garment whose *topology* fails. A closed-solid scanned garment with no
armhole seam still stretches ~9.6× at the armpit under a high arm raise even with correct
weights — that needs mesh work, not rigging. (A garment merely modelled *inside* the skin
is handled by the collision guard.)

**Refit your mesh.** Human Generator's own `add_obj` assumes a garment built on the
default HumGen body and reshapes it onto the character — on a shirt already fitted to the
character it moved the mesh 14 cm up and 30 cm forward. *Add to Character Clothing*
therefore defaults to **Tag only**; pick *HumGen fitting* only for default-body garments.

## Verified

Against a real character, Blender 4.5.11:

- **Guards** — pose, body masks and weights all restored after a deliberate exception
- **Shirt, 3,281 verts** — ARP 16 s, 11 groups (jaw and thighs dropped by proximity),
  0 unweighted, influences med 2 / max 5; inside the body over 123 frames: mean 3,
  max 21, worst 0.4 cm (before: ~950 per frame, 5 cm)
- **Shoe, 183 verts** — `DEF-foot.L` + `DEF-toe.L`, guard after Subsurf: mean 0, max 5,
  worst 0.4 cm (guard placed before Subsurf: 164)
- **Without ARP** — bone-heat path binds the same shirt in 0.4 s with equivalent results
- **Preservation** — body masks, shape keys, drivers, `cloth` tag, `mask_0` and the
  user's pose unchanged after a bind; the guard is the only modifier added

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
