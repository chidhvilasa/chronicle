# Security Policy

## Supported Versions

Chronicle is pre-1.0 and under active development. Only the latest commit on
`main` is supported.

## Reporting a Vulnerability

If you find a security vulnerability in Chronicle, please report it privately
by opening a [GitHub Security Advisory](https://github.com/chidhvilasa/chronicle/security/advisories/new)
rather than a public issue.

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce
- Any relevant logs or proof-of-concept code

We'll acknowledge reports as soon as possible and follow up with a fix
timeline.

## Scope

Chronicle's server binds to `127.0.0.1` by default and is intended to run
locally alongside the agent it's tracing. It is not designed to be exposed to
untrusted networks. Do not run the Chronicle server on a publicly reachable
address without adding your own authentication layer in front of it.
