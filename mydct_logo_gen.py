import bpy
import xml.etree.ElementTree as ET
import re
import os
import math
from mathutils import Vector, Matrix

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
SVG_FILENAME = "logo_final.svg"
EXTRUSION_DEPTH = 0.5  # Half-depth (Total thickness = 1.0)
BEVEL_DEPTH = 0.005    # Slight bevel for realism
SCALE_FACTOR = 0.01    # Scale down raw units to Blender units

# ------------------------------------------------------------------------------
# UI Helper
# ------------------------------------------------------------------------------
def show_message_box(message="", title="Message", icon='INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

def resolve_file_path(filename):
    blend_path = bpy.data.filepath
    if blend_path:
        base_dir = os.path.dirname(blend_path)
        full_path = os.path.join(base_dir, filename)
        if os.path.exists(full_path):
            return full_path

    cwd = os.getcwd()
    full_path = os.path.join(cwd, filename)
    if os.path.exists(full_path):
        return full_path
    return None

# ------------------------------------------------------------------------------
# Robust SVG Path Parser
# ------------------------------------------------------------------------------

def tokenize_path(d):
    # Standardize separator handling
    for char in "MmLlHhVvCcZz":
        d = d.replace(char, f" {char} ")
    d = d.replace(",", " ")
    tokens = d.split()
    return tokens

def is_number_token(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def parse_svg_path_to_splines(d_string):
    tokens = tokenize_path(d_string)

    splines = []
    current_spline = []

    cx, cy = 0.0, 0.0
    start_x, start_y = 0.0, 0.0

    # Command argument counts
    CMD_ARGS = {
        'M': 2, 'm': 2,
        'L': 2, 'l': 2,
        'H': 1, 'h': 1,
        'V': 1, 'v': 1,
        'C': 6, 'c': 6,
        'Z': 0, 'z': 0
    }

    i = 0
    current_cmd = None

    while i < len(tokens):
        token = tokens[i]

        # Check if it's a new command
        if token in CMD_ARGS:
            current_cmd = token
            i += 1
        else:
            # If not a command letter, it must be data for the *current* command
            # But implicit Move (M) becomes Line (L) for subsequent points
            if current_cmd in ['M', 'm']:
                current_cmd = 'L' if current_cmd == 'M' else 'l'
            # For others (L, H, V, C), we just repeat the current_cmd
            pass

        args_needed = CMD_ARGS.get(current_cmd, 0)

        # Z/z has 0 args, handle immediately
        if args_needed == 0:
            if current_cmd in ['Z', 'z']:
                if current_spline:
                    current_spline[0]['cyclic'] = True
                    cx, cy = start_x, start_y
            continue

        # Collect arguments
        args = []
        try:
            for _ in range(args_needed):
                if i >= len(tokens): break
                val = tokens[i]
                if not is_number_token(val): break # Should not happen if valid SVG
                args.append(float(val))
                i += 1
        except IndexError:
            break

        if len(args) < args_needed:
            # Not enough args, maybe end of string or malformed
            continue

        # Execute Command Logic
        # ---------------------
        cmd_key = current_cmd

        # Common Point Creation Helper
        def add_point(x, y, h1=None, h2=None, h_type='VECTOR'):
            # Update previous point's right handle if needed (for lines)
            if current_spline and h_type == 'VECTOR':
                current_spline[-1]['handle_right'] = current_spline[-1]['co'].copy()

            pt = {'co': Vector((x, y, 0)),
                  'handle_left': h1 if h1 else Vector((x, y, 0)),
                  'handle_right': h2 if h2 else Vector((x, y, 0)),
                  'type': h_type}
            current_spline.append(pt)

        if cmd_key in ['M', 'm']:
            # Start new subpath
            if current_spline:
                splines.append(current_spline)
            current_spline = []

            nx, ny = args[0], args[1]
            if cmd_key == 'm':
                nx += cx
                ny += cy

            cx, cy = nx, ny
            start_x, start_y = cx, cy
            add_point(cx, cy)

        elif cmd_key in ['L', 'l']:
            nx, ny = args[0], args[1]
            if cmd_key == 'l':
                nx += cx
                ny += cy
            cx, cy = nx, ny
            add_point(cx, cy)

        elif cmd_key in ['H', 'h']:
            val = args[0]
            nx = val if cmd_key == 'H' else (cx + val)
            ny = cy
            cx, cy = nx, ny
            add_point(cx, cy)

        elif cmd_key in ['V', 'v']:
            val = args[0]
            ny = val if cmd_key == 'V' else (cy + val)
            nx = cx
            cx, cy = nx, ny
            add_point(cx, cy)

        elif cmd_key in ['C', 'c']:
            # args: cp1x, cp1y, cp2x, cp2y, ex, ey
            cp1x, cp1y = args[0], args[1]
            cp2x, cp2y = args[2], args[3]
            ex, ey = args[4], args[5]

            if cmd_key == 'c':
                cp1x += cx; cp1y += cy
                cp2x += cx; cp2y += cy
                ex += cx; ey += cy

            # 1. Update previous point's handle_right to be CP1
            if current_spline:
                current_spline[-1]['handle_right'] = Vector((cp1x, cp1y, 0))
                current_spline[-1]['type'] = 'FREE'

            # 2. Add new point with handle_left as CP2
            cx, cy = ex, ey
            # Note: handle_right is placeholder, will be updated by next segment
            add_point(cx, cy, h1=Vector((cp2x, cp2y, 0)), h_type='FREE')

    if current_spline:
        splines.append(current_spline)

    return splines

def parse_svg_transform(transform_str):
    mat = Matrix.Identity(4)
    if not transform_str:
        return mat

    if 'matrix' in transform_str:
        try:
            content = re.search(r'matrix\((.*?)\)', transform_str).group(1)
            # Handle comma or space separation
            clean_content = content.replace(',', ' ')
            nums = [float(x) for x in clean_content.split()]
            a, b, c, d, e, f = nums

            # SVG Matrix:
            # [a c e]
            # [b d f]
            # Blender 4x4:
            m = Matrix((
                (a, c, 0, e),
                (b, d, 0, f),
                (0, 0, 1, 0),
                (0, 0, 0, 1)
            ))
            return m
        except:
            return mat
    return mat

def load_svg_data(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    # Process Groups (Transform) -> Paths
    all_splines = []

    # Check if namespace is needed
    has_ns = 'http://www.w3.org/2000/svg' in root.tag

    def process_element(elem, parent_matrix):
        # Calculate local matrix
        t_str = elem.get('transform')
        local_mat = parse_svg_transform(t_str)
        current_mat = parent_matrix @ local_mat

        # Check tag (ignoring namespace for simpler check)
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

        if tag == 'path':
            d = elem.get('d')
            if d:
                splines = parse_svg_path_to_splines(d)
                # Apply transform
                for spline in splines:
                    for pt in spline:
                        pt['co'] = current_mat @ pt['co']
                        pt['handle_left'] = current_mat @ pt['handle_left']
                        pt['handle_right'] = current_mat @ pt['handle_right']
                all_splines.extend(splines)

        for child in elem:
            process_element(child, current_mat)

    process_element(root, Matrix.Identity(4))
    return all_splines

# ------------------------------------------------------------------------------
# Blender Creation
# ------------------------------------------------------------------------------

def clean_scene():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for b in bpy.data.meshes: bpy.data.meshes.remove(b)
    for b in bpy.data.materials: bpy.data.materials.remove(b)
    for b in bpy.data.curves: bpy.data.curves.remove(b)

def create_curve_object(name, splines_data):
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '2D'
    curve_data.fill_mode = 'BOTH'
    curve_data.extrude = EXTRUSION_DEPTH
    curve_data.bevel_depth = BEVEL_DEPTH
    curve_data.bevel_resolution = 4

    for pt_list in splines_data:
        spline = curve_data.splines.new('BEZIER')
        is_cyclic = pt_list[0].get('cyclic', False)
        spline.use_cyclic_u = is_cyclic

        spline.bezier_points.add(len(pt_list) - 1)

        for i, pt in enumerate(pt_list):
            bpt = spline.bezier_points[i]
            bpt.co = pt['co'] * SCALE_FACTOR
            bpt.handle_left = pt['handle_left'] * SCALE_FACTOR
            bpt.handle_right = pt['handle_right'] * SCALE_FACTOR
            bpt.handle_left_type = pt['type']
            bpt.handle_right_type = pt['type']

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
    bsdf.inputs['Base Color'].default_value = (pow(r, 2.2), pow(g, 2.2), pow(b, 2.2), 1.0)
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
    svg_path = resolve_file_path(SVG_FILENAME)
    if not svg_path:
        msg = f"ERROR: Could not find '{SVG_FILENAME}'."
        print(msg)
        show_message_box(msg, icon='ERROR')
        return

    try:
        clean_scene()

        splines = load_svg_data(svg_path)
        print(f"Parsed {len(splines)} sub-paths.")

        mat_black = create_material("MYDCT_Black", "101010", roughness=0.2)
        mat_white = create_material("MYDCT_White_Plane", "FFFFFF", roughness=0.8)

        logo_obj = create_curve_object("MYDCT_Logo", splines)
        logo_obj.data.materials.append(mat_black)

        logo_obj.rotation_euler = (math.radians(90), 0, 0)

        (min_pos, max_pos) = get_bmesh_bbox([logo_obj])
        cx = (min_pos[0] + max_pos[0]) / 2
        cy = (min_pos[1] + max_pos[1]) / 2

        logo_obj.location.x -= cx
        logo_obj.location.y -= cy
        logo_obj.location.z -= min_pos[2]

        bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
        floor = bpy.context.active_object
        floor.name = "Infinity_Floor"
        floor.data.materials.append(mat_white)

        bpy.ops.object.light_add(type='AREA', location=(0, -20, 10))
        key = bpy.context.active_object
        key.data.energy = 5000
        key.data.size = 10
        key.rotation_euler = (math.radians(60), 0, 0)

        bpy.ops.object.camera_add(location=(0, -40, 5))
        cam = bpy.context.active_object
        cam.rotation_euler = (math.radians(85), 0, 0)
        bpy.context.scene.camera = cam

        show_message_box("Logo Generated Successfully", icon='CHECKMARK')

    except Exception as e:
        import traceback
        traceback.print_exc()
        show_message_box(f"Error: {e}", icon='ERROR')

if __name__ == "__main__":
    main()
