from toga_iOS.libs import (
    UIApplication,
    UINavigationController,
    UIScreen,
    UIViewController,
    UIWindow,
)


class iOSViewport:
    def __init__(self, widget):
        self.widget = widget
        # iOS renders everything at 96dpi.
        self.dpi = 96
        self.baseline_dpi = self.dpi

        self.kb_height = 0.0

    @property
    def statusbar_height(self):
        # This is the height of the status bar frame.
        # If the status bar isn't visible (e.g., on iPhones in landscape orientation)
        # the size will be 0.
        return UIApplication.sharedApplication.statusBarFrame.size.height

    @property
    def navbar_height(self):
        try:
            return (
                self.widget.controller.navigationController.navigationBar.frame.size.height
            )
        except AttributeError:
            return 0

    @property
    def top_offset(self):
        return self.statusbar_height + self.navbar_height

    @property
    def bottom_offset(self):
        return self.kb_height

    @property
    def width(self):
        return self.widget.native.bounds.size.width

    @property
    def height(self):
        # Remove the height of the keyboard and the titlebar
        # from the available viewport height
        return (
            self.widget.native.bounds.size.height - self.bottom_offset - self.top_offset
        )

    def make_dirty(self, widget=None):
        # TODO: This won't be required once we complete the refactor
        # making container a separate impl concept.
        pass


class Window:
    def __init__(self, interface, title, position, size):
        self.interface = interface
        self.interface._impl = self

        self.native = UIWindow.alloc().initWithFrame(UIScreen.mainScreen.bounds)

        # The window has a UINavigationController to provide the navigation bar,
        # and provide a stack of navigable content; this is initialized with a
        # UIViewController to contain the actual content
        self.controller = UIViewController.alloc().init()

        self.navigation_controller = (
            UINavigationController.alloc().initWithRootViewController(self.controller)
        )
        self.native.rootViewController = self.navigation_controller

        self.set_title(title)

    def clear_content(self):
        if self.interface.content:
            for child in self.interface.content.children:
                child._impl.container = None

    def set_content(self, widget):
        widget.viewport = iOSViewport(self)

        # Add all children to the content widget.
        for child in widget.interface.children:
            child._impl.container = widget

        # Set the controller's view to be the new content widget
        self.controller.view = widget.native

        # The main window content needs to use the autoresizing mask so
        # that it fills all the available space in the view.
        widget.native.translatesAutoresizingMaskIntoConstraints = True

    def get_title(self):
        return str(self.navigation_controller.title)

    def set_title(self, title):
        # The title is set on the controller of the topmost content
        self.navigation_controller.topViewController.title = title

    def get_position(self):
        return (0, 0)

    def set_position(self, position):
        # Does nothing on mobile
        pass

    def get_size(self):
        return (
            UIScreen.mainScreen.bounds.size.width,
            UIScreen.mainScreen.bounds.size.height,
        )

    def set_size(self, size):
        # Does nothing on mobile
        pass

    def set_app(self, app):
        pass

    def create_toolbar(self):
        pass

    def show(self):
        self.native.makeKeyAndVisible()

        # Refresh with the actual viewport to do the proper rendering.
        self.interface.content.refresh()

    def hide(self):
        # A no-op, as the window cannot be hidden.
        pass

    def get_visible(self):
        # The window is alays visible
        return True

    def close(self):
        pass
