"""
Page generator
"""
from html.parser import HTMLParser
import bisect
import glob
import io
import math
import os
import string

from .object_handler import Entry as BaseEntry
from .object_handler import Book as BaseBook
from .config import get_configuration, read_from_config


import qrcode
from qrcode.image.svg import SvgImage
import warnings

from jinja2 import Template

WORD_CHARS = set(string.ascii_letters + string.digits)


def load_type(type_name):
    type_cache = getattr(load_type, 'type_cache', {})
    if type_name not in type_cache:
        config = get_configuration()
        et_loc = config['entry_templates_loc']
        if not os.path.exists(et_loc):
            raise IOError('Entry templates directory does not exist.')

        type_dir = os.path.join(et_loc, type_name)
        if not os.path.exists(type_dir):
            raise IOError('Type directory templates do not exist: ' +
                ' {}'.format(type_dir))

        type_dict = {}
        for fname in os.listdir(type_dir):
            fpath = os.path.join(type_dir, fname)
            if not (os.path.isfile(fpath) and fpath.endswith('.tpl')):
                continue

            tname = os.path.splitext(fname)[0]

            with open(fpath, 'r') as f:
                type_dict[tname] = Template(f.read())

        type_cache[type_name] = type_dict

        load_type.type_cache = type_cache

    return type_cache[type_name]


class _TagStripper(HTMLParser):
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


class QRGenerator:
    """
    Class for generating QR codes on demand
    """
    def __init__(self, fmt='svg', version=None, **qr_options):
        if fmt == 'svg':
            image_factory = SvgImage
            self.extension = '.svg'
        elif fmt == 'png':
            image_factory = None
            self.extension = '.png'

        qr_options['version'] = version
        qr_options['image_factory'] = image_factory
        self.qr_options = qr_options

    def generate_qr(self, data, save_path):
        img = qrcode.make(data, **self.qr_options)
        img.save(save_path)

    def get_save_path(self, save_dir, save_name):
        save_path = os.path.join(save_dir, save_name + self.extension)

        return save_path


class UrlResolver:
    def __init__(self, base_url, base_path,
                 rss_protocol='http',
                 img_protocol='http',
                 audio_protocol='http',
                 qr_generator=None):
        self.base_url = base_url
        self.base_path = base_path
        self.rss_protocol = rss_protocol
        self.img_protocol = img_protocol
        self.audio_protocol = audio_protocol

        self.static_url = read_from_config('static_media_url')
        self.static_path = read_from_config('static_media_path')

        if qr_generator is None:
            self.qr_generator = QRGenerator()

    def resolve_media(self, url_tail):
        return self.resolve_url(self.img_protocol,
                                self.base_url,
                                url_tail)

    def resolve_rss(self, entry_obj, tail=None):
        kwargs = dict(id=entry_obj.id, table=entry_obj.table, tail=tail or '')

        url_tail = read_from_config('rss_feed_urls')
        url_tail = url_tail.format(**kwargs)
        return self.resolve_url(self.rss_protocol,
                                self.base_url,
                                url_tail,
                                validate=False)

    def resolve_qr(self, e_id, url):
        # Check the QR cache - for the moment, we're going to assume that once
        # a QR code is generated, it's accurate until it's deleted. Eventually
        # it might be nice to allow multiple caches.
        qr_cache = os.path.join(self.static_path,
                                read_from_config('qr_cache_path'))

        rel_save_dir = self.resolve_relpath(qr_cache)
        rel_save_path = self.qr_generator.get_save_path(rel_save_dir,
                                                        '{}'.format(e_id))

        save_path = os.path.join(self.base_path, rel_save_path)
        if not os.path.exists(save_path):
            self.qr_generator.generate_qr(url, save_path)

        return self.resolve_url(protocol=self.img_protocol,
                                base_url=self.static_url,
                                url_tail=rel_save_path)

    def resolve_url(self, protocol, base_url, url_tail, validate=False):
        relpath = self.resolve_relpath(url_tail)
        if validate:
            self.validate_path(relpath)

        url_base = '{protocol}://{base_url}'.format(protocol=protocol,
                                                    base_url=base_url)

        return os.path.join(url_base, url_tail)

    def resolve_relpath(self, path):
        return os.path.relpath(path, self.base_path)

    def validate_path(self, relpath):
        if not os.path.exists(os.path.join(self.base_path, relpath)):
            raise FailedResolutionError


class EntryRenderer:
    FIELDS = ('id', 'rss_url', 'name', 'description',
              'cover_img_url', 'qr_img_url', 'truncation_point')

    def __init__(self, url_resolver):
        self.url_resolver = url_resolver

    def render(self, entry_obj, data_obj):
        """
        Creates a rendered entry, from the entry object and its corresponding
        data object.

        :param entry_obj:
            An :class:`object_handler.Entry` object.

        :param data_obj:
            A data object like a :class:`object_handler.Book`.

        """
        out = {k: None for k in self.FIELDS}

        out['id'] = entry_obj.id

        # Render the outputs from templates which cascade for use in the later
        # templates.
        type_dict = load_type(entry_obj.type)
        data_dict = data_obj.to_dict()

        # Renders the final output author name
        out['author'] = type_dict['author'].render(**data_dict)
        data_dict['author_'] = out['author']

        # Renders the channel name
        out['name'] = type_dict['name'].render(**data_dict)
        data_dict['name_'] = out['name']

        out['description'] = type_dict['description'].render(**data_dict)
        out['cover_url'] = None

        for cover_image in entry_obj.cover_images or []:
            try:
                out['cover_url'] = self.url_resolver.resolve_media(cover_image)
                break
            except FailedResolutionError:
                pass

        out['rss_url'] = self.url_resolver.resolve_rss(entry_obj)
        out['qr_img_url'] = self.url_resolver.resolve_qr(entry_obj.id,
                                                         out['rss_url'])

        out['truncation_point'] = self.truncation_point(out['description'])

        return out

    def truncation_point(self, description):
        # Strip out all HTML
        stripper = _TagStripper.feed_stripper(description)
        raw_chars = stripper.get_data()

        config = get_configuration()
        base_truncation_point = config['base_truncation_point']

        if len(raw_chars) > base_truncation_point:
            return -1

        word_offset = 0
        for c_char in raw_chars[base_truncation_point:]:
            if c_char not in WORD_CHARS:
                break

            word_offset += 1

        truncation_point = base_truncation_point + word_offset

        # Now get the position in the "unstripped" string
        orig_pos = stripper.get_unstripped_pos(truncation_point)

        return orig_pos


class NavItem:
    def __init__(self, base_url, display, params=None):
        self.display = display
        self.url = base_url

        if base_url is not None and params is not None:
            self.url += '?' + '&'.join('{k}={v}'.format(k=k, v=v)
                                       for k, v in params.items())

    def display_only(self):
        """
        Makes a "no-url" copy of this navigation item.
        """
        return self.__class__(None, self.display)


class NavGenerator:
    # For now, there won't be any truncation of the list.
    # TODO: Add list truncation
    def __init__(self, num_entries, base_url):
        self.num_entries = num_entries
        self.base_url = base_url
        self._page_cache = {}

    def get_pages(self, sort_args):
        sort_args = sort_args.copy()
        page = sort_args.pop('page')
        per_page = sort_args['perPage']

        cache_key = tuple(sorted(sort_args.items()))
        if cache_key not in self._page_cache:
            pages = []
            num_pages = math.ceil(self.num_entries / per_page)

            for ii in range(0, num_pages):
                sort_args['page'] = ii

                # The URL is generated on construction, so no need to worry
                # about the fact that we are mutating the same dictionary.
                ni = NavItem(self.base_url, display='{}'.format(ii),
                             params=sort_args)

                pages.append(ni)

            self._page_cache[cache_key] = pages
        else:
            pages = self._page_cache[cache_key]

        return [ni if ii != page else ni.display_only()
                for ii, ni in enumerate(pages)]


class FailedResolutionError(IOError):
    pass

