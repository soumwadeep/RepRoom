"""Make ``reproom`` and the fixture module importable without installing first.

The engine has no runtime dependencies, so the test suite runs against the
source tree directly. Install it with ``pip install -e .`` when you want it as a
package.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(ROOT)
for path in (HERE, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)
