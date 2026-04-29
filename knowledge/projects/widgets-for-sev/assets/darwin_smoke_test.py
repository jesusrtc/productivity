# Darwin smoke test for PrevalenceAtResponseWidget.
#
# Run from this project directory:
#   cd knowledge/projects/widgets-for-sev
#   lab darwin start              # if not already up
#   lab darwin run --file assets/darwin_smoke_test.py
#
# This executes on the Darwin pod with access to u_tdssample.* tables and the
# linkedin.account.measurements library. The cell output (chart + summary)
# lands in notebooks/widgets-for-sev.ipynb which the UI renders live.

# Install the lipy-davi branch on the pod (matches worktree state).
# Skip if the pod already has it from a prior run.
import subprocess
subprocess.run(
    ["pip", "install", "-e",
     "/home/jcortes/src/lipy-davi/lipy-davi",
     "--quiet"],
    check=False,
)

import sys
sys.path.insert(
    0, "/home/jcortes/src/lipy-davi/lipy-davi/lipy-davi/src"
)
sys.path.insert(
    0, "/home/jcortes/src/lipy-davi/lipy-davi/jupyter/extensions"
)

from linkedin.davi.widgets import PrevalenceAtResponseWidget  # noqa: E402

# T7D flavor — matches the ATO self-reports chart in the V1 framework image.
widget = PrevalenceAtResponseWidget(
    harm_type="RECEIVED_MESSAGE",
    rolling_days=7,
    lookback_days=120,
)
widget.run()

print("Latest T7D +/- WoW%:", widget.latest)
print("Daily frame tail:")
print(widget.data.tail(10))
