# QuantumFetcher

A command-line tool that downloads the live-action episodes of Quantum Break into the game folder, where
[QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer) plays them offline in the game.

Table of Contents
-----------------

- [Game Info](#game-info)
- [Legal notes](#legal-notes)
- [Features](#features)
- [Requirements](#requirements)
- [Installing](#installing)
- [Usage](#usage)
- [File formats](#file-formats)
- [Development](#development)
- [Credits](#credits)

Game Info
---------

![Quantum Break Cover](https://upload.wikimedia.org/wikipedia/en/d/d9/Quantum_Break_cover.jpg "Quantum Break Cover")

|         Type | Value                                                        |
|-------------:|:-------------------------------------------------------------|
| Developer(s) | Remedy Entertainment                                         |
| Publisher(s) | Microsoft Studios                                            |
|  Director(s) | Sam Lake, Mikael Kasurinen                                   |
|  Producer(s) | Miloš Jeřábek                                                |
|       Engine | Northlight Engine                                            |
|  Platform(s) | Windows, Xbox One                                            |
|     Genre(s) | Action-adventure, third-person shooter                       |
|      Mode(s) | Single-player                                                |

Legal notes
-----------

- The project includes no original assets from the game. The episodes are downloaded from the game's own streaming
  server.
- You need an original copy of the game, such as the one on
  [Steam](https://store.steampowered.com/app/474960/Quantum_Break/). The project neither makes piracy easier nor
  breaks the game's DRM.
- QuantumFetcher is not affiliated with or endorsed by Remedy Entertainment or Microsoft.

Features
--------

- Download the live-action episodes in the chosen video qualities, audio languages and captions for offline playback
  through QuantumStreamer
- Pick episodes and tracks on the command line with selectors such as `best`, `1080p`, a bitrate, a stream name or a
  language, or from lists in the terminal
- List the tracks the episodes offer, with their estimated sizes and the selectors that pick them (`formats`)
- Resume interrupted downloads from the last whole fragment and keep finished tracks
- Add tracks to downloaded episodes later, such as another audio language
- Download only the captions of an episode, which keeps streaming from the server
- Save captions as SubRip (`.srt`) files that QuantumStreamer shows instead, optionally with the episode title, without
  overwriting edited ones
- Dump `videoList.rmdj` to JSON (`videolist dump`)
- Patch `videoList.rmdj` to point the game at a QuantumStreamer compatible server, keeping the game's own list
  (`videolist patch`)
- Build `videoList.rmdj` from JSON, keeping a copy of the list it replaces (`videolist build`)

Requirements
------------

- Python 3.14+, when installing from the repository
- [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer) in the game, to play the downloaded episodes

Installing
----------

Portable builds for Windows, Linux and macOS are on the [Releases](https://github.com/GrzybDev/QuantumFetcher/releases)
page; the Windows build is code-signed. You can also install the tool from the repository with uv (or pipx):

```sh
uv tool install git+https://github.com/GrzybDev/QuantumFetcher
```

Usage
-----

```sh
quantumfetcher --help
python -m quantumfetcher --help
```

Every command has its own help, such as `quantumfetcher download --help`. The commands share these conventions:

- `path/to/QuantumBreak` is the game folder, the one holding `data` and `videos`. When it is left out, the command
  asks for it in a terminal. Without a terminal it stops with
  `No game folder given, and none is asked for without a terminal`, and with `download --yes` with
  `No game folder given, and none is asked for with --yes`, unless the options give every path the folder would be
  used for. A command counts as run in a terminal when both its input and its output are one.
- The episodes are read from `data/videoList.rmdj` in the game folder, or from `data/videoList_original.rmdj` once the
  list is patched, since only that copy keeps the episodes' own URLs. `--videolist-path` reads another file instead.
- `-e`, `--episodes` takes comma-separated episode IDs, in any letter case, or `all`. An ID the list does not have
  stops the command with `The video list has no episode <ID>`.
- `--retries` retries requests that fail in a way that may pass (timeouts, lost connections and HTTP 408, 429, 500,
  502, 503 and 504) after waiting 1, 2, 4, 8 and 16 seconds, then 30 seconds each time. `--workers` sets how many
  requests run at once. Requests identify themselves as `QuantumFetcher/<version> (<system>)`.
- An episode whose manifest cannot be fetched or read is skipped with a warning; when none can be fetched, the command
  stops with `No episode could be fetched`.
- Progress, logs and errors go to stderr, results to stdout. Errors are printed as `Error: <message>` and exit with
  code 1; invalid arguments, such as a game folder that does not exist, exit with code 2.

### Downloading episodes

```sh
quantumfetcher download [path/to/QuantumBreak] [-e IDS] [--video SELECTORS] [--audio SELECTORS] [--text SELECTORS] [--extract-subtitles] [--append-episode-title] [-y]
```

The command fetches the manifests of the chosen episodes, picks their tracks and saves each episode in its own folder,
`videos/episodes/<episode ID>`, where QuantumStreamer looks for it. In a terminal it asks for what the command line
leaves out: the game folder, the episodes, the video, audio and caption tracks (listing each option with its estimated
size, how many episodes offer it when not all do, and the defaults ticked), whether to save the captions as subtitles
and whether to add the episode title to them. With `--yes`, or without a terminal, it uses the defaults below instead.

|                                                Option | Description                                                            | Default                                               |
|------------------------------------------------------:|:-----------------------------------------------------------------------|:------------------------------------------------------|
|                                `path/to/QuantumBreak` | The game folder                                                        | asked for                                             |
|             `--videolist-path path/to/videoList.rmdj` | The video list to read the episodes from                               | the game's list, or its `_original` copy once patched |
|                    `--episodes-path path/to/episodes` | The folder to save the episodes in                                     | `videos/episodes` in the game folder                  |
|                                `-e`, `--episodes IDS` | Comma-separated episode IDs, or `all`                                  | asked for, else `all`                                 |
|                                   `--video SELECTORS` | Comma-separated video selectors                                        | asked for, else `best`                                |
|                                   `--audio SELECTORS` | Comma-separated audio selectors                                        | asked for, else `enus`                                |
|                                    `--text SELECTORS` | Comma-separated caption selectors                                      | asked for, else `enus`                                |
|       `--extract-subtitles`, `--no-extract-subtitles` | Save the captions as SubRip files, which QuantumStreamer shows instead | asked for when captions are picked, else off          |
| `--append-episode-title`, `--no-append-episode-title` | Add the episode title to the saved subtitles                           | asked for when subtitles are saved, else off          |
|                                         `--retries N` | Times to retry a failed request                                        | `10`                                                  |
|                                         `--workers N` | Requests to make at once                                               | `8`                                                   |
|                                         `-y`, `--yes` | Use the defaults instead of asking                                     | off                                                   |

A selector picks the tracks it names, in any letter case:

|                Selector | Picks                                                  |
|------------------------:|:-------------------------------------------------------|
|                  `best` | The track with the highest bitrate in each episode     |
|           `all`, `none` | Every track, no track                                  |
|                 `1080p` | The video tracks of that height                        |
|              `12000000` | The tracks of that bitrate                             |
| `enus`, `enus_captions` | The tracks of a stream, by its locale or its full name |
|                   `eng` | The tracks in that ISO 639-2 language                  |

A selector that picks no track in any of the episodes stops the command with
`No audio track matches <selector>; the formats command lists them` (or video, or text); `best` and `none` are always
accepted. An episode in which the selectors pick no track is skipped, and when they pick none at all the command stops
with `The selectors pick no tracks to download`. In a terminal, ticking no episode stops it with `No episodes chosen`.

Each track is downloaded to a `.part` file first, so an interrupted download (Ctrl+C included) carries on where it
stopped when the command runs again. Tracks whose files exist are kept and not downloaded again.

Once the episode folder holds a video and an audio track, the episode's manifests are written, and QuantumStreamer
plays the episode from them instead of the server's. They offer every track in the folder, also those of earlier
downloads, so another language can be added later. An episode without both keeps streaming from the server, which
lets you download only the captions of an episode to translate them. QuantumStreamer plays an episode from a single
server manifest, so any other `.ism` file in the folder, such as one an older version of this tool wrote under another
name, is renamed to `.ism.old`.

Existing `.srt` files are never overwritten, as they may hold edited or translated captions; delete one to save it
again. With `--append-episode-title`, the subtitles also show the episode's title while its title card is on screen.

An episode that fails is reported and the others carry on; the command then ends with
`Could not download <n> of <m> episodes: <IDs>` and exit code 1. Otherwise it ends with
`Saved <n> tracks to <folder>, with <n> of <m> episodes playable offline`, counting only the tracks this run saved.
Subtitles that cannot be saved leave their episode saved; the command then also reports
`Could not save the subtitles of <n> of <m> episodes: <IDs>` and ends with exit code 1.

For example, to download episode `J1A` in 1080p at 12 Mbps with English and Spanish (Mexico) audio, English captions
and their subtitles with the episode title:

```sh
quantumfetcher download path/to/QuantumBreak -e J1A --video 12000000 --audio enus,esmx --text enus --extract-subtitles --append-episode-title
```

```text
Saved 4 tracks to path/to/QuantumBreak/videos/episodes, with 1 of 1 episode playable offline
```

QuantumStreamer reads the episodes from its `Server.EpisodesPath` setting, `./videos/episodes` by default; when you
save them elsewhere with `--episodes-path`, point that setting at the same folder.

### Listing the tracks

```sh
quantumfetcher formats [path/to/QuantumBreak] [-e IDS]
```

The command fetches the manifests of the episodes, all of them unless `-e` names some, and prints a table of the
tracks they offer: the type, the selector that picks the track, what it holds, its estimated size per episode
(averaged over the episodes, from its bitrate and length) and the number of episodes that offer it. Captions get no
size estimate, as their declared bitrate is far above what their text takes. `best` comes first, then video by
falling bitrate, then audio and captions in the manifest's order. The command never asks for episodes.

|                                    Option | Description                              | Default                                               |
|------------------------------------------:|:-----------------------------------------|:------------------------------------------------------|
|                    `path/to/QuantumBreak` | The game folder                          | asked for                                             |
| `--videolist-path path/to/videoList.rmdj` | The video list to read the episodes from | the game's list, or its `_original` copy once patched |
|                    `-e`, `--episodes IDS` | Comma-separated episode IDs, or `all`    | `all`                                                 |
|                             `--retries N` | Times to retry a failed request          | `10`                                                  |
|                             `--workers N` | Requests to make at once                 | `8`                                                   |

For example, the tracks of `J1A`, shortened:

```sh
quantumfetcher formats path/to/QuantumBreak -e J1A
```

```text
┌───────┬───────────────┬────────────────────────────────────────┬──────────────────┬──────────┐
│ Type  │ Selector      │ Track                                  │ Size per episode │ Episodes │
├───────┼───────────────┼────────────────────────────────────────┼──────────────────┼──────────┤
│ video │ best          │ The highest bitrate of each episode    │ ~3.8 GB          │ 1        │
│ video │ 20000000      │ 2160p, 3840x2160 H264, 20.0 Mbps       │ ~3.8 GB          │ 1        │
│ video │ 12000000      │ 1080p, 1920x1080 H264, 12.0 Mbps       │ ~2.3 GB          │ 1        │
│ ...   │               │                                        │                  │          │
│ video │ 512000        │ 360p, 640x360 H264, 0.5 Mbps           │ ~96.2 MB         │ 1        │
│ audio │ enus          │ English, AACL 6 ch 48 kHz, 256 kbps    │ ~48.1 MB         │ 1        │
│ audio │ esmx          │ Spanish, AACL 6 ch 48 kHz, 256 kbps    │ ~48.1 MB         │ 1        │
│ ...   │               │                                        │                  │          │
│ text  │ enus_captions │ English, TTML                          │                  │ 1        │
│ text  │ esmx_captions │ Spanish, TTML                          │                  │ 1        │
│ ...   │               │                                        │                  │          │
└───────┴───────────────┴────────────────────────────────────────┴──────────────────┴──────────┘
```

### Dumping the video list

```sh
quantumfetcher videolist dump [path/to/QuantumBreak] [-o path/to/videoList.json]
```

The command decrypts the video list and prints it as JSON indented with four spaces, or saves it to the file `-o`
names, as UTF-8 with a line end after the last line. Once the list is patched, it dumps the kept original, which holds
the episodes' own URLs; give `--videolist-path` to dump another file, such as the patched list.

|                                    Option | Description                               | Default                                               |
|------------------------------------------:|:------------------------------------------|:------------------------------------------------------|
|                    `path/to/QuantumBreak` | The game folder                           | asked for                                             |
| `--videolist-path path/to/videoList.rmdj` | The video list to dump                    | the game's list, or its `_original` copy once patched |
|   `-o`, `--output path/to/videoList.json` | The JSON file to save to, or `-` to print | print                                                 |

For example:

```sh
quantumfetcher videolist dump path/to/QuantumBreak -o videoList.json
```

```text
Saved 45 episodes to videoList.json
```

### Patching the video list

```sh
quantumfetcher videolist patch [path/to/QuantumBreak] [-s HOST:PORT]
```

The command points every episode of `data/videoList.rmdj` at a QuantumStreamer compatible server, as
`http://HOST:PORT/<episode ID>/manifest`. The first time, it keeps the game's list as `data/videoList_original.rmdj`,
where QuantumStreamer and the other commands read the episodes' own URLs from. Patching again starts from that copy,
so it can point the list at another server. To undo the patch, copy `videoList_original.rmdj` back over
`videoList.rmdj` or verify the game files in Steam.

QuantumStreamer patches the list itself when the game starts unless its `VideoList.PatchFile` setting is off. With it
off, set QuantumStreamer's `Server.Port` to a fixed port, since its default of 0 picks a free port at every start, and
patch the list with that port.

|                                    Option | Description                     | Default                                  |
|------------------------------------------:|:--------------------------------|:-----------------------------------------|
|                    `path/to/QuantumBreak` | The game folder                 | asked for                                |
| `--videolist-path path/to/videoList.rmdj` | The video list to patch         | `data/videoList.rmdj` in the game folder |
|                `-s`, `--server HOST:PORT` | The host and port of the server | `127.0.0.1:10000`                        |

For example:

```sh
quantumfetcher videolist patch path/to/QuantumBreak -s 127.0.0.1:10000
```

```text
Pointed 45 episodes at http://127.0.0.1:10000, keeping the list as videoList_original.rmdj
```

### Building the video list

```sh
quantumfetcher videolist build path/to/videoList.json [path/to/QuantumBreak]
```

The command encrypts a JSON object that maps episode IDs to manifest URLs, in UTF-8 or UTF-16, and saves it as the
video list the episodes are read from: `data/videoList_original.rmdj` once the list is patched, else
`data/videoList.rmdj`. The first time it replaces a list, it keeps that list beside it as `<list>.old`, such as
`videoList.rmdj.old`. A file that is not such an object stops the command with an error that names it.

|                                    Option | Description                  | Default                                               |
|------------------------------------------:|:-----------------------------|:------------------------------------------------------|
|                  `path/to/videoList.json` | The JSON file to build from  | required                                              |
|                    `path/to/QuantumBreak` | The game folder              | asked for                                             |
| `--videolist-path path/to/videoList.rmdj` | The file to save the list to | the game's list, or its `_original` copy once patched |

For example, to put back a list dumped earlier, in a game whose list is patched:

```sh
quantumfetcher videolist build videoList.json path/to/QuantumBreak
```

```text
Saved 45 episodes to path/to/QuantumBreak/data/videoList_original.rmdj
```

File formats
------------

Each episode is saved in its own folder, `videos/episodes/<episode ID>` in the game folder, laid out as QuantumStreamer
reads it. For `J1A`:

| File                          | Content                                                                                       | Format                                     |
|:------------------------------|:----------------------------------------------------------------------------------------------|:-------------------------------------------|
| `J1A_video_<bitrate>.ismv`    | A video track                                                                                 | [Track files](docs/track-files.md)         |
| `J1A_<stream>_<bitrate>.isma` | An audio track, such as `J1A_enus_256000.isma`                                                | [Track files](docs/track-files.md)         |
| `J1A_<stream>_<bitrate>.ismt` | A caption track                                                                               | [Track files](docs/track-files.md)         |
| `<track file>.part`           | A track being downloaded                                                                      | [Track files](docs/track-files.md)         |
| `J1A.ismc`                    | The client manifest QuantumStreamer serves to the game, offering the saved tracks             | [Client manifest](docs/client-manifest.md) |
| `J1A.ism`                     | The server manifest naming the client manifest and the file of each track                     | [Server manifest](docs/server-manifest.md) |
| `<stream>.srt`                | Subtitles QuantumStreamer shows instead of that caption stream's, such as `enus_captions.srt` | [Subtitles](docs/subtitles.md)             |
| `<name>.ism.old`              | Another server manifest, moved aside                                                          |                                            |

The JSON that `videolist dump` writes and `videolist build` reads is the decrypted content of `videoList.rmdj`: one
object that maps each episode ID to the URL of its client manifest.
[videoList.rmdj](docs/videolist-rmdj.md) describes the encryption, the layout and the copies the commands keep beside
the list.

Development
-----------

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
```

The tests use invented data and need neither the game nor a network connection.

Credits
-------

- [GrzybDev](https://grzyb.dev)

Thanks to:

- [r00t0](https://github.com/cleverzaq) (for help with decoding `videoList.rmdj`)

Special thanks to:

- Remedy Entertainment (for making the game)
- Microsoft Studios (for publishing the game on PC)
