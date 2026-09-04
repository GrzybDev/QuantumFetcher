# Quantum Fetcher

Tool for fetching Quantum Break live action episodes for offline in-game playback

Table of Contents
-----------------
- [Game Info](#game-info)
- [Legal notes](#legal-notes)
- [Features](#features)
- [Requirements](#build-requirements)
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

- Download all Quantum Break Live Action episodes in selected languages and bitrates for offline in-game playback.
- Text streams extraction to SubRip (.srt)
- Dump contents of `videoList.rmdj`
- Patch `videoList.rmdj` to point to custom [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) compatible server.
- Build `videoList.rmdj` from any JSON file.

Requirements
------------

- Python 3.10+

Installing
----------

Either use compiled portable build for Windows or Linux from [Releases](https://github.com/GrzybDev/QuantumFetcher/releases) page or use your python package management system (like `pipx` or `uv`)

Example:
`pipx install git+https://github.com/GrzybDev/QuantumFetcher.git`

Usage
-----

```sh
quantumfetcher --help
```

Quantum Fetcher is split into two command groups: `download` (fetching episodes) and `videolist` (managing the `videoList.rmdj` manifest).

### Downloading episodes

```sh
quantumfetcher download [PATH] [OPTIONS]
```

`PATH` is the root game folder. You can run this command in interactive mode or non-interactive mode.

By default, if no filters are provided then english audio and subtitles will be downloaded with highest quality video stream.

The tool automatically falls back to interactive mode (prompting for the game folder, episodes, and stream quality/languages) whenever `PATH` or a filter option below is omitted — there is no separate flag to request it.

| Parameter          | Description                                                        | Default value                    |
|--------------------:|:-------------------------------------------------------------------|:----------------------------------|
| --videolist-path    | Path to videoList.rmdj file                                        | data/videoList.rmdj inside PATH   |
| --episodes-path     | Path to where episodes will be saved                                | videos/episodes inside PATH       |
| --retries           | Number of retries for stream and fragment downloads                 | 10                                |

Supported filters are provided below:

| Parameter             | Description                                           |
|----------------------:|:------------------------------------------------------|
| --episodes            | Comma-separated list of episode IDs to download       |
| --video-resolutions   | Comma-seperated list of video resolutions to download |
| --video-bitrates      | Comma-seperated list of video bitrates to download    |
| --audio-languages     | Comma-seperated list of audio languages to download   |
| --audio-bitrates      | Comma-seperated list of audio bitrates to download    |
| --text-languages      | Comma-seperated list of text languages to download    |
| --text-bitrates       | Comma-seperated list of text bitrates to download     |

*Note: All filters support `all` value (Example: `--audio-languages all` will download audio tracks in all languages)*

You can view available formats (bitrates, languages etc.) by running the `download` command with the `--show-formats` flag.

Running the `download` command with the `--extract-subtitles` flag will extract text streams to SubRip format (.srt) usable by [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git). Add `--append-episode-title` to also append the episode title to the extracted subtitles.

### Managing videoList.rmdj

This tool can also patch the original `videoList.rmdj` file to make the game point to a [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) compatible server:

```sh
quantumfetcher videolist patch [PATH]
```

By default, it will update `videoList.rmdj` to point to `127.0.0.1:10000`. You can change the default to any other host that is compatible with [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) via `--server`/`-s`.

You can also build the `videoList.rmdj` file from scratch from a JSON file:

```sh
quantumfetcher videolist build INPUT_JSON --path PATH
```

You can specify the output path for the built file via `--videolist-path`.

In order to dump the contents of a `videoList.rmdj` file, use:

```sh
quantumfetcher videolist dump [PATH] --output OUTPUT_JSON
```

You can also print the contents to console by setting `--output`/`-o` to `-`.

In order to be able to use downloaded episodes, you need to install [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git).

Credits
-------

- [GrzybDev](https://grzyb.dev)

Special thanks to:
- Remedy Entertainment (for making the game)
- Microsoft Studios (for publishing the game on PC)
- [r00t0](https://github.com/cleverzaq) - For help with decoding `videoList.rmdj`
