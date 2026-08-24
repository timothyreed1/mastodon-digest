# How to Install Mastodon Digest

Mastodon Digest is a Python script that generates a summary of your Mastodon feed and uploads it in XML format to folder on your web server that you or anyone with the path can subscribe to with an RSS reader. 

This software requires a computer to run the script and a remote web server to host the summary file. 

## File Manifest
`mastodon-digest.py`
`build_feed.py`
`run.sh`
``.env` environment variables template that you customize.

The default LLM provider is `openai` with `gpt-4o-mini`. `--provider anthropic` uses `claude-haiku-4-5-20251001`, `--provider ollama` runs locally with no key.
Each run logs provider, model, and input/output token counts to `run.log`.

## 1. Create a Mastodon token

On your instance, go to Preferences> Development> New application. 

* Uncheck everything except `read:statuses`. 
* Leave redirect URI at the default `urn:ietf:wg:oauth:2.0:oob`. 
* Submit, then copy "Your access token" from the application detail page.

## 2. Create an LLM access token

Go to your LLM API provider and generate an access token. 

```[NOTE]
It's good practice to set the budget for the key, or associate the key with a project that has a budget set. Using an inexpensive model, API cost should be under $1/month. A busy 12 hour window is roughly 300 posts, about 60k input tokens plus 1.5k output, which at gpt-4o-mini rates is about a cent per run, so roughly 60 cents a month at twice daily. Setting a $5 cap leaves room for a chatty timeline. Switching to a higher cost model like gpt-4o costs roughly 15x, so budget $20 if you do. The `max_pages: 20` ceiling in the script caps a single run at 800 posts.

```

## 3. Create a hard-to-find directory on the web host
At the end of the process, the script will save the summary to `atom.xml` and upload it to your web server over SSH. This set up assumes that your document root folder for your website is the folder `~/webhost.com` on your web server. 

To create the folder path using a hard-to-find folder name, run this command on the webhost:

    R=$(openssl rand -hex 4); echo $R
    mkdir -p ~/example.com/_feeds/$R
    printf 'Header set X-Robots-Tag "noindex, nofollow"\n' > ~/webhost.com/_feeds/.htaccess

Save this path to the appropriate variable in your .env.
## 4. SSH key
* Since the script will run as you, generate an SSH using your own account:

    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_digest -N ""
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/id_ed25519_digest
    chmod 644 ~/.ssh/id_ed25519_digest.pub

* Install it on the web host and test:

    ssh-copy-id -i ~/.ssh/id_ed25519_digest.pub USER@WEBHOST

* If `ssh-copy-id` is missing, run these commands:
	`cat ~/.ssh/id_ed25519_digest.pub | ssh USER@WEBHOST "cat >> ~/.ssh/authorized_keys"`

* Test to seed `known_hosts`, which the `StrictHostKeyChecking=yes` in `run.sh` requires, and ensure that the connection works.
	`ssh -i ~/.ssh/id_ed25519_digest USER@WEBHOST true` 

* You can optionally harden the connection by editing !/.ssh/authorized_keys on the web host and inserting 'restrict,no-pty' to ensure that a compromised sending machine can't access the server:
	`restrict,no-pty ssh-ed25519 ABC_keymaterial_123 yourname@yourhost.com`
## 5. Install

Install the software on your local computer. Create the folder that the software will be run from:
`mkdir -p ~/mastodon-digest ~/digests`
`chmod 700 ~/mastodon-digest ~/digests`
`cd ~/mastodon-digest`

Install library packages needed by the Python script:
`python3 -m venv venv`
`venv/bin/pip install requests markdown nh3`

* Copy `mastodon-digest.py`, `build_feed.py`, and `run.sh` into that directory.
* Create your .env file and customize it for your environment. 

    MASTODON_INSTANCE=https://hachyderm.io
    MASTODON_TOKEN=paste_token_here
    OPENAI_API_KEY=paste_key_here
    DIGEST_HOURS=12
    OUT_DIR="$HOMEDIR/digests"
    SSH_KEY="$HOMEDIR/.ssh/id_ed25519_digest"
    FEED_URL=https://example.com/_feeds/*summary_folder*/atom.xml
    DEST=USER@WEBHOST:example.com/_feeds/*summary_folder*/
    
* Optionally add must-read high priority accounts and interests:
    MASTODON_PRIORITY=someone@hachyderm.io,someoneelse@fosstodon.org
    DIGEST_INTERESTS="self-hosting, distributed systems, photography"

* Set file permissions:
    chmod 600 .env
    chmod +x run.sh

You can customize the program's behavior by setting environment variables in .env; otherwise, the files `mastodon-digest.py` and `run.sh` do not need customization or editing.
## 6. Test the Install

    ~/mastodon-digest/run.sh && tail -5 ~/mastodon-digest/run.log

The log will show post count, provider, model, token counts, and other information. Open the URL to the summary file in a browser to confirm that it renders correctly.
## 7. Schedule with Cron

If your system has crontab, you can set it to run twice daily with `crontab -e` per this example:

    0 7,19 * * * $HOME/mastodon-digest/run.sh

Note that cron doesn't give notifications on run failures, so check run.log if you don't see any updates for a while.

Other schedulers you can use include systemd timers or anacron on Linux, launchd on MacOS, or Task Scheduler on Synology or QNAP.

## 8. Subscribe With Your RSS Reader

Add `https://example.com/_feeds/RANDOM/atom.xml` in your RSS reader. Confirm the
must-read links are tappable.

## Notes
- An OS upgrade can replace the system Python and break the venv. If the job goes
  quiet after one, rebuild it per the above `venv` instructions.
