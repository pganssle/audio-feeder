Bugfixes
--------

- A book directory whose name doesn't match the ``Author - [Series N] - Title`` format no longer makes the whole update fail. Instead, a warning is logged and the book is added with the directory name as its title and no author; its metadata is still looked up by title, but the author is never filled in from that lookup. Books with no author are listed and their feeds rendered with just the title. (`#104 <https://github.com/pganssle/audio-feeder/issues/104>`_)
