import numpy as np
import networkx as nx

from cassiopeia.tools.lineage_simulator import lineage_tracing_simulator
from cassiopeia.tools.tree import Tree


def test_smoke():
    r"""
    Just tests that lineage_tracing_simulator runs
    """
    np.random.seed(1)
    T = nx.DiGraph()
    T.add_nodes_from([0, 1, 2, 3, 4, 5, 6]),
    T.add_edges_from([(0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)])
    T.nodes[0]["age"] = 1
    T.nodes[1]["age"] = 0.9
    T.nodes[2]["age"] = 0.1
    T.nodes[3]["age"] = 0
    T.nodes[4]["age"] = 0
    T.nodes[5]["age"] = 0
    T.nodes[6]["age"] = 0
    T = Tree(T)
    lineage_tracing_simulator(T, mutation_rate=1.0, num_characters=10)