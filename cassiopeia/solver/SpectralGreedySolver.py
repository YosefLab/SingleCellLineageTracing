"""
This file stores a subclass of GreedySolver, the SpectralGreedySolver. The
inference procedure here extends the "vanilla" Cassiopeia-Greedy, originally
proposed in Jones et al, Genome Biology (2020). After each putative split of
the samples generated by Cassiopeia-Greedy, the hill-climbing prodecure from
the SpectralSolver is applied to the partition to optimize the it for the 
modified normalized cut criterion on a similarity graph built from the 
observed mutations in the samples.
"""
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple, Union

from cassiopeia.solver import GreedySolver
from cassiopeia.solver import graph_utilities
from cassiopeia.solver.missing_data_methods import assign_missing_average


class SpectralGreedySolver(GreedySolver.GreedySolver):
    """
    TODO: Implement FuzzySolver
    The SpectralGreedySolver implements a top-down algorithm that recursively
    splits the sample set based on the presence, or absence, of the most
    frequent mutation. Additionally, the hill-climbing procedure from the
    SpectralSolver is used to further optimize each split for the normalized
    cut on the similarity graph on the samples. This effectively moves samples
    across the parition so that both sides of partition have higher internal
    similarity in their mutations. Multiple missing data imputation methods are
    included for handling the case when a sample has a missing value on the
    character being split, where presence or absence of the character is
    ambiguous. The user can also specify a missing data method.

    Args:
        character_matrix: A character matrix of observed character states for
            all samples
        missing_char: The character representing missing values
        missing_data_classifier: Takes either a string specifying one of the
            included missing data imputation methods, or a function
            implementing the user-specified missing data method. The default is
            the "average" method.
        meta_data: Any meta data associated with the samples
        priors: Prior probabilities of observing a transition from 0 to any
            character state
        weights: A set of optional weights for calculating similarity for edges
            in the graph

    Attributes:
        character_matrix: The character matrix describing the samples
        missing_char: The character representing missing values
        meta_data: Data table storing meta data for each sample
        priors: Prior probabilities of character state transitions
        tree: The tree built by `self.solve()`. None if `solve` has not been
            called yet
        prune_cm: A character matrix with duplicate rows filtered out
        weights: A set of optional weights for calculating similarity for edges
            in the graph
    """

    def __init__(
        self,
        character_matrix: pd.DataFrame,
        missing_char: str,
        missing_data_classifier: Union[Callable, str] = "average",
        meta_data: Optional[pd.DataFrame] = None,
        priors: Optional[Dict] = None,
        threshold: Optional[int] = 0,
        weights: Optional[Dict] = None,
    ):

        super().__init__(character_matrix, missing_char, meta_data, priors)

        self.missing_data_classifier = missing_data_classifier
        self.threshold = threshold
        self.weights = weights

    def perform_split(
        self,
        mutation_frequencies: Dict[int, Dict[str, int]],
        samples: List[int],
    ) -> Tuple[List[int], List[int]]:
        """Performs a partition using both Greedy and Spectral criteria.

        First, uses the most frequent (character, state) pair to split the
        list of samples. In doing so, the procedure makes use of the missing
        data classifier. Then, it optimizes this partition for the normalized
        cut on a similarity graph constructed on the samples using a hill-
        climbing method.

        Args:
            mutation_frequencies: A dictionary containing the frequencies of
                each character/state pair that appear in the character matrix
                restricted to the sample set
            samples: A list of samples to partition

        Returns:
            A tuple of lists, representing the left and right partitions
        """
        freq = 0
        char = 0
        state = ""
        for i in mutation_frequencies:
            for j in mutation_frequencies[i]:
                if j != self.missing_char and j != "0":
                    # Avoid splitting on mutations shared by all samples
                    if (
                        mutation_frequencies[i][j] > freq
                        and mutation_frequencies[i][j]
                        < len(samples)
                        - mutation_frequencies[i][self.missing_char]
                    ):
                        char, state = i, j
                        freq = mutation_frequencies[i][j]

        if state == "":
            return samples, []

        left_set = []
        right_set = []
        missing = []

        for i in samples:
            if self.prune_cm.iloc[i, char] == state:
                left_set.append(i)
            elif self.prune_cm.iloc[i, char] == self.missing_char:
                missing.append(i)
            else:
                right_set.append(i)

        if self.missing_data_classifier == "average":
            left_set, right_set = assign_missing_average(
                self.prune_cm, self.missing_char, left_set, right_set, missing
            )

        G = graph_utilities.construct_similarity_graph(
            self.prune_cm,
            mutation_frequencies,
            self.missing_char,
            samples,
            threshold=self.threshold,
            w=self.weights,
        )

        improved_left_set = graph_utilities.spectral_improve_cut(G, left_set)

        improved_right_set = set(samples) - set(improved_left_set)

        return improved_left_set, list(improved_right_set)
