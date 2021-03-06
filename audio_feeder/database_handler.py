import imghdr
import itertools
import math
import os
import shutil
import warnings

from datetime import datetime, timezone
from random import SystemRandom
_rand = SystemRandom()

from . import directory_parser as dp
from . import metadata_loader as mdl
from . import schema_handler as sh
from . import object_handler as oh

from .config import read_from_config
from .resolver import get_resolver
from .html_utils import clean_html

from ruamel import yaml

from PIL import Image

DB_VERSION = 0


def load_table(table_loc, table_type):
    """
    Loads a table of type ``table_type`` from the YAML file ``table_loc``.
    """
    with open(table_loc, 'r') as yf:
        table_file = yaml.safe_load(yf)

    assert table_file['db_version'] == DB_VERSION
    table_list = table_file['data']

    raw_table = (table_type(**params) for params in table_list)
    table_by_id = {x.id: x for x in raw_table}

    return table_by_id


def save_table(table_loc, table):
    """
    Saves a table of type ``table_type`` to a YAML file ``table_loc``
    """
    table_list = [obj.to_dict_sparse() for obj_id, obj in table.items()]
    table_obj = {
        'db_version': DB_VERSION,
        'data': table_list
    }

    if os.path.exists(table_loc):
        # Cache a backup of this
        shutil.copy2(table_loc, _get_bak_loc(table_loc))

    with open(table_loc, 'w') as yf:
        yaml.dump(table_obj, stream=yf, default_flow_style=False)


def load_database(schema_loc=None, db_loc=None):
    """
    Loads the 'database' into memory.

    For now, the 'database' is a directory full of YAML files, because I
    have not yet implemented the ability to make hand-modifications to the
    metadata, and I don't know how to easily edit SQL databases.
    """
    schema_loc, db_loc = _get_schema_db_locs(schema_loc=schema_loc,
                                             db_loc=db_loc)

    schema = sh.load_schema(schema_loc)

    # The tables will just be "table.yml"
    tables = {}
    for table, type_name in schema['tables'].items():
        table_type = oh.TYPE_MAPPING[type_name]

        table_loc = _get_table_loc(db_loc, table)
        if not os.path.exists(table_loc):
            tables[table] = {}
        else:
            # Load the table
            tables[table] = load_table(table_loc, table_type)

    return tables


def save_database(database, schema_loc=None, db_loc=None):
    """
    Saves the 'database' into memory. See :func:`load_database` for details.
    """
    schema_loc, db_loc = _get_schema_db_locs(schema_loc=schema_loc,
                                             db_loc=db_loc)

    schema = sh.load_schema(schema_loc)

    if not os.path.exists(db_loc):
        os.makedirs(db_loc)

    # Try and do this as a pseudo-atomic operation
    tables_saved = []
    try:
        for table in schema['tables'].keys():
            table_loc = _get_table_loc(db_loc, table)
            save_table(table_loc, database[table])
            tables_saved.append(table_loc)
    except Exception as e:
        # Restore the .bak files that were made
        for table_loc in tables_saved:
            bak_loc = _get_bak_loc(table_loc)
            if os.path.exists(bak_loc):
                shutil.move(bak_loc, table_loc)

        raise e


def get_database(refresh=False):
    """
    Loads the current default database into a cached read-only memory
    """
    db = getattr(get_database, '_database', None)
    if db is None or refresh:
        db = load_database()
        get_database._database = db

    return db


def get_database_table(table_name, database=None):
    """
    Loads a database table from a cached read-only database.
    """
    db = database or get_database()

    return db[table_name]


def get_data_obj(entry_obj, database=None):
    """
    Given an :class:`object_handler.Entry` object, return the corresponding data
    object, loaded from the appropriate table.
    """
    # Loads the data table
    table = get_database_table(entry_obj.table, database=database)

    return table[entry_obj.data_id]


class IDHandler:
    """
    This is a class for handling the assignment of new IDs.
    """
    def __init__(self, invalid_ids=None):
        if invalid_ids is None:
            invalid_ids = set()
        else:
            invalid_ids = set(invalid_ids)

        self.invalid_ids = invalid_ids

    def new_id(self):
        """
        Generates a new ID and adds it to the invalid ID list.
        """

        # The default method selects a random ID from a space of 1e6 numbers,
        # or 10x the number of values as are in the invalid list, so that the
        # chance of a collision is capped at 1:10.
        int_max = 10 ** (math.ceil(math.log10(len(self.invalid_ids) + 1)) + 1)
        int_max = max((int_max, 1000000))

        while True:
            new_id_val = _rand.randint(0, int_max)
            if new_id_val not in self.invalid_ids:
                break

        self.invalid_ids.add(new_id_val)
        return new_id_val


class BookDatabaseUpdater:
    AUTHOR_TABLE_NAME = 'authors'
    BOOK_TABLE_NAME = 'books'

    def __init__(self, books_location,
                 entry_table='entries', table=None,
                 book_loader=dp.AudiobookLoader,
                 metadata_loaders=(mdl.GoogleBooksLoader(),),
                 id_handler=IDHandler):
        self.table = table or self.BOOK_TABLE_NAME
        self.entry_table = entry_table
        self.books_location = books_location
        self.book_loader = book_loader
        self.metadata_loaders = metadata_loaders
        self.id_handler = id_handler

    def load_book_paths(self):
        aps = dp.load_all_audio(self.books_location)
        media_loc = read_from_config('media_loc')

        return [os.path.relpath(ap, media_loc.path) for ap in aps]

    def update_db_entries(self, database):
        book_paths = self.load_book_paths()

        entry_table = database[self.entry_table]

        # Find out which ones already exist
        id_by_path = {}
        for c_id, entry in entry_table.items():
            path = entry.path
            if path in id_by_path:
                raise DuplicateEntryError('Path duplicate found: {}'.format(path))

            id_by_path[path] = c_id

        # Drop any paths from the table that don't exist anymore
        for path, e_id in id_by_path.items():
            full_path = os.path.join(read_from_config('media_loc').path,
                                     path)
            if not os.path.exists(full_path):
                del entry_table[e_id]

        new_paths = [path for path in book_paths if path not in id_by_path]
        new_paths = list(set(new_paths))        # Enforce unique paths only

        entry_id_handler = self.id_handler(invalid_ids=entry_table.keys())

        for path in new_paths:
            entry_obj = self.make_new_entry(path, entry_id_handler)
            entry_table[entry_obj.id] = entry_obj

        return database

    def assign_books_to_entries(self, database):
        # Go through and assign a book to each entry for both new entries and
        # entries with missing book IDs.
        book_table = database[self.table]
        entry_table = database[self.entry_table]

        book_id_handler = self.id_handler(invalid_ids=book_table.keys())

        book_to_entry = {}
        for entry_id, entry_obj in entry_table.items():
            if entry_obj.type != 'Book':
                continue

            if entry_obj.data_id in book_table:
                book_obj = book_table[entry_obj.data_id]
            else:
                book_obj = self.load_book(entry_obj.path,
                                          book_table, book_id_handler)

                if book_obj.id not in book_table:
                    book_table[book_obj.id] = book_obj

                entry_obj.data_id = book_obj.id

            book_to_entry.setdefault(book_obj.id, []).append(entry_id)

        return database

    def update_book_metadata(self, database, pbar=None, reload_metadata=False):
        book_table = database[self.table]
        # Set the priority on who gets to set the description.
        description_priority = ((mdl.LOCAL_DATA_SOURCE,) +
            tuple(x.SOURCE_NAME for x in self.metadata_loaders))

        # Go through and try to update metadata.
        if pbar is None:
            pbar = _PBarStub()

        for book_id, book_obj in pbar(book_table.items()):
            for loader in self.metadata_loaders:
                # Skip anything that's already had metadata loaded for it.
                if (not reload_metadata and
                    (book_obj.metadata_sources is not None and
                     loader.SOURCE_NAME in book_obj.metadata_sources)):
                    continue

                book_obj = loader.update_book_info(book_obj,
                    overwrite_existing=reload_metadata)

                # Update 'last modified' on any entries updated.
                '''
                for entry_id in book_to_entry.get(book_id, []):
                    entry_obj = entry_table[entry_id]
                    entry_obj.last_modified = datetime.now(timezone.utc)
                '''
            # Try and assign priority for the descriptions
            if book_obj.descriptions is None:
                book_obj.descriptions = {}

            for source_name in description_priority:
                if source_name in book_obj.descriptions:
                    book_obj.description = book_obj.descriptions[source_name]
                    break
            else:
                book_obj.description = ''

            # Clean up the HTML on any book description we've gotten.
            book_obj.description = clean_html(book_obj.description)

            book_table[book_id] = book_obj

        return database

    def update_author_db(self, database):
        book_table = database[self.table]
        author_table = database[self.AUTHOR_TABLE_NAME]

        author_id_handler = self.id_handler(invalid_ids=author_table.keys())

        # Now update the author database
        for book_id, book_obj in book_table.items():
            book_tag_set = set(book_obj.tags or set())

            new_authors = []
            new_author_ids = []
            new_author_roles = []

            zl = itertools.zip_longest(book_obj.authors or [],
                                       book_obj.author_ids or [], 
                                       book_obj.author_roles or [],
                                       fillvalue=None)
            for author_name, author_id, author_role in zl:
                valid_author_id = (author_id is not None and
                                   author_id in author_table)

                if author_name is None and not valid_author_id:
                    continue   # This is a null entry

                if author_name is None:
                    new_author = author_table[author_id].name
                    new_author_id = author_id
                elif not valid_author_id:
                    author_obj = self.load_author(author_name,
                                                  author_table,
                                                  author_id_handler)

                    if author_obj.id not in author_table:
                        author_table[author_obj.id] = author_obj

                    new_author = author_name
                    new_author_id = author_obj.id
                else:
                    new_author = author_name
                    new_author_id = author_id

                new_authors.append(new_author)
                new_author_ids.append(new_author_id)
                new_author_roles.append(author_role if author_role is not None
                                        else 0)

                # Now update the author object's books and tags
                author_obj = author_table[new_author_id]
                if author_obj.books is None:
                    author_obj.books = []

                if book_id not in author_obj.books:
                    author_obj.books.append(book_id)

                orig_tags = set(author_obj.tags or set())
                author_obj.tags = list(orig_tags | book_tag_set)

            book_obj.authors = new_authors
            book_obj.author_ids = new_author_ids
            book_obj.roles = new_author_roles

        return database

    def update_cover_images(self, database):
        entry_table = database[self.entry_table]
        base_static_path = read_from_config('static_media_path')
        cover_cache_path = read_from_config('cover_cache_path')

        def _img_path(img_path):
            return os.path.join(base_static_path, img_path)

        def _img_path_exists(img_path):
            return os.path.exists(_img_path(img_path))

        for entry_id, entry_obj in entry_table.items():
            # Check if the entry cover path exists.
            thumb_loc = os.path.join(cover_cache_path, 
                                     '{}-thumb.png'.format(entry_obj.id))

            regenerate_thumb = not _img_path_exists(thumb_loc)

            new_cover_images = entry_obj.cover_images or []
            new_cover_images = [cover_image
                                for cover_image in new_cover_images
                                if _img_path_exists(cover_image)]

            old_best_img = new_cover_images[0] if len(new_cover_images) else None

            # Check for the best cover image
            data_obj = get_data_obj(entry_obj, database)
            if hasattr(data_obj, 'cover_images') and data_obj.cover_images is not None:
                local_cover_img = data_obj.cover_images.get(mdl.LOCAL_DATA_SOURCE, None)

                if local_cover_img is not None:
                    if (local_cover_img not in new_cover_images
                        and _img_path_exists(local_cover_img)):
                        new_cover_images.insert(0, local_cover_img)

                for loader in self.metadata_loaders:
                    if loader.SOURCE_NAME not in data_obj.cover_images:
                        continue

                    img_base = '{}_{}'.format(entry_obj.id, loader.SOURCE_NAME)
                    if any(x.startswith(img_base)
                           for x in (os.path.split(y)[1] for y in new_cover_images)):
                        continue

                    cover_images = data_obj.cover_images[loader.SOURCE_NAME]
                    r, img_url, desc = loader.retrieve_best_image(cover_images)

                    if r is None:
                        continue

                    img_name_base = img_base + '-' + desc
                    try:
                        img_ext = _get_img_ext(r)
                    except UnsupportedImageType:
                        continue

                    img_name = img_name_base + img_ext
                    img_loc = os.path.join(cover_cache_path, img_name)
                    
                    with open(_img_path(img_loc), 'wb') as f:
                        shutil.copyfileobj(r, f)

                    new_cover_images.append(img_loc)

            if not new_cover_images:
                warnings.warn('No image found', RuntimeWarning)
                continue

            best_img = new_cover_images[0]
            regenerate_thumb = regenerate_thumb or (old_best_img != best_img)

            if regenerate_thumb:
                _generate_thumbnail(_img_path(best_img), _img_path(thumb_loc))

            entry_obj.cover_images = new_cover_images

        return database

    def make_new_entry(self, rel_path, id_handler):
        """
        Generates a new entry for the specified path.

        Note: This will mutate the id_handler!
        """
        # Try to match to an existing book.
        e_id = id_handler.new_id()

        abs_path = os.path.join(read_from_config('media_loc').path, rel_path)
        lmtime = os.path.getmtime(abs_path)
        added_dt = datetime.utcfromtimestamp(lmtime)
        last_modified = added_dt.replace(tzinfo=timezone.utc)

        entry_obj = oh.Entry(id=e_id, path=rel_path,
            date_added=datetime.now(timezone.utc),
            last_modified=last_modified,
            type='Book', table=self.BOOK_TABLE_NAME, data_id=None,
            hashseed=_rand.randint(0, 2**32))

        return entry_obj

    def load_book(self, path, book_table, id_handler):
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

        # The path will be relative to the base media path
        resolver = get_resolver()
        loc = resolver.resolve_media(path)

        # First load title and author from the path.
        audio_info = self.book_loader.parse_audio_info(loc.path)
        audio_cover = self.book_loader.audio_cover(loc.path)

        # Load books by title and author into a cache if necessary
        books_by_key = getattr(self, '_books_by_key', {})
        cached_book_ids = getattr(self, '_cached_book_ids', {})

        bt_id = id(book_table)
        if (bt_id not in books_by_key or 
            len(books_by_key[bt_id]) < len(book_table.items())):

            if bt_id in books_by_key:
                books_by_key_cache = books_by_key[bt_id]
                cached_book_id_set = cached_book_ids[bt_id]
                missing_keys = set(book_table.keys()) - cached_book_id_set
                book_gen = ((k, book_table[k]) for k in missing_keys)
            else:
                books_by_key_cache = {}
                cached_book_id_set = set()
                book_gen = book_table.items()

            for book_id, book_obj in book_gen:
                # Want to make sure each of these is unique and reproducible
                key_id = self._book_key(book_obj.authors, book_obj.title)

                if key_id in books_by_key_cache:
                    msg = ('Book table has duplicate author-title combination:'+
                           ' {}'.format(key_id))
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
        key_id = self._book_key(audio_info['authors'], audio_info['title'])
        if key_id in books_by_key_cache:
            return book_table[books_by_key_cache[key_id]]

        # If we didn't find the book, we'll have to create a new barebones
        # book object.
        book_id = id_handler.new_id()
        series_name, series_number = audio_info['series']
        if audio_cover is None:
            cover_images = None
        else:
            # Get audio cover relative to the static media path
            audio_cover = os.path.relpath(audio_cover,
                read_from_config('static_media_path'))
            # audio_cover = resolver.resolve_static(audio_cover).path
            cover_images = {mdl.LOCAL_DATA_SOURCE: audio_cover}

        book_obj = oh.Book(id=book_id,
            title=audio_info['title'],
            authors=audio_info['authors'],
            series_name=series_name,
            series_number=series_number,
            cover_images=cover_images
        )

        return book_obj

    def load_author(self, author_name, author_table, id_handler,
                    disamb_func=lambda x: x[0]):
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
            authors_by_name_cache = getattr(self, '_authors_by_name')
            cached_author_ids_cache = getattr(self, '_cached_author_ids')
        except AttributeError:
            # Need to establish the author cache
            authors_by_name_cache = {}
            cached_author_ids_cache = {}

            self._authors_by_name = authors_by_name_cache
            self._cached_author_ids = cached_author_ids_cache

        # Construct a lookup mapping author name to author id if it isn't
        # already cached.
        if (at_id not in cached_author_ids_cache or
            at_id not in authors_by_name_cache):
            authors_by_name = {}
            cached_author_ids = set()

            cached_author_ids_cache[at_id] = cached_author_ids
            authors_by_name_cache[at_id] = authors_by_name
        else:
            cached_author_ids = cached_author_ids_cache[at_id]
            authors_by_name = authors_by_name_cache[at_id]

        if set(author_table.keys()) != cached_author_ids:
            author_table = get_database_table('authors')

            for author_id, author_obj in author_table.items():
                if author_obj.name not in authors_by_name:
                    authors_by_name[author_obj.name] = [author_id]
                elif author_id not in authors_by_name[author_obj.name]:
                    authors_by_name[author_obj.name].append(author_id)

                cached_author_ids.add(author_id)

        # Try to find the author in the cached lookup table
        if author_name in authors_by_name:
            author_list = [author_table[author_id]
                           for author_id in authors_by_name[author_name]]
        else:
            author_id = id_handler.new_id()
            author_sort_name = self.author_sort(author_name)

            kwargs = {
                'id': author_id,
                'name': author_name,
                'sort_name': author_sort_name
            }

            author_obj = oh.Author(**kwargs)
            author_list = [author_obj]

        return disamb_func(author_list)

    @classmethod
    def author_sort(cls, author_name):
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
        comma_split = author_name.split(',')

        def bad_name_warning():
            warnings.warn('Cannot parse author name: {}'.format(author_name),
                          RuntimeWarning)

        prenoms = None
        surname = None
        modifiers = None

        if len(comma_split) == 2:
            base_name, modifiers = comma_split
            modifiers = modifiers.strip()
        elif len(comma_split) == 1:
            base_name, = comma_split
        else:
            bad_name_warning()
            return None  # Don't know what to do with this

        base_name = base_name.strip()

        # We'll assume this is a space-delimited name and the last element is
        # the surname. This is probably fine in almost all cases.
        split_name = base_name.split(' ')
        if len(split_name) == 1:
            prenom = split_name[0]
        else:
            prenom = split_name[:-1]
            surname = split_name[-1]

        if surname:
            author_sort_name = ', '.join((surname, ' '.join(prenom)))
        else:
            author_sort_name = prenom

        if modifiers:
            author_sort_name += ', ' + modifiers

        return author_sort_name

    @classmethod
    def _book_key(cls, authors, title):
        """ The key should be hashable and reproducible """
        return (tuple(sorted(authors)), title)


def _get_bak_loc(table_loc):
    return table_loc + '.bak'

def _get_table_loc(db_loc, table_loc):
    return os.path.join(db_loc, table_loc + '.yml')

def _get_schema_db_locs(schema_loc=None, db_loc=None):
    if schema_loc is None:
        schema_loc = read_from_config('schema_loc') 

    if db_loc is None:
        db_loc = read_from_config('database_loc')

    return schema_loc, db_loc

def _get_img_ext(fobj):

    img = Image.open(fobj)
    img_type = img.format
    ext_map = {
        'GIF': '.gif',
        'JPEG': '.jpg',
        'JPEG 2000': '.jpg',
        'PNG': '.png',
        'BMP': '.bmp',
        'TIFF': '.tiff'
    }

    fobj.seek(0)

    if img_type not in ext_map:
        raise UnsupportedImageType('Unsupported image type.')

    return ext_map[img_type]

def _generate_thumbnail(img_loc, thumb_loc):
    img = Image.open(img_loc)
    w, h = img.size
    w_m, h_m = read_from_config('thumb_max')

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


###
# Scripts
def update_database():
    """
    This is a console script for updating the databases from a given path.
    """
    import argparse
    desc = """Runs an update on the content databases."""

    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('path', metavar='P', type=str,
        help='The base path of the content to update the databases with.')

    parser.add_argument('-t', '--type', type=str, default='books',
        help=('The type of content to load from the directories. Options:'
              'b / books : Audiobooks'))

    args = parser.parse_args()

    if not os.path.exists(args.path):
        raise ValueError('Path not found: {}'.format(args.path))

    if args.type in ('b', 'books'):
        updater = BookDatabaseUpdater(args.path)
    else:
        raise ValueError('Unknown type {}'.format(args.type))

    db = load_database()
    updater.update_db(db)
    save_database(db)

###
# Util
class _PBarStub:
    def __call__(self, iterator_):
        return iterator_

###
# Errors
class DuplicateEntryError(ValueError):
    """ Raised when a duplicate entry is found in the database. """
    pass

class UnsupportedImageType(ValueError):
    pass