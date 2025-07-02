import operator
from itertools import groupby

from quantumfetcher.enumerators.type_manifest import ManifestType
from quantumfetcher.enumerators.type_stream import StreamType
from quantumfetcher.manifests.base import BaseManifest
from quantumfetcher.manifests.client import ClientManifest


def get_streams(
    manifests: dict[str, dict[ManifestType, BaseManifest]],
) -> dict[StreamType, list]:
    def should_process(episode_id):
        return episode_id != "J1 - 4K Test" or len(manifests) == 1

    video_set = set()
    audio_set = set()
    text_set = set()

    for episode_id in manifests.keys():
        if not should_process(episode_id):
            continue

        manifest = manifests[episode_id][ManifestType.Client]

        if not isinstance(manifest, ClientManifest):
            raise TypeError(
                f"Expected ClientManifest for episode {episode_id}, got {type(manifest)}"
            )

        for v in manifest.list_video_streams():
            video_set.add(v)
        for a in manifest.list_audio_streams():
            audio_set.add(a)
        for t in manifest.list_text_streams():
            text_set.add(t)

    def make_video_streams(streams):
        return sorted(
            video_set,
            key=operator.attrgetter("bitrate"),
            reverse=True,
        )

    def make_audio_streams(streams):
        return sorted(
            audio_set,
            key=lambda x: (x.language.name, -x.bitrate),
        )

    def make_text_streams(streams):
        return sorted(
            text_set,
            key=lambda x: (x.language.name, -x.bitrate),
        )

    return {
        StreamType.Video: make_video_streams(video_set),
        StreamType.Audio: make_audio_streams(audio_set),
        StreamType.Text: make_text_streams(text_set),
    }


def filter_streams(
    streams,
    langs,
    bitrates,
    lang_attr="language",
    bitrate_attr="bitrate",
    all_key="all",
):
    filtered = streams
    if langs:
        if langs == [all_key]:
            pass  # No filtering needed
        else:
            filtered = [
                s
                for s in filtered
                if getattr(getattr(s, lang_attr), "value", getattr(s, lang_attr, None))
                in langs
            ]

    if bitrates:
        if bitrates == [all_key]:
            pass  # No filtering needed
        else:
            filtered = [
                s for s in filtered if str(getattr(s, bitrate_attr, None)) in bitrates
            ]

    return filtered


def deduplicate_streams(streams, key_func, reverse=False):
    sorted_streams = sorted(streams, key=key_func, reverse=reverse)
    return [next(g) for _, g in groupby(sorted_streams, key=key_func)]
