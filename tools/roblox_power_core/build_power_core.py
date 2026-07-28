"""Generate an animated Roblox-ready arcade power core in Blender.

Run:
    blender --background --factory-startup --python build_power_core.py -- \
        --output /absolute/output/path
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_NAME = "ArcadePowerCore"
FRAME_START = 1
FRAME_END = 120


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)
    for existing in list(bpy.data.collections):
        bpy.data.collections.remove(existing)


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def move_to_collection(obj: bpy.types.Object, col: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    col.objects.link(obj)


def set_material(
    name: str,
    base: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
    transmission: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (base[0], base[1], base[2], alpha)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    transmission_input = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
    if transmission_input is not None:
        transmission_input.default_value = transmission
    emission_input = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    strength_input = bsdf.inputs.get("Emission Strength")
    if emission is not None and emission_input is not None:
        emission_input.default_value = emission
    if strength_input is not None:
        strength_input.default_value = emission_strength
    if alpha < 1.0:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "use_transparency_overlap"):
            mat.use_transparency_overlap = False
    return mat


def finish_mesh(
    obj: bpy.types.Object,
    name: str,
    col: bpy.types.Collection,
    material: bpy.types.Material,
    *,
    bevel: float = 0.0,
    smooth: bool = True,
) -> bpy.types.Object:
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    move_to_collection(obj, col)
    if material:
        obj.data.materials.append(material)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("EdgeBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    obj.select_set(False)
    return obj


def add_cylinder(name, radius, depth, loc, col, mat, *, vertices=32, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    return finish_mesh(bpy.context.object, name, col, mat, bevel=bevel)


def add_cube(name, dims, loc, col, mat, *, rot=(0.0, 0.0, 0.0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    obj = bpy.context.object
    obj.dimensions = dims
    return finish_mesh(obj, name, col, mat, bevel=bevel, smooth=False)


def add_torus(name, major, minor, loc, col, mat, *, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=48,
        minor_segments=10,
        location=loc,
        rotation=rot,
    )
    return finish_mesh(bpy.context.object, name, col, mat, bevel=0.02)


def add_ico(name, radius, scale, loc, col, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=loc)
    obj = bpy.context.object
    obj.scale = scale
    return finish_mesh(obj, name, col, mat, bevel=0.04, smooth=False)


def add_uv_sphere(name, radius, loc, col, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=loc)
    return finish_mesh(bpy.context.object, name, col, mat, bevel=0.02)


def parent(obj: bpy.types.Object, root: bpy.types.Object) -> None:
    matrix = obj.matrix_world.copy()
    obj.parent = root
    obj.matrix_world = matrix


def add_cycles(obj: bpy.types.Object) -> None:
    if not obj.animation_data or not obj.animation_data.action:
        return
    for fcurve in obj.animation_data.action.fcurves:
        fcurve.modifiers.new("CYCLES")
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"


def animate_rotation(obj: bpy.types.Object, end_angle: float) -> None:
    obj.rotation_mode = "XYZ"
    obj.rotation_euler.z = 0.0
    obj.keyframe_insert("rotation_euler", frame=FRAME_START, index=2)
    obj.rotation_euler.z = end_angle
    obj.keyframe_insert("rotation_euler", frame=FRAME_END, index=2)
    add_cycles(obj)


def animate_crystal(obj: bpy.types.Object) -> None:
    base_z = obj.location.z
    obj.rotation_mode = "XYZ"
    obj.rotation_euler.z = 0.0
    obj.location.z = base_z
    obj.keyframe_insert("rotation_euler", frame=FRAME_START, index=2)
    obj.keyframe_insert("location", frame=FRAME_START, index=2)
    obj.location.z = base_z + 0.28
    obj.keyframe_insert("location", frame=30, index=2)
    obj.location.z = base_z
    obj.keyframe_insert("location", frame=60, index=2)
    obj.location.z = base_z - 0.18
    obj.keyframe_insert("location", frame=90, index=2)
    obj.location.z = base_z
    obj.rotation_euler.z = math.tau
    obj.keyframe_insert("location", frame=FRAME_END, index=2)
    obj.keyframe_insert("rotation_euler", frame=FRAME_END, index=2)
    add_cycles(obj)


def animate_emission(mat: bpy.types.Material) -> None:
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    strength = bsdf.inputs.get("Emission Strength")
    if strength is None:
        return
    for frame, value in ((1, 4.0), (30, 9.0), (60, 4.0), (90, 7.0), (120, 4.0)):
        strength.default_value = value
        strength.keyframe_insert("default_value", frame=frame)
    action = mat.node_tree.animation_data.action if mat.node_tree.animation_data else None
    if action:
        for fcurve in action.fcurves:
            fcurve.modifiers.new("CYCLES")
            for point in fcurve.keyframe_points:
                point.interpolation = "BEZIER"


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_scene(output_dir: Path) -> dict[str, bpy.types.Collection]:
    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.frame_set(36)
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output_dir / f"{ASSET_NAME}_Preview.png")
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.unit_settings.system = "NONE"
    scene.unit_settings.scale_length = 1.0
    scene.world.color = (0.004, 0.006, 0.012)

    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    links = scene.node_tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    glare = nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 0.6
    glare.size = 7
    composite = nodes.new("CompositorNodeComposite")
    links.new(render_layers.outputs["Image"], glare.inputs["Image"])
    links.new(glare.outputs["Image"], composite.inputs["Image"])

    return {
        "VISUAL": collection("APC_VISUAL"),
        "COLLISION": collection("APC_COLLISION"),
        "PREVIEW": collection("APC_PREVIEW"),
    }


def build_asset(output_dir: Path) -> dict:
    clear_scene()
    cols = setup_scene(output_dir)
    visual = cols["VISUAL"]
    collision = cols["COLLISION"]
    preview = cols["PREVIEW"]

    gunmetal = set_material("MAT_Gunmetal", (0.025, 0.04, 0.065, 1), metallic=0.82, roughness=0.25)
    dark = set_material("MAT_DarkArmor", (0.008, 0.014, 0.025, 1), metallic=0.62, roughness=0.34)
    silver = set_material("MAT_BrushedSilver", (0.32, 0.42, 0.52, 1), metallic=0.9, roughness=0.2)
    cyan = set_material("MAT_CoreCyan", (0.0, 0.42, 0.72, 1), metallic=0.05, roughness=0.18, emission=(0.0, 0.8, 1.0, 1), emission_strength=6.0)
    cyan_soft = set_material("MAT_CoreCyanSoft", (0.0, 0.18, 0.32, 0.55), roughness=0.08, emission=(0.0, 0.48, 0.8, 1), emission_strength=2.5, alpha=0.55, transmission=0.35)
    glass = set_material("MAT_ContainmentGlass", (0.015, 0.22, 0.32, 0.18), roughness=0.08, emission=(0.0, 0.14, 0.22, 1), emission_strength=0.35, alpha=0.18, transmission=0.75)
    yellow = set_material("MAT_WarningYellow", (0.95, 0.46, 0.025, 1), metallic=0.15, roughness=0.28, emission=(1.0, 0.18, 0.0, 1), emission_strength=2.2)
    floor_mat = set_material("MAT_PreviewFloor", (0.008, 0.012, 0.02, 1), metallic=0.25, roughness=0.48)

    root = bpy.data.objects.new("APC_ROOT", None)
    visual.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root["roblox_asset"] = ASSET_NAME
    root["stud_scale"] = 1.0

    objects: list[bpy.types.Object] = []
    objects += [
        add_cylinder("Base_Foot", 3.0, 0.45, (0, 0, 0.28), visual, dark, vertices=48, bevel=0.12),
        add_cylinder("Base_Armor", 2.68, 0.65, (0, 0, 0.72), visual, gunmetal, vertices=48, bevel=0.12),
        add_cylinder("Base_InnerRing", 2.15, 0.35, (0, 0, 1.15), visual, silver, vertices=48, bevel=0.08),
        add_torus("Base_EnergyRing", 1.72, 0.12, (0, 0, 1.38), visual, cyan),
    ]

    for i, angle in enumerate((0, math.pi / 2, math.pi, 3 * math.pi / 2)):
        x, y = 2.32 * math.cos(angle), 2.32 * math.sin(angle)
        objects.append(add_cube(f"Pylon_{i+1:02d}", (0.72, 1.02, 6.75), (x, y, 4.75), visual, gunmetal, rot=(0.0, math.radians(11), angle), bevel=0.15))
        objects.append(add_cube(f"PylonAccent_{i+1:02d}", (0.78, 0.16, 1.25), (2.72 * math.cos(angle), 2.72 * math.sin(angle), 5.0), visual, yellow, rot=(0.0, 0.0, angle), bevel=0.07))
        objects.append(add_cylinder(f"ContainmentRod_{i+1:02d}", 0.09, 5.15, (1.72 * math.cos(angle + math.pi / 4), 1.72 * math.sin(angle + math.pi / 4), 5.05), visual, silver, vertices=16, bevel=0.03))

    objects.append(add_cylinder("ContainmentChamber", 1.62, 5.25, (0, 0, 5.05), visual, glass, vertices=48, bevel=0.04))
    objects += [
        add_torus("ChamberRing_Lower", 1.7, 0.16, (0, 0, 2.48), visual, silver),
        add_torus("ChamberRing_Upper", 1.7, 0.16, (0, 0, 7.62), visual, silver),
        add_cylinder("TopCap_Lower", 2.35, 0.55, (0, 0, 8.12), visual, gunmetal, vertices=48, bevel=0.13),
        add_cylinder("TopCap_Upper", 2.72, 0.52, (0, 0, 8.58), visual, dark, vertices=48, bevel=0.14),
        add_cylinder("TopCap_Crown", 1.45, 0.58, (0, 0, 9.02), visual, silver, vertices=32, bevel=0.12),
        add_torus("Top_EnergyRing", 1.25, 0.1, (0, 0, 9.34), visual, cyan),
    ]

    for i, angle in enumerate((math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)):
        objects.append(add_cube(f"TopFin_{i+1:02d}", (0.45, 1.25, 0.48), (1.88 * math.cos(angle), 1.88 * math.sin(angle), 8.84), visual, gunmetal, rot=(0, 0, angle), bevel=0.09))
        objects.append(add_uv_sphere(f"WarningLight_{i+1:02d}", 0.17, (2.18 * math.cos(angle), 2.18 * math.sin(angle), 8.58), visual, yellow))

    crystal = add_ico("Core_Crystal", 1.0, (0.92, 0.92, 1.85), (0, 0, 5.05), visual, cyan)
    crystal.rotation_euler = (math.radians(12), math.radians(-8), math.radians(45))
    objects.append(crystal)
    halo_a = add_torus("EnergyRing_A", 1.28, 0.095, (0, 0, 4.62), visual, cyan, rot=(math.radians(72), 0, math.radians(18)))
    halo_b = add_torus("EnergyRing_B", 1.05, 0.075, (0, 0, 5.72), visual, cyan_soft, rot=(math.radians(18), math.radians(70), 0))
    objects.extend([halo_a, halo_b])

    for i in range(8):
        angle = i * math.tau / 8
        objects.append(add_uv_sphere(f"EnergyNode_{i+1:02d}", 0.11, (1.28 * math.cos(angle), 1.28 * math.sin(angle), 5.05), visual, cyan))

    for obj in objects:
        parent(obj, root)
        obj["export_role"] = "visual"

    animate_rotation(halo_a, math.tau)
    animate_rotation(halo_b, -math.tau)
    animate_crystal(crystal)
    animate_emission(cyan)

    collision_obj = add_cylinder("COLLISION_Main", 2.92, 9.4, (0, 0, 4.7), collision, dark, vertices=12, bevel=0.0)
    collision_obj.display_type = "WIRE"
    collision_obj.hide_render = True
    collision_obj["export_role"] = "collision"

    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0.02))
    finish_mesh(bpy.context.object, "Preview_Ground", preview, floor_mat, smooth=False)

    bpy.ops.object.camera_add(location=(13.5, -15.5, 11.8))
    camera = bpy.context.object
    camera.name = "Preview_Camera"
    camera.data.lens = 58
    look_at(camera, (0, 0, 4.8))
    move_to_collection(camera, preview)
    bpy.context.scene.camera = camera

    def light(name, kind, loc, energy, color, size=5.0):
        data = bpy.data.lights.new(name=f"{name}_Data", type=kind)
        data.energy = energy
        data.color = color
        if kind == "AREA":
            data.shape = "DISK"
            data.size = size
        obj = bpy.data.objects.new(name, data)
        preview.objects.link(obj)
        obj.location = loc
        look_at(obj, (0, 0, 5))
        return obj

    light("Key_Area", "AREA", (6, -7, 13), 1250, (0.68, 0.82, 1.0), 7.0)
    light("Rim_Area", "AREA", (-8, 2, 9), 950, (0.08, 0.45, 1.0), 6.0)
    light("Warm_Fill", "AREA", (5, 7, 5), 650, (1.0, 0.34, 0.08), 5.0)
    light("Core_Point", "POINT", (0, 0, 5.1), 850, (0.0, 0.72, 1.0), 1.0)

    scene = bpy.context.scene
    scene.frame_set(36)
    blend_path = output_dir / f"{ASSET_NAME}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for obj in visual.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    glb_path = output_dir / f"{ASSET_NAME}.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_animations=True, export_yup=True)
    fbx_path = output_dir / f"{ASSET_NAME}.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, apply_unit_scale=True, bake_anim=True, bake_anim_use_all_actions=False, add_leaf_bones=False, axis_forward="-Z", axis_up="Y")

    bpy.ops.object.select_all(action="DESELECT")
    collision_obj.select_set(True)
    bpy.context.view_layer.objects.active = collision_obj
    collision_path = output_dir / f"{ASSET_NAME}_Collision.glb"
    bpy.ops.export_scene.gltf(filepath=str(collision_path), export_format="GLB", use_selection=True, export_apply=True, export_animations=False, export_yup=True)

    scene.render.filepath = str(output_dir / f"{ASSET_NAME}_Preview.png")
    scene.frame_set(36)
    bpy.ops.render.render(write_still=True)

    manifest = {
        "asset": ASSET_NAME,
        "version": 1,
        "units": "1 Blender unit = 1 Roblox stud",
        "target_dimensions_studs": [6.0, 6.0, 10.0],
        "frame_range": [FRAME_START, FRAME_END],
        "animated_objects": ["Core_Crystal", "EnergyRing_A", "EnergyRing_B"],
        "visual_collection": visual.name,
        "collision_collection": collision.name,
        "visual_objects": sorted(obj.name for obj in visual.objects if obj.type == "MESH"),
        "materials": sorted(mat.name for mat in bpy.data.materials),
        "exports": [glb_path.name, fbx_path.name, collision_path.name, blend_path.name, f"{ASSET_NAME}_Preview.png"],
    }
    (output_dir / f"{ASSET_NAME}_Manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_asset(output_dir)
    print(json.dumps(manifest, indent=2))
    print(f"BUILT:{output_dir / (ASSET_NAME + '.blend')}")


if __name__ == "__main__":
    main()
