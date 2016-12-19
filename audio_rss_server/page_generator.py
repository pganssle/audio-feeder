"""
Page generator
"""
from html.parser import HTMLParser
import string
import glob

from .object_handler import Entry as BaseEntry
from .object_handler import Book as BaseBook
from .config import get_configuration

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
            raise IOError('Type directory templates do not exist.')

        type_dict = {}
        for fname in os.listdir(type_dir):
            fpath = os.path.join(type_dir, fname)
            if not (os.path.isfile(fpath) and fpath.endswith('.tpl')):
                continue

            tname = os.path.splitext(fname)[0]

            with open(fpath, 'r') as f:
                type_dict[tname] = Template(f.read())

        type_cache[type_name] = tname

    return type_cache[type_name]


class _TagStripper(HTMLParser):
    def __init__(self):
        super(TagStripper, self).__init__(convert_charrefs=False)

        self.all_data = []

    def handle_data(self, d):
        self.all_data.append(d)

    def get_data(self):
        return ''.join(self.all_data)

    @classmethod
    def strip_tags(cls, html_str):
        ts = cls()
        ts.feed(html_str)

        return ts.get_data()

class EntryRenderer:
    FIELDS = ('id', 'rss_url', 'name', 'description',
              'cover_img_url', 'qr_img_url', 'truncation_point')

    def __init__(self, url_resolver):
        self.url_resolver = None

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

        # Render the name from template
        type_dict = load_type(entry_obj.type)
        data_dict = data_obj.to_dict()

        out['name'] = type_dict['name'].render(**data_dict)
        out['description'] = type_dict['description'].render(**data_dict)

        for cover_image in entry_obj.cover_images:
            try:
                out['cover_img_url'] = self.url_resolver.resolve_media(cover_image)
                break
            except FailedResolutionError:
                pass

        out['rss_url'] = self.url_resolver.resolve_rss(entry_obj.url)
        out['qr_img_url'] = self.url_resolver.resolve_qr(entry_obj.url)

        out['truncation_point'] = self.truncation_point(out['description'])

        return out

    def truncation_point(self, description):
        # Strip out all HTML
        raw_chars = _TagStripper.strip_tags(description)

        config = get_configuration()
        base_truncation_point = config['base_truncation_point']

        if len(raw_chars) > base_truncation_point:
            return None

        word_offset = 0
        for c_char in raw_chars[base_truncation_point:]:
            if c_char not in WORD_CHARS:
                break

            word_offset += 1

        return base_truncation_point + word_offset









