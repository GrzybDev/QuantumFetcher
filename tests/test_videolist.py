from pathlib import Path

import pytest

from quantumfetcher import videolist
from quantumfetcher.errors import FetchError
from support import encrypt

GAME_LIST = (
    b'{\r\n\t"J1 - 4K Test" : "http://a.test/J1A%20-%204K%20Test.ism/manifest?tkn=1",\r\n'
    b'\t"J1A" : "http://a.test/J1A.ism/manifest?tkn=1",\r\n\t\r\n'
    b'\t"J2A" : "http://a.test/J2A.ism/manifest?tkn=1"\r\n}\r\n'
)


@pytest.fixture
def game_list(tmp_path: Path) -> Path:
    path = tmp_path / "videoList.rmdj"
    path.write_bytes(encrypt(GAME_LIST))
    return path


def test_decodes_the_games_own_list(game_list: Path) -> None:
    assert videolist.load(game_list) == {
        "J1 - 4K Test": "http://a.test/J1A%20-%204K%20Test.ism/manifest?tkn=1",
        "J1A": "http://a.test/J1A.ism/manifest?tkn=1",
        "J2A": "http://a.test/J2A.ism/manifest?tkn=1",
    }


def test_reencodes_a_list_it_wrote_byte_for_byte(game_list: Path) -> None:
    videos = videolist.load(game_list)
    written = videolist.encode(videos)
    assert videolist.decode(written) == videos
    assert videolist.encode(videolist.decode(written)) == written


@pytest.mark.parametrize(
    "data",
    [encrypt(b"[]"), encrypt(b'{"J1A": 1}'), encrypt(b"{"), b"\xff\xfe"],
    ids=["not an object", "not a URL", "cut off", "not encrypted JSON"],
)
def test_rejects_files_that_are_not_video_lists(game_list: Path, data: bytes) -> None:
    game_list.write_bytes(data)
    with pytest.raises(FetchError, match=r"videoList\.rmdj"):
        videolist.load(game_list)


def test_patch_points_every_episode_at_the_server_and_keeps_the_original(game_list: Path) -> None:
    original = game_list.with_name("videoList_original.rmdj")
    assert videolist.unpatched(game_list) == game_list
    videolist.patch(game_list, "127.0.0.1:1234")
    assert videolist.load(game_list) == {
        "J1 - 4K Test": "http://127.0.0.1:1234/J1 - 4K Test/manifest",
        "J1A": "http://127.0.0.1:1234/J1A/manifest",
        "J2A": "http://127.0.0.1:1234/J2A/manifest",
    }
    assert original.read_bytes() == encrypt(GAME_LIST)
    assert videolist.unpatched(game_list) == original
    videolist.patch(game_list, "10.0.0.1:80")
    assert videolist.load(game_list)["J1A"] == "http://10.0.0.1:80/J1A/manifest"
    assert original.read_bytes() == encrypt(GAME_LIST)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_read_json_reads_what_windows_tools_write(tmp_path: Path, encoding: str) -> None:
    source = tmp_path / "list.json"
    source.write_text('{"J1A": "http://a.test/manifest"}', encoding=encoding)
    assert videolist.read_json(source) == {"J1A": "http://a.test/manifest"}


@pytest.mark.parametrize("text", ['{"J1A": ["http://a.test"]}', "{"], ids=["not a URL", "cut off"])
def test_read_json_names_the_file_with_the_problem(tmp_path: Path, text: str) -> None:
    source = tmp_path / "list.json"
    source.write_text(text, encoding="utf-8")
    with pytest.raises(FetchError, match=r"list\.json"):
        videolist.read_json(source)
