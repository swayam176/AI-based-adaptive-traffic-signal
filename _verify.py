"""
Headless verification script for simulation.py
Run: python _verify.py
"""
import os, sys, csv, time, copy
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pygame
pygame.init()

def approx_eq(a, b, tol=0.001):
    return abs(a - b) < tol

with open('simulation.py', encoding='utf-8') as f:
    src = f.read()

src2 = src.replace(
    'if __name__ == "__main__":\n    main()', ''
)

ns = {}
try:
    exec(compile(src2, 'simulation.py', 'exec'), ns)
    print('Module-level execution: OK')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

required = [
    '_generate_scenario', 'start_run', '_reset_vehicles', '_reset_stats',
    'export_summary_csv', 'export_timeseries_csv', 'ai_controller',
    'fixed_controller', '_scenario_generator_thread', '_free_generator_thread',
    '_finish_run', '_sample_queues', 'pct_improve',
]
for fn in required:
    assert fn in ns, f'MISSING: {fn}'
    print(f'  OK: {fn}')

ns['_generate_scenario']()
events = ns['_scenario_events']
print(f'\nScenario events generated: {len(events)}')
assert len(events) > 50
ns['_generate_scenario']()
events2 = ns['_scenario_events']
assert events == events2
print('  OK: Deterministic scenario')

ns['_reset_stats']()
s = ns['stats']
assert s['generated'] == 0 and s['served'] == 0 and s['max_wait'] == 0.0
print('  OK: Stats reset')

pi = ns['pct_improve']
assert approx_eq(pi(100, 80), 20.0)
assert approx_eq(pi(100, 120), -20.0)
assert pi(0, 10) is None
assert pi(None, 10) is None
print('  OK: pct_improve')

assert ns['export_summary_csv']() is None
print('  OK: CSV export None when no data')

mock_fixed = {
    'mode': 'FIXED', 'generated': 100, 'served': 80,
    'total_wait': 800.0, 'max_wait': 45.0, 'wait_samples': 80,
    'queue_sum': 240.0, 'queue_obs': 120, 'max_queue': 12,
    'dir_generated': [25,25,25,25], 'dir_served': [20,20,20,20],
    'dir_wait_sum': [200.0,200.0,200.0,200.0], 'dir_wait_cnt': [20,20,20,20],
    'dir_queue': [3,3,3,3], 'sim_elapsed': 120.0, 'sim_start': time.time()-120,
    'timeseries': [{'time':0,'mode':'FIXED','queue_r':0,'queue_d':0,'queue_l':0,
                    'queue_u':0,'total_q':0,'green_dir':0,'generated':0,'served':0}]
}
mock_ai = copy.deepcopy(mock_fixed)
mock_ai.update({'mode': 'AI', 'total_wait': 600.0, 'served': 95})
ns['completed_fixed'] = mock_fixed
ns['completed_ai']    = mock_ai

f1 = ns['export_summary_csv']()
assert f1 and os.path.exists(f1)
f2 = ns['export_timeseries_csv']()
assert f2 and os.path.exists(f2)
print(f'  OK: CSV summary -> {f1}')
print(f'  OK: CSV timeseries -> {f2}')

with open(f1) as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 2 and rows[0]['mode'] == 'FIXED' and rows[1]['mode'] == 'AI'
print('  OK: CSV content verified')

assert approx_eq(ns['_avg_wait'](mock_fixed), 800.0/80)
assert approx_eq(ns['_avg_queue'](mock_fixed), 240.0/120)
assert approx_eq(ns['_throughput'](mock_fixed), 80/(120/60))
print('  OK: Metric calculations correct')

print('\nALL VERIFICATION CHECKS PASSED')
