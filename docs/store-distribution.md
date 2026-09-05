# Store distribution

PDrive Desktop targets Flathub first because one sandboxed package reaches Zorin OS,
Ubuntu, Fedora, Debian, and other Flatpak-enabled distributions. Ubuntu App Center can
be considered separately through Snap after the Flathub permissions and browser/keyring
integration have completed public review.

The verified application ID is `io.github.alpereneser.pdrive-desktop`. The visible name
remains **PDrive Desktop**. Store metadata may use “Proton Drive” as a search keyword and
describe compatibility, but must always state that PDrive is an independent community
project not affiliated with or endorsed by Proton AG.

The Flatpak build:

- uses the current GNOME runtime;
- bundles Proton's official CLI from its published URL with the published SHA-512;
- disables debug extraction for the Bun-compiled CLI so its embedded application is not
  corrupted;
- requests network, display, and Secret Service access only;
- relies on document portals for user-selected local files;
- disables the Debian self-updater because Flatpak owns application updates.

Run the upstream manifest locally with Flatpak Builder before every submission. The
AppStream file, desktop file, manifest linter, full build, packaged CLI version command,
and GUI startup must all succeed.

Flathub's current generative-AI policy requires disclosure of AI-generated packaging and
forbids an AI agent from opening or automating the submission pull request or writing its
PR conversation. A human maintainer must therefore review the manifest, create the
Flathub fork and pull request through GitHub, disclose the assistance, and personally
handle reviewer communication.
