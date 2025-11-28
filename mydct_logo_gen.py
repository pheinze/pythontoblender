import bpy
import xml.etree.ElementTree as ET
import re
import os
import math
from mathutils import Vector

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
SVG_FILENAME = "logo2.svg"
EXTRUSION_DEPTH = 0.5  # Half-depth (Total thickness = 1.0)
BEVEL_DEPTH = 0.005    # Slight bevel for realism
SCALE_FACTOR = 0.01    # Scale down SVG coordinates to reasonable Blender units

# ------------------------------------------------------------------------------
# Helper: UI Messages
# ------------------------------------------------------------------------------
def show_message_box(message="", title="Message", icon='INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

def resolve_file_path(filename):
    """
    Attempts to find the file in:
    1. The same directory as the currently open .blend file.
    2. The current working directory.
    """
    # 1. Check relative to .blend file
    blend_path = bpy.data.filepath
    if blend_path:
        base_dir = os.path.dirname(blend_path)
        full_path = os.path.join(base_dir, filename)
        if os.path.exists(full_path):
            print(f"Found {filename} at: {full_path}")
            return full_path

    # 2. Check current working directory
    cwd = os.getcwd()
    full_path = os.path.join(cwd, filename)
    if os.path.exists(full_path):
        print(f"Found {filename} in CWD: {full_path}")
        return full_path

    return None

# ------------------------------------------------------------------------------
# SVG Parsing Logic
# ------------------------------------------------------------------------------
def parse_svg_path(d_string):
    d_string = d_string.replace(',', ' ')
    for cmd in ['M', 'L', 'Z', 'm', 'l', 'z']:
        d_string = d_string.replace(cmd, f' {cmd} ')

    tokens = d_string.split()
    polygons = []
    current_poly = []

    i = 0
    current_x, current_y = 0.0, 0.0

    while i < len(tokens):
        cmd = tokens[i]

        if cmd == 'M':
            if current_poly:
                polygons.append(current_poly)
                current_poly = []
            x = float(tokens[i+1])
            y = float(tokens[i+2])
            current_poly.append((x, y))
            current_x, current_y = x, y
            i += 3
        elif cmd == 'L':
            x = float(tokens[i+1])
            y = float(tokens[i+2])
            current_poly.append((x, y))
            current_x, current_y = x, y
            i += 3
        elif cmd == 'Z' or cmd == 'z':
            if current_poly:
                polygons.append(current_poly)
                current_poly = []
            i += 1
        else:
            if is_number(cmd):
                x = float(tokens[i])
                y = float(tokens[i+1])
                current_poly.append((x, y))
                current_x, current_y = x, y
                i += 2
            else:
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
    if not transform_str: return (0, 0)
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

        offset_polys = []
        for poly in polys:
            new_poly = []
            for (px, py) in poly:
                final_x = px + tx
                final_y = py + ty
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
    min_x, min_y, min_z = float('inf'), float('inf'), float('inf')
    max_x, max_y, max_z = float('-inf'), float('-inf'), float('-inf')

    bpy.context.view_layer.update()
    for obj in objects:
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
    # 1. Resolve File Path
    svg_path = resolve_file_path(SVG_FILENAME)

    if not svg_path:
        msg = f"ERROR: Could not find '{SVG_FILENAME}'. Please save your .blend file in the same folder as the SVG."
        print(msg)
        show_message_box(message=msg, title="File Not Found", icon='ERROR')
        return

    # 2. Execution
    try:
        clean_scene()
        shapes = load_svg_data(svg_path)
        print(f"Found {len(shapes)} shapes in SVG.")

        mat_black = create_material("MYDCT_Black", "101010", roughness=0.2)
        mat_white = create_material("MYDCT_White_Plane", "FFFFFF", roughness=0.8)

        logo_objs = []
        for i, shape_polys in enumerate(shapes):
            obj = create_curve_from_points(f"Logo_Part_{i}", shape_polys)
            obj.data.materials.append(mat_black)
            logo_objs.append(obj)

        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0))
        parent = bpy.context.active_object
        parent.name = "MYDCT_Logo_Group"

        for obj in logo_objs:
            obj.parent = parent

        parent.rotation_euler = (math.radians(90), 0, 0)

        (min_pos, max_pos) = get_bmesh_bbox(logo_objs)
        center_x = (min_pos[0] + max_pos[0]) / 2
        center_y = (min_pos[1] + max_pos[1]) / 2

        parent.location.x -= center_x
        parent.location.y -= center_y
        parent.location.z -= min_pos[2]

        # Floor
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

        show_message_box("Logo successfully generated!", title="Success", icon='CHECKMARK')

    except Exception as e:
        import traceback
        traceback.print_exc()
        show_message_box(f"Error: {str(e)}", title="Script Error", icon='ERROR')

if __name__ == "__main__":
    main()
