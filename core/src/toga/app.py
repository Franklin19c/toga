from __future__ import annotations

import importlib.metadata
import signal
import sys
import warnings
import webbrowser
from collections.abc import Iterator, MutableSet
from email.message import Message
from typing import Any, Iterable, Protocol
from warnings import warn

from toga.command import CommandSet
from toga.documents import Document
from toga.handlers import wrapped_handler
from toga.icons import Icon
from toga.paths import Paths
from toga.platform import get_platform_factory
from toga.widgets.base import Widget, WidgetRegistry
from toga.window import Window

# Make sure deprecation warnings are shown by default
warnings.filterwarnings("default", category=DeprecationWarning)


class AppStartupMethod(Protocol):
    def __call__(self, app: App, **kwargs: Any) -> Widget:
        """The startup method of the app.

        Called during app startup to set the initial main window content.

        .. note::
            ``**kwargs`` ensures compatibility with additional arguments
            introduced in future versions.

        :param app: The app instance that is starting.
        :returns: The widget to use as the main window content.
        """
        ...


class OnExitHandler(Protocol):
    def __call__(self, app: App, **kwargs: Any) -> bool:
        """A handler to invoke when the app is about to exit.

        The return value of this callback controls whether the app is allowed to exit.
        This can be used to prevent the app exiting with unsaved changes, etc.

        .. note::
            ``**kwargs`` ensures compatibility with additional arguments
            introduced in future versions.

        :param app: The app instance that is exiting.
        :returns: ``True`` if the app is allowed to exit; ``False`` if the app is not
            allowed to exit.
        """
        ...


class BackgroundTask(Protocol):
    def __call__(self, app: App, **kwargs: Any) -> None:
        """Code that should be executed as a background task.

        .. note::
            ``**kwargs`` ensures compatibility with additional arguments
            introduced in future versions.

        :param app: The app that is handling the background task.
        """
        ...


class WindowSet(MutableSet):
    def __init__(self, app: App):
        """A collection of windows managed by an app.

        A window is automatically added to the app when it is created, and removed when
        it is closed. Adding a window to an App's window set automatically sets the
        :attr:`~toga.Window.app` property of the Window.
        """
        self.app = app
        self.elements = set()

    def add(self, window: Window) -> None:
        if not isinstance(window, Window):
            raise TypeError("Can only add objects of type toga.Window")
        # Silently not add if duplicate
        if window not in self.elements:
            self.elements.add(window)
            window.app = self.app

    def discard(self, window: Window) -> None:
        if not isinstance(window, Window):
            raise TypeError("Can only discard objects of type toga.Window")
        if window not in self.elements:
            raise ValueError(f"{window!r} is not part of this app")
        self.elements.remove(window)

    def __iter__(self) -> Iterator:
        return iter(self.elements)

    def __contains__(self, value: Window) -> bool:
        return value in self.elements

    def __len__(self) -> int:
        return len(self.elements)


class MainWindow(Window):
    _WINDOW_CLASS = "MainWindow"

    def __init__(
        self,
        id: str | None = None,
        title: str | None = None,
        position: tuple[int, int] = (100, 100),
        size: tuple[int, int] = (640, 480),
        resizable: bool = True,
        minimizable: bool = True,
    ):
        """Create a new main window.

        :param id: A unique identifier for the window. If not provided, one will be
            automatically generated.
        :param title: Title for the window. Defaults to the formal name of the app.
        :param position: Position of the window, as a tuple of ``(x, y)`` coordinates,
            in :ref:`CSS pixels <css-units>`.
        :param size: Size of the window, as a tuple of ``(width, height)``, in :ref:`CSS
            pixels <css-units>`.
        :param resizable: Can the window be resized by the user?
        :param minimizable: Can the window be minimized by the user?
        """
        super().__init__(
            id=id,
            title=title,
            position=position,
            size=size,
            resizable=resizable,
            closable=True,
            minimizable=minimizable,
        )

    @property
    def _default_title(self) -> str:
        return App.app.formal_name

    @property
    def on_close(self) -> None:
        """The handler to invoke before the window is closed in response to a user
        action.

        Always returns ``None``. Main windows should use :meth:`toga.App.on_exit`,
        rather than ``on_close``.

        :raises ValueError: if an attempt is made to set the ``on_close`` handler.
        """
        return None

    @on_close.setter
    def on_close(self, handler: Any):
        if handler:
            raise ValueError(
                "Cannot set on_close handler for the main window. "
                "Use the app on_exit handler instead."
            )


class DocumentMainWindow(Window):
    def __init__(
        self,
        doc: Document,
        id: str | None = None,
        title: str | None = None,
        position: tuple[int, int] = (100, 100),
        size: tuple[int, int] = (640, 480),
        resizable: bool = True,
        minimizable: bool = True,
    ):
        """Create a new document Main Window.

        This installs a default on_close handler that honors platform-specific document
        closing behavior. If you want to control whether a document is allowed to close
        (e.g., due to having unsaved change), override
        :meth:`toga.Document.can_close()`, rather than implementing an on_close handler.

        :param document: The document being managed by this window
        :param id: The ID of the window.
        :param title: Title for the window. Defaults to the formal name of the app.
        :param position: Position of the window, as a tuple of ``(x, y)`` coordinates.
        :param size: Size of the window, as a tuple of ``(width, height)``, in pixels.
        :param resizable: Can the window be manually resized by the user?
        :param minimizable: Can the window be minimized by the user?
        """
        self.doc = doc
        super().__init__(
            id=id,
            title=title,
            position=position,
            size=size,
            resizable=resizable,
            closable=True,
            minimizable=minimizable,
            on_close=doc.handle_close,
        )

    @property
    def _default_title(self) -> str:
        return self.doc.path.name


class App:
    app = None

    def __init__(
        self,
        formal_name: str | None = None,
        app_id: str | None = None,
        distribution_name: str | None = None,
        *,
        icon: Icon | str | None = None,
        author: str | None = None,
        version: str | None = None,
        home_page: str | None = None,
        description: str | None = None,
        startup: AppStartupMethod | None = None,
        on_exit: OnExitHandler | None = None,
        app_name: str | None = None,  # DEPRECATED
        id=None,  # DEPRECATED
        windows=None,  # DEPRECATED
    ):
        """Create a new App instance.

        Once the app has been created, you should invoke the
        :meth:`~toga.App.main_loop()` method, which will start the event loop of your
        App.

        :param formal_name: The human-readable name of the app. If not provided,
            the metadata key ``Formal-Name`` must be present.
        :param app_id: The unique application identifier. This will usually be a
            reversed domain name, e.g. ``org.beeware.myapp``. If not provided, the
            metadata key ``App-ID`` must be present.
        :param distribution_name: The name of the distribution used to load metadata with
            :any:`importlib.metadata`. If not provided, the following will be tried in
            order:

            #. If the ``__main__`` module is contained in a package, that package's name
               will be used.
            #. If the ``app_id`` argument was provided, its last segment will be used.
               For example, an ``app_id`` of ``com.example.my-app`` would yield a
               distribution name of ``my-app``.
            #. As a last resort, the name ``toga``.
        :param icon: The :any:`Icon` for the app. If not provided, Toga will attempt to
            load an icon from ``resources/distribution_name``, where
            ``distribution_name`` is defined above. If no resource matching this name
            can be found, a warning will be printed, and the app will fall back to a
            default icon.
        :param author: The person or organization to be credited as the author of the
            app. If not provided, the metadata key ``Author`` will be used.
        :param version: The version number of the app.  If not provided, the metadata
            key ``Version`` will be used.
        :param home_page: The URL of a web page for the app. Used in auto-generated help
            menu items. If not provided, the metadata key ``Home-page`` will be used.
        :param description: A brief (one line) description of the app. If not provided,
            the metadata key ``Summary`` will be used.
        :param startup: A callable to run before starting the app.
        :param on_exit: The handler to invoke before the application exits.
        :param app_name: **DEPRECATED** –  Renamed to ``distribution_name``.
        :param id: **DEPRECATED** - This argument will be ignored. If you need a
            machine-friendly identifier, use ``app_id``.
        :param windows: **DEPRECATED** – Windows are now automatically added to the
            current app. Passing this argument will cause an exception.
        """
        ######################################################################
        # 2023-10: Backwards compatibility
        ######################################################################
        if app_name is not None:
            if distribution_name is not None:
                raise ValueError("Cannot specify both app_name and distribution_name")
            else:
                warn(
                    "App.app_name has been renamed to distribution_name",
                    DeprecationWarning,
                )
                distribution_name = app_name

        if id is not None:
            warn(
                "App.id is deprecated and will be ignored. Use app_id instead",
                DeprecationWarning,
            )

        if windows is not None:
            raise ValueError(
                "The `windows` constructor argument of toga.App has been removed. "
                "Windows are now automatically added to the current app."
            )
        ######################################################################
        # End backwards compatibility
        ######################################################################

        # Initialize empty widgets registry
        self._widgets = WidgetRegistry()

        # Keep an accessible copy of the app singleton instance
        App.app = self

        # We need a distribution name to load app metadata.
        if distribution_name is None:
            # If the code is contained in appname.py, and you start the app using
            # `python -m appname`, then __main__.__package__ will be an empty string.
            #
            # If the code is contained in appname.py, and you start the app using
            # `python appname.py`, then __main__.__package__ will be None.
            #
            # If the code is contained in appname/__main__.py, and you start the app
            # using `python -m appname`, then __main__.__package__ will be "appname".
            try:
                main_module_pkg = sys.modules["__main__"].__package__
                if main_module_pkg:
                    distribution_name = main_module_pkg
            except KeyError:
                # If there's no __main__ module, we're probably in a test.
                pass

        # Try deconstructing the distribution name from the app ID
        if (distribution_name is None) and app_id:
            distribution_name = app_id.split(".")[-1]

        # If we still don't have a distribution name, fall back to ``toga`` as a
        # last resort.
        if distribution_name is None:
            distribution_name = "toga"

        # Try to load the app metadata with our best guess of the distribution name.
        self._distribution_name = distribution_name
        try:
            self.metadata = importlib.metadata.metadata(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            self.metadata = Message()

        # If a formal name has been provided, use it; otherwise, look to
        # the metadata. However, a formal name *must* be provided.
        if formal_name:
            self._formal_name = formal_name
        else:
            self._formal_name = self.metadata.get("Formal-Name")
        if self._formal_name is None:
            raise RuntimeError("Toga application must have a formal name")

        # If an app_id has been provided, use it; otherwise, look to
        # the metadata. However, an app_id *must* be provided
        if app_id:
            self._app_id = app_id
        else:
            self._app_id = self.metadata.get("App-ID", None)
        if self._app_id is None:
            raise RuntimeError("Toga application must have an app ID")

        # Other metadata may be passed to the constructor, or loaded with importlib.
        if author:
            self._author = author
        else:
            self._author = self.metadata.get("Author", None)

        if version:
            self._version = version
        else:
            self._version = self.metadata.get("Version", None)

        if home_page:
            self._home_page = home_page
        else:
            self._home_page = self.metadata.get("Home-page", None)

        if description:
            self._description = description
        else:
            self._description = self.metadata.get("Summary", None)

        # Get a platform factory.
        self.factory = get_platform_factory()

        # Instantiate the paths instance for this app.
        self._paths = Paths()

        # If an icon (or icon name) has been explicitly provided, use it;
        # otherwise, the icon will be based on the distribution name.
        if icon:
            self.icon = icon
        else:
            self.icon = f"resources/{distribution_name}"

        self.on_exit = on_exit

        # We need the command set to exist so that startup et al can add commands;
        # but we don't have an impl yet, so we can't set the on_change handler
        self.commands = CommandSet()

        self._startup_method = startup

        self._main_window = None
        self._windows = WindowSet(self)

        self._full_screen_windows = None

        self._create_impl()

        # Now that we have an impl, set the on_change handler for commands
        self.commands.on_change = self._impl.create_menus

    def _create_impl(self):
        self.factory.App(interface=self)

    @property
    def paths(self) -> Paths:
        """Paths for platform appropriate locations on the user's file system.

        Some platforms do not allow arbitrary file access to any location on disk; even
        when arbitrary file system access is allowed, there are "preferred" locations
        for some types of content.

        The :class:`~toga.paths.Paths` object has a set of sub-properties that return
        :class:`pathlib.Path` instances of platform-appropriate paths on the file
        system.
        """
        return self._paths

    @property
    def name(self) -> str:
        """**DEPRECATED** – Use :any:`formal_name`."""
        warn("App.name is deprecated. Use formal_name instead", DeprecationWarning)
        return self._formal_name

    @property
    def formal_name(self) -> str:
        """The human-readable name of the app (read-only)."""
        return self._formal_name

    @property
    def distribution_name(self) -> str:
        """The name of the distribution used to load metadata with
        :any:`importlib.metadata` (read-only)."""
        return self._distribution_name

    @property
    def app_name(self) -> str:
        """**DEPRECATED** – Renamed to ``distribution_name``."""
        warn("App.app_name has been renamed to distribution_name", DeprecationWarning)
        return self._distribution_name

    @property
    def app_id(self) -> str:
        """The unique application identifier (read-only). This will usually be a
        reversed domain name, e.g. ``org.beeware.myapp``.
        """
        return self._app_id

    @property
    def author(self) -> str | None:
        """The person or organization to be credited as the author of the app
        (read-only)."""
        return self._author

    @property
    def version(self) -> str | None:
        """The version number of the app (read-only)."""
        return self._version

    @property
    def home_page(self) -> str | None:
        """The URL of a web page for the app (read-only). Used in auto-generated help
        menu items."""
        return self._home_page

    @property
    def description(self) -> str | None:
        """A brief (one line) description of the app (read-only)."""
        return self._description

    @property
    def id(self) -> str:
        """**DEPRECATED** – Use :any:`app_id`."""
        warn("App.id is deprecated. Use app_id instead", DeprecationWarning)
        return self._app_id

    @property
    def icon(self) -> Icon:
        """The Icon for the app.

        When setting the icon, you can provide either an :any:`Icon` instance, or a
        path that will be passed to the ``Icon`` constructor.
        """
        return self._icon

    @icon.setter
    def icon(self, icon_or_name: Icon | str) -> None:
        if isinstance(icon_or_name, Icon):
            self._icon = icon_or_name
        else:
            self._icon = Icon(icon_or_name)

    @property
    def widgets(self) -> WidgetRegistry:
        """The widgets managed by the app, over all windows.

        Can be used to look up widgets by ID over the entire app (e.g.,
        ``app.widgets["my_id"]``).
        """
        return self._widgets

    @property
    def windows(self) -> Iterable[Window]:
        """The windows managed by the app. Windows are added to the app when they are
        created, and removed when they are closed."""
        return self._windows

    @property
    def main_window(self) -> MainWindow:
        """The main window for the app."""
        return self._main_window

    @main_window.setter
    def main_window(self, window: MainWindow) -> None:
        self._main_window = window
        self._impl.set_main_window(window)

    @property
    def current_window(self) -> Window | None:
        """Return the currently active content window."""
        window = self._impl.get_current_window()
        if window is None:
            return None
        return window.interface

    @current_window.setter
    def current_window(self, window: Window):
        """Set a window into current active focus."""
        self._impl.set_current_window(window)

    @property
    def is_full_screen(self) -> bool:
        """Is the app currently in full screen mode?"""
        return self._full_screen_windows is not None

    def set_full_screen(self, *windows: Window) -> None:
        """Make one or more windows full screen.

        Full screen is not the same as "maximized"; full screen mode is when all window
        borders and other window decorations are no longer visible.

        :param windows: The list of windows to go full screen, in order of allocation to
            screens. If the number of windows exceeds the number of available displays,
            those windows will not be visible. If no windows are specified, the app will
            exit full screen mode.
        """
        if not windows:
            self.exit_full_screen()
        else:
            self._impl.enter_full_screen(windows)
            self._full_screen_windows = windows

    def exit_full_screen(self) -> None:
        """Exit full screen mode."""
        if self.is_full_screen:
            self._impl.exit_full_screen(self._full_screen_windows)
            self._full_screen_windows = None

    def show_cursor(self) -> None:
        """Make the cursor visible."""
        self._impl.show_cursor()

    def hide_cursor(self) -> None:
        """Hide cursor from view."""
        self._impl.hide_cursor()

    def startup(self) -> None:
        """Create and show the main window for the application.

        Subclasses can override this method to define customized startup behavior;
        however, as a result of invoking this method, the app *must* have a
        ``main_window``.
        """
        self.main_window = MainWindow(title=self.formal_name)

        if self._startup_method:
            self.main_window.content = self._startup_method(self)

        self.main_window.show()

    def _startup(self):
        # This is a wrapper around the user's startup method that performs any
        # post-setup validation.
        self.startup()
        self._verify_startup()

    def _verify_startup(self):
        if not isinstance(self.main_window, MainWindow):
            raise ValueError(
                "Application does not have a main window. "
                "Does your startup() method assign a value to self.main_window?"
            )

    def about(self) -> None:
        """Display the About dialog for the app.

        Default implementation shows a platform-appropriate about dialog using app
        metadata. Override if you want to display a custom About dialog.
        """
        self._impl.show_about_dialog()

    def visit_homepage(self) -> None:
        """Open the application's homepage in the default browser.

        If the application metadata doesn't define a homepage, this is a no-op.
        """
        if self.home_page is not None:
            webbrowser.open(self.home_page)

    def beep(self) -> None:
        """Play the default system notification sound."""
        self._impl.beep()

    def main_loop(self) -> None:
        """Invoke the application to handle user input.

        This method typically only returns once the application is exiting.
        """
        # Modify signal handlers to make sure Ctrl-C is caught and handled.
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        self._impl.main_loop()

    def exit(self) -> None:
        """Exit the application gracefully.

        This *does not* invoke the ``on_exit`` handler; the app will be immediately
        and unconditionally closed.
        """
        self._impl.exit()

    @property
    def on_exit(self) -> OnExitHandler:
        """The handler to invoke before the application exits."""
        return self._on_exit

    @on_exit.setter
    def on_exit(self, handler: OnExitHandler | None) -> None:
        def cleanup(app, should_exit):
            if should_exit or handler is None:
                app.exit()

        self._on_exit = wrapped_handler(self, handler, cleanup=cleanup)

    def add_background_task(self, handler: BackgroundTask) -> None:
        """Schedule a task to run in the background.

        Schedules a coroutine or a generator to run in the background. Control
        will be returned to the event loop during await or yield statements,
        respectively. Use this to run background tasks without blocking the
        GUI. If a regular callable is passed, it will be called as is and will
        block the GUI until the call returns.

        :param handler: A coroutine, generator or callable.
        """
        self._impl.loop.call_soon_threadsafe(wrapped_handler(self, handler), None)


class DocumentApp(App):
    def __init__(
        self,
        formal_name: str | None = None,
        app_id: str | None = None,
        distribution_name: str | None = None,
        *,
        icon: str | None = None,
        author: str | None = None,
        version: str | None = None,
        home_page: str | None = None,
        description: str | None = None,
        startup: AppStartupMethod | None = None,
        document_types: dict[str, type[Document]] = None,
        on_exit: OnExitHandler | None = None,
        app_name: str | None = None,  # DEPRECATED
        id=None,  # DEPRECATED
    ):
        """Create a document-based application.

        A document-based application is the same as a normal application, with the
        exception that there is no main window. Instead, each document managed by the
        app will create and manage it's own window (or windows).

        :param document_types: A dictionary of file extensions of document types that
            the application can managed, mapping to the :class:`toga.Document` subclass
            that will be created when a document of with that extension is opened. The
            :class:`toga.Document` subclass must take exactly 2 arguments in it's
            constructor: ``path`` and ``app``

        """
        if document_types is None:
            raise ValueError("A document must manage at least one document type.")

        self._document_types = document_types
        self._documents = []

        super().__init__(
            formal_name=formal_name,
            app_id=app_id,
            distribution_name=distribution_name,
            icon=icon,
            author=author,
            version=version,
            home_page=home_page,
            description=description,
            startup=startup,
            on_exit=on_exit,
            app_name=app_name,
            id=id,
        )

    def _create_impl(self):
        return self.factory.DocumentApp(interface=self)

    def _verify_startup(self):
        # No post-startup validation required for DocumentApps
        pass

    @property
    def document_types(self) -> dict[str, type[Document]]:
        """The document types this app can manage.

        This is a dictionary of file extensions mapping to the Document class that will
        be created when a document of with that extension is opened. This class will
        usually be a subclass of :class:`toga.Document`.toga.Document`.
        """
        return self._document_types

    @property
    def documents(self) -> list[Document]:
        """The list of documents associated with this app."""
        return self._documents

    def startup(self) -> None:
        """No-op; a DocumentApp has no windows until a document is opened.

        Subclasses can override this method to define customized startup behavior.
        """

    def _open(self, path):
        """Internal utility method; open a new document in this app, and shows the document.

        :param path: The path to the document to be opened.
        :raises ValueError: If the document is of a type that can't be opened. Backends can
            suppress this exception if necessary to presere platform-native behavior.
        """
        try:
            DocType = self.document_types[path.suffix[1:]]
        except KeyError:
            raise ValueError(f"Don't know how to open documents of type {path.suffix}")
        else:
            document = DocType(path, app=self)
            self._documents.append(document)
            document.show()
