# Release & store submission checklist

Nothing here has been published yet. Do these in order.

## 1. Publish the source

```sh
cd ~/monad
gh repo create numbpill3d/monad --public --source=. --push
git push origin v1.0.0
```

The app ID `io.github.numbpill3d.Monad` requires the GitHub user/org `numbpill3d`
to own `github.com/numbpill3d/monad`. The screenshot URLs in the metainfo point at
`raw.githubusercontent.com/numbpill3d/monad/main/data/screenshots/`, so they work once pushed.

## 2. Flathub (also covers Bazaar, GNOME Software, KDE Discover)

1. Put the tag's commit SHA in `packaging/flatpak/flathub/io.github.numbpill3d.Monad.yml`:
   `sed -i "s/COMMIT_SHA_OF_v1.0.0/$(git rev-parse v1.0.0^{commit})/" packaging/flatpak/flathub/io.github.numbpill3d.Monad.yml`
2. Test build + lint (needs ~2 GB free):
   ```sh
   flatpak install -y flathub org.flatpak.Builder
   cd packaging/flatpak/flathub
   flatpak run org.flatpak.Builder --force-clean --sandbox --user --install --install-deps-from=flathub --ccache --mirror-screenshots-url=https://dl.flathub.org/media/ --repo=repo builddir io.github.numbpill3d.Monad.yml
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest io.github.numbpill3d.Monad.yml
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo repo
   flatpak run io.github.numbpill3d.Monad
   ```
3. Fork https://github.com/flathub/flathub, branch from `new-pr`, add the three files in
   `packaging/flatpak/flathub/`, and open a PR against `new-pr`.
4. In the PR description, state the 2% developer fee clearly. Reviewers check for
   undisclosed or manipulative behaviour, and the fee is disclosed in the app, README and metainfo.
5. Bazaar lists Flathub apps, so once the PR is merged Monad shows up there with no extra step.

## 3. AUR

```sh
cd packaging/aur
updpkgsums                      # replaces the SKIP for the GitHub release tarball
makepkg -si                     # build + install test
makepkg --printsrcinfo > .SRCINFO
git clone ssh://aur@aur.archlinux.org/monad.git aur-monad
cp PKGBUILD .SRCINFO aur-monad/ && cd aur-monad
git add PKGBUILD .SRCINFO && git commit -m "Initial upload: monad 1.0.0" && git push
```

(Needs an AUR account with your SSH key.)

## Every release

- Bump `VERSION` in `monad/constants.py`, `pkgver` in the PKGBUILD, and add a `<release>` to the metainfo.
- Tag `vX.Y.Z`, update the Flathub manifest's `tag` + `commit`, then `updpkgsums` + `.SRCINFO` for the AUR.
