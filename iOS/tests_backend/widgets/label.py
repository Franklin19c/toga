from toga.color import TRANSPARENT
from toga_iOS.libs import UILabel

from .base import SimpleProbe
from .properties import toga_alignment, toga_color, toga_font


class LabelProbe(SimpleProbe):
    native_class = UILabel

    @property
    def text(self):
        return str(self.native.text)

    @property
    def color(self):
        return toga_color(self.native.textColor)

    @property
    def background_color(self):
        if self.native.backgroundColor is None:
            return TRANSPARENT
        else:
            return toga_color(self.native.backgroundColor)

    @property
    def font(self):
        return toga_font(self.native.font)

    @property
    def alignment(self):
        return toga_alignment(self.native.textAlignment)
