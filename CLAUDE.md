# label-sku-stamper - notes for AI assistants

- Whenever you change the app's behaviour, settings, outputs or setup, update ALL of these in the same piece of work:
  1. `README.md` (this repo)
  2. `docs/build-user-guide.js`, then rebuild `docs/Label-Stamper-User-Guide.docx` (`npm install docx`, `node docs/build-user-guide.js`)
  3. The SOPs in `C:\SOP beemine\beemine-manual`: SOP-FUL-001 (`06-fulfilment-and-customer-service/sop-label-sku-stamping.md`, how to use) and SOP-TEC-001 (`07-tech-and-automation/label-sku-stamper-tech.md`, technical), plus a line in `00-meta/changelog.md`, and commit there.
- Never commit customer data (PDFs, CSVs, PNGs, `Labels/`, `done/`). Check `git status` first. The only PNGs that belong in git are the logo files in `assets/` (allowed by a `!assets/*.png` line in `.gitignore`); they are not customer data.
- Commit with the GitHub no-reply email already set in this repo's git config; do not change it.
- After every piece of work, commit AND `git push` this repo and any other Beemine repo you touched (the SOP manual, the launcher, the sync...), so GitHub is always current. Never force-push.
- Run `py -m unittest discover -s tests` after every code change; add a test when a real slip is misread.
- Keep `defaults/settings.json` and `defaults/sort_groups.json` (known-good reset copies) in step with any new setting or documented structure.
