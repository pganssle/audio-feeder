Features
--------

- The book list has a new design, which works the same way on phones and computers. Each book shows its title, author and a line of details, with a button for each of its feeds and its QR code, and long descriptions continue in place when "more" is clicked. Books without a cover get a cloth binding with their title on it, marked with audio-feeder's logo.

- The book list can be themed. Themes are chosen in the "Appearance" section of the menu and remembered by the browser. The default theme ("Classic") keeps the old look's colours and has a dark mode, and audio-feeder comes with four more themes: "Shelf", "Card catalog", "Plain" and "Tape deck". To add your own, put a stylesheet in the ``themes`` directory of the CSS directory (by default ``static/css/themes``); see the custom properties at the top of ``main.css`` for what most themes need to set.

- The book list now has a logo and a favicon. The name in the top bar can be changed with the new ``site_title`` setting, and the logo (which is also the favicon) with ``site_logo`` (a path relative to the static directory, or a URL; an empty string removes the logo).

Bugfixes
--------

- Fixed books without a cover showing a broken image.

Misc
----

- The book list is much smaller: about a third smaller for a page of 25 books, and it uses no web fonts and only a few lines of JavaScript. Covers are shown using their thumbnails, which are now saved as JPEGs (about 13 KB each, rather than about 70 KB as PNGs), and covers below the first few load as they're scrolled to. The thumbnails are regenerated on the next update.

- Stylesheets in the CSS directory that didn't come with audio-feeder are no longer added to the book list; use the ``extra_css_files`` setting or a theme instead. The icon font is no longer installed.

- The book list's markup has changed, so custom stylesheets and ``list.tpl`` templates written for the old design may need updating.
