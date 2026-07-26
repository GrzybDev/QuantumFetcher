from contextlib import contextmanager

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


class Logger:
    def __init__(self):
        self.console = Console(log_path=False)
        self._init_progress()

    def _init_progress(self):
        self.progress_overall = Progress(
            SpinnerColumn(finished_text="\u2713"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )

        self.progress_stream = Progress(
            SpinnerColumn(finished_text="\u2713"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        )

        self.progress_media = Progress(
            SpinnerColumn(finished_text="\u2713"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TextColumn("[progress.data.speed]{task.fields[speed]}"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TextColumn("[progress.remaining]{task.fields[eta]}"),
            console=self.console,
        )

        self.progress_group = Group(
            self.progress_overall, self.progress_stream, self.progress_media
        )

    def clear_media_tasks(self):
        for task_id in [task.id for task in self.progress_media.tasks]:
            self.progress_media.remove_task(task_id)

    def print(self, msg, **kwargs):
        self.console.print(msg, **kwargs)

    def log(self, msg: str, **kwargs):
        self.console.log(msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self.console.log(f"[red]{msg}[/red]", **kwargs)

    @contextmanager
    def live_overall(self):
        with Live(
            self.progress_overall, console=self.console, refresh_per_second=10
        ) as live:
            yield live

    @contextmanager
    def live_group(self):
        with Live(
            self.progress_group, console=self.console, refresh_per_second=10
        ) as live:
            yield live


logger = Logger()
