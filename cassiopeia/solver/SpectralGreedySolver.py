"""
This file stores a subclass of GreedySolver, the SpectralGreedySolver. The
inference procedure here extends the "vanilla" Cassiopeia-Greedy, originally
proposed in Jones et al, Genome Biology (2020). After each putative split of
the samples generated by Cassiopeia-Greedy, the hill-climbing procedure from
the SpectralSolver is applied to the partition to optimize the it for the 
modified normalized cut criterion on a similarity graph built from the 
observed mutations in the samples.
"""
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from cassiopeia.solver import (
    dissimilarity_functions,
    graph_utilities,
    GreedySolver,
    missing_data_methods,
    solver_utilities,
)


class SpectralGreedySolver(GreedySolver.GreedySolver):
    """
    TODO: Implement FuzzySolver
    TODO: Experiment to find the best default similarity function
    The SpectralGreedySolver implements a top-down algorithm that recursively
    splits the sample set based on the presence, or absence, of the most
    frequent mutation. Additionally, the hill-climbing procedure from the
    SpectralSolver is used to further optimize each split for the normalized
    cut on the similarity graph on the samples. This effectively moves samples
    across the partition so that both sides of partition have higher internal
    similarity in their mutations. Multiple missing data imputation methods are
    included for handling the case when a sample has a missing value on the
    character being split, where presence or absence of the character is
    ambiguous. The user can also specify a missing data method.

    Args:
        missing_data_classifier: Takes either a string specifying one of the
            included missing data imputation methods, or a function
            implementing the user-specified missing data method. The default is
            the "average" method.
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations. The default
            is "hamming_distance_without_missing"
        threshold: A minimum similarity threshold to include an edge in the
            similarity graph
        prior_transformation: A function defining a transformation on the priors
            in forming weights to scale frequencies and the contribution of
            each mutation in the similarity graph. One of the following:
                "negative_log": Transforms each probability by the negative
                    log (default)
                "inverse": Transforms each probability p by taking 1/p
                "square_root_inverse": Transforms each probability by the
                    the square root of 1/p

    Attributes:
        similarity_function: A function that calculates a similarity score
            between two given samples and their observed mutations
        weights: Weights on character/mutation pairs, derived from priors
        threshold: A minimum similarity threshold
        prior_transformation: Function to use when transforming priors into
            weights.
    """

    def __init__(
        self,
        missing_data_classifier: Callable = missing_data_methods.assign_missing_average,
        similarity_function: Optional[
            Callable[
                [
                    List[int],
                    List[int],
                    int,
                    Optional[Dict[int, Dict[int, float]]],
                ],
                float,
            ]
        ] = dissimilarity_functions.hamming_similarity_without_missing,
        threshold: Optional[int] = 0,
        prior_transformation: str = "negative_log",
    ):

        super().__init__(prior_transformation)

        self.missing_data_classifier = missing_data_classifier

        self.threshold = threshold
        self.similarity_function = similarity_function

    def perform_split(
        self,
        character_matrix: pd.DataFrame,
        samples: List[int],
        weights: Optional[Dict[int, Dict[int, float]]] = None,
        missing_state_indicator: int = -1,
    ) -> Tuple[List[str], List[str]]:
        """Performs a partition using both Greedy and Spectral criteria.

        First, uses the most frequent (character, state) pair to split the
        list of samples. In doing so, the procedure makes use of the missing
        data classifier. Then, it optimizes this partition for the normalized
        cut on a similarity graph constructed on the samples using a hill-
        climbing method.

        Args:
            character_matrix: Character matrix
            samples: A list of samples to partition
            weights: Weighting of each (character, state) pair. Typically a
                transformation of the priors.
            missing_state_indicator: Character representing missing data.

        Returns:
            A tuple of lists, representing the left and right partition groups
        """
        sample_indices = solver_utilities.convert_sample_names_to_indices(
            character_matrix.index, samples
        )
        mutation_frequencies = self.compute_mutation_frequencies(
            samples, character_matrix, missing_state_indicator
        )

        best_frequency = 0
        chosen_character = 0
        chosen_state = 0
        for character in mutation_frequencies:
            for state in mutation_frequencies[character]:
                if state != missing_state_indicator and state != 0:
                    # Avoid splitting on mutations shared by all samples
                    if (
                        mutation_frequencies[character][state]
                        < len(samples)
                        - mutation_frequencies[character][
                            missing_state_indicator
                        ]
                    ):
                        if weights:
                            if (
                                mutation_frequencies[character][state]
                                * weights[character][state]
                                > best_frequency
                            ):
                                chosen_character, chosen_state = (
                                    character,
                                    state,
                                )
                                best_frequency = (
                                    mutation_frequencies[character][state]
                                    * weights[character][state]
                                )
                        else:
                            if (
                                mutation_frequencies[character][state]
                                > best_frequency
                            ):
                                chosen_character, chosen_state = (
                                    character,
                                    state,
                                )
                                best_frequency = mutation_frequencies[
                                    character
                                ][state]

        if chosen_state == 0:
            return samples, []

        left_set = []
        right_set = []
        missing = []

        unique_character_array = character_matrix.to_numpy()
        sample_names = list(character_matrix.index)

        for i in sample_indices:
            if unique_character_array[i, chosen_character] == chosen_state:
                left_set.append(sample_names[i])
            elif (
                unique_character_array[i, chosen_character]
                == missing_state_indicator
            ):
                missing.append(sample_names[i])
            else:
                right_set.append(sample_names[i])

        left_set, right_set = self.missing_data_classifier(
            character_matrix,
            missing_state_indicator,
            left_set,
            right_set,
            missing,
            weights=weights,
        )

        G = graph_utilities.construct_similarity_graph(
            character_matrix,
            missing_state_indicator,
            samples,
            similarity_function=self.similarity_function,
            threshold=self.threshold,
            weights=weights,
        )

        improved_left_set = graph_utilities.spectral_improve_cut(G, left_set)

        improved_right_set = []
        for i in samples:
            if i not in improved_left_set:
                improved_right_set.append(i)

        return improved_left_set, improved_right_set
