"""
Page generator
"""
import glob
import math
import os
import string
import warnings

from jinja2 import Template

from .config import get_configuration, read_from_config
from .html_utils import TagStripper
from .object_handler import Book as BaseBook
from .object_handler import Entry as BaseEntry

WORD_CHARS = set(string.ascii_letters + string.digits)


class EntryRenderer:
    FIELDS = (
        "id",
        "rss_url",
        "name",
        "description",
        "cover_img_url",
        "qr_img_url",
        "truncation_point",
    )

    def __init__(self, resolver, entry_templates_config="entry_templates_loc"):
        self.resolver = resolver
        self.entry_templates_loc = read_from_config(entry_templates_config)

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

        out["id"] = entry_obj.id

        # Render the outputs from templates which cascade for use in the later
        # templates.
        type_dict = self.load_type(entry_obj.type)
        data_dict = data_obj.to_dict()

        # Renders the final output author name
        out["author"] = type_dict["author"].render(**data_dict)
        data_dict["author_"] = out["author"]

        # Renders the channel name
        out["name"] = type_dict["name"].render(**data_dict)
        data_dict["name_"] = out["name"]

        out["description"] = type_dict["description"].render(**data_dict)
        out["cover_url"] = None

        for cover_image in entry_obj.cover_images or []:
            try:
                out["cover_url"] = self.resolver.resolve_static(cover_image).url
                break
            except FailedResolutionError:
                pass

        out["rss_url"] = self.resolver.resolve_rss(entry_obj).url
        out["qr_img_url"] = self.resolver.resolve_qr(entry_obj.id, out["rss_url"]).url

        out["truncation_point"] = self.truncation_point(out["description"])

        return out

    def truncation_point(self, description):
        # Strip out all HTML
        stripper = TagStripper.feed_stripper(description)
        raw_chars = stripper.get_data()

        base_truncation_point = read_from_config("base_truncation_point")

        if len(raw_chars) <= base_truncation_point:
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

    def load_type(self, type_name):
        type_cache = getattr(self, "_load_type_cache", {})
        if type_name not in type_cache:
            et_loc = self.entry_templates_loc
            if not os.path.exists(et_loc):
                raise IOError("Entry templates directory does not exist.")

            type_dir = os.path.join(et_loc, type_name)
            if not os.path.exists(type_dir):
                raise IOError(
                    "Type directory templates do not exist: " + " {}".format(type_dir)
                )

            type_dict = {}
            for fname in os.listdir(type_dir):
                fpath = os.path.join(type_dir, fname)
                if not (os.path.isfile(fpath) and fpath.endswith(".tpl")):
                    continue

                tname = os.path.splitext(fname)[0]

                with open(fpath, "r") as f:
                    type_dict[tname] = Template(f.read())

            type_cache[type_name] = type_dict

            self._load_type_cache = type_cache

        return type_cache[type_name]


class NavItem:
    def __init__(self, base_url, display, params=None):
        self.display = display
        self.url = base_url

        if base_url is not None and params is not None:
            self.url += "?" + "&".join(
                "{k}={v}".format(k=k, v=v) for k, v in params.items()
            )

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
        page = sort_args.pop("page")
        per_page = sort_args["perPage"]

        cache_key = tuple(sorted(sort_args.items()))
        if cache_key not in self._page_cache:
            pages = []
            num_pages = math.ceil(self.num_entries / per_page)

            for ii in range(0, num_pages):
                sort_args["page"] = ii

                # The URL is generated on construction, so no need to worry
                # about the fact that we are mutating the same dictionary.
                ni = NavItem(self.base_url, display="{}".format(ii), params=sort_args)

                pages.append(ni)

            self._page_cache[cache_key] = pages
        else:
            pages = self._page_cache[cache_key]

        return [ni if ii != page else ni.display_only() for ii, ni in enumerate(pages)]


class FailedResolutionError(IOError):
    pass
