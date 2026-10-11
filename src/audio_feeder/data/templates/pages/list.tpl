<!DOCTYPE html>
<html lang="en">
<head>
    <title>{% block title %}{{ pagetitle }}{% endblock %}</title>
    <meta name="description" content="List of content served">

    {% if not stylesheet_links is sameas none %}
    {% for stylesheet_link in stylesheet_links %}
    <link rel="stylesheet" href="{{stylesheet_link}}">
    {% endfor %}
    {% endif %}

    {% if not favicon is sameas none %}
    <link rel="icon" type="{{favicon.type}}" href="{{favicon.url}}">
    {% endif %}

</head>
<body>
<script>
/* Initialize all expanders */
function init_elements() {
    hidden_descs = document.querySelectorAll("span.hidden_description_section");
    for (var i = 0; i < hidden_descs.length; i++) {
        el = hidden_descs[i];
        el.style.display = "none";
    }
}

window.onload = init_elements;

/* Including and excluding the same folder or tag are mutually exclusive */
document.addEventListener("change", (event) => {
    const pair = event.target.closest(".toggle_pair");
    if (pair !== null && event.target.checked) {
        for (const box of pair.querySelectorAll("input")) {
            box.checked = box === event.target;
        }
    }
});

function toggle_hidden(entry_id) {
    target = document.querySelector("a.read_more_link#e" + entry_id);
    selection_query = "span.hidden_description_section#e" + entry_id;
    desc_section = document.querySelector(selection_query);
    ellipsis = document.querySelector('span.expander_ellipsis#e' + entry_id);

    if (desc_section.style.display == "none") {
        // Currently hidden, toggling to visible
        desc_section.style.display = "inline";
        ellipsis.style.display = "none";
        target.innerHTML = "(Collapse)";
    } else {
        desc_section.style.display = "none";
        target.innerHTML = "(Read More)";
        ellipsis.style.display = "inline";
    }
}

// Modal opening function
const qr_img_urls = new Map([
{% for entry in entries %}
    [ {{entry.id}} + null, "{{ entry.qr_img_url }}" ],
    [ {{entry.id}} + "SINGLEFILE", "{{ entry.rendered_qr_img_urls['SINGLEFILE'] }}"],
    {% if entry.has_chapter_info %}
        [ {{entry.id}} + "CHAPTERS", "{{ entry.rendered_qr_img_urls['CHAPTERS'] }}"],
    {% endif %}
    {% if entry.segmentable %}
        [ {{entry.id}} + "SEGMENTED", "{{ entry.rendered_qr_img_urls['SEGMENTED'] }}"],
    {% endif %}
{% endfor %}
]);
let modal_divs = new Map();
let active_modal = null;
const qr_container = document.querySelector("body");
let overlay = null;

function get_overlay() {
    if (overlay === null) {
        overlay = document.querySelector("#div-overlay");
    }
    return overlay;
}

function make_qr_modal(entry_id, mode=null) {
    const modal_div = document.createElement("div");
    let attribute_id = "qr-" + entry_id;
    if (mode !== null) {
        attribute_id = attribute_id + "-" + mode;
    }
    modal_div.setAttribute("id", attribute_id);
    modal_div.setAttribute("class", "modal-window");

    const qr_img = document.createElement("img");
    const img_key = entry_id + mode;

    qr_img.setAttribute("src", qr_img_urls.get(img_key));
    qr_img.setAttribute("class", "qr_img");

    modal_div.appendChild(qr_img);
    qr_container.appendChild(modal_div);
    return modal_div;
}

function toggle_modal(entry_id, mode=null) {
    if (active_modal === null) {
        active_modal = [entry_id, mode];
    } else {
        active_modal = null;
    }

    const entry_key = entry_id + mode;
    let modal_div;
    if (!modal_divs.has(entry_key)) {
        modal_div = make_qr_modal(entry_id, mode);
        modal_divs.set(entry_key, modal_div);
    } else {
        modal_div = modal_divs.get(entry_key);
    }

    get_overlay().classList.toggle("overlay-active");
    modal_div.classList.toggle("show-modal");
}


window.addEventListener("click", (event) => { if (event.target === get_overlay() && active_modal !== null) {toggle_modal(...active_modal);}});
</script>

{% block topnav %}
{% macro toggle_pair(include_name, exclude_name, value, label, included, excluded) -%}
<span class="toggle_pair">
    <label class="toggle include" title="Include {{ label|e }}"><input type="checkbox" name="{{ include_name }}" value="{{ value|e }}"{{ " checked" if included else "" }}><span aria-hidden="true">+</span><span class="visually_hidden">Include {{ label|e }}</span></label>
    <label class="toggle exclude" title="Exclude {{ label|e }}"><input type="checkbox" name="{{ exclude_name }}" value="{{ value|e }}"{{ " checked" if excluded else "" }}><span aria-hidden="true">&minus;</span><span class="visually_hidden">Exclude {{ label|e }}</span></label>
</span>
{%- endmacro %}
{% macro tag_row(tag, count) -%}
<li class="drawer_row">
    {{ toggle_pair("tag", "notTag", tag, tag, tag in entry_filter.tags, tag in entry_filter.not_tags) }}
    <span class="row_name">{{ tag|e }}</span>
    <span class="row_count">{{ count }}</span>
</li>
{%- endmacro %}
<div class="topnav">
    <!-- TODO: Implement login
    <a href="/login"><i class="fa fa-user topnav-icon"></i></a>
    -->
    <button type="button" class="topnav-icon topnav-button topnav-menu" popovertarget="browse-drawer"
            title="Browse and filter" aria-label="Browse and filter"><i class="fa fa-bars"></i>{% if filter_count %}<span class="filter_count">{{ filter_count }}</span>{% endif %}</button>
    <form action="/books" class="browse_drawer" id="browse-drawer" popover>
        {% for param_name, param_value in sort_params %}
        <input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
        {% endfor %}
        <div class="drawer_header">
            <h2>Browse</h2>
            <button type="button" class="topnav-button drawer_close" popovertarget="browse-drawer"
                    popovertargetaction="hide" title="Close" aria-label="Close">&times;</button>
        </div>
        {% if folder_tree or extra_folders %}
        <details class="drawer_section" open>
            <summary>Folders</summary>
            <ul class="folder_tree drawer_section_body">
            {% for extra in extra_folders %}
                <li>
                    <div class="drawer_row leaf">{{ toggle_pair("folder", "notFolder", extra.folder.as_posix(), extra.folder.as_posix(), extra.folder in entry_filter.folders, extra.folder in entry_filter.not_folders) }}<span class="row_name">{{ extra.folder.as_posix()|e }}</span><span class="row_count">{{ extra.count }}</span></div>
                </li>
            {% endfor %}
            {% for node in folder_tree recursive %}
                <li>
                {% set toggles = toggle_pair("folder", "notFolder", node.folder.as_posix(), node.folder.as_posix(), node.folder in entry_filter.folders, node.folder in entry_filter.not_folders) %}
                {% if node.children %}
                    <details{{ " open" if node.folder in open_folders else "" }}>
                        <summary class="drawer_row">{{ toggles }}<span class="row_name">{{ node.label|e }}</span><span class="row_count">{{ node.count }}</span></summary>
                        <ul>{{ loop(node.children) }}</ul>
                    </details>
                {% else %}
                    <div class="drawer_row leaf">{{ toggles }}<span class="row_name">{{ node.label|e }}</span><span class="row_count">{{ node.count }}</span></div>
                {% endif %}
                </li>
            {% endfor %}
            </ul>
        </details>
        {% endif %}
        <details class="drawer_section" open>
            <summary>Filters</summary>
            <div class="drawer_section_body">
                <div class="options-line">
                    <label for="filter-language" class="topnav-label">Language:</label>
                    <select id="filter-language" class="topnav-form" name="language">
                        <option value="">Any</option>
                        {% for language, count in facets.languages %}
                        <option value="{{ language|e }}"{{ " selected" if language == entry_filter.language else "" }}>{{ language|e }} ({{ count }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="options-line">
                    <label for="filter-author" class="topnav-label">Author:</label>
                    <input type="search" class="topnav-form" id="filter-author" name="author"
                           value="{{ filter_values.get("author", "")|e }}">
                </div>
                <div class="options-line">
                    <label for="filter-added-since" class="topnav-label">Added since:</label>
                    <input type="date" class="topnav-form" id="filter-added-since" name="addedSince"
                           value="{{ filter_values.get("addedSince", "")|e }}">
                </div>
                <div class="options-line">
                    <label for="filter-added-before" class="topnav-label">Added before:</label>
                    <input type="date" class="topnav-form" id="filter-added-before" name="addedBefore"
                           value="{{ filter_values.get("addedBefore", "")|e }}">
                </div>
            </div>
        </details>
        {% if tag_choices %}
        <details class="drawer_section"{{ " open" if entry_filter.tags or entry_filter.not_tags else "" }}>
            <summary>Tags</summary>
            <div class="drawer_section_body">
                <div class="tag_match">
                    Show books with
                    <label><input type="radio" name="tagMatch" value=""{{ " checked" if entry_filter.tag_match == "any" else "" }}> any</label>
                    <label><input type="radio" name="tagMatch" value="all"{{ " checked" if entry_filter.tag_match == "all" else "" }}> all</label>
                    of the included tags
                </div>
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
            <a class="topnav-form drawer_clear" href="{{ clear_filters_url|e }}">Clear filters</a>
            <button type="submit" class="topnav-form">Apply</button>
        </div>
    </form>
    <button type="button" class="topnav-icon topnav-button" popovertarget="sort-menu"
            title="Sort" aria-label="Sort"><i class="fa fa-arrow-down-wide-short"></i></button>
    <form action="/books" class="sort_menu" id="sort-menu" popover>
        {% for param_name, param_value in filter_param_pairs %}
        <input type="hidden" name="{{ param_name|e }}" value="{{ param_value|e }}">
        {% endfor %}
        <div class="options-line">
            <label for="sort-dropdown" class="topnav-label">Sort order:</label>
            <select id="sort-dropdown" class="topnav-form" name="orderBy">
                {% for sort_label, sort_value in sort_options.items() %}
                <option value="{{ sort_value }}"{{" selected" if sort_value == sort_args["orderBy"] else ""}}>
                    {{ sort_label }}
                 </option>
                {% endfor %}
            </select>
        </div>
        <div class="options-line">
            <label for="sort-ascending" class="topnav-label">Direction:</label>
            <select id="sort-ascending" name="sortAscending" class="topnav-form">
                <option value="True"{{ " selected" if sort_args["sortAscending"] else "" }}>Ascending</option>
                <option value="False"{{ " selected" if not sort_args["sortAscending"] else "" }}>Descending</option>
            </select>
        </div>
        <div class="options-line">
            <label for="per-page" class="topnav-label">Items per page:</label>
            <input type="number" class="topnav-form" style="width: 120px;"
                   id="per-page" name="perPage"
                   min="1" value="{{ sort_args["perPage"] }}">
        </div>
        <div class="options-line">
            <div></div> <!-- Spacer-->
            <button type="submit" class="topnav-form">Apply</button>
        </div>
    </form>
</div>
{% endblock %}
    <div class='maintable'>
    {% block breadcrumbs %}
    {% if breadcrumbs %}
    <div class="breadcrumbs">
        {% for crumb in breadcrumbs %}
            {% if not crumb.url is sameas none %}<a class="breadcrumb" href="{{ crumb.url|e }}">{{ crumb.name|e }}</a>{% else %}<span class="breadcrumb current_folder">{{ crumb.name|e }}</span>{% endif %}
            {% if not loop.last %}<span class="breadcrumb_separator">&rsaquo;</span>{% endif %}
        {% endfor %}
    </div>
    {% endif %}
    {% endblock %}
    {% block navbar %}
    {% if nav_list|length > 1 %}
    <div class="navbar">
        <div class="nav_arrow"><a{% if not first_index is sameas none %} href="{{ first_index }}"{% endif %}><i class="fa fa-angle-double-left nav_arrow" id="firstnav"></i></a></div>

        <div class="nav_arrow"><a{% if not prev_index is sameas none %} href="{{prev_index}}"{% endif %}><i class="fa fa-angle-left nav_arrow" id="backnav"></i></a></div>
        <div class="nav_links">
            {% block navlist %}
            {% for nav_item in nav_list %}
                {% if not nav_item.url is sameas none %}
                    <a class="nav_link" href="{{ nav_item.url }}">{{ nav_item.display }}</a>
                {% else %}
                    {{ nav_item.display }}
                {% endif %}
            {% endfor %}
            {% endblock %}
        </div>
        <div class="nav_arrow"><a {% if not next_index is sameas none %} href="{{next_index}}"{% endif%}><i class="fa fa-angle-right nav_arrow" id="fwdnav"></i></a></div>
        <div class="nav_arrow"><a {% if not final_index is sameas none %} href="{{ final_index }}" {% endif %}><i class="fa fa-angle-double-right nav_arrow" id="lastnav"></i></a></div>
        </div>
    {% endif %}
    {% endblock %}
    {% block mainlist %}
    {% for entry in entries %}
        <div class="entry_row {{ loop.cycle('odd', 'even') }}" id="{{ entry.id }}">
            <div class="cover_col" id="{{ entry.id }}">
                <img src="{{ entry.cover_url if not entry.cover_url is sameas none else default_cover }}" class="cover_img" />
            <a class="qr_link" onclick="toggle_modal({{entry.id}})"><i class="fa fa-qrcode"></i></a>
            </div>
            <div class="entry_body" id="{{ entry.id }}">
                <h3 class="entry_title"><a class="entry_link" href="{{ entry.rss_url }}">{{ entry.name }}</a></h3>
                <div class="entry_extra_feeds">
                    <div class="extra_feed">
                        <a onclick="toggle_modal({{ entry.id }}, 'SINGLEFILE')"><i class="fa fa-qrcode extra_feed_qr"></i></a><a href="{{ entry.derived_rss_url % 'singlefile' }}"> Single File</a>
                    </div>
                    {% if entry.has_chapter_info %}
                    <div class="extra_feed">
                    <a onclick="toggle_modal({{ entry.id }}, 'CHAPTERS')"><i class="fa fa-qrcode extra_feed_qr"></i></a><a href="{{ entry.derived_rss_url % 'chapters' }}"> Chapters</a>
                    </div>
                    {% endif %}
                    {% if entry.segmentable %}
                    <div class="extra_feed">
                    <a onclick="toggle_modal({{ entry.id }}, 'SEGMENTED')"><i class="fa fa-qrcode extra_feed_qr"></i></a><a href="{{ entry.derived_rss_url % 'segmented' }}"> Segmented</a>
                    </div>
                    {% endif %}
                </div>
                {% if entry.truncation_point <= 0 %}{{ entry.description }}{% else %}
                {{ entry.description[0:entry.truncation_point] }}{% if entry.description|length > entry.truncation_point %}<span class="hidden_description_section" id="e{{ entry.id }}">{{ entry.description[entry.truncation_point:] }}</span><span class="hidden_expander_span" id="e{{ entry.id }}"><span class="expander_ellipsis" id="e{{entry.id}}">... </span><a href="javascript:void(0);" class='read_more_link' id="e{{ entry.id }}" onclick="toggle_hidden({{ entry.id }})">(Read More)</a></span>{%endif%}
                {% endif %}
            </div>
        </div>
    {% endfor %}
    <div class="qr_holder" id="qr_container"></div>
    {% endblock %}
    {{ self.navbar() }}
    </div>
    <div class="overlay" id="div-overlay"/>
{% block botnav %}{% endblock %}
</body>
</html>
