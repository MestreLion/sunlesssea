python -m cProfile -o myLog.profile ./sunlesssea.py -f wikipage events notfound
gprof2dot -f pstats myLog.profile -o callingGraph.dot
open callingGraph.dot
pycallgraph graphviz -- ./sunlesssea.py -f wikipage events crossroadss
open pycallgraph.png
