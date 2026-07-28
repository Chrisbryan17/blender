"""Validate the generated arcade power core using Blender's Python runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_NAME = "ArcadePowerCore"
REQUIRED_OBJECTS = {
    "APC_ROOT",
    "Base_Foot",
    "ContainmentChamber",
    "Core_Crystal",
    "EnergyRing_A",
    "EnergyRing_B",
    "TopCap_Upper",
    "COLLISION_Main",
}
REQUIRED_MATERIALS = {
    "MAT_Gunmetal",
    "MAT_DarkArmor",
    "MAT_BrushedSilver",
    "MAT_CoreCyan",
    "MAT_ContainmentGlass",
    "MAT_WarningYellow",
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def triangle_count(collection_name: str) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    total = 0
    for obj in bpy.data.collections[collection_name].objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        total += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
    return total


def bounds(collection_name: str) -> tuple[list[float], list[float], list[float]]:
    points: list[Vector] = []
    for obj in bpy.data.collections[collection_name].objects:
        if obj.type != "MESH":
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    minimum = [min(point[i] for point in points) for i in range(3)]
    maximum = [max(point[i] for point in points) for i in range(3)]
    dimensions = [maximum[i] - minimum[i] for i in range(3)]
    return minimum, maximum, dimensions


def has_action(name: str) -> bool:
    obj = bpy.data.objects[name]
    return bool(obj.animation_data and obj.animation_data.action)


def main() -> None:
    args = parse_args()
    blend_path = Path(args.blend).resolve()
    output_dir = Path(args.output).resolve()
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))

    missing_objects = sorted(REQUIRED_OBJECTS - set(bpy.data.objects.keys()))
    missing_materials = sorted(REQUIRED_MATERIALS - set(bpy.data.materials.keys()))
    assert not missing_objects, f"Missing objects: {missing_objects}"
    assert not missing_materials, f"Missing materials: {missing_materials}"

    triangles = triangle_count("APC_VISUAL")
    minimum, maximum, dimensions = bounds("APC_VISUAL")
    assert triangles < 10_000, f"Triangle budget exceeded: {triangles}"
    assert dimensions[0] <= 6.5 and dimensions[1] <= 6.5, f"Footprint too large: {dimensions}"
    assert dimensions[2] <= 10.2, f"Height too large: {dimensions}"
    assert minimum[2] >= -0.05, f"Asset extends below ground: {minimum[2]}"

    animated = {name: has_action(name) for name in ("Core_Crystal", "EnergyRing_A", "EnergyRing_B")}
    assert all(animated.values()), f"Missing object animation: {animated}"

    scales = {
        obj.name: [round(value, 6) for value in obj.scale]
        for obj in bpy.data.collections["APC_VISUAL"].objects
        if obj.type == "MESH" and any(abs(value - 1.0) > 1e-5 for value in obj.scale)
    }
    assert not scales, f"Unapplied scales: {scales}"

    expected_files = [
        f"{ASSET_NAME}.blend",
        f"{ASSET_NAME}.glb",
        f"{ASSET_NAME}.fbx",
        f"{ASSET_NAME}_Collision.glb",
        f"{ASSET_NAME}_Preview.png",
        f"{ASSET_NAME}_Manifest.json",
    ]
    file_status = {name: (output_dir / name).stat().st_size for name in expected_files if (output_dir / name).exists()}
    assert set(file_status) == set(expected_files), f"Missing output files: {sorted(set(expected_files) - set(file_status))}"
    assert all(size > 1024 for name, size in file_status.items() if not name.endswith(".json")), file_status

    report = {
        "status": "PASS",
        "blend": str(blend_path),
        "triangles": triangles,
        "bounds_min": [round(v, 4) for v in minimum],
        "bounds_max": [round(v, 4) for v in maximum],
        "dimensions": [round(v, 4) for v in dimensions],
        "animated_objects": animated,
        "required_objects": sorted(REQUIRED_OBJECTS),
        "file_sizes": file_status,
    }
    report_path = output_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"VALIDATION_PASS:{report_path}")


if __name__ == "__main__":
    main()
