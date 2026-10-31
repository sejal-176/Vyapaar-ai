"""Configuration settings loaded from environment or .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root or current directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./vyapaar.db")
TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

