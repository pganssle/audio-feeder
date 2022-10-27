import pytest

from audio_feeder import rss_feeds as afrf

wrap_field_data = [
    ('<a href="test">B</a>', '<![CDATA[<a href="test">B</a>]]>'),
    ("One & Two", "One &amp; Two"),
    ("One &amp; Two", "One &amp; Two"),
    (14, 14),
    ("Three > 4 but 9 < 13", "Three &gt; 4 but 9 &lt; 13"),
]


@pytest.mark.parametrize("field,expected", wrap_field_data)
def test_wrap_field(field, expected):
    actual = afrf.wrap_field(field)

    assert actual == expected, actual
