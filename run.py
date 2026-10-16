"""Local launcher: python run.py --setup (first run), python run.py (later runs)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description='Run InfraClaim Phase 6 locally')
    parser.add_argument('--setup', action='store_true', help='Install locked dependencies and build the dashboard')
    parser.add_argument('--dev', action='store_true', help='Use the Next.js development server')
    args = parser.parse_args()
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        sys.exit('Install Node.js 22 LTS or newer, then retry.')
    venv = ROOT / 'backend' / '.venv'
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    env = dict(os.environ, NEXT_TELEMETRY_DISABLED='1')
    if args.setup:
        if not python.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'requirements.lock'], cwd=ROOT / 'backend', check=True)
        subprocess.run([npm, 'ci', '--no-fund'], cwd=ROOT / 'frontend', env=env, check=True)
        subprocess.run([npm, 'run', 'build'], cwd=ROOT / 'frontend', env=env, check=True)
    if not python.exists() or not (ROOT / 'frontend/node_modules').exists():
        sys.exit('Run python run.py --setup first.')
    if not args.dev and not (ROOT / 'frontend/.next/BUILD_ID').exists():
        sys.exit('Dashboard build missing. Run python run.py --setup.')
    children = []
    try:
        backend = subprocess.Popen([str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
                                   cwd=ROOT / 'backend', env=env)
        children.append(backend)
        for _ in range(100):
            if backend.poll() is not None:
                sys.exit('Backend failed to start; see the error above.')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=0.5) as response:
                    if response.status == 200: break
            except OSError:
                time.sleep(0.1)
        else:
            sys.exit('Backend did not become ready.')
        # Catch a port collision that could briefly return another service's health.
        time.sleep(0.3)
        if backend.poll() is not None:
            sys.exit('Backend port is unavailable. Stop the other process and retry.')
        frontend = subprocess.Popen([npm, 'run', 'dev' if args.dev else 'start', '--', '--hostname', '127.0.0.1', '--port', '3000'],
                                    cwd=ROOT / 'frontend', env=env)
        children.append(frontend)
        print('\nInfraClaim dashboard: http://localhost:3000\nAPI docs: http://localhost:8000/docs\nPress Ctrl+C to stop.\n', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError('A server exited unexpectedly; see its output above.')
    except KeyboardInterrupt:
        print('\nStopping InfraClaim...')
    finally:
        for child in reversed(children):
            if child.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()


if __name__ == '__main__':
    main()
