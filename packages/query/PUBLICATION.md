# Public-preview publication procedure

Keep the research repository private. Export only the approved tracked paths
from a committed revision, without Git history or local checkpoint refs. The
export tool adds the focused README, issue/PR templates, contribution and security
entry points, and an inventory of every exported file. It does not create a remote
repository, upload a package, push, change visibility or rewrite private history.

## Prepare the review candidate

From the research repository root, after committing the intended release files:

```sh
python packages/query/tools/prepare_publication.py /path/to/new-review-folder \
  --repository https://github.com/OWNER/PUBLIC_REPOSITORY \
  --deny-terms-file /path/to/private-release-exclusions.txt
```

The terms file has one confidential name/phrase per line and stays outside the
export. Never commit it or include its contents in release notes. The scan checks
text and supported nested gzip/tar/zip archives; it fails on matching contents,
unreadable archives, unsafe members or nesting/size limits (1 GiB per decoded
payload, eight nested containers). It is a name-exclusion
check, not a general secret scanner or image OCR. Review any images separately and
run a credential scan before publishing. Scan credentials offline; do not probe
whether detected credentials work.

The repository URL updates only the exported package metadata. Historical raw
evidence and source identities remain unchanged; historical origin URLs inside
archived evidence may refer to the private research repository. The public current
README links to locally retained evidence, not to private CI as proof of current
validation. Set `--ref` only to the committed revision you intend to publish.

## Validate the actual exported distribution

```sh
cd /path/to/new-review-folder
python -m build packages/query --outdir packages/query/dist/release
python packages/query/tools/audit_distribution.py packages/query/dist/release
python -m pip install packages/query/dist/release/orbweaver_query-1.0.0.dev1-py3-none-any.whl
python -I -m pytest -q packages/query/tests -o pythonpath=
python -I -m orbweaver_query.demo
```

Also run the movie walkthrough and CSV example from this export. Keep the resulting
artifact hashes and actual pass/skip counts. A metadata-only change still produces
a different wheel hash; distinguish package-content identity from archive identity.

## Before the external publication step

Confirm the public destination and version, and review the exported inventory,
README and evidence. GitHub supports private vulnerability reporting for public
repositories: enable and verify it immediately after the visibility change and
before announcing the release ([GitHub documentation](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)). The package
is a development preview; no stable 1.0 promise or broad superiority claim is
supported. Record both the requested measurement conditions and actual host
telemetry. A requested quiet window with background activity is not isolated evidence.

Publication is a separate action: create/upload only from the reviewed snapshot,
then validate links and installation from the actual public destination. Never
mirror all refs from the research repository. No operation in this document has
been performed merely because the local export exists.
