"""pytest 根配置：将项目根目录加入 sys.path，使 `import src` 可用。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
