from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

class Settings:
    jwt_secret_key = os.getenv('JWT_SECRET_KEY', '')
    if len(jwt_secret_key) < 32:
        raise RuntimeError('Set JWT_SECRET_KEY to a private value with at least 32 characters in backend/.env')
    jwt_algorithm = 'HS256'
    access_token_expire_minutes = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
    frontend_origins = [item.strip() for item in os.getenv('FRONTEND_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174').split(',') if item.strip()]
    database_url = os.getenv('DATABASE_URL', f"sqlite:///{(Path(__file__).resolve().parents[2] / 'spendwise.db').as_posix()}")
    demo_email = os.getenv('DEMO_EMAIL', '').strip().lower() or None
    demo_password = os.getenv('DEMO_PASSWORD') or None
    if bool(demo_email) != bool(demo_password):
        raise RuntimeError('Set both DEMO_EMAIL and DEMO_PASSWORD to provision a demo account')

settings = Settings()
