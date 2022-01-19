import torch
from torch import nn

from fab.target_distributions.base import TargetDistribution

import boltzgen as bg
from simtk import openmm as mm
from simtk import unit
from simtk.openmm import app
from openmmtools import testsystems
import mdtraj



class AldpBoltzmann(nn.Module, TargetDistribution):
    def __init__(self, data_path, temperature=1000, energy_cut=1.e+8, energy_max=1.e+20, n_threads=4):
        super(AldpBoltzmann, self).__init__()
        # Define molecule parameters
        ndim = 66
        z_matrix = [
            (0, [1, 4, 6]),
            (1, [4, 6, 8]),
            (2, [1, 4, 0]),
            (3, [1, 4, 0]),
            (4, [6, 8, 14]),
            (5, [4, 6, 8]),
            (7, [6, 8, 4]),
            (11, [10, 8, 6]),
            (12, [10, 8, 11]),
            (13, [10, 8, 11]),
            (15, [14, 8, 16]),
            (16, [14, 8, 6]),
            (17, [16, 14, 15]),
            (18, [16, 14, 8]),
            (19, [18, 16, 14]),
            (20, [18, 16, 19]),
            (21, [18, 16, 19])
        ]
        cart_indices = [6, 8, 9, 10, 14]

        # System setup
        system = testsystems.AlanineDipeptideVacuum(constraints=None)
        sim = app.Simulation(system.topology, system.system,
                             mm.LangevinIntegrator(temperature * unit.kelvin,
                                                   1. / unit.picosecond,
                                                   1. * unit.femtosecond),
                             mm.Platform.getPlatformByName('Reference'))

        # Load data for transform
        traj = mdtraj.load(data_path)
        traj.center_coordinates()

        # superpose on the backbone
        ind = traj.top.select("backbone")
        traj.superpose(traj, 0, atom_indices=ind, ref_atom_indices=ind)

        # Gather the training data into a pytorch Tensor with the right shape
        transform_data = traj.xyz
        n_atoms = transform_data.shape[1]
        n_dim = n_atoms * 3
        transform_data_npy = transform_data.reshape(-1, n_dim)
        transform_data = torch.from_numpy(transform_data_npy.astype("float64"))

        # Set distribution
        self.coordinate_transform = bg.flows.CoordinateTransform(transform_data, ndim,
                                                                 z_matrix, cart_indices)

        if n_threads > 1:
            self.p = bg.distributions.TransformedBoltzmannParallel(system, temperature,
                                                                   energy_cut=energy_cut, energy_max=energy_max,
                                                                   transform=self.coordinate_transform,
                                                                   n_threads=n_threads)
        else:
            self.p = bg.distributions.TransformedBoltzmann(sim.context, temperature,
                                                           energy_cut=energy_cut, energy_max=energy_max,
                                                           transform=self.coordinate_transform)

    def log_prob(self, x: torch.tensor):
        return self.p.log_prob(x)