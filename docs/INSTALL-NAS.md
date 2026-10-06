# Installing EmberProof on a NAS (no terminal needed)

Half the people who want this will not open a shell. These are the click-through
paths for the three NAS platforms people actually own.

In every case the shape is the same:

- an **image** built from the project (or your own build)
- a **port** to reach it on, usually `8787`
- a **volume** mounted at `/data` — this is where your inventory lives, so it is
  the folder you back up
- a **token**, so nobody else on your network can read your inventory

Everything the app stores lives in that one mounted folder: `emberproof.db`,
`media/originals/`, `media/thumbs/`, and `exports/`. Copy the folder, keep the
inventory.

---

## Synology (DSM 7.2+, Container Manager)

1. **Container Manager → Registry**, search for `emberproof`. If it is not
   published, use **Image → Add → Add from file** and select a `emberproof.tar`
   you built with `docker save emberproof > emberproof.tar` on another machine.
2. **Container Manager → Image → Run.** Name it `emberproof`.
3. **Advanced Settings → Enable auto-restart.**
4. **Port Settings:** local port `8787` → container port `8787` (TCP).
5. **Volume:** add a folder, e.g. `docker/emberproof/inventory`, mount path
   `/data`.
6. **Environment:** add `EMBERPROOF_TOKEN` with a long random value.
7. Apply, then browse to `http://<nas-ip>:8787`. The browser will ask for a
   username and password — the username is anything, the password is your token.

To upgrade later: stop the container, pull/replace the image, start it again.
Your data is in the mounted folder and is untouched by an image change.

## Unraid

1. **Docker → Add Container.**
2. Repository: `emberproof` (or your locally built tag).
3. Add a port mapping `8787` → `8787`.
4. Add a path: container `/data`, host `/mnt/user/appdata/emberproof`.
5. Add a variable `EMBERPROOF_TOKEN` = a long random string.
6. Set **Restart Policy** to `unless-stopped`.
7. Apply. Open `http://<unraid-ip>:8787`.

Unraid's Community Applications template can be submitted later once there is a
published image; until then the manual container above is the whole install.

## QNAP (Container Station)

1. **Container Station → Create → Create Application.**
2. Paste a compose file (see `docker-compose.yml` in the repo) and edit the
   volume path to somewhere under `/share/CACHEDEV1_DATA/`.
3. Set `EMBERPROOF_TOKEN` in the environment section.
4. Create, then open `http://<qnap-ip>:8787`.

## Any Docker host

```bash
docker build -t emberproof .
docker run -d --name emberproof --restart unless-stopped \
  -p 8787:8787 \
  -v /srv/emberproof:/data \
  -e EMBERPROOF_TOKEN='a-long-random-string' \
  emberproof
```

Or with compose, after editing the token in the file:

```bash
docker compose up -d
```

---

## Before you put it on your network

An inventory of your home is a burglary shopping list. It names your television,
its model number, and often what room it is in.

- **Keep a token on** whenever the port is reachable from anywhere but your own
  machine. Without one, anyone on the network can read and delete everything.
- Do **not** port-forward it to the internet. If you want it from outside your
  house, use a VPN (Tailscale, WireGuard) or a reverse proxy that terminates TLS
  and authenticates — not a forwarded port.
- Put the data folder on an **encrypted** volume if the NAS supports it. An
  unencrypted copy of this data on a disk that walks away is the whole problem.
- If you bind to a non-loopback address and forget the token, EmberProof
  generates one for you and prints it at startup rather than leaving you open.

## Making a backup from a NAS

Every property page has a **Full backup** button. It downloads a single ZIP with
a consistent database snapshot, every original photo, and a manifest. Save it
somewhere that is not the NAS.

Then prove it, from any machine with Python:

```bash
python run.py --inspect ~/Downloads/your-backup.zip     # what is in it
python run.py --restore ~/Downloads/your-backup.zip --data-dir ./restored
```

A backup you have never restored is not a backup. Do this once now.