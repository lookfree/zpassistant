import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    glm_model: str = os.getenv("GLM_MODEL", "glm-4.6")
    zhipu_base: str = "https://open.bigmodel.cn"
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    port: int = int(os.getenv("PORT", "8100"))

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
