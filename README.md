# IceLossMethod
Tooling to compute icing losses from wind turbine SCADA data. Produced by IEA wind tasks 19 and 54.

# Installation
Running the code requires Python libraries: Dash, Flask, Plotly, Matplotlib, Numpy and Pandas
requirements can be installed using Conda with
```
conda env create -f environment.yml
OR
conda create -n dashenv python=3.11 -y
conda activate dashenv
pip install dash dash-bootstrap-components dash-mantine-components pandas matplotlib
cd /pathToYourGitRepo/app
python app.py
```
This will create a new conda environment with Python 3.13 and the required libraries.



# IEA Wind
The International Energy Agency Implementing Agreement for Co-operation
in the Research, Development and Deployment of Wind Energy Systems (IEA Wind) is
a vehicle for member countries to exchange information on the planning and execution
of national, large-scale wind system projects and to undertake co-operative research and
development projects called Tasks or Annexes. IEA Wind is part of IEA’s Technology
Collaboration Programme or TCP.

# Task 54
For the wind industry, cold climate refers to sites that may experience significant
periods of icing events, temperatures below the operational limits of standard wind
turbines, or both. There is vast potential for producing electricity at these often windy
and uninhabited cold climate sites. Consequently, the International Energy Agency
Wind Agreement has since 2002, operated the international working group Task 54 (initially task 19)
Wind Energy in Cold Climates. The goal of this cooperation is to gather and
disseminate information about wind energy in cold climates and to establish guidelines
and state-of-the-art information.

# Disclaimer: 
The IEA Wind agreement, also known as the Implementing Agreement for
Co-operation in the Research, Development, and Deployment of Wind Energy Systems,
functions within a framework created by the International Energy Agency (IEA). Views,
findings, and publications of IEA Wind do not necessarily represent the views or policies
of the IEA Secretariat or of all its individual member countries.

# License

The code is available under the Three Clause BSD License.
