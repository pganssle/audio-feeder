import itertools
import pathlib

import pytest

from audio_feeder import file_location as afl

###
#  FileLocation tests
#

# (rel_path, [(base_url, url_out), ... ], [(base_path, path_out), ... ])
file_location_test_data_base = [
    (
        "images/site-images/grisly_murder.png",
        [
            (
                "http://localhost/static",
                "http://localhost/static/images/site-images/grisly_murder.png",
            ),
            (
                "http://localhost/static/",
                "http://localhost/static/images/site-images/grisly_murder.png",
            ),
            (
                "http://192.168.0.0/static",
                "http://192.168.0.0/static/images/site-images/grisly_murder.png",
            ),
            (
                "http://mydomain.com/static",
                "http://mydomain.com/static/images/site-images/grisly_murder.png",
            ),
            (
                "http://localhost:9090/static",
                "http://localhost:9090/static/images/site-images/grisly_murder.png",
            ),
            (
                "https://mydomain.com/static",
                "https://mydomain.com/static/images/site-images/grisly_murder.png",
            ),
            (
                "https://mydomain.com:9090/static",
                "https://mydomain.com:9090/static/images/site-images/grisly_murder.png",
            ),
        ],
        [
            (
                "/home/audio_feeder/static",
                "/home/audio_feeder/static/images/site-images/grisly_murder.png",
            ),
            (
                "/home/audio_feeder/static/",
                "/home/audio_feeder/static/images/site-images/grisly_murder.png",
            ),
            (
                "~/audio_feeder/static",
                "~/audio_feeder/static/images/site-images/grisly_murder.png",
            ),
            (None, None),
        ],
    ),
    (
        "../favicon.ico",
        [
            (
                "http://localhost:9090/static/images/site-images/all-images",
                "http://localhost:9090/static/images/site-images/favicon.ico",
            )
        ],
        [
            (
                "/home/audio_feeder/static/images/",
                "/home/audio_feeder/static/favicon.ico",
            ),
            (None, None),
        ],
    ),
]

file_location_test_data = [
    (
        (
            pathlib.Path(rel_path),
            base_url,
            pathlib.Path(base_path) if base_path else base_path,
        ),
        exp_url,
        pathlib.Path(exp_path) if exp_path else exp_path,
    )
    for rel_path, url_data, path_data in file_location_test_data_base
    for (base_url, exp_url), (base_path, exp_path) in itertools.product(
        url_data, path_data
    )
]


@pytest.mark.parametrize("args,exp_url,exp_path", file_location_test_data)
def test_file_location_basic(args, exp_url, exp_path):
    fl = afl.FileLocation(*args)

    assert fl.url == exp_url, "Non-matching url: {}".format(fl.url)
    assert fl.path == exp_path, "Non-matching path: {}".format(fl.path)


def test_file_location_invalid_url():
    with pytest.raises(afl.InvalidURLError):
        afl.FileLocation("test.png", "mydomain.com/images/", "/path/to/file")


def test_file_location_absolute_path():
    # Absolute paths are not allowed
    # Windows not currently tested
    with pytest.raises(afl.InvalidRelativePathError):
        afl.FileLocation(
            "/path/to/file/test.png", "http://localhost/static", "/path/to/file/"
        )


@pytest.mark.parametrize(
    "protocol,exp_url",
    [
        ("https", "https://mydomain.org/static/img.png"),
        ("https://", "https://mydomain.org/static/img.png"),
        ("ftp://", "ftp://mydomain.org/static/img.png"),
        ("ftp", "ftp://mydomain.org/static/img.png"),
    ],
)
def test_file_location_as_protocol(protocol, exp_url):
    fl = afl.FileLocation(
        "img.png", "http://mydomain.org/static/", "/home/audio_feeder/.config/static/"
    )

    url = fl.url_as_protocol(protocol)
    assert url == exp_url, url


def test_file_location_repr():
    fl = afl.FileLocation(
        "img.png",
        "http://www.mydomain.com:90/images/",
        "/home/audio_feeder/.config/static/",
    )

    assert repr(fl) == "<FileLocation('img.png')>", repr(fl)


def test_file_location_immutable():
    fl = afl.FileLocation(
        "img.png",
        "http://www.mydomain.com:90/static/",
        "/home/audio_feeder/.config/static/",
    )

    with pytest.raises(AttributeError):
        fl.path = "/home/audio_feeder/static"

    with pytest.raises(AttributeError):
        fl.url = "http://mydomain.com:90/static/"
