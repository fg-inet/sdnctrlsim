#!/usr/bin/python
#
# Dan Levin <dlevin@net.t-labs.tu-berlin.de>
# Brandon Heller <brandonh@stanford.edu>

from math import sqrt
import networkx as nx
from random import choice, randint, random
import sys
import unittest
from workload import *


class Controller(object):
    """
    Generic controller -- does not implement control logic:
    """
    def __init__(self, sw=[], srv=[], graph=None):
        """
        sw: list of switch names governed by this controller
        srv: list of servers known by this controller
        to which requests may be dispatched sent
        graph: full graph data, with capacities and utilization
        """
        self.switches = sw
        self.servers = srv
        self.graph = graph

    def __str__(self):
        return "Controller of: " + str(self.switches)

    def get_switches(self):
        return self.switches

    def handle_request(self):
        pass


class LinkBalancerCtrl(Controller):
    """
    Control logic for link balancer: Tracks link capacities of associated
    switches, and decides how to map requests such to minimize the maximum link
    utilization over all visible links
    """
    def handle_request(self, sw=None, util=0, duration=0):
        """
        Given a request that utilizes some bandwidth for a duration, map
        that request to an available path such that max link bandwidth util is
        minimized
        @return the chosen best path as a list of consecutive link pairs
         ((c1,sw1), (sw1,sw2),...,(sw_n, srv_x))
        """
        #1 get path list: from entry sw to available servers which can respond
        paths = []
        avail_srvs = self.servers
        for server in avail_srvs:
            paths.append(nx.shortest_path(self.graph, server, sw))

        #2 choose the path which mins the max link utilization
        bestpath = None
        bestpathmetric = 1      # [0,1] lower -> better path
        for path in paths:
            linkmetrics = []
            links = zip(path[:-1], path[1:])
            # calculate available capacity for each link in path
            for link in links:
                u, v = link
                # TODO Dan: rather than exclude links, we should just give
                # controller a set of links over which to compute best path
                # exclude links not known by this controller
                if not (v in self.switches or u in self.switches):
                    continue
                used = self.graph[u][v]["used"] + util
                capacity = self.graph[u][v]["capacity"]
                linkmetric = used / capacity
                #print "LinkMetric: " + str(linkmetric)
                # If we've oversubscribed a link, go to next path
                if linkmetric > 1:
                    print >> sys.stderr, "OVERSUBSCRIBED at time " + str(i)
                    next
                else:
                    linkmetrics.append(linkmetric)

            # We define pathmetric to be the worst link metric in path
            # we can redefine this to be average or wt. avg
            pathmetric = max(linkmetrics)

            if pathmetric < bestpathmetric:
                bestpath = path
                bestpathmetric = pathmetric

        #print >> sys.stderr, "DEBUG: " + str(self
        #    ) + " choosing best path: " + str(bestpath) + str(linkmetrics)
        return bestpath


class Simulation(object):
    """
    Assign switches to controllers in the graph, and run the workload through
    the switches, controllers
    """

    def __init__(self, graph=None, ctrls=[]):
        """
        graph: topology annotated with capacity and utilization per edge
        ctrls: list of controller objects
        switches: list of switch names
        servers: list of server names
        """
        self.active_flows = {}
        self.graph = graph
        for u, v in self.graph.edges():
            # Initialize edge utilization attribute values in graph
            self.graph[u][v].setdefault("used", 0.0)

        # reqs: list req tuples, each (input, duration, util)
        self.reqs = {}
        self.sw_to_ctrl = {}

        # Extract switches and server nodes from graph
        self.switches = []
        self.servers = []
        for node, attrdict in self.graph.nodes(data=True):
            if attrdict.get('type') == 'switch':
                self.switches.append(node)
            elif attrdict.get('type') == 'server':
                self.servers.append(node)

        # Map each switch to its unique controller
        self.ctrls = ctrls
        for ctrl in self.ctrls:
            for switch in ctrl.get_switches():
                assert (not switch in self.sw_to_ctrl)
                self.sw_to_ctrl[switch] = ctrl

        self.switches = self.sw_to_ctrl.keys()

    def __str__(self):
        return "Simulation: " + str([str(c) for c in self.ctrls])

    def metric(self):
        """ Stub Calculated our performance by chosen metric """
        return None


class LinkBalancerSim(Simulation):
    """
    Simulation in which each controller balances link utilization according to
    its view of available links
    """
    def __init__(self, *args, **kwargs):
        super(LinkBalancerSim, self).__init__(*args, **kwargs)
        self.metric_fcns = [self.rmse_links, self.rmse_servers]

    def metrics(self, graph=None):
        """Return dict of metric names to values"""
        m = {}
        for fcn in self.metric_fcns():
            m[fcn.__name__] = fcn(self, graph)
        return m

    def rmse_links(self, graph=None):
        """Calculate RMSE over _all_ links"""
        # Compute ideal used fraction over all links, assuming
        # perfect split between them (regardless of discrete demands with
        # bin-packing constraints).

        if not graph:
            graph = self.graph

        # First, find total capacity and util of entire network
        used_total = 0.0
        cap_total = 0.0
        pairs = []
        for src, dst, attrs in graph.edges(data=True):
            assert 'capacity' in attrs and 'used' in attrs
            cap = attrs['capacity']
            used = attrs['used']
            pairs.append((cap, used))
            cap_total += cap
            used_total += used

#        print "DEBUG: cap total: " + str(cap_total)
#        print "DEBUG: used total: " + str(used_total)
#        print "DEBUG: pairs: " + str(pairs)
        values = []  # values to be used in metric computation
        for pair in pairs:
            capacity, used = pair
            opt_used = (used_total / cap_total) * capacity
            # Use the absolute difference
            # Not scaled by capacity.
            values.append(abs(used - opt_used) ** 2)

        return sqrt(sum(values))

    def rmse_servers(self, graph=None):
        """
        Calculate RMSE over server outgoing links:
        Compute ideal used fraction of each server's outgoing link, assuming
        perfect split between them (regardless of discrete demands with
        bin-packing constraints).
        """
        if not graph:
            graph = self.graph

        # Assuming a proportional spread of those requests, find optimal.
        cap_total = 0.0  # total capacity of all server links
        used_total = 0.0
        pairs = []  # list of (capacity, used) pairs
        for s in self.servers:
            neighbor_sw = graph.neighbors(s)
            if len(neighbor_sw) != 1:
                raise NotImplementedError("Single server links only")
            else:
                src = s
                dst = neighbor_sw[0]
                capacity = graph[src][dst]["capacity"]
                used = graph[src][dst]["used"]
                pairs.append((capacity, used))
                cap_total += capacity
                used_total += used

        values = []  # values to be used in metric computation
        for pair in pairs:
            capacity, used = pair
            opt_used = (used_total / cap_total) * capacity
            # Use the absolute difference
            # Not scaled by capacity.
            values.append(abs(used - opt_used) ** 2)

        return sqrt(sum(values))

    def allocate_resources(self, path=[], resources=0, whenfree=0):
        """
        Subtract resources for each link in path (add to self.used[src][dst])
        Detect if any link in a path is fully utilized, do not oversubscribe
        Record the resources for link to be freed at time <whenfree>
        """
        if not (path):
            return
        links = zip(path[:-1], path[1:])
        for src, dst in links:
            edge = self.graph.edge[src][dst]
            if (edge['used'] + resources > edge['capacity']):
                return

        for src, dst in links:
            edge = self.graph.edge[src][dst]
            edge['used'] += resources

        self.active_flows.setdefault(whenfree, []).append((path, resources))
        #print self.graph.edges(data=True)
#        print >> sys.stderr, "DEBUG: Allocated " + str(resources
#            ) + " to " + str(path)

    def free_resources(self, timestep):
        """
        Free (put back) resources along path for each link
        Scales with number of simultaneous links
        """
        if timestep in self.active_flows:
            for ending_flow in self.active_flows[timestep]:
                path, resources = ending_flow
                links = zip(path[:-1], path[1:])
                for src, dst in links:
                    used = self.graph.edge[src][dst]['used']
                    self.graph.edge[src][dst]['used'] -= resources
#                print >> sys.stderr, "DEBUG: Freed " + str(resources
#                    ) + " to " + str(path)
            # Allow grbg collection on the list of paths for this timestep
            self.active_flows.pop(timestep)
        else:
            pass

    def sync_ctrls(self, ctrls=[]):
        #TODO each controller should obtain the capacity state of edges
        #belonging to ctrls Probably we could represent this as a matrix of
        #which controllers consider link state from the links seen by which
        #other controllers
        pass

    def run(self, workload):
        """Run the full simulation.
        TODO: expand to continuous time with a priority queue, like discrete
        event sims do.
          Comment[andi]: We might want to stick with discrete time if we
          want to model elastic / non-constant traffic requirements (This 
          essentially means our workload changes between flow arrivals and
          expiries, so we have to calculate each step separately.)

        workload: a list of lists.
            Each top-level list element corresponds to one time step.
            Each second-level list element is a tuple of:
              (switch of arrival, utilization, duration)
        returns: dict of metric names to value list (one entry per timestep)
        """
        # dict mapping metric function names to lists;
        # each list covers the metric values for each timestep
        all_metrics = {}
        for fcn in self.metric_fcns:
            all_metrics[fcn.__name__] = []
        for i, reqs in enumerate(workload):
            # Free link resources from flows that terminate at this timestep
            self.free_resources(i)
            # Handle each request for this timestep
            for req in reqs:
                sw, size, duration = req
                assert (isinstance(duration, int) and duration > 0)
                ctrl = self.sw_to_ctrl[sw]
                path = ctrl.handle_request(sw, size, duration)
                self.allocate_resources(path, size, duration + i)

            # TODO: add back sync_probability
            #if (sync_probability):
            #    self.sync_ctrls(self.ctrls)

            # Compute metric(s) for this timestep
            for fcn in self.metric_fcns:
                all_metrics[fcn.__name__].append(fcn(self.graph))
            #print >> sys.stderr, "DEBUG: time %i, metric %s" % (i, metric_val)

        return all_metrics

###############################################################################


class TestSimulator(unittest.TestCase):
    """Unit tests for LinkBalancerSim class"""
    graph = nx.DiGraph()
    graph.add_nodes_from(['sw1', 'sw2'], type='switch')
    graph.add_nodes_from(['s1', 's2'], type='server')
    graph.add_edges_from([['s1', 'sw1', {'capacity':100, 'used':0.0}],
                          ['sw1', 'sw2', {'capacity':1000, 'used':0.0}],
                          ['sw2', 'sw1', {'capacity':1000, 'used':0.0}],
                          ['s2', 'sw2', {'capacity':100, 'used':0.0}]])

    def test_zero_metric(self):
        """Assert that RMSE metric == 0 for varying link utils"""
        graph = self.graph
        ctrls = [LinkBalancerCtrl(['sw1'], ['s1', 's2'], graph)]
        sim = LinkBalancerSim(graph, ctrls)
        for util in [0.0, 0.5, 1.0]:
            for u, v in graph.edges():
                graph[u][v]["used"] = util * graph[u][v]["capacity"]
            self.assertEqual(sim.rmse_links(graph), 0.0)

    def test_metric_unbalanced(self):
        """Assert that the metric != 0 with links of differing utils"""
        graph = self.graph
        ctrls = [LinkBalancerCtrl(['sw1'], ['s1', 's2'], graph)]
        sim = LinkBalancerSim(graph, ctrls)
        increasingvalue = 0
        for u, v in graph.edges():
            graph[u][v]["used"] = increasingvalue
            increasingvalue += 1
        #print graph.edges(data=True)
        self.assertNotEqual(sim.rmse_links(graph), 0)

    def test_metric_unbalanced_known(self):
        """Assert that the unweighted metric == 50.0 for this given case"""
        graph = nx.DiGraph()
        graph.add_nodes_from(['sw1', 'sw2'], type='switch')
        graph.add_nodes_from(['s1', 's2'], type='server')
        graph.add_edges_from([['s1', 'sw1', {'capacity':100, 'used':100.0}],
                              ['sw1', 'sw2', {'capacity':100, 'used':50.0}],
                              ['sw2', 'sw1', {'capacity':100, 'used':50.0}],
                              ['s2', 'sw2', {'capacity':100, 'used':100.0}]])
        ctrls = [LinkBalancerCtrl(['sw1'], ['s1', 's2'], graph)]
        sim = LinkBalancerSim(graph, ctrls)
        self.assertEqual(sim.rmse_links(graph), 50.0)

    def test_single_allocate_and_free(self):
        """Assert that for a path, one free negates one allocate"""
        graph = self.graph
        ctrls = [LinkBalancerCtrl(['sw1'], ['s1', 's2'], graph)]
        sim = LinkBalancerSim(graph, ctrls)
        metric_before_alloc = sim.rmse_links(graph)
        path = nx.shortest_path(graph, 's1', 'sw1')

        sim.allocate_resources(path, 40, 'some_time')
        metric_after_alloc = sim.rmse_links(graph)
        sim.free_resources('some_time')
        metric_after_free = sim.rmse_links(graph)

        self.assertEqual(metric_before_alloc, metric_after_free)
        self.assertNotEqual(metric_before_alloc, metric_after_alloc)
        self.assertEqual(len(sim.active_flows.keys()), 0)

    def test_multi_allocate_and_free(self):
        """Assert that resources allocated by flows are freed"""
        SWITCHES = ['sw1', 'sw2']
        SERVERS = ['s1', 's2']
        graph = self.graph
        max_duration = 10
        durations = range(1, max_duration)
        steps = 100
        a = nx.shortest_path(graph, choice(SERVERS), choice(SWITCHES))
        b = nx.shortest_path(graph, choice(SERVERS), choice(SWITCHES))
        paths = [a, b]
        workload = [(choice(paths), choice(durations)) for t in range(steps)]

        ctrls = [LinkBalancerCtrl(['sw1', 'sw2'], graph)]
        sim = LinkBalancerSim(graph, ctrls)

        metric_before_alloc = sim.rmse_links(graph)

        for now, item in enumerate(workload):
            path, dur = item
            sim.free_resources(now)
            sim.allocate_resources(path, 1, now + dur)

        # Free the (up to max_duration) possibly remaining live flows
        for i in range(len(workload), steps + max_duration):
            sim.free_resources(i)

        metric_after_free = sim.rmse_links(graph)

        self.assertEqual(metric_before_alloc, metric_after_free)
        self.assertEqual(len(sim.active_flows.keys()), 0)

###############################################################################

def two_switch_topo():
    graph = nx.DiGraph()
    graph.add_nodes_from(['sw1', 'sw2'], type='switch')
    graph.add_nodes_from(['s1', 's2'], type='server')
    graph.add_edges_from([['s1', 'sw1', {'capacity':100, 'used':0.0}],
                          ['sw1', 'sw2', {'capacity':1000, 'used':0.0}],
                          ['sw2', 'sw1', {'capacity':1000, 'used':0.0}],
                          ['s2', 'sw2', {'capacity':100, 'used':0.0}]])
    return graph


class TestTwoSwitch(unittest.TestCase):
    """Unit tests for two-switch simulation scenario"""

    SWITCHES = ['sw1', 'sw2']
    TIMESTEPS = 10

    def two_ctrls(self):
        """Return controller list with two different controllers."""
        graph = two_switch_topo()
        ctrls = []
        c1 = LinkBalancerCtrl(sw=['sw1'], srv=['s1', 's2'], graph=graph)
        c2 = LinkBalancerCtrl(sw=['sw2'], srv=['s1', 's2'], graph=graph)
        ctrls.append(c1)
        ctrls.append(c2)
        return ctrls

    def test_one_switch_unit_reqs(self):
        """For equal unit reqs and one switch, ensure that RMSE == 0."""

        graph2 = nx.DiGraph()
        graph2.add_nodes_from(['sw1'], type='switch')
        graph2.add_nodes_from(['s1', 's2'], type='server')
        graph2.add_edges_from([['s1', 'sw1', {'capacity':100, 'used':0.0}],
                              ['s2', 'sw1', {'capacity':100, 'used':0.0}]])

        workload = unit_workload(switches=2 * ['sw1'], size=1,
                                 duration=2, timesteps=10)

        ctrls = [LinkBalancerCtrl(sw=['sw1'], srv=['s1', 's2'], graph=graph2)]
        sim = LinkBalancerSim(graph2, ctrls)
        metrics = sim.run(workload)
        #print metrics
        for metric_val in metrics['rmse_links']:
            self.assertEqual(metric_val, 0)

    def test_two_ctrl_single_step(self):
        """A single-step simulation run should have zero RMSE."""
        workload = unit_workload(switches=['sw1' ,'sw2'], size=1,
                                 duration=2, timesteps=1)
        ctrls = self.two_ctrls()
        sim = LinkBalancerSim(two_switch_topo(), ctrls)
        metrics = sim.run(workload)
        #print metrics
        self.assertEqual(metrics['rmse_servers'][0], 0.0)

    def test_two_ctrl_unit_reqs(self):
        """For equal unit reqs and two controllers, ensure server RMSE == 0."""
        workload = unit_workload(switches=self.SWITCHES, size=1,
                                 duration=2, timesteps=self.TIMESTEPS)
        ctrls = self.two_ctrls()
        sim = LinkBalancerSim(two_switch_topo(), ctrls)
        metrics = sim.run(workload)
        #print metrics
        for metric_val in metrics['rmse_servers']:
            self.assertEqual(metric_val, 0.0)

    def test_two_ctrl_sawtooth_inphase(self):
        """For in-phase sawtooth with 2 ctrls, ensure server RMSE == 0."""
        period = 10
        for max_demand in [2, 4, 8, 10]:
            workload = dual_sawtooth_workload(switches=self.SWITCHES,
                                              period=period, offset=0,
                                              max_demand=max_demand, size=1,
                                              duration=1, timesteps=2*period)
            ctrls = self.two_ctrls()
            sim = LinkBalancerSim(two_switch_topo(), ctrls)
            metrics = sim.run(workload)
            for metric_val in metrics['rmse_servers']:
                self.assertAlmostEqual(metric_val, 0.0)

    def test_two_ctrl_sawtooth_outofphase(self):
        """For out-of-phase sawtooth with 2 ctrls, verify server RMSE.

        Server RMSE = zero when sawtooths cross, non-zero otherwise.
        """
        max_demand = 5
        for period in [4, 5, 10]:
            workload = dual_sawtooth_workload(switches=self.SWITCHES,
                                              period=period, offset=period/2.0,
                                              max_demand=max_demand, size=1,
                                              duration=1, timesteps=period)
            ctrls = self.two_ctrls()
            sim = LinkBalancerSim(two_switch_topo(), ctrls)
            metrics = sim.run(workload)
            self.assertEqual(len(metrics['rmse_servers']), period)
            for i, metric_val in enumerate(metrics['rmse_servers']):
                # When aligned with a sawtooth crossing, RMSE should be equal.
                if i % (period / 2.0) == period / 4.0:
                    self.assertAlmostEqual(metric_val, 0.0)
                else:
                    self.assertTrue(metric_val > 0.0)


if __name__ == '__main__':
    unittest.main()