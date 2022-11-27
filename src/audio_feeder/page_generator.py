"""
Page generator
"""
import math
import os
import string
from urllib.parse import urljoin

from jinja2 import Template

from . import resources
from .config import read_from_config
from .html_utils import TagStripper
from .media_renderer import RenderModes

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
        out["derived_rss_url"] = urljoin(
            self.resolver.base_url, f"rss/derived/{entry_obj.id}-%s.xml"
        )
        out["qr_img_url"] = self.resolver.resolve_qr(entry_obj.id, out["rss_url"]).url

        has_chapter_info = False
        if entry_obj.file_metadata:
            if any(fi.chapters for fi in entry_obj.file_metadata.values()):
                has_chapter_info = True
        out["has_chapter_info"] = has_chapter_info
        out["segmentable"] = has_chapter_info or (
            entry_obj.files and len(entry_obj.files) > 1
        )

        out["rendered_qr_img_urls"] = {
            str(RenderModes.SINGLE_FILE): self.resolver.resolve_qr(
                entry_obj.id,
                (out["derived_rss_url"] % RenderModes.SINGLE_FILE),
                mode=RenderModes.SINGLE_FILE,
            ).url,
        }

        for mode, generate in (
            (RenderModes.SINGLE_FILE, True),
            (RenderModes.CHAPTERS, has_chapter_info),
            (RenderModes.SEGMENTED, out["segmentable"]),
        ):
            if generate:
                out["rendered_qr_img_urls"][str(mode)] = self.resolver.resolve_qr(
                    entry_obj.id,
                    (out["derived_rss_url"] % mode.lower()),
                    mode=mode.lower(),
                ).url

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

    def _get_template(self, loc, name, resource_default):
        template_loc = os.path.join(loc, name)

        if not os.path.exists(template_loc):
            # Load from resource
            return Template(resources.get_text_resource(resource_default, name))
        else:
            with open(template_loc, "rt") as f:
                return Template(f.read())

    def load_type(self, type_name):
        type_cache = getattr(self, "_load_type_cache", {})
        if type_name not in type_cache:
            type_dir = self.entry_templates_loc / type_name
            type_dict = {}
            if type_dir.exists():
                for fpath in type_dir.glob("*.tpl"):
                    type_dict[fpath.stem] = Template(fpath.read_text())
            else:
                resource = f"audio_feeder.data.templates.entry_types.{type_name}"
                for child in resources.get_children(resource):
                    if child.is_dir() or not child.name.endswith(".tpl"):
                        continue
                    fname = os.path.splitext(child.name)[0]
                    type_dict[fname] = Template(child.read_text())

            if not type_dict:
                raise FileNotFounderror(
                    f"No entry templates found for type {type_name}"
                )

            type_cache[type_name] = type_dict

            self._load_type_cache = type_cache

        return type_cache[type_name]


class NavItem:
    def __init__(self, base_url, display, params=None):
        self.display = display
        self.url = base_url

        if base_url is not None and params is not None:
            self.url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

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
                ni = NavItem(self.base_url, display=f"{ii}", params=sort_args)

                pages.append(ni)

            self._page_cache[cache_key] = pages
        else:
            pages = self._page_cache[cache_key]

        return [ni if ii != page else ni.display_only() for ii, ni in enumerate(pages)]


class FailedResolutionError(IOError):
    pass
