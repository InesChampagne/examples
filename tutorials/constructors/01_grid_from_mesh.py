"""
Tutorial 01: Beam Grid from Mesh

This tutorial demonstrates how to create a simple grid model using COMPAS FEA2.
We will define a grid made of multiple beam segments, apply boundary conditions,
add loads, and run a static analysis to extract and visualize the results.

Steps:
1. Define the grid geometry and material properties.
2. Create a deformable part from the mesh.
3. Set boundary conditions at both ends of the beam.
4. Define a static problem and add loads.
5. Run the analysis and visualize the results.
"""

import os

from compas.datastructures import Mesh

import compas_fea2
from compas_fea2.model import Model, DeformablePart
from compas_fea2.model import ElasticIsotropic, ISection
from compas_fea2.problem import LoadCombination, FieldOutput, StaticStep

from compas_fea2.units import units
units = units(system='SI_mm')

# Set the backend implementation
compas_fea2.set_backend('compas_fea2_opensees')

HERE = os.path.dirname(__file__)
TEMP = os.path.join(HERE, '..', '..', 'temp')

# ==============================================================================
# Create a beam lines model
# ==============================================================================
# Define the plate dimensions and mesh density
lx = (3 * units.m).to_base_units().magnitude
ly = (1 * units.m).to_base_units().magnitude
nx = 10
ny = 3
plate = Mesh.from_meshgrid(lx, nx, ly, ny)

# ==============================================================================
# COMPAS_FEA2
# ==============================================================================
# Initialize the model
mdl = Model(name='steel_grid')

# Define material properties
mat = ElasticIsotropic(E=210 * units.GPa, v=0.2, density=7800 * units("kg/m**3"))

# Define the beams section
sec = ISection(w=50, h=100, tw=2, tf=2, material=mat)

# Create a deformable part from the mesh
prt = DeformablePart.frame_from_compas_mesh(mesh=plate, section=sec, name='grid')
mdl.add_part(prt)

# Set boundary conditions at both ends of the beam
for vertex in plate.vertices():
    location = plate.vertex_coordinates(vertex)
    if location[0] == 0 or location[0] == lx:
        mdl.add_fix_bc(nodes=prt.find_nodes_around_point(location, distance=1))

# Print model summary
mdl.summary()

# ==============================================================================
# Define the problem
# ==============================================================================
prb = mdl.add_problem(name='mid_load')
stp = prb.add_static_step()
stp.combination = LoadCombination.SLS()

# Add a load in the middle of the grid
loaded_nodes = []
for vertex in plate.vertices():
    location = plate.vertex_coordinates(vertex)
    if location[0] == lx/2:
        loaded_nodes.extend(prt.find_nodes_around_point(location, distance=1))
stp.add_node_pattern(nodes=loaded_nodes, z=-1 * units.kN, load_case='LL')

# Define field outputs
fout = FieldOutput(node_outputs=['U', 'RF'], element_outputs=['S', 'SF'])
stp.add_output(fout)

# ==============================================================================
# Run the analysis and show results
# ==============================================================================
# Analyze and extract results to SQLite database
mdl.analyse_and_extract(problems=[prb], path=os.path.join(TEMP, prb.name), verbose=True)

# Get displacement and reaction fields
disp = prb.displacement_field 
react = prb.reaction_field

# Print reaction and displacement results
print("Max reaction force [N]: ", react.get_max_result(2, stp).magnitude)
print("Min displacement [mm]: ", disp.get_min_result(2, stp).magnitude)

# Show deformed shape
prb.show_deformed(scale_results=100, show_nodes=True, show_bcs=0.1)