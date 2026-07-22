# Windows launcher sources

Stemmy's executable `.bat` launchers are intentionally excluded from Git through `*.bat` in `.gitignore`.

The `.bat.txt` files in this folder are inert plain-text documentation containing the exact v1.5 launcher source. To recreate one locally, save it without the final `.txt` extension and use Windows CRLF line endings.

Do not commit recreated `.bat` files. Ready-to-run launchers belong only in local working folders and packaged Windows release assets.

See [BUILD.md](../../BUILD.md) for installation order, launcher purpose, and troubleshooting.
