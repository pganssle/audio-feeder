{# audio-feeder's logo: a book broadcasting, drawn in a 32x24 box #}
{% set logo_path = "M3 4h9a2 2 0 0 1 2 2v14H5a2 2 0 0 1-2-2zm0 14a2 2 0 0 1 2-2h9M18 9a4 4 0 0 1 0 6m3-9a8.5 8.5 0 0 1 0 12m3-15a13 13 0 0 1 0 18" %}
{# The colour scheme chosen in the menu, if the theme has both #}
{% set forced_scheme = scheme if theme_has_schemes else none %}
<!DOCTYPE html>
<html lang="en"{% if forced_scheme %} data-scheme="{{ forced_scheme }}"{% endif %}>
<head>
<meta charset="utf-8">
<title>{% block title %}{{ pagetitle }}{% endblock %}</title>
<meta name="description" content="List of content served">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="{{ forced_scheme or "light dark" }}">
{% for stylesheet_link in stylesheet_links or () %}
<link rel="stylesheet" href="{{ stylesheet_link }}">
{% endfor %}
{% if theme_link %}
<link rel="stylesheet" href="{{ theme_link }}">
{% endif %}
{% if site_logo %}
<link rel="icon" href="{{ site_logo|e }}">
{% elif site_logo is none %}
{# The logo, in the colours of the top bar's text in light and dark mode #}
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{{ ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -4 32 32" fill="none" stroke="#353535" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><style>@media(prefers-color-scheme:dark){*{stroke:#e5eaeb}}</style><path d="' ~ logo_path ~ '"/></svg>')|urlencode }}">
{% endif %}
</head>
<body>
{# Icons, used with <svg class="icon"><use href="#i-..."/></svg> #}
<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">
<symbol id="i-menu" viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18"/></symbol>
<symbol id="i-sort" viewBox="0 0 24 24"><path d="M3 6h10M3 12h7M3 18h4M18 4v16m-4-4 4 4 4-4"/></symbol>
<symbol id="i-close" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></symbol>
<symbol id="i-down" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
<symbol id="i-logo" viewBox="0 0 32 24"><path d="{{ logo_path }}"/></symbol>
<symbol id="i-github" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></symbol>
<symbol id="i-warn" viewBox="0 0 24 24"><path d="M12 3.5 2.5 20h19zM12 10v4.5m0 3v.01"/></symbol>
<symbol id="i-qr" viewBox="0 0 24 24"><path d="M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h2v2h-2zm4 4h2v2h-2zm-4 4h0m4-8h2v2h-2zm-4 4h2v2h-2z"/></symbol>
</svg>
<script>
/* Including and excluding the same folder or tag are mutually exclusive */
document.addEventListener("change", (event) => {
    const box = event.target;
    if (box.matches(".inc, .exc") && box.checked) {
        for (const other of box.parentElement.querySelectorAll(":scope > input")) {
            other.checked = other === box;
        }
    }
});
</script>
{% block topnav %}
{% macro toggle_pair(include_name, exclude_name, value, label, included, excluded) -%}
<input type="checkbox" name="{{ include_name }}" value="{{ value|e }}"{{ " checked" if included else "" }} class="inc" aria-label="Include {{ label|e }}"><input type="checkbox" name="{{ exclude_name }}" value="{{ value|e }}"{{ " checked" if excluded else "" }} class="exc" aria-label="Exclude {{ label|e }}">
{%- endmacro %}
{% macro tag_row(tag, count) -%}
<li class="drawer_row">{{ toggle_pair("tag", "notTag", tag, tag, tag in entry_filter.tags, tag in entry_filter.not_tags) }}<span class="row_name">{{ tag|e }}</span><span class="row_count">{{ count }}</span></li>
{%- endmacro %}
<header class="topnav">
<div class="topnav_inner">
<button type="button" class="topnav-button topnav-menu" popovertarget="browse-drawer" aria-label="Menu"><svg class="icon"><use href="#i-menu"/></svg><span class="button_label">Menu</span>{% if filter_count %}<span class="filter_count">{{ filter_count }}</span>{% endif %}</button>
<a class="wordmark" href="/books">{% if site_logo is none %}<svg class="icon logo" aria-hidden="true"><use href="#i-logo"/></svg>{% elif site_logo %}<img class="logo" src="{{ site_logo|e }}" alt="">{% endif %}<span>{{ site_title|e }}</span></a>
<button type="button" class="topnav-button" popovertarget="sort-menu" aria-label="Sort"><span class="button_label">Sort</span><svg class="icon"><use href="#i-sort"/></svg></button>
</div>
<form action="/books" class="browse_drawer" id="browse-drawer" popover>
{% for param_name, param_value in sort_params %}
<input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
{% endfor %}
<div class="drawer_header">
<h2>Menu</h2>
<button type="button" class="topnav-button drawer_close" popovertarget="browse-drawer" popovertargetaction="hide" aria-label="Close"><svg class="icon"><use href="#i-close"/></svg></button>
</div>
{# The theme and colour scheme have their own form (below), since forms can't be nested #}
<div class="appearance" role="group" aria-label="Appearance">
<label for="theme-select">Theme</label>
<select id="theme-select" name="theme" form="theme-form">
<option value="default"{{ " selected" if not theme else "" }}>Classic</option>
{% for theme_name, theme_label in themes %}
<option value="{{ theme_name|e }}"{{ " selected" if theme_name == theme else "" }}>{{ theme_label|e }}</option>
{% endfor %}
</select>
{% if theme_has_schemes %}
<fieldset class="scheme_toggle">
<legend>Colour scheme</legend>
{% for value in ("light", "dark", "system") %}
<input type="radio" id="scheme-{{ value }}" name="scheme" value="{{ value }}" form="theme-form"{{ " checked" if value == (scheme or "system") else "" }}><label for="scheme-{{ value }}">{{ value|capitalize }}</label>
{% endfor %}
</fieldset>
{% endif %}
<button type="submit" form="theme-form">Use</button>
</div>
<div class="browse_heading">
<h3>Browse</h3>
<p class="toggle_legend"><span class="inc_key">+</span> include <span class="exc_key">&minus;</span> exclude</p>
</div>
{% if folder_tree or extra_folders %}
<details class="drawer_section" open>
<summary>Folders</summary>
<ul class="folder_tree drawer_section_body">
{% for extra in extra_folders %}
<li><div class="drawer_row leaf">{{ toggle_pair("folder", "notFolder", extra.folder.as_posix(), extra.folder.as_posix(), extra.folder in entry_filter.folders, extra.folder in entry_filter.not_folders) }}<span class="row_name">{{ extra.label|e }}</span><span class="row_count">{{ extra.count }}</span></div></li>
{% endfor %}
{% for node in folder_tree recursive %}
{% set toggles = toggle_pair("folder", "notFolder", node.folder.as_posix(), node.folder.as_posix(), node.folder in entry_filter.folders, node.folder in entry_filter.not_folders) %}
{% if node.children %}
<li><details{{ " open" if node.folder in open_folders else "" }}><summary class="drawer_row">{{ toggles }}<span class="row_name">{{ node.label|e }}</span><span class="row_count">{{ node.count }}</span></summary><ul>{{ loop(node.children) }}</ul></details></li>
{% else %}
<li><div class="drawer_row leaf">{{ toggles }}<span class="row_name">{{ node.label|e }}</span><span class="row_count">{{ node.count }}</span></div></li>
{% endif %}
{% endfor %}
</ul>
</details>
{% endif %}
<details class="drawer_section" open>
<summary>Filters</summary>
<div class="drawer_section_body fields">
<label for="filter-language">Language</label>
<select id="filter-language" name="language">
<option value="">Any</option>
{% for language, count in facets.languages %}
<option value="{{ language|e }}"{{ " selected" if language == entry_filter.language else "" }}>{{ language|e }} ({{ count }})</option>
{% endfor %}
</select>
<label for="filter-author">Author</label>
<input type="search" id="filter-author" name="author" value="{{ filter_values.get("author", "")|e }}">
<label for="filter-added-since">Added since</label>
<input type="date" id="filter-added-since" name="addedSince" value="{{ filter_values.get("addedSince", "")|e }}">
<label for="filter-added-before">Added before</label>
<input type="date" id="filter-added-before" name="addedBefore" value="{{ filter_values.get("addedBefore", "")|e }}">
</div>
</details>
{% if tag_choices %}
<details class="drawer_section"{{ " open" if entry_filter.tags or entry_filter.not_tags else "" }}>
<summary>Tags</summary>
<div class="drawer_section_body">
<p class="tag_match">Show books with
<label><input type="radio" name="tagMatch" value=""{{ " checked" if entry_filter.tag_match == "any" else "" }}> any</label>
<label><input type="radio" name="tagMatch" value="all"{{ " checked" if entry_filter.tag_match == "all" else "" }}> all</label>
of the included tags</p>
<ul class="tag_list">
{% for tag, count in tag_choices[:15] %}
{{ tag_row(tag, count) }}
{% endfor %}
</ul>
{% if tag_choices|length > 15 %}
<details class="more_tags">
<summary>All {{ tag_choices|length }} tags</summary>
<ul class="tag_list">
{% for tag, count in tag_choices[15:] %}
{{ tag_row(tag, count) }}
{% endfor %}
</ul>
</details>
{% endif %}
</div>
</details>
{% endif %}
<div class="drawer_footer">
<a class="drawer_clear" href="{{ clear_filters_url|e }}">Clear filters</a>
<button type="submit" class="primary">Apply</button>
</div>
</form>
<form action="/books" id="theme-form" hidden>
{% for param_name, param_value in filter_param_pairs %}
<input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
{% endfor %}
{% for param_name, param_value in sort_params %}
<input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
{% endfor %}
</form>
<form action="/books" class="sort_menu" id="sort-menu" popover>
{% for param_name, param_value in filter_param_pairs %}
<input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
{% endfor %}
<div class="fields">
<label for="sort-dropdown">Sort by</label>
<select id="sort-dropdown" name="orderBy">
{% for sort_label, sort_value in sort_options.items() %}
<option value="{{ sort_value }}"{{ " selected" if sort_value == sort_args["orderBy"] else "" }}>{{ sort_label }}</option>
{% endfor %}
</select>
<label for="sort-ascending">Direction</label>
<select id="sort-ascending" name="sortAscending">
<option value="True"{{ " selected" if sort_args["sortAscending"] else "" }}>Ascending</option>
<option value="False"{{ " selected" if not sort_args["sortAscending"] else "" }}>Descending</option>
</select>
<label for="per-page">Per page</label>
<input type="number" id="per-page" name="perPage" min="1" value="{{ sort_args["perPage"] }}">
</div>
<button type="submit" class="primary">Apply</button>
</form>
</header>
{% endblock %}
<main class="maintable">
{% block breadcrumbs %}
{% if breadcrumbs %}
<nav class="breadcrumbs" aria-label="Folder">
{% for crumb in breadcrumbs %}
{% if not crumb.url is sameas none %}<a class="breadcrumb" href="{{ crumb.url|e }}">{{ crumb.name|e }}</a>{% else %}<span class="breadcrumb current_folder">{{ crumb.name|e }}</span>{% endif %}
{% if not loop.last %}<span class="breadcrumb_separator" aria-hidden="true">/</span>{% endif %}
{% endfor %}
</nav>
{% endif %}
{% endblock %}
<div class="pager">
{% block navbar %}
{% macro nav_arrow(url, text, label) -%}
{% if not url is sameas none %}<a class="nav_arrow" href="{{ url }}" aria-label="{{ label }}">{{ text }}</a>{% else %}<span class="nav_arrow" aria-hidden="true">{{ text }}</span>{% endif %}
{%- endmacro %}
{% if nav_list|length > 1 %}
<nav class="navbar" aria-label="Pages">
{{ nav_arrow(first_index, "«", "First page") }}{{ nav_arrow(prev_index, "‹", "Previous page") }}
<span class="nav_links">
{% block navlist %}
{% for nav_item in nav_list %}
{% if nav_item.kind == "link" %}<a class="nav_link" href="{{ nav_item.url }}">{{ nav_item.display }}</a>{% elif nav_item.kind == "gap" %}<span class="nav_gap" aria-hidden="true">{{ nav_item.display }}</span>{% else %}<span class="nav_current" aria-current="page">{{ nav_item.display }}</span>{% endif %}
{% endfor %}
{% endblock %}
</span>
{{ nav_arrow(next_index, "›", "Next page") }}{{ nav_arrow(final_index, "»", "Last page") }}
</nav>
{% endif %}
{% endblock %}
{# The page jump menu is only above the list, since the navbar below the
   list would repeat every page #}
{% block pagejump %}
{% if page_options|length > 1 %}
{% macro page_range(range) -%}
{{ range.start|e }}{% if not range.end is sameas none %}<i>{{ range.end|e }}</i>{% endif %}
{%- endmacro %}
<button type="button" class="page_jump_button" popovertarget="page-jump" aria-label="Jump to page"><span>{{ page_range(page_options[current_page][1]) }}</span><svg class="icon"><use href="#i-down"/></svg></button>
<form class="page_jump" id="page-jump" method="get" action="/books" popover>
{% for param_name, param_value in page_jump_params %}
<input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
{% endfor %}
<h2>Jump to page</h2>
<div class="page_list">
{% for number, range in page_options %}
<button name="page" value="{{ loop.index0 }}"{% if loop.index0 == current_page %} aria-current="page"{% endif %}><b>{{ number }}</b><span>{{ page_range(range) }}</span></button>
{% endfor %}
</div>
</form>
{% endif %}
{% endblock %}
</div>
{% block mainlist %}
{% macro feed(entry, label, url, qr_id, qr_url, warning=none) -%}
<li><a href="{{ url }}">{{ label }}{% if warning %}<svg class="icon feed_warning" role="img"><title>{{ warning }}</title><use href="#i-warn"/></svg>{% endif %}</a><button type="button" class="qr_button" popovertarget="{{ qr_id }}" aria-label="QR code for the {{ label|lower }} feed"><svg class="icon"><use href="#i-qr"/></svg></button><div class="modal-window" id="{{ qr_id }}" popover><img src="{{ qr_url }}" class="qr_img" loading="lazy" alt="QR code for the {{ label|lower }} feed of {{ entry.title|e }}"><p>{{ entry.title|e }} &middot; {{ label }}</p></div></li>
{%- endmacro %}
{% if not entries %}
<p class="no_results">
There's nothing here.
{% if filter_count %}Maybe your filters are too narrow? <a href="{{ clear_filters_url|e }}">Clear filters</a>{% endif %}
</p>
{% endif %}
{% for entry in entries %}
<article class="entry_row" id="e{{ entry.id }}" data-id="{{ entry.id }}" style="--n: {{ entry.id % 360 }}">
<div class="cover_col">
{% if not entry.thumb_url is sameas none %}
<img src="{{ entry.thumb_url }}" class="cover_img" alt=""{% if loop.index > 4 %} loading="lazy"{% endif %} decoding="async">
{% else %}
<div class="cover_img cover_blank" aria-hidden="true"><span>{{ entry.title }}</span><svg class="icon cover_mark"><use href="#i-logo"/></svg></div>
{% endif %}
</div>
<div class="entry_body">
<h2 class="entry_title"><span class="book_title">{{ entry.title }}</span> <span class="book_author">{{ entry.author }}</span></h2>
{{ entry.meta }}
<ul class="feeds">
{{ feed(entry, "Original", entry.rss_url, "qr-%s" % entry.id, entry.qr_img_url) }}
{{ feed(entry, "Single file", entry.derived_rss_url % 'singlefile', "qr-%s-SINGLEFILE" % entry.id, entry.rendered_qr_img_urls['SINGLEFILE']) }}
{% if entry.has_chapter_info %}
{# Files with broken chapter information are one chapter each #}
{{ feed(entry, "Chapters", entry.derived_rss_url % 'chapters', "qr-%s-CHAPTERS" % entry.id, entry.rendered_qr_img_urls['CHAPTERS'], warning="Some of this book's chapter information is broken, so those files are one chapter each" if entry.broken_chapter_info) }}
{% endif %}
{% if entry.segmentable %}
{{ feed(entry, "Segmented", entry.derived_rss_url % 'segmented', "qr-%s-SEGMENTED" % entry.id, entry.rendered_qr_img_urls['SEGMENTED']) }}
{% endif %}
</ul>
<div class="description">
{% if entry.truncation_point <= 0 %}{{ entry.description }}{% else %}{{ entry.description[0:entry.truncation_point] }}<details class="read_more"><summary>&hellip;&nbsp;more</summary>{{ entry.description[entry.truncation_point:] }}</details>{% endif %}
</div>
</div>
</article>
{% endfor %}
{% endblock %}
{{ self.navbar() }}
</main>
{% block botnav %}
<footer class="site_footer">
<a href="https://github.com/pganssle/audio-feeder"><svg class="icon github" aria-hidden="true"><use href="#i-github"/></svg>audio-feeder</a>
</footer>
{% endblock %}
</body>
</html>
