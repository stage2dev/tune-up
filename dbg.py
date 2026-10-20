import json, os, subprocess, sys, tempfile
d = tempfile.mkdtemp()
env = dict(os.environ, TUNEUP_TESTE="1", CLAUDE_PLUGIN_DATA=os.path.join(d, "dados"), HOME=d, USERPROFILE=d, TUNEUP_FAKE_BRANCH="feat/x", TUNEUP_FAKE_GH_MERGED="")
for cmd in ["git stash -u", "sh -c 'gh pr merge 3'"]:
    inp = json.dumps({"session_id": "s1", "prompt_id": "p1", "cwd": d, "tool_name": "Bash", "tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, "scripts/guarda.py", "bash"], input=inp, capture_output=True, text=True, env=env)
    print(cmd, r.returncode, repr(r.stdout), repr(r.stderr))
for root, _, fs in os.walk(d):
    for f in fs:
        if f.endswith(".log"):
            print(f, open(os.path.join(root, f)).read())
