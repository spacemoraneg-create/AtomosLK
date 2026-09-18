import os
import sys
from pathlib import Path

# Ensure src is on Python path
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from atomos.server import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
