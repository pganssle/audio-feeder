import json
import os
import pathlib
import tempfile
import typing

import click

from audio_feeder import _db_types, config
from audio_feeder import metadata_loader as mdl
from audio_feeder import updater


class RecordingGoogleBooksLoader(mdl.GoogleBooksLoader):
    SessionKey = typing.Tuple[str, typing.Sequence[typing.Tuple[str, str]]]
    SessionJson = typing.Mapping[str, typing.Any]

    def __init__(self, *args, **kwargs):
        self._session_recording: typing.MutableMapping[
            self.SessionKey, self.SessionJson
        ] = {}
        super().__init__(*args, **kwargs)

    def make_request_raw(self, *args, **kwargs):
        (url,) = args

        params = kwargs["params"]
        assert not (kwargs.keys() - {"params"})

        key = (url, tuple(params.items()))
        if key in self._session_recording:
            raise ValueError(f"Duplicate key: {key}")

        resp = super().make_request_raw(*args, **kwargs)

        self._session_recording[key] = resp.json()
        return resp

    @property
    def session_recording(self) -> typing.Mapping[SessionKey, SessionJson]:
        return self._session_recording

    def write_session_recording(self, out_path: pathlib.Path) -> None:
        serializable = list(self.session_recording.items())
        with open(out_path, "wt") as f:
            json.dump(serializable, f, sort_keys=True, indent=2)


@click.command()
@click.option(
    "--media-dir",
    required=True,
    type=click.Path(
        dir_okay=True, exists=True, file_okay=False, path_type=pathlib.Path
    ),
)
@click.option(
    "--output",
    required=True,
    type=click.Path(
        dir_okay=False, file_okay=True, exists=False, path_type=pathlib.Path
    ),
)
def main(media_dir: pathlib.Path, output: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory() as t_f:
        tmp_path = pathlib.Path(t_f)
        config_loc = tmp_path / "config.yml"
        conf = config.Configuration(
            config_loc_=config_loc,
            media_path=media_dir.name,
            static_media_path=os.fspath(media_dir.parent),
        )
        conf.to_file(config_loc)
        os.environ["AF_CONFIG_DIR"] = t_f
        config.get_configuration.cache_clear()
        config.get_configuration()

    db: _db_types.MutableDatabase = {
        "entries": {},  # type: ignore[dict-item]
        "books": {},  # type: ignore[dict-item]
        "authors": {},  # type: ignore[dict-item]
        "series": {},  # type: ignore[dict-item]
    }
    book_loader = RecordingGoogleBooksLoader()
    book_updater = updater.BookDatabaseUpdater(
        media_dir, metadata_loaders=(book_loader,)
    )
    book_updater.update_db_entries(db)
    book_updater.assign_books_to_entries(db)
    book_updater.update_book_metadata(db)

    book_loader.write_session_recording(output)


if __name__ == "__main__":
    main()  # type: ignore
