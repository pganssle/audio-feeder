Bugfixes
--------

- Sorting by author, title or series now ignores case and accents, so "Miéville" sorts before "Mitnick" and "van der Whatever" no longer sorts after every capitalized name. Numbers in names and titles are also sorted by their value, so "Book 2" comes before "Book 10". Names that differ only in case or accents are ordered by the original text. (`#81 <https://github.com/pganssle/audio-feeder/issues/81>`_)
