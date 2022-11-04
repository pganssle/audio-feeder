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
    [ {{entry.id}}, "{{ entry.qr_img_url }}" ],
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

function make_qr_modal(entry_id) {
    const modal_div = document.createElement("div");
    modal_div.setAttribute("id", "qr-" + entry_id);
    modal_div.setAttribute("class", "modal-window");

    const qr_img = document.createElement("img");
    qr_img.setAttribute("src", qr_img_urls.get(entry_id));
    qr_img.setAttribute("class", "qr_img");

    modal_div.appendChild(qr_img);
    qr_container.appendChild(modal_div);
    return modal_div;
}

function toggle_modal(entry_id) {
    if (active_modal === null) {
        active_modal = entry_id;
    } else {
        active_modal = null;
    }

    let modal_div;
    if (!modal_divs.has(entry_id)) {
        modal_div = make_qr_modal(entry_id);
        modal_divs.set(entry_id, modal_div);
    } else {
        modal_div = modal_divs.get(entry_id);
    }

    get_overlay().classList.toggle("overlay-active");
    modal_div.classList.toggle("show-modal");
}

window.addEventListener("click", (event) => { if (event.target === get_overlay() && active_modal !== null) {toggle_modal(active_modal);}});
</script>

{% block topnav %}{% endblock %}
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
            <a class="qr_link" onclick="toggle_modal({{entry.id}})">QR</a>
            </div>
            <div class="entry_body" id="{{ entry.id }}">
                <h3 class="entry_title"><a class="entry_link" href="{{ entry.rss_url }}">{{ entry.name }}</a></h3>
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
