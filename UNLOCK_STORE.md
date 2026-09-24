# ActionNotes unlock store

The source is `SharedProjectNotes/projects/rupertunlocks.md`. Add a normal
unchecked task with one attached image and a sterling price:

```md
- [ ] A game or other reward
  ![Photo](../attachments/rupertunlocks/photo.png)

  £10.49
```

Check the task (`- [x]`) or delete it to remove it from the *visible* store.
The Kindle never edits the note. Its saved redemption ledger continues to
count spent points after a reward leaves the store.

The hourly `Publish unlock store` workflow checks out the private notes
repository, crops each attached image to a 220 × 220 square, converts it to
16-level greyscale, and publishes `published/unlocks/catalog.tsv` and images
here. Points are five per pound, rounded up to the next whole point.

## One-time access

Create a fine-grained GitHub token with **Contents: read** on
`grahamwheaton/SharedProjectNotes` only. Save it as the Actions secret
`RUPERT_NOTES_TOKEN` in `grahamwheaton/rupert-reading-missions`. Then run
**Actions → Publish unlock store → Run workflow** once, or wait for the hourly
job. The job fails clearly if the secret is missing; it cannot use the content
repository's built-in token to read another private repository.

The Kindle software update also needs to be published through the existing
private `rupert-device-signing` **Publish device update** workflow, which
builds the latest device source and signs it. That update teaches the Kindle
to download the generated catalog. Until it installs, the existing store
remains as before.

The attachment filename becomes the reward ID. Keep that filename if changing
the title or price of a reward that Rupert may already have requested; using
a different attachment filename makes a new reward ID.
