"""A hostile or failing worker for GA9 (not production code; never imported by velith).

Invoked by ``GeometryVerifier(worker_command=[python, -I, this_file, MODE])``; the verifier appends
``LIMITS_JSON STEP_PATH OUT_PATH REQUIREMENTS_JSON``. Each mode reproduces one abnormal-exit class
of spec F r3 §6, including the r3 text-spoofing and trailing-data cases.
"""

import json
import resource
import sys
import time

mode = sys.argv[1]
limits = json.loads(sys.argv[2])
step_path, out_path = sys.argv[3], sys.argv[4]
resource.setrlimit(resource.RLIMIT_AS, (limits["address_space_bytes"],) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_soft_s"], limits["cpu_hard_s"]))
resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"],) * 2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
VALID = {"protocol": "g0-child-1", "status": "NO_GEOMETRY", "length_units": []}

if mode == "mesh":  # a real OCCT fault: meshing a 100 m plate at 1 micrometre deflection
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    reader.ReadFile(step_path)
    reader.TransferRoots()
    BRepMesh_IncrementalMesh(reader.OneShape(), 0.001, False, 0.05, True)
    with open(out_path, "w") as handle:
        json.dump(VALID, handle)
elif mode == "cpu_loop":
    count = 0
    while True:
        count += 1
elif mode == "wall_hang":
    time.sleep(3600)
elif mode == "memory":
    try:
        block = bytearray(3 * 1024**3)
    except MemoryError:
        import os

        os._exit(3)  # the production bootstrap's EXIT_MEMORY
elif mode == "garbage":
    with open(out_path, "w") as handle:
        handle.write("not json {")
elif mode == "flood":
    with open(out_path, "w") as handle:
        while True:
            handle.write("x" * 65536)
elif mode == "stderr_flood":
    while True:
        sys.stderr.write("y" * 65536)
        sys.stderr.flush()
elif mode == "spoof_efbig_text":
    sys.stderr.write("OSError: [Errno 27] File too large\nEFBIG\n")
    sys.exit(1)
elif mode == "spoof_memory_text":
    sys.stderr.write("MemoryError\ncpu time limit exceeded\n")
    sys.exit(1)
elif mode == "trailing_after_64k":
    with open(out_path, "w") as handle:
        handle.write(json.dumps(VALID) + " " * 70000 + "GARBAGE")
elif mode == "exit0_at_limit":
    body = json.dumps(VALID)
    with open(out_path, "w") as handle:
        handle.write(body + " " * (limits["output_bytes"] - len(body)))
elif mode == "nan_token":
    with open(out_path, "w") as handle:
        handle.write('{"protocol": "g0-child-1", "status": "MEASURED", "length_units": [NaN]}')
else:
    raise SystemExit(f"unknown mode {mode}")
