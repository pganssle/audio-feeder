import functools
import itertools
import logging
import math
import os
import pathlib
import shutil
import typing
import warnings
from datetime import datetime, timezone
from random import SystemRandom

from PIL import Image

from . import cache_utils
from . import database_handler as dh
from . import directory_parser as dp
from . import metadata_loader as mdl
from . import object_handler as oh
from ._db_types import (
    ID,
    Database,
    MutableDatabase,
    MutableTable,
    Table,
    TableName,
)
from ._useful_types import PathType
from .config import read_from_config
from .html_utils import clean_html
from .resolver import get_resolver

_rand = SystemRandom()
_T = typing.TypeVar("_T")

# This technically violates PEP 484, but it works. See
# https://github.com/python/mypy/issues/14023 for more details.
_PBar = typing.TypeVar(
    "_PBar", bound=typing.Callable[[typing.Iterable[_T]], typing.Iterable[_T]]
)


class IDHandler:
    """
    This is a class for handling the assignment of new IDs.
    """

    def __init__(self, invalid_ids: typing.Optional[typing.Iterable[ID]] = None):
        if invalid_ids is None:
            invalid_ids = set()
        else:
            invalid_ids = set(invalid_ids)

        self.invalid_ids = invalid_ids

    def new_id(self) -> ID:
        """
        Generates a new ID and adds it to the invalid ID list.
        """

        # The default method selects a random ID from a space of 1e6 numbers,
        # or 10x the number of values as are in the invalid list, so that the
        # chance of a collision is capped at 1:10.
        int_max = 10 ** (math.ceil(math.log10(len(self.invalid_ids) + 1)) + 1)
        int_max = max((int_max, 1000000))

        while True:
            new_id_val = ID(_rand.randint(0, int_max))
            if new_id_val not in self.invalid_ids:
                break

        self.invalid_ids.add(new_id_val)
        return new_id_val


class BookDatabaseUpdater:
    AUTHOR_TABLE_NAME: typing.Final[TableName] = TableName("authors")
    BOOK_TABLE_NAME: typing.Final[TableName] = TableName("books")

    def __init__(
        self,
        books_location: PathType,
        *,
        entry_table: TableName = TableName("entries"),
        table: typing.Optional[TableName] = None,
        book_loader: typing.Type[dp.BaseAudioLoader] = dp.AudiobookLoader,
        metadata_loaders: typing.Sequence[mdl.BookLoader] = (mdl.GoogleBooksLoader(),),
        id_handler: typing.Type[IDHandler] = IDHandler,
    ):
        self.table = table or self.BOOK_TABLE_NAME
        self.entry_table = entry_table
        self.books_location = books_location
        self.book_loader = book_loader
        self.metadata_loaders = metadata_loaders
        self.id_handler = id_handler

    def load_book_paths(self) -> typing.Sequence[pathlib.Path]:
        aps = dp.load_all_audio(self.books_location)
        media_loc = read_from_config("media_loc")

        return [ap.relative_to(media_loc.path) for ap in aps]

    def update_db_entries(self, database: MutableDatabase) -> MutableDatabase:
        book_paths = self.load_book_paths()

        entry_table = typing.cast(
            typing.MutableMapping[ID, oh.Entry], database[self.entry_table]
        )

        # Find out which ones already exist
        id_by_path = {}
        for c_id, entry in entry_table.items():
            path = entry.path
            if path in id_by_path:
                raise DuplicateEntryError("Path duplicate found: {}".format(path))

            id_by_path[path] = c_id

        # Drop any paths from the table that don't exist anymore
        for path, e_id in id_by_path.items():
            media_loc_path = read_from_config("media_loc").path

            if path is None or not (media_loc_path / path).exists():
                del entry_table[e_id]

        new_paths = [path for path in book_paths if path not in id_by_path]
        new_paths = list(set(new_paths))  # Enforce unique paths only

        entry_id_handler = self.id_handler(invalid_ids=entry_table.keys())

        for path in new_paths:
            entry_obj = self.make_new_entry(path, entry_id_handler)
            entry_table[entry_obj.id] = entry_obj

        return database

    def assign_books_to_entries(self, database: MutableDatabase) -> MutableDatabase:
        # Go through and assign a book to each entry for both new entries and
        # entries with missing book IDs.
        book_table = typing.cast(
            typing.MutableMapping[ID, oh.Book], database[self.table]
        )
        entry_table = typing.cast(
            typing.Mapping[ID, oh.Entry], database[self.entry_table]
        )

        book_id_handler = self.id_handler(invalid_ids=set(book_table.keys()))

        book_to_entry: typing.MutableMapping[ID, typing.MutableSequence[ID]] = {}
        for entry_id, entry_obj in entry_table.items():
            if entry_obj.type != "Book":
                continue

            if entry_obj.data_id in book_table:
                book_obj = book_table[entry_obj.data_id]
            else:
                book_obj = self.load_book(entry_obj.path, book_table, book_id_handler)

                if book_obj.id not in book_table:
                    book_table[book_obj.id] = book_obj

                entry_obj.data_id = book_obj.id

            book_to_entry.setdefault(book_obj.id, []).append(entry_id)

        return database

    def update_book_metadata(
        self,
        database: MutableDatabase,
        pbar: typing.Optional[_PBar] = None,
        reload_metadata: bool = False,
    ) -> MutableDatabase:
        book_table = typing.cast(
            typing.MutableMapping[ID, oh.Book], database[self.table]
        )
        # Set the priority on who gets to set the description.
        description_priority = (mdl.LOCAL_DATA_SOURCE,) + tuple(
            x.source_name for x in self.metadata_loaders
        )

        if pbar is None:
            # No idea why this is necessary, but support for this sort of thing
            # is super sketchy anyway, so 🤷
            pbar_resolved: _PBar = typing.cast(_PBar, _pbar_stub)
        else:
            pbar_resolved = pbar

        # Go through and try to update metadata.
        for book_id, book_obj in pbar_resolved(book_table.items()):
            for loader in self.metadata_loaders:
                # Skip anything that's already had metadata loaded for it.
                if not reload_metadata and (
                    book_obj.metadata_sources is not None
                    and loader.source_name in book_obj.metadata_sources
                ):
                    continue

                book_obj = loader.update_book_info(
                    book_obj, overwrite_existing=reload_metadata
                )

                # Update 'last modified' on any entries updated.
                """
                for entry_id in book_to_entry.get(book_id, []):
                    entry_obj = entry_table[entry_id]
                    entry_obj.last_modified = datetime.now(timezone.utc)
                """
            # Try and assign priority for the descriptions
            if book_obj.descriptions is None:
                book_obj.descriptions = {}

            for source_name in description_priority:
                if source_name in book_obj.descriptions:
                    description = book_obj.descriptions[source_name]
                    if description is not None:
                        book_obj.description = book_obj.descriptions[source_name]
                        break
            else:
                book_obj.description = ""

            # Clean up the HTML on any book description we've gotten.
            if len(book_obj.description):
                book_obj.description = clean_html(book_obj.description)

            book_table[book_id] = book_obj

        return database

    def update_author_db(self, database: MutableDatabase) -> MutableDatabase:
        book_table = typing.cast(typing.Mapping[ID, oh.Book], database[self.table])
        author_table = typing.cast(
            typing.MutableMapping[ID, oh.Author], database[self.AUTHOR_TABLE_NAME]
        )

        author_id_handler = self.id_handler(invalid_ids=author_table.keys())

        # Now update the author database
        for book_id, book_obj in book_table.items():
            book_tag_set = set(book_obj.tags or set())

            new_authors: typing.MutableSequence[str] = []
            new_author_ids = []
            new_author_roles = []

            zl = itertools.zip_longest(
                book_obj.authors or [],
                book_obj.author_ids or [],
                book_obj.author_roles or [],
                fillvalue=None,
            )
            for author_name, author_id, author_role in zl:
                valid_author_id = author_id is not None and author_id in author_table

                if author_name is None and not valid_author_id:
                    continue  # This is a null entry

                if author_name is None:
                    assert author_id is not None
                    new_author = author_table[author_id].name
                    new_author_id = author_id
                elif not valid_author_id:
                    author_obj = self.load_author(
                        author_name, author_table, author_id_handler
                    )

                    if author_obj.id not in author_table:
                        author_table[author_obj.id] = author_obj

                    new_author = author_name
                    new_author_id = author_obj.id
                else:
                    assert author_id is not None
                    new_author = author_name
                    new_author_id = author_id

                assert new_author is not None
                new_authors.append(new_author)
                new_author_ids.append(new_author_id)
                new_author_roles.append(author_role if author_role is not None else 0)

                # Now update the author object's books and tags
                author_obj = author_table[new_author_id]
                if author_obj.books is None:
                    author_obj.books = []

                if book_id not in author_obj.books:
                    # TODO: Add an official method for this
                    typing.cast(typing.MutableSequence[ID], author_obj.books).append(
                        book_id
                    )

                orig_tags = set(author_obj.tags or set())
                author_obj.tags = list(orig_tags | book_tag_set)

            book_obj.authors = new_authors
            book_obj.author_ids = new_author_ids
            book_obj.author_roles = new_author_roles

        return database

    def update_cover_images(self, database: MutableDatabase) -> MutableDatabase:
        entry_table = typing.cast(
            typing.MutableMapping[ID, oh.Entry], database[self.entry_table]
        )
        base_static_path = read_from_config("static_media_path")
        cover_cache_path = read_from_config("cover_cache_path")

        def _img_path(img_path):
            return os.path.join(base_static_path, img_path)

        def _img_path_exists(img_path):
            return os.path.exists(_img_path(img_path))

        for entry_id, entry_obj in entry_table.items():
            # Check if the entry cover path exists.
            thumb_loc = os.path.join(
                cover_cache_path, "{}-thumb.png".format(entry_obj.id)
            )

            regenerate_thumb = not _img_path_exists(thumb_loc)

            new_cover_images = entry_obj.cover_images or []
            new_cover_images = [
                cover_image
                for cover_image in new_cover_images
                if _img_path_exists(cover_image)
            ]

            old_best_img = new_cover_images[0] if len(new_cover_images) else None

            # Check for the best cover image
            # TODO: data_obj is always going to be "book" right now, but we need to
            # make a more generic version of this.
            data_obj = dh.get_data_obj(entry_obj, database)
            assert isinstance(data_obj, oh.Book)
            if hasattr(data_obj, "cover_images") and data_obj.cover_images is not None:
                local_cover_img = data_obj.cover_images.get(mdl.LOCAL_DATA_SOURCE, None)

                if local_cover_img is not None:
                    assert isinstance(local_cover_img, pathlib.Path)
                    if local_cover_img not in new_cover_images and _img_path_exists(
                        local_cover_img
                    ):
                        new_cover_images.insert(0, local_cover_img)

                for loader in self.metadata_loaders:
                    if loader.source_name not in data_obj.cover_images:
                        continue

                    img_base = f"{entry_obj.id}_{loader.source_name}"
                    if any(
                        x.startswith(img_base)
                        for x in (os.path.split(y)[1] for y in new_cover_images)
                    ):
                        continue

                    cover_images = data_obj.cover_images[loader.source_name]
                    assert isinstance(cover_images, typing.Mapping)
                    r, img_url, desc = loader.retrieve_best_image(cover_images)

                    if r is None:
                        continue

                    assert desc is not None  # mypy narrowing
                    img_name_base = img_base + "-" + desc
                    try:
                        img_ext = _get_img_ext(r)
                    except UnsupportedImageType:
                        continue

                    img_name = img_name_base + img_ext
                    img_loc = os.path.join(cover_cache_path, img_name)

                    with open(_img_path(img_loc), "wb") as f:
                        shutil.copyfileobj(r, f)

                    new_cover_images.append(pathlib.Path(img_loc))

            if not new_cover_images:
                warnings.warn("No image found", RuntimeWarning)
                continue

            best_img = new_cover_images[0]
            regenerate_thumb = regenerate_thumb or (old_best_img != best_img)

            if regenerate_thumb:
                _generate_thumbnail(_img_path(best_img), _img_path(thumb_loc))

            entry_obj.cover_images = new_cover_images

        return database

    def make_new_entry(self, rel_path: PathType, id_handler: IDHandler) -> oh.Entry:
        """
        Generates a new entry for the specified path.

        Note: This will mutate the id_handler!
        """
        # Try to match to an existing book.
        e_id = id_handler.new_id()

        abs_path = os.path.join(read_from_config("media_loc").path, rel_path)
        lmtime = os.path.getmtime(abs_path)
        last_modified = datetime.fromtimestamp(lmtime, tz=timezone.utc)

        entry_obj = oh.Entry(
            id=e_id,
            path=pathlib.Path(rel_path),
            date_added=datetime.now(timezone.utc),
            last_modified=last_modified,
            type="Book",
            table=self.BOOK_TABLE_NAME,
            data_id=None,  # type: ignore
            hashseed=_rand.randint(0, 2**32),
        )

        return entry_obj

    def load_book(
        self, path: PathType, book_table: Table, id_handler: IDHandler
    ) -> oh.Book:
        """
        If the book is already in the table, load it by ID, otherwise create
        a new entry for it.

        :param path:
            The path to the book.

        :param book_table:
            The table in the database from which to do lookups (treated as
            immutable).

        :param id_handler:
            The handler for book IDs (this will be treated as mutable)

        :return:
            Returns a :class:`object_handler.Book` object.
        """
        book_table = typing.cast(typing.Mapping[ID, oh.Book], book_table)

        # The path will be relative to the base media path
        resolver = get_resolver()
        loc = resolver.resolve_media(os.fspath(path))

        if loc.path is None:
            raise ValueError(f"Could not resolve {path}")

        # First load title and author from the path.
        audio_info = self.book_loader.parse_audio_info(loc.path)
        audio_cover = self.book_loader.audio_cover(loc.path)

        # Load books by title and author into a cache if necessary
        books_by_key = getattr(self, "_books_by_key", {})
        cached_book_ids = getattr(self, "_cached_book_ids", {})

        bt_id = id(book_table)
        if bt_id not in books_by_key or len(books_by_key[bt_id]) < len(
            book_table.items()
        ):

            if bt_id in books_by_key:
                books_by_key_cache = books_by_key[bt_id]
                cached_book_id_set = cached_book_ids[bt_id]
                missing_keys = set(book_table.keys()) - cached_book_id_set
                book_gen: typing.Iterable[tuple[ID, oh.Book]] = (
                    (k, book_table[k]) for k in missing_keys
                )
            else:
                books_by_key_cache = {}
                cached_book_id_set = set()
                book_gen = book_table.items()

            for book_id, book_obj in book_gen:
                # Want to make sure each of these is unique and reproducible
                assert book_obj.authors is not None
                assert book_obj.title is not None
                key_id = self._book_key(book_obj.authors, book_obj.title)

                if key_id in books_by_key_cache:
                    msg = (
                        "Book table has duplicate author-title combination:"
                        + " {}".format(key_id)
                    )
                    raise DuplicateEntryError(msg)

                books_by_key_cache[key_id] = book_id
                cached_book_id_set.add(book_id)

            books_by_key[bt_id] = books_by_key_cache
            cached_book_ids[bt_id] = cached_book_id_set

            self._books_by_key = books_by_key
            self._cached_book_ids = cached_book_ids
        else:
            books_by_key_cache = books_by_key[bt_id]

        # Try and find the book in the lookup table
        key_id = self._book_key(audio_info["authors"], audio_info["title"])
        if key_id in books_by_key_cache:
            return book_table[books_by_key_cache[key_id]]

        # If we didn't find the book, we'll have to create a new barebones
        # book object.
        book_id = id_handler.new_id()
        series_name, series_number = audio_info["series"]
        if audio_cover is None:
            cover_images = None
        else:
            # Get audio cover relative to the static media path
            static_media_path: pathlib.Path = read_from_config("static_media_path")
            audio_cover = pathlib.Path(os.path.relpath(audio_cover, static_media_path))
            # audio_cover = resolver.resolve_static(audio_cover).path
            cover_images = {mdl.LOCAL_DATA_SOURCE: audio_cover}

        book_obj = oh.Book(
            id=book_id,
            title=audio_info["title"],
            authors=audio_info["authors"],
            series_name=series_name,
            series_number=series_number,
            cover_images=cover_images,
        )

        return book_obj

    def load_author(
        self,
        author_name: str,
        author_table: typing.Mapping[ID, oh.Author],
        id_handler: IDHandler,
        disamb_func: typing.Callable[
            [typing.Sequence[oh.Author]], oh.Author
        ] = lambda x: x[0],
    ) -> oh.Author:
        """
        If the author is already in the table, load it by ID, otherwise create
        a new entry for it.

        .. note::
            Currently you have to manually de-duplicate authors with conflicting
            names. There may be some programmatic way to do this by lookup to
            a database, but it is not implemented. That said, multiple authors
            MAY have the same name.

        :param author_name:
            The author's full name string.

        :param id_handler:
            A :class:`IDHandler` for authors - treated as mutable.

        :param book_ids:
            If not :py:object:`None`, this should be a list of ids in the
            books table of additional books by this author.

        :param disamb_func:
            For ambiguous author name lookups, we'll have multiple authors in
            an essentially random order. ``disamb_func`` is a function taking a
            list of :class:`object_handler.Author` objects and returning the
            disambiguated value. It is assumed that this returns a
            :class:`object_handler.Author` object.

            By default returns the first object in the list of authors by the
            given name.

        :return:
            Returns a :class:`object_handler.Author` object, or whatever is
            returned by the ``diamb_func``, if different.
        """
        at_id = id(author_table)
        try:
            authors_by_name_cache = getattr(self, "_authors_by_name")
            cached_author_ids_cache = getattr(self, "_cached_author_ids")
        except AttributeError:
            # Need to establish the author cache
            authors_by_name_cache = {}
            cached_author_ids_cache = {}

            self._authors_by_name = authors_by_name_cache
            self._cached_author_ids = cached_author_ids_cache

        # Construct a lookup mapping author name to author id if it isn't
        # already cached.
        if at_id not in cached_author_ids_cache or at_id not in authors_by_name_cache:
            authors_by_name: typing.Dict[
                typing.Optional[str], typing.MutableSequence[ID]
            ] = {}
            cached_author_ids: typing.Set[ID] = set()

            cached_author_ids_cache[at_id] = cached_author_ids
            authors_by_name_cache[at_id] = authors_by_name
        else:
            cached_author_ids = cached_author_ids_cache[at_id]
            authors_by_name = authors_by_name_cache[at_id]

        if set(author_table.keys()) != cached_author_ids:
            author_table = typing.cast(
                typing.Mapping[ID, oh.Author],
                dh.get_database_table(TableName("authors")),
            )

            for author_id, author_obj in author_table.items():
                if author_obj.name not in authors_by_name:
                    authors_by_name[author_obj.name] = [author_id]
                elif author_id not in authors_by_name[author_obj.name]:
                    authors_by_name[author_obj.name].append(author_id)

                cached_author_ids.add(author_id)

        # Try to find the author in the cached lookup table
        if author_name in authors_by_name:
            author_list: typing.List[oh.Author] = [
                author_table[author_id] for author_id in authors_by_name[author_name]
            ]
        else:
            author_id = id_handler.new_id()
            author_sort_name = self.author_sort(author_name)

            kwargs = {
                "id": author_id,
                "name": author_name,
                "sort_name": author_sort_name,
            }

            author_obj = oh.Author(**kwargs)  # type: ignore
            author_list = [author_obj]

        return disamb_func(author_list)

    @classmethod
    def author_sort(cls, author_name: str) -> typing.Optional[str]:
        """
        Takes the author name and returns a plausible sort name.

        :param author_name:
            The input author name.

        :return:
            Returns a plausible sort name. Some examples:

            .. doctest::

                >>> BookDatabaseUpdater.author_sort('Bob Jones')
                'Jones, Bob'
                >>> BookDatabaseUpdater.author_sort('Teller')
                'Teller'
                >>> BookDatabaseUpdater.author_sort('Steve Miller, Ph.D')
                'Miller, Steve, Ph.D'
                >>> BookDatabaseUpdater.author_sort('James Mallard Filmore')
                'Filmore, James Mallard'
        """
        comma_split = author_name.split(",")

        def bad_name_warning():
            warnings.warn(
                "Cannot parse author name: {}".format(author_name), RuntimeWarning
            )

        prenoms = None
        surname = None
        modifiers = None

        if len(comma_split) == 2:
            base_name, modifiers = comma_split
            modifiers = modifiers.strip()
        elif len(comma_split) == 1:
            (base_name,) = comma_split
        else:
            bad_name_warning()
            return None  # Don't know what to do with this

        base_name = base_name.strip()

        # We'll assume this is a space-delimited name and the last element is
        # the surname. This is probably fine in almost all cases.
        split_name = base_name.split(" ")
        if len(split_name) == 1:
            prenom = split_name[0]
            author_sort_name = split_name[0]
        else:
            author_sort_name = ", ".join((split_name[-1], " ".join(split_name[:-1])))

        if modifiers:
            author_sort_name += ", " + modifiers

        return author_sort_name

    @classmethod
    def _book_key(cls, authors: typing.Sequence[str], title: str) -> typing.Hashable:
        """The key should be hashable and reproducible"""
        return (tuple(sorted(authors)), title)


###
# Trigger update action
UPDATE_OUTPUT: typing.Sequence[str] = []  # TODO: Replace with logging-based solution
UPDATE_IN_PROGRESS: bool = False


def _log_update_output(update: str) -> None:
    global UPDATE_OUTPUT
    if UPDATE_OUTPUT is None:
        UPDATE_OUTPUT = []

    typing.cast(typing.MutableSequence[str], UPDATE_OUTPUT).append(update)
    logging.info(update)


def _clear_update_output() -> None:
    global UPDATE_OUTPUT
    typing.cast(typing.MutableSequence[str], UPDATE_OUTPUT).clear()


def _update_books(
    update_path: str, progress_bar: typing.Optional[_PBar] = None
) -> None:
    """
    Trigger an update to the database.
    """

    _log_update_output("Updating audiobooks from all directories.")
    path = get_resolver().resolve_media(update_path).path
    assert path is not None

    book_updater = BookDatabaseUpdater(path)

    OpFunction = typing.Callable[[typing.Any], typing.Any]
    ops: typing.Sequence[typing.Tuple[OpFunction, str]] = [
        (book_updater.update_db_entries, "Updating database entries."),
        (book_updater.assign_books_to_entries, "Assigning books to entries"),
        (
            functools.partial(book_updater.update_book_metadata, pbar=progress_bar),
            "Updating book metadata",
        ),
        (book_updater.update_author_db, "Updating author db"),
        (book_updater.update_cover_images, "Updating cover images"),
    ]

    try:
        _log_update_output("Loading existing database")
        db = dh.load_database()

        for op, log_output in ops:
            _log_update_output(log_output)
            op(db)

        dh.save_database(db)
        cache_utils.clear_caches("books")
        _log_update_output("Reloading database")
        dh.get_database(refresh=True)
    finally:
        _clear_update_output()

        global UPDATE_IN_PROGRESS
        UPDATE_IN_PROGRESS = False


def update(
    content_type: typing.Optional[str] = None,
    path: typing.Optional[str] = None,
    progress_bar: typing.Optional[_PBar] = None,
) -> None:

    if path is None:
        path = "."

    if content_type is None or content_type == "books":
        _update_books(update_path=path, progress_bar=progress_bar)
    else:
        raise ValueError(f"Unknown content type: {content_type}")


###
# Util
def _pbar_stub(iterator_: typing.Iterable[_T]) -> typing.Iterable[_T]:
    return iterator_


def _generate_thumbnail(img_loc: PathType, thumb_loc: PathType) -> None:
    img = Image.open(img_loc)
    w, h = img.size
    w_m, h_m = read_from_config("thumb_max")

    # Unspecified widths and heights are unlimited
    w_m = w_m or w
    h_m = h_m or h

    # Check who has a larger aspect ratio
    ar = w / h
    ar_m = w_m / h_m

    if ar >= ar_m:
        # If the image has a wider aspect ratio than we do, scale by width
        scale = w_m / w
    else:
        scale = h_m / h

    # Don't upscale it
    scale = min([scale, 1])

    img.thumbnail((w * scale, h * scale))
    img.save(thumb_loc)


def _get_img_ext(fobj: typing.BinaryIO) -> str:

    img = Image.open(fobj)
    img_type = img.format
    ext_map = {
        "GIF": ".gif",
        "JPEG": ".jpg",
        "JPEG 2000": ".jpg",
        "PNG": ".png",
        "BMP": ".bmp",
        "TIFF": ".tiff",
    }

    fobj.seek(0)

    if img_type not in ext_map:
        raise UnsupportedImageType("Unsupported image type.")

    return ext_map[img_type]


###
# Errors
class DuplicateEntryError(ValueError):
    """Raised when a duplicate entry is found in the database."""

    pass


class UnsupportedImageType(ValueError):
    pass
