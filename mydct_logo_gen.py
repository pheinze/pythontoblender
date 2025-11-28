import bpy
import xml.etree.ElementTree as ET
import re
import os
import math
from mathutils import Vector

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
SVG_FILE = "logo2.svg"
EXTRUSION_DEPTH = 0.5  # Half-depth (Total thickness = 1.0)
BEVEL_DEPTH = 0.005    # Slight bevel for realism
SCALE_FACTOR = 0.01    # Scale down SVG coordinates to reasonable Blender units

# ------------------------------------------------------------------------------
# SVG Parsing Logic
# ------------------------------------------------------------------------------
def parse_svg_path(d_string):
    """
    Parses a simple SVG path string containing M (Move), L (Line), and Z (Close).
    Returns a list of polygons (lists of (x,y) tuples).
    """
    # Normalize string: insert spaces around commands to make splitting easier
    d_string = d_string.replace(',', ' ')
    for cmd in ['M', 'L', 'Z', 'm', 'l', 'z']:
        d_string = d_string.replace(cmd, f' {cmd} ')

    tokens = d_string.split()

    polygons = []
    current_poly = []

    i = 0
    current_x = 0.0
    current_y = 0.0

    while i < len(tokens):
        cmd = tokens[i]

        if cmd == 'M': # Move Absolute
            if current_poly:
                polygons.append(current_poly)
                current_poly = []
            x = float(tokens[i+1])
            y = float(tokens[i+2])
            current_poly.append((x, y))
            current_x, current_y = x, y
            i += 3

        elif cmd == 'L': # Line Absolute
            x = float(tokens[i+1])
            y = float(tokens[i+2])
            current_poly.append((x, y))
            current_x, current_y = x, y
            i += 3

        elif cmd == 'Z' or cmd == 'z': # Close
            if current_poly:
                polygons.append(current_poly)
                current_poly = []
            i += 1

        else:
            # Handle numbers that might be implicit commands or part of a sequence
            # Check if it's a number (including negative)
            if is_number(cmd):
                 # Implicit LineTo (L)
                x = float(tokens[i])
                y = float(tokens[i+1])
                current_poly.append((x, y))
                current_x, current_y = x, y
                i += 2
            else:
                # Unknown token, skip
                i += 1

    if current_poly:
        polygons.append(current_poly)

    return polygons

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def extract_transform_translate(transform_str):
    """Extracts (tx, ty) from string 'translate(1293,906)'"""
    if not transform_str:
        return (0, 0)
    match = re.search(r'translate\(\s*([-\d.]+)\s*[,\s]\s*([-\d.]+)\s*\)', transform_str)
    if match:
        return (float(match.group(1)), float(match.group(2)))
    return (0, 0)

def load_svg_data(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    paths = root.findall('.//svg:path', ns)
    if not paths:
        paths = root.findall('.//path')

    shapes = []

    for p in paths:
        d = p.get('d')
        transform = p.get('transform')
        tx, ty = extract_transform_translate(transform)

        polys = parse_svg_path(d)

        # Apply translation and coordinate system change
        # SVG: Y down. Blender: Z up.
        # We map SVG X -> X, SVG Y -> -Y (temporarily) -> later mapped to Z

        offset_polys = []
        for poly in polys:
            new_poly = []
            for (px, py) in poly:
                final_x = px + tx
                final_y = py + ty
                # Invert Y here so shapes aren't upside down relative to each other
                new_poly.append((final_x, -final_y))
            offset_polys.append(new_poly)

        shapes.append(offset_polys)

    return shapes

# ------------------------------------------------------------------------------
# Blender Geometry Creation
# ------------------------------------------------------------------------------

def clean_scene():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    for block in bpy.data.meshes: bpy.data.meshes.remove(block)
    for block in bpy.data.materials: bpy.data.materials.remove(block)
    for block in bpy.data.curves: bpy.data.curves.remove(block)

def create_curve_from_points(name, polys):
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '2D'
    curve_data.fill_mode = 'BOTH'
    curve_data.extrude = EXTRUSION_DEPTH
    curve_data.bevel_depth = BEVEL_DEPTH
    curve_data.bevel_resolution = 4

    for points in polys:
        spline = curve_data.splines.new('POLY')
        spline.use_cyclic_u = True
        spline.points.add(len(points) - 1)
        for i, (x, y) in enumerate(points):
            spline.points[i].co = (x * SCALE_FACTOR, y * SCALE_FACTOR, 0.0, 1.0)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    return obj

def create_material(name, hex_color, roughness=0.4):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    color = (pow(r, 2.2), pow(g, 2.2), pow(b, 2.2), 1.0)

    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = roughness
    return mat

def get_bmesh_bbox(objects):
    """Calculates the bounding box of a list of objects."""
    min_x, min_y, min_z = float('inf'), float('inf'), float('inf')
    max_x, max_y, max_z = float('-inf'), float('-inf'), float('-inf')

    for obj in objects:
        # Update scene to ensure matrices are ready
        bpy.context.view_layer.update()
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            min_x = min(min_x, world_corner.x)
            min_y = min(min_y, world_corner.y)
            min_z = min(min_z, world_corner.z)
            max_x = max(max_x, world_corner.x)
            max_y = max(max_y, world_corner.y)
            max_z = max(max_z, world_corner.z)

    return (min_x, min_y, min_z), (max_x, max_y, max_z)

def main():
    clean_scene()

    # 1. Load Data
    if not os.path.exists(SVG_FILE):
        print(f"Error: {SVG_FILE} not found.")
        return

    shapes = load_svg_data(SVG_FILE)
    print(f"Found {len(shapes)} shapes in SVG.")

    # 2. Materials
    mat_black = create_material("MYDCT_Black", "101010", roughness=0.2)
    mat_white = create_material("MYDCT_White_Plane", "FFFFFF", roughness=0.8)

    # 3. Create Objects
    logo_objs = []
    for i, shape_polys in enumerate(shapes):
        obj = create_curve_from_points(f"Logo_Part_{i}", shape_polys)
        obj.data.materials.append(mat_black)
        logo_objs.append(obj)

    # 4. Group and Re-Center
    # Parent them
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0))
    parent = bpy.context.active_object
    parent.name = "MYDCT_Logo_Group"

    for obj in logo_objs:
        obj.parent = parent

    # Rotate first to stand up
    # SVG Y is inverted to be -Y in world (mapped to X/Y plane initially).
    # To stand up facing front: Rotate X by 90.
    parent.rotation_euler = (math.radians(90), 0, 0)

    # Now Calculate Bounding Box of the whole group in World Space
    # We must deselect all and select only logo parts for bbox calculation if needed,
    # or just iterate manually.

    (min_pos, max_pos) = get_bmesh_bbox(logo_objs)

    # Calculate Center
    center_x = (min_pos[0] + max_pos[0]) / 2
    center_y = (min_pos[1] + max_pos[1]) / 2
    center_z = (min_pos[2] + max_pos[2]) / 2

    # Dimensions
    size_z = max_pos[2] - min_pos[2]

    # Move Parent to compensate
    # We want the geometric center X to be at 0
    # We want the bottom (min Z) to be at 0 (on the floor)

    # Current World Position of Geometry Center is (center_x, center_y, center_z)
    # The parent is at (0,0,0). Moving the parent moves the children.
    # New Parent Loc = Old Parent Loc - Center + Offset

    parent.location.x -= center_x
    parent.location.y -= center_y # Keep centered on Y axis too
    parent.location.z -= min_pos[2] # Align bottom to floor

    print(f"Recentered Logo. Width: {max_pos[0]-min_pos[0]:.2f}, Height: {size_z:.2f}")

    # 5. Environment
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Infinity_Floor"
    floor.data.materials.append(mat_white)

    # Lighting
    bpy.ops.object.light_add(type='AREA', location=(0, -20, 10))
    key = bpy.context.active_object
    key.data.energy = 5000
    key.data.size = 10
    key.rotation_euler = (math.radians(60), 0, 0)

    bpy.ops.object.camera_add(location=(0, -40, 5))
    cam = bpy.context.active_object
    cam.rotation_euler = (math.radians(85), 0, 0)
    bpy.context.scene.camera = cam

    print("Generation Complete.")

if __name__ == "__main__":
    main()
