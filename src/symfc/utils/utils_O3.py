"""Utility functions for 3rd order force constants."""

import numpy as np
from scipy.sparse import csr_array, kron

from symfc.spg_reps.spg_reps_O3 import SpgRepsO3
from symfc.utils.cutoff_tools import FCCutoff
from symfc.utils.utils import get_indep_atoms_by_lat_trans


def get_atomic_lat_trans_decompr_indices_O3(trans_perms: np.ndarray) -> np.ndarray:
    """Return indices to de-compress compressed matrix by atom-lat-trans-sym.

    This is atomic permutation only version of get_lat_trans_decompr_indices.

    Usage
    -----
    vec[indices] of shape (n_a*N*N,) gives an array of shape=(N**3,).
    1/sqrt(n_lp) must be multiplied manually after decompression.

    Parameters
    ----------
    trans_perms : ndarray
        Permutation of atomic indices by lattice translational symmetry.
        dtype='intc'.
        shape=(n_l, N), where n_l and N are the numbers of lattce points and
        atoms in supercell.

    Returns
    -------
    indices : ndarray
        Indices of n_a * N * N elements.
        shape=(N**3,), dtype='int_'.

    """
    indep_atoms = get_indep_atoms_by_lat_trans(trans_perms)
    n_lp, N = trans_perms.shape
    size_row = N**3

    n = 0
    indices = np.zeros(size_row, dtype="int_")
    for i_patom in indep_atoms:
        index_shift_i = trans_perms[:, i_patom] * N**2
        for j in range(N):
            index_shift_j = index_shift_i + trans_perms[:, j] * N
            for k in range(N):
                index_shift = index_shift_j + trans_perms[:, k]
                indices[index_shift] = n
                n += 1
    assert n * n_lp == size_row
    return indices


def get_lat_trans_decompr_indices_O3(trans_perms: np.ndarray) -> np.ndarray:
    """Return indices to de-compress compressed matrix by lat-trans-sym.

    Usage
    -----
    vec[indices] of shape (n_a*N*N*27,) gives an array of shape=(N**3*27,).
    1/sqrt(n_lp) must be multiplied manually after decompression to mimic
    get_lat_trans_compr_matrix.

    Parameters
    ----------
    trans_perms : ndarray
        Permutation of atomic indices by lattice translational symmetry.
        dtype='intc'.
        shape=(n_l, N), where n_l and N are the numbers of lattce points and
        atoms in supercell.

    Returns
    -------
    indices : ndarray
        Indices of n_a * N * N * 27 elements.
        shape=(N^3*27,), dtype='int_'.

    """
    indep_atoms = get_indep_atoms_by_lat_trans(trans_perms)
    n_a = len(indep_atoms)
    N = trans_perms.shape[1]
    n_lp = N // n_a
    size_row = 27 * N**3

    trans_perms = trans_perms.astype("int_")
    n = 0
    indices = np.zeros(size_row, dtype="int_")
    for i_patom in indep_atoms:
        index_shift_i = trans_perms[:, i_patom] * N**2 * 27
        for j in range(N):
            index_shift_j = index_shift_i + trans_perms[:, j] * N * 27
            for k in range(N):
                index_shift = index_shift_j + trans_perms[:, k] * 27
                for ab in range(27):
                    indices[index_shift + ab] = n
                    n += 1
    assert n * n_lp == size_row
    return indices


def get_compr_coset_projector_O3(
    spg_reps: SpgRepsO3,
    fc_cutoff: FCCutoff = None,
    atomic_decompr_idx: np.ndarray = None,
    c_pt: csr_array = None,
    verbose: bool = False,
) -> csr_array:
    """Return compr matrix of sum of coset reps."""
    trans_perms = spg_reps.translation_permutations
    n_lp, N = trans_perms.shape
    size = N**3 * 27 // n_lp if c_pt is None else c_pt.shape[1]
    coset_reps_sum = csr_array(([], ([], [])), shape=(size, size), dtype="double")

    if atomic_decompr_idx is None:
        atomic_decompr_idx = get_atomic_lat_trans_decompr_indices_O3(trans_perms)

    if fc_cutoff is None:
        nonzero = None
        size_data = N**3
    else:
        nonzero = fc_cutoff.nonzero_atomic_indices_fc3()
        size_data = np.count_nonzero(nonzero)

    factor = 1 / n_lp / len(spg_reps.unique_rotation_indices)
    for i, _ in enumerate(spg_reps.unique_rotation_indices):
        if verbose:
            print("Coset sum:", i + 1, "/", len(spg_reps.unique_rotation_indices))
        permutation = spg_reps.get_sigma3_rep(i, nonzero=nonzero)
        if nonzero is None:
            """Equivalent to mat = C.T @ spg_reps.get_sigma3_rep(i) @ C
            C: atomic_lat_trans_compr_mat, shape=(NNN, NNN/n_lp)"""
            mat = csr_array(
                (
                    np.ones(size_data, dtype="int_"),
                    (atomic_decompr_idx[permutation], atomic_decompr_idx),
                ),
                shape=(N**3 // n_lp, N**3 // n_lp),
                dtype="int_",
            )
        else:
            mat = csr_array(
                (
                    np.ones(size_data, dtype="int_"),
                    (atomic_decompr_idx[permutation], atomic_decompr_idx[nonzero]),
                ),
                shape=(N**3 // n_lp, N**3 // n_lp),
                dtype="int_",
            )

        mat = kron(mat, spg_reps.r_reps[i] * factor)
        if c_pt is not None:
            mat = c_pt.T @ mat @ c_pt

        coset_reps_sum += mat

    return coset_reps_sum


def get_lat_trans_compr_matrix_O3(trans_perms):
    """Return lat trans compression matrix."""
    n_lp, N = trans_perms.shape
    decompr_idx = get_lat_trans_decompr_indices_O3(trans_perms)
    c_trans = _get_lat_trans_compr_matrix_O3(decompr_idx, N, n_lp)
    return c_trans


def _get_lat_trans_compr_matrix_O3(
    decompr_idx: np.ndarray, N: int, n_lp: int
) -> csr_array:
    """Return compression matrix by lattice translation symmetry.

    `decompr_idx` is obtained by `get_lat_trans_decompr_indices`.

    Matrix shape is (NNN333, n_a*NN333), where n_a is the number of independent
    atoms by lattice translation symmetry.

    Data order is (N, N, N, 3, 3, 3, n_a, N, N, 3, 3, 3)
    if it is in dense array.

    """
    NNN27 = N**3 * 27
    compression_mat = csr_array(
        (
            np.full(NNN27, 1 / np.sqrt(n_lp), dtype="double"),
            (np.arange(NNN27, dtype=int), decompr_idx),
        ),
        shape=(NNN27, NNN27 // n_lp),
        dtype="double",
    )
    return compression_mat
