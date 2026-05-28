# Import necessary classes from compas_fea2 for creating the model, materials, and elements
import os
import compas_fea2

from compas.geometry import Point, Line
from compas.geometry import Point, Line

from compas_fea2.model import Model, Part, ElasticIsotropic, UniaxialBilinearMaterial, TrussSection, RectangularSection, BeamElement, TrussElement, Node, ISection
from compas_fea2.problem import Problem, StaticStep, LoadFieldsCombination
from compas_fea2.results import DisplacementFieldResults, ReactionFieldResults, SectionForcesFieldResults
import compas_fea2.units as u
#--------------------------------------
# Backend
#--------------------------------------
# compas_fea2.set_backend("abaqus")
compas_fea2.set_backend("opensees")
# compas_fea2.set_backend("compas_fea2_sofistik")

u.set_unit_system('SI-mm')
u.set_output_magnitudes(True)

HERE = os.path.dirname(__file__)
TEMP = os.path.join(HERE, "..", "..", "temp")

#--------------------------------------
# Units
#--------------------------------------
# Define the unit system to be used (SI with millimeters)
# from compas_fea2.units import GPa, kg_per_m3, cm, kN

#--------------------------------------
# Model
#--------------------------------------
# Initialize the main finite element model
mdl = Model(name="simplebeam")
prt = mdl.add_part(Part())

elements_classification = {}
elements_classification['BEAMS'] = []
elements_classification['DIAGS'] = []
elements_classification['TIES'] = []

x_steps = [11090, 
           11090, 11090, 
           11090, 11090
           ]
y_steps = [4680, 
          6000, 6000, 6000, 6000, 
           4680
           ]


k_floor_shear = 14400
# k_floor_shear = 30000
k_floor = 41100 #N/mm
# k_floor = 330000 #N/mm
d_tie = 58 #mm
max_disp_c = 2 #mm


fixed_nodes_index = [(0,2), (0,4), (-1,0), (-1, 4)]
# fixed_nodes_index = [(4,0), (8,0), (4,-1), (8,-1)]
# fixed_nodes_index = [(0,0), (-1,0), (-1,-1), (0,-1)]

loads = {'x': -36900}
# loads = {'y': -136250}


node_matrix = []

# coordonnées cumulées
x_coords = [0]
y_coords = [0]

# construction des coordonnées X
for dx in x_steps:
    x_coords.append(x_coords[-1] + dx)

# construction des coordonnées Y
for dy in y_steps:
    dy_1 = dy/2
    y_coords.append(y_coords[-1] + dy_1)
    y_coords.append(y_coords[-1] + dy_1)

# création de la grille de noeuds
for y in y_coords:

    row = []

    for x in x_coords:

        node = Node([x, y, 0])
        row.append(node)
        prt.add_node(node)

    node_matrix.append(row)



# Geometry with compas.geometry objects
# The geometry being defined through compas.geometry, the units pint methods can't be used
# The users must care to the consistency of the units

n_column = len(node_matrix[0])
n_lines = len(node_matrix)

fixed_nodes = [node_matrix[i][j] for i,j in fixed_nodes_index]

from compas_viewer import Viewer
from compas_viewer.config import Config
from compas_viewer.config import RendererConfig
from compas_viewer.config import RendererConfig
from compas_viewer.config import CameraConfig
from compas_viewer.renderer.camera import RotationEuler
from compas.colors import Color
from compas_viewer.scene import Tag

bb = mdl.bounding_box
renderer = RendererConfig(show_grid=False)
camera = CameraConfig(target=[(bb.xmax/2),(bb.ymax)/2,0], position=[(bb.xmax/2),(bb.ymax)/2,100] )
config = Config(unit='mm', 
                renderer=renderer, camera = camera
                )

viewer = Viewer(config=config)
tie_floor = viewer.scene.add_group(name = 'TIE_FLOOR', show=False)
# TIE /RFSs
E_steel = 210000 #MPa ou N/mm2
L_tie = 11090 # mm
k_tie = E_steel*(3.14*(d_tie/2)**2)/L_tie #N/mm


loaded_nodes =  [node_matrix[i][-1] for i in range(n_lines)]
# loaded_nodes =  [node_matrix[0][j] for j in range(n_column)]
w_sec = 100
h_sec = 100
A_sec = w_sec*h_sec

E_tie_eq = k_tie * L_tie / A_sec
E_floor_eq = k_floor * L_tie / A_sec
epsyc_tie = -max_disp_c / L_tie  # déformation de plastification = 2mm de raccourcissement

mat_tie = UniaxialBilinearMaterial(
    kt=E_tie_eq,      # traction élastique avec le module du tie
    kc=E_floor_eq,    # compression : raideur plancher
    epsyc=epsyc_tie,  # plateau plastique après 2mm de déformation
)

sec_tie = TrussSection(
    A=A_sec,
    material=mat_tie,
)

for row in node_matrix:
    for i in range(len(row)-1):
        tie_element = TrussElement(nodes=[row[i], row[i+1]], section=sec_tie)
        prt.add_element(tie_element)
        tie_floor.add(Line(row[i].point, row[i+1].point), color=Color.blue())
        elements_classification['TIES'].append(tie_element)

# DIAGONALE : FLOO SHEAR


E_floor_eq = k_floor_shear *11090 / A_sec
mat_diag = ElasticIsotropic(
    E=E_floor_eq,  # Young's modulus (30 GPa)
    v=0.2,  # Poisson's ratio (dimensionless)
    density=2400 * u.kg_per_m3,  # Density (2400 kg/m³),
    notension = True
)

sec_diag = RectangularSection(
    w= w_sec * u.mm, #width
    h= h_sec * u.mm, # height
    material= mat_diag 
)


diags = viewer.scene.add_group(name = 'DIAGONALS', show=False)
for i in range(len(node_matrix)-1):
    for j in range(len(node_matrix[0])-1):
        tie_element = TrussElement(nodes=[node_matrix[i][j], node_matrix[i+1][j+1]], section=sec_diag)
        prt.add_element(tie_element)
        diags.add(Line(node_matrix[i][j].point, node_matrix[i+1][j+1].point), color=Color.orange())
        elements_classification['DIAGS'].append(tie_element)
        tie_element = TrussElement(nodes=[node_matrix[i+1][j], node_matrix[i][j+1]], section=sec_diag)
        prt.add_element(tie_element)
        diags.add(Line(node_matrix[i+1][j].point, node_matrix[i][j+1].point), color=Color.orange())
        elements_classification['DIAGS'].append(tie_element)


mat_beam =  ElasticIsotropic(
    E=210 *u.GPa,  # Young's modulus (30 GPa)
    v=0.2,  # Poisson's ratio (dimensionless)
    density=2400 * u.kg_per_m3,  # Density (2400 kg/m³),
)
sec_beam = ISection.IPE500(
    material= mat_beam 
)
beams = viewer.scene.add_group(name = 'I-BEAMS', show=False)
for j in range(len(node_matrix[0])):
    for i in range(len(node_matrix)-1):
        # beam discretization
        nstart = node_matrix[i][j]
        nend = node_matrix[i+1][j]
        beams.add(Line(nstart.point, nend.point), color=Color.green())
        length = abs(nend.y-nstart.y)
        n0 = nstart
        for i in range(5):
            n1 = Node([n0.x, n0.y+length/6, n0.z])
            prt.add_node(n1)
            beam_element = BeamElement(nodes=[n0, n1], section=sec_beam, orientation = [1,0,0])
            elements_classification['BEAMS'].append(beam_element)
            prt.add_element(beam_element)
            n0 = n1
        beam_element = BeamElement(nodes=[n1, nend], section=sec_beam, orientation = [1,0,0])
        elements_classification['BEAMS'].append(beam_element)
        prt.add_element(beam_element)

# viewer.show()

# Meshing and creation of part with specific method
not_fixed_nodes = []
for node in mdl.nodes :
    if node not in fixed_nodes:
        not_fixed_nodes.append(node)


mdl.add_pin_bc(nodes = fixed_nodes)
from compas_fea2.model.bcs import MechanicalBC
from compas_fea2.model.fields import BoundaryConditionsField
bc = MechanicalBC(x=False, y=False, z=True, xx=True, yy=True, zz=False)
bc_field = BoundaryConditionsField(distribution=not_fixed_nodes, condition=bc)
mdl.add_bcs(bc_fields=bc_field)

# Visualize the geometry 
# mdl.show()

#--------------------------------------
# Problem
#--------------------------------------

# define the problem
prb = mdl.add_problem(problem=Problem(name="SADV_diaphragm"))
# define a step
stp = prb.add_step(StaticStep())
stp.add_combination(LoadFieldsCombination.ec_sls_characteristic())
# Add a uniform load
stp.add_uniform_forcefield(nodes= loaded_nodes, **loads, load_case="Q")
# stp.add_uniform_forcefield(nodes= loaded_nodes, y=136260, load_case="Q")
# define the outputs
disp = stp.add_field_output(DisplacementFieldResults())
react = stp.add_field_output(ReactionFieldResults())
sf = stp.add_field_output(SectionForcesFieldResults())

#--------------------------------------
# Analysis
#--------------------------------------

prb.analyse_and_extract(problems=[prb], path=TEMP, verbose=True)

print("""*************************
RESULTS POST-PROCESSING
*************************""")
# Print reaction results
print("Max/Min reaction forces in X direction [N]: ", 
      react.get_limits_component('x')[0].magnitude, "/",
      react.get_limits_component('x')[1].magnitude)
print("Max/Min reaction forces in Y direction [N]: ", 
      react.get_limits_component('y')[0].magnitude, "/",
      react.get_limits_component('y')[1].magnitude)
#--------------------------------------
# VERIFICATION OF RESULTS
#--------------------------------------


from compas_viewer import Viewer
from compas_viewer.config import Config
from compas_viewer.config import RendererConfig
from compas_viewer.config import RendererConfig
from compas_viewer.config import CameraConfig
from compas_viewer.renderer.camera import RotationEuler
from compas.colors import Color
from compas_viewer.scene import Tag

def add_text_label(viewer, text: str, x: float, y: float, scale: float, parent, color: Color, show=False) -> None:
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
bb = mdl.bounding_box
# renderer = RendererConfig(show_grid=False)
# camera = CameraConfig(target=[(bb.xmax/2),(bb.ymax)/2,0], position=[(bb.xmax/2),(bb.ymax)/2,100] )
# config = Config(unit='mm', 
#                 renderer=renderer, camera = camera
#                 )

# viewer = Viewer(config=config)
# viewer.renderer.camera.position = [(bb.xmax/2),(bb.ymax)/2,100] 
# viewer.renderer.target = [(bb.xmax/2),(bb.ymax)/2,0] 
# viewer.renderer.camera.rotation = RotationEuler([0,0, 90*3.14/180])

initial_model = viewer.scene.add_group(name='Initial', show=False)
deformed_model = viewer.scene.add_group(name='Deformed', show=True)

for element in mdl.elements:
    line = Line(start=element.points[0], end = element.points[-1])
    initial_model.add(line, color= Color.grey(), opacity=0.3)

# DEFORMED 
scale = 100
max_deformed_y = disp.get_max_result('y')
min_deformed_y = disp.get_min_result('y')
max_y =  max_deformed_y if max_deformed_y.y > abs(min_deformed_y.y) else min_deformed_y
max_deformed_x = disp.get_max_result('x')
min_deformed_x = disp.get_min_result('x')
max_x =  max_deformed_x if max_deformed_x.x > abs(min_deformed_x.x) else min_deformed_x

print('uy_max (mm) :')
print(max_y.y)
print('ux_max (mm) :')
print(max_x.x)

for element in mdl.elements :
    start = element.nodes[0]
    end = element.nodes[-1]
    start_disp = disp.get_result_at(location=start)
    end_disp = disp.get_result_at(location=end)
    deformed_start = Point(x=start.x+start_disp.x*scale, y=start.y+start_disp.y*scale, z=0)
    deformed_end = Point(x=end.x+end_disp.x*scale, y=end.y+end_disp.y*scale, z=0)
    line = Line(start=deformed_start, end = deformed_end)
    deformed_model.add(line, color = Color.red() )
add_text_label(viewer=viewer, text=str(int(max_y.y))+ " mm", x=max_y.node.x , y= max_y.node.y, parent=deformed_model, color = Color.black(), scale=200)
add_text_label(viewer=viewer, text=str(int(max_x.x))+ " mm", x=max_x.node.x , y= max_x.node.y, parent=deformed_model, color = Color.black(), scale=200)

# REACTION FORCES
# reaction_forces = viewer.scene.add_group(name='Reaction forces', show=False)
# max_x_rf = react.get_max_result(component='x').x
# max_y_rf = react.get_max_result(component='y').y
# for node in mdl.nodes :
#     rf_result = react.get_result_at(location=node)
#     if rf_result.vector.length>0:
#         line = Line.from_point_direction_length(point=[node.point.x-rf_result.vector.x/max_x_rf*1000, node.point.y, 0], direction=[rf_result.vector.x/abs(rf_result.vector.x),0,0], length=abs(rf_result.vector.x)/max_x_rf*1000)
#         reaction_forces.add(line, color=Color.blue(), linewidth=2)
#         add_text_label(viewer=viewer, text=str(int(rf_result.x/1000))+ " kN", x=rf_result.node.x+1000 , y= rf_result.node.y, parent=reaction_forces, color = Color.black(), scale=200)

#         line = Line.from_point_direction_length(point=[node.point.x, node.point.y-rf_result.vector.y/max_y_rf*1000, 0], direction=[0,rf_result.vector.y/abs(rf_result.vector.y),0], length=abs(rf_result.vector.y)/max_y_rf*1000)
#         reaction_forces.add(line, color=Color.blue(), linewidth=2)

# SECITON FORCES
section_forces = viewer.scene.add_group(name='SF COMPRESSION/TENSION', show=True)
max_compression = sf.get_max_result(component='Fx_1')
max_tension = sf.get_min_result(component='Fx_1')
max_value = max(abs(max_compression.Fx_1), abs(max_tension.Fx_1))
for element in mdl.elements:
    sf_result = sf.get_result_at(location=element)
    line = Line(start=element.points[0], end = element.points[-1])
    if sf_result.Fx_1<0:
        section_forces.add(line, color=Color.red(), linewidth=0.5+8*abs(sf_result.Fx_1/max_value))
    elif sf_result.Fx_1>0:
        section_forces.add(line, color=Color.blue(), linewidth=0.5+8*abs(sf_result.Fx_1/max_value))
    else :
        section_forces.add(line, color=Color.grey(), opacity=0.3)
add_text_label(viewer=viewer, text=str(int(max_compression.Fx_1/1000))+ " kN", x=max_compression.reference_point.x+1000 , y= max_compression.reference_point.y, parent=section_forces, color = Color.blue(), scale=200, show=True)
add_text_label(viewer=viewer, text=str(abs(int(max_tension.Fx_1/1000)))+ " kN", x=max_tension.reference_point.x+1000 , y= max_tension.reference_point.y, parent=section_forces, color = Color.red(), scale=200, show=True)
        
# BENDING MOMENT
bending_sections = viewer.scene.add_group(name='SF MOMENT', show=True)
max_bending = sf.get_max_result(component='Mz_1')
min_bending = sf.get_min_result(component='Mz_1')
max_value = max(abs(max_bending.Mz_1), abs(min_bending.Mz_1))
# print(max_value)

from compas.geometry import Polygon
for element in mdl.elements:
    if isinstance(element, BeamElement):
        sf_result = sf.get_result_at(location=element)
        # points = [element.points[0], element.points[-1], Point(element.points[-1].x-sf_result.Mz_2/max_value*1000 , element.points[-1].y, 0), Point(element.points[0].x+sf_result.Mz_1/max_value*1000 , element.points[0].y, 0)]
        # pol = Polygon( points=points)
        # if len(pol.points)>2:
        #     bending_sections.add(pol)
        # else :
        #     print('wrf')
        line = Line(start=Point(element.points[0].x+sf_result.Mz_1/max_value*1000*2 , element.points[0].y, 0), end = Point(element.points[-1].x-sf_result.Mz_2/max_value*1000*2 , element.points[-1].y, 0))
        if sf_result.Mz_1<0:
            bending_sections.add(line, color=Color.violet(), linewidth=0.5+8*abs(sf_result.Mz_1/max_value))
        elif sf_result.Mz_1>0:
            bending_sections.add(line, color=Color.pink(), linewidth=0.5+8*abs(sf_result.Mz_1/max_value))
        else :
            bending_sections.add(line, color=Color.grey(), opacity=0.3)
add_text_label(viewer=viewer, text=str(int(max_bending.Mz_1/1000000))+ " kN.m", x=max_bending.reference_point.x+1000 , y= max_bending.reference_point.y, parent=bending_sections, color = Color.blue(), scale=200, show=True)
add_text_label(viewer=viewer, text=str(abs(int(min_bending.Mz_2/1000000)))+ " kN.m", x=min_bending.reference_point.x+1000 , y= min_bending.reference_point.y, parent=bending_sections, color = Color.red(), scale=200, show=True)

#LOADS
applied_loads = viewer.scene.add_group(name='Applied loads')
for load_field in stp.loads:
    for node, load in load_field.node_load:
        applied_loads.add(load.force_vector.scaled(0.1), anchor = node.point.translated(-load.force_vector.scaled(0.1)), color = Color.green())

# BOUNDARY CONDITIONS
bc_viewer = viewer.scene.add_group(name='BC')
for node in fixed_nodes:
    bc_viewer.add(node.point, pointcolor = Color.black(), pointsize = 30)

# SECITON FORCES
# section_forces = viewer.scene.add_group(name='Section forces')
# max_compression = sf.get_max_result(component='Fx_1').Fx_1
# max_tension = sf.get_max_result(component='Fx_1').Fx_1
# for element in mdl.elements:
#     sf_result = sf.get_result_at(location=element)
#     line = Line(start=element.points[0], end = element.points[-1])
#     if sf_result.Fx_1<0:
#         section_forces.add(line, color=Color.red(), linewidth=8*abs(sf_result.Fx_1/max_tension))
#     elif sf_result.Fx_1>0:
#         section_forces.add(line, color=Color.blue(), linewidth=8*abs(sf_result.Fx_1/max_compression))
#     else :
#         section_forces.add(line, color=Color.grey(), opacity=0.3)


viewer.show()
ties_Nx = [sf.get_result_at(element).Fx_1/1000 for element in elements_classification['TIES']]
print('NEGATIVE VALUE IS TENSION / POSITIVE COMPRESSION (kN):')
print('TIES MINvAXIAL FORCES / FLOOR MAX AXIAL FORCE (kN):')
print(min(ties_Nx), max(ties_Nx))
beams_Nx = [sf.get_result_at(element).Fx_1/1000 for element in elements_classification['BEAMS']]
print('BEAMS MIN/MAX AXIAL FORCES (kN):')
print(min(beams_Nx), max(beams_Nx))
print('DIAGS MIN/MAX AXIAL FORCES (kN):')
diag_Nx = [sf.get_result_at(element).Fx_1/1000 for element in elements_classification['DIAGS']]
print(min(diag_Nx), max(diag_Nx))

print('Youhou')