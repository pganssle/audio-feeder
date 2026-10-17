"""
Page generator
"""

import datetime
import enum
import math
import os
import string
from collections.abc import Callable, Sequence
from typing import Final, TypeVar
from urllib.parse import urlencode, urljoin

import attrs
from jinja2 import Template

from . import resources
from .config import read_from_config
from .html_utils import TagStripper
from .media_renderer import RenderModes

WORD_CHARS = set(string.ascii_letters + string.digits)

# The suffixes of cover thumbnails made by the updater, newest first: older
# versions made PNG thumbnails.
THUMBNAIL_SUFFIXES: Final = ("-thumb.jpg", "-thumb.png")


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
        cover_path = None

        for cover_image in entry_obj.cover_images or []:
            try:
                cover = self.resolver.resolve_static(cover_image)
            except FailedResolutionError:
                continue
            out["cover_url"] = cover.url
            cover_path = cover.path
            break

        # The book list shows the cover's thumbnail, which the updater makes
        # from the best cover image, unless the cover itself is smaller (as
        # small images from metadata sources often are).
        out["thumb_url"] = out["cover_url"]
        if cover_path is not None:
            for suffix in THUMBNAIL_SUFFIXES:
                thumb = self.resolver.resolve_static(
                    os.path.join(
                        read_from_config("cover_cache_path"),
                        f"{entry_obj.id}{suffix}",
                    )
                )
                if thumb.path is not None and thumb.path.exists():
                    if (
                        not cover_path.exists()
                        or thumb.path.stat().st_size < cover_path.stat().st_size
                    ):
                        out["thumb_url"] = thumb.url
                    break

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
            with open(template_loc) as f:
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
                raise FileNotFoundError(
                    f"No entry templates found for type {type_name}"
                )

            type_cache[type_name] = type_dict

            self._load_type_cache = type_cache

        return type_cache[type_name]


class NavKind(enum.StrEnum):
    """The kinds of item in the page navigation."""

    LINK = "link"
    CURRENT = "current"
    GAP = "gap"


class NavItem:
    def __init__(self, base_url, display, params=None, kind: NavKind | None = None):
        self.display = display
        self.url = base_url

        if base_url is not None and params is not None:
            self.url += "?" + urlencode(params, doseq=True)

        if kind is None:
            kind = NavKind.CURRENT if self.url is None else NavKind.LINK
        self.kind = kind

    def display_only(self):
        """
        Makes a "no-url" copy of this navigation item.
        """
        return self.__class__(None, self.display)

    @classmethod
    def gap(cls) -> "NavItem":
        """An ellipsis standing in for the pages left out of the navigation."""
        return cls(None, "\u2026", kind=NavKind.GAP)


def page_window(
    num_pages: int, current: int, *, edge: int = 3, around: int = 1
) -> Sequence[int | None]:
    """The pages to show in the page navigation, with ``None`` for gaps.

    This shows the first and last ``edge`` pages and the pages within
    ``around`` of the current page. Gaps between them are shown as an
    ellipsis, except that a gap of a single page shows that page instead,
    since an ellipsis would take up just as much room.
    """
    shown = sorted(
        {
            *range(min(edge, num_pages)),
            *range(max(current - around, 0), min(current + around + 1, num_pages)),
            *range(max(num_pages - edge, 0), num_pages),
        }
    )

    window: list[int | None] = []
    previous = -1
    for page in shown:
        gap = page - previous - 1
        if gap == 1:
            window.append(page - 1)
        elif gap > 1:
            window.append(None)
        window.append(page)
        previous = page

    return tuple(window)


def windowed_nav(nav_list: Sequence[NavItem], current: int) -> Sequence[NavItem]:
    """The items from a full list of pages to show in the page navigation."""
    return tuple(
        nav_list[page] if page is not None else NavItem.gap()
        for page in page_window(len(nav_list), current)
    )


SortKey = str | datetime.date | None
_T = TypeVar("_T")

MIN_LABEL_PREFIX = 2
MAX_LABEL_PREFIX = 12


@attrs.frozen
class PageRange:
    """The range of sort keys on a page, e.g. ``Aa`` to ``At``.

    ``end`` is ``None`` when the whole page has the same label.
    """

    start: str
    end: str | None = None

    def __str__(self) -> str:
        return self.start if self.end is None else f"{self.start} \u2192 {self.end}"


def page_range_labels(
    entries: Sequence[_T], per_page: int, key: Callable[[_T], SortKey]
) -> Sequence[PageRange]:
    """The range of sort keys on each page, e.g. ``Aa`` to ``At``.

    Text is shortened to the shortest prefix (of at least
    ``MIN_LABEL_PREFIX`` characters) that distinguishes it from the nearest
    different page boundary on either side (usually the other end of its page
    and the adjacent end of the neighbouring page), up to
    ``MAX_LABEL_PREFIX`` characters. Dates leave out what both ends of a page
    have in common, e.g. ``3`` to ``17 Mar 2023``, and pages whose start and
    end have the same label are labelled once.

    ``key`` is only called for the first and last entry on each page, so this
    takes time proportional to the number of pages, not the number of entries.
    """
    # Page boundaries in order, i.e. start_0, end_0, start_1, end_1, ...
    boundaries = [
        key(entries[index])
        for start in range(0, len(entries), per_page)
        for index in (start, min(start + per_page, len(entries)) - 1)
    ]

    # Each boundary is distinguished from the nearest different boundary on
    # either side. Skipping over equal ones (e.g. both ends of a page with a
    # single entry, or an author whose books span several pages) means that
    # equal keys always get the same label.
    before = _nearest_different(boundaries)
    after = _nearest_different(boundaries[::-1])[::-1]
    labels = [
        _boundary_label(value, (previous, following))
        for value, previous, following in zip(boundaries, before, after)
    ]

    return tuple(
        (
            _date_range(start_key, end_key)
            if isinstance(start_key, datetime.date)
            and isinstance(end_key, datetime.date)
            else PageRange(start) if start == end else PageRange(start, end)
        )
        for start_key, end_key, start, end in zip(
            boundaries[::2], boundaries[1::2], labels[::2], labels[1::2]
        )
    )


_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip


def _date_range(start: datetime.date, end: datetime.date) -> PageRange:
    """The range between two dates, leaving out what they have in common.

    Dates are written like ``3 Mar 2023``, which is unambiguous in any
    locale. Ranges within a year give the days, and longer ones only the
    months, e.g. ``3 Mar`` to ``17 Jun 2023``, or ``Dec 2022`` to
    ``Feb 2023``.
    """
    start, end = _as_date(start), _as_date(end)

    def month(date: datetime.date) -> str:
        return _MONTHS[date.month - 1]

    if start == end:
        return PageRange(_format_date(start))
    if start.year != end.year:
        return PageRange(f"{month(start)} {start.year}", f"{month(end)} {end.year}")
    end_label = _format_date(end)
    if start.month == end.month:
        return PageRange(f"{start.day}", end_label)
    return PageRange(f"{start.day} {month(start)}", end_label)


def _format_date(date: datetime.date) -> str:
    return f"{date.day} {_MONTHS[date.month - 1]} {date.year}"


def _as_date(value: datetime.date) -> datetime.date:
    return value.date() if isinstance(value, datetime.datetime) else value


def _nearest_different(values: Sequence[SortKey]) -> Sequence[SortKey]:
    """For each value, the closest earlier value that isn't equal to it."""
    nearest: list[SortKey] = []
    current: SortKey = None
    for index, value in enumerate(values):
        if index and values[index - 1] != value:
            current = values[index - 1]
        nearest.append(current)
    return nearest


def _boundary_label(value: SortKey, neighbours: Sequence[SortKey]) -> str:
    if value is None or value == "":
        return "?"
    if isinstance(value, datetime.date):
        return _format_date(_as_date(value))

    length = max(
        (
            _common_prefix_length(value, neighbour) + 1
            for neighbour in neighbours
            if isinstance(neighbour, str)
        ),
        default=MIN_LABEL_PREFIX,
    )
    length = min(max(length, MIN_LABEL_PREFIX), MAX_LABEL_PREFIX)
    return value[:length].rstrip()


def _common_prefix_length(a: str, b: str) -> int:
    for index, (char_a, char_b) in enumerate(zip(a, b)):
        if char_a != char_b:
            return index
    return min(len(a), len(b))


class NavGenerator:
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
