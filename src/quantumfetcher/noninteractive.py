from pathlib import Path
from typing import Optional

import typer

from quantumfetcher.dataclasses.AudioStream import AudioStream
from quantumfetcher.dataclasses.TextStream import TextStream
from quantumfetcher.dataclasses.VideoStream import VideoStream
from quantumfetcher.enumerators.StreamType import StreamType
from quantumfetcher.flow import DownloadFlow
from quantumfetcher.surveys import get_episodes
from quantumfetcher.videolist import VideoList


def NonInteractiveMain(
    gamePath: Path,
    videoList_path: Path,
    episodes_path: Path,
    episodes: str,
    video_bitrates: Optional[str],
    audio_langs: Optional[str],
    audio_bitrates: Optional[str],
    text_langs: Optional[str],
    text_bitrates: Optional[str],
    extract_subtitles: bool,
):
    videoList = VideoList(gamePath / videoList_path)

    if episodes == "all":
        episode_ids = videoList.get_episode_list()
    elif episodes:
        episode_ids = [e.strip() for e in (episodes or "").split(",") if e.strip()]
    else:
        episode_ids = videoList.get_episode_list()

    video_bitrate_list = (
        [int(b) for b in video_bitrates.split(",")] if video_bitrates else []
    )
    audio_lang_list = (
        [lang.strip() for lang in audio_langs.split(",")] if audio_langs else []
    )
    audio_bitrate_list = (
        [int(b) for b in audio_bitrates.split(",")] if audio_bitrates else []
    )
    text_lang_list = (
        [lang.strip() for lang in text_langs.split(",")] if text_langs else []
    )
    text_bitrate_list = (
        [int(b) for b in text_bitrates.split(",")] if text_bitrates else []
    )

    videoList = VideoList(gamePath / videoList_path)
    _, manifests = get_episodes(videoList=videoList, selected_episodes=episode_ids)

    # Use get_streams logic if any quality/lang is specified, else fallback to ENG/highest
    if any([video_bitrates, audio_langs, audio_bitrates, text_langs, text_bitrates]):

        def filter_streams(fetch_episodes, manifests):
            video_set, audio_set, text_set = set(), set(), set()
            for episode_id in fetch_episodes:
                manifest = manifests[episode_id][1]
                video_set.update(manifest.list_video_streams())
                audio_set.update(manifest.list_audio_streams())
                text_set.update(manifest.list_text_streams())
            result = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}
            if video_bitrate_list:
                result[StreamType.Video] = [
                    VideoStream(*v) for v in video_set if v[2] in video_bitrate_list
                ]
            # Audio: allow filtering by lang, bitrate, or both
            if audio_lang_list or audio_bitrate_list:
                result[StreamType.Audio] = [
                    AudioStream(*a)
                    for a in audio_set
                    if (
                        (
                            not audio_lang_list
                            or (a[1].value if hasattr(a[1], "value") else a[1])
                            in audio_lang_list
                        )
                        and (not audio_bitrate_list or a[2] in audio_bitrate_list)
                    )
                ]
            # Text: allow filtering by lang, bitrate, or both
            if text_lang_list or text_bitrate_list:
                result[StreamType.Text] = [
                    TextStream(*t)
                    for t in text_set
                    if (
                        (
                            not text_lang_list
                            or (t[1].value if hasattr(t[1], "value") else t[1])
                            in text_lang_list
                        )
                        and (not text_bitrate_list or t[2] in text_bitrate_list)
                    )
                ]
            return result

        try:
            qualities_to_fetch = filter_streams(episode_ids, manifests)
        except KeyError as e:
            return typer.echo(
                "Error: Failed to fetch one or more manifests for the requested episodes. "
                "Please ensure the episode IDs are correct and the manifests are available.",
                err=True,
            )
    else:

        def eng_highest_streams(fetch_episodes, manifests):
            video_set, audio_set, text_set = set(), set(), set()
            for episode_id in fetch_episodes:
                manifest = manifests[episode_id][1]
                video_set.update(manifest.list_video_streams())
                audio_set.update(manifest.list_audio_streams())
                text_set.update(manifest.list_text_streams())
            result = {StreamType.Video: [], StreamType.Audio: [], StreamType.Text: []}
            # Highest video
            if video_set:
                best_video = sorted(video_set, key=lambda v: v[2], reverse=True)[0]
                result[StreamType.Video].append(VideoStream(*best_video))
            # English audio
            result[StreamType.Audio] = [
                AudioStream(*a)
                for a in audio_set
                if (a[1].value if hasattr(a[1], "value") else a[1]) == "eng"
            ]
            # English text
            result[StreamType.Text] = [
                TextStream(*t)
                for t in text_set
                if (t[1].value if hasattr(t[1], "value") else t[1]) == "eng"
            ]
            return result

        try:
            qualities_to_fetch = eng_highest_streams(episode_ids, manifests)
        except KeyError as e:
            return typer.echo(
                "Error: Failed to fetch one or more manifests for the requested episodes. "
                "Please ensure the episode IDs are correct and the manifests are available.",
                err=True,
            )

    # Deduplicate
    for k in qualities_to_fetch:
        qualities_to_fetch[k] = list(
            {str(x): x for x in qualities_to_fetch[k]}.values()
        )

    print(qualities_to_fetch)

    flow = DownloadFlow(
        videoList=videoList,
        manifests=manifests,
        output_path=gamePath / episodes_path,
        extract_subtitles=extract_subtitles,
    )
    flow.download(episode_ids, qualities_to_fetch)
