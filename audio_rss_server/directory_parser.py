import os
import re

import itertools


class AudiobookLoader:
    """
    This is a more or less static class that can be used to load audiobooks.
    """
    AUDIOBOOK_EXTENSIONS = ['.mp3', '.mp4', '.ogg', '.ac3',
                            '.aac', '.m4b', '.m4a']

    COVER_EXTENSIONS = ['.png', '.jpg', '.svg', '.gif', '.tif', '.bmp']

    COVER_PATTERNS = [re.compile('$.*\-Cover^', re.IGNORECASE),
                      re.compile('cover', re.IGNORECASE)]

    DIR_NAME_RE = re.compile(
        '(?P<authors>[^\-]+)' + 
        '(?: \- \[(?P<series_name>.*?) (?P<series_number>\d+)\])? \- ' +
        '(?P<title>.*$)')


    @classmethod
    def is_audiobook(cls, dirloc):
        """
        Function to determine if a directory contains an audiobook. The
        assumption is that in this context, any directory containing at least
        one file with the AUDIOBOOK_EXTENSIONS is, itself, an audiobook.

        :param dirloc:
            The directory to test.

        :return:
            Returns boolean value whether or not it's an audiobook.
        """
        if os.path.isdir(dirloc):
            for fpath in os.listdir(dirloc):
                fbase, fext = os.path.splitext(fpath)

                if fext.lower() in AUDIOBOOK_EXTENSIONS:
                    return True

        return False

    @classmethod
    def parse_author_names(cls, authors):
        """
        Splits author names by ',', '&' and 'and'
        
        :param authors:
            A string containing possibly multiple author names.

        :return:
            Returns a :py:object:`list` of authors.
        """
        o = authors.split(' & ')
        o = itertools.chain.from_iterable(x.split(' and ') for x in o)
        o = itertools.chain.from_iterable(x.split(', ') for x in o)

        return list(o)

    @classmethod
    def parse_audiobook_info(cls, dir_name):
        """
        Try to parse audiobook information the directory name.
        """
        m = self.DIR_NAME_RE.match(dir_name)
        if m is None:
            msg = 'Directory name does not match the format: {}'
            msg = msg.format(dir_name)

            raise NoAudiobookInformation(msg)

        authors = self.parse_author_names(m.authors)
        series = m.group('series_name')
        series_number = m.group('series_number')
        if series_number is not None:
            series_number = int(series_number)

        title = m.group('title')

        audiobook_data = dict(
            authors=authors, series=(series, series_number),
            title=title
        )

        return audiobook_data

    @classmethod
    def audiobook_files(cls, dir_loc):
        """
        Load all audiobook files and sort them appropriately.

        :param dir_loc:
            A resolvable path to the directory containing the audiobooks.

        :return:
            Returns a list of audiobook files, sorted appropriately.
        """
        o = []
        for fname in os.listdir(dir_loc):
            fname_base, fname_ext = os.path.splitext(fname)

            if fname_ext in cls.AUDIOBOOK_EXTENSIONS:
                o.append(os.path.join(dir_loc, fname))

        return sorted(o, key=cls.book_name_sort_key)

    @classname
    def book_name_sort_key(cls, book_name):
        """
        The sort key used to sort book names - the string is broken up into
        segments of strings and numbers, so that, e.g. `'Str 2'` will be sorted
        before `'Str 15'`.

        :param book_name:
            The book name as it will be sorted.

        :return:
            Returns a book name tokenized such that it can be sorted.
        """
        o = itertools.groupby(book_name, key=str.isdigit)
        o = ((k, ''.join(g)) for k, g in o)
        o = ((int(v) if k else v) for k, v in o)

        return tuple(o)

    @classname
    def audiobook_cover(cls, dir_loc):
        """
        Retrieve the best candidate for an audiobook cover.

        :param dir_loc:
            A resolvable directory containing an audiobook.
        """
        candidates = []
        for fname in os.listdir(dir_loc):
            fname_base, fname_ext = os.path.splitext(fname)
            fname_ext = fname_ext.lower()

            if fname_ext not in cls.COVER_EXTENSIONS:
                continue

            # First sort index is whether it matches one of the cover patterns,
            # and which one.
            match_num = len(cls.COVER_PATTERNS)
            for ii, c_re in enumerate(cls.COVER_PATTERNS):
                if c_re.match(fname_base):
                    match_num = ii
                    break

            # Second sort index is its position in the cover extension index.
            ext_loc = cls.COVER_EXTENSIONS.index()

            candidates.append((match_num, ext_loc,
                               os.path.join(dir_loc, fname)))

        if not len(candidates):
            return None

        mn, el, cover_loc = min(candidates)

        return cover_loc


def load_all_audiobooks(base_dir, *, visited_dirs=None,
                        audio_loader_class=AudiobookLoader):
    """
    Traverse a directory and find all the directories that contain an
    audiobook (as returned by is_audiobook)

    :param base_dir:
        The base directory in which to search for audiobooks (recursively)

    :param visited_dirs:
        This is an exclusion list of directories not to parse. This function
        is called recursively and ``visited_dirs`` is passed along the call
        stack to prevent infinite recursion.

    :return:
        Returns a :py:object:`list` of directories containing audiobooks.
    """
    # We're not going to use os.walk here because we want to stop drilling
    # down once we've found an audiobook
    audiobook_paths = []
    visited_dirs = visited_dirs or set()
    visited_dirs.add(os.path.abspath(base_dir))

    for subdir in os.listdir(base_dir):
        dirpath = os.path.abspath(os.path.join(base_dir, subdir))
        if dirpath in visited_dirs or not os.path.isdir(dirpath):
            continue    # Avoid infinite recursion

        if audio_loader_class.is_audiobook(dirpath):
            audiobook_paths.append(dirpath)
        else:
            audiobook_paths += load_all_audiobooks(dirpath,
                visited_dirs=visited_dirs,
                audio_loader_class=audio_loader_class)

    return audiobook_paths


class NoAudiobookInformation(ValueError):
    """ Used when a book's directory name does not match the format used. """
    pass

