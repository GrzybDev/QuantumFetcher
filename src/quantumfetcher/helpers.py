import operator
from collections.abc import Callable

import typer
from rich.progress import track

from quantumfetcher.dataclasses.AudioStream import AudioStream
from quantumfetcher.dataclasses.TextStream import TextStream
from quantumfetcher.dataclasses.VideoStream import VideoStream
from quantumfetcher.downloader import fetch_manifest
from quantumfetcher.enumerators.ManifestType import ManifestType
from quantumfetcher.enumerators.StreamType import StreamType
from quantumfetcher.videolist import VideoList


def fetch_manifests(videoList, episode_ids):
    # Fetch server and client manifests for all episodes
    manifests = {}
    for episode_id in track(
        episode_ids, description="Fetching episode manifests...", transient=True
    ):
        client_manifest_url = videoList.get_client_manifest_url(episode_id)
        server_manifect_url = videoList.get_server_manifest_url(episode_id)

        if client_manifest_url and server_manifect_url:
            try:
                client_manifest = fetch_manifest(
                    client_manifest_url, ManifestType.Client
                )
                server_manifest = fetch_manifest(
                    server_manifect_url, ManifestType.Server
                )
                manifests[episode_id] = (server_manifest, client_manifest)
            except Exception as e:
                typer.echo(
                    f"Failed to fetch episode {episode_id} manifests! ({e})", err=True
                )

    return manifests


def get_quality_levels(manifests, episode_ids):
    def should_process(episode_id):
        return episode_id != "J1 - 4K Test" or len(episode_ids) == 1

    video_set = set()
    audio_set = set()
    text_set = set()

    for episode_id in episode_ids:
        if not should_process(episode_id):
            continue

        manifest = manifests[episode_id][1]

        for v in manifest.list_video_streams():
            video_set.add(v)
        for a in manifest.list_audio_streams():
            audio_set.add(a)
        for t in manifest.list_text_streams():
            text_set.add(t)

    def make_video_streams(streams):
        return sorted(
            [VideoStream(*v) for v in streams],
            key=operator.attrgetter("bitrate"),
            reverse=True,
        )

    def make_audio_streams(streams):
        return sorted(
            [AudioStream(*a) for a in streams],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    def make_text_streams(streams):
        return sorted(
            [TextStream(*t) for t in streams],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    return {
        StreamType.Video: make_video_streams(video_set),
        StreamType.Audio: make_audio_streams(audio_set),
        StreamType.Text: make_text_streams(text_set),
    }


def _parse_list(param: str | None, cast_func: Callable | None = None):
    if param == "all" or param is None:
        return None
    if cast_func:
        return [cast_func(x) for x in param if x]
    return [x for x in param if x]


def _filter_streams(streams, lang_list, bitrate_list, lang_idx=1, bitrate_idx=2):
    def get_lang(val):
        return val.value if hasattr(val, "value") else val

    return [
        s
        for s in streams
        if (not lang_list or get_lang(s[lang_idx]) in lang_list)
        and (not bitrate_list or s[bitrate_idx] in bitrate_list)
    ]


def filter_streams_by_quality_and_language(
    fetch_episodes,
    manifests,
    video_bitrates=None,
    audio_langs=None,
    audio_bitrates=None,
    text_langs=None,
    text_bitrates=None,
):
    video_set, audio_set, text_set = set(), set(), set()
    for episode_id in fetch_episodes:
        manifest = manifests[episode_id][1]
        video_set.update(manifest.list_video_streams())
        audio_set.update(manifest.list_audio_streams())
        text_set.update(manifest.list_text_streams())
    result = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}

    # VIDEO
    if video_bitrates == "all":
        result[StreamType.Video] = [VideoStream(*v) for v in video_set]
    else:
        video_bitrate_list = _parse_list(video_bitrates, int)
        result[StreamType.Video] = sorted(
            [
                VideoStream(*v)
                for v in _filter_streams(video_set, None, video_bitrate_list)
            ],
            key=operator.attrgetter("bitrate"),
        )

    # AUDIO
    if audio_langs == "all" and audio_bitrates == "all":
        result[StreamType.Audio] = [AudioStream(*a) for a in audio_set]
    else:
        audio_lang_list = _parse_list(audio_langs)
        audio_bitrate_list = _parse_list(audio_bitrates, int)
        result[StreamType.Audio] = sorted(
            [
                AudioStream(*a)
                for a in _filter_streams(audio_set, audio_lang_list, audio_bitrate_list)
            ],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    # TEXT
    if text_langs == "all" and text_bitrates == "all":
        result[StreamType.Text] = [TextStream(*t) for t in text_set]
    else:
        text_lang_list = _parse_list(text_langs)
        text_bitrate_list = _parse_list(text_bitrates, int)
        result[StreamType.Text] = sorted(
            [
                TextStream(*t)
                for t in _filter_streams(text_set, text_lang_list, text_bitrate_list)
            ],
            key=lambda x: (x.language.name, -x.bitrate),
        )

    return result


def select_highest_eng_streams(fetch_episodes, manifests):
    video_set, audio_set, text_set = set(), set(), set()
    for episode_id in fetch_episodes:
        manifest = manifests[episode_id][1]
        video_set.update(manifest.list_video_streams())
        audio_set.update(manifest.list_audio_streams())
        text_set.update(manifest.list_text_streams())
    result = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}
    if video_set:
        best_video = sorted(video_set, key=lambda v: v[2], reverse=True)[0]
        result[StreamType.Video].append(VideoStream(*best_video))
    result[StreamType.Audio] = [
        AudioStream(*a)
        for a in audio_set
        if (a[1].value if hasattr(a[1], "value") else a[1]) == "eng"
    ]
    result[StreamType.Text] = [
        TextStream(*t)
        for t in text_set
        if (t[1].value if hasattr(t[1], "value") else t[1]) == "eng"
    ]
    return result


def print_available_formats(videoListPath, episodes):
    videoList = VideoList(videoListPath)

    if episodes == "all":
        episode_ids = videoList.get_episode_list()
    elif episodes:
        episode_ids = [e.strip() for e in (episodes or "").split(",") if e.strip()]
    else:
        episode_ids = videoList.get_episode_list()

    manifests = fetch_manifests(videoList, episode_ids)
    qualities = get_quality_levels(manifests, episode_ids)

    print(
        "Available video formats:\n",
        "\n".join([f"- {v}" for v in qualities[StreamType.Video]]),
    )
    print(
        "Available audio languages:\n",
        "\n".join([f"- {a} [{a.language.value}]" for a in qualities[StreamType.Audio]]),  # type: ignore
    )
    print(
        "Available text formats:\n",
        "\n".join([f"- {t} [{t.language.value}]" for t in qualities[StreamType.Text]]),  # type: ignore
    )
