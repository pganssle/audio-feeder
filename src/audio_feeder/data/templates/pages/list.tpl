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
<div class="topnav">
    <!-- TODO: Implement login
    <a href="/login"><i class="fa fa-user topnav-icon"></i></a>
    -->
    <div class="topnav-settings-container topnav-icon">
            <i class="fa fa-gear"></i>
            <form action="/books" class="options-dropdown">
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
                <button type="submit" class="topnav-form">Submit</button>
            </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}
    <div class='maintable'>
    {% block navbar %}
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
