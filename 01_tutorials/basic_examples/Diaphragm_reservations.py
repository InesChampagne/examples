import os

import compas_fea2
from compas.geometry import Point, Line
from compas_fea2.model import (
    Model, Part, ElasticIsotropic, UniaxialBilinearMaterial,
    TrussSection, RectangularSection, BeamElement, TrussElement, Node, ISection,
)
from compas_fea2.model.bcs import MechanicalBC
from compas_fea2.model.fields import BoundaryConditionsField
from compas_fea2.problem import Problem, StaticStep, LoadFieldsCombination
from compas_fea2.results import DisplacementFieldResults, ReactionFieldResults, SectionForcesFieldResults
from compas_viewer import Viewer
from compas_viewer.config import Config, RendererConfig, CameraConfig
from compas.colors import Color
from compas_viewer.scene import Tag
import compas_fea2.units as u

# ==============================================================
# BACKEND & UNITS
# ==============================================================
compas_fea2.set_backend("opensees")
u.set_unit_system('SI-mm')
u.set_output_magnitudes(True)

HERE = os.path.dirname(__file__)
TEMP = os.path.join(HERE, "..", "..", "temp")

# ==============================================================
# CASE CONFIGURATION — change only these three variables
# ==============================================================
floor_type     = 'L1'  # 'L1'  | 'ROOF'
wind_direction = 'X+'     # 'X+' | 'X-' | 'Y+' | 'Y-'
combination    = 'ULS'   # 'SLS' | 'ULS'
stiffness = 'HIGH-ULS'   # 'LOW' | 'HIGH-SLS' | 'HIGH-ULS'

# True  -> viewer shows element stress values (section forces/moments)
# False -> viewer shows the displacement magnitude at each node
show_stresses = True

# Node-index pairs (row, col) in node_matrix, per element type, for which no
# element should be created — this carves the reservation (opening) out of
# the diaphragm. The nodes themselves stay ordinary part nodes.
RESERVED_STRUTS_INDEX ={'L1': [
    ((7, -1), (7, -2)),
    ((8, -1), (8, -2)),
    ((9, -1), (9, -2)),
],
'ROOF' :[
    ((11, -1), (11, -2)),
    ((13, -1), (13, -2)),
    ((16, -1), (16, -2)),

    ((4, 1), (4, 2)),
    ((9, 1), (9, 2)),
    ((13, 1), (13, 2)),
    ((16, 1), (16,2)),
    ((20, 1), (20, 2)),
    ((25,1), (25,2)),

    ((4, 2), (4, 3)),
    ((9, 2), (9, 3)),
    ((13, 2), (13, 3)),
    ((16, 2), (16, 3)),
    ((20, 2), (20, 3)),
    ((25, 2), (25, 3)),

    ((4, 3), (4, 4)),
    ((9, 3), (9, 4)),
    ((13, 3), (13, 4)),
    ((16, 3), (16, 4)),
    ((20, 3), (20, 4)),
    ((25, 3), (25, 4)),
]
}

DIAG_positions= [
    3, 4, 8, 9, 12, 13, 15, 16, 19, 20, 24, 25
    ]
def create_diag_reserv(row, column):
    return [((row, column), (row+1, column+1)), ((row+1, column), (row, column+1))]

RESERVED_DIAGONALS_INDEX_ROOF = []
for j in range(1,4):
    for i in DIAG_positions:
        RESERVED_DIAGONALS_INDEX_ROOF =RESERVED_DIAGONALS_INDEX_ROOF + create_diag_reserv(i,j)

RESERVED_DIAGONALS_INDEX_ROOF = RESERVED_DIAGONALS_INDEX_ROOF + [
    ((9, -1), (11, -2)),
    ((11, -1), (9, -2)),
    ((13, -2), (11, -1)),
    ((13, -1), (11, -2)),
    ((16, -1), (13, -2)),
    ((16, -2), (13, -1)),
    ((18, -1), (16, -2)),
    ((18, -2), (16, -1)),]

RESERVED_DIAGONALS_INDEX = {'L1' :[
    ((8, -1), (7, -2)),
    ((7, -1), (8, -2)),
    ((7, -1), (6, -2)),
    ((7, -2), (6, -1)),
    ((8, -1), (9, -2)),
    ((8, -2), (9, -1)),
    ((9, -1), (10, -2)),
    ((9, -2), (10, -1)),
],
'ROOF': RESERVED_DIAGONALS_INDEX_ROOF
}

RESERVED_BEAMS_INDEX = {'L1':[
],
'ROOF':[]
}
# Nodes (row, col) that sit on the loaded facade but must not receive load.
NO_LOAD_NODES_INDEX = {'L1' : [
    (7, -1), (8, -1), (9, -1)
    ],
    'ROOF': [
    (11, -1), (13, -1), (16,-1)
    ]}

# Node-index pairs normally built as a strut/tie that must instead be built
# as a beam element (same section/material as the I-beams). Empty the list
# to revert to the default tie behaviour for these connections.
TIES_AS_BEAMS_INDEX = {'L1':[
    ((6, -1), (6, -2)),
    ((10, -1), (10, -2)),
],

'ROOF' :[
    ((9, -1), (9, -2)),
    ((18, -1), (18, -2)),
]
}

# ==============================================================
# CASE PARAMETER TABLES
# ==============================================================

# I-beam profile per floor type
BEAM_SECTION = {
    'L1':   'IPE500',
    'ROOF': 'IPE450',
}

# Floor shear and tie stiffness (N/mm)
# L1: only SW values documented; all combinations use the same values
FLOOR_STIFFNESS = {
    'L1': {
        'LOW':      {'k_floor_shear': 107000,  'k_floor': 1500000},
        'HIGH-SLS': {'k_floor_shear': 200000,  'k_floor': 1500000},
        'HIGH-ULS': {'k_floor_shear': 240000, 'k_floor': 1500000},

    },
    'ROOF': {
        'LOW' :{'k_floor_shear': 91000, 'k_floor': 1500000},
           'HIGH-SLS' :{'k_floor_shear': 178000, 'k_floor': 1500000},
           'HIGH-ULS' :{'k_floor_shear': 189000, 'k_floor': 1500000},
    },
}

# Support indices (row, col) in node_matrix; negative indices count from end
FIXED_NODES_INDEX = {
    'L1': {
        'X+': [(0,  1), (0,  5), (-1,  1), (-1,  5), (6, -1), (10, -1), (6, -2), (10, -2)],
        'X-': [(-1, 1), (-1, 3), (0,   1), (0,   3), (6, -1), (10, -1), (6, -2), (10, -2)],
        'Y+': [(2,  0), (15, 0), (2,  -1), (15, -1), (6, -1), (10, -1), (6, -2), (10, -2)],
        'Y-': [(2,  0), (15, 0), (2,  -1), (15, -1), (6, -1), (10, -1), (6, -2), (10, -2)],
    },
    'ROOF': {
        'X+': [(-1, 4), (-1, 2), (0,  4), (0,  2)],
        'X-': [(-1, 0), (-1, 4), (0,  0), (0,  4)],
        'Y+': [(7,  0), (-1, 0), (7, -1), (-1, -1)],
        'Y-': [(0,  0), (22, 0), (0, -1), (22, -1)],
    },
}

# Applied wind loads (N); SW maps to same values as SLS (no distinct SW load defined)
LOADS = {
    'L1': {
        'X+': {'SW': {'x':  24600}, 'SLS': {'x':  24600}, 'ULS': {'x':  36900}},
        'X-': {'SW': {'x': -24600}, 'SLS': {'x': -24600}, 'ULS': {'x': -36900}},
        'Y+': {'SW': {'y':  90900}, 'SLS': {'y':  90900}, 'ULS': {'y': 136250}},
        'Y-': {'SW': {'y': -90900}, 'SLS': {'y': -90900}, 'ULS': {'y': -136250}},
    },
    'ROOF': {
        'X+': {'SW': {'x':  12700}, 'SLS': {'x':  12700}, 'ULS': {'x':  19100}},
        'X-': {'SW': {'x': -12700}, 'SLS': {'x': -12700}, 'ULS': {'x': -19100}},
        'Y+': {'SW': {'y':  46900}, 'SLS': {'y':  46900}, 'ULS': {'y':  70400}},
        'Y-': {'SW': {'y': -46900}, 'SLS': {'y': -46900}, 'ULS': {'y': -70400}},
    },
}

# Sliding BC for non-primary fixed nodes (first fixed node always gets a full pin)
BC1_PARAMS = {
    'X+': dict(x=True,  y=False, z=True, xx=True, yy=True, zz=False),
    'X-': dict(x=True,  y=False, z=True, xx=True, yy=True, zz=False),
    'Y+': dict(x=False, y=True,  z=True, xx=True, yy=True, zz=False),
    'Y-': dict(x=False, y=True,  z=True, xx=True, yy=True, zz=False),
}

X_STEPS = {'L1': [11090, 11090, 11090, 11090, 11090],
           'ROOF': [11090, 11090, 11090, 11090, 11090]}

Y_STEPS = {'L1': [2400 for i in range(17)],
           'ROOF': [
        2400, 
           2400,
           2100, 300, 
           300, 2100,
           2400,
           2100, 300,
           300, 2100,
           2100,300,
           300, 1800, 300,
           300, 2100,
           2100, 300,
           300, 2100,
           2400,
           2100, 300,
           300, 2100,
           2400,
           2400
           ]}

GOVERNING_NODES_PER_BAY = {'L1': [[i for i in range(18)] for _ in range(5)],
                           'ROOF': [ [0,1,2,4,6,7, 9,11,13,16,18,20,22,23,25,27, 28, 29],
                           [i for i in range(30)],
                           [i for i in range(30)],
                           [i for i in range(30)],
                           [0,1,2,4,6,7, 9,11,13,16,18,20,22,23,25,27, 28, 29]
                           ]}

# ==============================================================
# RESOLVE PARAMETERS FROM CASE SELECTION
# ==============================================================
k_floor_shear     = FLOOR_STIFFNESS[floor_type][stiffness]['k_floor_shear']
k_floor           = FLOOR_STIFFNESS[floor_type][stiffness]['k_floor']
fixed_nodes_index = FIXED_NODES_INDEX[floor_type][wind_direction]
loads             = LOADS[floor_type][wind_direction][combination]
beam_section_name = BEAM_SECTION[floor_type]

# ==============================================================
# GEOMETRY PARAMETERS
# ==============================================================
d_tie      = 48  # mm
max_disp_c = 10   # mm

x_steps = X_STEPS[floor_type]
y_steps = Y_STEPS[floor_type]
governing_nodes_per_bay = GOVERNING_NODES_PER_BAY[floor_type]

# ==============================================================
# MODEL — build node grid
# ==============================================================
mdl = Model(name="simplebeam")
prt = mdl.add_part(Part())
elements_classification = {'BEAMS': [], 'DIAGS': [], 'TIES': []}

x_coords = [0]
for dx in x_steps:
    x_coords.append(x_coords[-1] + dx)

y_coords = [0]
for dy in y_steps:
    y_coords.append(y_coords[-1] + dy)

node_matrix = []
for y in y_coords:
    row = []
    for x in x_coords:
        node = Node([x, y, 0])
        row.append(node)
        prt.add_node(node)
    node_matrix.append(row)

n_column = len(node_matrix[0])
n_lines  = len(node_matrix)

def _node_pairs(index_pairs):
    return {
        frozenset((node_matrix[i0][j0], node_matrix[i1][j1]))
        for (i0, j0), (i1, j1) in index_pairs
    }

reserved_struts    = _node_pairs(RESERVED_STRUTS_INDEX[floor_type])
reserved_diagonals = _node_pairs(RESERVED_DIAGONALS_INDEX[floor_type])
reserved_beams     = _node_pairs(RESERVED_BEAMS_INDEX[floor_type])
ties_as_beams      = _node_pairs(TIES_AS_BEAMS_INDEX[floor_type])

fixed_nodes = [node_matrix[i][j] for i, j in fixed_nodes_index]
no_load_nodes = {node_matrix[i][j] for i, j in NO_LOAD_NODES_INDEX[floor_type]}

if wind_direction == 'X+':
    loaded_nodes = [node_matrix[i][0]  for i in governing_nodes_per_bay[0] if node_matrix[i][0]  not in no_load_nodes]
elif wind_direction == 'X-':
    loaded_nodes = [node_matrix[i][-1] for i in governing_nodes_per_bay[0] if node_matrix[i][-1] not in no_load_nodes]
elif wind_direction == 'Y+':
    loaded_nodes = [node_matrix[0][j]  for j in range(n_column) if node_matrix[0][j]  not in no_load_nodes]
else:  # 'Y-'
    loaded_nodes = [node_matrix[-1][j] for j in range(n_column) if node_matrix[-1][j] not in no_load_nodes]

# ==============================================================
# VIEWER — initialise once before adding elements
# ==============================================================
bb       = mdl.bounding_box
renderer = RendererConfig(show_grid=False)
camera   = CameraConfig(target=[(bb.xmax / 2), (bb.ymax / 2), 0],
                        position=[(bb.xmax / 2), (bb.ymax / 2), 100])
config   = Config(unit='mm', renderer=renderer, camera=camera)
viewer   = Viewer(config=config)
tie_floor = viewer.scene.add_group(name='TIE_FLOOR', show=False)
diags     = viewer.scene.add_group(name='DIAGONALS', show=False)
beams     = viewer.scene.add_group(name='I-BEAMS',   show=False)

# ==============================================================
# ELEMENTS — ties
# ==============================================================
L_tie   = 11090   # mm
E_steel = 210000  # N/mm²
k_tie   = E_steel * (3.14 * (d_tie / 2) ** 2) / L_tie
print(k_tie)

w_sec = h_sec = 100
A_sec = w_sec * h_sec

E_tie_eq   = k_tie   * L_tie / A_sec
E_floor_eq = k_floor * L_tie / A_sec
epsyc_tie  = -max_disp_c / L_tie

mat_tie = UniaxialBilinearMaterial(kt=E_tie_eq, kc=E_floor_eq)
sec_tie = TrussSection(A=A_sec, material=mat_tie)

# Beam material/section defined here already: some struts/ties are built as
# beams instead (see TIES_AS_BEAMS_INDEX).
mat_beam = ElasticIsotropic(E=210 * u.GPa, v=0.2, density=2400 * u.kg_per_m3)
sec_beam = getattr(ISection, beam_section_name)(material=mat_beam)

for i in range(len(x_steps)):
    for j in governing_nodes_per_bay[i]:
        n0, n1 = node_matrix[j][i], node_matrix[j][i+1]
        if frozenset((n0, n1)) in reserved_struts:
            continue
        if frozenset((n0, n1)) in ties_as_beams:
            elem = BeamElement(nodes=[n0, n1], section=sec_beam, orientation=[1, 0, 0])
            prt.add_element(elem)
            beams.add(Line(n0.point, n1.point), color=Color.green())
            elements_classification['BEAMS'].append(elem)
            continue
        elem = TrussElement(nodes=[n0, n1], section=sec_tie)
        prt.add_element(elem)
        tie_floor.add(Line(n0.point, n1.point), color=Color.blue())
        elements_classification['TIES'].append(elem)

# ==============================================================
# ELEMENTS — diagonals (floor shear)
# ==============================================================
E_diag_eq = k_floor_shear * L_tie / A_sec
mat_diag  = ElasticIsotropic(E=E_diag_eq, v=0.2,
                              density=2400 * u.kg_per_m3, notension=True)
sec_diag  = RectangularSection(w=w_sec * u.mm, h=h_sec * u.mm, material=mat_diag)

# mat_diag  = UniaxialBilinearMaterial(kc=E_diag_eq, epsyc= -100/L_tie)
# sec_diag  = TrussSection(A=A_sec, material=mat_diag)

for j in range(len(x_steps)):
    for i in range(len(governing_nodes_per_bay[j])-1):
        node_indice1 = governing_nodes_per_bay[j][i]
        node_indice2 = governing_nodes_per_bay[j][i+1]
        for n0, n1 in [(node_matrix[node_indice1][j],     node_matrix[node_indice2][j + 1]),
                       (node_matrix[node_indice2][j], node_matrix[node_indice1][j + 1])]:
            if frozenset((n0, n1)) in reserved_diagonals:
                continue
            elem = TrussElement(nodes=[n0, n1], section=sec_diag)
            prt.add_element(elem)
            diags.add(Line(n0.point, n1.point), color=Color.orange())
            elements_classification['DIAGS'].append(elem)

# ==============================================================
# ELEMENTS — I-beams
# A beam span (row i -> row i+1) is discretized into 6 sub-elements.
# If the span is listed in RESERVED_BEAMS_INDEX, the whole span is skipped.
# ==============================================================
for j in range(len(node_matrix[0])):
    for i in range(len(node_matrix) - 1):
        nstart = node_matrix[i][j]
        nend   = node_matrix[i + 1][j]
        if frozenset((nstart, nend)) in reserved_beams:
            continue
        beams.add(Line(nstart.point, nend.point), color=Color.green())
        length = abs(nend.y - nstart.y)
        n0 = nstart
        for _ in range(5):
            n1 = Node([n0.x, n0.y + length / 6, n0.z])
            prt.add_node(n1)
            elem = BeamElement(nodes=[n0, n1], section=sec_beam, orientation=[1, 0, 0])
            prt.add_element(elem)
            elements_classification['BEAMS'].append(elem)
            n0 = n1
        elem = BeamElement(nodes=[n1, nend], section=sec_beam, orientation=[1, 0, 0])
        prt.add_element(elem)
        elements_classification['BEAMS'].append(elem)

# ==============================================================
# BOUNDARY CONDITIONS
# ==============================================================
not_fixed_nodes = [n for n in mdl.nodes if n not in fixed_nodes]

# The first 4 entries of fixed_nodes_index are the direction-specific corner
# supports (1 full pin + 3 sliding); any further entries are diaphragm nodes
# that must always be blocked in both directions regardless of wind direction.
primary_fixed_nodes    = fixed_nodes[:4]
diaphragm_fixed_nodes  = fixed_nodes[4:]

bc_full    = MechanicalBC(x=True,  y=True,  z=True, xx=True, yy=True, zz=False)
bc_sliding = MechanicalBC(**BC1_PARAMS[wind_direction])
bc_free    = MechanicalBC(x=False, y=False, z=True, xx=True, yy=True, zz=False)

mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=primary_fixed_nodes[0],  condition=bc_full))
mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=primary_fixed_nodes[1:], condition=bc_sliding))
if diaphragm_fixed_nodes:
    mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=diaphragm_fixed_nodes, condition=bc_full))
mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=not_fixed_nodes, condition=bc_free))

# ==============================================================
# PROBLEM
# ==============================================================
prb = mdl.add_problem(problem=Problem(name="SADV_diaphragm_reservations"))
stp = prb.add_step(StaticStep(test="NormDispIncr 1.0e-2 100"))

stp.add_combination(LoadFieldsCombination.ec_sls_characteristic())

stp.add_uniform_forcefield(nodes=loaded_nodes, **loads, load_case="Q")

disp  = stp.add_field_output(DisplacementFieldResults())
react = stp.add_field_output(ReactionFieldResults())
sf    = stp.add_field_output(SectionForcesFieldResults())

# ==============================================================
# ANALYSIS
# ==============================================================
prb.analyse_and_extract(problems=[prb], path=TEMP, verbose=True, erase_data="armageddon")

# ==============================================================
# RESULTS
# ==============================================================
print("*************************")
print("RESULTS POST-PROCESSING")
print("*************************")
print("Max/Min reaction X [N]: ",
      react.get_limits_component('x')[0].x, "/",
      react.get_limits_component('x')[1].x)
print("Max/Min reaction Y [N]: ",
      react.get_limits_component('y')[0].y, "/",
      react.get_limits_component('y')[1].y)

for node in fixed_nodes :
    print("node")
    print(react.get_result_at(location=node).x)
    print(react.get_result_at(location=node).y)

# ==============================================================
# VISUALIZATION
# ==============================================================

def add_text_label(viewer, text, x, y, scale, parent, color, show=False):
    tag = Tag(
        text=text,
        position=(x, y, 0),
        color=color,
        height=scale * 1000,
        absolute_height=True,
        vertical_align="top",
        horizontal_align="center",
    )
    parent.add(tag, show=show)


initial_model  = viewer.scene.add_group(name='Initial',  show=False)
deformed_model = viewer.scene.add_group(name='Deformed', show=True)

for element in mdl.elements:
    line = Line(start=element.points[0], end=element.points[-1])
    initial_model.add(line, color=Color.grey(), opacity=0.3)

scale = 100
max_deformed_y = disp.get_max_result('y')
min_deformed_y = disp.get_min_result('y')
max_y = max_deformed_y if max_deformed_y.y > abs(min_deformed_y.y) else min_deformed_y
max_deformed_x = disp.get_max_result('x')
min_deformed_x = disp.get_min_result('x')
max_x = max_deformed_x if max_deformed_x.x > abs(min_deformed_x.x) else min_deformed_x

print(f'uy_max = {max_y.y:.2f} mm')
print(f'ux_max = {max_x.x:.2f} mm')

for element in mdl.elements:
    start = element.nodes[0]
    end   = element.nodes[-1]
    sd    = disp.get_result_at(location=start)
    ed    = disp.get_result_at(location=end)
    def_s = Point(start.x + sd.x * scale, start.y + sd.y * scale, 0)
    def_e = Point(end.x   + ed.x * scale, end.y   + ed.y * scale, 0)
    deformed_model.add(Line(start=def_s, end=def_e), color=Color.red())

# add_text_label(viewer=viewer, text=f"{int(max_y.y)} mm",
#                x=max_y.node.x, y=max_y.node.y, scale=200,
#                parent=deformed_model, color=Color.black())
# add_text_label(viewer=viewer, text=f"{int(max_x.x)} mm",
#                x=max_x.node.x, y=max_x.node.y, scale=200,
#                parent=deformed_model, color=Color.black())

if show_stresses:
    # Section forces — compression / tension
    section_forces  = viewer.scene.add_group(name='SF COMPRESSION/TENSION', show=True)
    max_compression = sf.get_max_result(component='Fx_1')
    max_tension     = sf.get_min_result(component='Fx_1')
    max_value       = max(abs(max_compression.Fx_1), abs(max_tension.Fx_1))
    for element in mdl.elements:
        sf_result = sf.get_result_at(location=element)
        line      = Line(start=element.points[0], end=element.points[-1])
        if sf_result.Fx_1 < 0:
            section_forces.add(line, color=Color.red(),  linewidth=0.5 + 8 * abs(sf_result.Fx_1 / max_value))
        elif sf_result.Fx_1 > 0:
            section_forces.add(line, color=Color.blue(), linewidth=0.5 + 8 * abs(sf_result.Fx_1 / max_value))
        else:
            section_forces.add(line, color=Color.grey(), opacity=0.3)
    # add_text_label(viewer=viewer, text=str(int(max_compression.Fx_1/1000))+ " kN", x=max_compression.reference_point.x+1000 , y= max_compression.reference_point.y, parent=section_forces, color = Color.blue(), scale=200, show=True)
    # add_text_label(viewer=viewer, text=str(abs(int(max_tension.Fx_1/1000)))+ " kN", x=max_tension.reference_point.x+1000 , y= max_tension.reference_point.y, parent=section_forces, color = Color.red(), scale=200, show=True)

    # Axial force labels — DIAGS
    diags_forces = viewer.scene.add_group(name='SF DIAGS (kN)', show=False)
    for elem in elements_classification['DIAGS']:
        sf_result = sf.get_result_at(location=elem)
        fx_kn = sf_result.Fx_1 / 1000
        if abs(fx_kn) < 2:
            continue
        mid_x = (elem.points[0].x + elem.points[-1].x) / 2
        mid_y = (elem.points[0].y + elem.points[-1].y) / 2
        color = Color.blue() if fx_kn >= 0 else Color.red()
        add_text_label(viewer=viewer, text=f"{fx_kn:.1f}", x=mid_x, y=mid_y,
                       scale=200, parent=diags_forces, color=color, show=True)

    # Axial force labels — TIES
    # y offset so the label doesn't overlap the DIAGS label sitting at the same
    # midpoint (ties and diagonals cross at the same node intersections).
    tie_label_x_offset = 3000  # mm
    ties_forces = viewer.scene.add_group(name='SF TIES (kN)', show=False)
    for elem in elements_classification['TIES']:
        sf_result = sf.get_result_at(location=elem)
        fx_kn = sf_result.Fx_1 / 1000
        if abs(fx_kn) < 2:
            continue
        mid_x = (elem.points[0].x + elem.points[-1].x) / 2 + tie_label_x_offset
        mid_y = (elem.points[0].y + elem.points[-1].y) / 2
        color = Color.blue() if fx_kn >= 0 else Color.red()
        add_text_label(viewer=viewer, text=f"{fx_kn:.1f}", x=mid_x, y=mid_y,
                       scale=200, parent=ties_forces, color=color, show=True)

    # Bending moments
    bending_sections = viewer.scene.add_group(name='SF MOMENT', show=True)
    max_bending      = sf.get_max_result(component='Mz_1')
    min_bending      = sf.get_min_result(component='Mz_1')
    max_value        = max(abs(max_bending.Mz_1), abs(min_bending.Mz_1))
    for element in mdl.elements:
        if isinstance(element, BeamElement):
            sf_result = sf.get_result_at(location=element)
            line = Line(
                start=Point(element.points[0].x  + sf_result.Mz_1 / max_value * 2000, element.points[0].y,  0),
                end=  Point(element.points[-1].x - sf_result.Mz_2 / max_value * 2000, element.points[-1].y, 0),
            )
            if sf_result.Mz_1 < 0:
                bending_sections.add(line, color=Color.violet(), linewidth=0.5 + 8 * abs(sf_result.Mz_1 / max_value))
            elif sf_result.Mz_1 > 0:
                bending_sections.add(line, color=Color.pink(),   linewidth=0.5 + 8 * abs(sf_result.Mz_1 / max_value))
            else:
                bending_sections.add(line, color=Color.grey(), opacity=0.3)
else:
    # Displacement magnitude at DIAGS/TIES nodes, positioned on the deformed shape
    diag_tie_nodes = set()
    for elem in elements_classification['DIAGS'] + elements_classification['TIES']:
        diag_tie_nodes.update(elem.nodes)

    disp_labels = viewer.scene.add_group(name='DISPLACEMENTS (mm)', show=True)
    for node in diag_tie_nodes:
        d = disp.get_result_at(location=node)
        if d.magnitude < 0.1:
            continue
        def_x = node.x + d.x * scale
        def_y = node.y + d.y * scale
        add_text_label(viewer=viewer, text=f"{d.magnitude:.1f}", x=def_x, y=def_y,
                       scale=200, parent=disp_labels, color=Color.black(), show=True)

# Applied loads
applied_loads = viewer.scene.add_group(name='Applied loads')
for load_field in stp.loads:
    for node, load in load_field.node_load:
        applied_loads.add(load.force_vector.scaled(0.1),
                          anchor=node.point.translated(-load.force_vector.scaled(0.1)),
                          color=Color.green())

# Boundary conditions
bc_viewer = viewer.scene.add_group(name='BC')
for node in fixed_nodes:
    bc_viewer.add(node.point, pointcolor=Color.black(), pointsize=10)

# Reservation — highlight the nodes touched by an excluded connection
reservation_nodes = set()
for pairs in (reserved_struts, reserved_diagonals, reserved_beams):
    for pair in pairs:
        reservation_nodes.update(pair)

reservation_viewer = viewer.scene.add_group(name='RESERVATION')
for node in reservation_nodes:
    reservation_viewer.add(node.point, pointcolor=Color.red(), pointsize=10)

# Axial force summary
ties_Nx  = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['TIES']]
beams_Nx = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['BEAMS']]
diag_Nx  = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['DIAGS']]

print(disp.get_result_at(node_matrix[5][0]).y-disp.get_result_at(node_matrix[5][1]).y)
print('NEGATIVE = TENSION / POSITIVE = COMPRESSION (kN):')
print(f'TIE/FLOOR    min/max: {min(ties_Nx):.1f} / {max(ties_Nx):.1f} kN')
print(f'BEAMS   min/max: {min(beams_Nx):.1f} / {max(beams_Nx):.1f} kN')
print(f'DIAGS   min/max: {min(diag_Nx):.1f} / {max(diag_Nx):.1f} kN')

viewer.show()
print('Youhou')
