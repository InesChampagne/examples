"""
Batch runner — SADV diaphragm, with reservations, all stiffness levels.
floor_type selects 'L1' or 'ROOF' — drives geometry, reservations, loads,
supports AND the exported Excel file name (SADV_<floor_type>_results.xlsx).
"""

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
import compas_fea2.units as u
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

compas_fea2.set_backend("opensees")
u.set_unit_system('SI-mm')
u.set_output_magnitudes(True)

HERE = os.path.dirname(__file__)
TEMP = os.path.join(HERE, "..", "..", "temp")

# ==============================================================
#  CASE CONFIGURATION — change only this variable
# ==============================================================
floor_type = 'L1'  # 'L1' | 'ROOF'
date = '260904_wallbutresses'

# ==============================================================
#  RESERVATIONS (openings) — node-index pairs (row, col) in node_matrix,
#  per element type, for which no element should be created.
# ==============================================================
RESERVED_STRUTS_INDEX = {
    'L1': [
        ((7, -1), (7, -2)),
        ((8, -1), (8, -2)),
        ((9, -1), (9, -2)),
    ],
    'ROOF': [
        ((11, -1), (11, -2)),
        ((13, -1), (13, -2)),
        ((16, -1), (16, -2)),

        ((4, 1), (4, 2)),
        ((9, 1), (9, 2)),
        ((13, 1), (13, 2)),
        ((16, 1), (16, 2)),
        ((20, 1), (20, 2)),
        ((25, 1), (25, 2)),

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
    ],
}

DIAG_positions = [3, 4, 8, 9, 12, 13, 15, 16, 19, 20, 24, 25]


def create_diag_reserv(row, column):
    return [((row, column), (row + 1, column + 1)), ((row + 1, column), (row, column + 1))]


RESERVED_DIAGONALS_INDEX_ROOF = []
for j in range(1, 4):
    for i in DIAG_positions:
        RESERVED_DIAGONALS_INDEX_ROOF = RESERVED_DIAGONALS_INDEX_ROOF + create_diag_reserv(i, j)

RESERVED_DIAGONALS_INDEX_ROOF = RESERVED_DIAGONALS_INDEX_ROOF + [
    ((9, -1), (11, -2)),
    ((11, -1), (9, -2)),
    ((13, -2), (11, -1)),
    ((13, -1), (11, -2)),
    ((16, -1), (13, -2)),
    ((16, -2), (13, -1)),
    ((18, -1), (16, -2)),
    ((18, -2), (16, -1)),
]

RESERVED_DIAGONALS_INDEX = {
    'L1': [
        ((8, -1), (7, -2)),
        ((7, -1), (8, -2)),
        ((7, -1), (6, -2)),
        ((7, -2), (6, -1)),
        ((8, -1), (9, -2)),
        ((8, -2), (9, -1)),
        ((9, -1), (10, -2)),
        ((9, -2), (10, -1)),
    ],
    'ROOF': RESERVED_DIAGONALS_INDEX_ROOF,
}

RESERVED_BEAMS_INDEX = {
    'L1': [],
    'ROOF': [],
}

# Nodes (row, col) that sit on the loaded facade but must not receive load.
NO_LOAD_NODES_INDEX = {
    'L1': [
        (7, -1), (8, -1), (9, -1)
    ],
    'ROOF': [
        (11, -1), (13, -1), (16, -1)
    ],
}

# Node-index pairs normally built as a strut/tie that must instead be built
# as a beam element (same section/material as the I-beams).
TIES_AS_BEAMS_INDEX = {
    'L1': [
        ((6, -1), (6, -2)),
        ((10, -1), (10, -2)),
    ],
    'ROOF': [
        ((9, -1), (9, -2)),
        ((18, -1), (18, -2)),
    ],
}

# Saint-André cross (X-brace) added inside the reservation opening, spanning
# the full height of the opening (rows) between the two given columns.
# Built with a very stiff HEB profile (rigid strut, not the standard tie/diag).
SAINT_ANDRE_BRACING = {
    'L1':   {'rows': (6, 10), 'columns': (-2, -1), 'section': 'HEB600'},
    'ROOF': None,
}

# ==============================================================
#  CASE PARAMETER TABLES
# ==============================================================

# I-beam profile per floor type
BEAM_SECTION = {
    'L1':   'IPE500',
    'ROOF': 'IPE450',
}

FLOOR_STIFFNESS = {
    'L1': {
        'LOW':      {'k_floor_shear': 91000, 'k_floor': 1500000},
        'HIGH-SLS': {'k_floor_shear': 200000, 'k_floor': 1500000},
        'HIGH-ULS': {'k_floor_shear': 240000, 'k_floor': 1500000},
    },
    'ROOF': {
        'LOW':      {'k_floor_shear': 91000,  'k_floor': 1500000},
        'HIGH-SLS': {'k_floor_shear': 178000, 'k_floor': 1500000},
        'HIGH-ULS': {'k_floor_shear': 189000, 'k_floor': 1500000},
    },
}

# Support indices (row, col) in node_matrix; negative indices count from end
FIXED_NODES_INDEX = {
    'L1': {
        'X+': [(0,  1), (0,  4), (-1,  1), (-1,  4), (6, -1), (10, -1), (6, -2), (10, -2)],
        'X-': [(-1, 1), (-1, 3), (0,   1), (0,   3), (6, -1), (10, -1), (6, -2), (10, -2)],
        'Y+': [(2,  0), (15, 0), (2,  -1), (15, -1), (6, -1), (10, -1), (6, -2), (10, -2)],
        'Y-': [(2,  0), (15, 0), (2,  -1), (15, -1), (6, -1), (10, -1), (6, -2), (10, -2)],
    },
    'ROOF': {
        'X+': [(-1, 5), (-1, 2), (0,  5), (0,  2)],
        'X-': [(-1, 0), (-1, 4), (0,  0), (0,  4)],
        'Y+': [(7,  0), (-1, 0), (7, -1), (-1, -1)],
        'Y-': [(0,  0), (22, 0), (0, -1), (22, -1)],
    },
}

# Applied wind loads (N)
LOADS = {
    'L1': {
        'X+': {'SLS': {'x':  24600}, 'ULS': {'x':  36900}},
        'X-': {'SLS': {'x': -24600}, 'ULS': {'x': -36900}},
        'Y+': {'SLS': {'y':  90900}, 'ULS': {'y': 136250}},
        'Y-': {'SLS': {'y': -90900}, 'ULS': {'y': -136250}},
    },
    'ROOF': {
        'X+': {'SLS': {'x':  12700}, 'ULS': {'x':  19100}},
        'X-': {'SLS': {'x': -12700}, 'ULS': {'x': -19100}},
        'Y+': {'SLS': {'y':  46900}, 'ULS': {'y':  70400}},
        'Y-': {'SLS': {'y': -46900}, 'ULS': {'y': -70400}},
    },
}

# Sliding BC for non-primary fixed nodes (first fixed node always gets a full pin)
BC1_PARAMS = {
    'X+': dict(x=True,  y=False, z=True, xx=True, yy=True, zz=False),
    'X-': dict(x=True,  y=False, z=True, xx=True, yy=True, zz=False),
    'Y+': dict(x=False, y=True,  z=True, xx=True, yy=True, zz=False),
    'Y-': dict(x=False, y=True,  z=True, xx=True, yy=True, zz=False),
}

X_STEPS = {
    'L1':   [11090, 11090, 11090, 11090, 11090],
    'ROOF': [11090, 11090, 11090, 11090, 11090],
}

Y_STEPS = {
    'L1': [2400 for _ in range(17)],
    'ROOF': [
        2400,
        2400,
        2100, 300,
        300, 2100,
        2400,
        2100, 300,
        300, 2100,
        2100, 300,
        300, 1800, 300,
        300, 2100,
        2100, 300,
        300, 2100,
        2400,
        2100, 300,
        300, 2100,
        2400,
        2400,
    ],
}

GOVERNING_NODES_PER_BAY = {
    'L1': [[i for i in range(18)] for _ in range(5)],
    'ROOF': [
        [0, 1, 2, 4, 6, 7, 9, 11, 13, 16, 18, 20, 22, 23, 25, 27, 28, 29],
        [i for i in range(30)],
        [i for i in range(30)],
        [i for i in range(30)],
        [0, 1, 2, 4, 6, 7, 9, 11, 13, 16, 18, 20, 22, 23, 25, 27, 28, 29],
    ],
}

WIND_DIRECTIONS = ['X+', 'X-', 'Y+', 'Y-']

CASES = [
    ('X+', 'SLS'), ('X+', 'ULS'),
    ('X-', 'SLS'), ('X-', 'ULS'),
    ('Y+', 'SLS'), ('Y+', 'ULS'),
    ('Y-', 'SLS'), ('Y-', 'ULS'),
]

UMAX = {
    'LOW':      10,
    'HIGH-SLS': 4,
    'HIGH-ULS': 4,
}

STIFFNESSES = ['LOW',
            #    'HIGH-SLS',
            #    'HIGH-ULS'
               ]

# Stiffness levels tied to a single load combination only run that combination's
# cases (e.g. HIGH-SLS is only meaningful under SLS loading). Stiffnesses not
# listed here (e.g. LOW) run every case in CASES.
STIFFNESS_COMBINATION = {
    'HIGH-SLS': 'SLS',
    'HIGH-ULS': 'ULS',
}


# ==============================================================
#  ANALYSIS FUNCTION
# ==============================================================
def run_case(floor_type: str, wind_direction: str, combination: str, stiffness: str) -> dict:
    print(f"  >>> {floor_type} | {wind_direction} | {combination} | {stiffness}")

    k_floor_shear     = FLOOR_STIFFNESS[floor_type][stiffness]['k_floor_shear']
    k_floor           = FLOOR_STIFFNESS[floor_type][stiffness]['k_floor']
    fixed_nodes_index = FIXED_NODES_INDEX[floor_type][wind_direction]
    loads             = LOADS[floor_type][wind_direction][combination]
    beam_section_name = BEAM_SECTION[floor_type]
    umax              = UMAX[stiffness]

    d_tie      = 30
    max_disp_c = umax
    x_steps    = X_STEPS[floor_type]
    y_steps    = Y_STEPS[floor_type]
    governing_nodes_per_bay = GOVERNING_NODES_PER_BAY[floor_type]
    wall_buttresses = {'L1':
                       [governing_nodes_per_bay[0][i] for i in range(1, len(governing_nodes_per_bay[0]) - 1, 2)]
                       }

    mdl = Model(name="batch")
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
    reserved_beams      = _node_pairs(RESERVED_BEAMS_INDEX[floor_type])
    ties_as_beams       = _node_pairs(TIES_AS_BEAMS_INDEX[floor_type])

    fixed_nodes   = [node_matrix[i][j] for i, j in fixed_nodes_index]
    no_load_nodes = {node_matrix[i][j] for i, j in NO_LOAD_NODES_INDEX[floor_type]}

    if wind_direction == 'X+':
        loaded_nodes = [node_matrix[i][0]  for i in governing_nodes_per_bay[0] if node_matrix[i][0]  not in no_load_nodes]
    elif wind_direction == 'X-':
        loaded_nodes = [node_matrix[i][-1] for i in governing_nodes_per_bay[0] if node_matrix[i][-1] not in no_load_nodes]
    elif wind_direction == 'Y+':
        loaded_nodes = [node_matrix[0][j]  for j in range(n_column) if node_matrix[0][j]  not in no_load_nodes]
    else:  # 'Y-'
        loaded_nodes = [node_matrix[-1][j] for j in range(n_column) if node_matrix[-1][j] not in no_load_nodes]

    L_tie   = 11090
    E_steel = 210000
    k_tie   = E_steel * (3.14 * (d_tie / 2) ** 2) / L_tie

    w_sec = h_sec = 100
    A_sec = w_sec * h_sec

    E_tie_eq   = k_tie   * L_tie / A_sec
    E_floor_eq = k_floor * L_tie / A_sec

    mat_tie = UniaxialBilinearMaterial(kt=E_tie_eq, kc=E_floor_eq)
    sec_tie = TrussSection(A=A_sec, material=mat_tie)

    # At the wall-buttress rows, the struts/ties funnel the buttress reaction
    # into the diaphragm and need extra capacity — doubled tension stiffness
    # (kt) there. Only the rows themselves are reinforced; the edge bays on
    # those rows are already replaced by the rigid wall_buttress_pairs strut.
    mat_tie_reinforced = UniaxialBilinearMaterial(kt=E_tie_eq * 2, kc=E_floor_eq)
    sec_tie_reinforced = TrussSection(A=A_sec, material=mat_tie_reinforced)
    wall_buttress_rows = set(wall_buttresses['L1'])

    # Node pairs occupied by the rigid wall buttress struts (see ELEMENTS —
    # wall buttress struts below) — the tie loop skips these so a normal tie
    # isn't built in parallel with the rigid strut at the same location.
    wall_buttress_pairs = set()
    for j in wall_buttresses['L1']:
        for col_a, col_b in ((-1, -2), (0, 1)):
            wall_buttress_pairs.add(frozenset((node_matrix[j][col_a], node_matrix[j][col_b])))

    # Beam material/section defined here already: some struts/ties are built
    # as beams instead (see TIES_AS_BEAMS_INDEX).
    mat_beam = ElasticIsotropic(E=210 * u.GPa, v=0.2, density=2400 * u.kg_per_m3)
    sec_beam = getattr(ISection, beam_section_name)(material=mat_beam)

    for i in range(len(x_steps)):
        for j in governing_nodes_per_bay[i]:
            n0, n1 = node_matrix[j][i], node_matrix[j][i + 1]
            if frozenset((n0, n1)) in reserved_struts:
                continue
            if frozenset((n0, n1)) in wall_buttress_pairs:
                continue
            if frozenset((n0, n1)) in ties_as_beams:
                elem = BeamElement(nodes=[n0, n1], section=sec_beam, orientation=[1, 0, 0])
                prt.add_element(elem)
                elements_classification['BEAMS'].append(elem)
                continue
            tie_section = sec_tie_reinforced if j in wall_buttress_rows else sec_tie
            elem = TrussElement(nodes=[n0, n1], section=tie_section)
            prt.add_element(elem)
            elements_classification['TIES'].append(elem)

    # ELEMENTS — wall buttress struts. At every wall-buttress row, add a
    # strut between the last two columns (-1/-2) and between the first two
    # columns (0/1), connecting the buttress support to the diaphragm edge.
    # Plain elastic truss elements sized on a stiff steel profile (HEB200)
    # so they behave as near-rigid struts.
    strut_profile   = ISection.HEB200(material=mat_beam)
    sec_strut_rigid = TrussSection(A=strut_profile.A, material=mat_beam)

    for j in wall_buttresses['L1']:
        for col_a, col_b in ((-1, -2), (0, 1)):
            n0, n1 = node_matrix[j][col_a], node_matrix[j][col_b]
            if frozenset((n0, n1)) in reserved_struts:
                continue
            elem = TrussElement(nodes=[n0, n1], section=sec_strut_rigid)
            prt.add_element(elem)
            elements_classification['TIES'].append(elem)

    E_diag_eq = k_floor_shear * L_tie / A_sec
    mat_diag  = ElasticIsotropic(E=E_diag_eq, v=0.2, density=2400 * u.kg_per_m3, notension=True)
    sec_diag  = RectangularSection(w=w_sec * u.mm, h=h_sec * u.mm, material=mat_diag)

    for j in range(len(x_steps)):
        for i in range(len(governing_nodes_per_bay[j]) - 1):
            node_indice1 = governing_nodes_per_bay[j][i]
            node_indice2 = governing_nodes_per_bay[j][i + 1]
            for n0, n1 in [(node_matrix[node_indice1][j],     node_matrix[node_indice2][j + 1]),
                           (node_matrix[node_indice2][j], node_matrix[node_indice1][j + 1])]:
                if frozenset((n0, n1)) in reserved_diagonals:
                    continue
                elem = TrussElement(nodes=[n0, n1], section=sec_diag)
                prt.add_element(elem)
                elements_classification['DIAGS'].append(elem)

    for j in range(len(node_matrix[0])):
        for i in range(len(node_matrix) - 1):
            nstart = node_matrix[i][j]
            nend   = node_matrix[i + 1][j]
            if frozenset((nstart, nend)) in reserved_beams:
                continue
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

    # ELEMENTS — Saint-André braces (X-braces) in the reservation opening.
    # One small rigid HEB cross per bay, stacked over the full height of the
    # opening, added on top of the (already carved-out) struts/diagonals.
    saint_andre = SAINT_ANDRE_BRACING[floor_type]
    if saint_andre:
        row0, row1 = saint_andre['rows']
        col0, col1 = saint_andre['columns']
        sec_brace  = getattr(ISection, saint_andre['section'])(material=mat_beam)

        for row in range(row0, row1):
            for n0, n1 in [(node_matrix[row][col0], node_matrix[row + 1][col1]),
                           (node_matrix[row][col1], node_matrix[row + 1][col0])]:
                elem = BeamElement(nodes=[n0, n1], section=sec_brace, orientation=[1, 0, 0])
                prt.add_element(elem)
                elements_classification['BEAMS'].append(elem)

    # The first 4 entries of fixed_nodes_index are the direction-specific corner
    # supports (1 full pin + 3 sliding); any further entries are diaphragm nodes,
    # which stay free (matching Diaphragm_reservations.py's default
    # DIAPHRAGM_FIXED=False / BC_PERM=False behaviour).
    primary_fixed_nodes = fixed_nodes[:4]
    not_fixed_nodes = [n for n in mdl.nodes if n not in primary_fixed_nodes]

    bc_full    = MechanicalBC(x=True,  y=True,  z=True, xx=True, yy=True, zz=False)
    bc_sliding = MechanicalBC(**BC1_PARAMS[wind_direction])
    bc_free    = MechanicalBC(x=False, y=False, z=True, xx=True, yy=True, zz=False)
    mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=primary_fixed_nodes[0],  condition=bc_full))
    mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=primary_fixed_nodes[1:], condition=bc_sliding))
    mdl.add_bcs(bc_fields=BoundaryConditionsField(distribution=not_fixed_nodes, condition=bc_free))

    prb = mdl.add_problem(problem=Problem(name=f"batch_{floor_type}_{stiffness}_{combination}"))
    stp = prb.add_step(StaticStep(test="NormDispIncr 1.0e-2 100"))
    stp.add_combination(LoadFieldsCombination.ec_sls_characteristic())
    stp.add_uniform_forcefield(nodes=loaded_nodes, **loads, load_case="Q")
    disp = stp.add_field_output(DisplacementFieldResults())
    sf   = stp.add_field_output(SectionForcesFieldResults())
    rf   = stp.add_field_output(ReactionFieldResults())

    prb.analyse_and_extract(problems=[prb], path=TEMP, verbose=False, erase_data="armageddon")

    max_deformed_y = disp.get_max_result('y')
    min_deformed_y = disp.get_min_result('y')
    max_y = max_deformed_y if max_deformed_y.y > abs(min_deformed_y.y) else min_deformed_y
    max_deformed_x = disp.get_max_result('x')
    min_deformed_x = disp.get_min_result('x')
    max_x = max_deformed_x if max_deformed_x.x > abs(min_deformed_x.x) else min_deformed_x

    react = rf
    rx_fixed = [react.get_result_at(n).x / 1000 for n in fixed_nodes]
    ry_fixed = [react.get_result_at(n).y / 1000 for n in fixed_nodes]

    ties_Nx  = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['TIES']]
    beams_Nx = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['BEAMS']]
    diag_Nx  = [sf.get_result_at(e).Fx_1 / 1000 for e in elements_classification['DIAGS']]

    return {
        'wind':       wind_direction,
        'stiffness':  stiffness,
        'comb':       combination,
        'ux_max':     round(abs(max_x.x), 2),
        'uy_max':     round(abs(max_y.y), 2),
        'floor_max':  round(max(ties_Nx),  1),
        'tie_min':    round(min(ties_Nx),  1),
        'diag_max':   round(max(diag_Nx),  1),
        'diag_min':   round(min(diag_Nx),  1),
        'beam_max':   round(max(beams_Nx), 1),
        'beam_min':   round(min(beams_Nx), 1),
        'rx_max':     round(max(rx_fixed, key=abs), 1),
        'ry_max':     round(max(ry_fixed, key=abs), 1),
    }


# ==============================================================
#  BATCH LOOP
# ==============================================================
all_results = {w: [] for w in WIND_DIRECTIONS}   # wind direction → list of row dicts (all stiffnesses)

for stiffness in STIFFNESSES:
    print(f"\n{'='*60}")
    print(f"  STIFFNESS: {stiffness}")
    print(f"{'='*60}")
    required_combination = STIFFNESS_COMBINATION.get(stiffness)
    for wind_dir, combination in CASES:
        if required_combination and combination != required_combination:
            continue
        res = run_case(floor_type, wind_dir, combination, stiffness)
        all_results[wind_dir].append(res)


# ==============================================================
#  EXCEL EXPORT — one sheet per wind direction, rows grouped by stiffness
# ==============================================================
HEADERS = [
    'Stiffness', 'Combinaison',
    'ux_max [mm]', 'uy_max [mm]',
    'FLOOR MAX [kN]', 'TIE MIN [kN]',
    'DIAG MAX [kN]', 'DIAG MIN [kN]',
    'BEAM MAX [kN]', 'BEAM MIN [kN]',
    'Rx_max [kN]', 'Ry_max [kN]',
]

ROW_KEYS = [
    'stiffness', 'comb',
    'ux_max', 'uy_max',
    'floor_max', 'tie_min',
    'diag_max', 'diag_min',
    'beam_max', 'beam_min',
    'rx_max', 'ry_max',
]

# Styles
HDR_FONT  = Font(bold=True, color='FFFFFF')
WIND_FILLS = {
    'X+': PatternFill('solid', fgColor='1F5C99'),
    'X-': PatternFill('solid', fgColor='1F7A99'),
    'Y+': PatternFill('solid', fgColor='1F7A4D'),
    'Y-': PatternFill('solid', fgColor='8B1A1A'),
}
# Light row tint per stiffness, so the three stiffness blocks stay visually
# distinct within a single wind-direction sheet.
STIFFNESS_ROW_FILLS = {
    'LOW':      PatternFill('solid', fgColor='EAF0FB'),
    'HIGH-SLS': PatternFill('solid', fgColor='E9F7EF'),
    'HIGH-ULS': PatternFill('solid', fgColor='FBEAEA'),
}
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'),  bottom=Side(style='thin'),
)
CENTER = Alignment(horizontal='center', vertical='center')

wb = openpyxl.Workbook()
wb.remove(wb.active)  # remove default empty sheet

for wind_dir in WIND_DIRECTIONS:
    rows = all_results[wind_dir]
    ws = wb.create_sheet(title=wind_dir)

    # Sheet title
    ws.merge_cells(f"A1:{get_column_letter(len(HEADERS))}1")
    title_cell = ws.cell(row=1, column=1,
                         value=f"{floor_type} — Vent {wind_dir}")
    title_cell.font      = Font(bold=True, size=12, color='FFFFFF')
    title_cell.fill      = WIND_FILLS[wind_dir]
    title_cell.alignment = CENTER

    # Column headers
    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=2, column=col, value=header)
        cell.font      = HDR_FONT
        cell.fill      = WIND_FILLS[wind_dir]
        cell.alignment = CENTER
        cell.border    = THIN_BORDER

    # Data rows
    for row_idx, res in enumerate(rows, start=3):
        fill = STIFFNESS_ROW_FILLS.get(res['stiffness'])
        for col, key in enumerate(ROW_KEYS, start=1):
            cell = ws.cell(row=row_idx, column=col, value=res[key])
            cell.alignment = CENTER
            cell.border    = THIN_BORDER
            if fill:
                cell.fill = fill

    # Column widths
    col_widths = [10, 12] + [14] * (len(HEADERS) - 2)
    for col, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 18
    ws.freeze_panes = 'A3'

excel_path = os.path.join(HERE, f'SADV_{floor_type}_results_{date}.xlsx')
wb.save(excel_path)
print(f"\nExcel exporté : {excel_path}")


# ==============================================================
#  CONSOLE SUMMARY
# ==============================================================
for wind_dir in WIND_DIRECTIONS:
    rows = all_results[wind_dir]
    print(f"\n{'='*60}")
    print(f"  VENT: {wind_dir}")
    print(f"{'='*60}")
    print('  ' + '\t'.join(HEADERS))
    for r in rows:
        print('  ' + '\t'.join(str(r[k]) for k in ROW_KEYS))
