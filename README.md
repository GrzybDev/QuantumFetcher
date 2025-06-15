# Quantum Fetcher

Simple tool for fetching Quantum Break live action episodes for offline in-game playback.

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
- Text streams extraction to JSON

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

You can run this tool in interactive mode or non-interactive mode.

In order to run this tool in interactive mode, you just have to launch this tool providing path to game files.

Example:
```
quantumstreamer G:\SteamLibrary\steamapps\common\QuantumBreak
```

In interactive mode, you will be asked which episodes you want to download, in which quality, languages etc.

Both interactive mode and non-interactive mode supports these two optional parameters:

| Parameter         | Description                                                                                           | Default value         |
|------------------:|:-----------------------------------------------------------------------------------------------------:|:----------------------|
| --videolist-path  | Relative path to videoList.rmdj file (will also additionally check if filename_original.rmdj exist)   | data/videoList.rmdj   |
| --episodes-path   | Relative output path to where episode data will be downloaded                                         | videos/episodes       |

Non-interactive mode is launched by providing `--episodes` argument.
By default, if no filters are provided then english audio and subtitles will be downloaded with highest quality video stream.

Supported filters are provided below:

| Parameter             | Description                                           |
|----------------------:|:------------------------------------------------------|
| --episodes            | Comma-separated list of episode IDs to download       |
| --video-bitrates      | Comma-seperated list of video bitrates to download    |
| --audio-langs         | Comma-seperated list of audio languages to download   |
| --audio-bitrates      | Comma-seperated list of audio bitrates to download    |
| --text-langs          | Comma-seperated list of text languages to download    |
| --text-bitrates       | Comma-seperated list of text bitrates to download     |
| --extract-subtitles   | Extract subtitles to JSON file                        |

*Note: All filters other than `--extract-subtitles` support `all` value (Example: `--audio-langs all` will download audio tracks in all languages)*

You can view available formats (bitrates, languages etc.) by running Quantum Fetcher with `--show-formats` flag.

This tool also can patch original `videoList.rmdj` file to make game point to [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git) compatible server.

To patch `videoList.rmdj` run this tool with `--patch-videolist` flag, by default, it will update videoList.rmdj to point to `127.0.0.1:10000`, which is the default for [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git).

You can change the default to any other host that is compatible with [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git), to do that just set `--patch-videolist-server`.

Additionally, you can print decrypted videoList.rmdj in console via `--dump-videolist` flag.

In order to be able to use downloaded episodes, you need to install [QuantumStreamer](https://github.com/GrzybDev/QuantumStreamer.git).

Credits
-------

- [GrzybDev](https://grzyb.dev)

Special thanks to:
- Remedy Entertainment (for making the game)
- Microsoft Studios (for publishing the game on PC)
- [r00t0](https://github.com/cleverzaq) - For help with decoding `videoList.rmdj`
