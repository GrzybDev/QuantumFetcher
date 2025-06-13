import operator

from quantumfetcher.dataclasses.AudioStream import AudioStream
from quantumfetcher.dataclasses.TextStream import TextStream
from quantumfetcher.dataclasses.VideoStream import VideoStream
from quantumfetcher.surveys import get_episodes
from quantumfetcher.videolist import VideoList


def print_available_formats(videoListPath, episodes):
    videoList = VideoList(videoListPath)

    if episodes == "all":
        episode_ids = videoList.get_episode_list()
    elif episodes:
        episode_ids = [e.strip() for e in (episodes or "").split(",") if e.strip()]
    else:
        episode_ids = videoList.get_episode_list()

    _, manifests = get_episodes(videoList=videoList, selected_episodes=episode_ids)

    video_set = set()
    audio_set = set()
    text_set = set()

    for episode_id in episode_ids:
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

    print(
        "Available video formats:\n",
        "\n".join([f"- {v}" for v in make_video_streams(video_set)]),
    )
    print(
        "Available audio languages:\n",
        "\n".join(
            [f"- {a} [{a.language.value}]" for a in make_audio_streams(audio_set)]
        ),
    )
    print(
        "Available text formats:\n",
        "\n".join([f"- {t} [{t.language.value}]" for t in make_text_streams(text_set)]),
    )
