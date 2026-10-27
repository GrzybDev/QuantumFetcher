import json
from collections.abc import Callable, Collection, Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from quantumfetcher import cli, prompts, videolist
from quantumfetcher.game import GameFolder
from quantumfetcher.network import HttpClient
from support import (
    MANIFEST_URL,
    FakeClient,
    caption,
    client_manifest,
    episode_responses,
    files,
    fragment,
    fragment_url,
    ttml,
)

MISSING_URL = "http://cdn.test/J2A.ism/manifest"

type Run = Callable[..., Result]


@pytest.fixture
def client() -> FakeClient:
    return FakeClient(episode_responses())


@pytest.fixture
def game(tmp_path: Path) -> GameFolder:
    game = GameFolder(tmp_path.resolve() / "QuantumBreak")
    game.videolist.parent.mkdir(parents=True)
    videolist.save(game.videolist, {"J1A": MANIFEST_URL, "J2A": MISSING_URL})
    return game


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, client: FakeClient) -> Run:
    monkeypatch.setattr(HttpClient, "get", lambda _, url: client.get(url))

    def invoke(*arguments: object) -> Result:
        return CliRunner().invoke(cli.app, [str(argument) for argument in arguments])

    return invoke


def test_downloads_the_default_tracks_of_the_episodes_given(run: Run, game: GameFolder) -> None:
    result = run("download", game.root, "--episodes", "j1a", "--yes")
    assert result.exit_code == 0, result.output
    assert (
        f"Saved 3 tracks to {game.episodes}, with 1 of 1 episode playable offline" in result.output
    )
    assert files(game.episodes / "J1A") == [
        "J1A.ism",
        "J1A.ismc",
        "J1A_enus_256000.isma",
        "J1A_enus_captions_256000.ismt",
        "J1A_video_2000000.ismv",
    ]


def test_downloads_from_the_original_list_once_it_is_patched(run: Run, game: GameFolder) -> None:
    videolist.patch(game.videolist, "127.0.0.1:1")
    result = run(
        "download", game.root, "-e", "J1A", "--video", "none", "--audio", "esmx", "--text", "none"
    )
    assert result.exit_code == 0, result.output
    assert (game.episodes / "J1A" / "J1A_esmx_256000.isma").exists()


def test_extracts_subtitles_when_asked(run: Run, game: GameFolder) -> None:
    result = run(
        "download", game.root, "-e", "J1A", "--video", "none", "--audio", "none",
        "--extract-subtitles", "--append-episode-title",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    srt = (game.episodes / "J1A" / "enus_captions.srt").read_text(encoding="utf-8")
    assert "EPISODE 1: Monarch Solutions" in srt
    assert "Saved 1 track to" in result.output
    assert "with 0 of 1 episode playable offline" in result.output


def test_keeps_the_episode_when_its_subtitles_cannot_be_saved(
    run: Run, game: GameFolder, client: FakeClient
) -> None:
    broken = fragment(ttml(caption("10f", "20f", "unsupported time")))
    client.responses[fragment_url("enus_captions", 256000, 0)] = broken
    result = run("download", game.root, "-e", "J1A", "-y", "--extract-subtitles")
    assert result.exit_code == 1, result.output
    assert "with 1 of 1 episode playable offline" in result.output
    assert "Error: Could not save the subtitles of 1 of 1 episode: J1A" in result.output
    assert "Could not download" not in result.output
    assert "J1A.ism" in files(game.episodes / "J1A")


def test_skips_episodes_whose_manifest_is_unavailable(run: Run, game: GameFolder) -> None:
    result = run("download", game.root, "-e", "all", "--video", "500000", "-y")
    assert result.exit_code == 0, result.output
    assert "Skipping J2A" in result.output
    assert "with 1 of 1 episode playable offline" in result.output


def test_skips_episodes_the_selectors_pick_no_track_of(
    run: Run, game: GameFolder, client: FakeClient
) -> None:
    other = "http://cdn.test/J3A.ism/manifest"
    client.responses[other] = (
        client_manifest().replace(b'"esmx"', b'"frfr"').replace(b'"500000"', b'"400000"')
    )
    videolist.save(game.videolist, {"J1A": MANIFEST_URL, "J3A": other})
    result = run(
        "download", game.root, "-e", "all", "--video", "500000", "--audio", "esmx", "--text", "none"
    )
    assert result.exit_code == 0, result.output
    assert "Skipping J3A" in result.output
    assert files(game.episodes) == ["J1A"]
    assert "Saved 2 tracks to" in result.output
    assert "with 1 of 1 episode playable offline" in result.output


def test_fails_when_an_episode_cannot_be_downloaded(
    run: Run, game: GameFolder, client: FakeClient
) -> None:
    del client.responses[next(url for url in client.responses if "video=0" in url)]
    result = run("download", game.root, "-e", "J1A", "--video", "all", "-y")
    assert result.exit_code == 1, result.output
    assert "Error: Could not download 1 of 1 episode: J1A" in result.output


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (["-e", "J9Z"], "The video list has no episode J9Z"),
        (["-e", "J1A", "--audio", "pl"], "No audio track matches pl"),
        (
            ["-e", "J1A", "--video", "none", "--audio", "none", "--text", "none"],
            "pick no tracks",
        ),
        (["-e", "J2A"], "No episode could be fetched"),
    ],
    ids=["unknown episode", "unknown track", "no tracks", "no manifest"],
)
def test_rejects_what_matches_nothing(
    run: Run, game: GameFolder, arguments: list[str], error: str
) -> None:
    result = run("download", game.root, *arguments, "-y")
    assert result.exit_code == 1, result.output
    assert error in result.output


@pytest.mark.parametrize(
    ("arguments", "terminal", "reason"),
    [
        (["download", "-e", "J1A", "-y"], True, "with --yes"),
        (["download", "-e", "J1A"], False, "without a terminal"),
        ([], False, "without a terminal"),
        (["videolist", "dump"], False, "without a terminal"),
    ],
)
def test_says_why_the_game_folder_left_out_is_not_asked_for(
    run: Run, monkeypatch: pytest.MonkeyPatch, arguments: list[str], terminal: bool, reason: str
) -> None:
    monkeypatch.setattr(cli, "_interactive", lambda: terminal)
    result = run(*arguments)
    assert result.exit_code == 1, result.output
    assert f"Error: No game folder given, and none is asked for {reason}" in result.output


def test_needs_no_game_folder_when_both_paths_are_given(run: Run, game: GameFolder) -> None:
    output = game.root / "elsewhere"
    result = run(
        "download", "--videolist-path", game.videolist, "--episodes-path", output,
        "-e", "J1A", "--video", "none", "--text", "none",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert (output / "J1A" / "J1A_enus_256000.isma").exists()


def test_downloads_without_a_command_asking_for_everything_in_a_terminal(
    run: Run, game: GameFolder, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[object, ...]] = []

    def folder(message: str) -> Path:
        asked.append((message,))
        return game.root

    def checkbox(
        message: str, choices: Sequence[tuple[str, str]], default: Collection[str] = ()
    ) -> list[str]:
        offered = [value for _, value in choices]
        picked = [value for value in offered if value in default]
        asked.append((message, offered, picked))
        return ["J1A"] if message == "Episodes to download" else picked

    def confirm(message: str, default: bool) -> bool:
        asked.append((message, default))
        return True

    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(prompts, "folder", folder)
    monkeypatch.setattr(prompts, "checkbox", checkbox)
    monkeypatch.setattr(prompts, "confirm", confirm)
    monkeypatch.setattr(prompts, "pause", lambda message: asked.append((message,)))
    result = run()
    assert result.exit_code == 0, result.output
    assert asked == [
        ("Game folder",),
        ("Episodes to download", ["J1A", "J2A"], []),
        ("Video tracks to download", ["best", "2000000", "500000"], ["best"]),
        ("Audio tracks to download", ["enus", "esmx"], ["enus"]),
        ("Text tracks to download", ["enus_captions", "eses_captions"], ["enus_captions"]),
        ("Save the captions as SubRip files that QuantumStreamer shows instead?", False),
        ("Add the episode title to the saved subtitles?", True),
        ("Press any key to exit",),
    ]
    assert files(game.episodes / "J1A") == [
        "J1A.ism",
        "J1A.ismc",
        "J1A_enus_256000.isma",
        "J1A_enus_captions_256000.ismt",
        "J1A_video_2000000.ismv",
        "enus_captions.srt",
    ]
    srt = (game.episodes / "J1A" / "enus_captions.srt").read_text(encoding="utf-8")
    assert "EPISODE 1: Monarch Solutions" in srt


def test_fails_when_no_episode_is_picked_and_waits_for_a_key_without_a_command(
    run: Run, game: GameFolder, monkeypatch: pytest.MonkeyPatch
) -> None:
    paused: list[str] = []
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(prompts, "folder", lambda message: game.root)
    monkeypatch.setattr(prompts, "checkbox", lambda message, choices, default=(): [])
    monkeypatch.setattr(prompts, "pause", paused.append)
    result = run()
    assert result.exit_code == 1, result.output
    assert "Error: No episodes chosen" in result.output
    assert paused == ["Press any key to exit"]


def test_formats_lists_the_tracks_and_their_selectors(run: Run, game: GameFolder) -> None:
    result = run("formats", game.root, "-e", "J1A")
    assert result.exit_code == 0, result.output
    cells = [[cell.strip() for cell in line.split("│")[1:3]] for line in result.output.splitlines()]
    assert [row for row in cells if row and row[0] in {"video", "audio", "text"}] == [
        ["video", "best"],
        ["video", "2000000"],
        ["video", "500000"],
        ["audio", "enus"],
        ["audio", "esmx"],
        ["text", "enus_captions"],
        ["text", "eses_captions"],
    ]


def test_videolist_dump_prints_or_saves_the_list(run: Run, game: GameFolder) -> None:
    result = run("videolist", "dump", game.root)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"J1A": MANIFEST_URL, "J2A": MISSING_URL}
    output = game.root / "list.json"
    result = run("videolist", "dump", "--videolist-path", game.videolist, "-o", output)
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["J1A"] == MANIFEST_URL


def test_videolist_patch_points_the_games_list_at_the_server(run: Run, game: GameFolder) -> None:
    result = run("videolist", "patch", game.root, "-s", "127.0.0.1:5000")
    assert result.exit_code == 0, result.output
    assert videolist.load(game.videolist)["J1A"] == "http://127.0.0.1:5000/J1A/manifest"


@pytest.mark.parametrize("patched", [False, True], ids=["unpatched", "patched"])
def test_videolist_build_replaces_the_list_episodes_are_read_from_keeping_the_games_own(
    run: Run, game: GameFolder, patched: bool
) -> None:
    if patched:
        videolist.patch(game.videolist, "127.0.0.1:1")
    replaced = videolist.unpatched(game.videolist)
    games_own = replaced.read_bytes()
    source = game.root / "list.json"
    for episode in ("J3A", "J4A"):
        built = {episode: f"http://cdn.test/{episode}.ism/manifest"}
        source.write_text(json.dumps(built), encoding="utf-16")
        result = run("videolist", "build", source, game.root)
        assert result.exit_code == 0, result.output
        assert json.loads(run("videolist", "dump", game.root).stdout) == built
        assert replaced.with_name(f"{replaced.name}.old").read_bytes() == games_own
    assert videolist.original_path(game.videolist).exists() == patched
