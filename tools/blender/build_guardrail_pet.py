"""Build the ContextGuard chibi robot in Blender and export a skinned GLB."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT_GLB = ROOT / "apps" / "web-src" / "src" / "assets" / "pet" / "guardrail-pet.glb"
OUT_BLEND = ROOT / "assets" / "blender" / "guardrail-pet.blend"
OUT_PREVIEW = ROOT / "assets" / "blender" / "guardrail-pet-preview.png"

FPS = 24
DEG = math.pi / 180.0

BODY = (0.078, 0.078, 0.082, 1.0)
BEZEL = (0.145, 0.145, 0.150, 1.0)
SCREEN = (0.012, 0.012, 0.014, 1.0)
GLOW = (1.0, 0.78, 0.12, 1.0)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablock in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.armatures, bpy.data.actions, bpy.data.cameras, bpy.data.lights):
        for item in list(datablock):
            datablock.remove(item)


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def set_active_object_mode():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def apply_object(obj):
    select_only(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def shade_smooth(obj):
    select_only(obj)
    bpy.ops.object.shade_smooth()
    for poly in obj.data.polygons:
        poly.use_smooth = True


def add_bevel_subdiv(obj, width=0.04, segments=4, levels=2):
    select_only(obj)
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = width
    bevel.segments = segments
    bevel.limit_method = "ANGLE"
    subdiv = obj.modifiers.new("Subsurf", "SUBSURF")
    subdiv.levels = levels
    subdiv.render_levels = levels
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    bpy.ops.object.modifier_apply(modifier=subdiv.name)


def new_material(name, color, roughness=0.42, metallic=0.08, emission=None, emission_strength=0.0, coat=0.12):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    if principled is None:
        return mat

    def set_input(key, value):
        socket = principled.inputs.get(key)
        if socket is not None:
            socket.default_value = value

    set_input("Base Color", color)
    set_input("Roughness", roughness)
    set_input("Metallic", metallic)
    set_input("Coat Weight", coat)
    set_input("Coat Roughness", 0.35)
    set_input("Specular IOR Level", 0.45)
    if emission is not None:
        set_input("Emission Color", emission)
        set_input("Emission Strength", emission_strength)
        # Older node layouts
        if principled.inputs.get("Emission") is not None and principled.inputs.get("Emission Color") is None:
            principled.inputs["Emission"].default_value = emission
    return mat


def assign_mat(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def make_cube(name, location, scale, mat, bevel=0.05, levels=2):
    bpy.ops.mesh.primitive_cube_add(size=2, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_object(obj)
    add_bevel_subdiv(obj, width=bevel, levels=levels)
    shade_smooth(obj)
    assign_mat(obj, mat)
    return obj


def make_capsule(name, location, radius, length, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=28, ring_count=16)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (1.0, 1.0, max(length / (2 * radius), 1.2))
    apply_object(obj)
    shade_smooth(obj)
    assign_mat(obj, mat)
    return obj


def make_sphere(name, location, radius, mat, scale=(1, 1, 1), segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=segments, ring_count=16)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_object(obj)
    shade_smooth(obj)
    assign_mat(obj, mat)
    return obj


def make_cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0), vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, rotation=rotation, vertices=vertices)
    obj = bpy.context.object
    obj.name = name
    apply_object(obj)
    add_bevel_subdiv(obj, width=min(radius, depth) * 0.18, segments=3, levels=1)
    shade_smooth(obj)
    assign_mat(obj, mat)
    return obj


def make_smile(name, location, mat):
    curve_data = bpy.data.curves.new(name + "_curve", "CURVE")
    curve_data.dimensions = "3D"
    curve_data.bevel_depth = 0.018
    curve_data.bevel_resolution = 6
    curve_data.fill_mode = "FULL"
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(2)
    coords = [(-0.105, 0.0, 0.04), (0.0, 0.0, -0.055), (0.105, 0.0, 0.04)]
    for i, co in enumerate(coords):
        point = spline.bezier_points[i]
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    select_only(obj)
    bpy.ops.object.convert(target="MESH")
    shade_smooth(obj)
    assign_mat(obj, mat)
    return obj


def make_empty(name, location):
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=location)
    obj = bpy.context.object
    obj.name = name
    obj.empty_display_size = 0.05
    return obj


def skin_to_bone(obj, armature, bone_name):
    set_active_object_mode()
    select_only(obj)
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    group = obj.vertex_groups.new(name=bone_name)
    group.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")
    for modifier in list(obj.modifiers):
        if modifier.type == "ARMATURE":
            obj.modifiers.remove(modifier)
    armature_mod = obj.modifiers.new(name="Armature", type="ARMATURE")
    armature_mod.object = armature
    armature_mod.use_vertex_groups = True
    obj.parent = armature


def parent_keep_world(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    child.matrix_world = world


def build_materials():
    return {
        "body": new_material("PetBody", BODY, roughness=0.48, metallic=0.04, coat=0.18),
        "bezel": new_material("PetBezel", BEZEL, roughness=0.40, metallic=0.06, coat=0.22),
        "screen": new_material("PetScreen", SCREEN, roughness=0.22, metallic=0.0, coat=0.05),
        "glow": new_material("PetGlow", GLOW, roughness=0.25, metallic=0.0, emission=GLOW, emission_strength=18.0, coat=0.0),
        "glow_dim": new_material("PetGlowDim", (0.35, 0.28, 0.08, 1.0), roughness=0.3, metallic=0.0, emission=(0.45, 0.34, 0.08, 1.0), emission_strength=2.2, coat=0.0),
    }


def build_meshes(mats):
    head = make_cube("HeadShell", (0.0, 0.0, 0.82), (0.40, 0.26, 0.33), mats["bezel"], bevel=0.09, levels=2)
    screen = make_cube("HeadScreen", (0.0, -0.205, 0.82), (0.30, 0.04, 0.24), mats["screen"], bevel=0.03, levels=2)

    antenna_l = make_sphere("Antenna_L", (-0.16, 0.0, 1.18), 0.045, mats["body"])
    antenna_r = make_sphere("Antenna_R", (0.16, 0.0, 1.18), 0.045, mats["body"])

    ear_l = make_cylinder("Ear_L", (-0.42, 0.0, 0.82), 0.11, 0.08, mats["body"], rotation=(0.0, math.pi / 2, 0.0))
    ear_r = make_cylinder("Ear_R", (0.42, 0.0, 0.82), 0.11, 0.08, mats["body"], rotation=(0.0, math.pi / 2, 0.0))
    ear_cap_l = make_sphere("EarCap_L", (-0.46, 0.0, 0.82), 0.07, mats["bezel"], scale=(0.45, 1.0, 1.0))
    ear_cap_r = make_sphere("EarCap_R", (0.46, 0.0, 0.82), 0.07, mats["bezel"], scale=(0.45, 1.0, 1.0))

    body = make_sphere("Body", (0.0, 0.0, 0.40), 0.20, mats["body"], scale=(1.08, 0.95, 1.12))
    arm_l = make_capsule("Arm_L", (-0.34, 0.02, 0.32), 0.07, 0.30, mats["body"])
    arm_r = make_capsule("Arm_R", (0.34, 0.02, 0.32), 0.07, 0.30, mats["body"])
    leg_l = make_capsule("Leg_L", (-0.12, 0.02, 0.14), 0.075, 0.28, mats["body"])
    leg_r = make_capsule("Leg_R", (0.12, 0.02, 0.14), 0.075, 0.28, mats["body"])

    face_happy = make_empty("PetFace_Happy", (0.0, -0.25, 0.82))
    eye_l = make_sphere("HappyEye_L", (-0.09, -0.255, 0.86), 0.055, mats["glow"], segments=24)
    eye_r = make_sphere("HappyEye_R", (0.09, -0.255, 0.86), 0.055, mats["glow"], segments=24)
    smile = make_smile("HappySmile", (0.0, -0.255, 0.755), mats["glow"])
    for piece in (eye_l, eye_r, smile):
        parent_keep_world(piece, face_happy)

    face_sad = make_empty("PetFace_Sad", (0.0, -0.25, 0.82))
    sad_l = make_cube("SadEye_L", (-0.09, -0.255, 0.86), (0.07, 0.018, 0.018), mats["glow"], bevel=0.01, levels=1)
    sad_r = make_cube("SadEye_R", (0.09, -0.255, 0.86), (0.07, 0.018, 0.018), mats["glow"], bevel=0.01, levels=1)
    for piece in (sad_l, sad_r):
        parent_keep_world(piece, face_sad)

    face_boring = make_empty("PetFace_Boring", (0.0, -0.25, 0.82))
    bore_l = make_cube("BoreEye_L", (-0.09, -0.255, 0.87), (0.07, 0.018, 0.016), mats["glow"], bevel=0.01, levels=1)
    bore_r = make_cube("BoreEye_R", (0.09, -0.255, 0.87), (0.07, 0.018, 0.016), mats["glow"], bevel=0.01, levels=1)
    bore_mouth = make_cube("BoreMouth", (0.0, -0.255, 0.76), (0.08, 0.016, 0.014), mats["glow"], bevel=0.008, levels=1)
    for piece in (bore_l, bore_r, bore_mouth):
        parent_keep_world(piece, face_boring)

    face_doubt = make_empty("PetFace_Doubt", (0.0, -0.25, 0.82))
    doubt_round = make_sphere("DoubtEye_L", (-0.09, -0.255, 0.86), 0.05, mats["glow"], segments=24)
    doubt_flat = make_cube("DoubtEye_R", (0.09, -0.255, 0.86), (0.07, 0.018, 0.016), mats["glow"], bevel=0.01, levels=1)
    for piece in (doubt_round, doubt_flat):
        parent_keep_world(piece, face_doubt)

    face_battery = make_empty("PetFace_Battery", (0.0, -0.25, 0.82))
    batt_body = make_cube("BatteryBody", (0.0, -0.255, 0.82), (0.13, 0.02, 0.18), mats["glow"], bevel=0.02, levels=1)
    batt_nip = make_cube("BatteryNipple", (0.0, -0.255, 1.01), (0.05, 0.016, 0.03), mats["glow"], bevel=0.01, levels=1)
    batt_fill = make_cube("BatteryFill", (0.0, -0.268, 0.72), (0.09, 0.012, 0.045), mats["glow"], bevel=0.008, levels=1)
    batt_empty_a = make_cube("BatteryEmptyA", (0.0, -0.268, 0.82), (0.09, 0.01, 0.04), mats["glow_dim"], bevel=0.006, levels=1)
    batt_empty_b = make_cube("BatteryEmptyB", (0.0, -0.268, 0.91), (0.09, 0.01, 0.04), mats["glow_dim"], bevel=0.006, levels=1)
    for piece in (batt_body, batt_nip, batt_fill, batt_empty_a, batt_empty_b):
        parent_keep_world(piece, face_battery)

    head_parts = [head, screen, antenna_l, antenna_r, ear_l, ear_r, ear_cap_l, ear_cap_r]
    face_roots = [face_happy, face_sad, face_boring, face_doubt, face_battery]
    return {
        "head_parts": head_parts,
        "body": body,
        "arm_l": arm_l,
        "arm_r": arm_r,
        "leg_l": leg_l,
        "leg_r": leg_r,
        "face_roots": face_roots,
    }


def build_armature():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0.0, 0.0, 0.0))
    arm_obj = bpy.context.object
    arm_obj.name = "PetArmature"
    arm = arm_obj.data
    arm.name = "PetRig"

    bpy.ops.armature.select_all(action="SELECT")
    bpy.ops.armature.delete()

    def add_bone(name, head, tail, parent=None):
        bone = arm.edit_bones.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.use_deform = True
        if parent is not None:
            bone.parent = arm.edit_bones[parent]
            bone.use_connect = False
        return bone

    add_bone("Root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.16))
    add_bone("Torso", (0.0, 0.0, 0.18), (0.0, 0.0, 0.46), "Root")
    add_bone("Head", (0.0, 0.0, 0.50), (0.0, 0.0, 0.98), "Torso")
    add_bone("Arm_L", (-0.30, 0.0, 0.42), (-0.30, 0.0, 0.18), "Torso")
    add_bone("Arm_R", (0.30, 0.0, 0.42), (0.30, 0.0, 0.18), "Torso")
    add_bone("Leg_L", (-0.11, 0.0, 0.18), (-0.11, 0.0, 0.02), "Torso")
    add_bone("Leg_R", (0.11, 0.0, 0.18), (0.11, 0.0, 0.02), "Torso")

    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def bind_meshes(parts, armature):
    for obj in parts["head_parts"]:
        skin_to_bone(obj, armature, "Head")
    for face in parts["face_roots"]:
        world = face.matrix_world.copy()
        face.parent = armature
        face.parent_type = "BONE"
        face.parent_bone = "Head"
        face.matrix_world = world
    skin_to_bone(parts["body"], armature, "Torso")
    skin_to_bone(parts["arm_l"], armature, "Arm_L")
    skin_to_bone(parts["arm_r"], armature, "Arm_R")
    skin_to_bone(parts["leg_l"], armature, "Leg_L")
    skin_to_bone(parts["leg_r"], armature, "Leg_R")


def eul(*xyz_deg):
    return Euler((xyz_deg[0] * DEG, xyz_deg[1] * DEG, xyz_deg[2] * DEG), "XYZ")


def zero_pose():
    return {
        "Root": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Torso": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Head": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Arm_L": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Arm_R": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Leg_L": (Vector((0, 0, 0)), eul(0, 0, 0)),
        "Leg_R": (Vector((0, 0, 0)), eul(0, 0, 0)),
    }


def apply_pose(armature, pose_map):
    for name, (loc, rot) in pose_map.items():
        bone = armature.pose.bones[name]
        bone.rotation_mode = "XYZ"
        bone.location = loc
        bone.rotation_euler = rot


def insert_pose(armature, frame, pose_map):
    apply_pose(armature, pose_map)
    for name in pose_map:
        bone = armature.pose.bones[name]
        bone.keyframe_insert(data_path="location", frame=frame)
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def set_interpolation(action, mode):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = mode


def merge_pose(base, **overrides):
    pose = {k: (v[0].copy(), v[1].copy()) for k, v in base.items()}
    for name, (loc, rot) in overrides.items():
        pose[name] = (loc, rot)
    return pose


def make_action(armature, name, frames, interpolation="BEZIER"):
    action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    rest = zero_pose()
    for frame, overrides in frames:
        insert_pose(armature, frame, merge_pose(rest, **overrides))
    set_interpolation(action, interpolation)
    action.use_frame_range = True
    action.frame_start = float(frames[0][0])
    action.frame_end = float(frames[-1][0])
    action.use_cyclic = True
    return action


def build_animations(armature):
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 48

    sit_legs = {
        "Root": (Vector((0.0, 0.04, -0.02)), eul(8, 0, 0)),
        "Torso": (Vector((0, 0, -0.02)), eul(6, 0, 0)),
        "Head": (Vector((0, 0, 0)), eul(-4, 0, 0)),
        "Arm_L": (Vector((0.02, 0.04, 0.0)), eul(55, 0, 18)),
        "Arm_R": (Vector((-0.02, 0.04, 0.0)), eul(55, 0, -18)),
        "Leg_L": (Vector((0.0, 0.08, 0.02)), eul(82, 0, -8)),
        "Leg_R": (Vector((0.0, 0.08, 0.02)), eul(82, 0, 8)),
    }
    sit_bob = dict(sit_legs)
    sit_bob["Root"] = (Vector((0.0, 0.04, -0.008)), eul(8, 0, 0))
    make_action(armature, "sit", [(1, sit_legs), (24, sit_bob), (48, sit_legs)])

    def walk_pose(amp, bounce):
        return {
            "Root": (Vector((0.0, 0.0, bounce)), eul(6, 0, amp * 4)),
            "Torso": (Vector((0, 0, 0)), eul(8, 0, amp * 6)),
            "Head": (Vector((0, 0, 0)), eul(-4, 0, -amp * 8)),
            "Arm_L": (Vector((0, 0, 0)), eul(-amp * 38, 0, 8)),
            "Arm_R": (Vector((0, 0, 0)), eul(amp * 38, 0, -8)),
            "Leg_L": (Vector((0.0, amp * 0.04, 0.0)), eul(amp * 42, 0, 0)),
            "Leg_R": (Vector((0.0, -amp * 0.04, 0.0)), eul(-amp * 42, 0, 0)),
        }

    make_action(
        armature,
        "walk",
        [
            (1, walk_pose(1, 0.0)),
            (7, walk_pose(0, 0.03)),
            (13, walk_pose(-1, 0.0)),
            (19, walk_pose(0, 0.03)),
            (25, walk_pose(1, 0.0)),
        ],
        interpolation="LINEAR",
    )

    play_a = {
        "Root": (Vector((0.0, 0.0, 0.04)), eul(8, 0, 18)),
        "Torso": (Vector((0, 0, 0)), eul(10, 0, 12)),
        "Head": (Vector((0, 0, 0)), eul(-6, 0, 16)),
        "Arm_L": (Vector((0, 0, 0.04)), eul(-20, 0, 10)),
        "Arm_R": (Vector((0, 0, 0.08)), eul(-110, 0, -20)),
        "Leg_L": (Vector((0, 0, 0.03)), eul(18, 0, -10)),
        "Leg_R": (Vector((0, 0, 0.0)), eul(-8, 0, 12)),
    }
    play_b = {
        "Root": (Vector((0.0, 0.0, 0.07)), eul(4, 0, -16)),
        "Torso": (Vector((0, 0, 0)), eul(6, 0, -10)),
        "Head": (Vector((0, 0, 0)), eul(-8, 0, -14)),
        "Arm_L": (Vector((0, 0, 0.08)), eul(-100, 0, 16)),
        "Arm_R": (Vector((0, 0, 0.03)), eul(-18, 0, -8)),
        "Leg_L": (Vector((0, 0, 0.0)), eul(-10, 0, -8)),
        "Leg_R": (Vector((0, 0, 0.04)), eul(16, 0, 10)),
    }
    make_action(armature, "play", [(1, play_a), (16, play_b), (32, play_a)])

    happy_a = {
        "Root": (Vector((0, 0, 0.01)), eul(0, 0, 0)),
        "Head": (Vector((0, 0, 0)), eul(-6, 0, 8)),
        "Arm_R": (Vector((0, 0, 0.02)), eul(-125, 0, -15)),
        "Arm_L": (Vector((0, 0, 0)), eul(12, 0, 10)),
    }
    happy_b = {
        "Root": (Vector((0, 0, 0.03)), eul(0, 0, 0)),
        "Head": (Vector((0, 0, 0)), eul(-4, 0, -8)),
        "Arm_R": (Vector((0, 0, 0.04)), eul(-150, 0, 18)),
        "Arm_L": (Vector((0, 0, 0)), eul(8, 0, 6)),
    }
    make_action(armature, "happy", [(1, happy_a), (12, happy_b), (24, happy_a)])

    sad = {
        "Root": (Vector((0, 0.02, -0.02)), eul(10, 0, 0)),
        "Torso": (Vector((0, 0, 0)), eul(8, 0, 0)),
        "Head": (Vector((0, 0, -0.02)), eul(22, 0, -10)),
        "Arm_L": (Vector((0, 0.03, 0)), eul(18, 0, 8)),
        "Arm_R": (Vector((0, 0.03, 0)), eul(18, 0, -8)),
        "Leg_L": (Vector((0, 0, 0)), eul(4, 0, 0)),
        "Leg_R": (Vector((0, 0, 0)), eul(4, 0, 0)),
    }
    sad_b = merge_pose(zero_pose(), **{**sad, "Head": (Vector((0, 0, -0.02)), eul(26, 0, -6))})
    make_action(armature, "sad", [(1, sad), (24, sad_b), (48, sad)])

    boring = {
        "Head": (Vector((0, 0, -0.01)), eul(4, 0, 0)),
        "Arm_L": (Vector((0, 0, 0)), eul(6, 0, 4)),
        "Arm_R": (Vector((0, 0, 0)), eul(6, 0, -4)),
    }
    make_action(armature, "boring", [(1, boring), (36, boring)])

    doubt_a = {
        "Head": (Vector((0, 0, 0)), eul(4, 0, 18)),
        "Torso": (Vector((0, 0, 0)), eul(0, 0, 6)),
        "Arm_L": (Vector((0, 0, 0)), eul(-8, 0, 12)),
        "Arm_R": (Vector((0, 0, 0.02)), eul(-35, 0, -8)),
    }
    doubt_b = {
        "Head": (Vector((0, 0, 0)), eul(2, 0, 12)),
        "Torso": (Vector((0, 0, 0)), eul(0, 0, 4)),
        "Arm_L": (Vector((0, 0, 0)), eul(-4, 0, 8)),
        "Arm_R": (Vector((0, 0, 0.01)), eul(-28, 0, -6)),
    }
    make_action(armature, "doubt", [(1, doubt_a), (20, doubt_b), (40, doubt_a)])

    make_action(
        armature,
        "low-battery",
        [
            (1, sit_legs),
            (16, merge_pose(zero_pose(), **{**sit_legs, "Head": (Vector((0, 0, -0.01)), eul(6, 0, 0))})),
            (32, sit_legs),
        ],
    )

    # Leave a default action so the file opens in a sensible pose.
    armature.animation_data.action = bpy.data.actions.get("sit")


def setup_preview_camera():
    bpy.ops.object.camera_add(location=(1.15, -2.35, 0.82), rotation=(math.radians(73), 0.0, math.radians(22)))
    camera = bpy.context.object
    camera.name = "PreviewCamera"
    camera.data.lens = 50
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(1.4, -1.6, 2.2))
    key = bpy.context.object
    key.data.energy = 250
    key.data.size = 1.8
    key.rotation_euler = (math.radians(50), math.radians(15), math.radians(20))

    bpy.ops.object.light_add(type="AREA", location=(-1.6, -0.4, 1.4))
    fill = bpy.context.object
    fill.data.energy = 90
    fill.data.size = 2.2

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.03, 0.03, 0.032, 1.0)
        bg.inputs[1].default_value = 1.0


def export_glb(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    kwargs = {
        "filepath": str(path),
        "export_format": "GLB",
        "use_selection": False,
        "export_apply": True,
        "export_animations": True,
        "export_extras": True,
        "export_cameras": False,
        "export_lights": False,
    }
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_animation_mode="ACTIONS")
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)


def render_preview(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True
    scene.frame_set(1)
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as exc:
        print("Preview render skipped:", exc)


def main():
    clear_scene()
    mats = build_materials()
    parts = build_meshes(mats)
    armature = build_armature()
    bind_meshes(parts, armature)
    build_animations(armature)
    setup_preview_camera()

    OUT_BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    export_glb(OUT_GLB)

    happy = next(obj for obj in bpy.data.objects if obj.name == "PetFace_Happy")
    for face in parts["face_roots"]:
        visible = face is happy
        face.hide_render = not visible
        for child in face.children:
            child.hide_render = not visible
            child.hide_viewport = not visible
    armature.animation_data.action = bpy.data.actions.get("sit")
    bpy.context.scene.frame_set(12)
    bpy.context.view_layer.update()
    render_preview(OUT_PREVIEW)
    print("Wrote", OUT_GLB)
    print("Wrote", OUT_BLEND)
    print("Actions:", [action.name for action in bpy.data.actions])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
