"""
Tutorial 03: Plate from Mesh Model

This tutorial demonstrates how to create a simple plate model using COMPAS FEA2.
We will define a plate made of a mesh, apply boundary conditions,
add loads, and run a static analysis to extract and visualize the results.

Steps:
1. Define the plate geometry and material properties.
2. Create a deformable part from the mesh.
3. Set boundary conditions at both ends of the plate.
4. Define a static problem and add loads.
5. Run the analysis and visualize the results.
"""

import os

from compas.datastructures import Mesh
from compas_gmsh.models import MeshModel
from compas.geometry import Point, Line

import compas_fea2
from compas_fea2.model import Model, Part
from compas_fea2.model import ElasticIsotropic, SolidSection
from compas_fea2.problem import (
    LoadCombination,
)
from compas_fea2.results import DisplacementFieldResults
from compas_fea2_vedo.viewer import ModelViewer
from compas_fea2.units import units

units = units(system="SI_mm")

# Set the backend implementation
# compas_fea2.set_backend("compas_fea2_opensees")
compas_fea2.set_backend("compas_fea2_calculix")
# compas_fea2.set_backend("compas_fea2_abaqus")
# compas_fea2.set_backend("compas_fea2_castem")
# compas_fea2.set_backend('compas_fea2_sofistik')

HERE = os.path.dirname(__file__)
TEMP = os.path.join(HERE, "..", "..", "temp")

# ==============================================================================
# Create a plate model
# ==============================================================================
# Define the plate dimensions and mesh density
lx = (3 * units.m).to_base_units().magnitude
ly = (1 * units.m).to_base_units().magnitude
nx = 10
ny = 3
plate = Mesh.from_meshgrid(lx, nx, ly, ny)
thk = (10 * units.mm).to_base_units().magnitude
plate = plate.thickened(thk)

# ==============================================================================
# GMSH model
# ==============================================================================
model = MeshModel.from_mesh(plate, targetlength=100)
solid_mesh = model.mesh_to_compas()

# ==============================================================================
# COMPAS_FEA2
# ==============================================================================
# Initialize the model
mdl = Model(name="steel_plate")

# Define material properties
mat = ElasticIsotropic(E=210 * units.GPa, v=0.2, density=7800 * units("kg/m**3"))

# Define the solid section
sec = SolidSection(material=mat)

# Create a deformable part from the mesh
prt = Part.from_gmsh(gmshModel=model, section=sec)
mdl.add_part(prt)

# Set boundary conditions at both ends of the plate
fixed_nodes = prt.nodes.subgroup(condition=lambda node: node.x == 0 or node.x == lx)
mdl.add_fix_bc(nodes=fixed_nodes)

# Print model summary
mdl.summary()

# ==============================================================================
# Define the problem
# ==============================================================================
prb = mdl.add_problem(name="mid_load")
stp = prb.add_static_step()
stp.combination = LoadCombination.SLS()

# Add a load in the middle of the grid
loaded_nodes = prt.nodes.subgroup(condition=lambda node: node.x == lx / 2)
stp.add_uniform_node_load(
    nodes=loaded_nodes, z=-1 * units.kN , load_case="LL"
)

# Define field outputs
stp.add_output(DisplacementFieldResults)

# ==============================================================================
# Run the analysis and show results
# ==============================================================================
# Analyze and extract results to SQLite database
mdl.analyse_and_extract(problems=[prb], path=os.path.join(TEMP, prb.name), verbose=True)

# Show deformed shape
#Compas Viewer
stp.show_deformed(scale_results=1000, show_bcs=0.5, show_loads=0.1)
#Vedo Viewer
viewer = ModelViewer(mdl)
viewer.add_node_field_results(
    stp.displacement_field, draw_cmap="viridis", draw_vectors=100
)
viewer.show()

#Plot deflection mid-width
line = Line(Point(0, ly/2, 0), Point(lx, ly/2, 0))
stp.plot_deflection_along_line(line, n_divide=100)