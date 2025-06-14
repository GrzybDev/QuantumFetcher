from pathlib import Path

import typer

from quantumfetcher.flow import DownloadFlow
from quantumfetcher.helpers import (
    filter_streams_by_quality_and_language,
    select_highest_eng_streams,
)
from quantumfetcher.surveys import get_episodes
from quantumfetcher.videolist import VideoList


def NonInteractiveMain(
    gamePath: Path,
    videoList_path: Path,
    episodes_path: Path,
    episodes: str,
    video_bitrates: str | None,
    audio_langs: str | None,
    audio_bitrates: str | None,
    text_langs: str | None,
    text_bitrates: str | None,
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
        "all"
        if video_bitrates == "all"
        else [int(b) for b in video_bitrates.split(",")] if video_bitrates else []
    )
    audio_lang_list = (
        "all"
        if audio_langs == "all"
        else [lang.strip() for lang in audio_langs.split(",")] if audio_langs else []
    )
    audio_bitrate_list = (
        "all"
        if audio_bitrates == "all"
        else [int(b) for b in audio_bitrates.split(",")] if audio_bitrates else []
    )
    text_lang_list = (
        "all"
        if text_langs == "all"
        else [lang.strip() for lang in text_langs.split(",")] if text_langs else []
    )
    text_bitrate_list = (
        "all"
        if text_bitrates == "all"
        else [int(b) for b in text_bitrates.split(",")] if text_bitrates else []
    )

    videoList = VideoList(gamePath / videoList_path)
    _, manifests = get_episodes(videoList=videoList, selected_episodes=episode_ids)

    # Use get_streams logic if any quality/lang is specified, else fallback to ENG/highest
    if any([video_bitrates, audio_langs, audio_bitrates, text_langs, text_bitrates]):
        try:
            qualities_to_fetch = filter_streams_by_quality_and_language(
                episode_ids,
                manifests,
                video_bitrate_list,
                audio_lang_list,
                audio_bitrate_list,
                text_lang_list,
                text_bitrate_list,
            )
        except KeyError as e:
            return typer.echo(
                "Error: Failed to fetch one or more manifests for the requested episodes. "
                "Please ensure the episode IDs are correct and the manifests are available.",
                err=True,
            )
    else:
        try:
            qualities_to_fetch = select_highest_eng_streams(episode_ids, manifests)
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

    flow = DownloadFlow(
        videoList=videoList,
        manifests=manifests,
        output_path=gamePath / episodes_path,
        extract_subtitles=extract_subtitles,
    )
    flow.download(episode_ids, qualities_to_fetch)
