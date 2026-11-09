"""Use an ephemeral signing key when tests run without local configuration."""
import os
import secrets

os.environ.setdefault('JWT_SECRET_KEY', secrets.token_urlsafe(48))
