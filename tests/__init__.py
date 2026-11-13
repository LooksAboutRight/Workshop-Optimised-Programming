"""Tests of WOP. The new-project tools are the plain stubs here (the expected numbers of the tests were made with them)."""

import os

# The real-window tests run Qt without a screen and fonts: it warns about that on every run. The warnings are not about WOP.
os.environ.setdefault("QT_LOGGING_RULES", "default.warning=false;qt.qpa.*=false")

from wop.ui.model import helpers  # noqa: E402

helpers.NEW_PROJECT_USES_STUB_TOOLS = True

from wop.ui import app_constants  # noqa: E402

app_constants.DISPLAY_UNITS = "mm"  # the tests work in millimetres whatever the user chose in File > Preferences
