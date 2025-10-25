import json, subprocess, pathlib, importlib.util, os

BASE = pathlib.Path(__file__).parent
MODULECACHE = BASE / ".modulecache"
MODULECACHE.mkdir(exist_ok=True)
ENV = os.environ.copy()
ENV.setdefault("SWIFT_MODULECACHE_PATH", str(MODULECACHE))
SWIFTC = ["swiftc", "-module-cache-path", str(MODULECACHE), "oracle.swift", "-o", ".oracle"]

# run swift oracle
subprocess.run(SWIFTC, cwd=BASE, check=True, env=ENV)
got = subprocess.run(["./.oracle"], cwd=BASE, check=True, capture_output=True, text=True, env=ENV).stdout
oracle = json.loads(got)

# import web function
p = BASE/"app.py"
spec = importlib.util.spec_from_file_location("app", str(p))
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

def approx(a,b,eps=1e-9): return abs(a-b) <= eps

def test_probability_matches_oracle():
    for k,v in oracle.items():
        x = float(k)
        assert approx(app.get_probability(x), v)
