from pathlib import Path
from typing import Any, cast
import xml.etree.ElementTree as ET

import humanize
import requests
import yt_dlp
from rich.table import Table

from quantumfetcher.constants import USER_AGENT
from quantumfetcher.downloader import Downloader
from quantumfetcher.enumerators.language import Language, LanguageMap
from quantumfetcher.enumerators.stream import StreamType
from quantumfetcher.logger import logger
from quantumfetcher.prompt import Prompt
from quantumfetcher.video_list import VideoList


class Flow:
    def __init__(self, video_list: VideoList, **kwargs) -> None:
        self.__downloader = Downloader(
            retries=kwargs.get("retries", 10),
        )
        self.__video_list = video_list

        self.__episodes_to_fetch: list[str] | None = kwargs.get("episodes")
        self.__episodes_path: Path = kwargs["episodes_path"]

        self.__fetch_video_resolutions: list[str] | None = kwargs.get(
            "video_resolutions"
        )
        self.__fetch_video_bitrates: list[str] | None = kwargs.get("video_bitrates")
        self.__fetch_audio_langs: list[str] | None = kwargs.get("audio_langs")
        self.__fetch_audio_bitrates: list[str] | None = kwargs.get("audio_bitrates")
        self.__fetch_text_langs: list[str] | None = kwargs.get("text_langs")
        self.__fetch_text_bitrates: list[str] | None = kwargs.get("text_bitrates")

        self.__extract_subtitles = kwargs.get("extract_subtitles", False)
        self.__append_episode_title = kwargs.get("append_episode_title", False)
        self.__show_formats = kwargs.get("show_formats", False)
        self.__interactive = kwargs.get("interactive", False)

        self.__run()

    def __run(self):
        episodes = self.__video_list.episode_list
        if self.__episodes_to_fetch:
            if self.__episodes_to_fetch == ["all"]:
                self.__episodes_to_fetch = list(episodes.keys())
            else:
                episodes = {
                    k: v for k, v in episodes.items() if k in self.__episodes_to_fetch
                }

        if self.__interactive:
            episodes = self._interactive_preload(episodes)
            if not episodes:
                logger.error("No available episodes to download. Exiting.")
                return

        with logger.live_group():
            task_overall = logger.progress_overall.add_task(
                "Downloading episodes...", total=len(episodes)
            )

            for ep_id, url in episodes.items():
                logger.log(f"[cyan]Downloading {ep_id}...[/cyan]")
                try:
                    self.__process_episode(ep_id, url)
                except Exception as e:
                    logger.error(f"Failed to process {ep_id}: {e}")

                logger.progress_overall.update(task_overall, advance=1)

    def _interactive_preload(self, episodes: dict[str, str]) -> dict[str, str]:
        logger.log("[cyan]Preloading manifests to fetch available streams...[/cyan]")
        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "http_headers": {"User-Agent": USER_AGENT},
        }

        raw_vid = set()
        raw_aud = set()
        raw_txt = set()

        total_duration_sec = 0.0
        valid_episodes = {}

        with logger.live_overall():
            task_preload = logger.progress_overall.add_task(
                "Preloading manifests...", total=len(episodes)
            )
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                for ep_id, url in episodes.items():
                    try:
                        duration_sec = self._extract_duration(url)
                        info = ydl.extract_info(url, download=False)

                        valid_episodes[ep_id] = url
                        total_duration_sec += duration_sec

                        self._parse_formats(info, raw_vid, raw_aud, raw_txt)

                    except Exception as e:
                        logger.error(f"Failed to preload {ep_id} (Unavailable): {e}")

                    logger.progress_overall.update(task_preload, advance=1)

            logger.progress_overall.remove_task(task_preload)

        if not valid_episodes:
            return {}

        self._prompt_streams(
            valid_episodes, total_duration_sec, raw_vid, raw_aud, raw_txt
        )
        return valid_episodes

    def _extract_duration(self, url: str) -> float:
        client_resp = requests.get(url, headers={"User-Agent": USER_AGENT})
        client_resp.raise_for_status()
        c_root = ET.fromstring(client_resp.text)
        duration_ticks = int(c_root.attrib.get("Duration", 0))
        timescale = int(c_root.attrib.get("TimeScale", 10000000))
        return duration_ticks / float(timescale)

    def _parse_formats(self, info: Any, raw_vid: set, raw_aud: set, raw_txt: set):
        formats = info.get("formats", [])
        for f in formats:
            if f.get("vcodec") != "none":
                res = f.get("height")
                width = f.get("width", 0)
                vbr = f.get("vbr")
                bps = (
                    int(vbr * 1000)
                    if vbr
                    else (int(f["format_id"]) if f["format_id"].isdigit() else 0)
                )
                codec_raw = f.get("vcodec", "Unknown")
                codec = "H264" if codec_raw.startswith("avc1") else codec_raw

                if res:
                    raw_vid.add((res, width, bps, codec, f["format_id"]))

            if f.get("acodec") != "none":
                lang_code = f.get("language", "unk")
                try:
                    lang_name = Language(lang_code).name
                except ValueError:
                    lang_name = lang_code

                codec_raw = f.get("acodec", "Unknown")
                codec = "AACL" if codec_raw.startswith("mp4a") else codec_raw
                asr = f.get("asr", 48000) or 48000
                channels = f.get("audio_channels", 2) or 2

                fmt_parts = f["format_id"].split("-")
                fallback_bps = (
                    int(fmt_parts[-1]) * 1000
                    if len(fmt_parts) > 1 and fmt_parts[-1].isdigit()
                    else 256000
                )
                abr = f.get("abr")
                bps = int(abr * 1000) if abr else fallback_bps

                raw_aud.add((lang_name, codec, asr, channels, bps, f["format_id"]))

        for yt_lang in info.get("subtitles", {}).keys():
            game_lang = LanguageMap.get_key(yt_lang, yt_lang)
            try:
                lang_name = Language(yt_lang).name
            except ValueError:
                lang_name = yt_lang

            raw_txt.add((lang_name, game_lang, 256000))

    def _prompt_streams(
        self,
        valid_episodes: dict,
        total_duration_sec: float,
        raw_vid: set,
        raw_aud: set,
        raw_txt: set,
    ):
        avg_duration_sec = total_duration_sec / len(valid_episodes)

        qualities_list = {
            StreamType.Video: [],
            StreamType.Audio: [],
            StreamType.Text: [],
        }

        for res, width, bps, codec, format_id in sorted(
            raw_vid, key=lambda x: x[2], reverse=True
        ):
            size_bytes = (bps * avg_duration_sec) / 8
            size_str = humanize.naturalsize(size_bytes, binary=False)
            label = f"{res}p ({codec} - {width}x{res} @ {bps} bps) [~{size_str} / ep]"
            qualities_list[StreamType.Video].append((label, format_id))

        for lang_name, codec, asr, channels, bps, format_id in sorted(
            raw_aud, key=lambda x: (x[0], -x[4])
        ):
            size_bytes = (bps * avg_duration_sec) / 8
            size_str = humanize.naturalsize(size_bytes, binary=False)
            label = f"{lang_name} ({codec} - {asr}hz, 16-bit, {channels} channels @ {bps} bps) [~{size_str} / ep]"
            qualities_list[StreamType.Audio].append((label, format_id))

        for lang_name, t_lang, bps in sorted(raw_txt, key=lambda x: (x[0], -x[2])):
            label = f"{lang_name} (TTML - {t_lang}_captions)"
            qualities_list[StreamType.Text].append((label, t_lang))

        selected_streams = Prompt.select_streams(qualities_list)

        vid_sel = selected_streams.get(StreamType.Video, [])
        self.__fetch_video_resolutions = vid_sel if vid_sel else ["none"]

        aud_sel = selected_streams.get(StreamType.Audio, [])
        self.__fetch_audio_langs = aud_sel if aud_sel else ["none"]

        text_sel = selected_streams.get(StreamType.Text, [])
        self.__fetch_text_langs = text_sel if text_sel else ["none"]

        if self.__fetch_text_langs != ["none"]:
            self.__extract_subtitles = Prompt.extract_subtitles()
            if self.__extract_subtitles:
                self.__append_episode_title = Prompt.append_episode_title()

    def __process_episode(self, episode_id: str, url: str):
        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "http_headers": {"User-Agent": USER_AGENT},
        }

        task_extract = logger.progress_stream.add_task(
            f"Extracting stream formats for {episode_id} via yt-dlp...", total=None
        )
        with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
        logger.progress_stream.remove_task(task_extract)

        if self.__show_formats:
            self.__dump_formats(info)
            return

        video_ids, audio_ids, text_langs = self._select_format_ids(info)

        format_labels = {}
        for f in info.get("formats", []):
            fid = f.get("format_id")
            if fid in video_ids:
                res = f.get("height")
                format_labels[fid] = f"{res}p video" if res else "video"
            if fid in audio_ids:
                lang_code = f.get("language", "unk")
                lang_val = LanguageMap.get_value(lang_code, lang_code)
                try:
                    lang_name = Language(lang_val).name
                    format_labels[fid] = f"{lang_name} ({lang_code}) audio"
                except ValueError:
                    format_labels[fid] = f"{lang_code} audio"
                
        for lang in text_langs:
            lang_val = LanguageMap.get_value(lang, lang)
            try:
                lang_name = Language(lang_val).name
                format_labels[lang] = f"{lang_name} ({lang}) subtitles"
            except ValueError:
                format_labels[lang] = f"{lang} subtitles"

        logger.log(f"Selected Video Formats: {video_ids}")
        logger.log(f"Selected Audio Formats: {audio_ids}")
        logger.log(f"Selected Subtitle Languages: {text_langs}")

        self.__downloader.download(
            video_list=self.__video_list,
            episode_id=episode_id,
            manifest_url=url,
            episodes_path=self.__episodes_path,
            video_format_ids=video_ids,
            audio_format_ids=audio_ids,
            text_langs=text_langs,
            extract_subs=self.__extract_subtitles,
            append_ep_title=self.__append_episode_title,
            format_labels=format_labels,
        )

    def _select_format_ids(self, info: Any) -> tuple[list[str], list[str], list[str]]:
        video_ids = []
        audio_ids = []

        formats = info.get("formats", [])
        video_formats = [f for f in formats if f.get("vcodec") != "none"]
        audio_formats = [f for f in formats if f.get("acodec") != "none"]

        if not self.__fetch_video_resolutions and not self.__fetch_video_bitrates:
            if video_formats:
                video_ids.append(video_formats[-1]["format_id"])
        else:
            for f in video_formats:
                res = f"{f.get('height', 0)}p" if f.get("height") else None
                vbr = str(f.get("vbr", ""))

                if self.__fetch_video_resolutions and (
                    res in self.__fetch_video_resolutions
                    or f["format_id"] in self.__fetch_video_resolutions
                ):
                    video_ids.append(f["format_id"])
                elif (
                    self.__fetch_video_resolutions
                    and "all" in self.__fetch_video_resolutions
                ):
                    video_ids.append(f["format_id"])
                elif self.__fetch_video_bitrates and vbr in self.__fetch_video_bitrates:
                    video_ids.append(f["format_id"])

        if not self.__fetch_audio_langs and not self.__fetch_audio_bitrates:
            for f in audio_formats:
                if f.get("language") in ["eng", "enus"]:
                    audio_ids.append(f["format_id"])
        else:
            for f in audio_formats:
                lang = f.get("language", "")
                matched = False

                if self.__fetch_audio_langs:
                    if "all" in self.__fetch_audio_langs:
                        matched = True
                    elif f["format_id"] in self.__fetch_audio_langs:
                        matched = True
                    else:
                        for lang_prefix in self.__fetch_audio_langs:
                            if lang.startswith(lang_prefix) or lang_prefix.startswith(
                                lang
                            ):
                                matched = True

                if (
                    self.__fetch_audio_bitrates
                    and str(f.get("abr", "")) in self.__fetch_audio_bitrates
                ):
                    matched = True

                if matched:
                    audio_ids.append(f["format_id"])

        text_langs = self.__fetch_text_langs or []
        if not text_langs and not self.__fetch_text_bitrates:
            text_langs = ["enus"]
        if "all" in text_langs:
            text_langs = list(info.get("subtitles", {}).keys())

        video_ids = (
            list(set(video_ids)) if self.__fetch_video_resolutions != ["none"] else []
        )
        audio_ids = list(set(audio_ids)) if self.__fetch_audio_langs != ["none"] else []
        text_langs = text_langs if text_langs != ["none"] else []

        return video_ids, audio_ids, text_langs

    def __dump_formats(self, info: Any):
        logger.print("[cyan]Available Formats:[/cyan]")
        table = Table(title="Stream Formats")
        table.add_column("Type")
        table.add_column("ID")
        table.add_column("Resolution")
        table.add_column("Bitrate")
        table.add_column("Language")
        table.add_column("Codec")

        for f in info.get("formats", []):
            type_str = "Video" if f.get("vcodec") != "none" else "Audio"
            res = f"{f.get('height', 'N/A')}p" if f.get("height") else "N/A"
            bitrate = str(f.get("vbr", f.get("abr", "N/A")))
            table.add_row(
                type_str,
                f["format_id"],
                res,
                bitrate,
                f.get("language", "N/A"),
                f.get("vcodec", f.get("acodec", "N/A")),
            )

        logger.print(table)
