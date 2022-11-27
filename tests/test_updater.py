"""Tests for audio_feeder.updater"""
import contextlib
import json
import pathlib
import typing
from unittest import mock

from audio_feeder import metadata_loader as mdl
from audio_feeder import updater


def _lists_to_tuple(l: typing.List[typing.Any]) -> typing.Tuple[typing.Any]:
    return tuple(
        _lists_to_tuple(item) if isinstance(item, list) else item for item in l
    )


SessionKey = typing.Tuple[str, typing.Sequence[typing.Tuple[str, str]]]
SessionJson = typing.Mapping[str, typing.Any]


class FakeResponse:
    def __init__(
        self, status_code: int = 200, json_contents: typing.Optional[SessionJson] = None
    ):
        self.status_code = status_code
        self._json_contents = json_contents

    def json(self) -> typing.Optional[SessionJson]:
        return self._json_contents


def load_response_mapping(
    responses: pathlib.Path,
) -> typing.Mapping[SessionKey, FakeResponse]:
    with open(responses, "rt") as f:
        session_responses = json.load(f)

    return {
        _lists_to_tuple(session_key): FakeResponse(
            status_code=200, json_contents=session_response
        )
        for session_key, session_response in session_responses
    }


class FakeGoogleBooksLoader(mdl.GoogleBooksLoader):
    def __init__(
        self, *args, _response_map: typing.Mapping[SessionKey, FakeResponse], **kwargs
    ):
        kwargs["poll_delay"] = kwargs.pop("poll_delay", 0)
        self._response_map = _response_map

        super().__init__(*args, **kwargs)

    def make_request_raw(self, *args, **kwargs):
        (url,) = args

        params = kwargs["params"]
        assert not (kwargs.keys() - {"params"})

        key = (url, tuple(params.items()))

        return self._response_map[key]


class FakeBookUpdater(updater.BookDatabaseUpdater):
    def __init__(self, books_location: pathlib.Path, **kwargs):
        kwargs["metadata_loaders"] = kwargs.get(
            "metadata_loaders",
            (
                FakeGoogleBooksLoader(
                    _response_map=load_response_mapping(
                        pathlib.Path(__file__).parent
                        / "data/example_google_books_responses.json"
                    )
                ),
            ),
        )
        super().__init__(books_location, **kwargs)


@contextlib.contextmanager
def patch_book_updater() -> typing.Iterator[None]:
    old_book_updater = updater.BookDatabaseUpdater
    try:
        updater.BookDatabaseUpdater = FakeBookUpdater
        with mock.patch.object(
            mdl.requests, "get", return_value=FakeResponse(status_code=403)
        ):
            yield
    finally:
        updater.BookDatabaseUpdater = old_book_updater


def test_update_books(testgen_config: pathlib.Path) -> None:
    with patch_book_updater():
        updater.update(content_type="books")
