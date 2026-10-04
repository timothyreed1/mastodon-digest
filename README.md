# Mastodon Digest

Mastodon Digest is small self-hosted python tool that reads the last N hours 
of your Mastodon home timeline, asks an LLM to summarize it, and publishes the
result as an Atom.xml feed on your own web server so you can catch up in your 
RSS reader instead of having to catch up on the live timeline.

## Features

- Pulls your home timeline for a configurable window.
- Always includes posts from a list of priority accounts that you choose.
- Summarizes with LLM that can be steered towards your most important topics. 
  OpenAI, Anthropic, or a local Ollama model are currently supported.
- Publishes a single-entry Atom feed (`atom.xml`) over SSH to a folder you 
  specify on your own webhost. To subscribe, add the `atom.xml` URL to your
 RSS reader.
- Logs provider, model, and token counts for every run.

## Requirements

- Python 3 with `requests`, `markdown`, and `nh3` installed
- A `venv` is set up as part of install.
- A Mastodon account and token with `read:statuses`.
- An API key for your chosen LLM provider.
- A web host you can reach over SSH, to host the generated summary.

## Quick Start

Full step-by-step setup that includes the Mastodon token, LLM key, web host folder,
SSH key, install, and scheduling is in [INSTALL.md](INSTALL.md). The short version:

1. Copy `env_sample` to `.env` and fill in your values.
2. `chmod 600 .env`
3. `python3 -m venv venv && venv/bin/pip install requests markdown nh3`
4. `chmod 644 *.py`
5. `chmod +x run.sh && ./run.sh`
6. Subscribe your RSS reader to the `atom.xml` URL you configured.

## Files

| File | Purpose |
| --- | --- |
| `mastodon-digest.py` | Fetches the timeline and writes the summary. |
| `build_feed.py` | Rebuilds `atom.xml` with the latest summary. |
| `run.sh` | Wrapper that loads `.env`, runs both scripts, uploads over SSH. |
| `env_sample` | `.env` template for you to copy and customize |
| `INSTALL.md` | Detailed installation instructions. |

## Mandatory Environment Settings

The following variables must be set in ENV or on the command line for the script to run. 
- Set `DIGEST_HOURS` to the number of hours of posts to summarize or specify the hours
  on the command line as an argument to --hours.
- Set `MASTODON_INSTANCE` to the Mastodon instance you are connecting to. A bare 
  hostname works. 
- Set `MASTODON_TOKEN` to the private access token you created.
- Set `OPENAI_API_KEY` to the API key you generated.
- Set `OUT_DIR` to the fully qualified path to the folder you keep the original 
  markdown-format summaries that are used to generate a new atom.xml file. By default,
  this is set to "$HOMEDIR/digests"
- Set `SSH_KEY` to the path to the SSH key file you generated.
- Set `FEED_URL` to the URL to the atom.xml file on your web server in the format:
  https://example.com/_feeds/*summary_folder*/atom.xml
- Set `DEST` to the destination in the following format that the `scp` command accepts:
  USER@WEBHOST:example.com/_feeds/*summary_folder*/

## Optional Environment Settings
- Set `MASTODON_PRIORITY` to a comma-separated list of Mastodon accounts that should always be included in the summary.
- Set `DIGEST_INTERESTS` to a comma-separated list of interests for the summarizer to prioritize.
- Set `PROVIDER` to `openai`, `anthropic`, or `ollama` to change the default LLM provider without passing `--provider` on every run. Defaults to `openai`.
- Set `OUTPUT_RULES` to `VERBOSE` or `TERSE` to choose the digest style. `VERBOSE` gives longer theme summaries, says why each must-read post matters, and lists what was skipped. `TERSE` gives short, factual lines with no evaluation. Defaults to `VERBOSE`.
- Set `FEED_AUTHOR` to the name shown as the Atom feed's author. Defaults to "Mastodon Digest".
- Set `TZ` to your local timezone (e.g. `America/New_York`) so digest timestamps use local time instead of the system default

## Command Line Arguments
Most environment settings may be set or overridden with the following command-line arguments to `run.sh`. Values may be set with either `--flag value` or 
`--flag=value` format. An unrecognized flag or missing mandatory environment 
variable makes `run.sh` exit with an error.

- `-h`, `--help` - print usage and exit.
- `--hours N` - hours of timeline to summarize. Overrides `DIGEST_HOURS`.
- `--provider anthropic|ollama|openai` - overrides `PROVIDER`.
- `--output verbose|terse` - digest style. Overrides `OUTPUT_RULES`.
- `--model MODEL` - override the provider's default model.
- `--feed-url https://your_webserver.com/path/to/atom.xml` - used by `build_feed.py`. Overrides `FEED_URL`.
- `--output-dir /path/to/local/folder` - local folder for the digest and feed file. Used by *both* scripts and overrides `OUT_DIR`, including the file `run.sh` uploads afterward.
- `--env_file /path/to/.env` - which `.env` file to load. Must be a fully qualified path. Consumed by `run.sh`; defaults to `.env` in the same folder as `run.sh`.

## Scheduling

Run it on a timer with cron, systemd timers, launchd, or your NAS's task
scheduler.

## License

[GPL-3.0](LICENSE)
