"""Unit/regression tests are offline, regardless of the user's local live configuration."""
import os
os.environ['INFRACLAIM_LLM_MODE'] = 'mock'
os.environ['NEBIUS_API_KEY'] = ''
