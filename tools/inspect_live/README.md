# Stage 1 Live Inspector & Auto-Reroller

A self-contained tool for Megabonk that evaluates Stage 1 seeds, automatically rerolls until desired thresholds and target Shady Guy offerings are met, and records comprehensive map and offering data.

## Directory Layout

`
tools/inspect_live/
├── inspect_live.py         # Main inspector & auto-reroll loop (relative paths)
├── analyze_seeds.py        # Seed dataset analyzer (relative paths)
├── run.bat                 # Quick launch batch script for Windows
├── artifacts/              # Generated outputs and datasets
│   └── shady_seed_data.json# Seed records, offerings, map sectors, and evaluation criteria
└── dependencies/           # Self-contained code dependencies
    ├── requirements.txt    # Pip packages (pymem, keyboard, pywin32, rich, pandas, numpy)
    ├── core/               # Domain data structures and metadata
    └── infra/memory/       # Memory reader and clients
`

## Features

- **Stage 1 Seed Filter**: Scans spawned shrines and Shady Guys in memory upon Stage 1 start.
- **Threshold Criteria**:
  1. Shady Guys + Moai Shrines >= 9
  2. Microwaves >= 2 (Both must be White / Tier 0; reports color tier, map sector, and distance)
  3. Boss Curses >= 1
  4. Magnet Curses >= 2
  5. Target Items / Rules: Disabled (optional tracking; Anvil, Dragonfire, Spicy Meatball, Soul Harvester, Kevin + Electric Plug, 2x Echo Shard, Power Gloves, 2x Beefy Ring)
- **Microwave Map Scanning**: Scans active map microwaves in real time, detecting color tier (White/Blue/Purple/Gold), distance from spawn, and map sector.
- **Auto-Restart on Failure**: Holds quick reset hotkey (auto-detected from game settings) if criteria fail.
- **Pause on Match**: Automatically presses Escape when a perfect seed is found.
- **Toggle Hotkey**: Press **F6** at any time to toggle auto-restart ON/OFF.
- **Dataset Recording**: Records all evaluation criteria, microwave colors/locations, map sectors, distances, and offered items per reroll to `artifacts/shady_seed_data.json`.
- **Statistical Analyzer**: Run `python analyze_seeds.py` to view pass rates, item frequencies, pricing statistics, microwave color distributions, and map sector distributions.

## Usage

From within this folder:
`powershell
python inspect_live.py
`

To analyze recorded seeds:
`powershell
python analyze_seeds.py
`
