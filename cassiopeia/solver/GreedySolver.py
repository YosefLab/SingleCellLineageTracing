"""
This file stores a subclass of CassiopeiaSolver, the GreedySolver. This class
represents the structure of top-down algorithms that build the reconstructed 
tree by recursively splitting the set of samples based on some split criterion.
"""
import logging

import abc
import networkx as nx
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from cassiopeia.solver import CassiopeiaSolver
from cassiopeia.solver import solver_utilities


class GreedySolver(CassiopeiaSolver.CassiopeiaSolver):
    """
    GreedySolver is an abstract class representing the structure of top-down
    inference algorithms. The solver procedure contains logic to build a tree
    from the root by recursively paritioning the set of samples. Each subclass
    will implement "perform_split", which is the procedure for successively
    partioning the sample set.

    Args:
        character_matrix: A character matrix of observed character states for
            all samples
        missing_char: The character representing missing values
        meta_data: Any meta data associated with the samples
        priors: Prior probabilities of observing a transition from 0 to any
            character state

    Attributes:
        character_matrix: The character matrix describing the samples
        missing_char: The character representing missing values
        meta_data: Data table storing meta data for each sample
        priors: Prior probabilities of character state transitions
        tree: The tree built by `self.solve()`. None if `solve` has not been
            called yet
        prune_cm: A character matrix with duplicate rows filtered out, removing
            doublets from the sample set
    """

    def __init__(
        self,
        character_matrix: pd.DataFrame,
        missing_char: str,
        meta_data: Optional[pd.DataFrame] = None,
        priors: Optional[Dict] = None,
    ):

        super().__init__(character_matrix, missing_char, meta_data, priors)
        self.prune_cm = self.character_matrix.drop_duplicates()
        self.tree = nx.DiGraph()
        for i in range(self.prune_cm.shape[0]):
            self.tree.add_node(i)

    @abc.abstractmethod
    def perform_split(
        self,
        mutation_frequencies: Dict[int, Dict[str, int]],
        samples: List[int],
    ) -> Tuple[List[int], List[int]]:
        """Performs a partition of the samples.

        Args:
            mutation_frequencies: A dictionary containing the frequencies of
                each character/state pair that appear in the character matrix
                restricted to the sample set
            samples: A list of samples to partition

        Returns:
            A tuple of lists, representing the left and right partitions
        """
        pass

    def solve(self) -> nx.DiGraph:
        """Implements a top-down greedy solving procedure.

        Returns:
            A networkx directed graph representing the reconstructed tree
        """

        # A helper function that builds the subtree given a set of samples
        def _solve(samples):
            if len(samples) == 1:
                return samples[0]
            mutation_frequencies = self.compute_mutation_frequencies(samples)
            # Finds the best partition of the set given the split criteria
            left_set, right_set = self.perform_split(
                mutation_frequencies, samples
            )
            # Generates a root for this subtree with a unique int identifier
            root = len(self.tree.nodes)
            self.tree.add_node(root)
            # If unable to return a split, generate a polytomy and return
            if len(left_set) == 0:
                for i in right_set:
                    self.tree.add_edge(root, i)
                return root
            if len(right_set) == 0:
                for i in left_set:
                    self.tree.add_edge(root, i)
                return root
            # Recursively generate the left and right subtrees
            left_child = _solve(left_set)
            right_child = _solve(right_set)
            self.tree.add_edge(root, left_child)
            self.tree.add_edge(root, right_child)
            return root

        _solve(range(self.prune_cm.shape[0]))
        # Collapse 0-mutation edges and append duplicate samples
        solver_utilities.collapse_tree(
            self.tree, True, self.prune_cm, self.missing_char
        )
        solver_utilities.post_process_tree(self.tree, self.character_matrix)

    def compute_mutation_frequencies(
        self, samples: List[int] = None
    ) -> Dict[int, Dict[int, int]]:
        """Computes the number of samples in a character matrix that have each
        character/state mutation.

        Generates a dictionary that maps each character to a dictionary of state/
        sample frequency pairs, allowing quick lookup. Subsets the character matrix
        to only include the samples in the sample set.

        Args:
            cm: The character matrix from which to calculate frequencies
            missing_char: The character representing missing values
            samples: The set of relevant samples in calculating frequencies

        Returns:
            A dictionary containing frequency information for each character/state
            pair

        """
        if not samples:
            samples = list(range(self.prune_cm.shape[0]))
        cm = self.prune_cm.iloc[samples, :]
        freq_dict = {}
        for char in range(cm.shape[1]):
            char_dict = {}
            state_counts = np.unique(cm.iloc[:, char], return_counts=True)
            for i in range(len(state_counts[0])):
                state = state_counts[0][i]
                count = state_counts[1][i]
                char_dict[state] = count
            if self.missing_char not in char_dict:
                char_dict[self.missing_char] = 0
            freq_dict[char] = char_dict
        return freq_dict