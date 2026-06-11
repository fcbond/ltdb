# Installing LTDB

## Requirements

- Python 3.12+ (managed automatically by `uv`)
- Apache 2 with `mod_proxy`, `mod_proxy_http`, `mod_headers`
- SQLite3

## Deployment (Apache + gunicorn)

The app runs under gunicorn, with Apache acting as a reverse proxy.
Static files are served directly by Apache.

### 1. Copy the app and set ownership

```bash
sudo cp -r /path/to/ltdb /var/www/ltdb
sudo chown -R www-data:www-data /var/www/ltdb
```

### 2. Set up the Python environment

```bash
# Ensure www-data can write its cache (needed by uv)
sudo mkdir -p /var/www/.cache/uv /var/www/.local/share/uv/python
sudo chown -R www-data:www-data /var/www/.cache /var/www/.local

cd /var/www/ltdb
sudo -u www-data uv sync
```

(`uv` creates `.venv` and installs all dependencies from `pyproject.toml` automatically.
Install `uv` with `curl -LsSf https://astral.sh/uv/install.sh | sh` if not present.)

### 3. Create the log directory

```bash
sudo mkdir -p /var/log/ltdb
sudo chown www-data:www-data /var/log/ltdb
```

### 4. Generate a secret key

Flask uses a secret key to sign session cookies. All gunicorn workers must share
the same key, and it must persist across restarts. Generate one and store it in
`/var/www/ltdb/.env`:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" \
    | sudo tee /var/www/ltdb/.env
sudo chmod 600 /var/www/ltdb/.env
sudo chown www-data:www-data /var/www/ltdb/.env
```

This file is loaded automatically by the service via `EnvironmentFile`. Never
commit it to version control (`.env` is already in `.gitignore`).

### 5. Install and start the gunicorn service

```bash
sudo cp ltdb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ltdb
sudo systemctl status ltdb   # confirm it is running
```

### 6. Configure Apache

```bash
sudo a2enmod proxy proxy_http headers
sudo cp ltdb-apache.conf /etc/apache2/conf-available/ltdb.conf
sudo a2enconf ltdb
sudo systemctl reload apache2
```

The app will be available at `https://compling.upol.cz/ltdb`.

## Adding grammars

Copy compiled `.db` files (and `.dat` files for the demo) to `web/db/`, then
fix permissions so gunicorn (`www-data`) can read them:

```bash
sudo cp path/to/*.db path/to/*.dat /var/www/ltdb/web/db/
sudo chmod 644 /var/www/ltdb/web/db/*.db /var/www/ltdb/web/db/*.dat
```

The parse/generate demo also requires the ACE binary. Download it with:

```bash
cd /var/www/ltdb && source .venv/bin/activate
python scripts/setup_ace.py
```

## Updating the app

```bash
cd /path/to/ltdb && git pull
sudo rsync -a --exclude='.git' --exclude='.venv' . /var/www/ltdb/
sudo chmod 644 /var/www/ltdb/web/db/*.db /var/www/ltdb/web/db/*.dat
cd /var/www/ltdb && sudo -u www-data uv sync
sudo systemctl restart ltdb
```

## Troubleshooting

Check gunicorn logs:
```bash
sudo journalctl -u ltdb -f
sudo tail -f /var/log/ltdb/error.log
```

Check Apache logs:
```bash
sudo tail -f /var/log/apache2/error.log
```

If encodings are wrong, add to `/etc/apache2/apache2.conf`:
```
SetEnv PYTHONIOENCODING utf8
```
