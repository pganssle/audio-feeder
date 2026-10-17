Themes and appearance
=====================

The book list comes with six themes, which change how it looks without
changing what's on it. Each person picks their own in the "Appearance" section
of the menu, and the choice is stored in a cookie, so it applies to that
browser only: you can use one theme on your computer and another on your phone,
and other people using the same server keep whatever theme they chose.

The page itself is the same whichever theme is chosen, and each theme is one
small stylesheet, so switching between them doesn't make the page any slower to
load.

Built-in themes
---------------

Classic
    The default. It keeps the colours and layout of the original book list
    (the dark bar, the teal links and the alternating grey bands), and switches
    to a dark version when your system is set to dark mode.

    .. image:: images/screenshots/themes/classic.jpg
        :width: 800px
        :alt: The book list in the Classic theme

    .. image:: images/screenshots/themes/classic_dark.jpg
        :width: 800px
        :alt: The book list in the Classic theme, in dark mode

Shelf
    Warm paper, old-style serif titles and italic authors, in a narrower
    column. It also has a dark mode.

    .. image:: images/screenshots/themes/shelf.jpg
        :width: 800px
        :alt: The book list in the Shelf theme

Card catalog
    Each book is typed up on an index card, filed in a wooden drawer, with the
    cover clipped to the corner and the feeds as rubber stamps.

    .. image:: images/screenshots/themes/card_catalog.jpg
        :width: 800px
        :alt: The book list in the Card catalog theme

Tape deck
    A dark theme in which each book is a cassette label, the feeds are the
    deck's keys, and the page numbers and tag counts are on its display.

    .. image:: images/screenshots/themes/tape_deck.jpg
        :width: 800px
        :alt: The book list in the Tape deck theme

Cyberpunk
    A dark theme, laid out like a heads-up display: each book is a panel with
    its record number in the corner, on a faint grid, with magenta for anything
    that can be pressed, cyan for readouts and amber for the exclude toggles.
    It's dark only, whatever the system is set to.

    .. image:: images/screenshots/themes/cyberpunk.jpg
        :width: 800px
        :alt: The book list in the Cyberpunk theme

Plain
    The browser's own look: serif text, blue links and feeds written as
    ``[Original]``. It uses the system's colours, so it's light or dark to
    match.

    .. image:: images/screenshots/themes/plain.jpg
        :width: 800px
        :alt: The book list in the Plain theme

.. _custom-themes:

Writing your own theme
----------------------

A theme is a stylesheet in the ``themes`` directory of the CSS directory
(``static/css/themes/`` with the default settings), and any stylesheet you put
there shows up in the "Appearance" menu, named after its file: ``night_bus.css``
is listed as "Night bus". The list of themes is read when the server starts, so
restart it after adding one.

A theme's stylesheet is loaded after audio-feeder's own (``main.css``, which is
also the Classic theme), so it only needs to change what's different. Most of
the look is set by custom properties on ``:root``, and a theme can be as small
as a few of them:

.. code-block:: css

    /* static/css/themes/night_bus.css, which shows up as "Night bus" */
    :root {
        color-scheme: dark;
        --paper: #10131c;
        --surface: #181d2a;
        --ink: #e9ecf5;
        --muted: #9099b0;
        --rule: #2a3146;
        --accent: #ffcf4a;
        --accent-ink: #10131c;
        --bar: #05070c;
        --entry-background: var(--surface);
        --entry-background-alt: var(--surface);
        --font-display: Futura, "Century Gothic", "URW Gothic", sans-serif;
    }

The custom properties are described at the top of ``main.css``. The main ones
are:

``--paper``, ``--surface``, ``--ink``, ``--muted`` and ``--rule``
    The page's background, the background of panels and controls, the text,
    secondary text, and lines and borders.

``--accent`` and ``--exclude``, each with an ``-ink`` colour for text on top
    Links and buttons, and the include and exclude toggles in the menu.

``--bar`` and ``--bar-ink``
    The top bar and the headers of the menu and the page jump menu.

``--entry-background``, ``--entry-background-alt``, ``--entry-padding`` and ``--entry-rule``
    The bands that books are on, which alternate between the two backgrounds,
    and the line between books.

``--cloth-saturation``, ``--cloth-lightness`` and ``--cloth-ink``
    The covers that are drawn for books without one, each in a colour picked
    from the book's ID.

``--font-body``, ``--font-display`` and ``--display-style``
    The fonts, and whether the title, author names and a few other flourishes
    are italic. The built-in themes only use fonts that come with the
    operating system, so they don't have to download any.

``--measure``, ``--cover-width``, ``--radius`` and ``--target``
    The widest the page's column gets, the width of the covers, how rounded
    corners are, and the size of buttons (which is larger on touch screens).

To change the default look for everyone rather than adding a theme, add a
stylesheet with the ``extra_css_files`` setting (see :doc:`configuration`).
These are loaded after ``main.css`` and before the chosen theme, so a theme
still overrides them.

Everything other than the custom properties is part of the page's markup,
which is more likely to change between releases, so a theme that restyles
other things may need updating when you upgrade.

The name and the logo
---------------------

The name in the top bar is "audio-feeder" by default, and can be changed with
the ``site_title`` setting. Next to it is audio-feeder's logo, which is also
the favicon; the ``site_logo`` setting replaces both with an image of your own,
given as a path relative to the static directory or as a URL, and setting it
to an empty string removes the logo:

.. code-block:: yaml

    site_title: The Listening Room
    site_logo: images/our-logo.svg

Books without a cover get one drawn by the page, in a colour picked from the
book's ID, with the book's title and a small copy of audio-feeder's logo on it
to show that it isn't the book's real cover; "Dracula" in the screenshots above
has one, drawn in each theme's own style.
