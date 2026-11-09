import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["HYPE_DATA_DIR"] = tempfile.mkdtemp(prefix="hypetrike-test-")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hypetrike"))
