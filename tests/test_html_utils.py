import pytest

from audio_feeder import html_utils as afhu

clean_html_data = [
    # Things that should stay
    (
        '<a href="https://www.google.com">Link</a>',
        '<a href="https://www.google.com">Link</a>',
    ),
    ("<b>Bold</b>", "<b>Bold</b>"),
    ("<i>Italics</i>", "<i>Italics</i>"),
    # Things that should be deleted
    ("<script>Delete</script>", "<div></div>"),
    ('<img src="https://malicious.ru">', "<div></div>"),
    ("<z>Test</z>", "<div>Test</div>"),
]


@pytest.mark.parametrize("input_,output", clean_html_data)
def test_clean_html(input_, output):
    actual = afhu.clean_html(input_)
    assert actual == output, actual


allowed_tags_data = [
    (
        ["a"],
        '<a href="https://www.example.org><i>Example</i></a>',
        '<a href="https://www.example.org>Example</a>',
    ),
    (
        ["a"],
        '<a href="https://www.example.org>Example</a>',
        '<a href="https://www.example.org>Example</a>',
    ),
    (["i"], '<a href="https://www.example.org><i>Example</i></a>', "<i>Example</i>"),
    (
        ["a", "i"],
        '<a href="https://www.example.org><i>Example</i></a>',
        '<a href="https://www.example.org><i>Example</i></a>',
    ),
]


@pytest.mark.skip(reason="LXML implementation does not drop tags.")
@pytest.mark.parametrize("tags,input_,output", allowed_tags_data)
def test_allowed_tags(tags, input_, output):
    actual = afhu.clean_html(input_, tag_whitelist=tags)
    assert actual == output, actual
