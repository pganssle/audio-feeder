import importlib.resources
import os
from pathlib import Path

import pytest

from audio_feeder import resources


@pytest.mark.parametrize(
    "resource",
    [
        importlib.resources.files("audio_feeder.data.templates.pages"),
        "audio_feeder.data.templates.pages",
    ],
)
def test_update_resource(tmp_path: Path, resource, subtests) -> None:
    target_dir = tmp_path
    expected_tree = (("", "list.tpl"),)

    target_paths = [
        tmp_path / subdir / resource_name for subdir, resource_name in expected_tree
    ]

    for target_path in target_paths:
        with subtests.test(f"{target_path}: before update"):
            assert not target_path.exists()

    resources.update_resource(resource, target_dir)

    for target_path in target_paths:
        with subtests.test(f"{target_path}: after update"):
            assert target_path.exists()
            assert target_path.read_text()  # Not empty file

    resources.update_resource(resource, target_dir)
    for target_path in target_paths:
        old_text = target_path.read_text()
        with subtests.test(f"{target_path}: update no modification"):
            assert target_path.exists()
            assert target_path.read_text() == old_text

    # Now try modifying the resource and running the update again
    originals = {}
    for target_path in target_paths:
        originals[target_path] = target_path.read_bytes()
        to_write = b"a" * os.path.getsize(target_path)
        target_path.write_bytes(to_write)

    resources.update_resource(resource, target_dir)

    for target_path in target_paths:
        with subtests.test(f"{target_path}: after modification"):
            assert target_path.exists()
            assert target_path.read_bytes() == originals[target_path]


@pytest.mark.parametrize(
    "resource",
    [
        importlib.resources.files("audio_feeder.data.templates.pages"),
        "audio_feeder.data.templates.pages",
    ],
)
def test_update_resource_changed_size(tmp_path: Path, resource, subtests) -> None:
    target_dir = tmp_path
    expected_tree = (("", "list.tpl"),)

    target_paths = [
        tmp_path / subdir / resource_name for subdir, resource_name in expected_tree
    ]

    for target_path in target_paths:
        with subtests.test(f"{target_path}: before update"):
            assert not target_path.exists()

    resources.update_resource(resource, target_dir)

    # Modify the resource in a way that changes its size
    originals = {}
    for target_path in target_paths:
        originals[target_path] = target_path.read_bytes()
        target_path.write_bytes(b"b" * 50)

    resources.update_resource(resource, target_dir)

    for target_path in target_paths:
        with subtests.test(f"{target_path}: after modification"):
            assert target_path.exists()
            assert target_path.read_bytes() == originals[target_path]


def test_get_resource(tmp_path: Path) -> None:
    resources.copy_resource("audio_feeder.data.templates.pages", tmp_path)
    list_contents = (tmp_path / "list.tpl").read_text()

    assert (
        resources.get_text_resource("audio_feeder.data.templates.pages", "list.tpl")
        == list_contents
    )
