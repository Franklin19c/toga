from android.widget import ProgressBar

from .base import SimpleProbe


class ProgressBarProbe(SimpleProbe):
    native_class = ProgressBar

    @property
    def is_determinate(self):
        return self.native.getMax() != 0

    @property
    def is_animating_indeterminate(self):
        # The Android "isIndeterminate" attribute encompasses animation status
        return self.native.isIndeterminate()
