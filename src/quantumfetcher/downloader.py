from pathlib import Path
from typing import Any, cast

import yt_dlp

from quantumfetcher.constants import USER_AGENT
from quantumfetcher.enumerators.language import LanguageMap
from quantumfetcher.logger import logger
from quantumfetcher.manifest import generate_local_manifests
from quantumfetcher.media import post_process_media_file
from quantumfetcher.subtitles import extract_subtitles


class Downloader:
    def __init__(self):
        self.ydl_opts: dict[str, Any] = {
            "http_headers": {"User-Agent": USER_AGENT},
            "allow_unplayable_formats": True,
            "retries": 10,
            "fragment_retries": 10,
            "no_warnings": True,
            "quiet": True,
            "noprogress": True,
        }

    def _create_hook(self, media_name: str, label: str = "", hide_size_estimation: bool = False):
        display_name = f"{label} ({media_name})" if label else media_name
        task_id = logger.progress_media.add_task(
            f"Downloading {display_name}...", total=None, speed="", eta="-:--:--"
        )

        def yt_dlp_hook(d):
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = None if hide_size_estimation else (d.get("total_bytes") or d.get("total_bytes_estimate"))

                speed = d.get("_speed_str", "").strip()
                
                eta_val = d.get("eta")
                if eta_val is not None and not hide_size_estimation:
                    eta_sec = int(eta_val)
                    h, rem = divmod(eta_sec, 3600)
                    m, s = divmod(rem, 60)
                    eta = f"{h}:{m:02d}:{s:02d}"
                else:
                    eta = "-:--:--"

                kwargs = {"completed": downloaded, "speed": speed, "eta": eta}
                if total is not None:
                    kwargs["total"] = total

                cast(Any, logger.progress_media).update(task_id, **kwargs)
            elif d["status"] == "finished":
                total = d.get("total_bytes") or d.get("downloaded_bytes") or 0
                cast(Any, logger.progress_media).update(
                    task_id, description=f"Downloaded {display_name}", completed=total, total=total, speed="", eta="-:--:--"
                )

        return yt_dlp_hook

    def download(
        self,
        video_list,
        episode_id: str,
        manifest_url: str,
        episodes_path: Path,
        video_format_ids: list[str],
        audio_format_ids: list[str],
        text_langs: list[str],
        extract_subs: bool,
        append_ep_title: bool = False,
        format_labels: dict[str, str] = None,
    ):
        if format_labels is None:
            format_labels = {}
        logger.clear_media_tasks()

        episode_dir = episodes_path / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)

        base_name = episode_id
        if episode_id in video_list.episode_list:
            url_path = video_list.episode_list[episode_id].split("?")[0]
            parts = url_path.split("/")
            for part in parts:
                if part.endswith(".ism"):
                    base_name = part.replace(".ism", "")
                    break

        total_streams = len(video_format_ids) + len(audio_format_ids) + len(text_langs)
        task_stream = logger.progress_stream.add_task(
            f"Downloading {episode_id} streams...", total=total_streams
        )

        self._download_video(
            base_name,
            manifest_url,
            episode_dir,
            video_format_ids,
            task_stream,
            format_labels,
        )
        self._download_audio(
            base_name,
            manifest_url,
            episode_dir,
            audio_format_ids,
            task_stream,
            format_labels,
        )
        self._download_subtitles(
            episode_id,
            base_name,
            manifest_url,
            episode_dir,
            text_langs,
            extract_subs,
            task_stream,
            append_ep_title,
            format_labels,
        )

        logger.progress_stream.remove_task(task_stream)

        logger.log("--- Generating Local Manifests ---")
        try:
            generate_local_manifests(
                manifest_url=manifest_url,
                episode_dir=episode_dir,
                base_name=base_name,
                video_format_ids=video_format_ids,
                audio_format_ids=audio_format_ids,
                text_langs=text_langs,
            )
        except Exception as e:
            logger.error(f"Failed to generate manifests: {e}")

    def _download_video(
        self,
        base_name,
        manifest_url,
        episode_dir,
        video_format_ids,
        task_stream,
        format_labels,
    ):
        for fmt_id in video_format_ids:
            filename = f"{base_name}_{fmt_id}.ismv"
            out_path = episode_dir / filename
            if out_path.exists():
                logger.log(
                    f"Skipping video {filename}, already exists."
                )
                self._post_process(out_path)
                logger.progress_stream.update(task_stream, advance=1)
                continue

            opts: dict[str, Any] = dict(self.ydl_opts)
            opts["format"] = fmt_id
            opts["outtmpl"] = str(out_path)
            label = format_labels.get(fmt_id, "video")
            opts["progress_hooks"] = [self._create_hook(filename, label=label)]

            logger.log(f"--- Downloading Video: {filename} ---")
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                ydl.download([manifest_url])
            self._post_process(out_path)

            logger.progress_stream.update(task_stream, advance=1)

    def _download_audio(
        self,
        base_name,
        manifest_url,
        episode_dir,
        audio_format_ids,
        task_stream,
        format_labels,
    ):
        for fmt_id in audio_format_ids:
            lang = fmt_id.split("-")[0] if "-" in fmt_id else fmt_id
            filename = f"{base_name}_{lang}.isma"
            out_path = episode_dir / filename
            if out_path.exists():
                logger.log(
                    f"Skipping audio {filename}, already exists."
                )
                self._post_process(out_path)
                logger.progress_stream.update(task_stream, advance=1)
                continue

            opts: dict[str, Any] = dict(self.ydl_opts)
            opts["format"] = fmt_id
            opts["outtmpl"] = str(out_path)
            label = format_labels.get(fmt_id, "audio")
            opts["progress_hooks"] = [self._create_hook(filename, label=label)]

            logger.log(f"--- Downloading Audio: {filename} ---")
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                ydl.download([manifest_url])
            self._post_process(out_path)

            logger.progress_stream.update(task_stream, advance=1)

    def _download_subtitles(
        self,
        episode_id,
        base_name,
        manifest_url,
        episode_dir,
        text_langs,
        extract_subs,
        task_stream,
        append_ep_title,
        format_labels,
    ):
        if not text_langs:
            return

        for lang in text_langs:
            filename = f"{base_name}_{lang}_cc.ismt"
            out_path = episode_dir / filename

            if out_path.exists():
                logger.log(f"Skipping subtitles {filename}, already exists.")
                if extract_subs:
                    self._extract_subtitles_helper(episode_id, lang, filename, out_path, append_ep_title)
                logger.progress_stream.update(task_stream, advance=1)
                continue

            yt_lang = LanguageMap.get_value(lang, lang) or lang

            logger.log(f"--- Downloading Subtitles: {filename}...")
            opts: dict[str, Any] = dict(self.ydl_opts)
            opts["skip_download"] = True
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = [yt_lang]
            label = format_labels.get(lang, "subtitles")
            opts["progress_hooks"] = [self._create_hook(filename, label=label, hide_size_estimation=True)]

            base_out_path = episode_dir / f"{base_name}_{lang}_cc"
            opts["outtmpl"] = str(base_out_path) + ".%(ext)s"

            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                ydl.download([manifest_url])

            ytdlp_file = episode_dir / f"{base_name}_{lang}_cc.{yt_lang}.ismt"
            if ytdlp_file.exists():
                ytdlp_file.rename(out_path)
                self._post_process(out_path)
            else:
                logger.log(f"Failed to find downloaded subtitle for {lang} ({yt_lang})")

            if extract_subs and out_path.exists():
                self._extract_subtitles_helper(episode_id, lang, filename, out_path, append_ep_title)

            logger.progress_stream.update(task_stream, advance=1)

    def _extract_subtitles_helper(
        self, episode_id: str, lang: str, filename: str, out_path: Path, append_ep_title: bool = False
    ):
        logger.log(f"Extracting subtitles for {filename}...")
        try:
            ep_num = (
                int(episode_id[1])
                if episode_id.startswith("J") and len(episode_id) > 1
                else 0
            )
        except ValueError:
            ep_num = 0

        track_name = f"{lang}_captions"
        extract_subtitles(out_path, ep_num, track_name, append_ep_title)

    def _post_process(self, out_path: Path):
        logger.log(f"Post processing {out_path.name}...")
        task_id = logger.progress_media.add_task(
            f"Post processing {out_path.name}...", total=None, speed="", eta=""
        )
        try:
            post_process_media_file(out_path)
        finally:
            logger.progress_media.remove_task(task_id)

