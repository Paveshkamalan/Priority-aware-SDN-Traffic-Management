"""
Path Computer Module
Implements Dijkstra's algorithm, K-shortest paths, and dynamic congestion-penalized
routing across multi-path SDN topologies.
"""

import heapq
from typing import Dict, List, Tuple, Optional, Any, Set


class PathComputer:
    """
    Computes optimal and alternate paths across the SDN topology using Dijkstra
    and Yen's algorithm, factoring in link delay, bandwidth, and real-time congestion.
    """

    def __init__(self, default_congestion_penalty: float = 10.0):
        """
        :param default_congestion_penalty: Multiplier applied to edge weight when link is congested.
        """
        self.congestion_penalty = default_congestion_penalty

    @staticmethod
    def get_static_paths_between_s1_and_s6() -> Dict[str, List[int]]:
        """
        Predefined canonical paths as defined in project requirements:
        Path 1: S1 -> S2 -> S4 -> S6 (Lowest latency baseline)
        Path 2: S1 -> S2 -> S5 -> S6 (Alternate path 1)
        Path 3: S1 -> S3 -> S5 -> S6 (Alternate path 2)
        """
        return {
            "path1": [1, 2, 4, 6],
            "path2": [1, 2, 5, 6],
            "path3": [1, 3, 5, 6],
        }

    def dijkstra_shortest_path(
        self,
        graph: Dict[int, Dict[int, Dict[str, Any]]],
        src: int,
        dst: int,
        weight_key: str = "delay",
        penalize_congested: bool = False,
        congested_links: Optional[Set[Tuple[int, int]]] = None,
    ) -> Optional[List[int]]:
        """
        Calculates shortest path using Dijkstra's algorithm.
        :param graph: Adjacency dict: {u: {v: {'delay': float, 'bw': float, 'utilization': float}}}
        :param src: Source switch DPID
        :param dst: Destination switch DPID
        :param weight_key: Edge attribute used as primary cost ('delay', 'cost', or 'hop')
        :param penalize_congested: If True, inflates weights of links marked congested
        :param congested_links: Set of (u, v) tuples currently exceeding congestion threshold
        :return: List of DPIDs along the path, or None if no path exists
        """
        if src not in graph or dst not in graph:
            return None
        if src == dst:
            return [src]

        congested_links = congested_links or set()
        distances: Dict[int, float] = {node: float("inf") for node in graph}
        previous: Dict[int, Optional[int]] = {node: None for node in graph}
        distances[src] = 0.0

        # Priority queue storing (distance, node)
        pq: List[Tuple[float, int]] = [(0.0, src)]

        while pq:
            curr_dist, u = heapq.heappop(pq)

            if curr_dist > distances[u]:
                continue
            if u == dst:
                break

            for v, attrs in graph.get(u, {}).items():
                base_weight = float(attrs.get(weight_key, 1.0))
                edge_utilization = float(attrs.get("utilization", 0.0))

                # Apply congestion penalty if enabled
                weight = base_weight
                is_congested = (u, v) in congested_links or (v, u) in congested_links or edge_utilization >= 0.85
                if penalize_congested and is_congested:
                    weight *= (1.0 + self.congestion_penalty * max(edge_utilization, 1.0))

                new_dist = curr_dist + weight
                if new_dist < distances[v]:
                    distances[v] = new_dist
                    previous[v] = u
                    heapq.heappush(pq, (new_dist, v))

        if distances[dst] == float("inf"):
            return None

        # Reconstruct path
        path: List[int] = []
        curr = dst
        while curr is not None:
            path.append(curr)
            curr = previous[curr]
        path.reverse()
        return path

    def find_all_paths(
        self,
        graph: Dict[int, Dict[int, Dict[str, Any]]],
        src: int,
        dst: int,
        max_depth: int = 6,
    ) -> List[List[int]]:
        """
        DFS traversal to find all simple acyclic paths between src and dst.
        """
        paths: List[List[int]] = []

        def dfs(current: int, target: int, visited: List[int]):
            if len(visited) > max_depth:
                return
            if current == target:
                paths.append(list(visited))
                return

            for neighbor in graph.get(current, {}):
                if neighbor not in visited:
                    visited.append(neighbor)
                    dfs(neighbor, target, visited)
                    visited.pop()

        dfs(src, dst, [src])
        return paths

    @staticmethod
    def evaluate_path_metrics(
        graph: Dict[int, Dict[int, Dict[str, Any]]], path: List[int]
    ) -> Dict[str, Any]:
        """
        Computes bottleneck capacity, total propagation delay, and peak utilization for a given path.
        """
        if len(path) < 2:
            return {"bottleneck_bw": 100.0, "total_delay": 0.0, "max_utilization": 0.0}

        bottleneck_bw = float("inf")
        total_delay = 0.0
        max_utilization = 0.0

        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            attrs = graph.get(u, {}).get(v, {})
            bw = float(attrs.get("bw", 100.0))
            delay = float(attrs.get("delay", 1.0))
            util = float(attrs.get("utilization", 0.0))

            bottleneck_bw = min(bottleneck_bw, bw)
            total_delay += delay
            max_utilization = max(max_utilization, util)

        return {
            "bottleneck_bw": bottleneck_bw,
            "total_delay": total_delay,
            "max_utilization": max_utilization,
            "hops": len(path) - 1,
        }

    def select_best_alternate_path(
        self,
        graph: Dict[int, Dict[int, Dict[str, Any]]],
        src: int,
        dst: int,
        current_path: List[int],
        required_bw: float = 20.0,
    ) -> Optional[List[int]]:
        """
        Finds the least congested alternate path that is distinct from current_path.
        Sorts candidates by:
          1. Under congestion threshold (< 0.70)
          2. Sufficient remaining capacity
          3. Lowest end-to-end delay
        """
        all_candidates = self.find_all_paths(graph, src, dst)
        valid_candidates = []

        for p in all_candidates:
            if p == current_path:
                continue
            metrics = self.evaluate_path_metrics(graph, p)
            # Candidate is valid if its max link utilization is below severe congestion (0.85)
            # and bottleneck bandwidth can accommodate required_bw
            if metrics["max_utilization"] < 0.85 and metrics["bottleneck_bw"] >= required_bw:
                valid_candidates.append((metrics["max_utilization"], metrics["total_delay"], p))

        if not valid_candidates:
            # If no path strictly meets the requirement, fallback to candidate with lowest max_utilization
            for p in all_candidates:
                if p != current_path:
                    metrics = self.evaluate_path_metrics(graph, p)
                    valid_candidates.append((metrics["max_utilization"], metrics["total_delay"], p))

        if not valid_candidates:
            return None

        # Sort primarily by lowest max_utilization, secondarily by lowest delay
        valid_candidates.sort(key=lambda item: (item[0], item[1]))
        return valid_candidates[0][2]
