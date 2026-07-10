# Bone collection rules

## Classification order

1. **Body (forced)** — humanoid anatomy wins over other rules
2. **Hair (name)** — `hair`, `Hair`, `J_Sec_Hair`
3. **Clothing (name)** — `hood`, `hoodString`, `J_Sec_*` garment tokens
4. **Hair (weights)** — deforms only Hair/Twintails meshes
5. **Clothing (weights)** — deforms only cloth-named meshes (Tops, Shoes, …)
6. **Body (default)** — everything else

## Body (forced) patterns

`root`, `J_Bip_*`, `hips`, `spine`, `chest`, `upperChest`, `neck`, `head`, limbs, digits, `faceEye`, `bust*`, `J_Adj_*`

## Hair patterns

- Remapped: `hair01.1.l`, `hair07.7.end.r`
- VRoid: `J_Sec_Hair1_01`, `Hair1_06`

## Clothing patterns

- Remapped: `hood.1`, `hoodString.2.end.l`
- VRoid: `J_Sec_*Hood*`, `*Skirt*`, `*Shoe*`, `*Cloth*` in secondary bone names

## Mesh weight hints

| Mesh name contains | Hint |
|--------------------|------|
| `hair`, `twintail` | Hair |
| `cloth`, `shoe`, `top`, `skirt`, `pants`, `jacket`, `coat` | Clothing |
| `body`, `face`, `skin` | Body |

Weight hint applies only when **all** weighted meshes for that bone match one category.

## Notes

- Bones can belong to one managed collection per apply pass (unassign then reassign).
- Pre-existing unrelated collections are left untouched.
- Run **after Phase G** so remapped `hair*` / `hood*` names classify correctly.
