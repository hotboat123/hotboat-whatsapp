import subprocess, sys
cmds = [
    ["git","checkout","booking-platform"],
    ["git","add","."],
    ["git","commit","-m","feat: HotBoat Booking Platform - web reservas con MercadoPago"],
    ["git","push","-u","origin","booking-platform"],
]
for cmd in cmds:
    r = subprocess.run(cmd, cwd="C:/Users/cuent/Desktop/hotboat-whatsapp", capture_output=True, text=True)
    print("CMD:", " ".join(cmd))
    print("OUT:", r.stdout[:300])
    print("ERR:", r.stderr[:300])
    print("CODE:", r.returncode)
    if r.returncode not in (0,1):
        sys.exit(r.returncode)
print("DONE")
