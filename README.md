# Quantum Fetcher

Tool for fetching Quantum Break live action episodes for offline in-game playback

Table of Contents
-----------------
- [Game Info](#game-info)
- [Legal notes](#legal-notes)
- [Features](#features)
- [Requirements](#requirements)
- [Installing](#installing)
- [Usage](#usage)
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

- The project doesn't contain ***any*** original assets from the game!
- To use this project you need to have an original copy of the game (bought from [Steam](https://store.steampowered.com/app/474960/Quantum_Break/)), the project doesn't make piracy easier and doesn't break any of the DRM included in-game.

Features
--------

- Download Quantum Break live action episodes in the chosen qualities and languages for offline in-game playback through [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git).
- Resume interrupted downloads where they stopped.
- Save captions as SubRip (`.srt`) files, which QuantumStreamer shows instead of the original ones, so they can be edited or translated.
- Dump `videoList.rmdj` to JSON, build it from JSON, or patch it to point to a [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) compatible server.

Requirements
------------

- Python 3.14+

Installing
----------

Either use compiled portable build for Windows, Linux or macOS from [Releases](https://github.com/GrzybDev/QuantumFetcher/releases) page or use your python package management system (like `pipx` or `uv`)

Example:
`pipx install git+https://github.com/GrzybDev/QuantumFetcher.git`

Usage
-----

```sh
quantumfetcher --help
```

Every command takes the game folder (the one holding `data` and `videos`) as an optional argument, after `INPUT_JSON` for `videolist build`. When it is left out, the tool asks for it, unless the paths it would be used for are given as options.

### Downloading episodes

```sh
quantumfetcher download [GAME_DIR] [OPTIONS]
```

Anything left out on the command line is asked for interactively: the episodes, the tracks of each kind and whether to save subtitles. With `--yes` (or when the input is not a terminal) the defaults below are used instead.

| Option                    | Description                                                                     | Default                          |
|--------------------------:|:--------------------------------------------------------------------------------|:---------------------------------|
| `-e`, `--episodes`        | Comma-separated episode IDs, or `all`                                           | `all`                            |
| `--video`                 | Comma-separated video selectors                                                 | `best`                           |
| `--audio`                 | Comma-separated audio selectors                                                 | `enus`                           |
| `--text`                  | Comma-separated caption selectors                                               | `enus`                           |
| `--extract-subtitles`     | Save the captions as SubRip files                                               | off                              |
| `--append-episode-title`  | Add the episode title to the saved subtitles                                    | off                              |
| `--videolist-path`        | `videoList.rmdj` to read the episodes from                                      | `data/videoList.rmdj` in the game folder, or its `_original` copy once patched |
| `--episodes-path`         | Folder to save the episodes in                                                  | `videos/episodes` in the game folder |
| `--retries`               | Times to retry a failed request                                                 | 10                               |
| `--workers`               | Requests to make at once                                                        | 8                                |
| `-y`, `--yes`             | Use the defaults instead of asking                                              |                                  |

A selector picks the tracks it names:

| Selector                  | Picks                                                                           |
|--------------------------:|:--------------------------------------------------------------------------------|
| `best`                    | the track with the highest bitrate                                              |
| `all`, `none`             | every track, no track                                                           |
| `1080p`                   | the video tracks of that height                                                 |
| `12000000`                | the tracks of that bitrate                                                      |
| `enus`, `enus_captions`   | the tracks of that stream, by its locale or its full name                       |
| `eng`                     | the tracks in that ISO 639-2 language                                           |

To see the tracks the episodes offer and the selectors that pick them, run:

```sh
quantumfetcher formats [GAME_DIR] [-e EPISODES]
```

For example, to download the first episode in 1080p with English and Spanish (Mexico) audio, English captions and their subtitles:

```sh
quantumfetcher download GAME_DIR -e J1A --video 12000000 --audio enus,esmx --text enus --extract-subtitles
```

Each episode is saved in its own folder (such as `videos/episodes/J1A`), where QuantumStreamer looks for it:

| File                          | Contents                                                                    |
|:------------------------------|:----------------------------------------------------------------------------|
| `J1A_<stream>_<bitrate>.ismv`, `.isma`, `.ismt` | a video, audio or caption track, playable on its own        |
| `J1A.ism`, `J1A.ismc`         | the server and client manifests QuantumStreamer serves the tracks with      |
| `<stream>.srt`                | subtitles QuantumStreamer shows instead of that caption track's own         |

Tracks are downloaded to `.part` files first, so an interrupted download carries on where it stopped when run again, and finished tracks are kept. Existing `.srt` files are never overwritten, as they may hold edited or translated captions; delete one to save it again.

The manifests offer every track in the episode folder, also the ones of earlier downloads, so you can add a language later. They are only written once the folder holds both a video and an audio track, since QuantumStreamer plays an episode from its local manifests instead of the server's. That way you can download just the captions of episodes to translate them while still streaming the episodes themselves.

QuantumStreamer plays an episode from a single server manifest, so any other `.ism` file in the folder, such as one written by an older version of this tool under another name, is renamed to `.ism.old`. Older versions also named the tracks differently, so their tracks are downloaded again.

### Managing videoList.rmdj

This tool can also patch the original `videoList.rmdj` file to make the game point to a [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) compatible server:

```sh
quantumfetcher videolist patch [GAME_DIR] [--server HOST:PORT]
```

By default, it will update `videoList.rmdj` to point to `127.0.0.1:10000`. The original file is kept as `videoList_original.rmdj`, which is also where QuantumStreamer looks for it.

You can also build the `videoList.rmdj` file from a JSON object mapping episode IDs to manifest URLs. Once the list is patched, the built list is saved as `videoList_original.rmdj`, which is the one the episodes are read from:

```sh
quantumfetcher videolist build INPUT_JSON [GAME_DIR] [--videolist-path OUTPUT]
```

In order to dump the contents of a `videoList.rmdj` file as JSON, use:

```sh
quantumfetcher videolist dump [GAME_DIR] [--output OUTPUT_JSON]
```

Without `--output` (or with `--output -`) the contents are printed to the console.

In order to be able to use downloaded episodes, you need to install [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git).

Credits
-------

- [GrzybDev](https://grzyb.dev)

Special thanks to:
- Remedy Entertainment (for making the game)
- Microsoft Studios (for publishing the game on PC)
- [r00t0](https://github.com/cleverzaq) - For help with decoding `videoList.rmdj`
