# Arche Extensions

A Blender add-on for [Human Generator](https://help.humgen3d.com/) characters — bind
garment weights properly, manage clothing, and repair what a Rigify conversion breaks.

> **Not affiliated with Human Generator or Auto-Rig Pro.** Contains no code from either
> and requires no modification to them.

| Button | Tab | What it does |
|---|---|---|
| **Bind Weights** | Clothing | Skins a garment to the character with Auto-Rig Pro's voxel binder, then cleans up. **Never touches body masks.** |
| **Add to Character Clothing** | Clothing | Turns any mesh placed on the character into real HumGen clothing, then binds it. |
| **Add to Clothing Asset Library** | Clothing | Saves **one** garment to your library, not the whole outfit. |
| **Remove Clothing** | Clothing | Deletes garments *and* the body masks they added, so no holes are left behind. |
| **Re-bind Clothing to Rigify** | Pose | Fixes clothing that stopped following the rig after a Rigify conversion. |

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

1. **ARP pseudo-voxel bind** — resolution slider, clamped 3–8, default 7. Falls back to
   `POLYINTERP_NEAREST` surface transfer if Auto-Rig Pro is not installed.
2. **Clean up** — cap influences at 4, drop dead and non-deform groups, remove bones a
   garment must never follow (head, jaw, toes, face), fill any unweighted vertex,
   normalise every vertex to exactly 1.0.
3. **Remove arm bleed from the chest** — otherwise the chest sloshes when an arm moves.
4. **Soften the seam** with a per-group smooth.

Typical result: 15 sensible groups, every vertex at 1.000, zero unweighted, median 3
influences.

## Install

1. Download `arche_extensions-2.0.0.zip` from
   [Releases](https://github.com/RC-Shadow/arche-extensions/releases).
2. **Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk…**, pick the zip, enable
   **Arche Extensions**.

Blender 4.0+. Auto-Rig Pro is optional but strongly recommended — without it the binder
falls back to surface transfer.

> **Upgrading from v1.x?** Remove the old single-file *Arche FX - HumGen Tools* add-on
> first. Both register the same operators and will collide.

## Use

Buttons appear under an **Arche Extensions** heading in
**3D View ▸ Sidebar (N) ▸ HumGen** — clothing tools in the **Clothing** tab, the Rigify
repair in **Pose**. If the add-on cannot attach to HumGen's panels it falls back to its
own **Arche FX** tab. Everything is also in the F3 search menu.

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

**Smooth one vertex group at a time** (`group_select_mode='ACTIVE'`). Smoothing with
`'ALL'` collapsed influences to a median of 1 bone per vertex.

**`outfit.add_obj`'s docstring says `"top"`**, but the corrective shape key JSON keys it as
`"torso"` — passing `"top"` raises `KeyError`.

`arp_pseudo_voxels_type='2'` binds faster (8.6 s vs 16 s) but produced no usable weights on
a real garment, so it is not exposed.

## What it deliberately does not do

**Touch your body masks.** The binder only changes weights. Mask painting is yours.

It also cannot fix a garment whose *geometry* fails. A closed-solid scanned garment with no
armhole seam still stretches ~9.6× at the armpit under a high arm raise even with correct
weights — that needs mesh work, not rigging.

## Verified

Headless against a real character, Blender 4.5.11:

- **Guards** — pose, body masks and weights all restored after a deliberate exception
- **Bind** — 16.6 s, 15 groups, sums 1.000–1.000, 0 unweighted, influences med 3 / max 6,
  only deform bones, no head/jaw/toe groups
- **Preservation** — body masks, shape keys, drivers, modifier stack, `cloth` tag, `mask_0`
  and the user's pose all byte-identical after a bind

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
