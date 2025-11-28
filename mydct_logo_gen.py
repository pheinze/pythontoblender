import bpy
import bmesh
import math
from mathutils import Vector, Euler

# ------------------------------------------------------------------------------
# 1. Constants & Configuration
# ------------------------------------------------------------------------------

PHI = 1.61803398875
HEIGHT = 8.0
STROKE = 3.0       # Thick, "Heavy" stroke
EXTRUSION = 1.5    # Depth of the 3D text (half-depth in Blender Curve, total is 2x)
BEVEL_DEPTH = 0.05 # Razor sharp but catches light

# Widths based on Fibonacci approximations relative to Height=8
WIDTH_WIDE = 13.0
WIDTH_STD = 8.0

# Spacing
KERNING = STROKE / PHI  # 3 / 1.618 = ~1.85

# ------------------------------------------------------------------------------
# 2. Helper Functions
# ------------------------------------------------------------------------------

def clean_scene():
    """Removes all objects from the scene to start fresh."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Clear orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.curves:
        if block.users == 0:
            bpy.data.curves.remove(block)

def create_material(name, hex_color, roughness=0.4, specular=0.5, emission=False):
    """Creates a PBR material."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    # Convert Hex to RGB (Blender uses 0-1 Linear RGB)
    # Hex string format: "RRGGBB"
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    # Gamma correction for linear color space approximation
    color = (pow(r, 2.2), pow(g, 2.2), pow(b, 2.2), 1.0)

    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Specular IOR Level'].default_value = specular

    if emission:
        bsdf.inputs['Emission Color'].default_value = color
        bsdf.inputs['Emission Strength'].default_value = 1.0

    return mat

def create_curve_object(name, splines_data):
    """
    Creates a 3D curve object from a list of splines.
    splines_data: List of dicts, each containing:
      - 'points': list of (x, y, z) tuples for Poly lines
      - 'type': 'POLY' or 'BEZIER'
      - 'cyclic': True/False
      - 'bezier_points': list of (co, handle_left, handle_right) if BEZIER
    """
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '2D'
    curve_data.fill_mode = 'BOTH'
    curve_data.extrude = EXTRUSION
    curve_data.bevel_depth = BEVEL_DEPTH
    curve_data.bevel_resolution = 4

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)

    for s_data in splines_data:
        spline = curve_data.splines.new(s_data['type'])
        spline.use_cyclic_u = s_data['cyclic']

        if s_data['type'] == 'POLY':
            points = s_data['points']
            spline.points.add(len(points) - 1)
            for i, coord in enumerate(points):
                x, y = coord
                spline.points[i].co = (x, y, 0.0, 1.0)

        elif s_data['type'] == 'BEZIER':
            b_points = s_data['bezier_points']
            spline.bezier_points.add(len(b_points) - 1)
            for i, (co, h1, h2) in enumerate(b_points):
                pt = spline.bezier_points[i]
                pt.co = (co[0], co[1], 0.0)
                # Handles are ABSOLUTE in Blender API, not relative vectors.
                pt.handle_left = (h1[0], h1[1], 0.0)
                pt.handle_right = (h2[0], h2[1], 0.0)
                pt.handle_left_type = 'FREE'
                pt.handle_right_type = 'FREE'

    return obj

# ------------------------------------------------------------------------------
# 3. Glyph Definitions
# ------------------------------------------------------------------------------

def make_m():
    w = WIDTH_WIDE
    h = HEIGHT
    s = STROKE

    # "The Heavy Panorama" M
    # Blocky, minimal.
    # Outer box: (0,0) -> (w,h)
    # Inner Cut: V shape.

    # We define the polygon vertices counter-clockwise

    # Inner V calculation:
    v_bottom_y = 3.0
    mid_x = w / 2

    points = [
        (0, 0),         # Bottom Left
        (s, 0),         # Leg Left Inner Bottom
        (s, h - 2),     # Leg Left Inner Top (Crook start)
        (mid_x, v_bottom_y), # V Bottom
        (w - s, h - 2), # Leg Right Inner Top
        (w - s, 0),     # Leg Right Inner Bottom
        (w, 0),         # Bottom Right
        (w, h),         # Top Right
        (mid_x, v_bottom_y + s*1.2), # V Top (Offset to keep thickness roughly visual)
        (0, h)          # Top Left
    ]

    return [{'type': 'POLY', 'cyclic': True, 'points': points}]

def make_y():
    w = WIDTH_WIDE
    h = HEIGHT
    s = STROKE
    mid = w / 2

    stem_h = 3.5 # Height of the vertical stem part

    points = [
        (mid - s/2, 0),
        (mid + s/2, 0),
        (mid + s/2, stem_h),
        (w, h),
        (w - s*1.2, h), # Top Right Inner
        (mid, stem_h + s*0.8), # Crotch
        (s*1.2, h),     # Top Left Inner
        (0, h),
        (mid - s/2, stem_h)
    ]
    return [{'type': 'POLY', 'cyclic': True, 'points': points}]

def make_t():
    w = WIDTH_WIDE
    h = HEIGHT
    s = STROKE

    mid = w/2
    stem_left = mid - s/2
    stem_right = mid + s/2

    points = [
        (stem_left, 0),
        (stem_right, 0),
        (stem_right, h - s),
        (w, h - s),
        (w, h),
        (0, h),
        (0, h - s),
        (stem_left, h - s)
    ]
    return [{'type': 'POLY', 'cyclic': True, 'points': points}]

def make_d():
    # Construction of D using Golden Curves
    w = WIDTH_STD + 1 # A bit wider for D
    h = HEIGHT
    s = STROKE

    # We use a BEZIER spline.
    # IMPORTANT: Handles are defined as absolute coordinates here.

    # Outer path
    r_outer = w * 0.6 # Large radius
    tangent_len = r_outer * 0.55228 # Bezier circle approximation constant

    # We define bezier points: (co, handle_left, handle_right)
    # co = (x, y)
    # handle = (x, y) absolute

    pts_out = []

    # 1. Bottom Left (Corner) - Sharp
    pts_out.append(((0,0), (0,0), (0,0)))

    # 2. Bottom Right Start of Curve (Linear from BL)
    # Point: (w-3, 0)
    # Handle Left: pointing back to BL -> (w-4, 0)
    # Handle Right: pointing forward into curve -> (w-3 + tangent_len?? No)
    # The curve starts here. The tangent should be horizontal (1,0).
    # Handle Right: (w-3 + 2, 0) - extending horizontally
    pts_out.append(((w-3, 0), (w-4, 0), (w-1, 0)))

    # 3. Right Apex
    # Point: (w, h/2)
    # Tangent is vertical.
    # Handle Left (Down): (w, h/2 - 2)
    # Handle Right (Up): (w, h/2 + 2)
    pts_out.append(((w, h/2), (w, h/2 - 2), (w, h/2 + 2)))

    # 4. Top Right End of Curve
    # Point: (w-3, h)
    # Tangent is horizontal (-1, 0).
    # Handle Left (from curve): (w-1, h)
    # Handle Right (towards TL): (w-4, h)
    pts_out.append(((w-3, h), (w-1, h), (w-4, h)))

    # 5. Top Left (Corner) - Sharp
    pts_out.append(((0, h), (0, h), (0, h)))

    # Inner D (Hole) - CW
    pts_in = []

    # 1. Top Left Inner
    pts_in.append(((s, h-s), (s, h-s), (s, h-s)))

    # 2. Top Inner Start Curve
    # Point: (w-3, h-s)
    # Handle Left (towards TL): (w-4, h-s)
    # Handle Right (into curve): (w-1, h-s)
    pts_in.append(((w-3, h-s), (w-4, h-s), (w-1, h-s)))

    # 3. Right Inner Apex
    # Point: (w-s+1, h/2)
    # Handle Left (Up): (w-s+1, h/2 + 2)
    # Handle Right (Down): (w-s+1, h/2 - 2) -- Note direction is CW!
    # Wait, if CW: Top -> Right -> Bottom.
    # Previous was Top. Next is Right.
    # Handle Left points to Top (Up). Handle Right points to Bottom (Down).
    pts_in.append(((w-s+1, h/2), (w-s+1, h/2 + 2), (w-s+1, h/2 - 2)))

    # 4. Bottom Inner End Curve
    # Point: (w-3, s)
    # Handle Left (from Right): (w-1, s)
    # Handle Right (towards BL): (w-4, s)
    pts_in.append(((w-3, s), (w-1, s), (w-4, s)))

    # 5. Bottom Left Inner
    pts_in.append(((s, s), (s, s), (s, s)))

    return [
        {'type': 'BEZIER', 'cyclic': True, 'bezier_points': pts_out},
        {'type': 'BEZIER', 'cyclic': True, 'bezier_points': pts_in}
    ]

def make_c():
    w = WIDTH_STD
    h = HEIGHT
    s = STROKE

    # C is Open.
    # CCW Outer, CW Inner (if we closed it).
    # Since it's one continuous loop for the "C" shape:
    # Top Tip -> Top Left -> Bottom Left -> Bottom Tip -> (turn in) -> Inner Bottom -> Inner Left -> Inner Top -> Close

    pts = []

    # 1. Top Tip Outer (Sharp)
    # Point: (w, h - s*0.2)
    pts.append(((w, h - s*0.2), (w, h - s*0.2), (w, h - s*0.2)))

    # 2. Top Curve Start (Top Middle)
    # Point: (w/2, h)
    # Tangent: Horizontal (-1, 0)
    # Handle Left (towards tip): (w*0.8, h)
    # Handle Right (towards left): (w*0.2, h)
    pts.append(((w/2, h), (w*0.8, h), (w*0.2, h)))

    # 3. Left Middle (Curve Apex)
    # Point: (0, h/2)
    # Tangent: Vertical (0, -1)
    # Handle Left (Up): (0, h*0.8)
    # Handle Right (Down): (0, h*0.2)
    pts.append(((0, h/2), (0, h*0.8), (0, h*0.2)))

    # 4. Bottom Curve Start (Bottom Middle)
    # Point: (w/2, 0)
    # Tangent: Horizontal (1, 0)
    # Handle Left (from Left): (w*0.2, 0)
    # Handle Right (towards Tip): (w*0.8, 0)
    pts.append(((w/2, 0), (w*0.2, 0), (w*0.8, 0)))

    # 5. Bottom Tip Outer (Sharp)
    pts.append(((w, s*0.2), (w, s*0.2), (w, s*0.2)))

    # -- Return inwards (Sharp turn) --

    # 6. Bottom Tip Inner (Sharp)
    pts.append(((w, s), (w, s), (w, s)))

    # 7. Inner Bottom Middle
    # Point: (w/2, s)
    # Tangent: Horizontal (-1, 0) -- Going backwards relative to X axis
    # Handle Left (from tip): (w*0.8, s)
    # Handle Right (towards Left): (w*0.2, s)
    pts.append(((w/2, s), (w*0.8, s), (w*0.2, s)))

    # 8. Inner Left Middle
    # Point: (s, h/2)
    # Tangent: Vertical (0, 1) -- Going Up
    # Handle Left (Down): (s, h*0.3)
    # Handle Right (Up): (s, h*0.7)
    pts.append(((s, h/2), (s, h*0.3), (s, h*0.7)))

    # 9. Inner Top Middle
    # Point: (w/2, h-s)
    # Tangent: Horizontal (1, 0) -- Going Right
    # Handle Left (from Left): (w*0.2, h-s)
    # Handle Right (towards Tip): (w*0.8, h-s)
    pts.append(((w/2, h-s), (w*0.2, h-s), (w*0.8, h-s)))

    # 10. Top Tip Inner (Sharp)
    pts.append(((w, h-s), (w, h-s), (w, h-s)))

    return [{'type': 'BEZIER', 'cyclic': True, 'bezier_points': pts}]


# ------------------------------------------------------------------------------
# 4. Main Execution
# ------------------------------------------------------------------------------

def main():
    clean_scene()

    # 1. Create Materials
    mat_black = create_material("MYDCT_Black", "050505", roughness=0.3, specular=0.6) # Almost black
    mat_white = create_material("MYDCT_White_Plane", "FFFFFF", roughness=0.8, specular=0.1)

    # 2. Create Geometry
    # Dictionary of generators
    glyphs = {
        'M': make_m(),
        'Y': make_y(),
        'D': make_d(),
        'C': make_c(),
        'T': make_t()
    }

    word = "MYDCT"
    cursor_x = 0

    logo_objects = []

    for char in word:
        data = glyphs[char]
        obj = create_curve_object(f"Logo_{char}", data)
        obj.location.x = cursor_x

        # Apply Material
        if obj.data.materials:
            obj.data.materials[0] = mat_black
        else:
            obj.data.materials.append(mat_black)

        logo_objects.append(obj)

        # Advance cursor (Kerning)
        # Get approx width of current char
        # This is a simple heuristic since we know the widths
        char_width = WIDTH_WIDE if char in ['M', 'Y', 'T'] else WIDTH_STD
        if char == 'D': char_width = WIDTH_STD + 1

        cursor_x += char_width + KERNING

    # 3. Center the Logo
    total_width = cursor_x - KERNING
    offset_x = -total_width / 2
    for obj in logo_objects:
        obj.location.x += offset_x
        # Rotate up to stand on floor
        obj.rotation_euler = (math.radians(90), 0, 0)
        # Lift so it sits on Z=0 (since origin is bottom-left)
        obj.location.z = 0

    # 4. Create Background Plane (Infinity Floor)
    bpy.ops.mesh.primitive_plane_add(size=1000, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "Infinity_Plane"
    if plane.data.materials:
        plane.data.materials[0] = mat_white
    else:
        plane.data.materials.append(mat_white)

    # 5. Lighting Setup (Apple-like Studio)
    # Key Light (Soft Area)
    bpy.ops.object.light_add(type='AREA', location=(0, -20, 20))
    key_light = bpy.context.active_object
    key_light.data.energy = 5000
    key_light.data.size = 20
    key_light.rotation_euler = (math.radians(45), 0, 0)

    # Fill Light (Cooler)
    bpy.ops.object.light_add(type='AREA', location=(-20, -10, 10))
    fill_light = bpy.context.active_object
    fill_light.data.energy = 2000
    fill_light.data.size = 15
    fill_light.rotation_euler = (math.radians(60), 0, math.radians(-45))

    # Rim Light (Back)
    bpy.ops.object.light_add(type='AREA', location=(10, 20, 10))
    rim_light = bpy.context.active_object
    rim_light.data.energy = 3000
    rim_light.data.size = 10
    rim_light.rotation_euler = (math.radians(-120), 0, math.radians(150))

    # 6. Camera Setup
    bpy.ops.object.camera_add(location=(0, -40, 5))
    cam = bpy.context.active_object
    cam.rotation_euler = (math.radians(85), 0, 0)
    cam.data.lens = 85 # Long focal length for "Architectural" look
    bpy.context.scene.camera = cam

    # Set Render Engine to Cycles if available (better for glass/metal)
    bpy.context.scene.render.engine = 'CYCLES'

    print("MYDCT Logo Generation Complete.")

if __name__ == "__main__":
    main()
