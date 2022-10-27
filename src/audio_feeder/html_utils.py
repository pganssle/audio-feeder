"""
Module for handling HTML-related operations
"""
import bisect
import io
from html.parser import HTMLParser

from lxml.html import clean as lxclean


class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)

        self.all_data = []
        self.pos_counts = []
        self.data_pos = 0

    def handle_data(self, d):
        self.all_data.append(d)
        pos_start = self.get_docpos()

        self.pos_counts.append((self.data_pos, pos_start))
        self.data_pos += len(d)

    def count_lines(self, html_str):
        """
        It does not seem that there is any way to retrieve the positions of
        tags when parsing HTML in any major library, so we'll need to use a
        two-pass solution instead - first go through each line and get the
        position in the string of the line.
        """
        html_io = io.StringIO(html_str)
        line_positions = {}
        for ii, line in enumerate(html_io):
            line_positions[ii] = html_io.tell() - len(line)

        self.line_positions = line_positions

    def get_docpos(self):
        line_no, offset = self.getpos()

        # Insanely, the line number is a 1-based index.
        line_no -= 1
        return self.line_positions[line_no] + offset

    @classmethod
    def feed_stripper(cls, html_str):
        ts = cls()
        ts.count_lines(html_str)
        ts.feed(html_str)
        ts.close()

        return ts

    def get_data(self):
        return "".join(self.all_data)

    def get_unstripped_pos(self, pos):
        """
        After the feed has been processed.

        :param pos:
            The position of the "stripped" tag

        :return:
            Returns the position in the "unstripped" string.
        """
        # Find out which segment we're in - always get the position to the
        # right of the one we want to be in.
        max_pos = self.pos_counts[-1][1]
        pos_counts_pos = bisect.bisect_right(self.pos_counts, (pos, max_pos))
        pos_counts_pos -= 1

        stripped_base, unstripped_base = self.pos_counts[pos_counts_pos]

        return unstripped_base + (pos - stripped_base)


ALLOWED_TAGS = [
    "a",
    "b",
    "em",
    "i",
    "u",
    "strike",
    "code",
    "blockquote",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ul",
    "ol",
    "p",
    "br",
    "span",
    "strong",
    "tt",
    "pre",
    "s",
    "q",
]


def clean_html(in_str, tag_whitelist=ALLOWED_TAGS):
    """
    Sanitize input HTML. Currently this is a wrapper around
    :func:`lxml.html.clean_html`.

    :param in_str:
        HTML string the sanitize.

    :param tag_whitelist:
        A list of HTML tags to allow. All other tags will be stripped out.

    :return:
        Returns the sanitized string.

    """
    cleaner = lxclean.Cleaner(allow_tags=tag_whitelist, remove_unknown_tags=False)

    # For the moment this is just a wrapper around lxml.html.clean_html
    out_str = cleaner.clean_html(in_str)

    return out_str
