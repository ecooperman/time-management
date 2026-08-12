import os

HOST = "127.0.0.1"
PORT = 8010

# Resume generation feature (see app/resume_gen.py): calls the resume app's
# admin API to fetch resume.yaml and render tailored PDFs/DOCX, and calls
# the Anthropic API to do the tailoring itself. All three are secrets/config
# that only make sense as environment variables - set on the droplet's
# systemd unit (never committed), and exported in your shell for local dev.
# The feature degrades to a clear error (not a crash) if these are unset;
# see resume_gen.py.
RESUME_ADMIN_URL = os.environ.get("RESUME_ADMIN_URL", "http://127.0.0.1:8041")
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
