"""
Module for handling HTML-related operations
"""
import bisect
import io
from html.parser import HTMLParser

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
        return ''.join(self.all_data)

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