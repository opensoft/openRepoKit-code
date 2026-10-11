# Code leg

Run from assembly: `python3 code/openRepoKit verify` and
`python3 -m unittest discover -s code/tests -v`.

The `components/` mounts are unmodified upstream sources. Exact commits live
in `../spec/contracts/components.json`. Tools' nested Shape remains its own
dependency, distinct from Kit's runtime Shape. Python 3.10+, Git, Bash and
PyYAML are prerequisites. Installation does not install prerequisites.
