"""
This file stores a subclass of GreedySolver, the SpectralSolver. 
This subclass implements an inference procedure that uses Fiedler's algorithm to
minimize for a version of the normalized cut on a similarity graph generated from 
the observed mutations on a group of samples. The goal is to find a partition 
on a graph that minimizes seperation in samples that share mutations, normalizing 
for the sizes of each of the sides of the partition.
"""
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import scipy as sp

from typing import Callable, Dict, List, Optional, Tuple, Union

from cassiopeia.solver import GreedySolver
from cassiopeia.solver import graph_utilities
from cassiopeia.solver import dissimilarity_functions


class SpectralSolver(GreedySolver.GreedySolver):
    """
    TODO: Experiment to find the best default similarity function
    The SpectralSolver implements a top-down algorithm that recursively
    partitions the sample set based on similarity. At each recursive step,
    a similarity graph is generated for the sample set, where edges
    represent the number of shared mutations between nodes. Then a partition
    is generated by finding the minimum weight cut over the graph,
    normalized over the sum of edges within each side of the partition. The
    cut is minimized in order to preserve similarities. The final partition
    is then improved upon by a greedy hill-climbing procedure that further
    optimizes the cut.

    Args:
        character_matrix: A character matrix of observed character states for
            all samples
        missing_char: The character representing missing values
        meta_data: Any meta data associated with the samples
        priors: Prior probabilities of observing a transition from 0 to any
            state for each character
        prior_function: A function defining a transformation on the priors
            in forming weights to scale the contribution of each mutation in
            the similarity graph
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations. The default
            is "hamming_distance_without_missing"
        threshold: A minimum similarity threshold to include an edge in the
            similarity graph

    Attributes:
        character_matrix: The character matrix describing the samples
        missing_char: The character representing missing values
        meta_data: Data table storing meta data for each sample
        priors: Prior probabilities of character state transitions
        tree: The tree built by `self.solve()`. None if `solve` has not been
            called yet
        unique_character_matrix: A character matrix with duplicate rows filtered
        duplicate_groups: A mapping of samples to the set of duplicates that
            share the same character vector. Uses the original sample names
        weights: Weights on character/mutation pairs, derived from priors
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations
        threshold: A minimum similarity threshold
    """

    def __init__(
        self,
        character_matrix: pd.DataFrame,
        missing_char: int,
        meta_data: Optional[pd.DataFrame] = None,
        priors: Optional[Dict[int, Dict[str, float]]] = None,
        prior_function: Optional[Callable[[float], float]] = "negative_log",
        similarity_function: Optional[
            Callable[
                [
                    int,
                    int,
                    pd.DataFrame,
                    int,
                    Optional[Dict[int, Dict[str, float]]],
                ],
                float,
            ]
        ] = None,
        threshold: Optional[int] = 0,
    ):

        super().__init__(
            character_matrix, missing_char, meta_data, priors, prior_function
        )

        self.threshold = threshold
        if similarity_function:
            self.similarity_function = similarity_function
        else:
            self.similarity_function = (
                dissimilarity_functions.hamming_similarity_without_missing
            )

    def perform_split(
        self,
        samples: List[str] = None,
    ) -> Tuple[List[str], List[str]]:
        """The function used by the spectral algorithm to generate a partition
        of the samples.
        First, a similarity graph is generated with samples as nodes such that
        edges between a pair of nodes is some provided function on the number
        of character/state mutations shared. Then, Fiedler's algorithm is used
        to generate a partition on this graph that minimizes a modified
        normalized cut: weight of edges across cut/ min(weight of edges within
        each side of cut). It does this efficiently by first calculating the
        2nd eigenvector of the normalized Laplacian of the similarity matrix.
        Then, it orders the nodes in a graph by the eigenvector values and finds
        an index such that partitioning the ordered nodes on that index
        minimizes the normalized cut ratio. As the optimal partition can be
        determined using the 2nd eigenvector, this greatly reduces the space of
        cuts needed to be explored.

        Args:
            samples: A list of samples, represented by their names in the
                original character matrix

        Returns:
            A tuple of lists, representing the left and right partition groups
        """
        G = graph_utilities.construct_similarity_graph(
            self.unique_character_matrix,
            self.missing_char,
            samples,
            similarity_function=self.similarity_function,
            threshold=self.threshold,
            weights=self.weights,
        )

        L = nx.normalized_laplacian_matrix(G).todense()
        diag = sp.linalg.eig(L)
        second_eigenvector = diag[1][:, 1]
        nodes_to_eigenvector = {}
        vertices = list(G.nodes())
        for i in range(len(vertices)):
            nodes_to_eigenvector[vertices[i]] = second_eigenvector[i]
        vertices.sort(key=lambda v: nodes_to_eigenvector[v])
        total_weight = 2 * sum([G[e[0]][e[1]]["weight"] for e in G.edges()])
        # If the similarity graph is empty and there are no meaningful splits,
        # return a polytomy over the remaining samples
        if total_weight == 0:
            return samples, []
        cut = set()
        numerator = 0
        denominator = 0
        prev_numerator = -1
        best_score = np.inf
        best_index = 0
        for i in range(len(vertices) - 1):
            v = vertices[i]
            cut.add(v)
            cut_edges = 0
            neighbor_weight = 0
            for w in G.neighbors(v):
                neighbor_weight += G[v][w]["weight"]
                if w in cut:
                    cut_edges += G[v][w]["weight"]
            denominator += neighbor_weight
            if i > 0:
                prev_numerator = numerator
            numerator += neighbor_weight - 2 * cut_edges
            # Avoids naively taking the first zero-weight cut. If more samples
            # can be added without changing the cut weight, those samples do not
            # share any similarity with the other side of the partition.
            if numerator != 0 and prev_numerator == 0:
                best_index = i - 1
                break
            if min(denominator, total_weight - denominator) != 0:
                if (
                    numerator / min(denominator, total_weight - denominator)
                    < best_score
                ):
                    best_score = numerator / min(
                        denominator, total_weight - denominator
                    )
                    best_index = i
            else:
                best_score = 0
                best_index = i

        improved_left_set = graph_utilities.spectral_improve_cut(
            G, vertices[: best_index + 1]
        )

        improved_right_set = []
        for i in samples:
            if i not in improved_left_set:
                improved_right_set.append(i)

        return improved_left_set, improved_right_set
